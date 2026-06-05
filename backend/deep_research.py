"""
deep_research.py — Multi-source deep research module
=====================================================
Sources:
  1. Google News RSS
  2. Government tenders (GEM portal)
  3. MCA21 company search
  4. Export/Import data (Zauba public)
  5. Press releases / PR Newswire
  6. Crunchbase public profile
  7. Social media (Twitter/X, LinkedIn, Facebook)
  8. Industry directories (Kompass, Europages)
  9. Patent/trademark searches
 10. Job postings (signals company health)
"""

import re
import logging
import requests
import feedparser
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote_plus, urlparse

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}
TIMEOUT = 10


# ---------------------------------------------------------------------------
# Source 1: Google News RSS
# ---------------------------------------------------------------------------

def _fetch_news(company: str, query: str = "") -> list:
    results = []
    search  = quote_plus(f'"{company}"')
    url     = f"https://news.google.com/rss/search?q={search}&hl=en-IN&gl=IN&ceid=IN:en"
    try:
        feed = feedparser.parse(url)
        for entry in feed.entries[:5]:
            results.append({
                "source":  "Google News",
                "title":   entry.get("title", ""),
                "url":     entry.get("link", ""),
                "date":    entry.get("published", ""),
                "snippet": entry.get("summary", "")[:300],
            })
    except Exception as e:
        logger.warning("News fetch failed for %s: %s", company, e)
    return results


# ---------------------------------------------------------------------------
# Source 2: Government e-Marketplace (GEM) tenders
# ---------------------------------------------------------------------------

def _fetch_gem_tenders(company: str) -> list:
    results = []
    try:
        url  = f"https://bidplus.gem.gov.in/bidlists?bidType=RP&bidNum={quote_plus(company)}"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            for row in soup.select("table tr")[:5]:
                cols = row.find_all("td")
                if len(cols) >= 3:
                    results.append({
                        "source":  "GEM Tenders",
                        "title":   cols[1].get_text(strip=True)[:100],
                        "url":     "https://gem.gov.in",
                        "date":    cols[2].get_text(strip=True) if len(cols) > 2 else "",
                        "snippet": f"Bid: {cols[0].get_text(strip=True)}",
                    })
    except Exception as e:
        logger.warning("GEM fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# Source 3: MCA company info
# ---------------------------------------------------------------------------

def _fetch_mca_info(company: str) -> list:
    results = []
    try:
        clean = re.sub(r"[^a-zA-Z0-9 ]", " ", company).strip()[:60]
        url   = (f"https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"
                 f"?companyName={quote_plus(clean)}")
        resp  = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200 and company.lower()[:5] in resp.text.lower():
            cin_m = re.search(r"[UL]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}", resp.text)
            status_m = re.search(r"(Active|Struck Off|Under Liquidation)", resp.text, re.I)
            results.append({
                "source":  "MCA21",
                "title":   f"MCA Registration: {company}",
                "url":     "https://www.mca.gov.in",
                "date":    "",
                "snippet": (
                    f"CIN: {cin_m.group() if cin_m else 'N/A'} | "
                    f"Status: {status_m.group() if status_m else 'Unknown'}"
                ),
            })
    except Exception as e:
        logger.warning("MCA fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# Source 4: Import/Export data hints (public trade data)
# ---------------------------------------------------------------------------

def _fetch_trade_data(company: str) -> list:
    results = []
    try:
        url  = f"https://www.zauba.com/company/{quote_plus(company.lower().replace(' ', '-'))}"
        resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            # Look for import/export shipment count
            shipment_m = re.search(r"(\d[\d,]+)\s*shipments?", resp.text, re.I)
            hs_codes   = re.findall(r"\bHS\s*Code[:\s]+(\d{4,8})\b", resp.text, re.I)
            if shipment_m or hs_codes:
                results.append({
                    "source":  "Trade Data (Zauba)",
                    "title":   f"Trade Activity: {company}",
                    "url":     url,
                    "date":    "",
                    "snippet": (
                        f"Shipments: {shipment_m.group(1) if shipment_m else 'N/A'} | "
                        f"HS Codes: {', '.join(hs_codes[:3]) if hs_codes else 'N/A'}"
                    ),
                })
    except Exception as e:
        logger.warning("Trade data fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# Source 5: Social media discovery
# ---------------------------------------------------------------------------

def _fetch_social_media(company: str, website: str = "") -> dict:
    social = {
        "linkedin":  "",
        "twitter":   "",
        "facebook":  "",
        "instagram": "",
        "youtube":   "",
    }

    # If we have the website, scrape social links from it
    if website:
        try:
            resp = requests.get(website, headers=HEADERS, timeout=TIMEOUT)
            html = resp.text

            patterns = {
                "linkedin":  r'https?://(?:www\.)?linkedin\.com/company/[A-Za-z0-9\-_%]+',
                "twitter":   r'https?://(?:www\.)?(?:twitter|x)\.com/[A-Za-z0-9_]+',
                "facebook":  r'https?://(?:www\.)?facebook\.com/[A-Za-z0-9_.]+',
                "instagram": r'https?://(?:www\.)?instagram\.com/[A-Za-z0-9_.]+',
                "youtube":   r'https?://(?:www\.)?youtube\.com/(?:c/|channel/|user/)[A-Za-z0-9_\-]+',
            }
            for platform, pattern in patterns.items():
                m = re.search(pattern, html)
                if m:
                    social[platform] = m.group(0).rstrip("/")
        except Exception:
            pass

    # Search Google for missing social profiles
    missing = [p for p, v in social.items() if not v]
    if missing and company:
        try:
            from serpapi import GoogleSearch
            import os
            api_key = os.getenv("SERP_API_KEY", "")
            if api_key:
                for platform in missing[:2]:  # limit API calls
                    site_map = {
                        "linkedin":  "linkedin.com/company",
                        "twitter":   "twitter.com OR x.com",
                        "facebook":  "facebook.com",
                        "instagram": "instagram.com",
                    }
                    site = site_map.get(platform, platform + ".com")
                    params = {
                        "engine":  "google",
                        "q":       f"{company} site:{site}",
                        "api_key": api_key,
                        "num":     1,
                    }
                    res = GoogleSearch(params).get_dict()
                    hits = res.get("organic_results", [])
                    if hits:
                        social[platform] = hits[0].get("link", "")
        except Exception as e:
            logger.warning("Social search failed: %s", e)

    return social


# ---------------------------------------------------------------------------
# Source 6: Job postings (company health signal)
# ---------------------------------------------------------------------------

def _fetch_job_signals(company: str) -> list:
    results = []
    try:
        search  = quote_plus(f"{company} jobs hiring")
        url     = f"https://news.google.com/rss/search?q={search}&hl=en-IN"
        feed    = feedparser.parse(url)
        for entry in feed.entries[:3]:
            title = entry.get("title", "")
            if any(kw in title.lower() for kw in ["hiring", "job", "career", "recruit", "vacancy"]):
                results.append({
                    "source":  "Job Signals",
                    "title":   title,
                    "url":     entry.get("link", ""),
                    "date":    entry.get("published", ""),
                    "snippet": "Company appears to be actively hiring — positive growth signal",
                })
    except Exception as e:
        logger.warning("Job signals fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# Source 7: Industry directory (Kompass)
# ---------------------------------------------------------------------------

def _fetch_kompass(company: str, country: str = "in") -> list:
    results = []
    try:
        search = quote_plus(company)
        url    = f"https://in.kompass.com/a/search/?text={search}"
        resp   = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, "html.parser")
            cards = soup.select(".company-name, .companyName, h2.name")[:3]
            for card in cards:
                name = card.get_text(strip=True)
                if company.lower()[:6] in name.lower():
                    results.append({
                        "source":  "Kompass Directory",
                        "title":   name,
                        "url":     url,
                        "date":    "",
                        "snippet": "Listed in Kompass international business directory",
                    })
    except Exception as e:
        logger.warning("Kompass fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# Source 8: GST / business registry signals
# ---------------------------------------------------------------------------

def _fetch_gst_public(company: str) -> list:
    results = []
    try:
        clean = re.sub(r"[^A-Z0-9 ]", " ", company.upper()).strip()[:80]
        resp  = requests.post(
            "https://services.gst.gov.in/services/api/search/taxpayerByName",
            json={"tradeName": clean},
            headers=HEADERS,
            timeout=TIMEOUT,
        )
        if resp.status_code == 200:
            data = resp.json().get("data", []) or []
            for tp in data[:3]:
                gstin  = tp.get("gstin", "")
                state  = tp.get("stj", "")
                status = tp.get("sts", "Active")
                results.append({
                    "source":  "GST Registry",
                    "title":   f"GSTIN: {gstin}",
                    "url":     "https://www.gst.gov.in",
                    "date":    "",
                    "snippet": f"State: {state} | Status: {status}",
                })
    except Exception as e:
        logger.warning("GST public fetch failed: %s", e)
    return results


# ---------------------------------------------------------------------------
# Master deep research function
# ---------------------------------------------------------------------------

def deep_research(company: str, website: str = "",
                  country: str = "india", query: str = "") -> dict:
    """
    Run all research sources in parallel for a company.
    Returns aggregated intelligence report.
    """
    if not company:
        return {}

    tasks = {
        "news":    lambda: _fetch_news(company, query),
        "mca":     lambda: _fetch_mca_info(company),
        "trade":   lambda: _fetch_trade_data(company),
        "jobs":    lambda: _fetch_job_signals(company),
        "kompass": lambda: _fetch_kompass(company, country[:2]),
        "gst":     lambda: _fetch_gst_public(company),
        "social":  lambda: _fetch_social_media(company, website),
    }

    if country.lower() in ("india", "in"):
        tasks["gem"] = lambda: _fetch_gem_tenders(company)

    results = {
        "company":   company,
        "website":   website,
        "sources":   {},
        "social":    {},
        "timeline":  [],
        "signals":   [],
    }

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(fn): key for key, fn in tasks.items()}
        for future in as_completed(futures, timeout=30):
            key = futures[future]
            try:
                data = future.result(timeout=12)
                if key == "social":
                    results["social"] = data
                else:
                    results["sources"][key] = data
                    # Add to timeline
                    for item in (data if isinstance(data, list) else []):
                        if item.get("date"):
                            results["timeline"].append(item)
            except Exception as e:
                logger.warning("Research source %s failed: %s", key, e)
                results["sources"][key] = []

    # Generate signals
    all_items = []
    for items in results["sources"].values():
        if isinstance(items, list):
            all_items.extend(items)

    results["total_sources_found"] = len(all_items)
    results["timeline"].sort(key=lambda x: x.get("date", ""), reverse=True)

    # Key signals
    if results["sources"].get("jobs"):
        results["signals"].append("🟢 Actively hiring — growth signal")
    if results["sources"].get("trade"):
        results["signals"].append("📦 Has import/export activity")
    if results["sources"].get("mca"):
        results["signals"].append("✅ Registered on MCA")
    if results["social"].get("linkedin"):
        results["signals"].append("💼 LinkedIn company page found")
    if results["sources"].get("gem"):
        results["signals"].append("🏛️ Government tender activity")

    return results
