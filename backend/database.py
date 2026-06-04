from pymongo import MongoClient, ASCENDING, DESCENDING
from dotenv import load_dotenv
import os
import logging

load_dotenv()
logger = logging.getLogger(__name__)

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db = client["buyera_ai"]

leads_collection        = db["leads"]
search_state_collection = db["search_state"]
users_collection        = db["users"]

# FIX: wrap index creation — unreachable Mongo at import time must not crash startup
try:
    leads_collection.create_index("company")
    leads_collection.create_index("website")
    leads_collection.create_index([("user_id", ASCENDING), ("final_score", DESCENDING)])
    leads_collection.create_index([("user_id", ASCENDING), ("searched_query", ASCENDING)])
    leads_collection.create_index([("search_job_id", ASCENDING), ("result_index", ASCENDING)])

    # FIX: search_state_collection uniqueness was on [user_id, query] but
    # _write_search_state() upserts on state_key (a combined string).
    # Change the unique index to match what the code actually queries on.
    try:
        search_state_collection.drop_index("user_id_1_query_1")
    except Exception:
        pass
    search_state_collection.create_index("state_key", unique=True)

    users_collection.create_index("username", unique=True)
    users_collection.create_index("user_id",  unique=True)

    logger.info("MongoDB indexes ensured.")
except Exception as exc:
    logger.warning("Startup index creation skipped (will retry on first use): %s", exc)
