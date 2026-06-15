"""
search_strategy.py — AI-powered search query engine
=====================================================
FIX v2: Correct relative/absolute import handling so this works
both when run as part of the backend package AND standalone.
"""

import os
import re
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SERP_API_KEY = os.getenv("SERP_API_KEY", "")

_QUERY_GEN_PROMPT = """
You are a B2B lead generation expert. A salesperson wants to find:

"{user_query}"

Generate 10 highly targeted Google search queries that will find REAL companies
with actual contact details — NOT directories, NOT aggregators, NOT listing sites.

Rules:
- Target company websites directly (their own domains)
- Include queries that find contact pages, about pages, team pages
- Include LinkedIn company searches for decision makers
- Include variations with specific cities/states if relevant
- Avoid queries that return Indiamart, JustDial, Sulekha, TradeIndia etc.
- Mix broad and niche queries to find hidden gems

Return ONLY valid JSON array of strings:
["query 1", "query 2", ...]
"""


def generate_search_queries(user_query: str, country: str = "",
                            city: str = "", industry: str = "") -> list:
    """
    Generate targeted search queries. Uses Grok or OpenRouter if available,
    otherwise falls back to rule-based generation.
    """
    # Fixed import — works in both package mode (backend.llm) and direct mode
    try:
        # Try relative import first (when running as part of the package)
        try:
            from .llm import _call_llm, _get_provider
        except ImportError:
            from llm import _call_llm, _get_provider

        # Try Grok first, then OpenRouter for query generation
        pname, _ = _get_provider("grok")
        if not pname:
            pname, _ = _get_provider("openrouter")

        if pname:
            context = user_query
            if city and city not in ("Any", ""):
                context += f" in {city}"
            elif country and country not in ("Any Country", ""):
                context += f" in {country}"
            if industry and industry not in ("Any", ""):
                context += f" ({industry} industry)"

            prompt = _QUERY_GEN_PROMPT.format(user_query=context)
            text   = _call_llm([{"role": "user", "content": prompt}],
                               provider_name=pname, max_tokens=600, temperature=0.3)
            arr = re.search(r'\[.*?\]', text, re.DOTALL)
            if arr:
                queries = json.loads(arr.group())
                if isinstance(queries, list) and len(queries) >= 3:
                    logger.info("LLM (%s) generated %d search queries", pname, len(queries))
                    return [str(q) for q in queries[:12]]
    except Exception as e:
        logger.warning("LLM query generation failed: %s", e)

    # Rule-based fallback — always works
    logger.info("Using rule-based query generation for: %s", user_query[:60])
    return _rule_based_queries(user_query, country, city, industry)


def _rule_based_queries(query: str, country: str = "",
                        city: str = "", industry: str = "") -> list:
    """
    Generate targeted queries without LLM — covers 12 proven search angles.
    """
    q       = query.strip()
    loc     = city if city and city not in ("Any", "") else (
              country if country and country not in ("Any Country", "") else "india")
    loc_low = loc.lower()

    # Strip common generic words from intent
    intent = re.sub(
        r'\b(importers?|exporters?|manufacturers?|distributors?|traders?|'
        r'wholesalers?|dealers?|suppliers?|india|uae|usa|uk|in|list|top|best|'
        r'company|companies)\b',
        '', q, flags=re.I
    ).strip()
    intent = re.sub(r'\s+', ' ', intent).strip() or q

    queries = [
        # Direct company contact pages
        f'{q} {loc} "contact us" -indiamart -justdial -tradeindia',
        # Company about pages
        f'{q} {loc} "about us" "established" -justdial -indiamart -sulekha',
        # LinkedIn company profiles
        f'{q} {loc} site:linkedin.com/company',
        # Owner/director contact
        f'"{intent}" {loc_low} owner director email -indiamart -justdial -tradeindia',
        # DGFT/IEC registered exporters
        f'"{intent}" {loc_low} DGFT IEC registered exporters',
        # Industry association members
        f'"{intent}" {loc_low} association members manufacturers',
        # Trade fair participants
        f'"{intent}" {loc_low} exhibition participants 2024',
        # Government GeM portal suppliers
        f'"{intent}" {loc_low} gem.gov.in supplier',
        # SME/MSME databases
        f'"{intent}" {loc_low} SME MSME company -directory -listing',
        # News mentions (active businesses)
        f'"{intent}" {loc_low} company launched OR expanded 2023 OR 2024',
        # LinkedIn decision makers
        f'{intent} {loc_low} "managing director" OR owner site:linkedin.com/in',
        # Products/services pages
        f'{q} {loc} "our products" OR "our services" "contact" -indiamart -justdial',
    ]

    return [q for q in queries if q.strip()]


def generate_contact_queries(company: str, website: str, industry: str = "") -> list:
    """Generate queries to find decision maker contact info."""
    queries = [
        f'"{company}" owner OR director OR CEO email',
        f'"{company}" contact phone',
        f'"{company}" site:linkedin.com/in OR site:linkedin.com/company',
    ]

    try:
        try:
            from .llm import _call_llm, _get_provider
        except ImportError:
            from llm import _call_llm, _get_provider

        pname, _ = _get_provider("deepseek")
        if not pname:
            pname, _ = _get_provider("openrouter")

        if pname:
            prompt = f"""Find decision maker contacts for:
Company: {company}
Website: {website}
Generate 3 Google search queries. Return ONLY JSON array: ["q1","q2","q3"]"""
            text = _call_llm([{"role": "user", "content": prompt}],
                             provider_name=pname, max_tokens=200, temperature=0.2)
            arr = re.search(r'\[.*?\]', text, re.DOTALL)
            if arr:
                llm_qs = json.loads(arr.group())
                if isinstance(llm_qs, list):
                    queries = [str(q) for q in llm_qs[:3]] + queries
    except Exception:
        pass

    return queries[:5]
