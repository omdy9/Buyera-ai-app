"""
cert_checker.py  (v2)
=====================
Checks four Indian government portals in parallel.
New in v2: MCA check now extracts incorporation_date and company_type.

Portals checked
---------------
1. BIS  – bis.gov.in
2. GST  – gst.gov.in
3. DGFT – dgft.gov.in (IEC)
4. MCA  – mca.gov.in  (now also returns incorporation_date, company_type)

Return shape
------------
{
    "bis":  {"checked": True, "certified": False, ...},
    "gst":  {"checked": True, "registered": True, "gstin": "...", ...},
    "dgft": {"checked": True, "iec_found": False, ...},
    "mca":  {"checked": True, "active": True, "cin": "...",
             "incorporation_date": "2010", "company_type": "Private Limited", ...},
    "compliance_gaps":  ["no_bis"],
    "compliance_score": 0.75,
    "checker_error":    "",
}
"""

import re
import time
import logging
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
})

_TIMEOUT          = 15
_PARALLEL_WORKERS = 4

# ---------------------------------------------------------------------------
# Name normalisation
# ---------------------------------------------------------------------------

def _clean_name(name: str) -> str:
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
    t_tokens = set(_clean_name(target).split())
    c_tokens = set(_clean_name(candidate).split())
    if not t_tokens:
        return False
    overlap = len(t_tokens & c_tokens) / len(t_tokens)
    return overlap >= (threshold / 100)


# ---------------------------------------------------------------------------
# 1. BIS checker (unchanged)
# ---------------------------------------------------------------------------

def check_bis(company_name: str) -> dict:
    result = {"checked": False, "certified": False, "licences": [], "detail": ""}
    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result
    try:
        url = "https://www.bis.gov.in/index.php"
        params = {
            "lang": "en", "c": "public_search",
            "type": "licensee", "search_string": clean[:60],
        }
        resp = _SESSION.get(url, params=params, timeout=_TIMEOUT)
        result["checked"] = True
        if resp.status_code != 200:
            result["detail"] = f"BIS portal returned HTTP {resp.status_code}"
            return result
        text = resp.text
        if _name_matches(text, company_name, threshold=55):
            is_numbers = re.findall(r"IS[\s:]*\d+(?:[:\-/]\d+)?", text, re.IGNORECASE)
            r_numbers  = re.findall(r"R[\-]\d{7,}", text)
            licences   = list(set(is_numbers + r_numbers))[:10]
            result["certified"] = True
            result["licences"]  = licences
            result["detail"]    = f"BIS licence(s) found: {', '.join(licences) if licences else 'yes'}"
        else:
            result["certified"] = False
            result["detail"]    = "No BIS licence found — prospective client"
    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"BIS check failed: {exc}"
        logger.warning("BIS check error for '%s': %s", company_name, exc)
    return result


# ---------------------------------------------------------------------------
# 2. GST checker (unchanged)
# ---------------------------------------------------------------------------

def check_gst(company_name: str) -> dict:
    result = {"checked": False, "registered": False, "gstin": "", "status": "", "detail": ""}
    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result
    try:
        url     = "https://services.gst.gov.in/services/api/search/taxpayerByName"
        payload = {"tradeName": clean[:100]}
        resp    = _SESSION.post(url, json=payload, timeout=_TIMEOUT)
        result["checked"] = True
        if resp.status_code == 200:
            data      = resp.json()
            taxpayers = data.get("data", []) or []
            for tp in taxpayers:
                trade  = tp.get("tradeName", "") or tp.get("lgnm", "")
                legal  = tp.get("legalName", "") or tp.get("ctb", "")
                status = (tp.get("sts", "") or tp.get("rgdt", "")).upper()
                gstin  = tp.get("gstin", "")
                if _name_matches(trade, company_name) or _name_matches(legal, company_name):
                    result.update({
                        "registered": True, "gstin": gstin,
                        "status": status or "Active",
                        "detail": f"GST registered (GSTIN: {gstin}, status: {status or 'Active'})",
                    })
                    return result
            result["registered"] = False
            result["detail"]     = "No active GSTIN found — prospective client"
            return result
    except requests.RequestException as exc:
        logger.warning("GST API error for '%s': %s", company_name, exc)

    try:
        url  = "https://www.gst.gov.in/taxpayerSearch/search"
        resp = _SESSION.get(url, params={"name": clean[:80]}, timeout=_TIMEOUT)
        result["checked"] = True
        if _name_matches(resp.text, company_name, threshold=60):
            gstins = re.findall(r"\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}[Z]{1}[A-Z\d]{1}", resp.text)
            result.update({
                "registered": True,
                "gstin":      gstins[0] if gstins else "",
                "status":     "Active",
                "detail":     f"GST registered (GSTIN: {gstins[0] if gstins else ''})",
            })
        else:
            result["registered"] = False
            result["detail"]     = "No active GSTIN found — prospective client"
    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"GST check failed: {exc}"
        logger.warning("GST fallback error for '%s': %s", company_name, exc)
    return result


# ---------------------------------------------------------------------------
# 3. DGFT / IEC checker (unchanged)
# ---------------------------------------------------------------------------

def check_dgft(company_name: str) -> dict:
    result = {"checked": False, "iec_found": False, "iec_number": "", "detail": ""}
    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result
    try:
        url     = "https://www.dgft.gov.in/CP/?opt=IEC-Profile&cat=IECXML&service=IECXML"
        payload = {"iecEntityName": clean[:80]}
        resp    = _SESSION.post(url, json=payload, timeout=_TIMEOUT)
        result["checked"] = True
        if resp.status_code == 200:
            text        = resp.text
            iec_numbers = re.findall(r"\b\d{10}\b", text)
            if iec_numbers and _name_matches(text, company_name, threshold=50):
                result.update({
                    "iec_found":  True,
                    "iec_number": iec_numbers[0],
                    "detail":     f"IEC found: {iec_numbers[0]}",
                })
            else:
                result["iec_found"] = False
                result["detail"]    = "No IEC found — cannot legally import/export"
            return result
    except requests.RequestException as exc:
        logger.warning("DGFT API error for '%s': %s", company_name, exc)

    try:
        url  = "https://www.dgft.gov.in/PT/IECPublicSearch"
        resp = _SESSION.get(url, params={"name": clean[:80]}, timeout=_TIMEOUT)
        result["checked"] = True
        iec_numbers = re.findall(r"\b\d{10}\b", resp.text)
        if iec_numbers and _name_matches(resp.text, company_name, threshold=50):
            result.update({
                "iec_found":  True,
                "iec_number": iec_numbers[0],
                "detail":     f"IEC found: {iec_numbers[0]}",
            })
        else:
            result["iec_found"] = False
            result["detail"]    = "No IEC found — prospective client"
    except requests.RequestException as exc:
        result["checked"] = False
        result["detail"]  = f"DGFT check failed: {exc}"
        logger.warning("DGFT fallback error for '%s': %s", company_name, exc)
    return result


# ---------------------------------------------------------------------------
# 4. MCA checker — NOW extracts incorporation_date and company_type
# ---------------------------------------------------------------------------

# Company-type patterns found in MCA master data HTML
_MCA_TYPE_MAP = {
    "Private Limited": ["private limited", "pvt ltd", "pvt. ltd"],
    "Public Limited":  ["public limited"],
    "LLP":             ["limited liability partnership", "llp"],
    "OPC":             ["one person company", "opc"],
    "Section 8":       ["section 8", "npo", "not for profit"],
    "Foreign":         ["foreign company"],
}

_MCA_INCORP_RE = re.compile(
    r"(?:date\s+of\s+incorporation|incorporation\s+date|doi)[:\s]+(\d{2}[/-]\d{2}[/-]\d{4})",
    re.IGNORECASE,
)
_MCA_YEAR_RE = re.compile(
    r"[UL]\d{5}[A-Z]{2}(\d{4})[A-Z]{3}\d{6}",  # year embedded in CIN
)


def check_mca(company_name: str) -> dict:
    result = {
        "checked":            False,
        "active":             False,
        "cin":                "",
        "status":             "",
        "incorporation_date": "",
        "company_type":       "",
        "detail":             "",
    }
    clean = _clean_name(company_name)
    if not clean:
        result["detail"] = "Empty company name"
        return result

    try:
        url  = "https://www.mca.gov.in/mcafoportal/viewCompanyMasterData.do"
        resp = _SESSION.get(
            url, params={"companyName": clean[:80]}, timeout=_TIMEOUT,
        )
        result["checked"] = True

        if resp.status_code == 200:
            text = resp.text

            # CIN
            cin_matches = re.findall(
                r"[UL]\d{5}[A-Z]{2}\d{4}(?:PTC|OPC|LLC|FLC|NPL|PLC)\d{6}", text
            )

            active_kw   = ["active", "incorporated"]
            inactive_kw = ["struck off", "under liquidation", "dissolved",
                           "under process of striking off", "dormant"]
            text_lower  = text.lower()
            is_inactive = any(kw in text_lower for kw in inactive_kw)
            is_active   = any(kw in text_lower for kw in active_kw) and not is_inactive

            if cin_matches and _name_matches(text, company_name, threshold=50):
                cin = cin_matches[0]
                result["cin"]    = cin
                result["active"] = is_active

                # --- Extract incorporation date ---
                # Method 1: explicit "Date of Incorporation" field
                date_m = _MCA_INCORP_RE.search(text)
                if date_m:
                    result["incorporation_date"] = date_m.group(1)
                else:
                    # Method 2: year from CIN (positions 8–11)
                    year_m = _MCA_YEAR_RE.search(cin)
                    if year_m:
                        result["incorporation_date"] = year_m.group(1)

                # --- Extract company type ---
                for ctype, signals in _MCA_TYPE_MAP.items():
                    if any(s in text_lower for s in signals):
                        result["company_type"] = ctype
                        break

                if is_inactive:
                    result["status"] = "Struck off / Inactive"
                    result["detail"] = f"Inactive (CIN: {cin}) — may need re-registration"
                else:
                    result["status"] = "Active"
                    result["detail"] = (
                        f"Active (CIN: {cin}"
                        + (f", incorporated {result['incorporation_date']}" if result["incorporation_date"] else "")
                        + (f", {result['company_type']}" if result["company_type"] else "")
                        + ")"
                    )
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
# Master checker
# ---------------------------------------------------------------------------

def check_company_compliance(company_name: str, website: str = "") -> dict:
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
            except Exception as exc:
                results[key] = {"checked": False, "detail": str(exc)}
                errors.append(f"{key}: {exc}")

    for key in checkers:
        results.setdefault(key, {"checked": False, "detail": "Did not run"})

    gaps: list = []
    if results["bis"].get("checked")  and not results["bis"].get("certified"):
        gaps.append("no_bis")
    if results["gst"].get("checked")  and not results["gst"].get("registered"):
        gaps.append("no_gst")
    if results["dgft"].get("checked") and not results["dgft"].get("iec_found"):
        gaps.append("no_iec")
    if results["mca"].get("checked"):
        if not results["mca"].get("active") and results["mca"].get("status") == "Not found":
            gaps.append("mca_not_found")
        elif "struck off" in results["mca"].get("status", "").lower():
            gaps.append("mca_inactive")

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


GAP_LABELS = {
    "no_bis":        "No BIS licence",
    "no_gst":        "No GST registration",
    "no_iec":        "No Import/Export Code",
    "mca_not_found": "Not registered (MCA)",
    "mca_inactive":  "Company struck off",
}


def gap_display(gaps: list) -> str:
    return ", ".join(GAP_LABELS.get(g, g) for g in gaps) if gaps else "None"
