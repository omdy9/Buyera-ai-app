import hashlib
import os
import re
import threading
import time
import requests
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from urllib.parse import quote_plus, urljoin, urlparse, urlunparse

try:
    # google-search-results package (legacy, widely used)
    from serpapi import GoogleSearch
    _HAS_GOOGLE_SEARCH_CLASS = True
except Exception:
    # serpapi package (new client) exposes `search(...)` instead
    from serpapi import search as serpapi_search
    _HAS_GOOGLE_SEARCH_CLASS = False

if __package__:
    from .llm import analyze_with_llm, llm_enabled, structure_query_with_llm
    from .nlp import ai_summary_for_query, keyword_match_ratio, semantic_similarity
else:
    from llm import analyze_with_llm, llm_enabled, structure_query_with_llm
    from nlp import ai_summary_for_query, keyword_match_ratio, semantic_similarity

load_dotenv()

SERP_API_KEY = os.getenv("SERP_API_KEY")

EMAIL_RE = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
PHONE_RE = r"\+?\d[\d\s\-()]{9,}"
MAX_SITE_PAGES = 20
MAX_CONTENT_CHARS = 25000
SERP_PAGE_SIZE = 10
MAX_CRAWL_WORKERS = 6
MAX_EXTRACT_WORKERS = int(os.getenv("MAX_EXTRACT_WORKERS", "6"))
MAX_AI_WORKERS = int(os.getenv("MAX_AI_WORKERS", "4"))
MAX_AI_ENRICHMENT_CANDIDATES = int(os.getenv("MAX_AI_ENRICHMENT_CANDIDATES", "4"))

SEARCH_CACHE_TTL_SEC = int(os.getenv("SEARCH_CACHE_TTL_SEC", str(24 * 60 * 60)))
PAGE_CACHE_TTL_SEC = int(os.getenv("PAGE_CACHE_TTL_SEC", str(7 * 24 * 60 * 60)))
LLM_CACHE_TTL_SEC = int(os.getenv("LLM_CACHE_TTL_SEC", str(7 * 24 * 60 * 60)))
QUERY_STRUCT_CACHE_TTL_SEC = int(os.getenv("QUERY_STRUCT_CACHE_TTL_SEC", str(24 * 60 * 60)))

MIN_FINAL_SCORE = float(os.getenv("MIN_FINAL_SCORE", "0.45"))
TRUSTED_ONLY_MIN_AUTHORITY = float(os.getenv("TRUSTED_ONLY_MIN_AUTHORITY", "0.7"))
COUNTRY_HARD_FILTER = os.getenv("COUNTRY_HARD_FILTER", "false").lower() == "true"
COUNTRY_SOFT_PENALTY = float(os.getenv("COUNTRY_SOFT_PENALTY", "0.12"))
ALLOW_NO_CONTACT_RESULTS = os.getenv("ALLOW_NO_CONTACT_RESULTS", "true").lower() == "true"
NO_CONTACT_SCORE_PENALTY = float(os.getenv("NO_CONTACT_SCORE_PENALTY", "0.12"))
RELAXED_MIN_FINAL_SCORE = float(os.getenv("RELAXED_MIN_FINAL_SCORE", "0.22"))
ENABLE_EMPTY_PAGE_FALLBACK = os.getenv("ENABLE_EMPTY_PAGE_FALLBACK", "true").lower() == "true"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
}

_CACHE_LOCK = threading.Lock()
_SEARCH_CACHE = {}
_PAGE_CACHE = {}
_LLM_CACHE = {}
_QUERY_STRUCT_CACHE = {}
_REQUEST_SESSION = requests.Session()


def _serp_search(params):
    if _HAS_GOOGLE_SEARCH_CLASS:
        return GoogleSearch(params).get_dict()
    return serpapi_search(params)


BLOCKED_DOMAINS = {
    "yellowpages.com",
    "yellowpages.in",
    "yelp.com",
    "justdial.com",
    "sulekha.com",
    "indiamart.com",
    "tradeindia.com",
    "quikr.com",
    "olx.in",
    "locanto.com",
    "classifiedads.com",
    "hotfrog.com",
    "superpages.com",
    "angi.com",
    "manta.com",
    "clutch.co",
    "goodfirms.co",
    "threebestrated.com",
}

BLOCKED_TERMS = (
    "list of",
    "directory",
    "directories",
    "classified",
    "classifieds",
    "yellow pages",
    "listing",
    "listings",
    "top 10",
    "top companies",
    "top service providers",
    "best companies",
    "best service providers",
    "companies in",
    "suppliers in",
    "business list",
)

CONSULTING_TERMS = (
    "consultant",
    "consultancy",
    "advisory",
    "advisor",
    "service provider",
    "agency",
    "broker",
    "documentation",
    "compliance service",
    "registration service",
    "certification consultant",
    "license consultant",
    "legal service",
    "ca firm",
    "chartered accountant",
    "accounting firm",
    "dgft consultant",
    "gst consultant",
    "bis consultant",
    "epr consultant",
)

BUSINESS_OPERATION_TERMS = (
    "manufacturer",
    "manufacturing",
    "exporter",
    "importer",
    "supplier",
    "trader",
    "distributor",
    "wholesaler",
    "factory",
    "production",
    "product range",
    "our products",
    "catalog",
    "we export",
    "we import",
    "exports",
    "imports",
)

ROLE_HINTS = {
    "exporter": ("exporter", "export", "exports", "exporting"),
    "importer": ("importer", "import", "imports", "importing"),
    "manufacturer": ("manufacturer", "manufacturing", "factory", "producer"),
    "supplier": ("supplier", "suppliers", "wholesale", "trader", "trading"),
    "distributor": ("distributor", "distribution", "dealer"),
}

LISTING_PATH_TERMS = (
    "/directory",
    "/directories",
    "/classified",
    "/classifieds",
    "/list",
    "/listing",
    "/rankings",
    "/top-",
)

LISTING_RE = re.compile(
    r"\b(list of|directories?|classifieds?|yellow pages|top\s+\d+|best\s+\d+|companies in|suppliers in)\b",
    re.IGNORECASE,
)

FILE_EXT_RE = re.compile(
    r"\.(jpg|jpeg|png|gif|svg|webp|pdf|zip|rar|7z|doc|docx|xls|xlsx|ppt|pptx|mp4|mp3)$",
    re.IGNORECASE
)

TRUSTED_GLOBAL_DOMAINS = {
    "mca.gov.in": 1.0,
    "zaubacorp.com": 0.95,
    "tofler.in": 0.95,
    "walza.com": 0.9,
}

COUNTRY_HINTS = {
    "india": {"india", ".in", "bharat", "delhi", "mumbai", "bangalore", "chennai"},
    "usa": {"usa", "united states", "u.s.", "america", ".us"},
    "uk": {"uk", "united kingdom", "england", ".uk"},
    "uae": {"uae", "united arab emirates", "dubai", "abu dhabi", ".ae"},
    "canada": {"canada", ".ca"},
    "italy": {"italy", "italia", ".it", "milan", "rome"},
    "china": {"china", "prc", ".cn", "beijing", "shanghai", "guangzhou", "shenzhen"},
    "singapore": {"singapore", ".sg"},
    "dubai": {"dubai", "uae", ".ae"},
    "australia": {"australia", ".au"},
    "germany": {"germany", "deutschland", ".de"},
}

JUNK_TEXT_TERMS = (
    "cookie policy",
    "privacy policy",
    "terms of service",
    "enable javascript",
    "javascript is disabled",
    "page not found",
    "404",
    "lorem ipsum",
)


def _now():
    return int(time.time())


def _cache_get(cache_store, key):
    with _CACHE_LOCK:
        item = cache_store.get(key)
        if not item:
            return None
        if item["expires_at"] <= _now():
            cache_store.pop(key, None)
            return None
        return item["value"]


def _cache_set(cache_store, key, value, ttl_seconds):
    with _CACHE_LOCK:
        cache_store[key] = {
            "value": value,
            "expires_at": _now() + max(1, int(ttl_seconds)),
        }


def _hash_key(text):
    return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()


def _clip01(value):
    try:
        return max(0.0, min(1.0, float(value)))
    except Exception:
        return 0.0


def _normalize_country(country):
    c = (country or "").strip().lower()
    if c in {"us", "u.s.", "united states of america"}:
        return "usa"
    if c in {"united arab emirates", "uae", "abu dhabi"}:
        return "uae"
    if c == "dubai":
        return "dubai"
    if c in {"prc", "people's republic of china"}:
        return "china"
    return c


def _extract_country_from_query(query):
    q = (query or "").lower()
    for country, hints in COUNTRY_HINTS.items():
        if any(h in q for h in hints):
            return country
    return ""


def _country_match_score(country, *texts):
    country = _normalize_country(country)
    if not country:
        return 1.0

    hints = COUNTRY_HINTS.get(country, set())
    merged = " ".join((t or "").lower() for t in texts)

    if not hints:
        # Fallback for ad-hoc country/location values.
        if re.search(rf"\b{re.escape(country)}\b", merged):
            return 0.5
        return 0.0

    hits = sum(1 for h in hints if h in merged)
    if hits == 0:
        return 0.0
    return min(1.0, hits / max(3, len(hints)))


def _country_search_phrase(country):
    c = _normalize_country(country)
    if not c:
        return ""
    phrases = {
        "uae": "UAE Dubai Abu Dhabi",
        "dubai": "Dubai UAE",
        "usa": "USA United States",
        "uk": "UK United Kingdom",
        "italy": "Italy",
        "china": "China",
        "singapore": "Singapore",
        "canada": "Canada",
    }
    return phrases.get(c, c)


def _domain_authority(domain):
    d = (domain or "").lower()
    if not d:
        return 0.0

    for trusted, score in TRUSTED_GLOBAL_DOMAINS.items():
        if d == trusted or d.endswith("." + trusted):
            return score

    if ".gov." in d or d.endswith(".gov"):
        return 0.95
    if d.endswith(".edu"):
        return 0.85
    if d.endswith(".org"):
        return 0.65
    if d.endswith(".com") or d.endswith(".net"):
        return 0.55
    return 0.45


def _importance_label(final_score):
    score = _clip01(final_score)
    if score >= 0.75:
        return "high"
    if score >= 0.55:
        return "medium"
    return "low"


def _looks_like_junk(text, title="", snippet=""):
    merged = f"{title} {snippet} {(text or '')[:3000]}".lower()
    junk_hits = sum(1 for term in JUNK_TEXT_TERMS if term in merged)
    alpha_count = len(re.findall(r"[a-zA-Z]", merged))
    if junk_hits >= 2:
        return True
    # Avoid over-filtering short snippets; apply this check only on larger bodies.
    if alpha_count < 180 and len(merged) > 900:
        return True
    if alpha_count < 40 and junk_hits > 0:
        return True
    return False


def _company_recorder_links(company_name):
    name = (company_name or "").strip()
    if not name:
        return []

    q = quote_plus(name)
    return [
        {"source": "tofler", "query_url": f"https://www.google.com/search?q=site%3Atofler.in+{q}"},
        {"source": "zauba", "query_url": f"https://www.google.com/search?q=site%3Azaubacorp.com+{q}"},
        {"source": "mca", "query_url": f"https://www.google.com/search?q=site%3Amca.gov.in+{q}"},
        {"source": "walza", "query_url": f"https://www.google.com/search?q=site%3Awalza.com+{q}"},
    ]


def clean_domain(url):
    try:
        return urlparse(url).netloc.replace("www.","")
    except:
        return ""


def fetch_page(url):
    normalized = normalize_url(url)
    cached = _cache_get(_PAGE_CACHE, normalized)
    if cached is not None:
        return cached

    try:
        r = _REQUEST_SESSION.get(normalized, headers=HEADERS, timeout=15)
        text = r.text
        _cache_set(_PAGE_CACHE, normalized, text, PAGE_CACHE_TTL_SEC)
        return text
    except Exception:
        return ""


def _get_structured_query(query):
    key = _hash_key(f"struct::{query}")
    cached = _cache_get(_QUERY_STRUCT_CACHE, key)
    if cached is not None:
        return cached

    structured = structure_query_with_llm(query)
    structured = structured if isinstance(structured, dict) else {}
    if not structured.get("search_query"):
        structured["search_query"] = query
    if "country" not in structured:
        structured["country"] = ""
    if "must_have_terms" not in structured or not isinstance(structured["must_have_terms"], list):
        structured["must_have_terms"] = []
    if "exclude_terms" not in structured or not isinstance(structured["exclude_terms"], list):
        structured["exclude_terms"] = []

    _cache_set(_QUERY_STRUCT_CACHE, key, structured, QUERY_STRUCT_CACHE_TTL_SEC)
    return structured


def _fetch_serp_result_page(search_q, start):
    key = _hash_key(f"serp::{search_q}::{start}")
    cached = _cache_get(_SEARCH_CACHE, key)
    if cached is not None:
        return cached

    params = {
        "engine": "google",
        "q": search_q,
        "api_key": SERP_API_KEY,
        "num": SERP_PAGE_SIZE,
        "start": start,
    }
    results = _serp_search(params)
    _cache_set(_SEARCH_CACHE, key, results, SEARCH_CACHE_TTL_SEC)
    return results


def is_blocked_google_result(link, title="", snippet=""):
    domain = clean_domain(link).lower()
    if not domain:
        return True

    if any(domain == blocked or domain.endswith("." + blocked) for blocked in BLOCKED_DOMAINS):
        return True

    combined = f"{link} {title} {snippet}".lower()
    if any(term in combined for term in BLOCKED_TERMS):
        return True

    path = urlparse(link).path.lower()
    if any(term in path for term in LISTING_PATH_TERMS):
        return True

    if LISTING_RE.search(f"{title} {snippet}"):
        return True

    return False


def _count_hits(text, terms):
    low = (text or "").lower()
    return sum(1 for term in terms if term in low)


def _query_target_roles(query):
    q = (query or "").lower()
    detected = set()
    for role, hints in ROLE_HINTS.items():
        if any(h in q for h in hints):
            detected.add(role)
    return detected


def _role_evidence_in_text(roles, text):
    if not roles:
        return True

    low = (text or "").lower()
    for role in roles:
        if any(h in low for h in ROLE_HINTS.get(role, ())):
            return True
    return False


def is_consulting_or_non_business_result(query, title, snippet, summary, content):
    head = f"{title} {snippet}"
    full = f"{title} {snippet} {summary} {content[:2500] if content else ''}"

    consulting_hits = _count_hits(full, CONSULTING_TERMS)
    business_hits = _count_hits(full, BUSINESS_OPERATION_TERMS)
    roles = _query_target_roles(query)
    role_match = _role_evidence_in_text(roles, full)

    # Pure consulting context: reject.
    if consulting_hits >= 2 and business_hits == 0:
        return True

    if consulting_hits >= 3 and consulting_hits > business_hits:
        return True

    # If query asks for operator roles (e.g., exporters/importers), enforce role evidence.
    if roles and not role_match:
        return True

    # If headline itself looks like consultancy/service listing and lacks business cues, reject.
    if _count_hits(head, CONSULTING_TERMS) > 0 and business_hits < 2:
        return True

    return False


def _build_search_query(base_query, structured, business_only, country_filter=""):
    search_q = (structured.get("search_query") or base_query or "").strip()
    must_have = [
        t.strip() for t in structured.get("must_have_terms", [])
        if str(t).strip()
    ]
    exclude = [
        t.strip() for t in structured.get("exclude_terms", [])
        if str(t).strip()
    ]

    if business_only:
        exclude.extend(
            [
                "consultant",
                "consultancy",
                "advisory",
                "service provider",
                "directory",
                "listing",
            ]
        )

    if must_have:
        search_q = f"{search_q} " + " ".join(must_have)
    country_phrase = _country_search_phrase(country_filter)
    if country_phrase and country_phrase.lower() not in search_q.lower():
        search_q = f"{search_q} {country_phrase}"
    if exclude:
        search_q = f"{search_q} " + " ".join(f"-{x}" for x in dict.fromkeys(exclude))
    return search_q.strip()


def _compute_final_score(keyword_score, semantic_score, domain_authority, has_contact):
    contact_presence = 1.0 if has_contact else 0.0
    final_score = (
        0.4 * _clip01(keyword_score)
        + 0.3 * _clip01(semantic_score)
        + 0.2 * _clip01(domain_authority)
        + 0.1 * contact_presence
    )
    return round(final_score, 3), contact_presence


def _llm_cache_key(query, title, snippet, content):
    return _hash_key(
        f"llm::{query}::{title}::{snippet}::{(content or '')[:3500]}"
    )


def _analyze_with_llm_cached(query, content, title="", snippet=""):
    key = _llm_cache_key(query, title, snippet, content)
    cached = _cache_get(_LLM_CACHE, key)
    if cached is not None:
        return cached

    result = analyze_with_llm(
        query=query,
        content=content,
        title=title,
        snippet=snippet,
    )
    _cache_set(_LLM_CACHE, key, result, LLM_CACHE_TTL_SEC)
    return result


def _country_pass(country_filter, domain, title, snippet, content):
    country = _normalize_country(country_filter)
    if not country:
        return True

    score = _country_match_score(country, domain, title, snippet, content[:1200])
    return score > 0.0


def normalize_url(url):
    try:
        p = urlparse(url)
        return urlunparse((p.scheme, p.netloc, p.path.rstrip("/"), "", "", ""))
    except Exception:
        return url


def _priority_link_score(path):
    low = path.lower()
    if "/contact" in low:
        return 0
    if "/about" in low:
        return 1
    if "/service" in low or "/product" in low:
        return 2
    return 3


def _extract_internal_links(base_url, html):
    base_domain = clean_domain(base_url)
    if not base_domain:
        return []

    soup = BeautifulSoup(html, "html.parser")
    links = []

    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href:
            continue

        low_href = href.lower()
        if low_href.startswith("#") or low_href.startswith("mailto:") or low_href.startswith("tel:"):
            continue

        absolute = urljoin(base_url, href)
        parsed = urlparse(absolute)

        if parsed.scheme not in {"http", "https"}:
            continue

        if clean_domain(absolute) != base_domain:
            continue

        if FILE_EXT_RE.search(parsed.path or ""):
            continue

        links.append(normalize_url(absolute))

    links = list(dict.fromkeys(links))
    links.sort(key=lambda link: _priority_link_score(urlparse(link).path))
    return links


def extract_contacts_and_content(base_url, max_pages=MAX_SITE_PAGES):
    seed_pages = [
        normalize_url(base_url),
        normalize_url(urljoin(base_url, "/contact")),
        normalize_url(urljoin(base_url, "/contact-us")),
        normalize_url(urljoin(base_url, "/about")),
        normalize_url(urljoin(base_url, "/support"))
    ]

    queue = deque(seed_pages)
    seen = set()
    all_text = ""
    emails = set()
    phones = set()

    while queue and len(seen) < max_pages and len(all_text) < MAX_CONTENT_CHARS:
        p = queue.popleft()
        if not p or p in seen:
            continue

        seen.add(p)
        html = fetch_page(p)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text(separator=" ")

        all_text += " " + text[:3000]

        for e in re.findall(EMAIL_RE, text):
            if not e.lower().endswith((".png",".jpg",".jpeg",".gif")):
                emails.add(e.lower())

        for ph in re.findall(PHONE_RE, text):
            phones.add(ph.strip())

        for link in _extract_internal_links(base_url, html):
            if link not in seen and len(queue) < max_pages * 2:
                queue.append(link)

        # Fast path: stop crawling deeper once core contact details + enough content exist.
        if (emails or phones) and len(all_text) >= 2500:
            break

    return list(emails)[:1], list(phones)[:1], all_text[:MAX_CONTENT_CHARS]


def crawl_company_site(link):
    emails, phones, content = extract_contacts_and_content(link)
    return {
        "emails": emails,
        "phones": phones,
        "content": content,
    }


def google_search(
    query,
    max_results=10,
    start=0,
    exclude_domains=None,
    max_pages=1,
    business_only=True,
    country_filter="",
    trusted_only=False,
):
    """
    Cursor-based Google discovery.
    Uses parallel scrape -> extract -> AI enrichment stages.
    """
    companies = []
    seen = set(exclude_domains or [])
    current_start = max(0, int(start))
    pages_scanned = 0
    has_more = True

    structured = _get_structured_query(query)
    inferred_country = _extract_country_from_query(query)
    effective_country = _normalize_country(
        country_filter or structured.get("country") or inferred_country
    )
    search_q = _build_search_query(
        query,
        structured,
        business_only,
        country_filter=effective_country,
    )

    while pages_scanned < max_pages and has_more and len(companies) < max_results:
        results = _fetch_serp_result_page(search_q, current_start)
        organic_results = results.get("organic_results", [])
        pagination = results.get("serpapi_pagination", {})
        has_next = bool(isinstance(pagination, dict) and pagination.get("next"))

        if not organic_results and ENABLE_EMPTY_PAGE_FALLBACK:
            broad_q = f"{query} {_country_search_phrase(effective_country)}".strip()
            if broad_q and broad_q != search_q:
                fallback_results = _fetch_serp_result_page(broad_q, current_start)
                fallback_organic = fallback_results.get("organic_results", [])
                if fallback_organic:
                    results = fallback_results
                    organic_results = fallback_organic
                    pagination = results.get("serpapi_pagination", {})
                    has_next = bool(isinstance(pagination, dict) and pagination.get("next"))
                    search_q = broad_q

        if not organic_results:
            has_more = False
            break

        candidates = []
        for r in organic_results:
            link = r.get("link", "")
            title = r.get("title", "")
            snippet = r.get("snippet", "")

            if is_blocked_google_result(link, title, snippet):
                continue

            domain = clean_domain(link)
            if not domain or domain in seen:
                continue

            seen.add(domain)
            candidates.append(
                {
                    "title": title,
                    "snippet": snippet,
                    "link": link,
                    "domain": domain,
                }
            )

        crawled_payloads = []
        if candidates:
            workers = min(MAX_CRAWL_WORKERS, len(candidates))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_to_candidate = {
                    pool.submit(crawl_company_site, c["link"]): c for c in candidates
                }
                for future in as_completed(future_to_candidate):
                    c = future_to_candidate[future]
                    try:
                        crawled_payloads.append((c, future.result()))
                    except Exception:
                        continue

        def _extract_candidate(candidate, crawled, relaxed=False, ignore_country=False):
            emails = crawled.get("emails", [])
            phones = crawled.get("phones", [])
            title = candidate["title"]
            snippet = candidate["snippet"]
            link = candidate["link"]
            domain = candidate["domain"]
            content = (crawled.get("content", "") or "").strip()
            if not content:
                content = f"{title}. {snippet}".strip()
            if not content:
                return None

            if _looks_like_junk(content, title=title, snippet=snippet):
                if not relaxed:
                    return None

            # Keep only leads where at least one direct contact is present.
            has_contact = bool(emails or phones)
            if not has_contact and not ALLOW_NO_CONTACT_RESULTS and not relaxed:
                return None

            country_match = (
                _country_match_score(
                    effective_country,
                    domain,
                    title,
                    snippet,
                    content[:1200],
                )
                if effective_country else 1.0
            )
            if effective_country and (not ignore_country) and COUNTRY_HARD_FILTER and country_match <= 0.0:
                return None

            local_summary = ai_summary_for_query(query, content)
            semantic_score = _clip01(semantic_similarity(query, local_summary or content[:2000]))
            keyword_score = _clip01(keyword_match_ratio(query, f"{title} {snippet} {local_summary}"))
            domain_authority = _clip01(_domain_authority(domain))
            final_score, contact_presence = _compute_final_score(
                keyword_score=keyword_score,
                semantic_score=semantic_score,
                domain_authority=domain_authority,
                has_contact=has_contact,
            )
            if not has_contact:
                final_score = round(max(0.0, final_score - NO_CONTACT_SCORE_PENALTY), 3)
            if effective_country and country_match <= 0.0:
                # Keep results flowing even when location signal is weak.
                final_score = round(max(0.0, final_score - COUNTRY_SOFT_PENALTY), 3)

            if trusted_only and domain_authority < TRUSTED_ONLY_MIN_AUTHORITY:
                return None
            min_required_score = MIN_FINAL_SCORE
            if effective_country:
                min_required_score = max(0.30, MIN_FINAL_SCORE - 0.08)
            if relaxed:
                min_required_score = min(min_required_score, RELAXED_MIN_FINAL_SCORE)
            if final_score < min_required_score:
                return None

            if business_only and is_consulting_or_non_business_result(
                query=query,
                title=title,
                snippet=snippet,
                summary=local_summary,
                content=content,
            ):
                return None

            return {
                "company": title,
                "website": link,
                "domain": domain,
                "snippet": snippet,
                "email": emails[0] if emails else "",
                "phone": phones[0] if phones else "",
                "content": content,
                "summary": local_summary,
                "products": [],
                "llm_relevant": None,
                "semantic_score": semantic_score,
                "keyword_score": keyword_score,
                "domain_authority": domain_authority,
                "contact_presence": contact_presence,
                "has_contact": has_contact,
                "final_score": final_score,
                "importance": _importance_label(final_score),
                "country_match": country_match,
                "company_recorder": _company_recorder_links(title),
            }

        extracted = []
        if crawled_payloads:
            workers = min(MAX_EXTRACT_WORKERS, len(crawled_payloads))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {
                    pool.submit(_extract_candidate, c, crawled): c
                    for c, crawled in crawled_payloads
                }
                for future in as_completed(future_map):
                    try:
                        item = future.result()
                    except Exception:
                        item = None
                    if item:
                        extracted.append(item)

        if not extracted and crawled_payloads and ENABLE_EMPTY_PAGE_FALLBACK:
            workers = min(MAX_EXTRACT_WORKERS, len(crawled_payloads))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {
                    pool.submit(_extract_candidate, c, crawled, True, True): c
                    for c, crawled in crawled_payloads
                }
                for future in as_completed(future_map):
                    try:
                        item = future.result()
                    except Exception:
                        item = None
                    if item:
                        extracted.append(item)

        extracted.sort(key=lambda x: x.get("final_score", 0), reverse=True)

        if llm_enabled() and extracted:
            enrich_targets = extracted[:MAX_AI_ENRICHMENT_CANDIDATES]
            workers = min(MAX_AI_WORKERS, len(enrich_targets))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                future_map = {
                    pool.submit(
                        _analyze_with_llm_cached,
                        query,
                        item.get("content", ""),
                        item.get("company", ""),
                        item.get("snippet", ""),
                    ): item
                    for item in enrich_targets
                }
                for future in as_completed(future_map):
                    item = future_map[future]
                    try:
                        llm_result = future.result()
                    except Exception:
                        llm_result = {}

                    llm_relevant = llm_result.get("relevant")
                    if llm_relevant is False:
                        item["_drop"] = True
                        continue

                    llm_summary = llm_result.get("summary", "")
                    llm_products = llm_result.get("products", [])
                    if llm_summary:
                        item["summary"] = llm_summary
                    item["products"] = llm_products if isinstance(llm_products, list) else []
                    item["llm_relevant"] = llm_relevant

        for item in extracted:
            if item.get("_drop"):
                continue
            item.pop("_drop", None)
            if business_only and is_consulting_or_non_business_result(
                query=query,
                title=item.get("company", ""),
                snippet=item.get("snippet", ""),
                summary=item.get("summary", ""),
                content=item.get("content", ""),
            ):
                continue

            companies.append(item)
            if len(companies) >= max_results:
                break

        pages_scanned += 1
        current_start += SERP_PAGE_SIZE
        has_more = has_next

    companies.sort(key=lambda x: x.get("final_score", 0), reverse=True)
    companies = companies[:max_results]

    return {
        "companies": companies,
        "next_start": current_start,
        "has_more": has_more,
        "pages_scanned": pages_scanned,
        "effective_country": effective_country,
        "search_query": search_q,
    }


def linkedin_discovery(query, country_filter=""):
    effective_country = _normalize_country(country_filter) or _extract_country_from_query(query)
    country_phrase = _country_search_phrase(effective_country)
    if country_phrase:
        search_q = f"{query} {country_phrase} site:linkedin.com/in"
    else:
        search_q = f"{query} site:linkedin.com/in"
    results = _fetch_serp_result_page(search_q, 0)

    people = []

    for r in results.get("organic_results", []):
        title = r.get("title", "")
        snippet = r.get("snippet", "")
        link = r.get("link")
        country_match = (
            _country_match_score(
                effective_country,
                clean_domain(link),
                title,
                snippet,
            )
            if effective_country else 1.0
        )
        if effective_country and COUNTRY_HARD_FILTER and country_match <= 0.0:
            continue

        if is_consulting_or_non_business_result(
            query=query,
            title=title,
            snippet=snippet,
            summary="",
            content="",
        ):
            continue

        people.append({
            "name": title,
            "profile": link,
            "snippet": snippet,
            "country_filter": effective_country,
            "country_match": country_match,
        })

    return people


def smart_google_search(queries):

    all_companies = []
    all_people = []

    for q in queries:
        try:
            result = google_search(q)
            all_companies.extend(result.get("companies", []))
            all_people.extend(linkedin_discovery(q))
        except Exception as e:
            print("Search error:", e)

    return all_companies, all_people


def local_business_search(query):

    params = {
        "engine": "google",
        "q": query,
        "api_key": SERP_API_KEY,
        "num": 10
    }

    results = _serp_search(params)

    businesses = []
    seen = set()

    # Local results (can be messy)
    for r in results.get("local_results", []):

        if not isinstance(r, dict):
            continue

        website = r.get("website", "")
        domain = clean_domain(website)

        if not domain or domain in seen:
            continue

        seen.add(domain)

        businesses.append({
            "company": r.get("title"),
            "website": website,
            "phone": r.get("phone", ""),
            "domain": domain
        })

    # Organic results (more reliable)
    for r in results.get("organic_results", []):

        if not isinstance(r, dict):
            continue

        link = r.get("link", "")
        domain = clean_domain(link)

        if not domain or domain in seen:
            continue

        seen.add(domain)

        businesses.append({
            "company": r.get("title"),
            "website": link,
            "phone": "",
            "domain": domain
        })

    return businesses
