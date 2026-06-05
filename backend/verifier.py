"""
verifier.py — Free verification module
=======================================
Email:   MX record check + SMTP ping
Website: HTTP status + SSL + redirect check  
Phone:   Format validation + country prefix check
"""

import re
import socket
import smtplib
import ssl
import logging
import requests
from urllib.parse import urlparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Email Verification
# ---------------------------------------------------------------------------

def _get_mx_record(domain: str) -> str:
    """Get MX record for domain using DNS lookup."""
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, 'MX')
        mx = sorted(answers, key=lambda r: r.preference)[0]
        return str(mx.exchange).rstrip('.')
    except Exception:
        pass
    # Fallback: try common MX patterns
    common_mx = {
        "gmail.com": "alt1.gmail-smtp-in.l.google.com",
        "yahoo.com": "mta5.am0.yahoodns.net",
        "outlook.com": "outlook-com.olc.protection.outlook.com",
        "hotmail.com": "outlook-com.olc.protection.outlook.com",
    }
    return common_mx.get(domain.lower(), "")


def _smtp_check(email: str, mx_host: str) -> dict:
    """Try SMTP connection to verify email exists."""
    try:
        with smtplib.SMTP(timeout=10) as smtp:
            smtp.connect(mx_host, 25)
            smtp.helo("verify.buyera.ai")
            smtp.mail("verify@buyera.ai")
            code, _ = smtp.rcpt(email)
            return {"deliverable": code == 250, "smtp_code": code}
    except smtplib.SMTPRecipientsRefused:
        return {"deliverable": False, "smtp_code": 550}
    except Exception as e:
        return {"deliverable": None, "smtp_code": None, "error": str(e)}


def verify_email(email: str) -> dict:
    """
    Verify email address.
    Returns:
        valid_format, mx_found, deliverable, score (0-100), verdict
    """
    result = {
        "email":       email,
        "valid_format": False,
        "mx_found":    False,
        "deliverable": None,
        "is_free":     False,
        "is_disposable": False,
        "score":       0,
        "verdict":     "unknown",
    }

    if not email or "@" not in email:
        result["verdict"] = "invalid"
        return result

    EMAIL_RE = re.compile(
        r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$'
    )
    if not EMAIL_RE.match(email):
        result["verdict"] = "invalid_format"
        return result

    result["valid_format"] = True
    domain = email.split("@")[1].lower()

    FREE_PROVIDERS = {
        "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
        "rediffmail.com", "ymail.com", "live.com", "icloud.com",
        "protonmail.com", "zoho.com",
    }
    DISPOSABLE = {
        "mailinator.com", "guerrillamail.com", "tempmail.com",
        "throwaway.email", "fakeinbox.com", "sharklasers.com",
    }

    result["is_free"]       = domain in FREE_PROVIDERS
    result["is_disposable"] = domain in DISPOSABLE

    if result["is_disposable"]:
        result["verdict"] = "disposable"
        result["score"]   = 5
        return result

    # MX record check
    mx_host = _get_mx_record(domain)
    if mx_host:
        result["mx_found"] = True
        # SMTP check (skip for free providers — they always accept)
        if not result["is_free"]:
            smtp_result = _smtp_check(email, mx_host)
            result["deliverable"] = smtp_result.get("deliverable")

    # Score calculation
    score = 0
    if result["valid_format"]:  score += 30
    if result["mx_found"]:      score += 40
    if result["deliverable"] is True:   score += 30
    elif result["deliverable"] is None: score += 15  # unknown but MX found
    if result["is_free"]:       score = min(score, 70)  # cap free emails

    result["score"]   = score
    result["verdict"] = (
        "valid"    if score >= 70 else
        "risky"    if score >= 40 else
        "invalid"
    )
    return result


# ---------------------------------------------------------------------------
# Website Verification
# ---------------------------------------------------------------------------

def verify_website(url: str) -> dict:
    """
    Verify website is live, check SSL, redirects, response time.
    """
    result = {
        "url":           url,
        "is_live":       False,
        "status_code":   None,
        "has_ssl":       False,
        "redirects_to":  "",
        "response_ms":   None,
        "domain_age":    "",
        "title":         "",
        "score":         0,
        "verdict":       "unknown",
    }

    if not url:
        return result

    if not url.startswith("http"):
        url = "https://" + url

    try:
        start = datetime.utcnow()
        resp  = requests.get(
            url, timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
            allow_redirects=True,
        )
        ms = int((datetime.utcnow() - start).total_seconds() * 1000)

        result["status_code"] = resp.status_code
        result["response_ms"] = ms
        result["is_live"]     = resp.status_code < 400
        result["has_ssl"]     = resp.url.startswith("https://")
        result["redirects_to"] = resp.url if resp.url != url else ""

        # Extract title
        title_match = re.search(r"<title[^>]*>([^<]+)</title>", resp.text, re.I)
        if title_match:
            result["title"] = title_match.group(1).strip()[:100]

    except requests.exceptions.SSLError:
        result["has_ssl"]  = False
        result["verdict"]  = "ssl_error"
    except requests.exceptions.ConnectionError:
        result["verdict"]  = "unreachable"
        return result
    except requests.exceptions.Timeout:
        result["verdict"]  = "timeout"
        return result
    except Exception as e:
        result["verdict"]  = f"error: {e}"
        return result

    # Check WHOIS for domain age (best-effort)
    try:
        domain = urlparse(url).netloc.replace("www.", "")
        whois_resp = requests.get(
            f"https://api.whois.vu/?q={domain}", timeout=5
        )
        if whois_resp.status_code == 200:
            data = whois_resp.json()
            created = data.get("registered", "")
            if created:
                result["domain_age"] = created[:10]
    except Exception:
        pass

    # Score
    score = 0
    if result["is_live"]:       score += 50
    if result["has_ssl"]:       score += 25
    if result["domain_age"]:    score += 15
    if result["response_ms"] and result["response_ms"] < 2000: score += 10

    result["score"]   = score
    result["verdict"] = (
        "verified"   if score >= 70 else
        "partial"    if score >= 40 else
        "unverified"
    )
    return result


# ---------------------------------------------------------------------------
# Phone Verification
# ---------------------------------------------------------------------------

PHONE_PATTERNS = {
    "India":     re.compile(r"^\+?91?\s*[6-9]\d{9}$"),
    "UAE":       re.compile(r"^\+?971\s*[0-9]{8,9}$"),
    "USA":       re.compile(r"^\+?1?\s*[2-9]\d{9}$"),
    "UK":        re.compile(r"^\+?44\s*[1-9]\d{9,10}$"),
    "Singapore": re.compile(r"^\+?65\s*[689]\d{7}$"),
}

COUNTRY_PREFIXES = {
    "+91": "India", "+971": "UAE", "+1": "USA/Canada",
    "+44": "UK", "+65": "Singapore", "+61": "Australia",
    "+49": "Germany", "+33": "France", "+39": "Italy",
    "+81": "Japan", "+86": "China",
}


def verify_phone(phone: str) -> dict:
    """Validate phone number format and detect country."""
    result = {
        "phone":        phone,
        "cleaned":      "",
        "valid_format": False,
        "country":      "",
        "is_mobile":    None,
        "score":        0,
        "verdict":      "unknown",
    }

    if not phone:
        return result

    # Clean phone number
    cleaned = re.sub(r"[\s\-\(\)\.ext]", "", phone)
    if not cleaned.startswith("+"):
        # Try to detect prefix
        if cleaned.startswith("91") and len(cleaned) == 12:
            cleaned = "+" + cleaned
        elif cleaned.startswith("0"):
            cleaned = cleaned[1:]

    result["cleaned"] = cleaned

    # Detect country from prefix
    for prefix, country in COUNTRY_PREFIXES.items():
        if cleaned.startswith(prefix):
            result["country"] = country
            break

    # Validate format
    digits_only = re.sub(r"\D", "", cleaned)
    if 7 <= len(digits_only) <= 15:
        result["valid_format"] = True

    # Check against country patterns
    for country, pattern in PHONE_PATTERNS.items():
        if pattern.match(cleaned):
            result["country"]   = country
            result["is_mobile"] = True
            break

    score = 0
    if result["valid_format"]: score += 50
    if result["country"]:      score += 30
    if result["is_mobile"]:    score += 20

    result["score"]   = score
    result["verdict"] = "valid" if score >= 50 else "invalid"
    return result


# ---------------------------------------------------------------------------
# Batch verifier
# ---------------------------------------------------------------------------

def verify_lead(lead: dict) -> dict:
    """Run all verifications for a lead in parallel."""
    results = {}

    with ThreadPoolExecutor(max_workers=3) as ex:
        futures = {}
        if lead.get("email"):
            futures["email"]   = ex.submit(verify_email,   lead["email"])
        if lead.get("website"):
            futures["website"] = ex.submit(verify_website, lead["website"])
        if lead.get("phone"):
            futures["phone"]   = ex.submit(verify_phone,   lead["phone"])

        for key, future in futures.items():
            try:
                results[key] = future.result(timeout=15)
            except Exception as e:
                results[key] = {"error": str(e), "verdict": "error"}

    return results
