import re
from sentence_transformers import SentenceTransformer, util

model = SentenceTransformer("all-MiniLM-L6-v2")

SERVICES = [
    "web development",
    "seo",
    "marketing",
    "software development",
    "app development",
    "accounting",
    "legal services",
    "logistics",
]

COUNTRIES = [
    "india", "usa", "uk", "uae",
    "germany", "canada", "australia"
]

STOPWORDS = {
    "a", "an", "and", "or", "the", "in", "on", "at", "to", "for", "from", "of",
    "by", "with", "near", "me", "company", "companies", "service", "services"
}


def extract_fields(text):
    text_low = text.lower()

    service = next((s for s in SERVICES if s in text_low), "unknown")
    country = next((c for c in COUNTRIES if c in text_low), "unknown")
    urgency = "high" if "urgent" in text_low else "normal"

    budget = None
    for word in text_low.split():
        if word.startswith("$"):
            try:
                budget = float(word.replace("$", ""))
            except Exception:
                pass

    return service, country, urgency, budget


def score_match(text, service_keyword):
    emb1 = model.encode([text], convert_to_tensor=True)
    emb2 = model.encode([service_keyword], convert_to_tensor=True)
    score = util.cos_sim(emb1, emb2).item()
    return round(float(score), 3)


def semantic_similarity(query, text):
    if not query or not text:
        return 0.0

    query = query.strip()
    text = text.strip()[:4000]

    if not query or not text:
        return 0.0

    emb_q = model.encode([query], convert_to_tensor=True)
    emb_t = model.encode([text], convert_to_tensor=True)
    return round(float(util.cos_sim(emb_q, emb_t).item()), 3)


def _query_tokens(query):
    return [
        t for t in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(t) > 2 and t not in STOPWORDS
    ]


def keyword_match_ratio(query, text):
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0

    low = text.lower()
    hits = 0
    for token in tokens:
        if re.search(rf"\b{re.escape(token)}\b", low):
            hits += 1

    return round(hits / len(tokens), 3)


def ai_summary_for_query(query, content, max_sentences=3):
    if not content:
        return ""

    cleaned = " ".join(content.split())
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned)
        if 20 <= len(s.strip()) <= 280
    ]

    if not sentences:
        return cleaned[:500]

    sentences = sentences[:120]
    top_k = min(max_sentences, len(sentences))

    emb_q = model.encode([query], convert_to_tensor=True)
    emb_s = model.encode(sentences, convert_to_tensor=True)
    sims = util.cos_sim(emb_q, emb_s)[0]

    ranked = sorted(
        range(len(sentences)),
        key=lambda idx: float(sims[idx]),
        reverse=True
    )[:top_k]

    ranked.sort()
    summary = " ".join(sentences[idx] for idx in ranked)
    return summary[:700]
