"""
database.py — MongoDB collections
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import os
import logging

logger = logging.getLogger(__name__)
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db     = client["buyera_ai"]

# Collections
leads_collection        = db["leads"]
users_collection        = db["users"]


def _rebuild_search_state():
    """
    The search_state collection has accumulated bad indexes and null-state_key
    documents across multiple failed migrations. The only reliable fix is to
    drop the collection entirely and recreate it clean.

    search_state only holds pagination cursors (next_start / has_more) — it
    contains no user data worth keeping.  Dropping it means the next search
    for each query starts from page 0 again, which is correct behaviour.
    """
    try:
        db.drop_collection("search_state")
        logger.info("Dropped search_state collection")
    except Exception as e:
        logger.warning("Could not drop search_state: %s", e)

    # Recreate with the correct unique index from the start
    col = db["search_state"]
    try:
        col.create_index("state_key", unique=True)
        logger.info("Created fresh unique index on search_state.state_key")
    except Exception as e:
        logger.error("Could not create state_key index: %s", e)
    return col


search_state_collection = _rebuild_search_state()

# Core indexes (idempotent)
try:
    leads_collection.create_index("company")
    leads_collection.create_index("website")
    leads_collection.create_index("user_id")
    users_collection.create_index("username", unique=True)
    users_collection.create_index("user_id",  unique=True)
except Exception as e:
    logger.warning("Core index creation warning: %s", e)
