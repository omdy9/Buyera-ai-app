"""
scraper_google.py  — v8  (AI-powered multi-angle search)
=========================================================
Key changes from v7:
  - Grok generates 10-12 targeted queries per search (not just 1)
  - Each query targets a different signal: contact pages, LinkedIn,
    government registries, trade fairs, news mentions, MSME databases
  - Aggressive deduplication — same domain never appears twice
  - Aggressive filtering — remove all aggregators, directories (unless user wants them)
  - SERP API pagination skips page 1 for some queries to find hidden companies
  - DeepSeek does a SECOND web search for contact details of each found company
  - Only companies with at least 1 contact signal are kept (unless low quality mode)
"""

import os
import re
import time
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
    "india":"in","usa":"us","uk":"gb","uae":"ae","dubai":"ae",
    "germany":"de","canada":"ca","australia":"au","singapore":"sg",
    "china":"cn","italy":"it","france":"fr","japan":"jp",
}

# ── Aggressive bad-domain list ─────────────────────────────────────────────
# These NEVER produce useful direct company leads
BAD_DOMAINS = {
    # Directories
    "justdial","yellowpages","sulekha","tradeindia","indiamart",
    "exportersindia","alibaba","made-in-china","globalsources",
    "thomasnet","kompass","europages","bizbuysell","clutch",
    "goodfirms","sortlist","upcity","bark.com","bark",
    # Social / jobs
    "linkedin","facebook","instagram","twitter","x.com",
    "youtube","naukri","monster","indeed","glassdoor","apna",
    # Shopping
    "amazon","flipkart","snapdeal","meesho","shopclues",
    # Info sites
    "wikipedia","wikidata","quora","reddit","medium","blogspot",
    "wordpress.com","wixsite","weebly","squarespace",
    # News (not useful as leads)
    "economictimes","livemint","businessstandard","financialexpress",
    "timesofindia","ndtv","thehindu",
    # Government portals that list aggregated data
    "zaubacorp","tofler","mca.gov","registrar","roc.gov",
    # Review sites
    "trustpilot","g2.com","capterra","getapp",
}

_FREE_HOST_RE = re.compile(r"\.(blogspot|wordpress\.com|wixsite|weebly|tumblr)\.", re.I)

EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}")
PHONE_RE  = re.compile(r"(?:\+91[\-\s]?|0)?[6-9]\d{9}|\+\d{1,3}[\s\-]?\d{6,12}")

INDUSTRY_MAP = {
    "Electronics":     ["electronics","semiconductor","pcb","led","solar panel","display","circuit"],
    "Pharmaceuticals": ["pharma","pharmaceutical","medicine","drug","api","tablet","capsule","biotech"],
    "Textiles":        ["textile","fabric","garment","apparel","yarn","weaving","knitting","dyeing"],
    "Chemicals":       ["chemical","polymer","resin","adhesive","solvent","dye","pigment","coating"],
    "Machinery":       ["machinery","machine","equipment","cnc","lathe","pump","valve","motor","press"],
    "Food & Beverage": ["food","beverage","spice","grain","dairy","snack","packaged food","agri"],
    "Automotive":      ["automotive","automobile","vehicle","car","tyre","auto parts","spare parts"],
    "Construction":    ["construction","cement","steel","rebar","tile","pipe","sanitary","building material"],
    "IT & Software":   ["software","it services","saas","technology","cloud","erp","app development"],
    "Healthcare":      ["healthcare","hospital","medical device","diagnostics","surgical","health equipment"],
    "Logistics":       ["logistics","freight","shipping","warehouse","courier","supply chain","transport"],
    "Agriculture":     ["agriculture","agro","fertilizer","pesticide","seed","crop","farm","irrigation"],
    "Energy":          ["energy","solar","wind","power","battery","generator","inverter","renewable"],
    "Retail":          ["retail","ecommerce","e-commerce","marketplace","fmcg","consumer goods","trading"],
}

_CHANNEL_KW = {
    "Manufacturer": ["manufacturer","manufacturing","we manufacture","production facility","fabricat","oem","odm","production capacity","in-house","our factory","our plant"],
    "Importer":     ["importer","import","we import","imported from","iec","cif","fob","incoterms","customs clearance","overseas"],
    "Wholesaler":   ["wholesaler","wholesale","bulk supply","moq","minimum order quantity","bulk order","bulk pricing"],
    "Distributor":  ["distributor","distribution","authorised distributor","authorized distributor","exclusive distributor","channel partner","sole distributor"],
    "Trader":       ["trader","trading company","trading house","buy and sell","commodity trading"],
    "Retailer":     ["retailer","retail","showroom","shop","add to cart","buy now","walk-in store"],
}

_SOCIAL_PATTERNS = {
    "linkedin":  re.compile(r'https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?', re.I),
    "twitter":   re.compile(r'https?://(?:www\.)?(?:twitter|x)\.com/(?!share|intent|home|hashtag)[A-Za-z0-9_]+/?', re.I),
    "facebook":  re.compile(r'https?://(?:www\.)?facebook\.com/(?!sharer|share)[A-Za-z0-9_.]+/?', re.I),
    "instagram": re.compile(r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+/?', re.I),
    "youtube":   re.compile(r'https?://(?:www\.)?youtube\.com/(?:c/|channel/|user/|@)[A-Za-z0-9_\-]+/?', re.I),
    "whatsapp":  re.compile(r'https?://(?:wa\.me|api\.whatsapp\.com/send)[/?][^\s"\'<>]+', re.I),
}

_CITY_LIST = [
    "Mumbai","Delhi","Bangalore","Bengaluru","Hyderabad","Ahmedabad","Chennai","Kolkata",
    "Surat","Pune","Jaipur","Lucknow","Nagpur","Indore","Thane","Bhopal","Patna","Vadodara",
    "Ghaziabad","Ludhiana","Agra","Nashik","Faridabad","Meerut","Rajkot","Varanasi","Noida",
    "Gurgaon","Gurugram","Chandigarh","Mysuru","Kochi","Amritsar","Dubai","Abu Dhabi",
    "Singapore","Hong Kong","Shanghai","London","New York","Toronto","Sydney","Melbourne",
]
_CITY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in _CITY_LIST) + r")\b", re.I)

_INCORP_RE = [
    re.compile(r"(?:incorporated|established|founded|since|est\.?)\s*(?:in\s*)?(\d{4})", re.I),
    re.compile(r"(?:year\s+of\s+(?:incorporation|establishment))[:\s]+(\d{4})", re.I),
    re.compile(r"\bsince\s+(\d{4})\b", re.I),
    re.compile(r"\best(?:ablished)?\.?\s*(\d{4})\b", re.I),
]

_TURNOVER_RE = [
    re.compile(r"(?:turnover|revenue|sales)[:\s]+(?:rs\.?|inr|usd|\$)?\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh|million|billion)?", re.I),
    re.compile(r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh)\s*(?:turnover|revenue)", re.I),
]

_CERT_RE = re.compile(
    r"\b(ISO\s*\d{4,5}(?::\d{4})?|BIS|CE\b|FDA|GMP|HACCP|FSSAI|OHSAS|"
    r"SA\s*8000|IATF|REACH|RoHS|IS\s*\d+|NABL|CRISIL|ZED|MSME)\b", re.I
)

CRAWL_PATHS = [
    "", "/about", "/about-us", "/contact", "/contact-us",
    "/products", "/our-products", "/services", "/team",
    "/certifications", "/export", "/management",
]


# ── URL filter ─────────────────────────────────────────────────────────────────
def _is_valid_company_url(url: str) -> bool:
    if not url: return False
    try:
        parsed = urlparse(url)
        netloc = parsed.netloc.lower().replace("www.", "")
        # Block bad domains
        for bad in BAD_DOMAINS:
            if bad in netloc: return False
        # Block free hosting
        if _FREE_HOST_RE.search(netloc): return False
        # Must have a proper TLD
        if "." not in netloc: return False
        # Block very long paths (usually pagination/listing pages)
        if len(parsed.path) > 100: return False
        return True
    except Exception:
        return False


def _domain_from_url(url: str) -> str:
    try: return urlparse(url).netloc.lower().replace("www.","")
    except: return ""


def _da_heuristic(url: str) -> float:
    netloc = _domain_from_url(url)
    score  = 0.5
    if netloc.endswith(".com"):   score += 0.20
    if any(netloc.endswith(t) for t in [".in",".ae",".co.uk",".com.au",".sg",".ca",".co.in"]): score += 0.15
    if len(netloc.split(".")) > 3: score -= 0.10
    return round(min(max(score,0.0),1.0),3)


# ── Detection helpers ──────────────────────────────────────────────────────────
def _detect_channel(text: str) -> str:
    tl = text.lower()
    scores = {ch: sum(1 for kw in kws if kw in tl) for ch, kws in _CHANNEL_KW.items()}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""

def _detect_industry(text: str) -> str:
    tl = text.lower()
    for ind, kws in INDUSTRY_MAP.items():
        if any(kw in tl for kw in kws): return ind
    return ""

def _detect_city(text: str, html: str = "") -> str:
    m = re.search(r'"addressLocality"\s*:\s*"([^"]{2,40})"', html, re.I)
    if m: return m.group(1).strip()
    m = _CITY_RE.search(text)
    return m.group(1).title() if m else ""

def _detect_country(text: str) -> str:
    tl = text.lower()
    signals = [("India",["india","indian",".in","bharat"]),
               ("UAE",["uae","dubai","abu dhabi","emirates"]),
               ("USA",["usa","united states","america"]),
               ("UK",["uk","united kingdom","britain"]),
               ("Singapore",["singapore"]),("Germany",["germany"]),
               ("Canada",["canada"]),("Australia",["australia"]),]
    for country, sigs in signals:
        if any(s in tl for s in sigs): return country
    return ""

def _detect_incorporation(text: str) -> str:
    for pat in _INCORP_RE:
        m = pat.search(text)
        if m: return m.group(1)
    return ""

def _detect_size(text: str) -> str:
    patterns = [
        (re.compile(r"\b(\d{1,4})\s*[-–to]+\s*(\d{2,5})\s*(employees|staff)\b",re.I), "{a}–{b}"),
        (re.compile(r"\b(\d{2,5})\s*\+?\s*(employees|staff|people|workers)\b",re.I), "{n}+"),
        (re.compile(r"team\s+of\s+(\d+)",re.I),"team of {n}"),
    ]
    for pat, label in patterns:
        m = pat.search(text)
        if m:
            if "{a}" in label: return f"{m.group(1)}–{m.group(2)}"
            return label.replace("{n}",m.group(1))
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

def _detect_exports(text: str) -> list:
    markets = ["usa","uk","europe","middle east","uae","dubai","africa",
               "southeast asia","australia","canada","germany","france",
               "japan","china","bangladesh","sri lanka","nepal"]
    return [m.title() for m in markets if m in text.lower()]

def _detect_social(html: str) -> dict:
    social = {}
    for platform, pat in _SOCIAL_PATTERNS.items():
        m = pat.search(html)
        if m:
            url = m.group(0).rstrip("/")
            if platform == "twitter" and any(x in url for x in ["/share","/intent"]): continue
            if platform == "facebook" and "/sharer" in url: continue
            social[platform] = url
    return social


# ── Deep website crawler ───────────────────────────────────────────────────────
def _fetch_page(url: str, timeout: int = 8) -> tuple:
    try:
        resp = requests.get(url, timeout=timeout,
            headers={"User-Agent":"Mozilla/5.0 (compatible; BuyeraBot/3.0)"},
            allow_redirects=True)
        if resp.status_code != 200: return "", ""
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script","style","nav","footer","header","noscript"]): tag.decompose()
        return soup.get_text(separator=" ", strip=True)[:6000], html[:30000]
    except Exception: return "", ""


def deep_crawl(website: str, query: str = "") -> dict:
    base     = website.rstrip("/")
    all_text = ""
    all_html = ""
    emails   = set()
    phones   = set()

    # Try Node crawler
    node_ok = False
    try:
        resp = requests.post(f"{NODE_CRAWLER_URL}/crawl",
                             json={"url":website}, timeout=15)
        if resp.status_code == 200:
            d = resp.json()
            all_text += " " + d.get("content","")
            all_html += d.get("html","")
            if d.get("email"): emails.add(d["email"])
            if d.get("phone"): phones.add(d["phone"])
            node_ok = True
    except Exception: pass

    # BS4 crawl
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
                    for m in EMAIL_RE.finditer(text): emails.add(m.group())
                    for m in PHONE_RE.finditer(text): phones.add(m.group().strip())
            except Exception: pass

    all_text = all_text[:12000].strip()
    all_html = all_html[:50000]

    # Filter junk emails
    clean_emails = [e for e in emails
                    if not re.search(r"\.(png|jpg|gif|svg|ico|css|js)$",e,re.I)
                    and "@" in e and len(e) < 80
                    and not re.search(r"@example|@test|@sample",e,re.I)]

    # Prefer non-generic emails
    best_email = next(
        (e for e in clean_emails
         if not re.search(r"^(noreply|no-reply|donotreply|webmaster|postmaster)",e,re.I)),
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
        "export_markets":     _detect_exports(all_text),
        "active_website":     website,
        "linkedin_url":       social.get("linkedin",""),
        "twitter_url":        social.get("twitter",""),
        "facebook_url":       social.get("facebook",""),
        "instagram_url":      social.get("instagram",""),
        "youtube_url":        social.get("youtube",""),
        "whatsapp_url":       social.get("whatsapp",""),
        "social_links":       social,
    }


# ── Full enrichment: crawl → DeepSeek contact → Grok validate ─────────────────
def enrich_company(company: dict, query: str = "",
                   quality_threshold: int = 0) -> dict | None:
    website = company.get("website","")
    name    = company.get("company","")

    logger.info("Enriching: %s (%s)", name, website[:50])

    # Step 1: Deep crawl
    crawl = deep_crawl(website, query=query)
    company.update({k:v for k,v in crawl.items() if k not in ("content","all_html")})
    company["content"] = crawl["content"]

    # Step 2: LLM pipeline
    try:
        from llm import full_llm_pipeline, extract_directory_companies
    except ImportError:
        from .llm import full_llm_pipeline, extract_directory_companies

    llm = full_llm_pipeline(query=query, company=name,
                            website=website, content=crawl["content"])

    # Apply LLM results
    if llm.get("summary"):        company["ai_summary"]   = llm["summary"]
    if llm.get("products"):       company["products"]     = llm["products"]
    if llm.get("usp"):            company["usp"]          = llm["usp"]
    if llm.get("key_customers"):  company["key_customers"]= llm["key_customers"]

    for comp_field, llm_field in [
        ("channel_type","channel_type"),("industry_detected","industry"),
        ("company_size","company_size"),("city","city"),
        ("country_detected","country"),("incorporation_date","incorporation_date"),
        ("annual_turnover","annual_turnover"),("contact_person","contact_person"),
        ("contact_email","contact_email"),("linkedin_url","linkedin_url"),
    ]:
        if llm.get(llm_field) and not company.get(comp_field):
            company[comp_field] = llm[llm_field]

    company["contact_title"]     = llm.get("contact_title","")
    company["contact_linkedin"]  = llm.get("contact_linkedin","")
    company["contact_confidence"]= llm.get("confidence","low")
    company["is_directory"]      = llm.get("is_directory",False)
    company["is_valid_lead"]     = llm.get("is_valid_lead",True)
    company["rejection_reason"]  = llm.get("rejection_reason","")
    company["grok_score"]        = llm.get("relevance_score",5)

    company["certifications"] = list(set(
        crawl.get("certifications",[]) + [str(c) for c in llm.get("certifications",[])]
    ))[:15]
    company["export_markets"] = list(set(
        crawl.get("export_markets",[]) + [str(e) for e in llm.get("export_markets",[])]
    ))[:15]

    # Step 3: Quality gate — filter low-quality leads if threshold set
    if quality_threshold >= 2:
        # Must have at least 1 contact signal
        has_contact = any([
            company.get("email"), company.get("phone"),
            company.get("linkedin_url"), company.get("contact_person"),
        ])
        if not has_contact and not company.get("is_directory"):
            logger.info("Filtered (no contact): %s", name)
            return None

    if quality_threshold >= 3:
        # Grok must say it's valid AND score >= 6
        if not company.get("is_valid_lead") or int(company.get("grok_score",0) or 0) < 6:
            logger.info("Filtered (Grok rejected): %s score=%s",
                        name, company.get("grok_score"))
            return None

    # Directory extraction
    if company.get("is_directory") and crawl["content"]:
        try:
            dir_cos = extract_directory_companies(website, crawl["content"])
            company["directory_companies"] = dir_cos
            company["directory_count"]     = len(dir_cos)
        except Exception: pass

    return company


def parallel_enrich(companies: list, query: str = "",
                    quality_threshold: int = 0,
                    max_workers: int = 3) -> list:
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {ex.submit(enrich_company, c, query, quality_threshold): c
                   for c in companies}
        for future in as_completed(futures, timeout=150):
            try:
                result = future.result(timeout=90)
                if result is not None:
                    enriched.append(result)
                # None means filtered out by quality gate — don't add
            except Exception as exc:
                logger.warning("Enrichment failed: %s", exc)
                c = futures[future]
                c.setdefault("ai_summary", c.get("snippet",""))
                c.setdefault("products",[])
                if quality_threshold < 2:  # only keep if quality allows
                    enriched.append(c)
    return enriched


# ── Scoring ────────────────────────────────────────────────────────────────────
def _score(query: str, company: dict) -> dict:
    try:
        from nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query
    except ImportError:
        from .nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query

    content  = company.get("content","") or company.get("snippet","")
    website  = company.get("website","")
    combined = " ".join(filter(None,[
        company.get("company",""), company.get("snippet",""),
        company.get("ai_summary",""), content[:3000],
    ]))

    sem_score = semantic_similarity(query, combined) if combined.strip() else 0.0
    kw_score  = keyword_match_ratio(query, combined)
    da_score  = _da_heuristic(website)

    # Contact richness (weighted heavily — this is the key quality signal)
    contact = round(
        (0.35 if company.get("email")           else 0.0) +
        (0.25 if company.get("phone")           else 0.0) +
        (0.20 if company.get("contact_person")  else 0.0) +
        (0.10 if company.get("linkedin_url")    else 0.0) +
        (0.05 if company.get("whatsapp_url")    else 0.0) +
        (0.05 if company.get("instagram_url")   else 0.0),
        2
    )

    bonus = 0.0
    if company.get("annual_turnover"):    bonus += 0.03
    if company.get("certifications"):     bonus += 0.02
    if company.get("export_markets"):     bonus += 0.02
    if company.get("incorporation_date"): bonus += 0.01
    if company.get("usp"):                bonus += 0.01

    grok = float(company.get("grok_score",5) or 5) / 10.0
    is_valid = bool(company.get("is_valid_lead",True))
    if not is_valid: bonus -= 0.15

    final = round(
        (0.20*sem_score) + (0.15*kw_score) + (0.10*da_score) +
        (0.30*contact)   + (0.25*grok)     + bonus, 3
    )
    final = max(0.0, min(final, 1.0))

    importance = "high" if final>=0.60 else "medium" if final>=0.38 else "low"

    if not company.get("ai_summary") and combined.strip():
        company["ai_summary"] = ai_summary_for_query(query, combined, max_sentences=3)

    company.update({
        "semantic_score":sem_score,"keyword_score":kw_score,
        "domain_authority":da_score,"contact_presence":contact,
        "final_score":final,"importance":importance,
    })
    return company


# ── SERP search — single query ─────────────────────────────────────────────────
def _serp_search(search_query: str, country_filter: str = "",
                 start: int = 0, num: int = 10) -> list:
    """Run one SERP query and return raw results."""
    if not SERP_API_KEY: return []
    params = {
        "engine":"google","q":search_query,
        "api_key":SERP_API_KEY,"num":num,"start":start,
    }
    gl = COUNTRY_GL.get(country_filter.lower(),"")
    if gl: params["gl"] = gl
    try:
        result = GoogleSearch(params).get_dict()
        return result.get("organic_results",[])
    except Exception as exc:
        logger.error("SERP failed for '%s': %s", search_query[:50], exc)
        return []


# ── Main search function ───────────────────────────────────────────────────────
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
        return {"companies":[],"next_start":start,"has_more":False,
                "pages_scanned":0,"effective_country":country_filter or "",
                "error":"SERP_API_KEY not configured"}

    country_filter = (country_filter or "").strip().lower()

    # Step 1: Generate AI-powered search queries
    try:
        from search_strategy import generate_search_queries
    except ImportError:
        from .search_strategy import generate_search_queries

    search_queries = generate_search_queries(
        query, country=country_filter, city="", industry=""
    )
    logger.info("Generated %d search queries for: %s", len(search_queries), query[:60])

    # Step 2: Run all queries and collect unique candidates
    seen_domains = set(exclude_domains or [])
    candidates   = []
    pages_scanned = 0

    # Run queries in parallel (up to 6 at once)
    def _run_query(sq_start):
        sq, s = sq_start
        return _serp_search(sq, country_filter, start=s, num=10)

    # Mix of page 1 and page 2 results for diversity
    query_jobs = []
    for i, sq in enumerate(search_queries):
        query_jobs.append((sq, 0))    # page 1
        if i < 3:
            query_jobs.append((sq, 10))  # also get page 2 for first 3 queries

    all_raw = []
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(_run_query, job) for job in query_jobs[:16]]
        for future in as_completed(futures, timeout=30):
            try:
                results = future.result(timeout=15)
                all_raw.extend(results)
                pages_scanned += 1
            except Exception: pass

    logger.info("Total raw SERP results: %d", len(all_raw))

    # Step 3: Deduplicate and filter
    for r in all_raw:
        link  = r.get("link","")
        title = r.get("title","")
        if not link or not _is_valid_company_url(link): continue
        domain = _domain_from_url(link)
        if domain in seen_domains: continue
        seen_domains.add(domain)
        candidates.append({
            "company": _clean_title(title),
            "website": link,
            "snippet": r.get("snippet",""),
            "domain":  domain,
        })

    logger.info("Unique candidates after filter: %d", len(candidates))

    # Take top N for enrichment
    candidates = candidates[:max(max_results, 15)]

    # Step 4: Deep enrich (crawl + DeepSeek contact + Grok validation)
    if candidates:
        candidates = parallel_enrich(
            candidates, query=query,
            quality_threshold=quality_threshold,
            max_workers=3,
        )

    # Step 5: Score and sort
    scored = []
    for c in candidates:
        try:
            scored.append(_score(query, c))
        except Exception as exc:
            logger.warning("Scoring failed: %s", exc)
            c.setdefault("final_score",0.0)
            c.setdefault("importance","low")
            c.setdefault("ai_summary",c.get("snippet",""))
            c.setdefault("products",[])
            scored.append(c)

    scored.sort(key=lambda x: x.get("final_score",0), reverse=True)

    return {
        "companies":         scored,
        "next_start":        start + 10,
        "has_more":          len(all_raw) >= 10,
        "pages_scanned":     pages_scanned,
        "effective_country": country_filter,
        "queries_used":      len(search_queries),
    }


def _clean_title(title: str) -> str:
    return re.sub(
        r"\s*[\|\-–—:]+\s*(home|welcome|official\s+website|about|contact|homepage)\s*$",
        "", title, flags=re.I
    ).strip()


def linkedin_discovery(query: str, country_filter: str | None = None,
                       trusted_only: bool = False, max_results: int = 5,
                       exclude_domains: set | None = None) -> list:
    if not SERP_API_KEY: return []
    country_filter = (country_filter or "").strip().lower()
    params = {"engine":"google","q":f"{query} site:linkedin.com/in",
              "api_key":SERP_API_KEY,"num":max_results}
    gl = COUNTRY_GL.get(country_filter,"")
    if gl: params["gl"] = gl
    try:
        results = GoogleSearch(params).get_dict()
        return [{"name":r.get("title",""),"profile":r.get("link",""),
                 "snippet":r.get("snippet","")}
                for r in results.get("organic_results",[])]
    except Exception as exc:
        logger.error("LinkedIn search failed: %s", exc)
        return []


def smart_google_search(queries: list) -> tuple:
    all_companies, all_people = [], []
    for q in queries:
        result = google_search(q)
        all_companies.extend(result.get("companies",[]))
        all_people.extend(linkedin_discovery(q))
    return all_companies[:10], all_people[:10]
