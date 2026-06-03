"""
database.py — MongoDB collections
"""
from pymongo import MongoClient
from pymongo.errors import OperationFailure
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

# ---------------------------------------------------------------------------
# Nuke every index on search_state except _id, then rebuild correctly.
# The old unique index on {user_id, query} causes E11000 because docs only
# have a state_key field — user_id and query are always null/missing.
# ---------------------------------------------------------------------------
def _fix_search_state_indexes():
    try:
        existing = search_state_collection.index_information()
        for name, info in existing.items():
            if name == "_id_":
                continue  # never drop the primary index
            try:
                search_state_collection.drop_index(name)
                logger.info("Dropped search_state index: %s", name)
            except Exception as e:
                logger.warning("Could not drop index %s: %s", name, e)
        # Now create the correct unique index
        search_state_collection.create_index("state_key", unique=True)
        logger.info("Created correct search_state index on state_key")
    except Exception as e:
        logger.warning("_fix_search_state_indexes failed: %s", e)

_fix_search_state_indexes()

# Core indexes (idempotent)
try:
    leads_collection.create_index("company")
    leads_collection.create_index("website")
    leads_collection.create_index("user_id")
    users_collection.create_index("username", unique=True)
    users_collection.create_index("user_id",  unique=True)
except Exception as e:
    logger.warning("Index creation warning: %s", e)
