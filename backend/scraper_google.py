"""
scraper_google.py  –  v4  (enriched company profile edition)
=============================================================

New in v4
---------
- extract_company_data() now returns:
    city, country_detected, linkedin_url, incorporation_date,
    company_size, channel_type, contact_person, contact_email,
    active_website, industry_detected, product_type
- _detect_channel_type()  — classifies Manufacturer/Importer/Trader/
    Wholesaler/Distributor/Retailer from page text
- _detect_company_size()  — parses employee-count signals from text
- _detect_city()          — extracts city from structured address markup
- _extract_linkedin()     — finds linkedin.com/company URLs in page HTML
- _detect_incorporation() — finds "incorporated", "established", "founded"
    date patterns
- All previous v3 features retained
"""

import os
import re
import logging
import hashlib
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
# Domain block-lists (unchanged from v3)
# ---------------------------------------------------------------------------
BAD_DOMAINS = [
    "justdial", "yellowpages", "sulekha", "tradeindia", "indiamart",
    "exportersindia", "bizvibe", "kompass", "dnb.com", "zaubacorp",
    "tofler", "zauba", "connect2india", "globalspec", "thomasnet",
    "alibaba", "aliexpress", "made-in-china", "tradekey",
    "linkedin", "facebook", "instagram", "twitter", "youtube",
    "pinterest", "reddit", "quora", "tumblr",
    "amazon", "flipkart", "snapdeal", "meesho",
    "wikipedia", "wikidata", "crunchbase",
    "business-standard", "economictimes", "livemint", "moneycontrol",
    "thehindu", "ndtv", "hindustantimes", "financialexpress",
    "theprint", "scroll.in", "wire.in",
    "clutch.co", "goodfirms", "sortlist", "bark.com", "upcity",
    "toptenreviews", "g2.com", "capterra",
    "blogspot", "wordpress", "medium", "ghost.io",
    "wix", "weebly", "squarespace", "webflow", "jimdo",
    "site123", "yola", "strikingly", "carrd",
    "naukri", "monster", "indeed", "shine.com", "glassdoor", "internshala",
    "makeinindia", "startupindia", "ibef.org", "ficci.in", "assocham", "cii.in",
]

_ARTICLE_PATH_RE = re.compile(
    r"/(top|best|list|ranking|review|compare|vs|news|article|blog|"
    r"post|insight|report|guide|tips|how-?to|press-?release|"
    r"category|tag|author|page/\d|p/\d|\d{4}/\d{2}/\d{2})",
    re.IGNORECASE,
)

_ARTICLE_TITLE_RE = re.compile(
    r"(top\s+\d+|best\s+\d*\s*|leading\s+\d+|\d+\s+best|\d+\s+top"
    r"|list\s+of|brands\s+in|companies\s+in|manufacturers\s+in"
    r"|suppliers\s+in|directory|ranking|review\s+of|compared|vs\.)",
    re.IGNORECASE,
)

_FREE_HOST_RE = re.compile(
    r"\.(blogspot|wordpress|wixsite|weebly|squarespace|"
    r"webflow|ghost|carrd|strikingly|yola|jimdo)\.",
    re.IGNORECASE,
)

_EXCLUDE_SITES = [
    "indiamart.com", "justdial.com", "tradeindia.com", "sulekha.com",
    "exportersindia.com", "yellowpages.in", "clutch.co", "goodfirms.co",
    "wikipedia.org", "quora.com", "reddit.com", "medium.com",
    "business-standard.com", "economictimes.indiatimes.com",
    "livemint.com", "moneycontrol.com", "ndtv.com",
    "linkedin.com", "facebook.com",
]

_QUERY_STRIP_WORDS = re.compile(
    r"\b(top|best|leading|list\s+of|ranking|reviews?|compared?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# NEW: Channel-type keywords
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
        "wholesaler", "wholesale", "bulk supply", "bulk order", "bulk pricing",
        "minimum order quantity", "moq",
    ],
    "Distributor": [
        "distributor", "distribution", "authorised distributor",
        "authorized distributor", "exclusive distributor", "channel partner",
    ],
    "Trader": [
        "trader", "trading company", "trading house", "commodity trading",
        "buy and sell",
    ],
    "Retailer": [
        "retailer", "retail", "walk-in", "showroom", "store",
        "shop online", "add to cart", "buy now",
    ],
}

# NEW: Company-size signals
_SIZE_PATTERNS = [
    (re.compile(r"\b([1-9]\d?)\s*(employees|staff|people|team members)\b", re.I), "1–{n}"),
    (re.compile(r"\b(1[0-4]\d|[1-9]\d)\s*[-–to]+\s*(\d{2,3})\s*(employees|staff)\b", re.I), "{a}–{b}"),
    (re.compile(r"\b(5[0-9]|[6-9]\d|[1-4]\d{2})\s*(employees|staff|people)\b", re.I), "50–499"),
    (re.compile(r"\b([5-9]\d{2}|[1-4]\d{3})\s*(employees|staff|people)\b", re.I), "500–4999"),
    (re.compile(r"\b([5-9]\d{3}|\d{5,})\s*(employees|staff|people)\b", re.I), "5000+"),
    (re.compile(r"team\s+of\s+(\d+)", re.I), "team of {n}"),
    (re.compile(r"(\d{2,4})\s*\+?\s*(employees|professionals|experts|engineers)", re.I), "{n}+"),
    # LinkedIn-style size labels scraped from about pages
    (re.compile(r"(1[-–]10|11[-–]50|51[-–]200|201[-–]500|501[-–]1[,.]?000|1[,.]?001[-–]5[,.]?000|5[,.]?001[-–]10[,.]?000|10[,.]?001\+)\s*(employees)?", re.I), "{n}"),
]

# NEW: Incorporation / founded date patterns
_INCORP_PATTERNS = [
    re.compile(r"(?:incorporated|established|founded|since|est\.?)\s*(?:in\s*)?(\d{4})", re.I),
    re.compile(r"(?:year\s+of\s+(?:incorporation|establishment|founding))[:\s]+(\d{4})", re.I),
    re.compile(r"\bCIN\b.{0,60}(\d{2})/(\d{4})\b"),   # MCA CIN contains year
    re.compile(r"(?:date\s+of\s+incorporation)[:\s]+(\d{1,2}[/-]\d{1,2}[/-]\d{4})", re.I),
    re.compile(r"(?:date\s+of\s+incorporation)[:\s]+(\d{4})", re.I),
]

# NEW: City extraction — common Indian + global city list for fast match
_MAJOR_CITIES = [
    "Mumbai","Delhi","Bangalore","Bengaluru","Hyderabad","Ahmedabad","Chennai",
    "Kolkata","Surat","Pune","Jaipur","Lucknow","Kanpur","Nagpur","Indore",
    "Thane","Bhopal","Visakhapatnam","Pimpri","Patna","Vadodara","Ghaziabad",
    "Ludhiana","Agra","Nashik","Faridabad","Meerut","Rajkot","Varanasi",
    "Aurangabad","Coimbatore","Vijayawada","Noida","Gurgaon","Gurugram",
    "Chandigarh","Mysore","Mysuru","Amritsar","Kochi","Cochin","Ernakulam",
    # Global
    "Dubai","Abu Dhabi","Singapore","Kuala Lumpur","Hong Kong","Shanghai",
    "Beijing","London","New York","Los Angeles","Toronto","Sydney","Melbourne",
    "Frankfurt","Paris","Amsterdam","Milan","Zurich",
]
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _MAJOR_CITIES) + r")\b",
    re.IGNORECASE,
)

# NEW: LinkedIn company URL pattern
_LINKEDIN_RE = re.compile(
    r'https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?',
    re.IGNORECASE,
)

# NEW: Country detection from page text
_COUNTRY_MENTIONS = {
    "India": ["india", "indian", ".in", "bharath", "bharat"],
    "UAE": ["uae", "dubai", "abu dhabi", "emirates", "emirati"],
    "USA": ["usa", "united states", "america", "u.s.a"],
    "UK": ["uk", "united kingdom", "britain", "england", "london"],
    "Germany": ["germany", "german", "deutschland"],
    "Singapore": ["singapore"],
    "Canada": ["canada", "canadian"],
    "Australia": ["australia", "australian"],
    "China": ["china", "chinese", "prc"],
    "Italy": ["italy", "italian", "italia"],
}

# ---------------------------------------------------------------------------
# Query sanitiser (unchanged)
# ---------------------------------------------------------------------------

def _sanitise_query(query: str, country_filter: str = "") -> str:
    clean_q = _QUERY_STRIP_WORDS.sub("", query).strip()
    clean_q = re.sub(r"\b\d+\b", "", clean_q)
    clean_q = re.sub(r"\s{2,}", " ", clean_q)
    if country_filter and country_filter.lower() not in clean_q.lower():
        clean_q = f"{clean_q} {country_filter}"
    return clean_q.strip()


# ---------------------------------------------------------------------------
# URL / title classifier (unchanged)
# ---------------------------------------------------------------------------

def _is_company_url(url: str, title: str = "") -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")
    path   = parsed.path.lower()
    for bad in BAD_DOMAINS:
        if bad.lower() in netloc:
            return False
    if _FREE_HOST_RE.search(netloc):
        return False
    if _ARTICLE_PATH_RE.search(path):
        return False
    if title and _ARTICLE_TITLE_RE.search(title):
        if not re.search(
            r"\b(pvt\.?\s*ltd|private\s+limited|corp|incorporated|inc\.|llp)\b",
            title, re.IGNORECASE
        ):
            return False
    path_parts = [p for p in path.split("/") if p]
    if len(path_parts) > 4:
        return False
    return True


def _clean_title(title: str) -> str:
    generic_suffixes = re.compile(
        r"\s*[\|\-\u2013\u2014:]+\s*(home|welcome|official\s+website|official\s+site"
        r"|about\s+us|contact\s+us|index|main\s+page|homepage)\s*$",
        re.IGNORECASE,
    )
    return generic_suffixes.sub("", title).strip()


# ---------------------------------------------------------------------------
# NEW: Enrichment helpers
# ---------------------------------------------------------------------------

def _detect_channel_type(text: str) -> str:
    """Return best-match channel type or empty string."""
    text_lower = text.lower()
    scores = {}
    for channel, keywords in _CHANNEL_KEYWORDS.items():
        scores[channel] = sum(1 for kw in keywords if kw in text_lower)
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else ""


def _detect_company_size(text: str) -> str:
    """Return employee-count range string or empty string."""
    for pattern, label in _SIZE_PATTERNS:
        m = pattern.search(text)
        if m:
            if "{n}" in label:
                return label.replace("{n}", m.group(1))
            if "{a}" in label and "{b}" in label:
                return f"{m.group(1)}–{m.group(2)}"
            return label
    return ""


def _detect_city(text: str, html: str = "") -> str:
    """Extract city from schema markup first, then plain text."""
    # Try JSON-LD / microdata address locality
    locality = re.search(
        r'"addressLocality"\s*:\s*"([^"]{2,40})"', html, re.IGNORECASE
    )
    if locality:
        return locality.group(1).strip()
    # Try schema.org itemprop
    locality2 = re.search(
        r'itemprop=["\']addressLocality["\'][^>]*>([^<]{2,40})<', html, re.IGNORECASE
    )
    if locality2:
        return locality2.group(1).strip()
    # Fallback: known-city list scan
    m = _CITY_RE.search(text)
    return m.group(1).title() if m else ""


def _detect_country_from_text(text: str) -> str:
    """Return detected country name from page text."""
    text_lower = text.lower()
    for country, signals in _COUNTRY_MENTIONS.items():
        if any(s in text_lower for s in signals):
            return country
    return ""


def _extract_linkedin(html: str) -> str:
    """Find first LinkedIn company profile URL in raw HTML."""
    m = _LINKEDIN_RE.search(html)
    return m.group(0).rstrip("/") if m else ""


def _detect_incorporation(text: str) -> str:
    """Extract incorporation / founding year or date."""
    for pat in _INCORP_PATTERNS:
        m = pat.search(text)
        if m:
            # Return the most specific group
            return m.group(1) if m.lastindex else ""
    return ""


def _detect_product_type(text: str, query: str = "") -> str:
    """
    Best-effort product type from query keywords + page content.
    Returns the top noun phrase from the query if nothing better found.
    """
    # Use query words as seed
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", query.lower())
             if w not in {"from", "with", "that", "this", "their", "company",
                          "import", "export", "india", "best", "list"}]
    if words:
        return " ".join(words[:3]).title()
    # Fallback: look for product mentions in text
    m = re.search(
        r"\b((?:[A-Z][a-z]+ ){0,2}(?:Products?|Solutions?|Systems?|Equipment|Devices?|Components?))\b",
        text,
    )
    return m.group(1).strip() if m else ""


def _detect_industry(text: str) -> str:
    """Simple rule-based industry detection."""
    INDUSTRY_MAP = {
        "Electronics": ["electronics", "semiconductor", "circuit", "pcb", "led", "display"],
        "Pharmaceuticals": ["pharma", "pharmaceutical", "medicine", "drug", "api", "formulation"],
        "Textiles": ["textile", "fabric", "garment", "apparel", "yarn", "weaving"],
        "Chemicals": ["chemical", "polymer", "resin", "adhesive", "solvent", "dye"],
        "Machinery": ["machinery", "machine", "equipment", "cnc", "lathe", "press"],
        "Food & Beverage": ["food", "beverage", "spice", "grain", "dairy", "snack"],
        "Automotive": ["automotive", "automobile", "vehicle", "car", "truck", "tyre"],
        "Construction": ["construction", "cement", "steel", "rebar", "building material"],
        "IT & Software": ["software", "it services", "saas", "technology", "cloud", "erp"],
        "Healthcare": ["healthcare", "hospital", "medical device", "diagnostics"],
        "Logistics": ["logistics", "freight", "shipping", "warehouse", "supply chain"],
        "Agriculture": ["agriculture", "agro", "fertilizer", "pesticide", "seed"],
        "Energy": ["energy", "solar", "wind", "power", "battery", "generator"],
        "Retail": ["retail", "ecommerce", "e-commerce", "marketplace", "fmcg"],
    }
    text_lower = text.lower()
    for industry, keywords in INDUSTRY_MAP.items():
        if any(kw in text_lower for kw in keywords):
            return industry
    return ""


# ---------------------------------------------------------------------------
# MCA / GSTIN spot-check (unchanged from v3)
# ---------------------------------------------------------------------------
_DOMAIN_VERIFIED_CACHE: dict = {}


def _verify_india_domain(domain: str, company_name: str) -> bool:
    cache_key = hashlib.md5((domain + company_name).lower().encode()).hexdigest()[:12]
    if cache_key in _DOMAIN_VERIFIED_CACHE:
        return _DOMAIN_VERIFIED_CACHE[cache_key]
    name_clean = re.sub(
        r"\b(pvt|ltd|private|limited|llp|corp|inc|co)\b\.?",
        "", company_name, flags=re.IGNORECASE
    ).strip()
    name_clean = re.sub(r"[^a-zA-Z0-9 ]", " ", name_clean).strip()
    if len(name_clean) < 3:
        _DOMAIN_VERIFIED_CACHE[cache_key] = True
        return True
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0"}
    verified = False
    portal_reached = False
    try:
        resp = requests.post(
            "https://services.gst.gov.in/services/api/search/taxpayerByName",
            json={"tradeName": name_clean[:80]},
            headers=headers, timeout=8,
        )
        portal_reached = True
        if resp.status_code == 200:
            taxpayers = resp.json().get("data", []) or []
            for tp in taxpayers:
                trade = (tp.get("tradeName", "") or tp.get("lgnm", "")).lower()
                words = [w for w in name_clean.lower().split() if len(w) > 2]
                if words and sum(1 for w in words if w in trade) >= max(1, len(words) // 2):
                    verified = True
                    break
    except Exception:
        pass
    if not verified:
        try:
            resp = requests.get(
                "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
                params={"companyName": name_clean[:60]},
                headers=headers, timeout=8,
            )
            portal_reached = True
            if resp.status_code == 200:
                text  = resp.text.lower()
                words = [w for w in name_clean.lower().split() if len(w) > 2]
                if words and sum(1 for w in words if w in text) >= max(1, len(words) // 2):
                    verified = True
        except Exception:
            pass
    result = verified if portal_reached else True
    _DOMAIN_VERIFIED_CACHE[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# Domain authority heuristic (unchanged)
# ---------------------------------------------------------------------------

def _domain_authority_heuristic(url: str) -> float:
    netloc = urlparse(url).netloc.lower().replace("www.", "")
    score  = 0.5
    if netloc.endswith(".com"):
        score += 0.20
    if any(netloc.endswith(t) for t in
           [".ae", ".in", ".co.uk", ".com.au", ".sg", ".ca", ".co.in"]):
        score += 0.15
    if len(netloc.split(".")) > 3:
        score -= 0.10
    return round(min(max(score, 0.0), 1.0), 3)


# ---------------------------------------------------------------------------
# ENHANCED: Node.js crawler + BS4 fallback — now returns enriched profile
# ---------------------------------------------------------------------------

def extract_company_data(website: str, query: str = "") -> dict:
    """
    Crawl company website and return enriched profile dict.

    Returns
    -------
    {
        email, phone, content,
        city, country_detected, linkedin_url,
        incorporation_date, company_size, channel_type,
        contact_person, contact_email, active_website,
        industry_detected, product_type,
    }
    """
    empty = {
        "email": "", "phone": "", "content": "",
        "city": "", "country_detected": "", "linkedin_url": "",
        "incorporation_date": "", "company_size": "", "channel_type": "",
        "contact_person": "", "contact_email": "", "active_website": website or "",
        "industry_detected": "", "product_type": "",
    }
    if not website:
        return empty

    # --- Try Node.js crawler first ---
    raw_html = ""
    try:
        resp = requests.post(
            f"{NODE_CRAWLER_URL}/crawl",
            json={"url": website},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            result = dict(empty)
            result["email"]   = data.get("email", "")
            result["phone"]   = data.get("phone", "")
            result["content"] = data.get("content", "")
            raw_html          = data.get("html", "")
            # Enrich with new extractors
            text = result["content"]
            result["city"]              = _detect_city(text, raw_html)
            result["country_detected"]  = _detect_country_from_text(text)
            result["linkedin_url"]      = _extract_linkedin(raw_html or text)
            result["incorporation_date"] = _detect_incorporation(text)
            result["company_size"]      = _detect_company_size(text)
            result["channel_type"]      = _detect_channel_type(text)
            result["industry_detected"] = _detect_industry(text)
            result["product_type"]      = _detect_product_type(text, query)
            result["active_website"]    = website
            result["contact_email"]     = result["email"]
            return result
    except Exception:
        pass

    # --- BS4 fallback ---
    EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}")
    PHONE_RE = re.compile(r"\+?\d[\d\s\-()\\.]{7,}")
    # Contact person: look for "Contact: Name" or "Mr./Ms. Name" patterns
    PERSON_RE = re.compile(
        r"(?:contact\s*(?:person|us|name)[:\s]+|(?:Mr|Ms|Mrs|Dr)\.?\s+)([A-Z][a-z]+ [A-Z][a-z]+)",
    )

    email, phone, content, person = "", "", "", ""
    all_html = ""
    for path in ["", "/contact", "/about", "/contact-us", "/about-us"]:
        try:
            r = requests.get(
                website.rstrip("/") + path,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            html_chunk = r.text
            all_html += html_chunk
            soup = BeautifulSoup(html_chunk, "html.parser")
            text = soup.get_text(separator=" ", strip=True)
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
    result = dict(empty)
    result["email"]              = email
    result["phone"]              = phone
    result["content"]            = content
    result["city"]               = _detect_city(content, all_html)
    result["country_detected"]   = _detect_country_from_text(content)
    result["linkedin_url"]       = _extract_linkedin(all_html)
    result["incorporation_date"] = _detect_incorporation(content)
    result["company_size"]       = _detect_company_size(content)
    result["channel_type"]       = _detect_channel_type(content)
    result["contact_person"]     = person
    result["contact_email"]      = email
    result["active_website"]     = website
    result["industry_detected"]  = _detect_industry(content)
    result["product_type"]       = _detect_product_type(content, query)
    return result


# ---------------------------------------------------------------------------
# NLP + LLM scoring (updated to pass new fields through)
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

    summary      = ai_summary_for_query(query, combined, max_sentences=3) if combined.strip() else ""
    products     = []
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
                    summary  = llm_data["summary"]
                products     = llm_data.get("products", [])
                llm_relevant = bool(llm_data.get("relevant", False))
                llm_score    = int(llm_data.get("score", 0))
                # Pull enriched fields from LLM if not already filled
                if not company.get("channel_type") and llm_data.get("channel_type"):
                    company["channel_type"] = llm_data["channel_type"]
                if not company.get("industry_detected") and llm_data.get("industry"):
                    company["industry_detected"] = llm_data["industry"]
                if not company.get("company_size") and llm_data.get("company_size"):
                    company["company_size"] = llm_data["company_size"]
                if not company.get("city") and llm_data.get("city"):
                    company["city"] = llm_data["city"]
                if not company.get("country_detected") and llm_data.get("country"):
                    company["country_detected"] = llm_data["country"]
                if not company.get("incorporation_date") and llm_data.get("incorporation_date"):
                    company["incorporation_date"] = llm_data["incorporation_date"]

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
# Enrichment  (crawl + compliance check)
# ---------------------------------------------------------------------------

def enrich_company(company: dict, run_compliance: bool = False, query: str = "") -> dict:
    crawl = extract_company_data(company.get("website", ""), query=query)
    # Core fields
    company["email"]   = crawl.get("email", "")
    company["phone"]   = crawl.get("phone", "")
    company["content"] = crawl.get("content", "")
    # NEW enriched fields
    company["city"]               = crawl.get("city", "")
    company["country_detected"]   = crawl.get("country_detected", "")
    company["linkedin_url"]       = crawl.get("linkedin_url", "")
    company["incorporation_date"] = crawl.get("incorporation_date", "")
    company["company_size"]       = crawl.get("company_size", "")
    company["channel_type"]       = crawl.get("channel_type", "")
    company["contact_person"]     = crawl.get("contact_person", "")
    company["contact_email"]      = crawl.get("contact_email", "")
    company["active_website"]     = crawl.get("active_website", company.get("website", ""))
    company["industry_detected"]  = crawl.get("industry_detected", "")
    company["product_type"]       = crawl.get("product_type", "")

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
                    company.get("company", ""),
                    company.get("website", ""),
                )
                company["compliance"] = compliance
                # Pull incorporation_date from MCA result if available
                mca = compliance.get("mca", {})
                if mca.get("incorporation_date") and not company.get("incorporation_date"):
                    company["incorporation_date"] = mca["incorporation_date"]
            except Exception as exc:
                logger.warning("Compliance check failed for %s: %s",
                               company.get("company"), exc)
                company["compliance"] = {
                    "compliance_gaps": [], "compliance_score": 1.0,
                    "checker_error": str(exc),
                }
    return company


def parallel_enrich(companies: list, max_workers: int = 5,
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
    country_filter = (country_filter or "").strip().lower()
    search_query   = _sanitise_query(query, country_filter)
    logger.info("Sanitised query: %s", search_query[:120])

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
        }

    raw_results = results.get("organic_results", [])
    logger.info("SerpAPI returned %d raw results", len(raw_results))

    candidates = []
    rejected   = []
    for r in raw_results:
        link  = r.get("link", "")
        title = r.get("title", "")
        if not link:
            continue
        if not _is_company_url(link, title):
            rejected.append((link[:70], "classifier"))
            continue
        if trusted_only and _FREE_HOST_RE.search(urlparse(link).netloc.lower()):
            rejected.append((link[:70], "free-host"))
            continue
        domain = urlparse(link).netloc.lower().replace("www.", "")
        if exclude_domains and domain in exclude_domains:
            rejected.append((link[:70], "duplicate"))
            continue
        candidates.append({
            "company": _clean_title(title),
            "website": link,
            "snippet": r.get("snippet", ""),
            "domain":  domain,
        })

    if rejected:
        logger.info("Rejected %d/%d results. Sample: %s",
                    len(rejected), len(raw_results), rejected[:3])

    candidates = candidates[:max_results]

    if candidates:
        candidates = parallel_enrich(candidates, query=query)

    scored = []
    for c in candidates:
        try:
            scored.append(_score_company(query, c))
        except Exception as exc:
            logger.warning("Scoring failed for %s: %s", c.get("website"), exc)
            for field in ["semantic_score", "keyword_score", "domain_authority",
                          "contact_presence", "final_score"]:
                c.setdefault(field, 0.0)
            c.setdefault("importance",       "low")
            c.setdefault("summary",          c.get("snippet", ""))
            c.setdefault("products",         [])
            c.setdefault("llm_relevant",     None)
            # New fields default
            for f in ["city", "country_detected", "linkedin_url",
                      "incorporation_date", "company_size", "channel_type",
                      "contact_person", "contact_email", "active_website",
                      "industry_detected", "product_type"]:
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
# LinkedIn discovery (unchanged)
# ---------------------------------------------------------------------------

def linkedin_discovery(
    query: str,
    country_filter: str | None = None,
    trusted_only: bool = False,
    max_results: int = 5,
    exclude_domains: set | None = None,
) -> list:
    country_filter = (country_filter or "").strip().lower()
    search_q = f"{query} site:linkedin.com/in"
    if country_filter and country_filter not in query.lower():
        search_q = f"{query} {country_filter} site:linkedin.com/in"

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
        link = r.get("link", "")
        if exclude_domains and urlparse(link).netloc.lower() in exclude_domains:
            continue
        people.append({
            "name":    r.get("title", ""),
            "profile": link,
            "snippet": r.get("snippet", ""),
        })
    return people


# ---------------------------------------------------------------------------
# Legacy helper
# ---------------------------------------------------------------------------

def smart_google_search(queries: list) -> tuple:
    all_companies = []
    all_people    = []
    for q in queries:
        result = google_search(q)
        all_companies.extend(result.get("companies", []))
        all_people.extend(linkedin_discovery(q))
    return all_companies[:10], all_people[:10]
