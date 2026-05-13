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

SEARCH_JOBS = {}
SEARCH_JOBS_LOCK = threading.Lock()


@app.on_event("startup")
def ensure_indexes():
    try:
        leads_collection.create_index([("searched_query", 1), ("created_at", -1)])
        leads_collection.create_index([("website", 1)])
        leads_collection.create_index([("search_job_id", 1), ("result_index", 1)])
        leads_collection.create_index([("country_filter", 1), ("final_score", -1)])
        search_state_collection.create_index([("query", 1)], unique=True)
    except Exception as exc:
        # Keep API booting so local debugging is possible even if Mongo is unavailable.
        logger.warning("Index creation skipped on startup: %s", exc)


def _domain_from_url(url):
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _state_key(query, country_filter="", trusted_only=False):
    return f"{query.strip().lower()}|country={country_filter.strip().lower()}|trusted={bool(trusted_only)}"


def _existing_domains_for_query(query, country_filter=""):
    domains = set()
    filters = {
        "searched_query": query,
        "website": {"$exists": True, "$ne": ""},
    }
    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()

    cursor = leads_collection.find(
        filters,
        {"_id": 0, "website": 1},
    )

    for row in cursor:
        domain = _domain_from_url(row.get("website", ""))
        if domain:
            domains.add(domain)

    return domains


def _read_search_state(query):
    state = search_state_collection.find_one({"query": query}, {"_id": 0})
    if not state:
        return {"next_start": 0, "has_more": True}

    return {
        "next_start": int(state.get("next_start", 0)),
        "has_more": bool(state.get("has_more", True)),
    }


def _write_search_state(query, next_start, has_more):
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


def _upsert_job(job_id, **fields):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def _append_job_result(job_id, lead_doc):
    lead = dict(lead_doc)
    lead.pop("_id", None)

    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            return
        lead["result_index"] = len(job["results"])
        job["results"].append(lead)


def _run_discovery(
    query,
    continue_search=False,
    scan_all_remaining=False,
    search_job_id=None,
    country_filter="",
    trusted_only=False,
):
    query = query.strip()
    country_filter = (country_filter or "").strip().lower()
    state_key = _state_key(query, country_filter=country_filter, trusted_only=trusted_only)
    if not query:
        return {
            "saved": 0,
            "linkedin_saved": 0,
            "saved_total": 0,
            "has_more": False,
            "next_start": 0,
            "pages_scanned": 0,
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
            "saved": 0,
            "linkedin_saved": 0,
            "saved_total": 0,
            "has_more": False,
            "next_start": next_start,
            "pages_scanned": 0,
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
        result = google_search(
            query,
            max_results=DEFAULT_BATCH_RESULTS if scan_all_remaining else (DEFAULT_BATCH_RESULTS - saved),
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
            lead_doc = {
                "company": c.get("company"),
                "website": c.get("website"),
                "email": c.get("email"),
                "phone": c.get("phone"),
                "ai_summary": c.get("summary", ""),
                "products": c.get("products", []),
                "llm_relevant": c.get("llm_relevant"),
                "semantic_score": c.get("semantic_score", 0),
                "keyword_score": c.get("keyword_score", 0),
                "domain_authority": c.get("domain_authority", 0),
                "contact_presence": c.get("contact_presence", 0),
                "final_score": c.get("final_score", 0),
                "importance": c.get("importance", "low"),
                "country_match": c.get("country_match", 0),
                "company_recorder": c.get("company_recorder", []),
                "country_filter": country_filter,
                "searched_query": query,
                "source": "google_semantic",
                "created_at": datetime.utcnow(),
            }
            if search_job_id:
                lead_doc["search_job_id"] = search_job_id

            lead_docs.append(lead_doc)

            saved += 1

            domain = c.get("domain", "")
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

    # Keep LinkedIn discovery only on fresh search, not on continuation batches.
    if not continue_search:
        people = linkedin_discovery(query, country_filter=country_filter)
        linkedin_docs = []
        for p in people:
            lead_doc = {
                "name": p.get("name"),
                "profile": p.get("profile"),
                "snippet": p.get("snippet"),
                "country_filter": country_filter,
                "searched_query": query,
                "source": "linkedin_semantic",
                "created_at": datetime.utcnow(),
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
        "saved": saved,
        "linkedin_saved": linkedin_saved,
        "saved_total": saved + linkedin_saved,
        "has_more": has_more,
        "next_start": next_start,
        "pages_scanned": pages_scanned,
        "continue_search": continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter": country_filter,
        "trusted_only": trusted_only,
    }


def _run_discovery_job(
    job_id,
    query,
    continue_search,
    scan_all_remaining,
    country_filter,
    trusted_only,
):
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
        _upsert_job(
            job_id,
            status="completed",
            finished_at=datetime.utcnow(),
            **result,
        )
    except Exception as exc:
        _upsert_job(
            job_id,
            status="failed",
            finished_at=datetime.utcnow(),
            error=str(exc),
        )


@app.get("/")
def home():
    return {"status": "running", "service": "Global Lead Discovery"}


# ===============================
# Manual Lead Add
# ===============================
@app.post("/add_lead")
def add_lead(text: str, service_focus: str = "marketing"):
    service, country, urgency, budget = extract_fields(text)
    score = score_match(text, service_focus)

    lead = {
        "text": text,
        "service": service,
        "country": country,
        "urgency": urgency,
        "budget": budget if budget else 0,
        "score": score,
        "source": "manual",
        "created_at": datetime.utcnow(),
    }

    leads_collection.insert_one(lead)
    return {"status": "added"}


# ===============================
# DISCOVERY (sync mode)
# ===============================
@app.get("/discover")
def discover(
    query: str,
    continue_search: bool = False,
    scan_all_remaining: bool = False,
    country_filter: str = "",
    trusted_only: bool = False,
):
    return _run_discovery(
        query=query,
        continue_search=continue_search,
        scan_all_remaining=scan_all_remaining,
        country_filter=country_filter,
        trusted_only=trusted_only,
    )


# ===============================
# BACKGROUND SEARCH
# ===============================
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

    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id,
        "query": query,
        "status": "queued",
        "continue_search": continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter": country_filter,
        "trusted_only": trusted_only,
        "created_at": datetime.utcnow(),
        "started_at": None,
        "finished_at": None,
        "saved": 0,
        "linkedin_saved": 0,
        "saved_total": 0,
        "has_more": True,
        "next_start": 0,
        "pages_scanned": 0,
        "error": "",
        "results": [],
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
        "job_id": job_id,
        "status": "started",
        "query": query,
        "continue_search": continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter": country_filter,
        "trusted_only": trusted_only,
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
        "job_id": job_id,
        "results": items,
        "next_since": start_idx + len(items),
        "total": total,
    }


@app.get("/search/more-like-this/{job_id}")
def search_more_like_this(job_id: str, result_index: int, limit: int = 5):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        results = list(job.get("results", []))

    seed = None
    for row in results:
        if int(row.get("result_index", -1)) == int(result_index):
            seed = row
            break
    if not seed:
        raise HTTPException(status_code=404, detail="seed result not found")

    seed_text = " ".join(
        [
            seed.get("company", ""),
            seed.get("ai_summary", ""),
            " ".join(seed.get("products", []) if isinstance(seed.get("products"), list) else []),
        ]
    )

    scored = []
    for row in results:
        if row.get("source") == "linkedin_semantic":
            continue
        if int(row.get("result_index", -1)) == int(result_index):
            continue

        row_text = " ".join(
            [
                row.get("company", ""),
                row.get("ai_summary", ""),
                " ".join(row.get("products", []) if isinstance(row.get("products"), list) else []),
            ]
        )
        sim = max(0.0, float(semantic_similarity(seed_text, row_text)))
        blended = round((0.7 * sim) + (0.3 * float(row.get("final_score", 0) or 0)), 3)
        item = dict(row)
        item["similarity_score"] = round(sim, 3)
        item["more_like_this_score"] = blended
        scored.append(item)

    scored.sort(key=lambda x: x.get("more_like_this_score", 0), reverse=True)
    return {
        "job_id": job_id,
        "seed_result_index": int(result_index),
        "results": scored[: max(1, min(int(limit), 20))],
    }


# ===============================
# GET ALL LEADS
# ===============================
@app.get("/leads")
def get_leads(
    query: str = "",
    source: str = "",
    country_filter: str = "",
    min_score: float = 0.0,
    skip: int = 0,
    limit: int = 500,
):
    filters = {}
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

    sort_field = "final_score" if min_score > 0 else "created_at"
    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort(sort_field, -1)
        .skip(safe_skip)
        .limit(safe_limit)
    )
    return list(cursor)


# ===============================
# DEMO SEED
# ===============================
@app.get("/seed")
def seed():
    samples = [
        {
            "company": "Zenith Imports LLC",
            "email": "info@zenithimports.ae",
            "phone": "+971-4-555111",
            "searched_query": "importers in dubai",
            "source": "seed",
            "created_at": datetime.utcnow(),
        },
        {
            "company": "Falcon Trading",
            "email": "sales@falcontrading.ae",
            "phone": "+971-50-888777",
            "searched_query": "importers in dubai",
            "source": "seed",
            "created_at": datetime.utcnow(),
        },
        {
            "name": "Ahmed Khan - Import Manager",
            "profile": "https://linkedin.com/in/demo",
            "searched_query": "importers in dubai",
            "source": "seed",
            "created_at": datetime.utcnow(),
        },
    ]

    leads_collection.insert_many(samples)
    return {"status": "seeded"}


# ===============================
# CLEAR DATABASE
# ===============================
@app.delete("/clear")
def clear():
    leads_collection.delete_many({})
    search_state_collection.delete_many({})
    with SEARCH_JOBS_LOCK:
        SEARCH_JOBS.clear()
    return {"status": "cleared"}
