try:
    from .database import leads_collection
except ImportError:
    from database import leads_collection

SAMPLES = [
{"text":"Company in Mumbai looking for GST consultant for annual return","service":"Indirect Taxation","country":"india","urgency":"high","budget":0,"score":0.9},
{"text":"Importer needs DGFT / EXIM advisor for EPCG scheme support","service":"Foreign Trade Policy & EXIM","country":"india","urgency":"medium","budget":0,"score":0.87},
{"text":"Electronics firm requires BIS registration consultant","service":"BIS Certification","country":"india","urgency":"high","budget":0,"score":0.94},
{"text":"Company wants EPR registration support for plastic waste","service":"EPR Compliance","country":"india","urgency":"medium","budget":0,"score":0.89},
]

leads_collection.insert_many(SAMPLES)
print("Seeded!")
