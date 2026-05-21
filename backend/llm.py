"""
llm.py  –  Multi-provider LLM client
======================================
Supports three providers selectable via LLM_PROVIDER env var:

    LLM_PROVIDER=deepseek    (default — best JSON extraction, cheapest)
    LLM_PROVIDER=grok
    LLM_PROVIDER=openrouter

Set the matching API key in .env:
    DEEPSEEK_API_KEY=...
    GROK_API_KEY=...
    OPENROUTER_API_KEY=...

All three use the OpenAI-compatible /v1/chat/completions format.

Functions
---------
analyze_company(query, content)  -> dict
    Extracts company summary, products, industry, relevance, score.

analyze_leads_batch(query, leads) -> list[dict]
    Runs analysis on a list of lead dicts and returns enriched results.
    Useful for post-search bulk enrichment.
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

# Fallback order if primary provider key is missing
_FALLBACK_ORDER = ["deepseek", "grok", "openrouter"]


def _get_provider() -> dict | None:
    """Return active provider config, falling back if key is missing."""
    # Try the configured provider first
    cfg = _PROVIDERS.get(PROVIDER)
    if cfg and os.getenv(cfg["key_env"], "").strip():
        return cfg

    # Try fallbacks
    for name in _FALLBACK_ORDER:
        cfg = _PROVIDERS[name]
        if os.getenv(cfg["key_env"], "").strip():
            logger.info("LLM: falling back to provider '%s'", name)
            return cfg

    return None  # No key available at all


_FALLBACK_RESULT = {
    "summary":  "",
    "products": [],
    "industry": "",
    "relevant": False,
    "score":    0,
}


# ---------------------------------------------------------------------------
# JSON extraction
# ---------------------------------------------------------------------------

def _extract_json(text: str) -> dict:
    """Strip markdown fences and parse the first JSON object found."""
    # Remove ```json ... ``` or ``` ... ```
    clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    # Find the first { ... } block
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(clean)


def _normalise(result: dict) -> dict:
    """Ensure all expected keys exist with correct types."""
    products = result.get("products") or []
    if not isinstance(products, list):
        products = [str(products)]

    return {
        "summary":  str(result.get("summary",  "") or ""),
        "products": [str(p) for p in products if p],
        "industry": str(result.get("industry", "") or ""),
        "relevant": bool(result.get("relevant", False)),
        "score":    max(0, min(int(result.get("score", 0) or 0), 10)),
    }


# ---------------------------------------------------------------------------
# Core LLM call
# ---------------------------------------------------------------------------

def _call_llm(messages: list, max_tokens: int = 512,
              temperature: float = 0.1, retries: int = 2) -> str:
    """
    Send messages to the active provider and return the text response.
    Retries once on transient errors with a short backoff.
    """
    cfg = _get_provider()
    if not cfg:
        raise RuntimeError("No LLM API key configured. Set DEEPSEEK_API_KEY, "
                           "GROK_API_KEY, or OPENROUTER_API_KEY in .env")

    api_key = os.getenv(cfg["key_env"], "").strip()
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type":  "application/json",
    }

    # OpenRouter needs a few extra headers
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
            logger.warning("LLM attempt %d/%d failed (%s): %s",
                           attempt + 1, retries, cfg["url"], exc)
            if attempt < retries - 1:
                time.sleep(1.5)

    raise RuntimeError(f"LLM call failed after {retries} attempts: {last_exc}")


# ---------------------------------------------------------------------------
# Company analysis
# ---------------------------------------------------------------------------

_COMPANY_PROMPT = """\
You are a B2B lead qualification assistant.

User Search Query: {query}

Company Website Content:
{content}

Analyse this company and return ONLY a valid JSON object — no explanation, \
no markdown, no extra text.

JSON schema:
{{
  "summary":  "One sentence describing what this company does",
  "products": ["product or service 1", "product or service 2"],
  "industry": "Industry sector",
  "relevant": true or false (is this company a potential client for the query?),
  "score":    integer 1-10 (relevance score, 10 = perfect match)
}}
"""


def analyze_company(query: str, content: str) -> dict:
    """
    Analyse a company's website content against the user's search query.
    Returns a dict with keys: summary, products, industry, relevant, score.
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
                           max_tokens=400, temperature=0.1)
        result = _extract_json(text)
        return _normalise(result)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("LLM JSON parse failed: %s", exc)
        return dict(_FALLBACK_RESULT)
    except RuntimeError as exc:
        logger.warning("LLM call failed: %s", exc)
        return dict(_FALLBACK_RESULT)


# ---------------------------------------------------------------------------
# Batch lead analysis  (for post-search enrichment)
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
  "summary":  "One sentence",
  "products": ["product1"],
  "industry": "sector",
  "relevant": true/false,
  "score":    1-10
}}
"""


def analyze_leads_batch(query: str, leads: list) -> list:
    """
    Run LLM analysis on a batch of lead dicts.

    Each lead dict should have at least:
        company, ai_summary or snippet, products (optional)

    Returns a list of enriched dicts in the same order.
    Gracefully falls back to the original lead if LLM fails.
    """
    cfg = _get_provider()
    if not cfg or not leads:
        return leads

    # Build a compact company list string
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
            max_tokens=min(150 * len(leads), 2000),
            temperature=0.1,
        )

        # Extract JSON array
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
                    updated["products"]   = r["products"]
                updated["llm_industry"] = r["industry"]
                updated["llm_relevant"] = r["relevant"]
                updated["llm_score"]    = r["score"]
            enriched.append(updated)

        return enriched

    except (json.JSONDecodeError, ValueError, RuntimeError) as exc:
        logger.warning("Batch LLM analysis failed: %s", exc)
        return leads


# ---------------------------------------------------------------------------
# Provider info  (useful for debugging)
# ---------------------------------------------------------------------------

def get_active_provider() -> dict:
    """Return info about which provider is currently active."""
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