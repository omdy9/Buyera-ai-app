import json
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "mistralai/mixtral-8x7b-instruct")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_TIMEOUT = int(os.getenv("OPENROUTER_TIMEOUT", "30"))
OPENROUTER_ENABLED = os.getenv("OPENROUTER_ENABLED", "true").lower() == "true"
OPENROUTER_QUERY_TIMEOUT = int(os.getenv("OPENROUTER_QUERY_TIMEOUT", "6"))


def llm_enabled():
    return OPENROUTER_ENABLED and bool(OPENROUTER_API_KEY)


def _extract_json(text):
    text = (text or "").strip()
    if not text:
        return {}

    # Handle markdown fences.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)

    try:
        return json.loads(text)
    except Exception:
        pass

    match = re.search(r"\{[\s\S]*\}", text)
    if not match:
        return {}

    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def analyze_with_llm(query, content, title="", snippet=""):
    if not llm_enabled():
        return {
            "summary": "",
            "products": [],
            "relevant": None,
        }

    prompt = f"""
You are analyzing a company website for B2B lead discovery.

User query:
{query}

Google title:
{title}

Google snippet:
{snippet}

Website content (truncated):
{(content or "")[:3500]}

Return ONLY valid JSON:
{{
  "summary": "2-3 lines about what this company actually does",
  "products": ["product/service 1", "product/service 2"],
  "relevant": true
}}

Rules:
- "relevant" must be true only if this company is directly doing business related to the query.
- If it looks like a consultant/agency/directory/listing, set relevant=false.
- Keep summary concise and factual.
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=OPENROUTER_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json()

        message = (
            raw.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _extract_json(message)

        summary = str(parsed.get("summary", "")).strip()
        products = parsed.get("products", [])
        relevant = parsed.get("relevant")

        if not isinstance(products, list):
            products = []
        products = [str(p).strip() for p in products if str(p).strip()]

        if isinstance(relevant, str):
            relevant = relevant.lower() == "true"
        elif not isinstance(relevant, bool):
            relevant = None

        return {
            "summary": summary,
            "products": products[:8],
            "relevant": relevant,
        }
    except Exception:
        return {
            "summary": "",
            "products": [],
            "relevant": None,
        }


def structure_query_with_llm(query):
    query = (query or "").strip()
    if not query:
        return {
            "search_query": "",
            "country": "",
            "must_have_terms": [],
            "exclude_terms": [],
        }

    fallback = {
        "search_query": query,
        "country": "",
        "must_have_terms": [],
        "exclude_terms": [],
    }

    if not llm_enabled():
        return fallback

    prompt = f"""
You are structuring a B2B company discovery query.

Original query:
{query}

Return ONLY valid JSON:
{{
  "search_query": "optimized query for finding direct business operators",
  "country": "country or empty string",
  "must_have_terms": ["term1", "term2"],
  "exclude_terms": ["term1", "term2"]
}}

Rules:
- Keep "search_query" concise.
- "country" should be a plain country name if clearly present, else empty.
- Avoid directory/listing intent.
- Return strict JSON only.
"""

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": OPENROUTER_MODEL,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.0,
    }

    try:
        response = requests.post(
            OPENROUTER_URL,
            headers=headers,
            json=payload,
            timeout=OPENROUTER_QUERY_TIMEOUT,
        )
        response.raise_for_status()
        raw = response.json()
        message = (
            raw.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
        )
        parsed = _extract_json(message)

        search_query = str(parsed.get("search_query", "")).strip() or query
        country = str(parsed.get("country", "")).strip().lower()
        must_have_terms = parsed.get("must_have_terms", [])
        exclude_terms = parsed.get("exclude_terms", [])

        if not isinstance(must_have_terms, list):
            must_have_terms = []
        if not isinstance(exclude_terms, list):
            exclude_terms = []

        must_have_terms = [
            str(x).strip().lower() for x in must_have_terms if str(x).strip()
        ][:8]
        exclude_terms = [
            str(x).strip().lower() for x in exclude_terms if str(x).strip()
        ][:12]

        return {
            "search_query": search_query,
            "country": country,
            "must_have_terms": must_have_terms,
            "exclude_terms": exclude_terms,
        }
    except Exception:
        return fallback
