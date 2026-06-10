"""
job_store.py — Persist search job status in MongoDB
====================================================
Survives backend restarts. Users can still see their
completed results even after Render wakes from sleep.
"""

from datetime import datetime, timedelta
from pymongo import MongoClient
import os

try:
    from .database import db
except ImportError:
    from database import db

jobs_collection = db["search_jobs"]

# Index for fast lookup and auto-cleanup
try:
    jobs_collection.create_index("job_id", unique=True)
    jobs_collection.create_index("user_id")
    jobs_collection.create_index("created_at")
    # Auto-delete jobs older than 7 days
    jobs_collection.create_index(
        "created_at",
        expireAfterSeconds=7 * 24 * 3600,
        name="ttl_7days"
    )
except Exception:
    pass


def save_job(job: dict) -> None:
    """Upsert job to MongoDB (without full results list — too large)."""
    doc = {k: v for k, v in job.items() if k != "results"}
    doc["results_count"] = len(job.get("results", []))
    doc["updated_at"]    = datetime.utcnow()
    try:
        jobs_collection.update_one(
            {"job_id": job["job_id"]},
            {"$set": doc},
            upsert=True,
        )
    except Exception:
        pass


def load_job(job_id: str) -> dict | None:
    """Load job metadata from MongoDB."""
    try:
        return jobs_collection.find_one({"job_id": job_id}, {"_id": 0})
    except Exception:
        return None


def load_recent_jobs(user_id: str, limit: int = 10) -> list:
    """Load recent jobs for a user."""
    try:
        return list(
            jobs_collection.find(
                {"user_id": user_id},
                {"_id": 0}
            ).sort("created_at", -1).limit(limit)
        )
    except Exception:
        return []


def cleanup_old_jobs(days: int = 7) -> int:
    """Remove jobs older than N days."""
    try:
        cutoff = datetime.utcnow() - timedelta(days=days)
        result = jobs_collection.delete_many({"created_at": {"$lt": cutoff}})
        return result.deleted_count
    except Exception:
        return 0
