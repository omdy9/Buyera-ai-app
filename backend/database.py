"""
database.py — MongoDB collections
"""
from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)
db     = client["buyera_ai"]

# Collections
leads_collection        = db["leads"]
search_state_collection = db["search_state"]
users_collection        = db["users"]

# Drop old conflicting indexes before creating new ones
for _idx in ["query_1", "user_id_1_query_1"]:
    try:
        search_state_collection.drop_index(_idx)
    except Exception:
        pass  # already gone, fine

# Clean up old documents with null fields that cause duplicate key errors
try:
    search_state_collection.delete_many(
        {"$or": [
            {"user_id": None},
            {"query": None},
            {"state_key": {"$exists": False}},
        ]}
    )
except Exception:
    pass

# Core indexes
leads_collection.create_index("company")
leads_collection.create_index("website")
leads_collection.create_index("user_id")
users_collection.create_index("username", unique=True)
users_collection.create_index("user_id",  unique=True)

# Use state_key as the unique field for search_state — never null
try:
    search_state_collection.create_index("state_key", unique=True)
except Exception:
    pass
