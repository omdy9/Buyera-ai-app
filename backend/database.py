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
users_collection        = db["users"]          # NEW

try:
    search_state_collection.drop_index("query_1")
except Exception:
    pass
# Core indexes
leads_collection.create_index("company")
leads_collection.create_index("website")
leads_collection.create_index("user_id")        # NEW — per-user isolation
users_collection.create_index("username", unique=True)
users_collection.create_index("user_id",  unique=True)
