"""
search_strategy.py — AI-powered search query engine
=====================================================
Instead of searching Google once with the user's raw query,
this module uses Grok to generate 8-12 targeted search queries
designed to find REAL company contacts — not directories or aggregators.

Strategy:
  1. Grok analyses intent → generates diverse search angles
  2. Each angle targets a different signal: contact pages, LinkedIn,
     industry associations, government registries, trade databases
  3. Results are deduplicated and scored by uniqueness
  4. Companies already on page 1 of Google are DEPRIORITISED
     (they're usually too big or already known)
"""

import os
import re
import json
import logging
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

SERP_API_KEY = os.getenv("SERP_API_KEY","")

# ── Query generation prompt ───────────────────────────────────────────────────
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
- Include industry association member lists
- Include government export/import database searches
- Avoid queries that return Indiamart, JustDial, Sulekha, TradeIndia etc.
- Mix broad and niche queries to find hidden gems

Return ONLY valid JSON array of strings:
[
  "query 1",
  "query 2",
  ...
]

Focus on finding companies that:
- Have a real website with contact details
- Are NOT on the first page of obvious searches
- Have a decision maker's name/email/phone findable
"""

# ── Contact finder prompt ─────────────────────────────────────────────────────
_CONTACT_SEARCH_PROMPT = """
Find the decision maker's contact details for this company:
Company: {company}
Website: {website}
Industry: {industry}

Generate 3 Google search queries to find:
1. The owner/director/CEO name and email
2. Their LinkedIn profile
3. Their phone number or direct contact

Return ONLY JSON array:
["query1", "query2", "query3"]
"""

def generate_search_queries(user_query: str, country: str = "",
                            city: str = "", industry: str = "") -> list:
    """
    Use Grok to generate 10 targeted search queries from user intent.
    Falls back to rule-based generation if Grok unavailable.
    """
    # Try LLM first
    try:
        from llm import _call_llm, _extract_json, _get_provider
        if _get_provider("grok"):
            context = user_query
            if city and city != "Any":       context += f" in {city}"
            elif country and country != "Any Country": context += f" in {country}"
            if industry and industry != "Any": context += f" ({industry} industry)"

            prompt = _QUERY_GEN_PROMPT.format(user_query=context)
            text   = _call_llm([{"role":"user","content":prompt}],
                               provider_name="grok", max_tokens=600, temperature=0.3)
            arr = re.search(r'\[.*?\]', text, re.DOTALL)
            if arr:
                queries = json.loads(arr.group())
                if isinstance(queries, list) and len(queries) >= 3:
                    logger.info("Grok generated %d search queries", len(queries))
                    return [str(q) for q in queries[:12]]
    except Exception as e:
        logger.warning("Grok query generation failed: %s", e)

    # Rule-based fallback — covers 8 proven angles
    return _rule_based_queries(user_query, country, city, industry)


def _rule_based_queries(query: str, country: str = "",
                        city: str = "", industry: str = "") -> list:
    """
    Generate targeted queries without LLM.
    Each query is designed to surface a different type of lead.
    """
    q       = query.strip()
    loc     = city if city and city not in ("Any","") else (
              country if country and country != "Any Country" else "india")
    loc_low = loc.lower()

    # Extract core intent words (remove location words)
    intent = re.sub(
        r'\b(importers?|exporters?|manufacturers?|distributors?|traders?|'
        r'wholesalers?|dealers?|suppliers?|india|uae|usa|uk|in|list|top|best)\b',
        '', q, flags=re.I
    ).strip()
    intent = re.sub(r'\s+', ' ', intent).strip() or q

    queries = [
        # 1. Direct company website with contact page
        f'{q} {loc} "contact us" site:.com OR site:.in',

        # 2. LinkedIn company pages
        f'{q} {loc} site:linkedin.com/company',

        # 3. Find owner/director contact
        f'"{intent}" {loc_low} owner director email -indiamart -justdial -tradeindia',

        # 4. About us pages (have company info)
        f'{q} {loc} "about us" "established" -justdial -indiamart -sulekha',

        # 5. Industry association members
        f'"{intent}" {loc_low} association members exporters importers',

        # 6. DGFT / export import registered companies
        f'"{intent}" {loc_low} DGFT IEC registered exporters',

        # 7. Trade fair / exhibition participants
        f'"{intent}" {loc_low} exhibition participants 2023 OR 2024',

        # 8. Government supplier / GeM portal
        f'"{intent}" {loc_low} gem.gov.in supplier OR government supplier',

        # 9. Startup / SME databases
        f'"{intent}" {loc_low} SME MSME company -directory -listing',

        # 10. News mentions (real operating businesses)
        f'"{intent}" {loc_low} company inaugurated OR launched OR expanded 2023 OR 2024',

        # 11. LinkedIn personal profiles of decision makers
        f'{intent} {loc_low} director OR "managing director" OR owner site:linkedin.com/in',

        # 12. Domain-specific searches
        f'{q} {loc} "our products" OR "our services" "contact" -indiamart -justdial',
    ]

    return [q for q in queries if q.strip()]


def generate_contact_queries(company: str, website: str,
                              industry: str = "") -> list:
    """Generate queries specifically to find decision maker contact info."""
    domain = ""
    try:
        from urllib.parse import urlparse
        domain = urlparse(website).netloc.replace("www.","")
    except Exception: pass

    queries = [
        f'"{company}" owner OR director OR CEO email',
        f'"{company}" {domain} contact phone',
        f'"{company}" linkedin.com/in OR linkedin.com/company',
    ]

    # Try LLM for better queries
    try:
        from llm import _call_llm, _get_provider
        if _get_provider("deepseek"):
            prompt = _CONTACT_SEARCH_PROMPT.format(
                company=company, website=website, industry=industry)
            text = _call_llm([{"role":"user","content":prompt}],
                             provider_name="deepseek", max_tokens=200, temperature=0.2)
            arr = re.search(r'\[.*?\]', text, re.DOTALL)
            if arr:
                llm_queries = json.loads(arr.group())
                if isinstance(llm_queries, list):
                    queries = [str(q) for q in llm_queries[:3]] + queries
    except Exception: pass

    return queries[:5]
