"""
nlp.py  — keyword-only scoring (no sentence-transformers, no heavy deps)
Removed model loading entirely to keep Render free tier under memory limits.
"""
import re
import math
import logging
from collections import Counter

logger = logging.getLogger(__name__)

SERVICES = [
    "web development", "seo", "marketing", "software development",
    "app development", "accounting", "legal services", "logistics",
]

COUNTRIES = ["india", "usa", "uk", "uae", "germany", "canada", "australia"]

STOPWORDS = {
    "a", "an", "and", "or", "the", "in", "on", "at", "to", "for",
    "from", "of", "by", "with", "near", "me", "company", "companies",
    "service", "services",
}


def extract_fields(text):
    text_low = text.lower()
    service  = next((s for s in SERVICES if s in text_low), "unknown")
    country  = next((c for c in COUNTRIES if c in text_low), "unknown")
    urgency  = "high" if "urgent" in text_low else "normal"
    budget   = None
    for word in text_low.split():
        if word.startswith("$"):
            try:
                budget = float(word.replace("$", ""))
            except Exception:
                pass
    return service, country, urgency, budget


def _query_tokens(query: str) -> list:
    return [
        t for t in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(t) > 2 and t not in STOPWORDS
    ]


def _tfidf_cosine(query: str, text: str) -> float:
    def _tok(t):
        return [w for w in re.findall(r"[a-zA-Z0-9]+", t.lower())
                if len(w) > 2 and w not in STOPWORDS]

    q_tok = _tok(query)
    t_tok = _tok(text[:3000])
    if not q_tok or not t_tok:
        return keyword_match_ratio(query, text)

    vocab = set(q_tok) | set(t_tok)
    qc    = Counter(q_tok)
    tc    = Counter(t_tok)

    def vec(counts, total):
        return {
            w: (counts[w] / total) *
               math.log(2 / (1 + (w in qc) + (w in tc)) + 1)
            for w in vocab if counts[w] > 0
        }

    qv  = vec(qc, len(q_tok))
    tv  = vec(tc, len(t_tok))
    dot = sum(qv.get(w, 0) * tv.get(w, 0) for w in vocab)
    qn  = math.sqrt(sum(v**2 for v in qv.values()))
    tn  = math.sqrt(sum(v**2 for v in tv.values()))
    if qn == 0 or tn == 0:
        return 0.0
    return round(dot / (qn * tn), 3)


def score_match(text, service_keyword):
    return _tfidf_cosine(service_keyword, text)


def semantic_similarity(query, text):
    if not query or not text:
        return 0.0
    return _tfidf_cosine(query, text)


def keyword_match_ratio(query: str, text: str) -> float:
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    low  = text.lower()
    hits = sum(1 for t in tokens if re.search(rf"\b{re.escape(t)}\b", low))
    return round(hits / len(tokens), 3)


def ai_summary_for_query(query: str, content: str, max_sentences: int = 3) -> str:
    if not content:
        return ""
    cleaned   = " ".join(content.split())
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned)
        if 20 <= len(s.strip()) <= 280
    ]
    if not sentences:
        return cleaned[:500]
    tokens = _query_tokens(query)
    scored = []
    for s in sentences[:40]:
        sl   = s.lower()
        hits = sum(1 for t in tokens if t in sl)
        scored.append((hits, s))
    scored.sort(reverse=True)
    return " ".join(s for _, s in scored[:max_sentences])[:700]
