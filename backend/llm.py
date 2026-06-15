"""
llm.py  — v4  (Robust multi-model pipeline with OpenRouter primary fallback)
=============================================================================
Priority order per job:
  Contact finder  : DeepSeek → OpenRouter → skip (return empty)
  Lead validator  : Grok     → OpenRouter → rule-based fallback (never fails)
  Directory extract: any available → skip

Key fixes in v4:
  - OpenRouter is now the PRIMARY fallback when DeepSeek/Grok are unavailable
  - All LLM calls check availability BEFORE attempting (no wasted retries)
  - Rule-based fallback in validate_and_analyse so leads are ALWAYS saved
  - import path fixed for both package and standalone modes
  - Provider health cache: once a provider fails 402/403, skip it for the session
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
        "model":   os.getenv("LLM_MODEL", "mistralai/mistral-7b-instruct:free"),
    },
}

# Session-level health cache: if a provider returns 402/403 once, skip it
_PROVIDER_DEAD: dict[str, bool] = {}


def _has_key(name: str) -> bool:
    cfg = _PROVIDERS.get(name)
    if not cfg:
        return False
    return bool(os.getenv(cfg["key_env"], "").strip())


def _is_alive(name: str) -> bool:
    return _has_key(name) and not _PROVIDER_DEAD.get(name, False)


def _mark_dead(name: str, status_code: int) -> None:
    """Mark a provider as dead for this session if auth/billing error."""
    if status_code in (401, 402, 403):
        _PROVIDER_DEAD[name] = True
        logger.warning("Provider '%s' marked dead (HTTP %d) for this session", name, status_code)


def _get_provider(name: str = None) -> tuple[str, dict] | tuple[None, None]:
    """
    Return (name, config) for the requested or best available provider.
    Returns (None, None) if nothing is available.
    """
    if name:
        cfg = _PROVIDERS.get(name)
        if cfg and _is_alive(name):
            return name, cfg
        return None, None

    # Auto-select: prefer deepseek → grok → openrouter
    for n in ["deepseek", "grok", "openrouter"]:
        if _is_alive(n):
            return n, _PROVIDERS[n]
    return None, None


def _call_llm(messages: list, provider_name: str = None,
              max_tokens: int = 800, temperature: float = 0.1,
              retries: int = 2) -> str:
    """
    Call specified provider (or best available). Marks providers dead on
    402/403 so they aren't retried in the same session.
    Raises RuntimeError if all options exhausted.
    """
    # Build candidate list
    if provider_name:
        candidates = [provider_name]
        # Always add openrouter as fallback
        if provider_name != "openrouter" and _is_alive("openrouter"):
            candidates.append("openrouter")
    else:
        candidates = [n for n in ["deepseek", "grok", "openrouter"] if _is_alive(n)]

    if not candidates:
        raise RuntimeError("No LLM provider available (all keys missing or dead)")

    last_exc = None
    for pname in candidates:
        cfg = _PROVIDERS.get(pname)
        if not cfg or not _is_alive(pname):
            continue

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

        for attempt in range(retries):
            try:
                resp = requests.post(cfg["url"], headers=headers,
                                     json=payload, timeout=30)
                if resp.status_code in (402, 403):
                    _mark_dead(pname, resp.status_code)
                    break  # try next provider
                resp.raise_for_status()
                return resp.json()["choices"][0]["message"]["content"]
            except requests.HTTPError as exc:
                code = exc.response.status_code if exc.response else 0
                _mark_dead(pname, code)
                last_exc = exc
                logger.warning("LLM %s attempt %d/%d HTTP %d", pname, attempt+1, retries, code)
                break  # don't retry 4xx — move to next provider
            except Exception as exc:
                last_exc = exc
                logger.warning("LLM %s attempt %d/%d failed: %s", pname, attempt+1, retries, exc)
                if attempt < retries - 1:
                    time.sleep(1.5)

    raise RuntimeError(f"All LLM providers exhausted. Last error: {last_exc}")


def _extract_json(text: str) -> dict:
    clean = re.sub(r"```(?:json)?", "", text).replace("```", "").strip()
    match = re.search(r"\{.*\}", clean, re.DOTALL)
    if match:
        return json.loads(match.group())
    return json.loads(clean)


# ---------------------------------------------------------------------------
# JOB 1 — Contact Finder (DeepSeek preferred, OpenRouter fallback)
# ---------------------------------------------------------------------------

_CONTACT_PROMPT = """\
You are a B2B contact research specialist. Find the best person to contact at this company.

Company Name: {company}
Website: {website}
Website Content:
{content}

Search for: Owner / Founder / Director / CEO / MD / Partner name, email, phone, LinkedIn.

Return ONLY valid JSON:
{{
  "contact_person":  "Full name",
  "contact_title":   "Job title",
  "contact_email":   "Direct email if found",
  "contact_phone":   "Phone/mobile if found",
  "contact_linkedin":"LinkedIn URL if found",
  "confidence":      "high / medium / low",
  "source":          "Where found"
}}
"""

def find_contact_person(company: str, website: str, content: str) -> dict:
    fallback = {
        "contact_person": "", "contact_title": "", "contact_email": "",
        "contact_phone": "", "contact_linkedin": "", "confidence": "low", "source": "",
    }
    if not content or len(content.strip()) < 50:
        return fallback

    # Try DeepSeek first, then OpenRouter
    pname, _ = _get_provider("deepseek")
    if not pname:
        pname, _ = _get_provider("openrouter")
    if not pname:
        logger.info("No provider available for contact finding — skipping")
        return fallback

    prompt = _CONTACT_PROMPT.format(
        company=company[:100], website=website[:100], content=content[:4000])
    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           provider_name=pname, max_tokens=400, temperature=0.1)
        result = _extract_json(text)
        logger.info("Contact found for %s: %s (conf: %s)",
                    company, result.get("contact_person","—"), result.get("confidence","?"))
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
        logger.warning("Contact find failed for %s: %s", company, exc)
        return fallback


# ---------------------------------------------------------------------------
# JOB 2 — Lead Validator (Grok preferred, OpenRouter fallback, rule-based last)
# ---------------------------------------------------------------------------

_VALIDATE_PROMPT = """\
You are a B2B sales analyst. Validate this company as a sales prospect and extract its profile.

Search Query: {query}
Company: {company}
Website: {website}
Content:
{content}

Return ONLY valid JSON:
{{
  "is_valid_lead":      true,
  "rejection_reason":   "",
  "relevance_score":    7,
  "summary":            "2-3 sentence description",
  "usp":                "Unique selling point",
  "products":           ["product1", "product2"],
  "product_type":       "Primary product category",
  "industry":           "Industry sector",
  "channel_type":       "Manufacturer / Importer / Trader / Wholesaler / Distributor / Retailer",
  "company_size":       "Employee count",
  "annual_turnover":    "Revenue if mentioned",
  "city":               "HQ city",
  "country":            "HQ country",
  "incorporation_date": "Year founded",
  "certifications":     [],
  "export_markets":     [],
  "key_customers":      [],
  "is_directory":       false
}}
"""

def validate_and_analyse(query: str, company: str, website: str, content: str) -> dict:
    fallback = _rule_based_analyse(query, company, website, content)

    if not content or len(content.strip()) < 50:
        return fallback

    # Try Grok first, then OpenRouter
    pname, _ = _get_provider("grok")
    if not pname:
        pname, _ = _get_provider("openrouter")
    if not pname:
        logger.info("No LLM provider available — using rule-based analysis for %s", company)
        return fallback

    prompt = _VALIDATE_PROMPT.format(
        query=query[:200], company=company[:100],
        website=website[:100], content=content[:6000])
    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           provider_name=pname, max_tokens=900, temperature=0.1)
        result = _extract_json(text)

        valid_channels = {"Manufacturer","Importer","Trader","Wholesaler","Distributor","Retailer",""}
        channel = str(result.get("channel_type","") or "").strip().title()
        if channel not in valid_channels:
            channel = ""

        logger.info("Validated %s: valid=%s score=%s (provider=%s)",
                    company, result.get("is_valid_lead"), result.get("relevance_score"), pname)
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
        logger.warning("LLM validation failed for %s: %s — using rule-based fallback", company, exc)
        return fallback


def _rule_based_analyse(query: str, company: str, website: str, content: str) -> dict:
    """
    Pure rule-based analysis — always succeeds, no LLM required.
    Detects industry, channel type, city, country from text patterns.
    """
    from nlp import _query_tokens, keyword_match_ratio
    import re as _re

    text = (content or "").lower()
    q_lo = query.lower()

    # Channel detection
    channel_kw = {
        "Manufacturer": ["manufacturer","manufacturing","we manufacture","our factory","oem","odm","fabricat"],
        "Importer":     ["importer","import","we import","iec","customs","cif","fob"],
        "Wholesaler":   ["wholesaler","wholesale","bulk","moq","minimum order"],
        "Distributor":  ["distributor","distribution","authorised distributor","channel partner"],
        "Trader":       ["trader","trading company","buy and sell"],
        "Retailer":     ["retailer","retail","showroom","add to cart"],
    }
    channel = ""
    best_ch  = 0
    for ch, kws in channel_kw.items():
        score = sum(1 for kw in kws if kw in text)
        if score > best_ch:
            best_ch, channel = score, ch

    # Industry detection
    industry_map = {
        "Electronics":     ["electronics","led","solar","circuit","semiconductor"],
        "Pharmaceuticals": ["pharma","medicine","drug","biotech","api"],
        "Textiles":        ["textile","fabric","garment","apparel","yarn"],
        "Chemicals":       ["chemical","polymer","resin","adhesive","pigment"],
        "Machinery":       ["machinery","machine","equipment","pump","valve","motor"],
        "Food & Beverage": ["food","beverage","spice","dairy","snack"],
        "Automotive":      ["automotive","automobile","tyre","auto parts"],
        "Construction":    ["construction","cement","steel","tile","pipe"],
        "IT & Software":   ["software","saas","cloud","erp","technology"],
        "Healthcare":      ["healthcare","medical","diagnostics","surgical"],
        "Logistics":       ["logistics","freight","shipping","warehouse"],
        "Agriculture":     ["agriculture","fertilizer","seed","crop","farm"],
    }
    industry = ""
    for ind, kws in industry_map.items():
        if any(kw in text or kw in q_lo for kw in kws):
            industry = ind
            break

    # Simple city/country detection
    city_list = ["Mumbai","Delhi","Bangalore","Hyderabad","Ahmedabad","Chennai",
                 "Kolkata","Pune","Surat","Jaipur","Lucknow","Noida","Gurgaon",
                 "Dubai","Singapore","London","New York","Toronto"]
    city = next((c for c in city_list if c.lower() in text), "")

    country = ""
    for sig, name in [("india","India"),("uae","UAE"),("usa","USA"),
                       ("uk","UK"),("singapore","Singapore"),("dubai","UAE")]:
        if sig in text:
            country = name
            break

    # Extract emails
    emails = _re.findall(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-z]{2,}", content or "")
    best_email = next((e for e in emails if "@" in e and len(e) < 80 and
                       not _re.search(r"^(noreply|no-reply|webmaster|example)", e, _re.I)), "")

    # Relevance score based on keyword overlap
    kw_score = keyword_match_ratio(query, content or "") if content else 0.0
    rel_score = min(10, max(1, int(kw_score * 10) + (2 if channel else 0) + (1 if industry else 0)))

    # Build a basic summary from content
    sentences = [s.strip() for s in _re.split(r"[.!?]", content or "") if 20 < len(s.strip()) < 200]
    summary   = ". ".join(sentences[:2]) if sentences else f"{company} — {industry or 'business'} company."

    return {
        "is_valid_lead":      True,
        "rejection_reason":   "",
        "relevance_score":    rel_score,
        "summary":            summary[:400],
        "usp":                "",
        "products":           [],
        "product_type":       industry,
        "industry":           industry,
        "channel_type":       channel,
        "company_size":       "",
        "annual_turnover":    "",
        "city":               city,
        "country":            country,
        "incorporation_date": "",
        "certifications":     [],
        "export_markets":     [],
        "key_customers":      [],
        "is_directory":       False,
    }


# ---------------------------------------------------------------------------
# Directory extractor
# ---------------------------------------------------------------------------

_DIRECTORY_PROMPT = """\
This webpage is a business directory. Extract ALL individual companies listed.

Directory URL: {url}
Page Content:
{content}

Return ONLY a valid JSON array:
[
  {{
    "company":  "Company name",
    "website":  "Their website URL",
    "phone":    "Their phone",
    "email":    "Their email",
    "city":     "Their city",
    "products": "What they sell",
    "snippet":  "Brief description"
  }}
]

Return empty array [] if no companies found.
"""

def extract_directory_companies(url: str, content: str) -> list:
    if not content:
        return []

    pname, _ = _get_provider()
    if not pname:
        return []

    prompt = _DIRECTORY_PROMPT.format(url=url[:100], content=content[:7000])
    try:
        text  = _call_llm([{"role": "user", "content": prompt}],
                          provider_name=pname, max_tokens=2000, temperature=0.1)
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
# Combined pipeline
# ---------------------------------------------------------------------------

def full_llm_pipeline(query: str, company: str, website: str, content: str) -> dict:
    """
    Run contact finder + validator in parallel.
    ALWAYS returns a result (rule-based fallback if all LLMs fail).
    """
    import concurrent.futures

    contact_result  = {}
    validate_result = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        f_contact  = ex.submit(find_contact_person, company, website, content)
        f_validate = ex.submit(validate_and_analyse, query, company, website, content)
        try:
            contact_result  = f_contact.result(timeout=35)
        except Exception as e:
            logger.warning("Contact pipeline timeout/error: %s", e)
        try:
            validate_result = f_validate.result(timeout=40)
        except Exception as e:
            logger.warning("Validate pipeline timeout/error: %s", e)

    merged = dict(validate_result) if validate_result else _rule_based_analyse(query, company, website, content)

    for field in ["contact_person", "contact_email", "contact_phone",
                  "contact_title", "contact_linkedin", "confidence"]:
        val = contact_result.get(field, "")
        if val and not merged.get(field):
            merged[field] = val

    if merged.get("contact_email") and not merged.get("email"):
        merged["email"] = merged["contact_email"]

    return merged


# ---------------------------------------------------------------------------
# Provider info
# ---------------------------------------------------------------------------

def get_active_provider() -> dict:
    pname, cfg = _get_provider()
    if not cfg:
        return {"provider": "none", "model": "none", "status": "no API key configured"}
    return {"provider": pname, "model": cfg["model"], "url": cfg["url"], "status": "active"}


def get_all_providers() -> dict:
    result = {}
    for name, cfg in _PROVIDERS.items():
        key   = os.getenv(cfg["key_env"], "").strip()
        dead  = _PROVIDER_DEAD.get(name, False)
        result[name] = {
            "available": bool(key) and not dead,
            "key_set":   bool(key),
            "dead":      dead,
            "model":     cfg["model"],
        }
    return result


# Aliases
analyze_company = lambda q, c: full_llm_pipeline(q, "", "", c)
analyse_company = analyze_company
