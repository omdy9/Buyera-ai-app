"""
backend/main.py  –  v3  (per-user lead isolation)
==================================================
"""

from datetime import datetime
from urllib.parse import urlparse
import threading
import uuid
import logging

from fastapi import FastAPI, HTTPException, Depends, Header
from pydantic import BaseModel

if __package__:
    from .database import leads_collection, search_state_collection
    from .nlp import extract_fields, score_match, semantic_similarity
    from .scraper_google import google_search, linkedin_discovery
    from .auth import (
        register_user, login_user, get_current_user,
        get_optional_user, create_token,
    )
else:
    from database import leads_collection, search_state_collection
    from nlp import extract_fields, score_match, semantic_similarity
    from scraper_google import google_search, linkedin_discovery
    from auth import (
        register_user, login_user, get_current_user,
        get_optional_user, create_token,
    )

app = FastAPI(title="Global B2B Lead Discovery API")
logger = logging.getLogger("uvicorn.error")

DEFAULT_BATCH_RESULTS        = 10
MAX_SEARCH_PAGES_PER_REQUEST = 100
MAX_JOBS_IN_MEMORY           = 200

SEARCH_JOBS: dict = {}
SEARCH_JOBS_LOCK  = threading.Lock()

ANONYMOUS = "anonymous"


# ---------------------------------------------------------------------------
# Pydantic request bodies
# ---------------------------------------------------------------------------

class RegisterRequest(BaseModel):
    username: str
    password: str
    email:    str = ""

class LoginRequest(BaseModel):
    username: str
    password: str


# ---------------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------------

@app.on_event("startup")
def ensure_indexes():
    # Drop ALL old conflicting indexes first
    for idx in ["query_1", "user_id_1_query_1"]:
        try:
            search_state_collection.drop_index(idx)
            logger.info("Dropped old index: %s", idx)
        except Exception:
            pass  # already gone, fine

    # Clean up any old documents with null fields
    try:
        deleted = search_state_collection.delete_many(
            {"$or": [
                {"user_id": None},
                {"query": None},
                {"state_key": {"$exists": False}},
            ]}
        )
        if deleted.deleted_count:
            logger.info("Cleaned %d bad search_state docs", deleted.deleted_count)
    except Exception as exc:
        logger.warning("Cleanup failed: %s", exc)

    try:
        leads_collection.create_index([("user_id", 1), ("searched_query", 1), ("created_at", -1)])
        leads_collection.create_index([("user_id", 1), ("website", 1)])
        leads_collection.create_index([("user_id", 1), ("final_score", -1)])
        leads_collection.create_index([("search_job_id", 1), ("result_index", 1)])
        leads_collection.create_index([("user_id", 1), ("channel_type", 1)])
        leads_collection.create_index([("user_id", 1), ("industry_detected", 1)])
        leads_collection.create_index([("user_id", 1), ("city", 1)])
        # Use state_key as the unique field — never null
        search_state_collection.create_index("state_key", unique=True)
        logger.info("MongoDB indexes ensured.")
    except Exception as exc:
        logger.warning("Index creation skipped: %s", exc)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _domain_from_url(url: str) -> str:
    try:
        return urlparse(url).netloc.lower().replace("www.", "")
    except Exception:
        return ""


def _state_key(query: str, country_filter: str = "",
               trusted_only: bool = False, user_id: str = "") -> str:
    return (
        f"{user_id}|{query.strip().lower()}"
        f"|country={country_filter.strip().lower()}"
        f"|trusted={bool(trusted_only)}"
    )


def _existing_domains_for_query(query: str, country_filter: str = "",
                                user_id: str = ANONYMOUS) -> set:
    domains: set = set()
    filters: dict = {
        "user_id":        user_id,
        "searched_query": query,
        "website":        {"$exists": True, "$ne": ""},
    }
    if country_filter:
        filters["country_filter"] = country_filter.strip().lower()
    for row in leads_collection.find(filters, {"_id": 0, "website": 1}):
        domain = _domain_from_url(row.get("website", ""))
        if domain:
            domains.add(domain)
    return domains


def _read_search_state(state_key: str) -> dict:
    state = search_state_collection.find_one({"state_key": state_key}, {"_id": 0})
    if not state:
        return {"next_start": 0, "has_more": True}
    return {"next_start": int(state.get("next_start", 0)),
            "has_more":   bool(state.get("has_more", True))}


def _write_search_state(state_key: str, next_start: int, has_more: bool) -> None:
    if not state_key:
        return
    search_state_collection.update_one(
        {"state_key": state_key},
        {"$set": {
            "state_key":  state_key,
            "next_start": int(next_start),
            "has_more":   bool(has_more),
            "updated_at": datetime.utcnow(),
        }},
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

def _build_lead_doc(c: dict, query: str, country_filter: str,
                    user_id: str = ANONYMOUS,
                    search_job_id: str | None = None) -> dict:
    country_match = 0
    if country_filter:
        combined = " ".join([
            str(c.get("company", "")),
            str(c.get("website", "")),
            str(c.get("summary", "")),
            str(c.get("snippet", "")),
            str(c.get("country_detected", "")),
        ]).lower()
        country_match = 1 if country_filter in combined else 0

    compliance      = c.get("compliance", {})
    compliance_gaps = compliance.get("compliance_gaps", [])
    mca             = compliance.get("mca", {})
    incorporation_date = (
        c.get("incorporation_date", "") or mca.get("incorporation_date", "")
    )
    company_type_mca = mca.get("company_type", "")

    doc = {
        "user_id":            user_id,
        "company":            c.get("company", ""),
        "website":            c.get("website", ""),
        "active_website":     c.get("active_website", c.get("website", "")),
        "city":               c.get("city", ""),
        "country_detected":   c.get("country_detected", ""),
        "country_filter":     country_filter,
        "country_match":      country_match,
        "email":              c.get("email", ""),
        "phone":              c.get("phone", ""),
        "contact_person":     c.get("contact_person", ""),
        "contact_email":      c.get("contact_email", c.get("email", "")),
        "linkedin_url":       c.get("linkedin_url", ""),
        "industry_detected":  c.get("industry_detected", ""),
        "product_type":       c.get("product_type", ""),
        "channel_type":       c.get("channel_type", ""),
        "company_size":       c.get("company_size", ""),
        "incorporation_date": incorporation_date,
        "mca_company_type":   company_type_mca,
        "ai_summary":         c.get("summary", ""),
        "products":           c.get("products", []),
        "llm_relevant":       c.get("llm_relevant"),
        "semantic_score":     c.get("semantic_score", 0.0),
        "keyword_score":      c.get("keyword_score", 0.0),
        "domain_authority":   c.get("domain_authority", 0.0),
        "contact_presence":   c.get("contact_presence", 0.0),
        "final_score":        c.get("final_score", 0.0),
        "importance":         c.get("importance", "low"),
        "compliance_gaps":    compliance_gaps,
        "compliance_score":   compliance.get("compliance_score", 1.0),
        "bis_certified":      compliance.get("bis",  {}).get("certified",  None),
        "gst_registered":     compliance.get("gst",  {}).get("registered", None),
        "iec_found":          compliance.get("dgft", {}).get("iec_found",  None),
        "mca_active":         mca.get("active", None),
        "bis_detail":         compliance.get("bis",  {}).get("detail", ""),
        "gst_detail":         compliance.get("gst",  {}).get("detail", ""),
        "dgft_detail":        compliance.get("dgft", {}).get("detail", ""),
        "mca_detail":         mca.get("detail", ""),
        "compliance_checked": any(
            v.get("checked") for v in [
                compliance.get("bis",  {}),
                compliance.get("gst",  {}),
                compliance.get("dgft", {}),
                compliance.get("mca",  {}),
            ]
        ),
        "searched_query": query,
        "source":         "google_semantic",
        "created_at":     datetime.utcnow(),
    }
    if search_job_id:
        doc["search_job_id"] = search_job_id
    return doc


def _run_discovery(
    query: str,
    continue_search: bool = False,
    scan_all_remaining: bool = False,
    search_job_id: str | None = None,
    country_filter: str = "",
    trusted_only: bool = False,
    user_id: str = ANONYMOUS,
) -> dict:
    query          = query.strip()
    country_filter = (country_filter or "").strip().lower()
    sk             = _state_key(query, country_filter, trusted_only, user_id)

    if not query:
        return {"saved": 0, "linkedin_saved": 0, "saved_total": 0,
                "has_more": False, "next_start": 0, "pages_scanned": 0}

    if continue_search:
        state      = _read_search_state(sk)
        next_start = state["next_start"]
        has_more   = state["has_more"]
    else:
        next_start = 0
        has_more   = True
        _write_search_state(sk, next_start=0, has_more=True)

    if continue_search and not has_more:
        return {"saved": 0, "linkedin_saved": 0, "saved_total": 0,
                "has_more": False, "next_start": next_start, "pages_scanned": 0,
                "message": "No more pages left for this query."}

    known_domains  = _existing_domains_for_query(query, country_filter, user_id)
    saved          = 0
    pages_scanned  = 0
    linkedin_saved = 0
    guard          = 0

    while has_more and (scan_all_remaining or saved < DEFAULT_BATCH_RESULTS):
        want   = DEFAULT_BATCH_RESULTS if scan_all_remaining else (DEFAULT_BATCH_RESULTS - saved)
        result = google_search(
            query, max_results=want, start=next_start,
            exclude_domains=known_domains, max_pages=1,
            country_filter=country_filter, trusted_only=trusted_only,
        )

        companies      = result.get("companies", [])
        next_start     = int(result.get("next_start", next_start))
        has_more       = bool(result.get("has_more", False))
        pages_scanned += int(result.get("pages_scanned", 0))

        effective_country = (result.get("effective_country", "") or country_filter).strip().lower()
        if not country_filter and effective_country:
            country_filter = effective_country

        lead_docs = []
        for c in companies:
            lead_doc = _build_lead_doc(c, query, country_filter, user_id, search_job_id)
            lead_docs.append(lead_doc)
            saved += 1
            domain = c.get("domain", "") or _domain_from_url(c.get("website", ""))
            if domain:
                known_domains.add(domain)

        if lead_docs:
            leads_collection.insert_many(lead_docs)
            if search_job_id:
                for ld in lead_docs:
                    _append_job_result(search_job_id, ld)

        guard += 1
        if guard >= MAX_SEARCH_PAGES_PER_REQUEST:
            has_more = False
            break

    # LinkedIn
    if not continue_search:
        people = linkedin_discovery(query, country_filter=country_filter)
        linkedin_docs = []
        for p in people:
            ld = {
                "user_id":        user_id,
                "name":           p.get("name", ""),
                "profile":        p.get("profile", ""),
                "snippet":        p.get("snippet", ""),
                "country_filter": country_filter,
                "searched_query": query,
                "source":         "linkedin_semantic",
                "created_at":     datetime.utcnow(),
            }
            if search_job_id:
                ld["search_job_id"] = search_job_id
            linkedin_docs.append(ld)
            linkedin_saved += 1

        if linkedin_docs:
            leads_collection.insert_many(linkedin_docs)
            if search_job_id:
                for ld in linkedin_docs:
                    _append_job_result(search_job_id, ld)

    _write_search_state(sk, next_start=next_start, has_more=has_more)

    return {
        "saved": saved, "linkedin_saved": linkedin_saved,
        "saved_total": saved + linkedin_saved,
        "has_more": has_more, "next_start": next_start,
        "pages_scanned": pages_scanned,
        "continue_search": continue_search,
        "scan_all_remaining": scan_all_remaining,
        "country_filter": country_filter, "trusted_only": trusted_only,
    }


def _run_discovery_job(job_id: str, query: str, continue_search: bool,
                       scan_all_remaining: bool, country_filter: str,
                       trusted_only: bool, user_id: str) -> None:
    _upsert_job(job_id, status="running", started_at=datetime.utcnow())
    try:
        result = _run_discovery(
            query=query, continue_search=continue_search,
            scan_all_remaining=scan_all_remaining, search_job_id=job_id,
            country_filter=country_filter, trusted_only=trusted_only,
            user_id=user_id,
        )
        _upsert_job(job_id, status="completed", finished_at=datetime.utcnow(), **result)
        logger.info("Job %s (user=%s) completed: saved=%s", job_id, user_id, result.get("saved_total"))
    except Exception as exc:
        logger.exception("Job %s failed: %s", job_id, exc)
        _upsert_job(job_id, status="failed", finished_at=datetime.utcnow(), error=str(exc))


# ---------------------------------------------------------------------------
# Auth routes
# ---------------------------------------------------------------------------

@app.post("/auth/register")
def auth_register(body: RegisterRequest):
    try:
        user = register_user(body.username, body.password, body.email)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    token = create_token(user["user_id"])
    return {**user, "token": token}


@app.post("/auth/login")
def auth_login(body: LoginRequest):
    try:
        return login_user(body.username, body.password)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))


@app.get("/auth/me")
def auth_me(user: dict = Depends(get_current_user)):
    return user


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------

@app.get("/")
def home():
    return {"status": "running", "service": "Global Lead Discovery"}


@app.get("/llm/provider")
def llm_provider_info():
    try:
        from llm import get_active_provider
    except ImportError:
        from .llm import get_active_provider
    return get_active_provider()


# ---------------------------------------------------------------------------
# Admin fix endpoint — visit once to clean up old indexes/docs, then remove
# ---------------------------------------------------------------------------

@app.get("/admin/fix-indexes")
def fix_indexes():
    results = {}
    for idx in ["query_1", "user_id_1_query_1"]:
        try:
            search_state_collection.drop_index(idx)
            results[idx] = "dropped"
        except Exception as e:
            results[idx] = f"already gone or error: {e}"
    deleted = search_state_collection.delete_many(
        {"$or": [
            {"user_id": None},
            {"query": None},
            {"state_key": {"$exists": False}},
        ]}
    )
    results["deleted_bad_docs"] = deleted.deleted_count
    return results


# ---------------------------------------------------------------------------
# Background search
# ---------------------------------------------------------------------------

@app.post("/search/start")
def start_search(
    query: str,
    continue_search: bool = False,
    scan_all_remaining: bool = False,
    country_filter: str = "",
    trusted_only: bool = False,
    user: dict = Depends(get_current_user),
):
    query = query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required")
    country_filter = (country_filter or "").strip().lower()
    user_id = user["user_id"]
    _evict_old_jobs()

    job_id = uuid.uuid4().hex
    job = {
        "job_id": job_id, "query": query, "status": "queued",
        "user_id": user_id,
        "continue_search": continue_search, "scan_all_remaining": scan_all_remaining,
        "country_filter": country_filter, "trusted_only": trusted_only,
        "created_at": datetime.utcnow(), "started_at": None, "finished_at": None,
        "saved": 0, "linkedin_saved": 0, "saved_total": 0,
        "has_more": True, "next_start": 0, "pages_scanned": 0,
        "error": "", "results": [],
    }
    with SEARCH_JOBS_LOCK:
        SEARCH_JOBS[job_id] = job

    worker = threading.Thread(
        target=_run_discovery_job,
        args=(job_id, query, continue_search, scan_all_remaining,
              country_filter, trusted_only, user_id),
        daemon=True,
    )
    worker.start()
    return {"job_id": job_id, "status": "started", "query": query,
            "continue_search": continue_search, "country_filter": country_filter}


@app.get("/search/status/{job_id}")
def search_status(job_id: str, user: dict = Depends(get_current_user)):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job.get("user_id") != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="access denied")
        payload = {k: v for k, v in job.items() if k != "results"}
        payload["results_count"] = len(job["results"])
    payload["ask_continue"] = bool(
        payload.get("status") == "completed" and payload.get("has_more")
    )
    return payload


@app.get("/search/results/{job_id}")
def search_results(job_id: str, since: int = 0,
                   user: dict = Depends(get_current_user)):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job.get("user_id") != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="access denied")
        total     = len(job["results"])
        start_idx = max(0, min(int(since), total))
        items     = job["results"][start_idx:]
    return {"job_id": job_id, "results": items,
            "next_since": start_idx + len(items), "total": total}


@app.get("/search/more-like-this/{job_id}")
def search_more_like_this(job_id: str, result_index: int, limit: int = 5,
                          user: dict = Depends(get_current_user)):
    with SEARCH_JOBS_LOCK:
        job = SEARCH_JOBS.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="job not found")
        if job.get("user_id") != user["user_id"] and user.get("role") != "admin":
            raise HTTPException(status_code=403, detail="access denied")
        results = list(job.get("results", []))

    seed = next(
        (r for r in results if int(r.get("result_index", -1)) == int(result_index)), None)
    if not seed:
        raise HTTPException(status_code=404, detail="seed result not found")

    seed_text = " ".join(filter(None, [
        seed.get("company", ""), seed.get("ai_summary", ""),
        " ".join(seed.get("products", []) if isinstance(seed.get("products"), list) else []),
    ]))

    scored = []
    for row in results:
        if row.get("source") == "linkedin_semantic":
            continue
        if int(row.get("result_index", -1)) == int(result_index):
            continue
        row_text = " ".join(filter(None, [
            row.get("company", ""), row.get("ai_summary", ""),
            " ".join(row.get("products", []) if isinstance(row.get("products"), list) else []),
        ]))
        sim     = max(0.0, float(semantic_similarity(seed_text, row_text)))
        blended = round((0.7 * sim) + (0.3 * float(row.get("final_score", 0) or 0)), 3)
        item    = dict(row)
        item["similarity_score"]     = round(sim, 3)
        item["more_like_this_score"] = blended
        scored.append(item)

    scored.sort(key=lambda x: x.get("more_like_this_score", 0), reverse=True)
    return {"job_id": job_id, "seed_result_index": int(result_index),
            "results": scored[: max(1, min(int(limit), 20))]}


# ---------------------------------------------------------------------------
# Leads read — ALL filtered by user_id
# ---------------------------------------------------------------------------

def _user_base_filter(user: dict, country_filter: str = "") -> dict:
    f: dict = {}
    if user.get("role") != "admin":
        f["user_id"] = user["user_id"]
    if country_filter:
        f["country_filter"] = country_filter.strip().lower()
    return f


@app.get("/leads")
def get_leads(
    query: str = "", source: str = "", country_filter: str = "",
    min_score: float = 0.0, skip: int = 0, limit: int = 1000,
    user: dict = Depends(get_current_user),
):
    filters = _user_base_filter(user, country_filter)
    if query:
        filters["searched_query"] = query
    if source:
        filters["source"] = source
    if min_score > 0:
        filters["final_score"] = {"$gte": float(min_score)}

    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort("final_score", -1)
        .skip(max(0, int(skip)))
        .limit(max(1, min(int(limit), 2000)))
    )
    return list(cursor)


@app.get("/leads/by-channel")
def leads_by_channel(
    channel: str, country_filter: str = "",
    min_score: float = 0.0, limit: int = 500,
    user: dict = Depends(get_current_user),
):
    valid = {"Manufacturer", "Importer", "Trader", "Wholesaler", "Distributor", "Retailer"}
    channel = channel.strip().title()
    if channel not in valid:
        raise HTTPException(status_code=400, detail=f"channel must be one of {sorted(valid)}")
    filters = _user_base_filter(user, country_filter)
    filters["channel_type"] = channel
    filters["source"]       = {"$ne": "linkedin_semantic"}
    if min_score > 0:
        filters["final_score"] = {"$gte": float(min_score)}
    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort("final_score", -1)
        .limit(max(1, min(int(limit), 2000)))
    )
    return list(cursor)


@app.get("/leads/by-industry")
def leads_by_industry(
    industry: str, country_filter: str = "",
    min_score: float = 0.0, limit: int = 500,
    user: dict = Depends(get_current_user),
):
    filters = _user_base_filter(user, country_filter)
    filters["industry_detected"] = {"$regex": industry.strip(), "$options": "i"}
    filters["source"]            = {"$ne": "linkedin_semantic"}
    if min_score > 0:
        filters["final_score"] = {"$gte": float(min_score)}
    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort("final_score", -1)
        .limit(max(1, min(int(limit), 2000)))
    )
    return list(cursor)


@app.get("/leads/channel-summary")
def channel_summary(country_filter: str = "",
                    user: dict = Depends(get_current_user)):
    filters = _user_base_filter(user, country_filter)
    filters["source"]       = {"$ne": "linkedin_semantic"}
    filters["channel_type"] = {"$nin": ["", None]}
    pipeline = [
        {"$match": filters},
        {"$group": {"_id": "$channel_type", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = list(leads_collection.aggregate(pipeline))
    return {r["_id"]: r["count"] for r in rows}


@app.post("/leads/enrich-compliance")
def enrich_compliance_background(
    limit: int = 50, country_filter: str = "",
    user: dict = Depends(get_current_user),
):
    try:
        from cert_checker import check_company_compliance
    except ImportError:
        from .cert_checker import check_company_compliance

    filters = _user_base_filter(user, country_filter)
    filters["source"]             = {"$ne": "linkedin_semantic"}
    filters["compliance_checked"] = {"$ne": True}
    filters["company"]            = {"$exists": True, "$ne": ""}

    leads = list(
        leads_collection.find(filters, {"_id": 1, "company": 1, "website": 1})
        .limit(max(1, min(int(limit), 200)))
    )

    def _run(lead):
        compliance      = check_company_compliance(
            lead.get("company", ""), lead.get("website", ""))
        compliance_gaps = compliance.get("compliance_gaps", [])
        mca             = compliance.get("mca", {})
        leads_collection.update_one(
            {"_id": lead["_id"]},
            {"$set": {
                "compliance_gaps":    compliance_gaps,
                "compliance_score":   compliance.get("compliance_score", 1.0),
                "bis_certified":      compliance.get("bis",  {}).get("certified",  None),
                "gst_registered":     compliance.get("gst",  {}).get("registered", None),
                "iec_found":          compliance.get("dgft", {}).get("iec_found",  None),
                "mca_active":         mca.get("active",     None),
                "bis_detail":         compliance.get("bis",  {}).get("detail",     ""),
                "gst_detail":         compliance.get("gst",  {}).get("detail",     ""),
                "dgft_detail":        compliance.get("dgft", {}).get("detail",     ""),
                "mca_detail":         mca.get("detail",     ""),
                "mca_company_type":   mca.get("company_type", ""),
                "incorporation_date": mca.get("incorporation_date", ""),
                "compliance_checked": True,
            }}
        )

    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=6) as ex:
        list(ex.map(_run, leads))

    return {"status": "done", "checked": len(leads)}


@app.get("/leads/gaps")
def get_leads_with_gaps(
    gap: str = "", country_filter: str = "",
    min_score: float = 0.0, importance: str = "",
    skip: int = 0, limit: int = 1000,
    user: dict = Depends(get_current_user),
):
    filters = _user_base_filter(user, country_filter)
    filters["source"]             = {"$ne": "linkedin_semantic"}
    filters["compliance_checked"] = True
    filters["compliance_gaps"]    = {"$exists": True, "$not": {"$size": 0}}
    if gap:
        filters["compliance_gaps"] = gap.strip()
    if min_score > 0:
        filters["final_score"] = {"$gte": float(min_score)}
    if importance:
        filters["importance"] = importance.strip().lower()

    cursor = (
        leads_collection.find(filters, {"_id": 0})
        .sort([("compliance_score", 1), ("final_score", -1)])
        .skip(max(0, int(skip)))
        .limit(max(1, min(int(limit), 2000)))
    )
    return list(cursor)


@app.get("/leads/gap-summary")
def gap_summary(country_filter: str = "",
                user: dict = Depends(get_current_user)):
    filters = _user_base_filter(user, country_filter)
    filters["source"]             = {"$ne": "linkedin_semantic"}
    filters["compliance_checked"] = True
    pipeline = [
        {"$match": filters},
        {"$unwind": {"path": "$compliance_gaps", "preserveNullAndEmptyArrays": False}},
        {"$group": {"_id": "$compliance_gaps", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
    ]
    rows = list(leads_collection.aggregate(pipeline))
    return {r["_id"]: r["count"] for r in rows}


@app.post("/leads/recheck/{lead_id}")
def recheck_lead(lead_id: str, user: dict = Depends(get_current_user)):
    from bson import ObjectId
    try:
        oid = ObjectId(lead_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid lead_id")
    lead = leads_collection.find_one({"_id": oid})
    if not lead:
        raise HTTPException(status_code=404, detail="Lead not found")
    if lead.get("user_id") != user["user_id"] and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="access denied")

    try:
        from cert_checker import check_company_compliance
    except ImportError:
        from .cert_checker import check_company_compliance

    compliance      = check_company_compliance(
        lead.get("company", ""), lead.get("website", ""))
    compliance_gaps = compliance.get("compliance_gaps", [])
    mca             = compliance.get("mca", {})
    update = {
        "compliance_gaps":    compliance_gaps,
        "compliance_score":   compliance.get("compliance_score", 1.0),
        "bis_certified":      compliance.get("bis",  {}).get("certified",  None),
        "gst_registered":     compliance.get("gst",  {}).get("registered", None),
        "iec_found":          compliance.get("dgft", {}).get("iec_found",  None),
        "mca_active":         mca.get("active",     None),
        "bis_detail":         compliance.get("bis",  {}).get("detail",     ""),
        "gst_detail":         compliance.get("gst",  {}).get("detail",     ""),
        "dgft_detail":        compliance.get("dgft", {}).get("detail",     ""),
        "mca_detail":         mca.get("detail",     ""),
        "mca_company_type":   mca.get("company_type", ""),
        "incorporation_date": mca.get("incorporation_date", ""),
        "compliance_checked": True,
    }
    leads_collection.update_one({"_id": oid}, {"$set": update})
    return {"status": "rechecked", "compliance_gaps": compliance_gaps}


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

@app.delete("/clear")
def clear(user: dict = Depends(get_current_user)):
    if user.get("role") == "admin":
        leads_collection.delete_many({})
        search_state_collection.delete_many({})
        with SEARCH_JOBS_LOCK:
            SEARCH_JOBS.clear()
        return {"status": "cleared", "scope": "all"}
    else:
        leads_collection.delete_many({"user_id": user["user_id"]})
        search_state_collection.delete_many(
            {"state_key": {"$regex": f"^{user['user_id']}\\|"}}
        )
        with SEARCH_JOBS_LOCK:
            to_del = [jid for jid, j in SEARCH_JOBS.items()
                      if j.get("user_id") == user["user_id"]]
            for jid in to_del:
                del SEARCH_JOBS[jid]
        return {"status": "cleared", "scope": user["user_id"]}


# ---------------------------------------------------------------------------
# Debug endpoint — test SERP API directly
# ---------------------------------------------------------------------------

@app.get("/admin/test-search")
def test_search(query: str = "electronics importers india"):
    """Call SERP API directly and return raw results for debugging."""
    try:
        from scraper_google import google_search, SERP_API_KEY
    except ImportError:
        from .scraper_google import google_search, SERP_API_KEY

    return {
        "serp_api_key_set": bool(SERP_API_KEY and SERP_API_KEY.strip()),
        "serp_api_key_preview": SERP_API_KEY[:8] + "..." if SERP_API_KEY else "NOT SET",
        "query": query,
        "result": google_search(query, max_results=3),
    }


# ---------------------------------------------------------------------------
# Deep Research endpoint
# ---------------------------------------------------------------------------

class ResearchRequest(BaseModel):
    company: str
    website: str = ""
    country: str = "india"
    query:   str = ""

@app.post("/research/deep")
def deep_research_endpoint(body: ResearchRequest,
                           user: dict = Depends(get_current_user)):
    try:
        from deep_research import deep_research
    except ImportError:
        from .deep_research import deep_research
    result = deep_research(
        company=body.company,
        website=body.website,
        country=body.country,
        query=body.query,
    )
    return result


# ---------------------------------------------------------------------------
# Verification endpoint
# ---------------------------------------------------------------------------

class VerifyRequest(BaseModel):
    email:   str = ""
    phone:   str = ""
    website: str = ""

@app.post("/verify/lead")
def verify_lead_endpoint(body: VerifyRequest,
                         user: dict = Depends(get_current_user)):
    try:
        from verifier import verify_lead
    except ImportError:
        from .verifier import verify_lead
    result = verify_lead({
        "email":   body.email,
        "phone":   body.phone,
        "website": body.website,
    })
    return result
