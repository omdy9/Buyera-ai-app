"""
ai_assistant.py — Conversational lead-research assistant
==========================================================
Two responsibilities:

1. Adaptive questioning
   generate_next_question() looks at the conversation so far and either
   asks one more clarifying question, or returns {"ready": true, "brief": {...}}
   once it has enough to search (industry, location, channel type at minimum).

2. Strict verified-only research
   run_verified_research() runs the existing discovery pipeline
   (google_search → enrich_company) and then re-filters every candidate
   through verifier.verify_email / verify_phone. Only leads where the
   email is deliverable (score >= 70) AND the phone is valid survive.

Both pieces degrade gracefully: if no LLM provider is available, the
question flow falls back to a fixed checklist instead of failing.
"""

import re
import json
import logging
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from .llm import _call_llm, _get_provider, _extract_json
    from .scraper_google import google_search
    from .verifier import verify_email, verify_phone
    from .cert_checker import check_company_compliance
except ImportError:
    from llm import _call_llm, _get_provider, _extract_json
    from scraper_google import google_search
    from verifier import verify_email, verify_phone
    from cert_checker import check_company_compliance

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Required fields before we're willing to search
# ---------------------------------------------------------------------------
REQUIRED_BRIEF_FIELDS = ["industry_or_service", "location", "channel_type"]

# Fixed fallback checklist — used only if no LLM provider is reachable
_FALLBACK_QUESTIONS = [
    {"field": "industry_or_service", "question": "What kind of business or service are you looking for? (e.g. \"LED lighting manufacturers\", \"GST consultants\")"},
    {"field": "location",            "question": "Which city, state, or country should I focus on?"},
    {"field": "channel_type",        "question": "Are you looking for Manufacturers, Importers, Distributors, Wholesalers, Traders, or Retailers? (or 'any')"},
    {"field": "company_size",        "question": "Any preference on company size? (e.g. small/SME, mid-size, large — or 'no preference')"},
]


_QUESTION_PROMPT = """\
You are a B2B lead-research assistant helping a salesperson define exactly what
companies they want to find, before an expensive verified-contact search runs.

Conversation so far (question/answer pairs):
{history}

Required information before we can search:
- industry_or_service: what the company does / what the user is selling to them
- location: city, state, or country to focus on
- channel_type: Manufacturer / Importer / Distributor / Wholesaler / Trader / Retailer / any

Optional but useful: company_size, budget_sensitivity, urgency, specific_compliance_needs.

Rules:
- Ask ONE question at a time, conversational and short.
- Do not re-ask something already answered.
- Once all REQUIRED fields are known (even loosely), stop asking and return ready=true.
- Don't ask more than 6 questions total even if optional fields are missing.

Return ONLY valid JSON in exactly this shape:
{{
  "ready": false,
  "question": "your next question here",
  "field": "which field this question targets",
  "brief_so_far": {{"industry_or_service": "...", "location": "...", "channel_type": "...", "company_size": "...", "urgency": "...", "specific_compliance_needs": "..."}}
}}

OR, once ready:
{{
  "ready": true,
  "question": "",
  "field": "",
  "brief_so_far": {{"industry_or_service": "...", "location": "...", "channel_type": "...", "company_size": "...", "urgency": "...", "specific_compliance_needs": "..."}}
}}

Leave any field blank ("") if not yet known.
"""


def _format_history(history: list) -> str:
    lines = []
    for turn in history:
        q = turn.get("question", "")
        a = turn.get("answer", "")
        if q:
            lines.append(f"Q: {q}")
        if a:
            lines.append(f"A: {a}")
    return "\n".join(lines) if lines else "(nothing yet — this is the first question)"


def _fallback_next_question(history: list) -> dict:
    """Fixed-checklist fallback when no LLM provider is available."""
    answered_fields = {turn.get("field") for turn in history if turn.get("answer")}
    brief = {}
    for turn in history:
        if turn.get("field") and turn.get("answer"):
            brief[turn["field"]] = turn["answer"]

    for q in _FALLBACK_QUESTIONS:
        if q["field"] not in answered_fields:
            return {
                "ready": False,
                "question": q["question"],
                "field": q["field"],
                "brief_so_far": brief,
            }

    return {"ready": True, "question": "", "field": "", "brief_so_far": brief}


def generate_next_question(history: list) -> dict:
    """
    history: list of {"question": str, "answer": str, "field": str}
    Returns: {"ready": bool, "question": str, "field": str, "brief_so_far": dict}
    """
    pname, _ = _get_provider("deepseek")
    if not pname:
        pname, _ = _get_provider("openrouter")
    if not pname:
        logger.info("No LLM provider available — using fixed question checklist")
        return _fallback_next_question(history)

    prompt = _QUESTION_PROMPT.format(history=_format_history(history))
    try:
        text   = _call_llm([{"role": "user", "content": prompt}],
                           provider_name=pname, max_tokens=400, temperature=0.3)
        result = _extract_json(text)

        brief = result.get("brief_so_far", {}) or {}
        ready = bool(result.get("ready", False))

        # Safety net: never trust "ready" blindly — confirm required fields
        # actually have non-empty values before accepting it.
        if ready:
            missing = [f for f in REQUIRED_BRIEF_FIELDS if not str(brief.get(f, "")).strip()]
            if missing:
                ready = False

        return {
            "ready":        ready,
            "question":     str(result.get("question", "") or ""),
            "field":        str(result.get("field", "") or ""),
            "brief_so_far": brief,
        }
    except Exception as exc:
        logger.warning("Adaptive question generation failed: %s — falling back to checklist", exc)
        return _fallback_next_question(history)


def build_search_query(brief: dict) -> str:
    """Turn a completed brief into a single search query string."""
    parts = [
        str(brief.get("industry_or_service", "")).strip(),
        str(brief.get("channel_type", "")).strip() if brief.get("channel_type", "").lower() != "any" else "",
        str(brief.get("location", "")).strip(),
    ]
    return " ".join(p for p in parts if p)


# ---------------------------------------------------------------------------
# Strict verified-only research
# ---------------------------------------------------------------------------

def _verify_contact_strict(company: dict) -> dict:
    """
    Run email + phone verification. Returns the verification results
    and a single boolean: did this lead pass the strict gate?
    Gate: email deliverable (score >= 70) AND phone valid.
    """
    email = company.get("email", "")
    phone = company.get("phone", "")

    email_result = verify_email(email) if email else {"score": 0, "verdict": "missing"}
    phone_result = verify_phone(phone) if phone else {"score": 0, "verdict": "missing"}

    email_ok = email_result.get("score", 0) >= 70
    phone_ok = phone_result.get("verdict") == "valid"

    return {
        "email_verification": email_result,
        "phone_verification": phone_result,
        "passes_strict_gate": bool(email_ok and phone_ok),
    }


def _enrich_compliance(company: dict) -> dict:
    try:
        compliance = check_company_compliance(
            company.get("company", ""), company.get("website", ""))
        company["compliance_gaps"]  = compliance.get("compliance_gaps", [])
        company["compliance_score"] = compliance.get("compliance_score", 1.0)
        mca = compliance.get("mca", {})
        company["bis_certified"]  = compliance.get("bis", {}).get("certified")
        company["gst_registered"] = compliance.get("gst", {}).get("registered")
        company["iec_found"]      = compliance.get("dgft", {}).get("iec_found")
        company["mca_active"]     = mca.get("active")
    except Exception as exc:
        logger.warning("Compliance check failed for %s: %s", company.get("company"), exc)
    return company


def run_verified_research(brief: dict, progress_cb=None, run_compliance: bool = True) -> dict:
    """
    Full pipeline: search → enrich (existing) → strict contact verification
    → compliance (optional) → return ONLY leads that pass the strict gate.

    progress_cb(stage: str, detail: dict) — optional callback for live status.
    """
    query          = build_search_query(brief)
    country_filter = str(brief.get("location", "")).strip().lower()
    channel        = str(brief.get("channel_type", "")).strip()

    if progress_cb:
        progress_cb("searching", {"query": query})

    search_result = google_search(
        query=query,
        max_results=25,
        country_filter=country_filter,
        quality_threshold=1,
    )
    candidates = search_result.get("companies", [])

    if channel and channel.lower() != "any":
        candidates = [c for c in candidates
                      if str(c.get("channel_type", "")).lower() == channel.lower()] or candidates

    if progress_cb:
        progress_cb("found_candidates", {"count": len(candidates)})

    verified = []
    rejected = []

    def _process(c):
        check = _verify_contact_strict(c)
        c.update(check)
        if check["passes_strict_gate"]:
            if run_compliance:
                _enrich_compliance(c)
            return ("verified", c)
        return ("rejected", c)

    with ThreadPoolExecutor(max_workers=6) as ex:
        futures = {ex.submit(_process, c): c for c in candidates}
        done = 0
        for future in as_completed(futures, timeout=180):
            try:
                status, c = future.result(timeout=60)
                if status == "verified":
                    verified.append(c)
                else:
                    rejected.append(c)
            except Exception as exc:
                logger.warning("Verification failed for candidate: %s", exc)
                rejected.append(futures[future])
            done += 1
            if progress_cb:
                progress_cb("verifying", {"done": done, "total": len(candidates),
                                          "verified_so_far": len(verified)})

    verified.sort(key=lambda x: x.get("final_score", 0), reverse=True)

    if progress_cb:
        progress_cb("done", {"verified": len(verified), "rejected": len(rejected),
                             "total_candidates": len(candidates)})

    return {
        "brief":            brief,
        "query_used":       query,
        "total_candidates": len(candidates),
        "verified_count":   len(verified),
        "rejected_count":   len(rejected),
        "verified_leads":   verified,
        "generated_at":     datetime.utcnow().isoformat(),
    }
