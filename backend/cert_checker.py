"""
cert_checker.py
===============
Checks four Indian government portals in parallel for each lead company and
returns a structured compliance_gaps dict.  Integrated into the enrichment
pipeline via check_company_compliance().

Portals checked
---------------
1. BIS  – bis.gov.in   licensee search  (CRS / IS licence)
2. GST  – gst.gov.in   taxpayer search  (active GSTIN)
3. DGFT – dgft.gov.in  IEC holder search
4. MCA  – mca.gov.in   company master   (incorporated / struck-off / active)

Return shape (per company)
--------------------------
{
    "bis":  {"checked": True,  "certified": False, "detail": "No BIS licence found"},
    "gst":  {"checked": True,  "registered": True, "gstin": "27AABCU9603R1ZX", "status": "Active"},
    "dgft": {"checked": True,  "iec_found": False, "detail": "No IEC found"},
    "mca":  {"checked": True,  "active": True,     "cin": "U72200MH2010PTC123456", "status": "Active"},
    "compliance_gaps": ["no_bis", "no_iec"],
    "compliance_score": 0.5,   # 0 = all gaps  1 = fully compliant (lower = better prospect)
    "checker_error":    "",
}

Gap codes
---------
no_bis          BIS licensee search returned nothing
no_gst          No active GSTIN found
no_iec          No IEC found on DGFT portal
mca_not_found   Company not found on MCA
mca_inactive    Company found but status is struck-off / under-liquidation
"""

import re
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared session (connection pool, retries via urllib3 built-in)
# ---------------------------------------------------------------------------
_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
})

_TIMEOUT = 15          # seconds per portal request
_PARALLEL_WORKERS = 4  # one per portal

# ---------------------------------------------------------------------------
# Name normalisation helpers
# ---------------------------------------------------------------------------

def _clean_name(name: str) -> str:
    """Strip legal suffixes and punctuation for fuzzy matching."""
    name = name.upper().strip()
    for suffix in [
        "PRIVATE LIMITED", "PVT LTD", "PVT. LTD.", "PVT. LTD",
        "LIMITED", "LTD.", "LTD", "LLP", "INC.", "INC",
        "CORPORATION", "CORP.", "CORP", "& CO.", "& CO",
        "INDIA", "(INDIA)",
    ]:
        name = name.replace(suffix, "")
    name = re.sub(r"[^A-Z0-9 ]", " ", name)
    return " ".join(name.split())


def _name_matches(candidate: str, target: str, threshold: int = 60) -> bool:
    """
    Simple token-overlap match – avoids heavy dependency (fuzzywuzzy/rapidfuzz).
    Returns True if ≥ threshold % of target tokens appear in candidate.
    """
    t_tokens = set(_clean_name(target).split())
    c_tokens = set(_clean_name(candidate).split())
    if not t_tokens:
        return False
    overlap = len(t_tokens & c_tokens) / len(t_tokens)
    return overlap >= (threshold / 100)


# ---------------------------------------------------------------------------
# 1. BIS checker
# ---------------------------------------------------------------------------

def check_bis(company_name: str) -> dict:
    """
    Searches the BIS public licensee database.
    Endpoint: POST https://www.bis.gov.in/index.php  (public search form)
    Falls back to scraping the search results page.
    """
    result = {
        "checked": False,
        "certified": False,
        "licences": [],
        "detail": "",
    }

    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result

    try:
        # BIS uses a GET-based search on their public portal
        url = "https://www.bis.gov.in/index.php"
        params = {
            "lang": "en",
            "c": "public_search",
            "type": "licensee",
            "search_string": clean[:60],
        }
        resp = _SESSION.get(url, params=params, timeout=_TIMEOUT)
        result["checked"] = True

        if resp.status_code != 200:
            result["detail"] = f"BIS portal returned HTTP {resp.status_code}"
            return result

        text = resp.text

        # Look for table rows containing licence data
        # BIS portal returns HTML tables; we scan for the company name
        if _name_matches(text, company_name, threshold=55):
            # Extract IS numbers mentioned near the company name
            is_numbers = re.findall(r"IS[\s:]*\d+(?:[:\-/]\d+)?", text, re.IGNORECASE)
            r_numbers  = re.findall(r"R[\-]\d{7,}", text)
            licences = list(set(is_numbers + r_numbers))[:10]

            result["certified"] = True
            result["licences"]  = licences
            result["detail"]    = f"BIS licence(s) found: {', '.join(licences) if licences else 'yes (number not parsed)'}"
        else:
            result["certified"] = False
            result["detail"]    = "No BIS licence found — prospective client"

    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"BIS check failed: {exc}"
        logger.warning("BIS check error for '%s': %s", company_name, exc)

    return result


# ---------------------------------------------------------------------------
# 2. GST checker
# ---------------------------------------------------------------------------

def check_gst(company_name: str) -> dict:
    """
    Searches the GST taxpayer database by trade name.
    Uses the public JSON API endpoint that powers the GST portal search.
    """
    result = {
        "checked": False,
        "registered": False,
        "gstin": "",
        "status": "",
        "detail": "",
    }

    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result

    # Primary: GST public search API
    try:
        url = "https://services.gst.gov.in/services/api/search/taxpayerByName"
        payload = {"tradeName": clean[:100]}
        resp = _SESSION.post(url, json=payload, timeout=_TIMEOUT)
        result["checked"] = True

        if resp.status_code == 200:
            data = resp.json()
            taxpayers = data.get("data", []) or []

            for tp in taxpayers:
                trade  = tp.get("tradeName", "") or tp.get("lgnm", "")
                legal  = tp.get("legalName", "") or tp.get("ctb", "")
                status = (tp.get("sts", "") or tp.get("rgdt", "")).upper()
                gstin  = tp.get("gstin", "")

                if _name_matches(trade, company_name) or _name_matches(legal, company_name):
                    result["registered"] = True
                    result["gstin"]      = gstin
                    result["status"]     = status or "Active"
                    result["detail"]     = f"GST registered (GSTIN: {gstin}, status: {result['status']})"
                    return result

            result["registered"] = False
            result["detail"]     = "No active GSTIN found — prospective client"
            return result

    except requests.RequestException as exc:
        logger.warning("GST API error for '%s': %s", company_name, exc)

    # Fallback: scrape the portal HTML search page
    try:
        url  = "https://www.gst.gov.in/taxpayerSearch/search"
        resp = _SESSION.get(url, params={"name": clean[:80]}, timeout=_TIMEOUT)
        result["checked"] = True

        if _name_matches(resp.text, company_name, threshold=60):
            gstins = re.findall(r"\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}", resp.text)
            result["registered"] = True
            result["gstin"]      = gstins[0] if gstins else ""
            result["status"]     = "Active"
            result["detail"]     = f"GST registered (GSTIN: {result['gstin']})"
        else:
            result["registered"] = False
            result["detail"]     = "No active GSTIN found — prospective client"

    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"GST check failed: {exc}"
        logger.warning("GST fallback error for '%s': %s", company_name, exc)

    return result


# ---------------------------------------------------------------------------
# 3. DGFT / IEC checker
# ---------------------------------------------------------------------------

def check_dgft(company_name: str) -> dict:
    """
    Searches the DGFT IEC (Import Export Code) public database.
    Uses the DGFT public search endpoint.
    """
    result = {
        "checked": False,
        "iec_found": False,
        "iec_number": "",
        "detail": "",
    }

    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result

    try:
        # DGFT public IEC search – POST JSON API
        url = "https://www.dgft.gov.in/CP/?opt=IEC-Profile&cat=IECXML&service=IECXML"
        payload = {"iecEntityName": clean[:80]}
        resp = _SESSION.post(url, json=payload, timeout=_TIMEOUT)
        result["checked"] = True

        if resp.status_code == 200:
            text = resp.text
            # IEC numbers are 10-digit numeric
            iec_numbers = re.findall(r"\b\d{10}\b", text)

            if iec_numbers and _name_matches(text, company_name, threshold=50):
                result["iec_found"]  = True
                result["iec_number"] = iec_numbers[0]
                result["detail"]     = f"IEC found: {iec_numbers[0]}"
            else:
                result["iec_found"] = False
                result["detail"]    = "No IEC found — cannot legally import/export — prospective client"
            return result

    except requests.RequestException as exc:
        logger.warning("DGFT API error for '%s': %s", company_name, exc)

    # Fallback: DGFT PT search page
    try:
        url  = "https://www.dgft.gov.in/PT/IECPublicSearch"
        resp = _SESSION.get(url, params={"name": clean[:80]}, timeout=_TIMEOUT)
        result["checked"] = True

        iec_numbers = re.findall(r"\b\d{10}\b", resp.text)
        if iec_numbers and _name_matches(resp.text, company_name, threshold=50):
            result["iec_found"]  = True
            result["iec_number"] = iec_numbers[0]
            result["detail"]     = f"IEC found: {iec_numbers[0]}"
        else:
            result["iec_found"] = False
            result["detail"]    = "No IEC found — prospective client"

    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"DGFT check failed: {exc}"
        logger.warning("DGFT fallback error for '%s': %s", company_name, exc)

    return result


# ---------------------------------------------------------------------------
# 4. MCA checker
# ---------------------------------------------------------------------------

def check_mca(company_name: str) -> dict:
    """
    Searches the MCA company master database.
    Uses the MCA21 public search endpoint.
    """
    result = {
        "checked": False,
        "active": False,
        "cin": "",
        "status": "",
        "detail": "",
    }

    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result

    try:
        url  = "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"
        resp = _SESSION.get(
            url,
            params={"companyName": clean[:80]},
            timeout=_TIMEOUT,
        )
        result["checked"] = True

        if resp.status_code == 200:
            text = resp.text

            # CIN pattern: U/L + 5 alpha + 4 digit year + state + PTC/OPC/LLC + 6 digits
            cin_matches = re.findall(
                r"[UL]\d{5}[A-Z]{2}\d{4}(?:PTC|OPC|LLC|FLC|NPL|PLC)\d{6}", text
            )

            # Active status keywords
            active_kw   = ["active", "incorporated"]
            inactive_kw = ["struck off", "under liquidation", "dissolved",
                           "under process of striking off", "dormant"]

            text_lower = text.lower()
            is_inactive = any(kw in text_lower for kw in inactive_kw)
            is_active   = any(kw in text_lower for kw in active_kw) and not is_inactive

            if cin_matches and _name_matches(text, company_name, threshold=50):
                result["cin"]    = cin_matches[0]
                result["active"] = is_active and not is_inactive

                if is_inactive:
                    result["status"] = "Struck off / Inactive"
                    result["detail"] = f"Company found but inactive (CIN: {cin_matches[0]}) — may need re-registration"
                else:
                    result["status"] = "Active"
                    result["detail"] = f"Active company found (CIN: {cin_matches[0]})"
            else:
                result["active"] = False
                result["status"] = "Not found"
                result["detail"] = "Not found on MCA — may be unregistered or use a different name"

    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"MCA check failed: {exc}"
        logger.warning("MCA check error for '%s': %s", company_name, exc)

    return result


# ---------------------------------------------------------------------------
# Master checker — runs all four in parallel
# ---------------------------------------------------------------------------

def check_company_compliance(company_name: str, website: str = "") -> dict:
    """
    Run BIS / GST / DGFT / MCA checks in parallel.
    Returns a compliance dict suitable for storing on the lead document.

    Usage:
        gaps = check_company_compliance("Ratan Electronics Pvt Ltd")
        lead_doc["compliance"] = gaps
    """
    if not company_name or not company_name.strip():
        return _empty_compliance("No company name provided")

    checkers = {
        "bis":  check_bis,
        "gst":  check_gst,
        "dgft": check_dgft,
        "mca":  check_mca,
    }

    results: dict = {}
    errors: list  = []

    with ThreadPoolExecutor(max_workers=_PARALLEL_WORKERS) as executor:
        futures = {
            executor.submit(fn, company_name): key
            for key, fn in checkers.items()
        }
        for future in as_completed(futures, timeout=30):
            key = futures[future]
            try:
                results[key] = future.result(timeout=20)
            except TimeoutError:
                results[key] = {"checked": False, "detail": "Timeout"}
                errors.append(f"{key}: timeout")
                logger.warning("Compliance check timeout for %s / %s", key, company_name)
            except Exception as exc:
                results[key] = {"checked": False, "detail": str(exc)}
                errors.append(f"{key}: {exc}")
                logger.warning("Compliance check error for %s / %s: %s", key, company_name, exc)

    # Ensure all keys exist even if a future crashed
    for key in checkers:
        results.setdefault(key, {"checked": False, "detail": "Did not run"})

    # Build gap list
    gaps: list = []

    if results["bis"].get("checked") and not results["bis"].get("certified"):
        gaps.append("no_bis")

    if results["gst"].get("checked") and not results["gst"].get("registered"):
        gaps.append("no_gst")

    if results["dgft"].get("checked") and not results["dgft"].get("iec_found"):
        gaps.append("no_iec")

    if results["mca"].get("checked"):
        if not results["mca"].get("active") and results["mca"].get("status") == "Not found":
            gaps.append("mca_not_found")
        elif results["mca"].get("status", "").lower() in ("struck off / inactive",):
            gaps.append("mca_inactive")

    # compliance_score: fraction of checks passed  (lower = more gaps = better prospect)
    checks_run    = sum(1 for r in results.values() if r.get("checked"))
    checks_passed = (
        (1 if results["bis"].get("certified")  else 0) +
        (1 if results["gst"].get("registered") else 0) +
        (1 if results["dgft"].get("iec_found") else 0) +
        (1 if results["mca"].get("active")     else 0)
    )
    compliance_score = round(checks_passed / max(checks_run, 1), 2)

    return {
        "bis":              results["bis"],
        "gst":              results["gst"],
        "dgft":             results["dgft"],
        "mca":              results["mca"],
        "compliance_gaps":  gaps,
        "compliance_score": compliance_score,
        "checker_error":    "; ".join(errors),
    }


def _empty_compliance(reason: str) -> dict:
    empty = {"checked": False, "detail": reason}
    return {
        "bis":              dict(empty),
        "gst":              dict(empty),
        "dgft":             dict(empty),
        "mca":              dict(empty),
        "compliance_gaps":  [],
        "compliance_score": 1.0,
        "checker_error":    reason,
    }


# ---------------------------------------------------------------------------
# Gap labels for display
# ---------------------------------------------------------------------------

GAP_LABELS = {
    "no_bis":        "No BIS licence",
    "no_gst":        "No GST registration",
    "no_iec":        "No Import/Export Code",
    "mca_not_found": "Not registered (MCA)",
    "mca_inactive":  "Company struck off",
}

def gap_display(gaps: list) -> str:
    """Human-readable comma-separated gap string for the UI."""
    return ", ".join(GAP_LABELS.get(g, g) for g in gaps) if gaps else "None"