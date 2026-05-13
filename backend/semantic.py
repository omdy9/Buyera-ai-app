import spacy

nlp = spacy.load("en_core_web_sm")

def understand_query(query):

    doc = nlp(query)

    intent = {
        "location": "",
        "service": "",
        "industry": ""
    }

    for ent in doc.ents:
        if ent.label_ in ["GPE", "LOC"]:
            intent["location"] = ent.text

    keywords = [t.text.lower() for t in doc if t.pos_ in ["NOUN","PROPN"]]

    if len(keywords) > 0:
        intent["service"] = keywords[0]

    if len(keywords) > 1:
        intent["industry"] = keywords[-1]

    return intent


def generate_queries(intent):

    base = f"{intent['industry']} {intent['service']} {intent['location']}"

    return [
        base,
        f"{intent['service']} company {intent['location']}",
        f"site:linkedin.com/in {intent['service']} {intent['location']}"
    ]
