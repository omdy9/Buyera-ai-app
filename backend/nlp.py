"""
nlp.py  –  Fixed for Render free tier
Model loads lazily on first use instead of at import time.
This keeps startup RAM under 512MB.
"""
import re
import logging

logger = logging.getLogger(__name__)

SERVICES = [
    "web development", "seo", "marketing", "software development",
    "app development", "accounting", "legal services", "logistics",
]

COUNTRIES = [
    "india", "usa", "uk", "uae", "germany", "canada", "australia"
]

STOPWORDS = {
    "a", "an", "and", "or", "the", "in", "on", "at", "to", "for",
    "from", "of", "by", "with", "near", "me", "company", "companies",
    "service", "services"
}

# ---------------------------------------------------------------------------
# Lazy model loader — only downloads/loads on first actual use
# ---------------------------------------------------------------------------
_model = None

def _get_model():
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading sentence-transformers model...")
            _model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Model loaded.")
        except Exception as exc:
            logger.warning("sentence-transformers not available: %s", exc)
            _model = False   # Mark as unavailable so we don't retry every call
    return _model if _model else None


# ---------------------------------------------------------------------------
# Functions
# ---------------------------------------------------------------------------

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


def score_match(text, service_keyword):
    model = _get_model()
    if not model:
        return _keyword_fallback(text, service_keyword)
    try:
        from sentence_transformers import util
        e1 = model.encode([text], convert_to_tensor=True)
        e2 = model.encode([service_keyword], convert_to_tensor=True)
        return round(float(util.cos_sim(e1, e2).item()), 3)
    except Exception:
        return _keyword_fallback(text, service_keyword)


def semantic_similarity(query, text):
    if not query or not text:
        return 0.0
    model = _get_model()
    if not model:
        return keyword_match_ratio(query, text)
    try:
        from sentence_transformers import util
        eq = model.encode([query.strip()],       convert_to_tensor=True)
        et = model.encode([text.strip()[:4000]], convert_to_tensor=True)
        return round(float(util.cos_sim(eq, et).item()), 3)
    except Exception:
        return keyword_match_ratio(query, text)


def _query_tokens(query):
    return [
        t for t in re.findall(r"[a-zA-Z0-9]+", query.lower())
        if len(t) > 2 and t not in STOPWORDS
    ]


def _keyword_fallback(query, text):
    """TF-IDF cosine similarity — zero dependencies, used when model unavailable."""
    import math
    from collections import Counter

    def _tok(t):
        return [w for w in re.findall(r"[a-zA-Z0-9]+", t.lower())
                if len(w) > 2 and w not in STOPWORDS]

    q_tok = _tok(query)
    t_tok = _tok(text[:3000])
    if not q_tok or not t_tok:
        return keyword_match_ratio(query, text)

    vocab    = set(q_tok) | set(t_tok)
    qc       = Counter(q_tok)
    tc       = Counter(t_tok)

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


def keyword_match_ratio(query, text):
    tokens = _query_tokens(query)
    if not tokens:
        return 0.0
    low  = text.lower()
    hits = sum(1 for t in tokens if re.search(rf"\b{re.escape(t)}\b", low))
    return round(hits / len(tokens), 3)


def ai_summary_for_query(query, content, max_sentences=3):
    if not content:
        return ""

    cleaned   = " ".join(content.split())
    sentences = [
        s.strip() for s in re.split(r"(?<=[.!?])\s+", cleaned)
        if 20 <= len(s.strip()) <= 280
    ]

    if not sentences:
        return cleaned[:500]

    model = _get_model()
    if not model:
        # Fallback: return first N sentences that contain query tokens
        tokens = _query_tokens(query)
        scored = []
        for s in sentences[:40]:
            sl   = s.lower()
            hits = sum(1 for t in tokens if t in sl)
            scored.append((hits, s))
        scored.sort(reverse=True)
        return " ".join(s for _, s in scored[:max_sentences])[:700]

    try:
        from sentence_transformers import util
        sentences = sentences[:120]
        top_k     = min(max_sentences, len(sentences))
        emb_q     = model.encode([query],     convert_to_tensor=True)
        emb_s     = model.encode(sentences,   convert_to_tensor=True)
        sims      = util.cos_sim(emb_q, emb_s)[0]
        ranked    = sorted(range(len(sentences)),
                           key=lambda i: float(sims[i]),
                           reverse=True)[:top_k]
        ranked.sort()
        return " ".join(sentences[i] for i in ranked)[:700]
    except Exception:
        return " ".join(sentences[:max_sentences])[:700]
