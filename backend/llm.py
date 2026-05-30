"""
llm.py  –  Multi-provider LLM client  (v2 — enriched company profile)
=======================================================================
Supports three providers selectable via LLM_PROVIDER env var:

    LLM_PROVIDER=deepseek    (default)
    LLM_PROVIDER=grok
    LLM_PROVIDER=openrouter

New in v2
---------
analyze_company() now extracts 12 additional fields:
    city, country, linkedin_url, incorporation_date, company_size,
    channel_type, contact_person, contact_email, industry, product_type,
    website_active, products
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
PROVIDER = os.getenv("LLM_PROVIDER", "deepseek").lower().strip()

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

_FALLBACK_ORDER = ["deepseek", "grok", "openrouter"]


def _get_provider() -> dict | None:
    cfg = _PROVIDERS.get(PROVIDER)
    if cfg and os.getenv(cfg["key_env"], "").strip():
        return cfg
    for name in _FALLBACK_ORDER:
        cfg = _PROVIDERS[name]
        if os.getenv(cfg["key_env"], "").strip():
            logger.info("LLM: falling back to provider '%s'", name)
            return cfg
    return None


_FALLBACK_RESULT = {
    "summary":            "",
    "products":           [],
    "industry":           "",
    "relevant":           False,
    "score":              0,
    # New enriched fields
    "city":               "",
    "country":            "",
    "linkedin_url":       "",
    "incorporation_date": "",
    "company_size":       "",
    "channel_type":       "",
    "contact_person":     "",
    "contact_email":      "",
    "website_active":     "",
    "product_type":       "",
}


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(clean)


def _normalise(result: dict) -> dict:
    products = result.get("products") or []
    if not isinstance(products, list):
        products = [str(products)]

    # Validate channel_type
    valid_channels = {
        "Manufacturer", "Importer", "Trader",
        "Wholesaler", "Distributor", "Retailer", ""
    }
    channel = str(result.get("channel_type", "") or "").strip().title()
    if channel not in valid_channels:
        channel = ""

    return {
        "summary":            str(result.get("summary",            "") or ""),
        "products":           [str(p) for p in products if p],
        "industry":           str(result.get("industry",           "") or ""),
        "relevant":           bool(result.get("relevant",          False)),
        "score":              max(0, min(int(result.get("score", 0) or 0), 10)),
        # New fields
        "city":               str(result.get("city",               "") or ""),
        "country":            str(result.get("country",            "") or ""),
        "linkedin_url":       str(result.get("linkedin_url",       "") or ""),
        "incorporation_date": str(result.get("incorporation_date", "") or ""),
        "company_size":       str(result.get("company_size",       "") or ""),
        "channel_type":       channel,
        "contact_person":     str(result.get("contact_person",     "") or ""),
        "contact_email":      str(result.get("contact_email",      "") or ""),
        "website_active":     str(result.get("website_active",     "") or ""),
        "product_type":       str(result.get("product_type",       "") or ""),
    }


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------

def _call_llm(messages: list, max_tokens: int = 512,
              temperature: float = 0.1, retries: int = 2) -> str:
    cfg = _get_provider()
    if not cfg:
        raise RuntimeError("No LLM API key configured. Set DEEPSEEK_API_KEY, "
                           "GROK_API_KEY, or OPENROUTER_API_KEY in .env")

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
            resp = requests.post(
                cfg["url"], headers=headers,
                json=payload, timeout=30,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"]
        except (requests.RequestException, KeyError, IndexError) as exc:
            last_exc = exc
            logger.warning("LLM attempt %d/%d failed: %s", attempt + 1, retries, exc)
            if attempt < retries - 1:
                time.sleep(1.5)

    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# ENHANCED: Company analysis prompt — extracts 16 fields
# ---------------------------------------------------------------------------

_COMPANY_PROMPT = """\
You are a B2B lead qualification assistant.

User Search Query: {query}

Company Website Content:
{content}

Analyse this company carefully and return ONLY a valid JSON object — no explanation, \
no markdown, no extra text.

JSON schema (return ALL keys, use empty string "" or null for unknown values):
{{
  "summary":            "One sentence describing what this company does",
  "products":           ["product or service 1", "product or service 2"],
  "product_type":       "Primary product category (e.g. LED Lighting, Steel Pipes)",
  "industry":           "Industry sector (e.g. Electronics, Pharmaceuticals, Textiles)",
  "channel_type":       "One of: Manufacturer / Importer / Trader / Wholesaler / Distributor / Retailer",
  "company_size":       "Employee count or range (e.g. 50-200, 500+, 10-50)",
  "city":               "City where company is headquartered",
  "country":            "Country where company is headquartered",
  "linkedin_url":       "LinkedIn company page URL if mentioned in content, else empty string",
  "incorporation_date": "Year or date of incorporation/founding (e.g. 2005, 12/03/2010)",
  "contact_person":     "Name of contact person if mentioned",
  "contact_email":      "Contact email address if found in content",
  "website_active":     "Company website URL",
  "relevant":           true or false (is this company a potential client for the query?),
  "score":              integer 1-10 (relevance score, 10 = perfect match)
}}
"""


def analyze_company(query: str, content: str) -> dict:
    """
    Analyse a company's website content against the user's search query.
    Returns a dict with all enriched fields including the 12 new profile fields.
    """
    cfg = _get_provider()
    if not cfg:
        logger.debug("No LLM provider available — skipping analysis")
        return dict(_FALLBACK_RESULT)

    if not content or len(content.strip()) < 50:
        return dict(_FALLBACK_RESULT)

    prompt = _COMPANY_PROMPT.format(
        query=query[:200],
        content=content[:3500],
    )

    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           max_tokens=600, temperature=0.1)
        result = _extract_json(text)
        return _normalise(result)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM JSON parse failed: %s", exc)
        return dict(_FALLBACK_RESULT)
    except RuntimeError as exc:
        logger.warning("LLM call failed: %s", exc)
        return dict(_FALLBACK_RESULT)


# ---------------------------------------------------------------------------
# Batch lead analysis
# ---------------------------------------------------------------------------

_BATCH_PROMPT = """\
You are a B2B lead qualification assistant.

User Search Query: {query}

Below are {n} companies. For each, analyse its description and return a JSON \
array of objects — one per company in the same order.

Companies:
{companies}

Return ONLY a valid JSON array. No explanation, no markdown.

Schema per object:
{{
  "summary":      "One sentence",
  "products":     ["product1"],
  "industry":     "sector",
  "channel_type": "Manufacturer / Importer / Trader / Wholesaler / Distributor / Retailer",
  "company_size": "employee range",
  "city":         "headquarters city",
  "country":      "headquarters country",
  "relevant":     true/false,
  "score":        1-10
}}
"""


def analyze_leads_batch(query: str, leads: list) -> list:
    cfg = _get_provider()
    if not cfg or not leads:
        return leads

    company_lines = []
    for i, lead in enumerate(leads):
        name    = lead.get("company", f"Company {i+1}")
        snippet = (lead.get("ai_summary", "") or
                   lead.get("snippet", "") or "")[:400]
        company_lines.append(f"{i+1}. {name}: {snippet}")

    companies_text = "\n".join(company_lines)
    prompt = _BATCH_PROMPT.format(
        query=query[:200],
        n=len(leads),
        companies=companies_text,
    )

    try:
        text = _call_llm(
            [{"role": "user", "content": prompt}],
            max_tokens=min(200 * len(leads), 2000),
            temperature=0.1,
        )
        clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
        arr_match = re.search(r"\[.*\]", clean, re.DOTALL)
        if not arr_match:
            raise ValueError("No JSON array in response")

        results = json.loads(arr_match.group())
        enriched = []
        for i, lead in enumerate(leads):
            updated = dict(lead)
            if i < len(results):
                r = _normalise(results[i])
                if r["summary"]:
                    updated["ai_summary"] = r["summary"]
                if r["products"]:
                    updated["products"]      = r["products"]
                updated["llm_industry"]  = r["industry"]
                updated["llm_relevant"]  = r["relevant"]
                updated["llm_score"]     = r["score"]
                # Batch also fills new fields if present
                for field in ["channel_type", "company_size", "city", "country"]:
                    if r.get(field) and not updated.get(field):
                        updated[field] = r[field]
            enriched.append(updated)
        return enriched

    except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
        logger.warning("Batch LLM analysis failed: %s", exc)
        return leads


# ---------------------------------------------------------------------------
# Provider info
# ---------------------------------------------------------------------------

def get_active_provider() -> dict:
    cfg = _get_provider()
    if not cfg:
        return {"provider": "none", "model": "none", "status": "no API key set"}
    name = next((k for k, v in _PROVIDERS.items() if v is cfg), "unknown")
    return {
        "provider": name,
        "model":    cfg["model"],
        "url":      cfg["url"],
        "status":   "active",
    }


# Alias
analyse_company = analyze_company
