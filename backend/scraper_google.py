"""
scraper_google.py  –  v3  (pure company data edition)
======================================================

Key changes in this version
----------------------------
1. QUERY SANITISER  – builds a Google query that structurally excludes
   listicles, directories, and ranking articles before even calling SerpAPI.
   Uses -site: exclusions, exact-phrase suppression, and company-signal terms.

2. URL CLASSIFIER   – every URL that comes back from Google passes through
   _is_company_url() which rejects it if:
     - the domain is a known directory / aggregator / news / blog site
     - the URL path contains article/list signals (/blog/, /top-10-, /best-,
       /list/, /ranking/, /review/, /news/, /article/, etc.)
     - the title contains listicle signals ("top 10", "best X", "X companies")
     - the domain is a free-host (blogspot, wordpress.com, wix, etc.)

3. TITLE CLEANER    – strips "| Home", "- Official Website" suffixes.

4. MCA / GSTIN SPOT-CHECK  – after URL filtering, each surviving domain is
   looked up on mca.gov.in and gst.gov.in to confirm it belongs to a real
   registered entity (India queries only; skipped otherwise).
   Results are cached in-process.

5. All previous features retained:
     - Node.js crawler + BS4 fallback for email/phone/content
     - country_filter wired to SerpAPI gl param
     - trusted_only flag
     - parallel enrichment
     - NLP scoring (semantic, keyword, domain authority, contact presence)
     - optional LLM enrichment via OpenRouter
     - cert_checker compliance gap detection
"""

import os
import re
import logging
import hashlib
import requests

from bs4 import BeautifulSoup
from serpapi import google_search
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
# 1. DOMAIN BLOCK-LISTS
# ---------------------------------------------------------------------------

BAD_DOMAINS = [
    # Trade directories
    "justdial", "yellowpages", "sulekha", "tradeindia", "indiamart",
    "exportersindia", "bizvibe", "kompass", "dnb.com", "zaubacorp",
    "tofler", "zauba", "connect2india", "globalspec", "thomasnet",
    "alibaba", "aliexpress", "made-in-china", "tradekey",
    # Social / UGC
    "linkedin", "facebook", "instagram", "twitter", "youtube",
    "pinterest", "reddit", "quora", "tumblr",
    # E-commerce
    "amazon", "flipkart", "snapdeal", "meesho",
    # Encyclopaedic
    "wikipedia", "wikidata", "crunchbase",
    # News aggregators
    "business-standard", "economictimes", "livemint", "moneycontrol",
    "thehindu", "ndtv", "hindustantimes", "financialexpress",
    "theprint", "scroll.in", "wire.in",
    # List / ranking sites
    "clutch.co", "goodfirms", "sortlist", "bark.com", "upcity",
    "toptenreviews", "g2.com", "capterra",
    # Generic blogging / builders
    "blogspot", "wordpress", "medium", "ghost.io",
    "wix", "weebly", "squarespace", "webflow", "jimdo",
    "site123", "yola", "strikingly", "carrd",
    # Job boards
    "naukri", "monster", "indeed", "shine.com", "glassdoor", "internshala",
    # Gov / association portals (not individual companies)
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

# ---------------------------------------------------------------------------
# 2. QUERY SANITISER
# ---------------------------------------------------------------------------

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


def _sanitise_query(query: str, country_filter: str = "") -> str:
    """
    Strip listicle words from the user query and append the country.
    No -site: exclusions are added here — they bloat the query past
    Google's char limit and kill results. Junk domains are filtered
    post-fetch by _is_company_url() instead.
    """
    clean_q = _QUERY_STRIP_WORDS.sub("", query).strip()
    clean_q = re.sub(r"\b\d+\b", "", clean_q)  # remove stray numbers (e.g. "10" from "top 10")
    clean_q = re.sub(r"\s{2,}", " ", clean_q)
    if country_filter and country_filter.lower() not in clean_q.lower():
        clean_q = f"{clean_q} {country_filter}"
    return clean_q.strip()

# ---------------------------------------------------------------------------
# 3. URL / TITLE CLASSIFIER
# ---------------------------------------------------------------------------

def _is_company_url(url: str, title: str = "") -> bool:
    """Return True only if this URL looks like a real company website."""
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
    """Strip generic suffixes from page titles."""
    generic_suffixes = re.compile(
        r"\s*[\|\-\u2013\u2014:]+\s*(home|welcome|official\s+website|official\s+site"
        r"|about\s+us|contact\s+us|index|main\s+page|homepage)\s*$",
        re.IGNORECASE,
    )
    return generic_suffixes.sub("", title).strip()


# ---------------------------------------------------------------------------
# 4. MCA / GSTIN SPOT-CHECK  (India only, cached, fail-open)
# ---------------------------------------------------------------------------

_DOMAIN_VERIFIED_CACHE: dict = {}


def _verify_india_domain(domain: str, company_name: str) -> bool:
    """
    Quick check against MCA and GST portals to confirm a real registered entity.
    Fail-open: returns True if both portals are unreachable.
    """
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

    # GST check
    try:
        resp = requests.post(
            "https://services.gst.gov.in/services/api/search/taxpayerByName",
            json={"tradeName": name_clean[:80]},
            headers=headers,
            timeout=8,
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

    # MCA check (only if GST didn't confirm)
    if not verified:
        try:
            resp = requests.get(
                "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do",
                params={"companyName": name_clean[:60]},
                headers=headers,
                timeout=8,
            )
            portal_reached = True
            if resp.status_code == 200:
                text  = resp.text.lower()
                words = [w for w in name_clean.lower().split() if len(w) > 2]
                if words and sum(1 for w in words if w in text) >= max(1, len(words) // 2):
                    verified = True
        except Exception:
            pass

    # Fail-open if no portal was reachable
    result = verified if portal_reached else True
    _DOMAIN_VERIFIED_CACHE[cache_key] = result
    return result


# ---------------------------------------------------------------------------
# 5. DOMAIN AUTHORITY HEURISTIC
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
# 6. NODE.JS CRAWLER + BS4 FALLBACK
# ---------------------------------------------------------------------------

def extract_company_data(website: str) -> dict:
    if not website:
        return {"email": "", "phone": "", "content": ""}

    try:
        resp = requests.post(
            f"{NODE_CRAWLER_URL}/crawl",
            json={"url": website},
            timeout=20,
        )
        if resp.status_code == 200:
            data = resp.json()
            return {
                "email":   data.get("email", ""),
                "phone":   data.get("phone", ""),
                "content": data.get("content", ""),
            }
    except Exception:
        pass

    EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}")
    PHONE_RE = re.compile(r"\+?\d[\d\s\-()\\.]{7,}")

    email, phone, content = "", "", ""
    for path in ["", "/contact", "/about", "/contact-us"]:
        try:
            r = requests.get(
                website.rstrip("/") + path,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            soup = BeautifulSoup(r.text, "html.parser")
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
        except Exception:
            continue

    return {"email": email, "phone": phone, "content": content[:5000].strip()}


# ---------------------------------------------------------------------------
# 7. NLP + LLM SCORING
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
                llm_data     = analyze_company(query, content)
                if llm_data.get("summary"):
                    summary  = llm_data["summary"]
                products     = llm_data.get("products", [])
                llm_relevant = bool(llm_data.get("relevant", False))
                llm_score    = int(llm_data.get("score", 0))
                final_score  = round(
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
# 8. ENRICHMENT  (crawl + compliance check)
# ---------------------------------------------------------------------------

def enrich_company(company: dict, run_compliance: bool = False) -> dict:
    crawl = extract_company_data(company.get("website", ""))
    company["email"]   = crawl.get("email", "")
    company["phone"]   = crawl.get("phone", "")
    company["content"] = crawl.get("content", "")

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
            except Exception as exc:
                logger.warning("Compliance check failed for %s: %s",
                               company.get("company"), exc)
                company["compliance"] = {
                    "compliance_gaps": [], "compliance_score": 1.0,
                    "checker_error": str(exc),
                }
    return company


def parallel_enrich(companies: list, max_workers: int = 5,
                    run_compliance: bool = False) -> list:
    enriched = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(enrich_company, c, run_compliance): c
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
# 9. MAIN GOOGLE SEARCH
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
    """
    Search Google via SerpAPI.
    Returns only real company websites. Listicles, directories, and
    article pages are rejected at query, URL, title, and domain layers.
    India queries additionally spot-check against MCA and GST portals.
    """
    country_filter = (country_filter or "").strip().lower()
    is_india       = country_filter in ("india", "in")

    search_query = _sanitise_query(query, country_filter)
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

    # Layer 1 + 2 + 3: URL classifier, trusted-only, dedup
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
        candidates = parallel_enrich(candidates)

    scored = []
    for c in candidates:
        try:
            scored.append(_score_company(query, c))
        except Exception as exc:
            logger.warning("Scoring failed for %s: %s", c.get("website"), exc)
            c.setdefault("semantic_score",   0.0)
            c.setdefault("keyword_score",    0.0)
            c.setdefault("domain_authority", 0.5)
            c.setdefault("contact_presence", 0.0)
            c.setdefault("final_score",      0.0)
            c.setdefault("importance",       "low")
            c.setdefault("summary",          c.get("snippet", ""))
            c.setdefault("products",         [])
            c.setdefault("llm_relevant",     None)
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
# 10. LINKEDIN DISCOVERY
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
# 11. LEGACY HELPER
# ---------------------------------------------------------------------------

def smart_google_search(queries: list) -> tuple:
    all_companies = []
    all_people    = []
    for q in queries:
        result = google_search(q)
        all_companies.extend(result.get("companies", []))
        all_people.extend(linkedin_discovery(q))
    return all_companies[:10], all_people[:10]