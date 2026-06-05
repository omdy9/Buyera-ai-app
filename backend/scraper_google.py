"""
scraper_google.py  — v5  (looser filtering + better fallback)
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

SERP_API_KEY       = os.getenv("SERP_API_KEY", "")
NODE_CRAWLER_URL   = os.getenv("NODE_CRAWLER_URL", "http://127.0.0.1:5050")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Country -> SerpAPI gl code
# ---------------------------------------------------------------------------
COUNTRY_GL = {
    "india": "in", "usa": "us", "uk": "gb", "uae": "ae",
    "dubai": "ae", "germany": "de", "canada": "ca",
    "australia": "au", "singapore": "sg", "china": "cn",
    "italy": "it", "france": "fr", "japan": "jp",
}

# ---------------------------------------------------------------------------
# Only block the most obvious non-company domains
# ---------------------------------------------------------------------------
BAD_DOMAINS = [
    "justdial", "yellowpages", "sulekha", "tradeindia", "indiamart",
    "exportersindia", "linkedin", "facebook", "instagram", "twitter",
    "youtube", "amazon", "flipkart", "wikipedia", "wikidata",
    "naukri", "monster", "indeed", "glassdoor",
    "blogspot", "wordpress.com", "medium.com",
]

_FREE_HOST_RE = re.compile(
    r"\.(blogspot|wordpress\.com|wixsite|weebly)\.",
    re.IGNORECASE,
)

_EXCLUDE_SITES = [
    "indiamart.com", "justdial.com", "tradeindia.com",
    "wikipedia.org", "linkedin.com", "facebook.com",
]

_QUERY_STRIP_WORDS = re.compile(
    r"\b(top|best|leading|list\s+of|ranking|reviews?|compared?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Channel-type keywords
# ---------------------------------------------------------------------------
_CHANNEL_KEYWORDS = {
    "Manufacturer": [
        "manufacturer", "manufacturing", "we manufacture", "our factory",
        "production facility", "our plant", "fabricat", "oem", "odm",
    ],
    "Importer": [
        "importer", "import", "we import", "imported from", "importing",
        "customs", "iec", "cif", "fob",
    ],
    "Wholesaler": [
        "wholesaler", "wholesale", "bulk supply", "bulk order",
        "minimum order quantity", "moq",
    ],
    "Distributor": [
        "distributor", "distribution", "authorised distributor",
        "authorized distributor", "exclusive distributor", "channel partner",
    ],
    "Trader": [
        "trader", "trading company", "trading house", "buy and sell",
    ],
    "Retailer": [
        "retailer", "retail", "showroom", "store", "shop online", "add to cart",
    ],
}

_MAJOR_CITIES = [
    "Mumbai","Delhi","Bangalore","Bengaluru","Hyderabad","Ahmedabad","Chennai",
    "Kolkata","Surat","Pune","Jaipur","Lucknow","Nagpur","Indore","Thane",
    "Bhopal","Visakhapatnam","Patna","Vadodara","Ghaziabad","Ludhiana","Agra",
    "Nashik","Faridabad","Meerut","Rajkot","Varanasi","Aurangabad","Coimbatore",
    "Vijayawada","Noida","Gurgaon","Gurugram","Chandigarh","Mysore","Mysuru",
    "Amritsar","Kochi","Cochin","Ernakulam","Dubai","Abu Dhabi","Singapore",
    "Kuala Lumpur","Hong Kong","Shanghai","Beijing","London","New York",
    "Los Angeles","Toronto","Sydney","Melbourne","Frankfurt","Paris",
]
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _MAJOR_CITIES) + r")\b",
    re.IGNORECASE,
)

_LINKEDIN_RE = re.compile(
    r'https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?',
    re.IGNORECASE,
)

_COUNTRY_MENTIONS = {
    "India":     ["india", "indian", ".in", "bharath", "bharat"],
    "UAE":       ["uae", "dubai", "abu dhabi", "emirates"],
    "USA":       ["usa", "united states", "america"],
    "UK":        ["uk", "united kingdom", "britain", "england"],
    "Germany":   ["germany", "german", "deutschland"],
    "Singapore": ["singapore"],
    "Canada":    ["canada", "canadian"],
    "Australia": ["australia", "australian"],
    "China":     ["china", "chinese"],
    "Italy":     ["italy", "italian"],
}

_INCORP_PATTERNS = [
    re.compile(r"(?:incorporated|established|founded|since|est\.?)\s*(?:in\s*)?(\d{4})", re.I),
    re.compile(r"(?:year\s+of\s+(?:incorporation|establishment|founding))[:\s]+(\d{4})", re.I),
    re.compile(r"(?:date\s+of\s+incorporation)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", re.I),
]

INDUSTRY_MAP = {
    "Electronics":      ["electronics", "semiconductor", "circuit", "pcb", "led", "display"],
    "Pharmaceuticals":  ["pharma", "pharmaceutical", "medicine", "drug", "api"],
    "Textiles":         ["textile", "fabric", "garment", "apparel", "yarn"],
    "Chemicals":        ["chemical", "polymer", "resin", "adhesive", "solvent"],
    "Machinery":        ["machinery", "machine", "equipment", "cnc", "lathe"],
    "Food & Beverage":  ["food", "beverage", "spice", "grain", "dairy"],
    "Automotive":       ["automotive", "automobile", "vehicle", "car", "truck"],
    "Construction":     ["construction", "cement", "steel", "rebar", "building"],
    "IT & Software":    ["software", "it services", "saas", "technology", "cloud"],
    "Healthcare":       ["healthcare", "hospital", "medical device", "diagnostics"],
    "Logistics":        ["logistics", "freight", "shipping", "warehouse"],
    "Agriculture":      ["agriculture", "agro", "fertilizer", "pesticide", "seed"],
    "Energy":           ["energy", "solar", "wind", "power", "battery"],
    "Retail":           ["retail", "ecommerce", "e-commerce", "marketplace"],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sanitise_query(query: str, country_filter: str = "") -> str:
    clean_q = _QUERY_STRIP_WORDS.sub("", query).strip()
    clean_q = re.sub(r"\s{2,}", " ", clean_q)
    if country_filter and country_filter.lower() not in clean_q.lower():
        clean_q = f"{clean_q} {country_filter}"
    return clean_q.strip()


def _is_company_url(url: str, title: str = "") -> bool:
    """Looser filter — only block obvious non-company domains."""
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")
    # Block known bad domains
    for bad in BAD_DOMAINS:
        if bad.lower() in netloc:
            return False
    # Block free hosting
    if _FREE_HOST_RE.search(netloc):
        return False
    return True


def _clean_title(title: str) -> str:
    suffixes = re.compile(
        r"\s*[\|\-\u2013\u2014:]+\s*(home|welcome|official\s+website|about\s+us"
        r"|contact\s+us|index|homepage)\s*$",
        re.IGNORECASE,
    )
    return suffixes.sub("", title).strip()


def _domain_authority_heuristic(url: str) -> float:
    netloc = urlparse(url).netloc.lower().replace("www.", "")
    score  = 0.5
    if netloc.endswith(".com"):
        score += 0.20
    if any(netloc.endswith(t) for t in [".ae", ".in", ".co.uk", ".com.au", ".sg", ".ca", ".co.in"]):
        score += 0.15
    if len(netloc.split(".")) > 3:
        score -= 0.10
    return round(min(max(score, 0.0), 1.0), 3)


def _detect_channel_type(text: str) -> str:
    text_lower = text.lower()
    scores = {}
    for channel, keywords in _CHANNEL_KEYWORDS.items():
        scores[channel] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def _detect_industry(text: str) -> str:
    text_lower = text.lower()
    for industry, keywords in INDUSTRY_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return industry
    return ""


def _detect_city(text: str, html: str = "") -> str:
    locality = re.search(r'"addressLocality"\s*:\s*"([^"]{2,40})"', html, re.I)
    if locality:
        return locality.group(1).strip()
    m = _CITY_RE.search(text)
    return m.group(1).title() if m else ""


def _detect_country_from_text(text: str) -> str:
    text_lower = text.lower()
    for country, signals in _COUNTRY_MENTIONS.items():
        if any(s in text_lower for s in signals):
            return country
    return ""


def _extract_linkedin(html: str) -> str:
    m = _LINKEDIN_RE.search(html)
    return m.group(0).rstrip("/") if m else ""


def _detect_incorporation(text: str) -> str:
    for pat in _INCORP_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1)
    return ""


def _detect_company_size(text: str) -> str:
    patterns = [
        (re.compile(r"\b(\d{1,4})\s*[-–to]+\s*(\d{2,5})\s*(employees|staff)\b", re.I), "{a}–{b}"),
        (re.compile(r"\b(\d{2,5})\s*\+?\s*(employees|staff|people|professionals)\b", re.I), "{n}+"),
        (re.compile(r"team\s+of\s+(\d+)", re.I), "team of {n}"),
    ]
    for pattern, label in patterns:
        m = pattern.search(text)
        if m:
            if "{a}" in label:
                return f"{m.group(1)}–{m.group(2)}"
            return label.replace("{n}", m.group(1))
    return ""


def _detect_product_type(text: str, query: str = "") -> str:
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", query.lower())
             if w not in {"from", "with", "that", "this", "their", "company",
                          "import", "export", "india", "best", "list"}]
    if words:
        return " ".join(words[:3]).title()
    return ""


# ---------------------------------------------------------------------------
# Website crawl (BS4 only — no Node dependency)
# ---------------------------------------------------------------------------

EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}")
PHONE_RE  = re.compile(r"\+?\d[\d\s\-()\\.]{7,}")
PERSON_RE = re.compile(
    r"(?:contact\s*(?:person|us|name)[:\s]+|(?:Mr|Ms|Mrs|Dr)\.?\s+)([A-Z][a-z]+ [A-Z][a-z]+)"
)


def extract_company_data(website: str, query: str = "") -> dict:
    empty = {
        "email": "", "phone": "", "content": "",
        "city": "", "country_detected": "", "linkedin_url": "",
        "incorporation_date": "", "company_size": "", "channel_type": "",
        "contact_person": "", "contact_email": "", "active_website": website or "",
        "industry_detected": "", "product_type": "",
    }
    if not website:
        return empty

    # Try Node.js crawler first
    try:
        resp = requests.post(
            f"{NODE_CRAWLER_URL}/crawl",
            json={"url": website},
            timeout=15,
        )
        if resp.status_code == 200:
            data    = resp.json()
            text    = data.get("content", "")
            raw_html = data.get("html", "")
            return {
                "email":              data.get("email", ""),
                "phone":              data.get("phone", ""),
                "content":            text,
                "city":               data.get("city", "") or _detect_city(text, raw_html),
                "country_detected":   data.get("country_detected", "") or _detect_country_from_text(text),
                "linkedin_url":       data.get("linkedin_url", "") or _extract_linkedin(raw_html),
                "incorporation_date": data.get("incorporation_date", "") or _detect_incorporation(text),
                "company_size":       data.get("company_size", "") or _detect_company_size(text),
                "channel_type":       data.get("channel_type", "") or _detect_channel_type(text),
                "contact_person":     data.get("contact_person", ""),
                "contact_email":      data.get("contact_email", "") or data.get("email", ""),
                "active_website":     website,
                "industry_detected":  _detect_industry(text),
                "product_type":       _detect_product_type(text, query),
            }
    except Exception:
        pass

    # BS4 fallback
    email, phone, content, person, all_html = "", "", "", "", ""
    for path in ["", "/contact", "/about"]:
        try:
            r = requests.get(
                website.rstrip("/") + path,
                timeout=8,
                headers={"User-Agent": "Mozilla/5.0"},
                allow_redirects=True,
            )
            html_chunk = r.text
            all_html  += html_chunk
            soup       = BeautifulSoup(html_chunk, "html.parser")
            for tag in soup(["script", "style", "nav", "footer"]):
                tag.decompose()
            text     = soup.get_text(separator=" ", strip=True)
            content += " " + text
            if not email:
                m = EMAIL_RE.search(text)
                if m:
                    email = m.group()
            if not phone:
                m = PHONE_RE.search(text)
                if m:
                    phone = m.group().strip()
            if not person:
                m = PERSON_RE.search(text)
                if m:
                    person = m.group(1).strip()
        except Exception:
            continue

    content = content[:5000].strip()
    return {
        "email":              email,
        "phone":              phone,
        "content":            content,
        "city":               _detect_city(content, all_html),
        "country_detected":   _detect_country_from_text(content),
        "linkedin_url":       _extract_linkedin(all_html),
        "incorporation_date": _detect_incorporation(content),
        "company_size":       _detect_company_size(content),
        "channel_type":       _detect_channel_type(content),
        "contact_person":     person,
        "contact_email":      email,
        "active_website":     website,
        "industry_detected":  _detect_industry(content),
        "product_type":       _detect_product_type(content, query),
    }


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _score_company(query: str, company: dict) -> dict:
    try:
        from nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query
    except ImportError:
        from .nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query

    content  = company.get("content", "") or company.get("snippet", "")
    website  = company.get("website", "")

    combined = " ".join(filter(None, [
        company.get("company", ""),
        company.get("snippet", ""),
        content[:2000],
    ]))

    sem_score = semantic_similarity(query, combined) if combined.strip() else 0.0
    kw_score  = keyword_match_ratio(query, combined)
    da_score  = _domain_authority_heuristic(website)
    contact   = round(
        (0.5 if company.get("email") else 0.0) +
        (0.5 if company.get("phone") else 0.0), 2
    )

    final_score = round(
        (0.40 * sem_score) + (0.20 * kw_score) +
        (0.20 * da_score)  + (0.20 * contact), 3,
    )
    importance = (
        "high"   if final_score >= 0.55 else
        "medium" if final_score >= 0.35 else
        "low"
    )

    summary  = ai_summary_for_query(query, combined, max_sentences=3) if combined.strip() else ""
    products = []
    llm_relevant = None

    if OPENROUTER_API_KEY and content and len(content) > 100:
        try:
            from llm import analyze_company
        except ImportError:
            try:
                from .llm import analyze_company
            except ImportError:
                analyze_company = None

        if analyze_company:
            try:
                llm_data = analyze_company(query, content)
                if llm_data.get("summary"):
                    summary      = llm_data["summary"]
                products         = llm_data.get("products", [])
                llm_relevant     = bool(llm_data.get("relevant", False))
                llm_score        = int(llm_data.get("score", 0))
                for field, llm_field in [
                    ("channel_type",       "channel_type"),
                    ("industry_detected",  "industry"),
                    ("company_size",       "company_size"),
                    ("city",               "city"),
                    ("country_detected",   "country"),
                    ("incorporation_date", "incorporation_date"),
                ]:
                    if not company.get(field) and llm_data.get(llm_field):
                        company[field] = llm_data[llm_field]

                final_score = round(
                    (0.35 * sem_score) + (0.15 * kw_score) +
                    (0.15 * da_score)  + (0.15 * contact) +
                    (0.20 * (llm_score / 10.0)), 3,
                )
                importance = (
                    "high"   if final_score >= 0.55 else
                    "medium" if final_score >= 0.35 else
                    "low"
                )
            except Exception as exc:
                logger.warning("LLM analysis failed for %s: %s", website, exc)

    company.update({
        "semantic_score":   sem_score,
        "keyword_score":    kw_score,
        "domain_authority": da_score,
        "contact_presence": contact,
        "final_score":      final_score,
        "importance":       importance,
        "summary":          summary,
        "products":         products,
        "llm_relevant":     llm_relevant,
    })
    return company


# ---------------------------------------------------------------------------
# Enrichment
# ---------------------------------------------------------------------------

def enrich_company(company: dict, run_compliance: bool = False, query: str = "") -> dict:
    crawl = extract_company_data(company.get("website", ""), query=query)
    company.update({
        "email":              crawl.get("email", ""),
        "phone":              crawl.get("phone", ""),
        "content":            crawl.get("content", ""),
        "city":               crawl.get("city", ""),
        "country_detected":   crawl.get("country_detected", ""),
        "linkedin_url":       crawl.get("linkedin_url", ""),
        "incorporation_date": crawl.get("incorporation_date", ""),
        "company_size":       crawl.get("company_size", ""),
        "channel_type":       crawl.get("channel_type", ""),
        "contact_person":     crawl.get("contact_person", ""),
        "contact_email":      crawl.get("contact_email", ""),
        "active_website":     crawl.get("active_website", company.get("website", "")),
        "industry_detected":  crawl.get("industry_detected", ""),
        "product_type":       crawl.get("product_type", ""),
    })

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
                compliance = check_company_compliance(
                    company.get("company", ""), company.get("website", ""))
                company["compliance"] = compliance
                mca = compliance.get("mca", {})
                if mca.get("incorporation_date") and not company.get("incorporation_date"):
                    company["incorporation_date"] = mca["incorporation_date"]
            except Exception as exc:
                logger.warning("Compliance check failed: %s", exc)
                company["compliance"] = {"compliance_gaps": [], "compliance_score": 1.0}
    return company


def parallel_enrich(companies: list, max_workers: int = 4,
                    run_compliance: bool = False, query: str = "") -> list:
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(enrich_company, c, run_compliance, query): c
            for c in companies
        }
        for future in as_completed(futures):
            try:
                enriched.append(future.result())
            except Exception as exc:
                logger.warning("Enrichment failed: %s", exc)
                enriched.append(futures[future])
    return enriched


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
) -> dict:
    if not SERP_API_KEY or not SERP_API_KEY.strip():
        logger.error("SERP_API_KEY is not set!")
        return {
            "companies": [], "next_start": start,
            "has_more": False, "pages_scanned": 0,
            "effective_country": country_filter or "",
            "error": "SERP_API_KEY not configured",
        }

    country_filter = (country_filter or "").strip().lower()
    search_query   = _sanitise_query(query, country_filter)
    logger.info("Searching: %s", search_query[:120])

    params: dict = {
        "engine":  "google",
        "q":       search_query,
        "api_key": SERP_API_KEY,
        "num":     10,
        "start":   start,
    }
    gl = COUNTRY_GL.get(country_filter, "")
    if gl:
        params["gl"] = gl

    try:
        search  = GoogleSearch(params)
        results = search.get_dict()
    except Exception as exc:
        logger.error("SerpAPI call failed: %s", exc)
        return {
            "companies": [], "next_start": start,
            "has_more": False, "pages_scanned": 0,
            "effective_country": country_filter,
            "error": str(exc),
        }

    raw_results = results.get("organic_results", [])
    logger.info("SerpAPI returned %d raw results for query: %s", len(raw_results), search_query)

    if not raw_results:
        # Log full response for debugging
        logger.warning("Empty results. Full response keys: %s", list(results.keys()))
        error_info = results.get("error", results.get("search_information", {}))
        logger.warning("SerpAPI error info: %s", error_info)

    candidates = []
    rejected   = []
    for r in raw_results:
        link  = r.get("link", "")
        title = r.get("title", "")
        if not link:
            continue
        if not _is_company_url(link, title):
            rejected.append(link[:60])
            continue
        domain = urlparse(link).netloc.lower().replace("www.", "")
        if exclude_domains and domain in exclude_domains:
            continue
        candidates.append({
            "company": _clean_title(title),
            "website": link,
            "snippet": r.get("snippet", ""),
            "domain":  domain,
        })

    logger.info("Candidates after filter: %d / %d (rejected: %d)",
                len(candidates), len(raw_results), len(rejected))

    candidates = candidates[:max_results]

    if candidates:
        candidates = parallel_enrich(candidates, query=query)

    scored = []
    for c in candidates:
        try:
            scored.append(_score_company(query, c))
        except Exception as exc:
            logger.warning("Scoring failed for %s: %s", c.get("website"), exc)
            c.setdefault("semantic_score",   0.0)
            c.setdefault("keyword_score",    0.0)
            c.setdefault("domain_authority", 0.0)
            c.setdefault("contact_presence", 0.0)
            c.setdefault("final_score",      0.0)
            c.setdefault("importance",       "low")
            c.setdefault("summary",          c.get("snippet", ""))
            c.setdefault("products",         [])
            c.setdefault("llm_relevant",     None)
            for f in ["city", "country_detected", "linkedin_url", "incorporation_date",
                      "company_size", "channel_type", "contact_person", "contact_email",
                      "active_website", "industry_detected", "product_type"]:
                c.setdefault(f, "")
            scored.append(c)

    scored.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    return {
        "companies":         scored,
        "next_start":        start + len(raw_results),
        "has_more":          len(raw_results) >= 10,
        "pages_scanned":     1,
        "effective_country": country_filter,
    }


# ---------------------------------------------------------------------------
# LinkedIn discovery
# ---------------------------------------------------------------------------

def linkedin_discovery(
    query: str,
    country_filter: str | None = None,
    trusted_only: bool = False,
    max_results: int = 5,
    exclude_domains: set | None = None,
) -> list:
    if not SERP_API_KEY:
        return []

    country_filter = (country_filter or "").strip().lower()
    search_q = f"{query} site:linkedin.com/in"

    params: dict = {
        "engine":  "google",
        "q":       search_q,
        "api_key": SERP_API_KEY,
        "num":     max_results,
    }
    gl = COUNTRY_GL.get(country_filter, "")
    if gl:
        params["gl"] = gl

    try:
        search  = GoogleSearch(params)
        results = search.get_dict()
    except Exception as exc:
        logger.error("LinkedIn SerpAPI call failed: %s", exc)
        return []

    people = []
    for r in results.get("organic_results", []):
        people.append({
            "name":    r.get("title", ""),
            "profile": r.get("link", ""),
            "snippet": r.get("snippet", ""),
        })
    return people


def smart_google_search(queries: list) -> tuple:
    all_companies, all_people = [], []
    for q in queries:
        result = google_search(q)
        all_companies.extend(result.get("companies", []))
        all_people.extend(linkedin_discovery(q))
    return all_companies[:10], all_people[:10]
