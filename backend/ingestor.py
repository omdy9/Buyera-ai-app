import feedparser
try:
    from .nlp import score_match
    from .database import leads_collection
except ImportError:
    from nlp import score_match
    from database import leads_collection

KEYWORDS = [
    "GST consultant India",
    "DGFT consultant",
    "Foreign trade policy consultant",
    "IBC insolvency advisor",
    "tax consultant India",
    "BIS certification consultant",
    "EPR registration consultant",
    "legal metrology consultant"
]

SERVICE_MAP = {
    "dgft": "Foreign Trade Policy & EXIM",
    "foreign trade": "Foreign Trade Policy & EXIM",
    "gst": "Indirect Taxation",
    "tax": "Direct Taxation",
    "insolvency": "Insolvency & Bankruptcy",
    "ibc": "Insolvency & Bankruptcy",
    "bis": "BIS Certification",
    "epr": "EPR Compliance",
    "legal metrology": "Legal Metrology",
    "consultant": "Business Consulting"
}


def detect_category(text):
    text = text.lower()
    for k,v in SERVICE_MAP.items():
        if k in text:
            return v
    return "Other Regulatory Matters"


def fetch_news():
    for kw in KEYWORDS:
        url = f"https://news.google.com/rss/search?q={kw.replace(' ', '+')}+india"
        feed = feedparser.parse(url)

        for item in feed.entries:
            text = item.title + " " + getattr(item, "summary", "")

            category = detect_category(text)

            score = score_match(text, category)

            lead = {
                "text": text,
                "service": category,
                "country": "india",
                "urgency": "normal",
                "budget": 0,
                "link": item.link,
                "score": score
            }

            leads_collection.insert_one(lead)
