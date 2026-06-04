import logging

logger = logging.getLogger(__name__)

# FIX: do NOT call spacy.load() at module level — it crashes if the model
# isn't downloaded yet (e.g. first Render deploy before build completes).
_nlp = None

def _get_nlp():
    global _nlp
    if _nlp is None:
        try:
            import spacy
            _nlp = spacy.load("en_core_web_sm")
        except OSError as e:
            logger.warning("spaCy model 'en_core_web_sm' not found: %s. "
                           "Run: python -m spacy download en_core_web_sm", e)
            _nlp = False
    return _nlp if _nlp else None


def understand_query(query: str) -> dict:
    intent = {"location": "", "service": "", "industry": ""}

    nlp = _get_nlp()
    if not nlp:
        # Fallback: simple keyword split when spaCy unavailable
        words = [w for w in query.split() if len(w) > 3]
        if words:
            intent["service"] = words[0]
        if len(words) > 1:
            intent["industry"] = words[-1]
        return intent

    doc = nlp(query)
    for ent in doc.ents:
        if ent.label_ in ["GPE", "LOC"]:
            intent["location"] = ent.text

    keywords = [t.text.lower() for t in doc if t.pos_ in ["NOUN", "PROPN"]]
    if keywords:
        intent["service"] = keywords[0]
    if len(keywords) > 1:
        intent["industry"] = keywords[-1]

    return intent


def generate_queries(intent: dict) -> list:
    base = f"{intent['industry']} {intent['service']} {intent['location']}"
    return [
        base,
        f"{intent['service']} company {intent['location']}",
        f"site:linkedin.com/in {intent['service']} {intent['location']}",
    ]
