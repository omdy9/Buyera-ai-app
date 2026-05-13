import re
try:
    from .bis_master import BIS_PRODUCTS
except ImportError:
    from bis_master import BIS_PRODUCTS

BIS_RE = r"(IS\s?\d+|R-\d+)"

def analyze_bis(content):

    text = content.lower()

    detected=[]
    scheme=""

    for p,s in BIS_PRODUCTS.items():
        if p in text:
            detected.append(p)
            scheme=s

    bis_found = bool(re.search(BIS_RE, content.upper()))

    return {
        "products":detected,
        "scheme":scheme,
        "bis_status":"CERTIFIED" if bis_found else "NOT FOUND"
    }
