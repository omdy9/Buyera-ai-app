"""
llm.py  — v3  (Specialised multi-model pipeline)
=================================================
Each LLM has a dedicated job:

  DeepSeek  → Contact finder  (searches web for person, email, phone, LinkedIn)
  Grok      → Lead validator   (decides if company is a genuine prospect)
  OpenRouter→ Fallback summariser if others unavailable

Pipeline per company:
  1. DeepSeek: find contact person + details
  2. Grok:     validate lead relevance + score
  3. Combine results into final enriched profile
"""

import os
import re
import json
import time
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider config
# ---------------------------------------------------------------------------
_PROVIDERS = {
    "deepseek": {
        "url":     "https://api.deepseek.com/v1/chat/completions",
        "key_env": "DEEPSEEK_API_KEY",
        "model":   os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
    },
    "grok": {
        "url":     "https://api.x.ai/v1/chat/completions",
        "key_env": "GROK_API_KEY",
        "model":   os.getenv("GROK_MODEL", "grok-3-mini"),
    },
    "openrouter": {
        "url":     "https://openrouter.ai/api/v1/chat/completions",
        "key_env": "OPENROUTER_API_KEY",
        "model":   os.getenv("LLM_MODEL", "mistralai/mistral-7b-instruct"),
    },
}


def _get_provider(name: str = None) -> dict | None:
    """Get a specific provider or best available."""
    if name:
        cfg = _PROVIDERS.get(name)
        if cfg and os.getenv(cfg["key_env"], "").strip():
            return cfg
        return None
    # Auto-select best available
    for n in ["deepseek", "grok", "openrouter"]:
        cfg = _PROVIDERS[n]
        if os.getenv(cfg["key_env"], "").strip():
            return cfg
    return None


def _call_llm(messages: list, provider_name: str = None,
              max_tokens: int = 800, temperature: float = 0.1,
              retries: int = 2) -> str:
    cfg = _get_provider(provider_name) or _get_provider()
    if not cfg:
        raise RuntimeError("No LLM API key configured")

    api_key = os.getenv(cfg["key_env"], "").strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }
    if "openrouter" in cfg["url"]:
        headers["HTTP-Referer"] = "https://buyera.ai"
        headers["X-Title"]      = "Buyera AI Lead Discovery"

    payload = {
        "model":       cfg["model"],
        "messages":    messages,
        "max_tokens":  max_tokens,
        "temperature": temperature,
    }

    last_exc = None
    for attempt in range(retries):
        try:
            resp = requests.post(cfg["url"], headers=headers,
                                 json=payload, timeout=30)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as exc:
            last_exc = exc
            logger.warning("LLM %s attempt %d/%d failed: %s",
                           provider_name or "auto", attempt + 1, retries, exc)
            if attempt < retries - 1:
                time.sleep(1.5)
    raise RuntimeError(f"LLM call failed: {last_exc}")


def _extract_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(clean)


# ---------------------------------------------------------------------------
# JOB 1 — DeepSeek: Contact Finder
# ---------------------------------------------------------------------------

_CONTACT_PROMPT = """\
You are a B2B contact research specialist. Your job is to find the best \
person to contact at this company.

Company Name: {company}
Website: {website}
Website Content:
{content}

Search through the content carefully for:
- Owner / Founder / Director / CEO / MD / Partner name
- Their direct email address
- Their phone number or mobile number
- Their LinkedIn profile URL
- Their designation / job title

Return ONLY valid JSON, no explanation:
{{
  "contact_person":  "Full name of best contact person",
  "contact_title":   "Their job title (CEO, Director, Owner etc)",
  "contact_email":   "Their direct email if found",
  "contact_phone":   "Their direct phone/mobile if found",
  "contact_linkedin":"Their personal LinkedIn URL if found",
  "confidence":      "high / medium / low  (how confident are you this is the right person)",
  "source":          "Where you found this info (About page, Contact page etc)"
}}
"""


def find_contact_person(company: str, website: str, content: str) -> dict:
    """
    DeepSeek specialised job: find the best contact person at a company.
    """
    fallback = {
        "contact_person":   "",
        "contact_title":    "",
        "contact_email":    "",
        "contact_phone":    "",
        "contact_linkedin": "",
        "confidence":       "low",
        "source":           "",
    }

    if not _get_provider("deepseek"):
        logger.info("DeepSeek not available for contact finding")
        return fallback

    if not content or len(content.strip()) < 50:
        return fallback

    prompt = _CONTACT_PROMPT.format(
        company=company[:100],
        website=website[:100],
        content=content[:5000],
    )

    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           provider_name="deepseek",
                           max_tokens=400, temperature=0.1)
        result = _extract_json(text)
        logger.info("DeepSeek found contact for %s: %s (confidence: %s)",
                    company, result.get("contact_person","—"),
                    result.get("confidence","?"))
        return {
            "contact_person":   str(result.get("contact_person",   "") or ""),
            "contact_title":    str(result.get("contact_title",    "") or ""),
            "contact_email":    str(result.get("contact_email",    "") or ""),
            "contact_phone":    str(result.get("contact_phone",    "") or ""),
            "contact_linkedin": str(result.get("contact_linkedin", "") or ""),
            "confidence":       str(result.get("confidence",       "low") or "low"),
            "source":           str(result.get("source",           "") or ""),
        }
    except Exception as exc:
        logger.warning("DeepSeek contact find failed for %s: %s", company, exc)
        return fallback


# ---------------------------------------------------------------------------
# JOB 2 — Grok: Lead Validator + Full Analyser
# ---------------------------------------------------------------------------

_VALIDATE_PROMPT = """\
You are a sharp B2B sales analyst. Validate whether this company is a genuine \
sales prospect for the given search query, and extract a full business profile.

Search Query: {query}
Company: {company}
Website: {website}

Website Content:
{content}

Be critical. Return ONLY valid JSON:
{{
  "is_valid_lead":      true or false,
  "rejection_reason":   "Why this is NOT a good lead (empty if valid)",
  "relevance_score":    1-10,
  "summary":            "2-3 sentences: what they do, who buys from them, why they matter",
  "usp":                "Their unique selling point in one sentence",
  "products":           ["specific products or services they offer"],
  "product_type":       "Primary product category (be specific)",
  "industry":           "Industry sector",
  "channel_type":       "Manufacturer / Importer / Trader / Wholesaler / Distributor / Retailer",
  "company_size":       "Employee count or range if found",
  "annual_turnover":    "Revenue/turnover if mentioned",
  "city":               "Headquarters city",
  "country":            "Headquarters country",
  "incorporation_date": "Year founded/incorporated",
  "certifications":     ["ISO 9001", "BIS", "CE" etc if mentioned],
  "export_markets":     ["countries/regions they export to"],
  "key_customers":      ["notable clients or customer types"],
  "is_directory":       true or false (is this a business directory listing multiple companies?)
}}
"""


def validate_and_analyse(query: str, company: str, website: str,
                         content: str) -> dict:
    """
    Grok specialised job: validate lead quality + extract full business profile.
    """
    fallback = {
        "is_valid_lead": True, "rejection_reason": "",
        "relevance_score": 5, "summary": "", "usp": "",
        "products": [], "product_type": "", "industry": "",
        "channel_type": "", "company_size": "", "annual_turnover": "",
        "city": "", "country": "", "incorporation_date": "",
        "certifications": [], "export_markets": [], "key_customers": [],
        "is_directory": False,
    }

    if not _get_provider("grok"):
        logger.info("Grok not available, using fallback analyser")
        return _fallback_analyse(query, company, website, content, fallback)

    if not content or len(content.strip()) < 50:
        return fallback

    prompt = _VALIDATE_PROMPT.format(
        query=query[:200],
        company=company[:100],
        website=website[:100],
        content=content[:7000],
    )

    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           provider_name="grok",
                           max_tokens=900, temperature=0.1)
        result = _extract_json(text)

        valid_channels = {"Manufacturer","Importer","Trader",
                          "Wholesaler","Distributor","Retailer",""}
        channel = str(result.get("channel_type","") or "").strip().title()
        if channel not in valid_channels:
            channel = ""

        logger.info("Grok validated %s: valid=%s score=%s is_directory=%s",
                    company, result.get("is_valid_lead"),
                    result.get("relevance_score"),
                    result.get("is_directory"))

        return {
            "is_valid_lead":      bool(result.get("is_valid_lead", True)),
            "rejection_reason":   str(result.get("rejection_reason", "") or ""),
            "relevance_score":    max(0, min(int(result.get("relevance_score", 5) or 5), 10)),
            "summary":            str(result.get("summary", "") or ""),
            "usp":                str(result.get("usp", "") or ""),
            "products":           result.get("products", []) if isinstance(result.get("products"), list) else [],
            "product_type":       str(result.get("product_type", "") or ""),
            "industry":           str(result.get("industry", "") or ""),
            "channel_type":       channel,
            "company_size":       str(result.get("company_size", "") or ""),
            "annual_turnover":    str(result.get("annual_turnover", "") or ""),
            "city":               str(result.get("city", "") or ""),
            "country":            str(result.get("country", "") or ""),
            "incorporation_date": str(result.get("incorporation_date", "") or ""),
            "certifications":     result.get("certifications", []) if isinstance(result.get("certifications"), list) else [],
            "export_markets":     result.get("export_markets", []) if isinstance(result.get("export_markets"), list) else [],
            "key_customers":      result.get("key_customers", []) if isinstance(result.get("key_customers"), list) else [],
            "is_directory":       bool(result.get("is_directory", False)),
        }
    except Exception as exc:
        logger.warning("Grok validation failed for %s: %s", company, exc)
        return _fallback_analyse(query, company, website, content, fallback)


def _fallback_analyse(query: str, company: str, website: str,
                      content: str, fallback: dict) -> dict:
    """Use OpenRouter or any available provider as fallback analyser."""
    if not _get_provider():
        return fallback

    prompt = _VALIDATE_PROMPT.format(
        query=query[:200],
        company=company[:100],
        website=website[:100],
        content=content[:5000],
    )
    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           max_tokens=900, temperature=0.1)
        result = _extract_json(text)
        fallback.update({
            "is_valid_lead":   bool(result.get("is_valid_lead", True)),
            "relevance_score": max(0, min(int(result.get("relevance_score", 5) or 5), 10)),
            "summary":         str(result.get("summary", "") or ""),
            "products":        result.get("products", []) if isinstance(result.get("products"), list) else [],
            "industry":        str(result.get("industry", "") or ""),
            "channel_type":    str(result.get("channel_type", "") or ""),
            "is_directory":    bool(result.get("is_directory", False)),
        })
    except Exception as exc:
        logger.warning("Fallback analysis failed for %s: %s", company, exc)
    return fallback


# ---------------------------------------------------------------------------
# Directory extractor — used when Grok flags is_directory=True
# ---------------------------------------------------------------------------

_DIRECTORY_PROMPT = """\
This webpage is a business directory. Extract ALL individual companies listed on it.

Directory URL: {url}
Page Content:
{content}

Return ONLY a valid JSON array of companies found:
[
  {{
    "company":  "Company name",
    "website":  "Their website URL if shown",
    "phone":    "Their phone number",
    "email":    "Their email",
    "city":     "Their city/location",
    "products": "What they sell/make",
    "snippet":  "Brief description"
  }},
  ...
]

Extract as many companies as you can find. Return empty array [] if none found.
"""


def extract_directory_companies(url: str, content: str) -> list:
    """
    Extract individual company listings from a directory page.
    Returns list of company dicts.
    """
    if not content:
        return []

    provider = _get_provider()
    if not provider:
        return []

    prompt = _DIRECTORY_PROMPT.format(
        url=url[:100],
        content=content[:8000],
    )

    try:
        text = _call_llm([{"role": "user", "content": prompt}],
                         max_tokens=2000, temperature=0.1)
        clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
        arr_m = re.search(r"\[.*\]", clean, re.DOTALL)
        if not arr_m:
            return []
        companies = json.loads(arr_m.group())
        logger.info("Extracted %d companies from directory %s", len(companies), url)
        return companies if isinstance(companies, list) else []
    except Exception as exc:
        logger.warning("Directory extraction failed for %s: %s", url, exc)
        return []


# ---------------------------------------------------------------------------
# Combined pipeline — called by scraper_google.py
# ---------------------------------------------------------------------------

def full_llm_pipeline(query: str, company: str, website: str,
                      content: str) -> dict:
    """
    Run the full 2-model pipeline:
      Step 1: DeepSeek finds contact person
      Step 2: Grok validates + analyses the lead

    Returns merged result dict.
    """
    import concurrent.futures

    contact_result  = {}
    validate_result = {}

    # Run both in parallel to save time
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_contact  = ex.submit(find_contact_person, company, website, content)
        f_validate = ex.submit(validate_and_analyse, query, company, website, content)

        try:
            contact_result  = f_contact.result(timeout=25)
        except Exception as e:
            logger.warning("Contact pipeline failed: %s", e)
            contact_result = {}

        try:
            validate_result = f_validate.result(timeout=30)
        except Exception as e:
            logger.warning("Validate pipeline failed: %s", e)
            validate_result = {}

    # Merge — validate_result has richer data, contact_result fills contact fields
    merged = dict(validate_result)

    # Contact fields: use DeepSeek result if available and better
    for field in ["contact_person", "contact_email", "contact_phone",
                  "contact_title", "contact_linkedin", "confidence"]:
        val = contact_result.get(field, "")
        if val and not merged.get(field):
            merged[field] = val

    # Map contact_email → email if no email found yet
    if merged.get("contact_email") and not merged.get("email"):
        merged["email"] = merged["contact_email"]

    return merged


# ---------------------------------------------------------------------------
# Provider info
# ---------------------------------------------------------------------------

def get_active_provider() -> dict:
    cfg = _get_provider()
    if not cfg:
        return {"provider": "none", "model": "none", "status": "no API key set"}
    name = next((k for k, v in _PROVIDERS.items() if v is cfg), "unknown")
    return {"provider": name, "model": cfg["model"], "url": cfg["url"], "status": "active"}


def get_all_providers() -> dict:
    """Return status of all 3 providers."""
    result = {}
    for name, cfg in _PROVIDERS.items():
        key = os.getenv(cfg["key_env"], "").strip()
        result[name] = {
            "available": bool(key),
            "model":     cfg["model"],
            "key_set":   bool(key),
        }
    return result


# Aliases
analyze_company  = lambda q, c: full_llm_pipeline(q, "", "", c)
analyse_company  = analyze_company
