import os
import time
import re

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Backend URL
# ---------------------------------------------------------------------------
def _get_api_url() -> str:
    try:
        url = st.secrets.get("BACKEND_URL", "")
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    url = os.getenv("BACKEND_URL", "")
    if url:
        return url.rstrip("/")
    return "http://127.0.0.1:8000"

API          = _get_api_url()
POLL_SECONDS = 2

st.set_page_config(page_title="Global B2B Lead Discovery", layout="wide")

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict:
    """Return the X-User-Token header dict if logged in, else empty dict."""
    token = st.session_state.get("auth_token", "")
    return {"X-User-Token": token} if token else {}


def _api_post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{API}{path}", headers=_auth_headers(),
                         timeout=kwargs.pop("timeout", 30), **kwargs)

def _api_get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{API}{path}", headers=_auth_headers(),
                        timeout=kwargs.pop("timeout", 20), **kwargs)

def _api_delete(path: str, **kwargs) -> requests.Response:
    return requests.delete(f"{API}{path}", headers=_auth_headers(),
                           timeout=kwargs.pop("timeout", 15), **kwargs)


def _show_login_page():
    """Render the login / register screen. Returns only after successful login."""
    st.title("🌐 Global B2B Lead Discovery")
    st.markdown("#### Please log in or create an account to continue.")

    tab_login, tab_register = st.tabs(["🔑 Login", "📝 Register"])

    with tab_login:
        with st.form("login_form"):
            uname = st.text_input("Username")
            pwd   = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Login", use_container_width=True)
        if submitted:
            if not uname or not pwd:
                st.error("Please enter username and password.")
            else:
                try:
                    r = _api_post("/auth/login",
                        json={"username": uname.strip().lower(), "password": pwd},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        st.session_state.auth_token    = data["token"]
                        st.session_state.auth_user_id  = data["user_id"]
                        st.session_state.auth_username = data["username"]
                        st.session_state.auth_role     = data.get("role", "user")
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", "Login failed"))
                except Exception as e:
                    st.error(f"Cannot reach backend: {e}")

    with tab_register:
        with st.form("register_form"):
            new_user  = st.text_input("Choose a username")
            new_email = st.text_input("Email (optional)")
            new_pwd   = st.text_input("Choose a password (min 6 chars)", type="password")
            new_pwd2  = st.text_input("Confirm password", type="password")
            reg_submitted = st.form_submit_button("Create Account", use_container_width=True)
        if reg_submitted:
            if not new_user or not new_pwd:
                st.error("Username and password are required.")
            elif new_pwd != new_pwd2:
                st.error("Passwords do not match.")
            elif len(new_pwd) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    r = _api_post("/auth/register",
                        json={"username": new_user.strip().lower(),
                              "password": new_pwd, "email": new_email.strip()},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        data = r.json()
                        st.session_state.auth_token    = data["token"]
                        st.session_state.auth_user_id  = data["user_id"]
                        st.session_state.auth_username = data["username"]
                        st.session_state.auth_role     = data.get("role", "user")
                        st.success(f"Account created! Welcome, {data['username']} 🎉")
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", "Registration failed"))
                except Exception as e:
                    st.error(f"Cannot reach backend: {e}")

# ---------------------------------------------------------------------------
# Auth gate — show login page until user is authenticated
# ---------------------------------------------------------------------------
if "auth_token" not in st.session_state:
    st.session_state.auth_token    = ""
    st.session_state.auth_user_id  = ""
    st.session_state.auth_username = ""
    st.session_state.auth_role     = "user"

if not st.session_state.auth_token:
    _show_login_page()
    st.stop()   # nothing below runs until logged in

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GAP_LABELS = {
    "no_bis":        "No BIS Licence",
    "no_gst":        "No GST Registration",
    "no_iec":        "No IEC",
    "mca_not_found": "Not on MCA",
    "mca_inactive":  "Company Struck Off",
}

CHANNEL_TYPES = [
    "Manufacturer", "Importer", "Trader",
    "Wholesaler", "Distributor", "Retailer",
]

ALL_INDUSTRIES = [
    "Electronics", "Pharmaceuticals", "Textiles", "Chemicals", "Machinery",
    "Food & Beverage", "Automotive", "Construction", "IT & Software",
    "Healthcare", "Logistics", "Agriculture", "Energy", "Retail",
]

# Country → States / Regions
COUNTRY_STATES = {
    "India": [
        "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
        "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
        "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
        "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
        "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
        "West Bengal", "Delhi", "Jammu & Kashmir", "Ladakh", "Chandigarh",
        "Puducherry", "Lakshadweep", "Andaman & Nicobar",
    ],
    "UAE": [
        "Dubai", "Abu Dhabi", "Sharjah", "Ajman",
        "Ras Al Khaimah", "Fujairah", "Umm Al Quwain",
    ],
    "USA": [
        "Alabama","Alaska","Arizona","Arkansas","California","Colorado",
        "Connecticut","Delaware","Florida","Georgia","Hawaii","Idaho",
        "Illinois","Indiana","Iowa","Kansas","Kentucky","Louisiana",
        "Maine","Maryland","Massachusetts","Michigan","Minnesota",
        "Mississippi","Missouri","Montana","Nebraska","Nevada",
        "New Hampshire","New Jersey","New Mexico","New York",
        "North Carolina","North Dakota","Ohio","Oklahoma","Oregon",
        "Pennsylvania","Rhode Island","South Carolina","South Dakota",
        "Tennessee","Texas","Utah","Vermont","Virginia","Washington",
        "West Virginia","Wisconsin","Wyoming",
    ],
    "UK": [
        "England","Scotland","Wales","Northern Ireland",
        "London","Manchester","Birmingham","Leeds","Glasgow",
        "Liverpool","Bristol","Sheffield","Edinburgh",
    ],
    "Germany": [
        "Baden-Württemberg","Bavaria","Berlin","Brandenburg","Bremen",
        "Hamburg","Hesse","Lower Saxony","Mecklenburg-Vorpommern",
        "North Rhine-Westphalia","Rhineland-Palatinate","Saarland",
        "Saxony","Saxony-Anhalt","Schleswig-Holstein","Thuringia",
    ],
    "Canada": [
        "Alberta","British Columbia","Manitoba","New Brunswick",
        "Newfoundland and Labrador","Nova Scotia","Ontario",
        "Prince Edward Island","Quebec","Saskatchewan",
        "Northwest Territories","Nunavut","Yukon",
    ],
    "Australia": [
        "New South Wales","Victoria","Queensland","South Australia",
        "Western Australia","Tasmania","ACT","Northern Territory",
    ],
    "Singapore": [
        "Central Region","East Region","North Region",
        "North-East Region","West Region",
    ],
    "China": [
        "Beijing","Shanghai","Guangdong","Zhejiang","Jiangsu",
        "Shandong","Sichuan","Hubei","Hunan","Fujian",
        "Anhui","Henan","Liaoning","Chongqing","Tianjin",
    ],
    "Italy": [
        "Lombardy","Lazio","Campania","Sicily","Veneto",
        "Emilia-Romagna","Piedmont","Apulia","Tuscany","Calabria",
    ],
    "France": [
        "Île-de-France","Auvergne-Rhône-Alpes","Nouvelle-Aquitaine",
        "Occitanie","Hauts-de-France","Grand Est",
        "Provence-Alpes-Côte d'Azur","Pays de la Loire","Normandy","Brittany",
    ],
    "Japan": [
        "Tokyo","Osaka","Kanagawa","Aichi","Saitama","Chiba",
        "Hyogo","Hokkaido","Fukuoka","Shizuoka",
    ],
}

ALL_COUNTRIES = ["Any"] + sorted(COUNTRY_STATES.keys())

# ---------------------------------------------------------------------------
# Session state — initialise ALL keys before any widget is rendered
# ---------------------------------------------------------------------------
_DEFAULTS = {
    # search / job state
    "active_job_id":         "",
    "active_query":          "",
    "live_results":          [],
    "live_cursor":           0,
    "new_result_indexes":    [],
    "notified_jobs":         [],
    "mlt_results":           [],
    "mlt_seed_result_index": None,
    "mlt_seed_company":      "",
    # search filter state  (owned here, not by widgets)
    "sf_query":              "",
    "sf_country":            "Any",
    "sf_state":              "Any",
    "sf_industry":           "Any",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Display column definitions
# ---------------------------------------------------------------------------
DISPLAY_COLS = [
    "company", "city", "country_detected", "industry_detected", "product_type",
    "channel_type", "company_size", "incorporation_date", "importance",
    "final_score", "compliance_gaps", "bis_certified", "gst_registered",
    "iec_found", "mca_active", "contact_person", "contact_email", "email",
    "phone", "linkedin_url", "active_website", "website", "ai_summary",
    "products", "mca_company_type", "domain_authority", "contact_presence",
    "semantic_score", "keyword_score", "country_filter", "searched_query",
    "created_at",
]

COLUMN_LABELS = {
    "company":            "Company Name",
    "city":               "City / State",
    "country_detected":   "Country",
    "industry_detected":  "Industry",
    "product_type":       "Product Type",
    "channel_type":       "Channel Type",
    "company_size":       "Company Size",
    "incorporation_date": "Incorporated",
    "importance":         "Importance",
    "final_score":        "Score",
    "compliance_gaps":    "Compliance Gaps",
    "bis_certified":      "BIS",
    "gst_registered":     "GST",
    "iec_found":          "IEC",
    "mca_active":         "MCA Active",
    "contact_person":     "Contact Person",
    "contact_email":      "Contact Email",
    "email":              "Email",
    "phone":              "Phone",
    "linkedin_url":       "LinkedIn",
    "active_website":     "Active Website",
    "website":            "Website",
    "ai_summary":         "AI Summary",
    "products":           "Products",
    "mca_company_type":   "Company Type (MCA)",
    "domain_authority":   "Domain Auth.",
    "contact_presence":   "Contact Score",
    "semantic_score":     "Semantic",
    "keyword_score":      "Keyword",
    "country_filter":     "Filter Country",
    "searched_query":     "Query",
    "created_at":         "Found At",
}

# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

def _bool_icon(val) -> str:
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"


def _prep_df(df_in: pd.DataFrame) -> pd.DataFrame:
    df = df_in[[c for c in DISPLAY_COLS if c in df_in.columns]].copy()
    df.rename(columns={c: COLUMN_LABELS.get(c, c) for c in df.columns}, inplace=True)

    label_gaps = COLUMN_LABELS["compliance_gaps"]
    if label_gaps in df.columns:
        df[label_gaps] = df[label_gaps].apply(
            lambda g: ", ".join(GAP_LABELS.get(x, x) for x in g)
            if isinstance(g, list) else ""
        )
    label_products = COLUMN_LABELS["products"]
    if label_products in df.columns:
        df[label_products] = df[label_products].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p, list) else str(p or "")
        )
    for col_key in ["bis_certified", "gst_registered", "iec_found", "mca_active"]:
        col_label = COLUMN_LABELS[col_key]
        if col_label in df.columns:
            df[col_label] = df[col_label].apply(_bool_icon)
    for col_key in ["final_score", "semantic_score", "keyword_score",
                    "domain_authority", "contact_presence"]:
        col_label = COLUMN_LABELS[col_key]
        if col_label in df.columns:
            df[col_label] = pd.to_numeric(df[col_label], errors="coerce").round(3)
    score_label = COLUMN_LABELS["final_score"]
    if score_label in df.columns:
        df = df.sort_values(score_label, ascending=False)
    return df


def _row_style(row):
    imp     = str(row.get("Importance", "")).lower()
    gaps    = str(row.get("Compliance Gaps", ""))
    has_gap = bool(gaps and gaps not in ("", "nan", "None", "[]"))
    if has_gap:
        bg, color = "#4a0d0d", "#ffb3b3"
    elif imp == "high":
        bg, color = "#0d3320", "#6dffb0"
    elif imp == "medium":
        bg, color = "#3d2200", "#ffd980"
    else:
        bg, color = "#1a1f2e", "#a0aec0"
    return [f"background-color: {bg}; color: {color}"] * len(row)


def _show_table(df_in: pd.DataFrame, key_suffix: str = "") -> None:
    if df_in.empty:
        st.info("No leads in this category yet.")
        return
    df = _prep_df(df_in)
    styled = (
        df.style
        .apply(_row_style, axis=1)
        .set_properties(**{"font-size": "13px", "font-family": "monospace",
                           "border-color": "#2d3748"})
        .set_table_styles([
            {"selector": "th", "props": [
                ("background-color", "#0f172a"), ("color", "#e2e8f0"),
                ("font-size", "12px"), ("font-weight", "700"),
                ("text-transform", "uppercase"), ("letter-spacing", "0.05em"),
                ("padding", "8px 12px"), ("border-bottom", "2px solid #334155"),
            ]},
            {"selector": "td", "props": [
                ("padding", "7px 12px"), ("border-bottom", "1px solid #1e293b"),
                ("max-width", "260px"), ("overflow", "hidden"),
                ("text-overflow", "ellipsis"), ("white-space", "nowrap"),
            ]},
            {"selector": "tr:hover td", "props": [("filter", "brightness(1.25)")]},
        ])
    )
    st.dataframe(styled, use_container_width=True,
                 height=min(60 + len(df) * 38, 700))
    csv_df = df_in[[c for c in DISPLAY_COLS if c in df_in.columns]].copy()
    for col in ["compliance_gaps", "products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(
                lambda v: ", ".join(v) if isinstance(v, list) else str(v or ""))
    csv = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", csv,
                       f"leads_{key_suffix}.csv", "text/csv",
                       key=f"dl_{key_suffix}_{len(df_in)}")


def _tab_metrics(df_in: pd.DataFrame) -> None:
    if df_in.empty:
        return
    high_n = int((df_in.get("importance", pd.Series(dtype=str))
                  .astype(str).str.lower() == "high").sum()) \
             if "importance" in df_in.columns else 0
    gap_n  = int(df_in["compliance_gaps"].apply(
                 lambda g: isinstance(g, list) and len(g) > 0).sum()) \
             if "compliance_gaps" in df_in.columns else 0
    mfg_n  = int((df_in.get("channel_type", pd.Series(dtype=str))
                  .astype(str) == "Manufacturer").sum()) \
             if "channel_type" in df_in.columns else 0
    imp_n  = int((df_in.get("channel_type", pd.Series(dtype=str))
                  .astype(str) == "Importer").sum()) \
             if "channel_type" in df_in.columns else 0
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total",            len(df_in))
    m2.metric("🟢 High",          high_n)
    m3.metric("🔴 With Gaps",     gap_n)
    m4.metric("🏭 Manufacturers", mfg_n)
    m5.metric("📦 Importers",     imp_n)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _do_clear_filters():
    """Reset filter state — called via on_click so no post-widget assignment."""
    st.session_state.sf_industry = "Any"
    st.session_state.sf_country  = "Any"
    st.session_state.sf_state    = "Any"


def _start_background_search(search_query, continue_search=False, reset_results=False):
    # Build the country_filter string from session state
    cf = "" if st.session_state.sf_country == "Any" else st.session_state.sf_country.lower()
    try:
        response = _api_post("/search/start",
            params={
                "query":              search_query,
                "continue_search":    str(continue_search).lower(),
                "scan_all_remaining": str(st.session_state.get("scan_all_remaining", False)).lower(),
                "country_filter":     cf,
                "trusted_only":       str(st.session_state.get("trusted_only", False)).lower(),
            },
            timeout=30,
        )
        if response.status_code != 200:
            st.error("Backend error while starting background search")
            return False
        data = response.json()
        st.session_state.active_job_id = data.get("job_id", "")
        st.session_state.active_query  = search_query
        if reset_results:
            for k in ["live_results", "new_result_indexes", "mlt_results"]:
                st.session_state[k] = []
            st.session_state.live_cursor           = 0
            st.session_state.mlt_seed_result_index = None
            st.session_state.mlt_seed_company      = ""
        st.success("Background search started")
        return True
    except Exception as e:
        st.error(f"Cannot reach backend at {API} — {e}")
        return False


def _seed_by_result_index(rows, result_index):
    for row in rows:
        if int(row.get("result_index", -1)) == int(result_index):
            return row
    return {}


def _build_more_like_query(seed_row):
    searched_query = str(seed_row.get("searched_query", "")).strip()
    products       = seed_row.get("products", [])
    ai_summary     = str(seed_row.get("ai_summary", "")).strip()
    company        = str(seed_row.get("company", "")).strip()
    product_text   = ""
    if isinstance(products, list):
        product_text = " ".join(str(p).strip() for p in products[:2] if str(p).strip())
    if not product_text and ai_summary:
        stop_words = {"about","their","there","which","where","while","would","could",
                      "company","companies","service","services","business","global",
                      "offers","offer","provides","provide","based","using","with"}
        tokens = [t for t in re.findall(r"[a-zA-Z]{4,}", ai_summary.lower())
                  if t not in stop_words]
        product_text = " ".join(list(dict.fromkeys(tokens))[:4])
    q = " ".join(p for p in [searched_query, product_text] if p).strip()
    return q or company


# ---------------------------------------------------------------------------
# Page header + logout
# ---------------------------------------------------------------------------
hcol1, hcol2 = st.columns([7, 1])
with hcol1:
    st.title("🌐 Global B2B Lead Discovery Engine")
    st.caption(
        "Background search · Enriched profiles · Compliance gap detection  |  "
        f"👤 **{st.session_state.auth_username}**"
    )
with hcol2:
    if st.button("🚪 Logout", use_container_width=True):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

# Backend connection status
with st.expander("🔌 Backend Connection", expanded=False):
    st.code(f"Backend URL: {API}", language=None)
    try:
        ping = requests.get(f"{API}/", timeout=8)
        if ping.status_code == 200:
            st.success(f"✅ Connected — {ping.json().get('service','')}")
            try:
                prov   = requests.get(f"{API}/llm/provider", timeout=5).json()
                pname  = prov.get("provider","none").upper()
                pmodel = prov.get("model","—")
                if prov.get("status") == "active":
                    st.info(f"🤖 LLM: **{pname}** — `{pmodel}`")
                else:
                    st.warning("⚠️ No LLM API key set on backend")
            except Exception:
                pass
        else:
            st.error(f"❌ Backend returned HTTP {ping.status_code}")
    except Exception as e:
        st.error(f"❌ Cannot reach backend: {e}")

# ---------------------------------------------------------------------------
# Colour legend
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;font-size:13px;">
      <span style="background:#0d3320;color:#6dffb0;padding:3px 12px;border-radius:4px;">🟢 High importance</span>
      <span style="background:#3d2200;color:#ffd980;padding:3px 12px;border-radius:4px;">🟡 Medium importance</span>
      <span style="background:#4a0d0d;color:#ffb3b3;padding:3px 12px;border-radius:4px;">🔴 Has compliance gap</span>
      <span style="background:#1a1f2e;color:#a0aec0;padding:3px 12px;border-radius:4px;">⚪ Low / unchecked</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ===========================================================================
# SEARCH FILTERS  (single block — no sidebar, no duplication)
# ===========================================================================
st.markdown("### 🔍 Search")

# Row 1: query text input
query = st.text_input(
    "Search query",
    value=st.session_state.sf_query,
    placeholder="e.g. electronics importers india",
    key="sf_query",               # bound to session state directly
)

# Row 2: Country | State/Region | Industry  — three dropdowns in one row
fc1, fc2, fc3 = st.columns(3)

with fc1:
    sel_country = st.selectbox(
        "🌍 Country",
        options=ALL_COUNTRIES,
        index=ALL_COUNTRIES.index(st.session_state.sf_country)
              if st.session_state.sf_country in ALL_COUNTRIES else 0,
        key="sf_country",
    )

# State options depend on which country is selected
state_options = ["Any"] + COUNTRY_STATES.get(sel_country, []) if sel_country != "Any" else ["Any"]

# If the saved state is no longer valid for the new country, reset it
if st.session_state.sf_state not in state_options:
    st.session_state.sf_state = "Any"

with fc2:
    sel_state = st.selectbox(
        f"📍 State / Region",
        options=state_options,
        index=state_options.index(st.session_state.sf_state)
              if st.session_state.sf_state in state_options else 0,
        key="sf_state",
        disabled=(sel_country == "Any"),
    )

with fc3:
    sel_industry = st.selectbox(
        "🏭 Industry",
        options=["Any"] + ALL_INDUSTRIES,
        index=(["Any"] + ALL_INDUSTRIES).index(st.session_state.sf_industry)
              if st.session_state.sf_industry in ["Any"] + ALL_INDUSTRIES else 0,
        key="sf_industry",
    )

# Row 3: options checkboxes
col_a, col_b = st.columns(2)
with col_a:
    scan_all_remaining = st.checkbox("Continue until no pages", value=False,
                                     key="scan_all_remaining")
with col_b:
    trusted_only = st.checkbox("Trusted domains only", value=False,
                               key="trusted_only")

# Row 4: action buttons
col1, col2, col3, col4 = st.columns(4)

# Build the country_filter string sent to backend
country_filter = "" if sel_country == "Any" else sel_country.lower()
# Append state to query if selected
state_suffix = "" if (not sel_state or sel_state == "Any") else sel_state
industry_suffix = "" if (not sel_industry or sel_industry == "Any") else sel_industry

def _build_search_query() -> str:
    """Combine text query + industry + state into the final query string."""
    parts = [query.strip()]
    if industry_suffix and industry_suffix.lower() not in query.lower():
        parts.append(industry_suffix)
    if state_suffix and state_suffix.lower() not in query.lower():
        parts.append(state_suffix)
    if country_filter and country_filter not in query.lower():
        parts.append(country_filter)
    return " ".join(p for p in parts if p).strip()

with col1:
    if st.button("🔍 Start Search", use_container_width=True):
        final_query = _build_search_query()
        if not final_query:
            st.warning("Please enter a search query")
        else:
            _start_background_search(final_query, continue_search=False, reset_results=True)

with col2:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

with col3:
    # Clear filters — use on_click callback to avoid post-widget state assignment
    st.button("🗑️ Clear Filters", use_container_width=True,
              on_click=_do_clear_filters)

with col4:
    if st.button("🗑️ Clear All Leads", use_container_width=True):
        try:
            _api_delete("/clear", timeout=15)
            for k, v in _DEFAULTS.items():
                st.session_state[k] = v
            st.warning("All leads cleared")
            st.rerun()
        except Exception as e:
            st.error(f"Cannot reach backend: {e}")

# Show active filter summary inline (small, unobtrusive)
active_parts = []
if sel_country != "Any":
    active_parts.append(f"**Country:** {sel_country}")
if sel_state and sel_state != "Any":
    active_parts.append(f"**State:** {sel_state}")
if sel_industry != "Any":
    active_parts.append(f"**Industry:** {sel_industry}")
if active_parts:
    st.caption("🔎 Active filters: " + "  ·  ".join(active_parts))

# Compliance enrichment
with st.expander("🔬 Run Compliance Checks on Saved Leads", expanded=False):
    st.caption("Runs BIS · GST · DGFT · MCA checks and also fills in incorporation date and company type.")
    enrich_limit = st.slider("Max leads to check", 10, 200, 50, key="enrich_limit")
    if st.button("▶️ Start Compliance Checks", key="enrich_btn"):
        try:
            r = _api_post("/leads/enrich-compliance",
                params={"limit": enrich_limit, "country_filter": country_filter},
                timeout=300,
            )
            if r.status_code == 200:
                st.success(f"Done — {r.json().get('checked', 0)} leads checked. Refresh to see results.")
            else:
                st.error("Compliance check failed")
        except Exception as e:
            st.error(f"Cannot reach backend: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Live background job
# ---------------------------------------------------------------------------
if st.session_state.active_job_id:
    st.subheader("🔴 Live Search Results")

    status = None
    try:
        sr = _api_get("/search/status/{st.session_state.active_job_id}", timeout=20)
        if sr.status_code == 200:
            status = sr.json()
    except Exception as e:
        st.error(f"Backend not reachable: {e}")

    if status:
        try:
            rr = _api_get("/search/results/{st.session_state.active_job_id}",
                params={"since": st.session_state.live_cursor}, timeout=20)
            if rr.status_code == 200:
                payload   = rr.json()
                new_items = payload.get("results", [])
                if new_items:
                    st.session_state.live_results.extend(new_items)
                st.session_state.new_result_indexes = [
                    i.get("result_index") for i in new_items
                    if i.get("result_index") is not None
                ]
                st.session_state.live_cursor = int(
                    payload.get("next_since", st.session_state.live_cursor))
        except Exception as e:
            st.error(f"Backend not reachable: {e}")

        company_live = [x for x in st.session_state.live_results
                        if x.get("source") != "linkedin_semantic"]

        high_n   = sum(1 for x in company_live if str(x.get("importance","")).lower()=="high")
        medium_n = sum(1 for x in company_live if str(x.get("importance","")).lower()=="medium")
        gap_n    = sum(1 for x in company_live
                       if isinstance(x.get("compliance_gaps"), list)
                       and len(x["compliance_gaps"]) > 0)
        mfg_n    = sum(1 for x in company_live if x.get("channel_type") == "Manufacturer")
        imp_n    = sum(1 for x in company_live if x.get("channel_type") == "Importer")

        c1, c2, c3, c4, c5, c6 = st.columns(6)
        c1.metric("Results",          len(company_live))
        c2.metric("🟢 High",          high_n)
        c3.metric("🟡 Medium",         medium_n)
        c4.metric("🔴 Has Gaps",       gap_n)
        c5.metric("🏭 Manufacturers",  mfg_n)
        c6.metric("📦 Importers",      imp_n)

        st.caption(
            f"Status: **{status.get('status','—')}** | "
            f"Pages scanned: {status.get('pages_scanned',0)} | "
            f"Saved total: {status.get('saved_total',0)}"
        )

        if company_live:
            live_df = pd.DataFrame(company_live)
            _show_table(live_df, key_suffix="live")

            st.markdown("---")
            st.markdown("#### 🔁 Find Similar Leads")
            selectable = [r for r in company_live if r.get("result_index") is not None]
            if selectable:
                options = {}
                for row in sorted(selectable,
                                  key=lambda r: float(r.get("final_score",0) or 0),
                                  reverse=True):
                    idx   = int(row.get("result_index"))
                    name  = row.get("company","Unknown")
                    score = float(row.get("final_score",0) or 0)
                    gaps  = row.get("compliance_gaps",[])
                    tag   = " ⚠️" if isinstance(gaps,list) and gaps else ""
                    label = f"#{idx} | {name}{tag} | {score:.3f}"
                    options[label] = idx

                selected_label        = st.selectbox("Pick a lead", list(options.keys()),
                                                     key="mlt_lead")
                selected_result_index = options[selected_label]
                selected_seed         = _seed_by_result_index(selectable, selected_result_index)
                similar_limit         = st.slider("How many similar?", 3, 20, 8, key="mlt_lim")

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Find Similar (Current Results)", key="mlt_btn"):
                        try:
                            resp = _api_get("/search/more-like-this/{st.session_state.active_job_id}",
                                params={"result_index": selected_result_index,
                                        "limit": similar_limit},
                                timeout=30)
                            if resp.status_code == 200:
                                st.session_state.mlt_results           = resp.json().get("results",[])
                                st.session_state.mlt_seed_result_index = selected_result_index
                                st.session_state.mlt_seed_company      = selected_seed.get("company","")
                            else:
                                st.error("Could not find similar leads")
                        except Exception as e:
                            st.error(f"Backend not reachable: {e}")
                with b2:
                    if st.button("New Search Like This Lead", key="mlt_new"):
                        gq = _build_more_like_query(selected_seed)
                        if not gq:
                            st.warning("Could not build query")
                        else:
                            if _start_background_search(gq, reset_results=True):
                                st.info(f'New search: "{gq}"')
                                st.rerun()

                if st.session_state.mlt_results:
                    st.caption(f"Similar to: {st.session_state.mlt_seed_company}")
                    sim_df = pd.DataFrame(st.session_state.mlt_results)
                    _show_table(sim_df, key_suffix="similar")

        sv = status.get("status")
        if sv in ("running", "queued"):
            st.info("⏳ Search running — refreshing automatically…")
            time.sleep(POLL_SECONDS)
            st.rerun()
        elif sv == "completed":
            jid = status.get("job_id","")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast("✅ Search complete")
                st.session_state.notified_jobs.append(jid)
            if status.get("ask_continue"):
                st.warning("Batch complete. Continue to next page?")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("Yes, Continue"):
                        _start_background_search(
                            st.session_state.active_query,
                            continue_search=True, reset_results=False)
                        st.rerun()
                with cc2:
                    if st.button("No, Stop"):
                        st.session_state.active_job_id = ""
                        st.success("Search stopped")
            else:
                st.success("✅ Search complete.")
        elif sv == "failed":
            st.error(f"Search failed: {status.get('error','Unknown')}")

st.divider()

# ---------------------------------------------------------------------------
# Saved Leads
# ---------------------------------------------------------------------------
st.subheader("📁 Saved Leads")

try:
    lead_params = {"limit": 1000}
    if country_filter:
        lead_params["country_filter"] = country_filter
    res  = _api_get("/leads", params=lead_params, timeout=20)
    data = res.json()
except Exception as e:
    st.error(f"Backend not reachable: {e}")
    st.markdown(f"**URL:** `{API}/leads`")
    st.stop()

# Compliance gap summary cards
try:
    gp = {"country_filter": country_filter} if country_filter else {}
    gr       = _api_get("/leads/gap-summary", params=gp, timeout=10)
    gap_summ = gr.json() if gr.status_code == 200 else {}
except Exception:
    gap_summ = {}

if gap_summ:
    st.markdown("##### Compliance Gap Summary")
    gcols = st.columns(min(len(gap_summ), 5) or 1)
    for i, (gc, cnt) in enumerate(gap_summ.items()):
        gcols[i % len(gcols)].metric(GAP_LABELS.get(gc, gc), cnt)

# Channel type summary cards
try:
    cp           = {"country_filter": country_filter} if country_filter else {}
    cr           = _api_get("/leads/channel-summary", params=cp, timeout=10)
    channel_summ = cr.json() if cr.status_code == 200 else {}
except Exception:
    channel_summ = {}

if channel_summ:
    st.markdown("##### Channel Type Breakdown")
    ch_icons = {
        "Manufacturer": "🏭", "Importer": "📦", "Trader": "🤝",
        "Wholesaler": "🏢", "Distributor": "🚚", "Retailer": "🛍️",
    }
    ccols = st.columns(min(len(channel_summ), 6) or 1)
    for i, (ch, cnt) in enumerate(channel_summ.items()):
        ccols[i % len(ccols)].metric(f"{ch_icons.get(ch,'')} {ch}", cnt)

if data:
    df = pd.DataFrame(data)

    company_df  = df[df["source"] != "linkedin_semantic"].copy() \
                  if "source" in df.columns else df.copy()
    linkedin_df = df[df["source"] == "linkedin_semantic"].copy() \
                  if "source" in df.columns else pd.DataFrame()

    def _filter_gap(df_in, gap_code):
        if "compliance_gaps" not in df_in.columns:
            return pd.DataFrame()
        return df_in[df_in["compliance_gaps"].apply(
            lambda g: isinstance(g, list) and gap_code in g)].copy()

    def _filter_any_gap(df_in):
        if "compliance_gaps" not in df_in.columns:
            return pd.DataFrame()
        return df_in[df_in["compliance_gaps"].apply(
            lambda g: isinstance(g, list) and len(g) > 0)].copy()

    def _filter_channel(df_in, channel):
        if "channel_type" not in df_in.columns:
            return pd.DataFrame()
        return df_in[df_in["channel_type"].astype(str) == channel].copy()

    (tab_all, tab_gaps, tab_mfg, tab_imp, tab_trade,
     tab_no_bis, tab_no_iec, tab_no_gst) = st.tabs([
        "📋 All Leads",
        "🎯 Compliance Gaps",
        "🏭 Manufacturers",
        "📦 Importers",
        "🤝 Traders / Dist.",
        "🔴 No BIS",
        "📦 No IEC",
        "🧾 No GST",
    ])

    with tab_all:
        _tab_metrics(company_df)
        _show_table(company_df, key_suffix="all")

    with tab_gaps:
        st.info("🎯 Companies with at least one compliance gap — highest priority prospects.")
        gdf = _filter_any_gap(company_df)
        _tab_metrics(gdf)
        _show_table(gdf, key_suffix="gaps")

    with tab_mfg:
        st.info("🏭 Manufacturers — companies that produce goods themselves.")
        mdf = _filter_channel(company_df, "Manufacturer")
        _tab_metrics(mdf)
        _show_table(mdf, key_suffix="manufacturer")

    with tab_imp:
        st.info("📦 Importers — companies that bring goods from overseas.")
        idf = _filter_channel(company_df, "Importer")
        _tab_metrics(idf)
        _show_table(idf, key_suffix="importer")

    with tab_trade:
        st.info("🤝 Traders, Distributors, Wholesalers, Retailers.")
        tdf = pd.concat([
            _filter_channel(company_df, "Trader"),
            _filter_channel(company_df, "Distributor"),
            _filter_channel(company_df, "Wholesaler"),
            _filter_channel(company_df, "Retailer"),
        ], ignore_index=True) if not company_df.empty else pd.DataFrame()
        _tab_metrics(tdf)
        _show_table(tdf, key_suffix="traders")

    with tab_no_bis:
        st.info("🔴 No BIS licence — cannot legally sell regulated products in India.")
        gdf = _filter_gap(company_df, "no_bis")
        _tab_metrics(gdf)
        _show_table(gdf, key_suffix="no_bis")

    with tab_no_iec:
        st.info("📦 No IEC — cannot legally import or export.")
        gdf = _filter_gap(company_df, "no_iec")
        _tab_metrics(gdf)
        _show_table(gdf, key_suffix="no_iec")

    with tab_no_gst:
        st.info("🧾 No GST registration — needs registration and filing support.")
        gdf = _filter_gap(company_df, "no_gst")
        _tab_metrics(gdf)
        _show_table(gdf, key_suffix="no_gst")

    if not linkedin_df.empty:
        with st.expander("👤 LinkedIn Profiles"):
            linkedin_cols = ["name","profile","snippet","searched_query","created_at"]
            ld = linkedin_df[[c for c in linkedin_cols if c in linkedin_df.columns]]
            st.dataframe(ld, use_container_width=True)

else:
    st.info("No leads yet. Enter a query above and click **Start Search**.")
