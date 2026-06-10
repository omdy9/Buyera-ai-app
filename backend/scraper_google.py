"""
scraper_google.py  — v7  (full pipeline + directory extraction + quality slider)
"""

import os
import re
import logging
import requests

from bs4 import BeautifulSoup
from serpapi import GoogleSearch
from dotenv import load_dotenv
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

SERP_API_KEY     = os.getenv("SERP_API_KEY", "")
NODE_CRAWLER_URL = os.getenv("NODE_CRAWLER_URL", "http://127.0.0.1:5050")

logger = logging.getLogger(__name__)

COUNTRY_GL = {
    "india": "in", "usa": "us", "uk": "gb", "uae": "ae",
    "dubai": "ae", "germany": "de", "canada": "ca",
    "australia": "au", "singapore": "sg", "china": "cn",
    "italy": "it", "france": "fr", "japan": "jp",
}

BAD_DOMAINS = [
    "justdial","yellowpages","sulekha","tradeindia","indiamart",
    "exportersindia","linkedin","facebook","instagram","twitter",
    "youtube","amazon","flipkart","wikipedia","wikidata",
    "naukri","monster","indeed","glassdoor",
    "blogspot","wordpress.com","medium.com",
]

_FREE_HOST_RE = re.compile(r"\.(blogspot|wordpress\.com|wixsite|weebly)\.", re.I)
_QUERY_STRIP  = re.compile(r"\b(top|best|leading|list\s+of|ranking|reviews?)\b", re.I)

# Social media patterns
_SOCIAL_PATTERNS = {
    "linkedin":  re.compile(r'https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?', re.I),
    "twitter":   re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/(?!share|intent)[A-Za-z0-9_]+/?', re.I),
    "facebook":  re.compile(r'https?://(?:www\.)?facebook\.com/(?!sharer)[A-Za-z0-9_.]+/?', re.I),
    "instagram": re.compile(r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+/?', re.I),
    "youtube":   re.compile(r'https?://(?:www\.)?youtube\.com/(?:c/|channel/|user/|@)[A-Za-z0-9_\-]+/?', re.I),
    "whatsapp":  re.compile(r'https?://(?:wa\.me|api\.whatsapp\.com/send)[/?][^\s"\'<>]+', re.I),
}

_CITY_LIST = [
    "Mumbai","Delhi","Bangalore","Bengaluru","Hyderabad","Ahmedabad","Chennai",
    "Kolkata","Surat","Pune","Jaipur","Lucknow","Nagpur","Indore","Thane",
    "Bhopal","Patna","Vadodara","Ghaziabad","Ludhiana","Agra","Nashik",
    "Faridabad","Meerut","Rajkot","Varanasi","Aurangabad","Coimbatore",
    "Vijayawada","Noida","Gurgaon","Gurugram","Chandigarh","Mysore","Mysuru",
    "Amritsar","Kochi","Cochin","Dubai","Abu Dhabi","Singapore","Hong Kong",
    "Shanghai","Beijing","London","New York","Toronto","Sydney","Melbourne",
    "Frankfurt","Paris","Tokyo","Osaka",
]
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _CITY_LIST) + r")\b", re.I
)

_COUNTRY_SIGNALS = {
    "India":     ["india","indian",".in","bharat"],
    "UAE":       ["uae","dubai","abu dhabi","emirates"],
    "USA":       ["usa","united states","america"],
    "UK":        ["uk","united kingdom","britain","england"],
    "Germany":   ["germany","german","deutschland"],
    "Singapore": ["singapore"],
    "Canada":    ["canada"],
    "Australia": ["australia","australian"],
    "China":     ["china","chinese"],
    "Italy":     ["italy","italian"],
}

_INCORP_RE = [
    re.compile(r"(?:incorporated|established|founded|since|est\.?)\s*(?:in\s*)?(\d{4})", re.I),
    re.compile(r"(?:year\s+of\s+(?:incorporation|establishment))[:\s]+(\d{4})", re.I),
    re.compile(r"\bsince\s+(\d{4})\b", re.I),
]

_TURNOVER_RE = [
    re.compile(r"(?:turnover|revenue|sales)[:\s]+(?:rs\.?|inr|usd|\$)?\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh|million|billion)?", re.I),
    re.compile(r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh)\s*(?:turnover|revenue)", re.I),
]

_CERT_RE = re.compile(
    r"\b(ISO\s*\d{4,5}(?::\d{4})?|BIS|CE\b|FDA|GMP|HACCP|FSSAI|OHSAS|"
    r"SA\s*8000|IATF|REACH|RoHS|IS\s*\d+|R-\d+|NABL|CRISIL|ZED)\b", re.I
)

_CHANNEL_KW = {
    "Manufacturer": ["manufacturer","manufacturing","we manufacture","our factory","fabricat","oem","odm","production capacity"],
    "Importer":     ["importer","import","we import","imported from","iec","cif","fob","incoterms"],
    "Wholesaler":   ["wholesaler","wholesale","bulk supply","moq","minimum order quantity","bulk order"],
    "Distributor":  ["distributor","distribution","authorised distributor","authorized distributor","channel partner"],
    "Trader":       ["trader","trading company","trading house","buy and sell"],
    "Retailer":     ["retailer","retail","showroom","shop online","add to cart","buy now"],
}

INDUSTRY_MAP = {
    "Electronics":     ["electronics","semiconductor","pcb","led","display","solar panel"],
    "Pharmaceuticals": ["pharma","pharmaceutical","medicine","drug","api","tablet","capsule"],
    "Textiles":        ["textile","fabric","garment","apparel","yarn","weaving"],
    "Chemicals":       ["chemical","polymer","resin","adhesive","solvent","dye","pigment"],
    "Machinery":       ["machinery","machine","equipment","cnc","lathe","pump","valve"],
    "Food & Beverage": ["food","beverage","spice","grain","dairy","snack"],
    "Automotive":      ["automotive","automobile","vehicle","car","tyre","auto parts"],
    "Construction":    ["construction","cement","steel","rebar","tile","pipe","sanitary"],
    "IT & Software":   ["software","it services","saas","technology","cloud","erp"],
    "Healthcare":      ["healthcare","hospital","medical device","diagnostics","surgical"],
    "Logistics":       ["logistics","freight","shipping","warehouse","courier"],
    "Agriculture":     ["agriculture","agro","fertilizer","pesticide","seed","crop"],
    "Energy":          ["energy","solar","wind","power","battery","generator","inverter"],
    "Retail":          ["retail","ecommerce","e-commerce","marketplace","fmcg"],
}

EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}")
PHONE_RE  = re.compile(r"(?:\+91[\-\s]?|0)?[6-9]\d{9}|\+\d{1,3}[\s\-]?\d{6,12}")

CRAWL_PATHS = [
    "", "/about", "/about-us", "/contact", "/contact-us",
    "/products", "/our-products", "/services", "/team",
    "/certifications", "/export", "/international",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_query(query: str, country_filter: str = "") -> str:
    q = _QUERY_STRIP.sub("", query).strip()
    q = re.sub(r"\s{2,}", " ", q)
    if country_filter and country_filter.lower() not in q.lower():
        q = f"{q} {country_filter}"
    return q.strip()


def _is_company_url(url: str) -> bool:
    if not url:
        return False
    netloc = urlparse(url).netloc.lower().replace("www.", "")
    for bad in BAD_DOMAINS:
        if bad in netloc:
            return False
    if _FREE_HOST_RE.search(netloc):
        return False
    return True


def _clean_title(title: str) -> str:
    return re.sub(
        r"\s*[\|\-–—:]+\s*(home|welcome|official\s+website|about|contact|homepage)\s*$",
        "", title, flags=re.I
    ).strip()


def _da_heuristic(url: str) -> float:
    netloc = urlparse(url).netloc.lower().replace("www.", "")
    score  = 0.5
    if netloc.endswith(".com"):   score += 0.20
    if any(netloc.endswith(t) for t in [".in",".ae",".co.uk",".com.au",".sg",".ca",".co.in"]):
        score += 0.15
    if len(netloc.split(".")) > 3: score -= 0.10
    return round(min(max(score, 0.0), 1.0), 3)


def _detect_social(html: str) -> dict:
    social = {}
    for platform, pattern in _SOCIAL_PATTERNS.items():
        m = pattern.search(html)
        if m:
            url = m.group(0).rstrip("/")
            # Filter out share/generic links
            if platform == "twitter" and any(x in url for x in ["/share","/intent"]):
                continue
            if platform == "facebook" and "/sharer" in url:
                continue
            social[platform] = url
    return social


def _detect_city(text: str, html: str = "") -> str:
    m = re.search(r'"addressLocality"\s*:\s*"([^"]{2,40})"', html, re.I)
    if m:
        return m.group(1).strip()
    m = _CITY_RE.search(text)
    return m.group(1).title() if m else ""


def _detect_country(text: str) -> str:
    tl = text.lower()
    for country, signals in _COUNTRY_SIGNALS.items():
        if any(s in tl for s in signals):
            return country
    return ""


def _detect_incorporation(text: str) -> str:
    for pat in _INCORP_RE:
        m = pat.search(text)
        if m:
            return m.group(1)
    return ""


def _detect_turnover(text: str) -> str:
    for pat in _TURNOVER_RE:
        m = pat.search(text)
        if m:
            val  = m.group(1).replace(",","")
            unit = (m.group(2) or "").lower() if m.lastindex >= 2 else ""
            return f"₹{val} {unit}".strip() if unit else f"₹{val}"
    return ""


def _detect_certs(text: str) -> list:
    return list(set(m.group(0).strip() for m in _CERT_RE.finditer(text)))[:10]


def _detect_channel(text: str) -> str:
    tl = text.lower()
    scores = {ch: sum(1 for kw in kws if kw in tl)
              for ch, kws in _CHANNEL_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def _detect_industry(text: str) -> str:
    tl = text.lower()
    for industry, kws in INDUSTRY_MAP.items():
        if any(kw in tl for kw in kws):
            return industry
    return ""


def _detect_size(text: str) -> str:
    patterns = [
        (re.compile(r"\b(\d{1,4})\s*[-–to]+\s*(\d{2,5})\s*(employees|staff)\b", re.I), "{a}–{b}"),
        (re.compile(r"\b(\d{2,5})\s*\+?\s*(employees|staff|people|workers)\b", re.I), "{n}+"),
        (re.compile(r"team\s+of\s+(\d+)", re.I), "team of {n}"),
        (re.compile(r"(1[-–]10|11[-–]50|51[-–]200|201[-–]500|501[-–]1000)\s*(employees)?", re.I), "{n}"),
    ]
    for pat, label in patterns:
        m = pat.search(text)
        if m:
            if "{a}" in label: return f"{m.group(1)}–{m.group(2)}"
            return label.replace("{n}", m.group(1))
    return ""


def _detect_export_markets(text: str) -> list:
    markets = ["usa","uk","europe","middle east","uae","dubai","africa",
               "southeast asia","australia","canada","germany","france",
               "japan","china","bangladesh","sri lanka","nepal"]
    tl = text.lower()
    return [m.title() for m in markets if m in tl]


# ---------------------------------------------------------------------------
# Deep website crawler
# ---------------------------------------------------------------------------

def _fetch_page(url: str, timeout: int = 8) -> tuple:
    try:
        resp = requests.get(
            url, timeout=timeout,
            headers={"User-Agent": "Mozilla/5.0 (compatible; BuyeraBot/2.0)"},
            allow_redirects=True,
        )
        if resp.status_code != 200:
            return "", ""
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script","style","nav","footer","header","noscript"]):
            tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:6000], html[:30000]
    except Exception:
        return "", ""


def deep_crawl(website: str, query: str = "") -> dict:
    base     = website.rstrip("/")
    all_text = ""
    all_html = ""
    emails   = set()
    phones   = set()

    # Try Node crawler first
    node_ok = False
    try:
        resp = requests.post(f"{NODE_CRAWLER_URL}/crawl",
                             json={"url": website}, timeout=15)
        if resp.status_code == 200:
            d = resp.json()
            all_text += " " + d.get("content", "")
            all_html += d.get("html", "")
            if d.get("email"): emails.add(d["email"])
            if d.get("phone"): phones.add(d["phone"])
            node_ok = True
    except Exception:
        pass

    # BS4 crawl additional pages
    paths = CRAWL_PATHS[:6] if node_ok else CRAWL_PATHS

    def _crawl(path):
        return _fetch_page(base + path if path else base)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_crawl, p): p for p in paths}
        for future in as_completed(futures, timeout=25):
            try:
                text, html = future.result(timeout=10)
                if text:
                    all_text += " " + text
                    all_html += html
                    for m in EMAIL_RE.finditer(text):
                        emails.add(m.group())
                    for m in PHONE_RE.finditer(text):
                        phones.add(m.group().strip())
            except Exception:
                pass

    all_text = all_text[:12000].strip()
    all_html = all_html[:50000]

    clean_emails = [e for e in emails
                    if not re.search(r"\.(png|jpg|gif|svg|ico|css|js)$", e, re.I)
                    and len(e) < 80]
    best_email = next(
        (e for e in clean_emails
         if not re.search(r"^(noreply|no-reply|donotreply)", e, re.I)),
        clean_emails[0] if clean_emails else ""
    )

    social = _detect_social(all_html)

    return {
        "content":            all_text,
        "all_html":           all_html,
        "email":              best_email,
        "phone":              sorted(phones, key=len, reverse=True)[0] if phones else "",
        "city":               _detect_city(all_text, all_html),
        "country_detected":   _detect_country(all_text),
        "incorporation_date": _detect_incorporation(all_text),
        "company_size":       _detect_size(all_text),
        "channel_type":       _detect_channel(all_text),
        "industry_detected":  _detect_industry(all_text),
        "annual_turnover":    _detect_turnover(all_text),
        "certifications":     _detect_certs(all_text),
        "export_markets":     _detect_export_markets(all_text),
        "active_website":     website,
        # Social media — all platforms
        "linkedin_url":       social.get("linkedin",  ""),
        "twitter_url":        social.get("twitter",   ""),
        "facebook_url":       social.get("facebook",  ""),
        "instagram_url":      social.get("instagram", ""),
        "youtube_url":        social.get("youtube",   ""),
        "whatsapp_url":       social.get("whatsapp",  ""),
        "social_links":       social,
    }


# ---------------------------------------------------------------------------
# Full enrichment — crawl + DeepSeek contact + Grok validation
# ---------------------------------------------------------------------------

def enrich_company(company: dict, run_compliance: bool = False,
                   query: str = "", quality_threshold: int = 0) -> dict:
    website = company.get("website", "")
    name    = company.get("company", "")

    logger.info("Enriching: %s (%s)", name, website)

    # Step 1: Deep crawl
    crawl = deep_crawl(website, query=query)
    company.update({k: v for k, v in crawl.items()
                    if k not in ("content","all_html")})
    company["content"] = crawl["content"]

    # Step 2: LLM pipeline (DeepSeek contact + Grok validation — parallel)
    try:
        from llm import full_llm_pipeline, extract_directory_companies
    except ImportError:
        from .llm import full_llm_pipeline, extract_directory_companies

    llm = full_llm_pipeline(
        query=query,
        company=name,
        website=website,
        content=crawl["content"],
    )

    # Apply LLM results
    if llm.get("summary"):
        company["ai_summary"] = llm["summary"]
    if llm.get("products"):
        company["products"] = llm["products"]

    # LLM overrides rule-based where better
    for comp_field, llm_field in [
        ("channel_type",       "channel_type"),
        ("industry_detected",  "industry"),
        ("company_size",       "company_size"),
        ("city",               "city"),
        ("country_detected",   "country"),
        ("incorporation_date", "incorporation_date"),
        ("annual_turnover",    "annual_turnover"),
        ("contact_person",     "contact_person"),
        ("contact_email",      "contact_email"),
        ("linkedin_url",       "linkedin_url"),
    ]:
        if llm.get(llm_field) and not company.get(comp_field):
            company[comp_field] = llm[llm_field]

    # DeepSeek-specific contact fields
    company["contact_title"]    = llm.get("contact_title",    "")
    company["contact_linkedin"] = llm.get("contact_linkedin", "")
    company["contact_confidence"] = llm.get("confidence",    "low")
    company["usp"]              = llm.get("usp",             "")
    company["key_customers"]    = llm.get("key_customers",   [])
    company["is_directory"]     = llm.get("is_directory",    False)
    company["is_valid_lead"]    = llm.get("is_valid_lead",   True)
    company["rejection_reason"] = llm.get("rejection_reason","")
    company["grok_score"]       = llm.get("relevance_score", 5)

    # Merge certs/exports from both sources
    company["certifications"] = list(set(
        crawl.get("certifications", []) +
        [str(c) for c in llm.get("certifications", [])]
    ))[:15]
    company["export_markets"] = list(set(
        crawl.get("export_markets", []) +
        [str(e) for e in llm.get("export_markets", [])]
    ))[:15]

    # Directory extraction — if Grok says it's a directory, extract companies
    if company.get("is_directory") and crawl["content"]:
        logger.info("Directory detected: %s — extracting companies", website)
        dir_companies = extract_directory_companies(website, crawl["content"])
        company["directory_companies"] = dir_companies
        company["directory_count"]     = len(dir_companies)

    # Compliance check
    if run_compliance:
        try:
            from cert_checker import check_company_compliance
        except ImportError:
            try:
                from .cert_checker import check_company_compliance
            except ImportError:
                check_company_compliance = None
        if check_company_compliance:
            try:
                compliance = check_company_compliance(name, website)
                company["compliance"] = compliance
                mca = compliance.get("mca", {})
                if mca.get("incorporation_date") and not company.get("incorporation_date"):
                    company["incorporation_date"] = mca["incorporation_date"]
            except Exception as exc:
                logger.warning("Compliance check failed: %s", exc)
                company["compliance"] = {"compliance_gaps": [], "compliance_score": 1.0}

    return company


def parallel_enrich(companies: list, max_workers: int = 3,
                    run_compliance: bool = False, query: str = "",
                    quality_threshold: int = 0) -> list:
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(enrich_company, c, run_compliance, query, quality_threshold): c
            for c in companies
        }
        for future in as_completed(futures, timeout=120):
            try:
                result = future.result(timeout=90)
                enriched.append(result)
            except Exception as exc:
                logger.warning("Enrichment failed: %s", exc)
                c = futures[future]
                c.setdefault("ai_summary", c.get("snippet",""))
                c.setdefault("products", [])
                enriched.append(c)
    return enriched


# ---------------------------------------------------------------------------
# Scoring — quality threshold filter
# ---------------------------------------------------------------------------

def _score_company(query: str, company: dict,
                   quality_threshold: int = 0) -> dict | None:
    """
    Score company. Returns None if below quality_threshold.
    quality_threshold: 0=all, 1=low+, 2=medium+, 3=high only
    """
    try:
        from nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query
    except ImportError:
        from .nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query

    content = company.get("content", "") or company.get("snippet", "")
    website = company.get("website", "")

    combined = " ".join(filter(None, [
        company.get("company",    ""),
        company.get("snippet",    ""),
        company.get("ai_summary", ""),
        content[:3000],
    ]))

    sem_score = semantic_similarity(query, combined) if combined.strip() else 0.0
    kw_score  = keyword_match_ratio(query, combined)
    da_score  = _da_heuristic(website)

    contact = round(
        (0.35 if company.get("email")          else 0.0) +
        (0.25 if company.get("phone")          else 0.0) +
        (0.20 if company.get("contact_person") else 0.0) +
        (0.10 if company.get("linkedin_url")   else 0.0) +
        (0.05 if company.get("whatsapp_url")   else 0.0) +
        (0.05 if company.get("instagram_url")  else 0.0),
        2
    )

    bonus = 0.0
    if company.get("annual_turnover"):    bonus += 0.03
    if company.get("certifications"):     bonus += 0.02
    if company.get("export_markets"):     bonus += 0.02
    if company.get("incorporation_date"): bonus += 0.01
    if company.get("usp"):                bonus += 0.01

    grok_score  = float(company.get("grok_score", 5) or 5) / 10.0
    is_valid    = bool(company.get("is_valid_lead", True))
    is_dir      = bool(company.get("is_directory", False))

    # Grok validation penalty
    if not is_valid:
        bonus -= 0.10

    # Directory bonus (valuable source)
    if is_dir:
        bonus += 0.05

    final_score = round(
        (0.25 * sem_score) +
        (0.15 * kw_score)  +
        (0.15 * da_score)  +
        (0.15 * contact)   +
        (0.25 * grok_score)+
        bonus,
        3,
    )
    final_score = max(0.0, min(final_score, 1.0))

    importance = (
        "high"   if final_score >= 0.60 else
        "medium" if final_score >= 0.38 else
        "low"
    )

    # Apply quality threshold filter
    # 0=all  1=low+  2=medium+  3=high only
    threshold_map = {0: None, 1: "low", 2: "medium", 3: "high"}
    min_imp = threshold_map.get(quality_threshold)
    if min_imp:
        rank = {"high": 3, "medium": 2, "low": 1}
        if rank.get(importance, 0) < rank.get(min_imp, 0):
            return None  # filtered out

    if not company.get("ai_summary") and combined.strip():
        company["ai_summary"] = ai_summary_for_query(query, combined, max_sentences=3)

    company.update({
        "semantic_score":   sem_score,
        "keyword_score":    kw_score,
        "domain_authority": da_score,
        "contact_presence": contact,
        "final_score":      final_score,
        "importance":       importance,
    })
    return company


# ---------------------------------------------------------------------------
# Main Google search
# ---------------------------------------------------------------------------

def google_search(
    query: str,
    max_results: int = 10,
    start: int = 0,
    exclude_domains: set | None = None,
    max_pages: int = 1,
    country_filter: str | None = None,
    trusted_only: bool = False,
    quality_threshold: int = 0,
) -> dict:
    if not SERP_API_KEY:
        logger.error("SERP_API_KEY not set")
        return {"companies": [], "next_start": start, "has_more": False,
                "pages_scanned": 0, "effective_country": country_filter or "",
                "error": "SERP_API_KEY not configured"}

    country_filter = (country_filter or "").strip().lower()
    search_query   = _sanitise_query(query, country_filter)

    params = {
        "engine": "google", "q": search_query,
        "api_key": SERP_API_KEY, "num": 10, "start": start,
    }
    gl = COUNTRY_GL.get(country_filter, "")
    if gl:
        params["gl"] = gl

    try:
        raw_results = GoogleSearch(params).get_dict().get("organic_results", [])
        logger.info("SerpAPI: %d results", len(raw_results))
    except Exception as exc:
        logger.error("SerpAPI failed: %s", exc)
        return {"companies": [], "next_start": start, "has_more": False,
                "pages_scanned": 0, "effective_country": country_filter,
                "error": str(exc)}

    candidates = []
    for r in raw_results:
        link = r.get("link", "")
        if not link or not _is_company_url(link):
            continue
        domain = urlparse(link).netloc.lower().replace("www.", "")
        if exclude_domains and domain in exclude_domains:
            continue
        candidates.append({
            "company": _clean_title(r.get("title", "")),
            "website": link,
            "snippet": r.get("snippet", ""),
            "domain":  domain,
        })

    candidates = candidates[:max_results]
    logger.info("Candidates: %d", len(candidates))

    if candidates:
        candidates = parallel_enrich(
            candidates, max_workers=3, query=query,
            quality_threshold=quality_threshold,
        )

    scored = []
    for c in candidates:
        result = _score_company(query, c, quality_threshold)
        if result is not None:
            scored.append(result)
        else:
            logger.info("Filtered out (quality threshold): %s", c.get("company","?"))

    scored.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    return {
        "companies":         scored,
        "next_start":        start + len(raw_results),
        "has_more":          len(raw_results) >= 10,
        "pages_scanned":     1,
        "effective_country": country_filter,
    }


def linkedin_discovery(query: str, country_filter: str | None = None,
                       trusted_only: bool = False, max_results: int = 5,
                       exclude_domains: set | None = None) -> list:
    if not SERP_API_KEY:
        return []
    country_filter = (country_filter or "").strip().lower()
    params = {"engine": "google", "q": f"{query} site:linkedin.com/in",
              "api_key": SERP_API_KEY, "num": max_results}
    gl = COUNTRY_GL.get(country_filter, "")
    if gl:
        params["gl"] = gl
    try:
        results = GoogleSearch(params).get_dict()
        return [{"name": r.get("title",""), "profile": r.get("link",""),
                 "snippet": r.get("snippet","")}
                for r in results.get("organic_results", [])]
    except Exception as exc:
        logger.error("LinkedIn search failed: %s", exc)
        return []


def smart_google_search(queries: list) -> tuple:
    all_companies, all_people = [], []
    for q in queries:
        result = google_search(q)
        all_companies.extend(result.get("companies", []))
        all_people.extend(linkedin_discovery(q))
    return all_companies[:10], all_people[:10]
