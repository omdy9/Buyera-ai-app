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

# Drop the bad unique index that caused E11000 errors
# (it was on {user_id, query} but search_state docs use state_key, not those fields)
for bad_index in ["user_id_1_query_1", "query_1"]:
    try:
        search_state_collection.drop_index(bad_index)
    except Exception:
        pass

# Correct unique index — search_state docs are keyed by state_key string
try:
    search_state_collection.create_index("state_key", unique=True)
except Exception:
    pass

# Core indexes
leads_collection.create_index("company")
leads_collection.create_index("website")
leads_collection.create_index("user_id")
users_collection.create_index("username", unique=True)
users_collection.create_index("user_id",  unique=True)
