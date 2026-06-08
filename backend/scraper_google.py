"""
scraper_google.py  — v6  (deep search + full LLM enrichment)
=============================================================
- Uses ANY configured LLM (Grok, DeepSeek, OpenRouter) not just OpenRouter
- Crawls multiple pages per company (home, about, contact, products, services)
- Extracts deeper company profile: turnover signals, certifications, key people,
  awards, year founded, employee count, export markets, social links
- LLM prompt upgraded to extract 20+ fields
- Parallel enrichment with retry logic
"""

import os
import re
import time
import logging
import requests
import hashlib

from bs4 import BeautifulSoup
from serpapi import GoogleSearch
from dotenv import load_dotenv
from urllib.parse import urlparse, urljoin
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

SERP_API_KEY     = os.getenv("SERP_API_KEY", "")
NODE_CRAWLER_URL = os.getenv("NODE_CRAWLER_URL", "http://127.0.0.1:5050")

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
# Bad domains — only the most obvious directories/social
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

_QUERY_STRIP_WORDS = re.compile(
    r"\b(top|best|leading|list\s+of|ranking|reviews?|compared?)\b",
    re.IGNORECASE,
)

# ---------------------------------------------------------------------------
# Deep crawl — pages to visit per company
# ---------------------------------------------------------------------------
CRAWL_PATHS = [
    "",
    "/about", "/about-us", "/about_us",
    "/contact", "/contact-us", "/contact_us",
    "/products", "/our-products", "/product-range",
    "/services", "/our-services",
    "/company", "/who-we-are",
    "/team", "/management",
    "/certifications", "/quality", "/compliance",
    "/export", "/global", "/international",
]

# ---------------------------------------------------------------------------
# Detection patterns
# ---------------------------------------------------------------------------
_CHANNEL_KEYWORDS = {
    "Manufacturer": [
        "manufacturer", "manufacturing", "we manufacture", "our factory",
        "production facility", "our plant", "fabricat", "oem", "odm",
        "in-house production", "production capacity",
    ],
    "Importer": [
        "importer", "import", "we import", "imported from", "importing",
        "customs", "iec", "cif", "fob", "incoterms",
    ],
    "Wholesaler": [
        "wholesaler", "wholesale", "bulk supply", "bulk order",
        "minimum order quantity", "moq", "bulk pricing",
    ],
    "Distributor": [
        "distributor", "distribution", "authorised distributor",
        "authorized distributor", "exclusive distributor", "channel partner",
        "sole distributor",
    ],
    "Trader": [
        "trader", "trading company", "trading house", "buy and sell",
        "commodity trading",
    ],
    "Retailer": [
        "retailer", "retail", "showroom", "store", "shop online",
        "add to cart", "buy now", "walk-in",
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
    "Amsterdam","Milan","Zurich","Tokyo","Osaka",
]
_CITY_RE = re.compile(
    r"\b(" + "|".join(re.escape(c) for c in _MAJOR_CITIES) + r")\b",
    re.IGNORECASE,
)

_LINKEDIN_RE = re.compile(
    r'https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+/?',
    re.IGNORECASE,
)
_TWITTER_RE = re.compile(
    r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+/?',
    re.IGNORECASE,
)
_FACEBOOK_RE = re.compile(
    r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.]+/?',
    re.IGNORECASE,
)
_INSTAGRAM_RE = re.compile(
    r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+/?',
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
    re.compile(r"\bsince\s+(\d{4})\b", re.I),
    re.compile(r"\best(?:ablished)?\.?\s*(\d{4})\b", re.I),
]

_TURNOVER_PATTERNS = [
    re.compile(r"(?:annual\s+)?turnover[:\s]+(?:rs\.?|inr|usd|\$)?\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh|million|billion)?", re.I),
    re.compile(r"(?:revenue|sales)[:\s]+(?:rs\.?|inr|usd|\$)?\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh|million|billion)?", re.I),
    re.compile(r"(?:rs\.?|inr)\s*([\d,]+(?:\.\d+)?)\s*(cr(?:ore)?|lakh)\s*(?:turnover|revenue|sales)", re.I),
]

_CERT_PATTERNS = re.compile(
    r"\b(ISO\s*\d{4,5}(?::\d{4})?|BIS|CE\b|FDA|GMP|HACCP|FSSAI|"
    r"OHSAS|SA\s*8000|IATF|AS\s*9100|NADCAP|REACH|RoHS|"
    r"IS\s*\d+|R-\d+)\b",
    re.I,
)

_EXPORT_MARKETS = [
    "usa", "united states", "uk", "europe", "middle east", "uae", "dubai",
    "africa", "southeast asia", "australia", "canada", "germany", "france",
    "japan", "china", "bangladesh", "sri lanka", "nepal", "bhutan",
]

INDUSTRY_MAP = {
    "Electronics":     ["electronics","semiconductor","circuit","pcb","led","display","solar panel"],
    "Pharmaceuticals": ["pharma","pharmaceutical","medicine","drug","api","tablet","capsule"],
    "Textiles":        ["textile","fabric","garment","apparel","yarn","weaving","knitting"],
    "Chemicals":       ["chemical","polymer","resin","adhesive","solvent","dye","pigment"],
    "Machinery":       ["machinery","machine","equipment","cnc","lathe","press","pump"],
    "Food & Beverage": ["food","beverage","spice","grain","dairy","snack","confection"],
    "Automotive":      ["automotive","automobile","vehicle","car","truck","tyre","auto parts"],
    "Construction":    ["construction","cement","steel","rebar","building","tile","pipe"],
    "IT & Software":   ["software","it services","saas","technology","cloud","erp","app"],
    "Healthcare":      ["healthcare","hospital","medical device","diagnostics","surgical"],
    "Logistics":       ["logistics","freight","shipping","warehouse","supply chain","courier"],
    "Agriculture":     ["agriculture","agro","fertilizer","pesticide","seed","crop","farm"],
    "Energy":          ["energy","solar","wind","power","battery","generator","inverter"],
    "Retail":          ["retail","ecommerce","e-commerce","marketplace","fmcg","consumer"],
}

EMAIL_RE  = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}")
PHONE_RE  = re.compile(r"(?:\+91[\-\s]?|0)?[6-9]\d{9}|\+\d{1,3}[\s\-]?\d{6,12}")
PERSON_RE = re.compile(
    r"(?:(?:contact|reach|speak\s+to|talk\s+to|email)\s*[:\-]?\s*"
    r"|(?:Mr|Ms|Mrs|Dr|Shri|Smt)\.?\s+)([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})"
)
PERSON_TITLE_RE = re.compile(
    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\s*[,\-–]\s*"
    r"(?:CEO|MD|Director|Manager|Founder|Partner|Chairman|President|Owner|Proprietor)",
    re.I,
)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _sanitise_query(query: str, country_filter: str = "") -> str:
    clean_q = _QUERY_STRIP_WORDS.sub("", query).strip()
    clean_q = re.sub(r"\s{2,}", " ", clean_q)
    if country_filter and country_filter.lower() not in clean_q.lower():
        clean_q = f"{clean_q} {country_filter}"
    return clean_q.strip()


def _is_company_url(url: str, title: str = "") -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    netloc = parsed.netloc.lower().replace("www.", "")
    for bad in BAD_DOMAINS:
        if bad.lower() in netloc:
            return False
    if _FREE_HOST_RE.search(netloc):
        return False
    return True


def _clean_title(title: str) -> str:
    suffixes = re.compile(
        r"\s*[\|\-\u2013\u2014:]+\s*(home|welcome|official\s+website|"
        r"about\s+us|contact\s+us|index|homepage)\s*$",
        re.IGNORECASE,
    )
    return suffixes.sub("", title).strip()


def _domain_authority_heuristic(url: str) -> float:
    netloc = urlparse(url).netloc.lower().replace("www.", "")
    score  = 0.5
    if netloc.endswith(".com"):   score += 0.20
    if any(netloc.endswith(t) for t in
           [".ae", ".in", ".co.uk", ".com.au", ".sg", ".ca", ".co.in"]):
        score += 0.15
    if len(netloc.split(".")) > 3: score -= 0.10
    return round(min(max(score, 0.0), 1.0), 3)


def _detect_channel_type(text: str) -> str:
    text_lower = text.lower()
    scores = {ch: sum(1 for kw in kws if kw in text_lower)
              for ch, kws in _CHANNEL_KEYWORDS.items()}
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
        (re.compile(r"\b(\d{1,4})\s*[-–to]+\s*(\d{2,5})\s*(employees|staff|people)\b", re.I), "{a}–{b}"),
        (re.compile(r"\b(\d{2,5})\s*\+?\s*(employees|staff|people|professionals|workers)\b", re.I), "{n}+"),
        (re.compile(r"team\s+of\s+(\d+)", re.I), "team of {n}"),
        (re.compile(r"(1[-–]10|11[-–]50|51[-–]200|201[-–]500|501[-–]1000|1001[-–]5000|5001\+)\s*(employees)?", re.I), "{n}"),
    ]
    for pattern, label in patterns:
        m = pattern.search(text)
        if m:
            if "{a}" in label:
                return f"{m.group(1)}–{m.group(2)}"
            return label.replace("{n}", m.group(1))
    return ""


def _detect_turnover(text: str) -> str:
    for pat in _TURNOVER_PATTERNS:
        m = pat.search(text)
        if m:
            val  = m.group(1).replace(",", "")
            unit = (m.group(2) or "").lower() if m.lastindex >= 2 else ""
            return f"₹{val} {unit}".strip() if unit else f"₹{val}"
    return ""


def _detect_certifications(text: str) -> list:
    found = list(set(m.group(0).strip()
                     for m in _CERT_PATTERNS.finditer(text)))
    return found[:10]


def _detect_export_markets(text: str) -> list:
    text_lower = text.lower()
    return [m.title() for m in _EXPORT_MARKETS if m in text_lower]


def _detect_social_links(html: str) -> dict:
    social = {}
    for platform, pattern in [
        ("linkedin",  _LINKEDIN_RE),
        ("twitter",   _TWITTER_RE),
        ("facebook",  _FACEBOOK_RE),
        ("instagram", _INSTAGRAM_RE),
    ]:
        m = pattern.search(html)
        if m:
            social[platform] = m.group(0).rstrip("/")
    return social


def _detect_product_type(text: str, query: str = "") -> str:
    words = [w for w in re.findall(r"[a-zA-Z]{4,}", query.lower())
             if w not in {"from","with","that","this","their","company",
                          "import","export","india","best","list","find"}]
    if words:
        return " ".join(words[:3]).title()
    return ""


def _detect_contact_person(text: str) -> str:
    # Try title-based pattern first (more reliable)
    m = PERSON_TITLE_RE.search(text)
    if m:
        return m.group(1).strip()
    # Fallback to contact-prefix pattern
    m = PERSON_RE.search(text)
    if m:
        return m.group(1).strip()
    return ""


# ---------------------------------------------------------------------------
# Deep website crawler — visits up to 6 pages per company
# ---------------------------------------------------------------------------

def _fetch_page(url: str, timeout: int = 8) -> tuple[str, str]:
    """Returns (text, html) for a URL, empty strings on failure."""
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
        text = soup.get_text(separator=" ", strip=True)
        return text[:6000], html[:30000]
    except Exception:
        return "", ""


def deep_crawl_website(website: str, query: str = "") -> dict:
    """
    Crawl multiple pages of a company website for maximum data extraction.
    Returns a rich dict with all extracted fields.
    """
    empty = {
        "email": "", "phone": "", "content": "", "all_html": "",
        "city": "", "country_detected": "", "linkedin_url": "",
        "twitter_url": "", "facebook_url": "", "instagram_url": "",
        "incorporation_date": "", "company_size": "", "channel_type": "",
        "contact_person": "", "contact_email": "", "active_website": website or "",
        "industry_detected": "", "product_type": "",
        "annual_turnover": "", "certifications": [], "export_markets": [],
        "social_links": {},
    }
    if not website:
        return empty

    base = website.rstrip("/")
    all_text = ""
    all_html = ""
    emails   = set()
    phones   = set()
    persons  = []

    # Try Node.js crawler first for the homepage
    node_ok = False
    try:
        resp = requests.post(
            f"{NODE_CRAWLER_URL}/crawl",
            json={"url": website}, timeout=15,
        )
        if resp.status_code == 200:
            d = resp.json()
            all_text += " " + d.get("content", "")
            all_html += d.get("html", "")
            if d.get("email"):   emails.add(d["email"])
            if d.get("phone"):   phones.add(d["phone"])
            node_ok = True
    except Exception:
        pass

    # BS4 fallback + additional pages
    pages_to_try = CRAWL_PATHS[:6] if node_ok else CRAWL_PATHS[:10]

    def _crawl_path(path):
        url = base + path if path else base
        return _fetch_page(url)

    with ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(_crawl_path, p): p for p in pages_to_try}
        for future in as_completed(futures, timeout=25):
            try:
                text, html = future.result(timeout=10)
                if text:
                    all_text += " " + text
                    all_html += html
                    # Extract contact info from each page
                    for m in EMAIL_RE.finditer(text):
                        emails.add(m.group())
                    for m in PHONE_RE.finditer(text):
                        phones.add(m.group().strip())
            except Exception:
                pass

    # Cap content size
    all_text = all_text[:12000].strip()
    all_html = all_html[:50000]

    # Find contact person
    for txt_chunk in [all_text[i:i+3000] for i in range(0, min(len(all_text),9000), 3000)]:
        p = _detect_contact_person(txt_chunk)
        if p:
            persons.append(p)

    # Filter out bad emails (icons, images etc)
    clean_emails = [e for e in emails
                    if not re.search(r"\.(png|jpg|gif|svg|ico|css|js)$", e, re.I)
                    and len(e) < 80]
    best_email = next(
        (e for e in clean_emails if not re.search(
            r"^(info|contact|admin|support|sales|hello|noreply)", e, re.I)
        ),
        clean_emails[0] if clean_emails else ""
    )

    social = _detect_social_links(all_html)

    result = {
        "email":              best_email or (clean_emails[0] if clean_emails else ""),
        "phone":              sorted(phones, key=len, reverse=True)[0] if phones else "",
        "content":            all_text,
        "all_html":           all_html,
        "city":               _detect_city(all_text, all_html),
        "country_detected":   _detect_country_from_text(all_text),
        "linkedin_url":       social.get("linkedin", ""),
        "twitter_url":        social.get("twitter", ""),
        "facebook_url":       social.get("facebook", ""),
        "instagram_url":      social.get("instagram", ""),
        "incorporation_date": _detect_incorporation(all_text),
        "company_size":       _detect_company_size(all_text),
        "channel_type":       _detect_channel_type(all_text),
        "contact_person":     persons[0] if persons else "",
        "contact_email":      best_email or (clean_emails[0] if clean_emails else ""),
        "active_website":     website,
        "industry_detected":  _detect_industry(all_text),
        "product_type":       _detect_product_type(all_text, query),
        "annual_turnover":    _detect_turnover(all_text),
        "certifications":     _detect_certifications(all_text),
        "export_markets":     _detect_export_markets(all_text),
        "social_links":       social,
    }
    return result


# ---------------------------------------------------------------------------
# LLM analysis — upgraded 20-field prompt, uses any available provider
# ---------------------------------------------------------------------------

_DEEP_LLM_PROMPT = """\
You are an expert B2B business analyst. Analyse the company website content below \
against the search query and extract a comprehensive business profile.

Search Query: {query}

Company Website Content (multiple pages):
{content}

Return ONLY a valid JSON object — no explanation, no markdown, no extra text.

{{
  "summary":            "2-3 sentences describing what this company does, who their customers are, and what makes them unique",
  "products":           ["list of specific products or services offered"],
  "product_type":       "Primary product category (specific, e.g. LED Street Lights, API Pharmaceuticals)",
  "industry":           "Industry sector",
  "channel_type":       "Manufacturer / Importer / Trader / Wholesaler / Distributor / Retailer",
  "company_size":       "Employee count or range if mentioned",
  "annual_turnover":    "Annual turnover or revenue if mentioned (e.g. ₹50 Crore, $2M)",
  "city":               "Headquarters city",
  "country":            "Headquarters country",
  "incorporation_date": "Year or date company was founded/incorporated",
  "contact_person":     "Name of owner/director/CEO if mentioned",
  "contact_email":      "Best contact email found",
  "linkedin_url":       "LinkedIn company URL if found",
  "certifications":     ["list of certifications: ISO, BIS, CE, FDA, GMP etc"],
  "export_markets":     ["countries or regions they export to"],
  "key_customers":      ["notable clients or customer types mentioned"],
  "usp":                "Their unique selling point or competitive advantage in one sentence",
  "relevant":           true or false,
  "score":              1-10
}}
"""


def _llm_analyze(query: str, content: str, company_name: str = "") -> dict:
    """Call any available LLM provider for deep company analysis."""
    fallback = {
        "summary": "", "products": [], "product_type": "", "industry": "",
        "channel_type": "", "company_size": "", "annual_turnover": "",
        "city": "", "country": "", "incorporation_date": "",
        "contact_person": "", "contact_email": "", "linkedin_url": "",
        "certifications": [], "export_markets": [], "key_customers": [],
        "usp": "", "relevant": False, "score": 0,
    }

    if not content or len(content.strip()) < 80:
        return fallback

    try:
        from llm import _get_provider, _call_llm, _extract_json
    except ImportError:
        try:
            from .llm import _get_provider, _call_llm, _extract_json
        except ImportError:
            return fallback

    provider = _get_provider()
    if not provider:
        logger.warning("No LLM provider available (no API keys set)")
        return fallback

    logger.info("Using LLM provider: %s for company: %s",
                provider.get("url","?")[:30], company_name)

    # Use first 8000 chars of content for deep analysis
    prompt = _DEEP_LLM_PROMPT.format(
        query=query[:300],
        content=content[:8000],
    )

    try:
        import json
        text   = _call_llm([{"role": "user", "content": prompt}],
                           max_tokens=1000, temperature=0.1)
        result = _extract_json(text)

        # Normalise
        def _str(v):  return str(v or "").strip()
        def _lst(v):  return v if isinstance(v, list) else []

        return {
            "summary":            _str(result.get("summary")),
            "products":           _lst(result.get("products")),
            "product_type":       _str(result.get("product_type")),
            "industry":           _str(result.get("industry")),
            "channel_type":       _str(result.get("channel_type","")).strip().title()
                                  if result.get("channel_type") in
                                  {"Manufacturer","Importer","Trader",
                                   "Wholesaler","Distributor","Retailer",""}
                                  else "",
            "company_size":       _str(result.get("company_size")),
            "annual_turnover":    _str(result.get("annual_turnover")),
            "city":               _str(result.get("city")),
            "country":            _str(result.get("country")),
            "incorporation_date": _str(result.get("incorporation_date")),
            "contact_person":     _str(result.get("contact_person")),
            "contact_email":      _str(result.get("contact_email")),
            "linkedin_url":       _str(result.get("linkedin_url")),
            "certifications":     _lst(result.get("certifications")),
            "export_markets":     _lst(result.get("export_markets")),
            "key_customers":      _lst(result.get("key_customers")),
            "usp":                _str(result.get("usp")),
            "relevant":           bool(result.get("relevant", False)),
            "score":              max(0, min(int(result.get("score", 0) or 0), 10)),
        }
    except Exception as exc:
        logger.warning("LLM analysis failed for %s: %s", company_name, exc)
        return fallback


# ---------------------------------------------------------------------------
# Full enrichment pipeline
# ---------------------------------------------------------------------------

def enrich_company(company: dict, run_compliance: bool = False,
                   query: str = "") -> dict:
    website = company.get("website", "")
    name    = company.get("company", "")

    logger.info("Deep crawling: %s (%s)", name, website)
    crawl = deep_crawl_website(website, query=query)

    # Update company with crawl data
    company.update({
        "email":              crawl["email"],
        "phone":              crawl["phone"],
        "content":            crawl["content"],
        "city":               crawl["city"],
        "country_detected":   crawl["country_detected"],
        "linkedin_url":       crawl["linkedin_url"],
        "incorporation_date": crawl["incorporation_date"],
        "company_size":       crawl["company_size"],
        "channel_type":       crawl["channel_type"],
        "contact_person":     crawl["contact_person"],
        "contact_email":      crawl["contact_email"],
        "active_website":     crawl["active_website"],
        "industry_detected":  crawl["industry_detected"],
        "product_type":       crawl["product_type"],
        "annual_turnover":    crawl["annual_turnover"],
        "certifications":     crawl["certifications"],
        "export_markets":     crawl["export_markets"],
        "social_links":       crawl["social_links"],
    })

    # LLM deep analysis — uses ANY available provider (Grok, DeepSeek, OpenRouter)
    llm = _llm_analyze(query, crawl["content"], company_name=name)

    if llm["summary"]:
        company["ai_summary"] = llm["summary"]
    if llm["products"]:
        company["products"] = llm["products"]
    if llm["usp"]:
        company["usp"] = llm["usp"]
    if llm["key_customers"]:
        company["key_customers"] = llm["key_customers"]

    # LLM overrides rule-based if it found better data
    for crawl_field, llm_field in [
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
        if llm.get(llm_field) and not company.get(crawl_field):
            company[crawl_field] = llm[llm_field]

    # Merge certifications & export markets
    certs = list(set(crawl["certifications"] +
                     [str(c) for c in llm.get("certifications", [])]))
    exports = list(set(crawl["export_markets"] +
                       [str(e) for e in llm.get("export_markets", [])]))
    company["certifications"]  = certs[:15]
    company["export_markets"]  = exports[:15]
    company["llm_relevant"]    = llm["relevant"]
    company["llm_score"]       = llm["score"]
    company["product_type"]    = llm.get("product_type") or company.get("product_type","")

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
                    run_compliance: bool = False, query: str = "") -> list:
    """Enrich companies in parallel — 3 workers to avoid rate limits."""
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(enrich_company, c, run_compliance, query): c
            for c in companies
        }
        for future in as_completed(futures, timeout=120):
            try:
                enriched.append(future.result(timeout=60))
            except Exception as exc:
                logger.warning("Enrichment failed: %s", exc)
                c = futures[future]
                c.setdefault("ai_summary", c.get("snippet", ""))
                c.setdefault("products", [])
                enriched.append(c)
    return enriched


# ---------------------------------------------------------------------------
# Scoring — now includes LLM score, turnover, certifications
# ---------------------------------------------------------------------------

def _score_company(query: str, company: dict) -> dict:
    try:
        from nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query
    except ImportError:
        from .nlp import semantic_similarity, keyword_match_ratio, ai_summary_for_query

    content = company.get("content", "") or company.get("snippet", "")
    website = company.get("website", "")

    combined = " ".join(filter(None, [
        company.get("company", ""),
        company.get("snippet", ""),
        company.get("ai_summary", ""),
        content[:3000],
    ]))

    sem_score = semantic_similarity(query, combined) if combined.strip() else 0.0
    kw_score  = keyword_match_ratio(query, combined)
    da_score  = _domain_authority_heuristic(website)

    # Contact richness score
    contact = round(
        (0.4 if company.get("email") else 0.0) +
        (0.3 if company.get("phone") else 0.0) +
        (0.2 if company.get("contact_person") else 0.0) +
        (0.1 if company.get("linkedin_url") else 0.0), 2
    )

    # Bonus signals
    bonus = 0.0
    if company.get("annual_turnover"):  bonus += 0.03
    if company.get("certifications"):   bonus += 0.02
    if company.get("export_markets"):   bonus += 0.02
    if company.get("incorporation_date"): bonus += 0.01

    llm_score = float(company.get("llm_score", 0) or 0) / 10.0

    if llm_score > 0:
        final_score = round(
            (0.30 * sem_score) +
            (0.15 * kw_score)  +
            (0.15 * da_score)  +
            (0.15 * contact)   +
            (0.20 * llm_score) +
            (0.05 * bonus / 0.08),  # normalise bonus
            3,
        )
    else:
        final_score = round(
            (0.40 * sem_score) +
            (0.20 * kw_score)  +
            (0.20 * da_score)  +
            (0.15 * contact)   +
            (0.05 * bonus / 0.08),
            3,
        )

    final_score = min(final_score, 1.0)

    importance = (
        "high"   if final_score >= 0.55 else
        "medium" if final_score >= 0.35 else
        "low"
    )

    if not company.get("ai_summary") and combined.strip():
        company["ai_summary"] = ai_summary_for_query(query, combined, max_sentences=3)

    company.update({
        "semantic_score":   sem_score,
        "keyword_score":    kw_score,
        "domain_authority": da_score,
        "contact_presence": contact,
        "final_score":      final_score,
        "importance":       importance,
        "products":         company.get("products", []),
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
) -> dict:
    if not SERP_API_KEY or not SERP_API_KEY.strip():
        logger.error("SERP_API_KEY is not set!")
        return {"companies": [], "next_start": start, "has_more": False,
                "pages_scanned": 0, "effective_country": country_filter or "",
                "error": "SERP_API_KEY not configured"}

    country_filter = (country_filter or "").strip().lower()
    search_query   = _sanitise_query(query, country_filter)
    logger.info("Deep search: %s", search_query[:120])

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
        results    = GoogleSearch(params).get_dict()
        raw_results = results.get("organic_results", [])
        logger.info("SerpAPI: %d results for '%s'", len(raw_results), search_query)
    except Exception as exc:
        logger.error("SerpAPI failed: %s", exc)
        return {"companies": [], "next_start": start, "has_more": False,
                "pages_scanned": 0, "effective_country": country_filter,
                "error": str(exc)}

    if not raw_results:
        logger.warning("No results. Keys: %s | Error: %s",
                       list(results.keys()), results.get("error", ""))

    candidates = []
    for r in raw_results:
        link  = r.get("link", "")
        title = r.get("title", "")
        if not link or not _is_company_url(link, title):
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

    logger.info("Candidates: %d / %d", len(candidates), len(raw_results))
    candidates = candidates[:max_results]

    if candidates:
        # Deep enrich with full crawl + LLM
        candidates = parallel_enrich(candidates, max_workers=3, query=query)

    scored = []
    for c in candidates:
        try:
            scored.append(_score_company(query, c))
        except Exception as exc:
            logger.warning("Scoring failed for %s: %s", c.get("website"), exc)
            for f in ["semantic_score","keyword_score","domain_authority",
                      "contact_presence","final_score"]:
                c.setdefault(f, 0.0)
            c.setdefault("importance",       "low")
            c.setdefault("ai_summary",       c.get("snippet",""))
            c.setdefault("products",         [])
            c.setdefault("llm_relevant",     None)
            c.setdefault("certifications",   [])
            c.setdefault("export_markets",   [])
            c.setdefault("annual_turnover",  "")
            c.setdefault("usp",              "")
            c.setdefault("key_customers",    [])
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
    params: dict = {
        "engine":  "google",
        "q":       f"{query} site:linkedin.com/in",
        "api_key": SERP_API_KEY,
        "num":     max_results,
    }
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
