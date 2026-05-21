from pymongo import MongoClient
from dotenv import load_dotenv
import os

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")

client = MongoClient(MONGO_URI)

db = client["buyera_ai"]

leads_collection = db["leads"]
search_state_collection = db["search_state"]

# indexes
leads_collection.create_index("company")
leads_collection.create_index("website")
leads_collection.create_index("industry")
leads_collection.create_index("country")