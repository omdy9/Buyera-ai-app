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
search_state_collection = db["search_state"]
users_collection        = db["users"]


def _fix_search_state_indexes():
    """
    Clean up the search_state collection so a unique index on state_key works:
    1. Drop every non-_id index (gets rid of the bad user_id+query index and
       any half-built state_key index).
    2. Delete all documents that have state_key = null / missing — these are
       orphan rows from the old schema and will block index creation.
    3. Create the correct unique index on state_key.
    """
    try:
        # Step 1 — drop all existing indexes except _id
        existing = search_state_collection.index_information()
        for name in list(existing.keys()):
            if name == "_id_":
                continue
            try:
                search_state_collection.drop_index(name)
                logger.info("Dropped search_state index: %s", name)
            except Exception as e:
                logger.warning("Could not drop index %s: %s", name, e)

        # Step 2 — purge documents that have no state_key (or null state_key)
        result = search_state_collection.delete_many(
            {"$or": [
                {"state_key": {"$exists": False}},
                {"state_key": None},
                {"state_key": ""},
            ]}
        )
        if result.deleted_count:
            logger.info(
                "Deleted %d orphan search_state documents with null/missing state_key",
                result.deleted_count,
            )

        # Step 3 — create the correct unique index
        search_state_collection.create_index("state_key", unique=True)
        logger.info("Created unique index on search_state.state_key")

    except Exception as e:
        logger.error("_fix_search_state_indexes failed: %s", e)


_fix_search_state_indexes()

# Core indexes (idempotent — safe to run on every startup)
try:
    leads_collection.create_index("company")
    leads_collection.create_index("website")
    leads_collection.create_index("user_id")
    users_collection.create_index("username", unique=True)
    users_collection.create_index("user_id",  unique=True)
except Exception as e:
    logger.warning("Core index creation warning: %s", e)
