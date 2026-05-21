"""
backend/main.py  –  Fixed version
Changes vs original:
  1. Broken /discover endpoint removed (referenced non-existent smart_google_search import)
  2. All fields produced by scraper_google.py now correctly mapped (summary → ai_summary)
  3. country_match field populated properly
  4. _run_discovery correctly passes search_job_id to linkedin docs
  5. Logging added throughout
  6. /leads endpoint default limit raised; sort always by final_score when available
  7. Minor: SEARCH_JOBS memory leak guard (cap at 200 jobs)
"""

from datetime import datetime
from urllib.parse import urlparse
import threading
import uuid
import logging

from fastapi import FastAPI, HTTPException

if __package__:
    from .database import leads_collection, search_state_collection
    from .nlp import extract_fields, score_match, semantic_similarity
    from .scraper_google import google_search, linkedin_discovery
else:
    from database import leads_collection, search_state_collection
    from nlp import extract_fields, score_match, semantic_similarity
    from scraper_google import google_search, linkedin_discovery

app = FastAPI(title="Global B2B Lead Discovery API")
logger = logging.getLogger("uvicorn.error")

DEFAULT_BATCH_RESULTS = 10
MAX_SEARCH_PAGES_PER_REQUEST = 100
MAX_JOBS_IN_MEMORY = 200          # evict oldest jobs when cap is exceeded

SEARCH_JOBS: dict = {}
SEARCH_JOBS_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def ensure_indexes():
    try:
        leads_collection.create_index([("searched_query", 1), ("created_at", -1)])
        leads_collection.create_index([("website", 1)])
        leads_collection.create_index([("search_job_id", 1), ("result_index", 1)])
        leads_collection.create_index([("country_filter", 1), ("final_score", -1)])
        search_state_collection.create_index([("query", 1)], unique=True)
        logger.info("MongoDB indexes ensured.")
    except Exception as exc:
        logger.warning("Index creation skipped on startup: %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _state_key(query: str, country_filter: str = "", trusted_only: bool = False) -> str:
    return (
        f"{query.strip().lower()}"
        f"|country={country_filter.strip().lower()}"
        f"|trusted={bool(trusted_only)}"
    )


def _existing_domains_for_query(query: str, country_filter: str = "") -> set:
    domains: set = set()
    filters: dict = {
        "searched_query": query,
        "website": {"$exists": True, "$ne": ""},
    }
    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()

    for row in leads_collection.find(filters, {"_id": 0, "website": 1}):
        domain = _domain_from_url(row.get("website", ""))
        if domain:
            domains.add(domain)

    return domains


def _read_search_state(query: str) -> dict:
    state = search_state_collection.find_one({"query": query}, {"_id": 0})
    if not state:
        return {"next_start": 0, "has_more": True}
    return {
        "next_start": int(state.get("next_start", 0)),
        "has_more": bool(state.get("has_more", True)),
    }


def _write_search_state(query: str, next_start: int, has_more: bool) -> None:
    search_state_collection.update_one(
        {"query": query},
        {
            "$set": {
                "query": query,
                "next_start": int(next_start),
                "has_more": bool(has_more),
                "updated_at": datetime.utcnow(),
            }
        },
        upsert=True,
    )


def _upsert_job(job_id: str, **fields) -> None:
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def _append_job_result(job_id: str, lead_doc: dict) -> None:
    lead = dict(lead_doc)
    lead.pop("_id", None)
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            return
        lead["result_index"] = len(job["results"])
        job["results"].append(lead)


def _evict_old_jobs() -> None:
    """Remove oldest completed/failed jobs when cap is reached."""
    with SEARCH_JOBS_LOCK:
        if len(SEARCH_JOBS) < MAX_JOBS_IN_MEMORY:
            return
        done = [
            (jid, j["created_at"])
            for jid, j in SEARCH_JOBS.items()
            if j.get("status") in ("completed", "failed")
        ]
        done.sort(key=lambda x: x[1])
        for jid, _ in done[: len(done) // 2]:
            del SEARCH_JOBS[jid]


# ---------------------------------------------------------------------------
# Core discovery logic
# ---------------------------------------------------------------------------

def _run_discovery(
    query: str,
    continue_search: bool = False,
    scan_all_remaining: bool = False,
    search_job_id: str | None = None,
    country_filter: str = "",
    trusted_only: bool = False,
) -> dict:
    query = query.strip()
    country_filter = (country_filter or "").strip().lower()
    state_key = _state_key(query, country_filter=country_filter, trusted_only=trusted_only)

    if not query:
        return {
            "saved": 0, "linkedin_saved": 0, "saved_total": 0,
            "has_more": False, "next_start": 0, "pages_scanned": 0,
            "continue_search": continue_search,
            "scan_all_remaining": scan_all_remaining,
            "country_filter": country_filter,
            "trusted_only": trusted_only,
        }

    if continue_search:
        state = _read_search_state(state_key)
        next_start = state["next_start"]
        has_more = state["has_more"]
    else:
        next_start = 0
        has_more = True
        _write_search_state(state_key, next_start=0, has_more=True)

    if continue_search and not has_more:
        return {
            "saved": 0, "linkedin_saved": 0, "saved_total": 0,
            "has_more": False, "next_start": next_start, "pages_scanned": 0,
            "continue_search": True,
            "scan_all_remaining": scan_all_remaining,
            "message": "No more pages left for this query.",
            "country_filter": country_filter,
            "trusted_only": trusted_only,
        }

    known_domains = _existing_domains_for_query(query, country_filter=country_filter)
    saved = 0
    pages_scanned = 0
    linkedin_saved = 0
    guard = 0

    while has_more and (scan_all_remaining or saved < DEFAULT_BATCH_RESULTS):
        want = DEFAULT_BATCH_RESULTS if scan_all_remaining else (DEFAULT_BATCH_RESULTS - saved)

        result = google_search(
            query,
            max_results=want,
            start=next_start,
            exclude_domains=known_domains,
            max_pages=1,
            country_filter=country_filter,
            trusted_only=trusted_only,
        )

        companies = result.get("companies", [])
        next_start = int(result.get("next_start", next_start))
        has_more = bool(result.get("has_more", False))
        pages_scanned += int(result.get("pages_scanned", 0))

        effective_country = (result.get("effective_country", "") or country_filter).strip().lower()
        if not country_filter and effective_country:
            country_filter = effective_country

        lead_docs = []
        for c in companies:
            # Detect country match
            country_match = 0
            if country_filter:
                combined = " ".join([
                    str(c.get("company", "")),
                    str(c.get("website", "")),
                    str(c.get("summary", "")),
                    str(c.get("snippet", "")),
                ]).lower()
                country_match = 1 if country_filter in combined else 0

            # Pull compliance data written by cert_checker during enrichment
            compliance      = c.get("compliance", {})
            compliance_gaps = compliance.get("compliance_gaps", [])

            lead_doc = {
                "company":           c.get("company", ""),
                "website":           c.get("website", ""),
                "email":             c.get("email", ""),
                "phone":             c.get("phone", ""),
                "ai_summary":        c.get("summary", ""),
                "products":          c.get("products", []),
                "llm_relevant":      c.get("llm_relevant"),
                "semantic_score":    c.get("semantic_score", 0.0),
                "keyword_score":     c.get("keyword_score", 0.0),
                "domain_authority":  c.get("domain_authority", 0.0),
                "contact_presence":  c.get("contact_presence", 0.0),
                "final_score":       c.get("final_score", 0.0),
                "importance":        c.get("importance", "low"),
                "country_match":     country_match,
                "country_filter":    country_filter,
                "searched_query":    query,
                "source":            "google_semantic",
                "created_at":        datetime.utcnow(),
                # --- compliance fields ---
                "compliance_gaps":   compliance_gaps,
                "compliance_score":  compliance.get("compliance_score", 1.0),
                "bis_certified":     compliance.get("bis",  {}).get("certified",  None),
                "gst_registered":    compliance.get("gst",  {}).get("registered", None),
                "iec_found":         compliance.get("dgft", {}).get("iec_found",  None),
                "mca_active":        compliance.get("mca",  {}).get("active",     None),
                "bis_detail":        compliance.get("bis",  {}).get("detail",     ""),
                "gst_detail":        compliance.get("gst",  {}).get("detail",     ""),
                "dgft_detail":       compliance.get("dgft", {}).get("detail",     ""),
                "mca_detail":        compliance.get("mca",  {}).get("detail",     ""),
                "compliance_checked": any(
                    v.get("checked") for v in [
                        compliance.get("bis",  {}),
                        compliance.get("gst",  {}),
                        compliance.get("dgft", {}),
                        compliance.get("mca",  {}),
                    ]
                ),
            }
            if search_job_id:
                lead_doc["search_job_id"] = search_job_id

            lead_docs.append(lead_doc)
            saved += 1

            domain = c.get("domain", "") or _domain_from_url(c.get("website", ""))
            if domain:
                known_domains.add(domain)

        if lead_docs:
            leads_collection.insert_many(lead_docs)
            if search_job_id:
                for lead_doc in lead_docs:
                    _append_job_result(search_job_id, lead_doc)

        guard += 1
        if guard >= MAX_SEARCH_PAGES_PER_REQUEST:
            has_more = False
            break

    # LinkedIn – only on fresh (non-continue) searches
    if not continue_search:
        people = linkedin_discovery(query, country_filter=country_filter)
        linkedin_docs = []
        for p in people:
            lead_doc = {
                "name":           p.get("name", ""),
                "profile":        p.get("profile", ""),
                "snippet":        p.get("snippet", ""),
                "country_filter": country_filter,
                "searched_query": query,
                "source":         "linkedin_semantic",
                "created_at":     datetime.utcnow(),
            }
            if search_job_id:
                lead_doc["search_job_id"] = search_job_id

            linkedin_docs.append(lead_doc)
            linkedin_saved += 1

        if linkedin_docs:
            leads_collection.insert_many(linkedin_docs)
            if search_job_id:
                for lead_doc in linkedin_docs:
                    _append_job_result(search_job_id, lead_doc)

    _write_search_state(state_key, next_start=next_start, has_more=has_more)

    return {
        "saved":              saved,
        "linkedin_saved":     linkedin_saved,
        "saved_total":        saved + linkedin_saved,
        "has_more":           has_more,
        "next_start":         next_start,
        "pages_scanned":      pages_scanned,
        "continue_search":    continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter":     country_filter,
        "trusted_only":       trusted_only,
    }


def _run_discovery_job(
    job_id: str,
    query: str,
    continue_search: bool,
    scan_all_remaining: bool,
    country_filter: str,
    trusted_only: bool,
) -> None:
    _upsert_job(job_id, status="running", started_at=datetime.utcnow())
    try:
        result = _run_discovery(
            query=query,
            continue_search=continue_search,
            scan_all_remaining=scan_all_remaining,
            search_job_id=job_id,
            country_filter=country_filter,
            trusted_only=trusted_only,
        )
        _upsert_job(job_id, status="completed", finished_at=datetime.utcnow(), **result)
        logger.info("Job %s completed: saved=%s", job_id, result.get("saved_total"))
    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        _upsert_job(job_id, status="failed", finished_at=datetime.utcnow(), error=str(exc))


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------


@app.get("/llm/provider")
def llm_provider_info():
    """Returns which LLM provider is currently active."""
    try:
        from llm import get_active_provider
    except ImportError:
        from .llm import get_active_provider
    return get_active_provider()

@app.get("/")
def home():
    return {"status": "running", "service": "Global Lead Discovery"}


@app.post("/add_lead")
def add_lead(text: str, service_focus: str = "marketing"):
    service, country, urgency, budget = extract_fields(text)
    match_score = score_match(text, service_focus)

    lead = {
        "text":       text,
        "service":    service,
        "country":    country,
        "urgency":    urgency,
        "budget":     budget if budget else 0,
        "score":      match_score,
        "source":     "manual",
        "created_at": datetime.utcnow(),
    }
    leads_collection.insert_one(lead)
    return {"status": "added"}


# ---- Background search ----

@app.post("/search/start")
def start_search(
    query: str,
    continue_search: bool = False,
    scan_all_remaining: bool = False,
    country_filter: str = "",
    trusted_only: bool = False,
):
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")

    country_filter = (country_filter or "").strip().lower()
    _evict_old_jobs()

    job_id = uuid.uuid4().hex
    job = {
        "job_id":             job_id,
        "query":              query,
        "status":             "queued",
        "continue_search":    continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter":     country_filter,
        "trusted_only":       trusted_only,
        "created_at":         datetime.utcnow(),
        "started_at":         None,
        "finished_at":        None,
        "saved":              0,
        "linkedin_saved":     0,
        "saved_total":        0,
        "has_more":           True,
        "next_start":         0,
        "pages_scanned":      0,
        "error":              "",
        "results":            [],
    }

    with SEARCH_JOBS_LOCK:
        SEARCH_JOBS[job_id] = job

    worker = threading.Thread(
        target=_run_discovery_job,
        args=(job_id, query, continue_search, scan_all_remaining, country_filter, trusted_only),
        daemon=True,
    )
    worker.start()

    return {
        "job_id":             job_id,
        "status":             "started",
        "query":              query,
        "continue_search":    continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter":     country_filter,
        "trusted_only":       trusted_only,
    }


@app.get("/search/status/{job_id}")
def search_status(job_id: str):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        payload = {k: v for k, v in job.items() if k != "results"}
        payload["results_count"] = len(job["results"])

    payload["ask_continue"] = bool(
        payload.get("status") == "completed" and payload.get("has_more")
    )
    return payload


@app.get("/search/results/{job_id}")
def search_results(job_id: str, since: int = 0):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        total = len(job["results"])
        start_idx = max(0, min(int(since), total))
        items = job["results"][start_idx:]

    return {
        "job_id":     job_id,
        "results":    items,
        "next_since": start_idx + len(items),
        "total":      total,
    }


@app.get("/search/more-like-this/{job_id}")
def search_more_like_this(job_id: str, result_index: int, limit: int = 5):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        results = list(job.get("results", []))

    seed = next(
        (r for r in results if int(r.get("result_index", -1)) == int(result_index)),
        None,
    )
    if not seed:
        raise HTTPException(status_code=404, detail="seed result not found")

    seed_text = " ".join(filter(None, [
        seed.get("company", ""),
        seed.get("ai_summary", ""),
        " ".join(seed.get("products", []) if isinstance(seed.get("products"), list) else []),
    ]))

    scored = []
    for row in results:
        if row.get("source") == "linkedin_semantic":
            continue
        if int(row.get("result_index", -1)) == int(result_index):
            continue

        row_text = " ".join(filter(None, [
            row.get("company", ""),
            row.get("ai_summary", ""),
            " ".join(row.get("products", []) if isinstance(row.get("products"), list) else []),
        ]))

        sim = max(0.0, float(semantic_similarity(seed_text, row_text)))
        blended = round((0.7 * sim) + (0.3 * float(row.get("final_score", 0) or 0)), 3)
        item = dict(row)
        item["similarity_score"] = round(sim, 3)
        item["more_like_this_score"] = blended
        scored.append(item)

    scored.sort(key=lambda x: x.get("more_like_this_score", 0), reverse=True)
    return {
        "job_id":            job_id,
        "seed_result_index": int(result_index),
        "results":           scored[: max(1, min(int(limit), 20))],
    }


# ---- Leads read ----

@app.get("/leads")
def get_leads(
    query: str = "",
    source: str = "",
    country_filter: str = "",
    min_score: float = 0.0,
    skip: int = 0,
    limit: int = 1000,
):
    filters: dict = {}
    if query:
        filters["searched_query"] = query
    if source:
        filters["source"] = source
    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()
    if min_score > 0:
        filters["final_score"] = {"$gte": float(min_score)}

    safe_skip = max(0, int(skip))
    safe_limit = max(1, min(int(limit), 2000))

    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort("final_score", -1)
        .skip(safe_skip)
        .limit(safe_limit)
    )
    return list(cursor)



@app.post("/leads/enrich-compliance")
def enrich_compliance_background(limit: int = 50, country_filter: str = ""):
    """
    Background task: runs cert_checker on leads that haven't been compliance-checked yet.
    Call this after a search completes — it won't slow down the search itself.
    """
    try:
        from cert_checker import check_company_compliance
    except ImportError:
        from .cert_checker import check_company_compliance

    filters: dict = {
        "source":             {"$ne": "linkedin_semantic"},
        "compliance_checked": {"$ne": True},
        "company":            {"$exists": True, "$ne": ""},
    }
    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()

    leads = list(
        leads_collection.find(filters, {"_id": 1, "company": 1, "website": 1})
        .limit(max(1, min(int(limit), 200)))
    )

    def _run(lead):
        compliance      = check_company_compliance(
            lead.get("company", ""), lead.get("website", ""))
        compliance_gaps = compliance.get("compliance_gaps", [])
        leads_collection.update_one(
            {"_id": lead["_id"]},
            {"$set": {
                "compliance_gaps":   compliance_gaps,
                "compliance_score":  compliance.get("compliance_score", 1.0),
                "bis_certified":     compliance.get("bis",  {}).get("certified",  None),
                "gst_registered":    compliance.get("gst",  {}).get("registered", None),
                "iec_found":         compliance.get("dgft", {}).get("iec_found",  None),
                "mca_active":        compliance.get("mca",  {}).get("active",     None),
                "bis_detail":        compliance.get("bis",  {}).get("detail",     ""),
                "gst_detail":        compliance.get("gst",  {}).get("detail",     ""),
                "dgft_detail":       compliance.get("dgft", {}).get("detail",     ""),
                "mca_detail":        compliance.get("mca",  {}).get("detail",     ""),
                "compliance_checked": True,
            }}
        )

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(_run, leads))

    return {"status": "done", "checked": len(leads)}


# ---- Compliance gap filter ----

@app.get("/leads/gaps")
def get_leads_with_gaps(
    gap: str = "",
    country_filter: str = "",
    min_score: float = 0.0,
    importance: str = "",
    skip: int = 0,
    limit: int = 1000,
):
    """
    Return only leads that have compliance gaps.

    gap (optional): filter to a specific gap code
        no_bis | no_gst | no_iec | mca_not_found | mca_inactive
    If gap is empty, returns all leads that have at least one gap.
    """
    filters: dict = {
        "source": {"$ne": "linkedin_semantic"},
        "compliance_checked": True,
        "compliance_gaps":    {"$exists": True, "$not": {"$size": 0}},
    }

    if gap:
        filters["compliance_gaps"] = gap.strip()

    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()

    if min_score > 0:
        filters["final_score"] = {"$gte": float(min_score)}

    if importance:
        filters["importance"] = importance.strip().lower()

    safe_skip  = max(0, int(skip))
    safe_limit = max(1, min(int(limit), 2000))

    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort([("compliance_score", 1), ("final_score", -1)])
        .skip(safe_skip)
        .limit(safe_limit)
    )
    return list(cursor)


@app.get("/leads/gap-summary")
def gap_summary(country_filter: str = ""):
    """
    Returns counts of each gap type across all checked leads.
    Useful for the dashboard summary cards.
    """
    filters: dict = {
        "source":             {"$ne": "linkedin_semantic"},
        "compliance_checked": True,
    }
    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()

    pipeline = [
        {"$match": filters},
        {"$unwind": {"path": "$compliance_gaps", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$compliance_gaps", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]

    rows = list(leads_collection.aggregate(pipeline))
    return {r["_id"]: r["count"] for r in rows}


@app.post("/leads/recheck/{lead_id}")
def recheck_lead(lead_id: str):
    """
    Re-run compliance checks for a single lead by its website field.
    Useful when portal data changes or a check previously timed out.
    """
    from bson import ObjectId
    try:
        oid = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")

    lead = leads_collection.find_one({"_id": oid})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")

    try:
        from cert_checker import check_company_compliance
    except ImportError:
        from .cert_checker import check_company_compliance

    compliance = check_company_compliance(
        lead.get("company", ""),
        lead.get("website", ""),
    )
    compliance_gaps = compliance.get("compliance_gaps", [])

    update = {
        "compliance_gaps":    compliance_gaps,
        "compliance_score":   compliance.get("compliance_score", 1.0),
        "bis_certified":      compliance.get("bis",  {}).get("certified",  None),
        "gst_registered":     compliance.get("gst",  {}).get("registered", None),
        "iec_found":          compliance.get("dgft", {}).get("iec_found",  None),
        "mca_active":         compliance.get("mca",  {}).get("active",     None),
        "bis_detail":         compliance.get("bis",  {}).get("detail",     ""),
        "gst_detail":         compliance.get("gst",  {}).get("detail",     ""),
        "dgft_detail":        compliance.get("dgft", {}).get("detail",     ""),
        "mca_detail":         compliance.get("mca",  {}).get("detail",     ""),
        "compliance_checked": True,
    }

    leads_collection.update_one({"_id": oid}, {"$set": update})
    return {"status": "rechecked", "compliance_gaps": compliance_gaps}


# ---- Utilities ----

@app.get("/seed")
def seed():
    samples = [
        {
            "company":       "Zenith Imports LLC",
            "email":         "info@zenithimports.ae",
            "phone":         "+971-4-555111",
            "final_score":   0.75,
            "importance":    "high",
            "searched_query": "importers in dubai",
            "source":        "seed",
            "created_at":    datetime.utcnow(),
        },
        {
            "company":       "Falcon Trading",
            "email":         "sales@falcontrading.ae",
            "phone":         "+971-50-888777",
            "final_score":   0.65,
            "importance":    "medium",
            "searched_query": "importers in dubai",
            "source":        "seed",
            "created_at":    datetime.utcnow(),
        },
        {
            "name":          "Ahmed Khan - Import Manager",
            "profile":       "https://linkedin.com/in/demo",
            "searched_query": "importers in dubai",
            "source":        "seed",
            "created_at":    datetime.utcnow(),
        },
    ]
    leads_collection.insert_many(samples)
    return {"status": "seeded", "count": len(samples)}


@app.delete("/clear")
def clear():
    leads_collection.delete_many({})
    search_state_collection.delete_many({})
    with SEARCH_JOBS_LOCK:
        SEARCH_JOBS.clear()
    return {"status": "cleared"}