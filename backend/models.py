from sqlalchemy import Column, Integer, String, Float
try:
    from .database import Base
except ImportError:
    from database import Base

class BuyerLead(Base):
    __tablename__ = "buyer_leads"

    id = Column(Integer, primary_key=True, index=True)
    text = Column(String)
    service = Column(String)
    country = Column(String)
    urgency = Column(String)
    budget = Column(Float)
    score = Column(Float)
