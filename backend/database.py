import os
from pymongo import MongoClient
from dotenv import load_dotenv

load_dotenv()

client = MongoClient(os.getenv("MONGO_URI"))
db = client["leadfinder"]
leads_collection = db["leads"]
search_state_collection = db["search_state"]
