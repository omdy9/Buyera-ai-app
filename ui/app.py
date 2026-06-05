import os
import time
import re
import json

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

st.set_page_config(
    page_title="Buyera AI — B2B Lead Discovery",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={"About": "Global B2B Lead Discovery Engine by Buyera AI"},
)

# ---------------------------------------------------------------------------
# Custom CSS — dark professional theme
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* Main background */
.stApp { background: #0a0e1a; }

/* Sidebar */
[data-testid="stSidebar"] {
    background: #0f1629;
    border-right: 1px solid #1e2d4a;
}
[data-testid="stSidebar"] .stMarkdown h3 {
    color: #4f8ef7;
    font-size: 0.85rem;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 0.5rem;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: #111827;
    border: 1px solid #1e2d4a;
    border-radius: 10px;
    padding: 12px 16px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.4);
}
[data-testid="metric-container"] [data-testid="stMetricValue"] {
    font-size: 1.8rem;
    font-weight: 700;
    color: #e2e8f0;
}
[data-testid="metric-container"] [data-testid="stMetricLabel"] {
    font-size: 0.75rem;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Buttons */
.stButton > button {
    background: linear-gradient(135deg, #1e3a5f, #2563eb);
    color: white;
    border: none;
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.2s;
}
.stButton > button:hover {
    background: linear-gradient(135deg, #2563eb, #3b82f6);
    transform: translateY(-1px);
    box-shadow: 0 4px 12px rgba(37,99,235,0.4);
}

/* Search button special */
.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #059669, #10b981);
}

/* Tabs */
[data-testid="stTabs"] [role="tab"] {
    color: #94a3b8;
    font-size: 0.85rem;
    font-weight: 500;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #4f8ef7;
    border-bottom: 2px solid #4f8ef7;
}

/* Input fields */
.stTextInput > div > div > input,
.stSelectbox > div > div {
    background: #111827 !important;
    border: 1px solid #1e2d4a !important;
    border-radius: 8px !important;
    color: #e2e8f0 !important;
}

/* Expander */
[data-testid="stExpander"] {
    background: #111827;
    border: 1px solid #1e2d4a;
    border-radius: 10px;
}

/* Status badges */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.75rem;
    font-weight: 600;
}
.badge-green  { background: #064e3b; color: #6ee7b7; }
.badge-yellow { background: #78350f; color: #fcd34d; }
.badge-red    { background: #7f1d1d; color: #fca5a5; }
.badge-blue   { background: #1e3a5f; color: #93c5fd; }
.badge-grey   { background: #1f2937; color: #9ca3af; }

/* Card style */
.lead-card {
    background: #111827;
    border: 1px solid #1e2d4a;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 12px;
    transition: border-color 0.2s;
}
.lead-card:hover { border-color: #4f8ef7; }

/* Score bar */
.score-bar-bg {
    background: #1f2937;
    border-radius: 4px;
    height: 6px;
    margin-top: 4px;
}
.score-bar-fill {
    height: 6px;
    border-radius: 4px;
    background: linear-gradient(90deg, #2563eb, #10b981);
}

/* Divider */
hr { border-color: #1e2d4a !important; }

/* Info/success/warning boxes */
.stAlert { border-radius: 10px; }

/* Table */
.dataframe { font-size: 12px !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: #0a0e1a; }
::-webkit-scrollbar-thumb { background: #1e2d4a; border-radius: 3px; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def _auth_headers() -> dict:
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


# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------
def _show_login_page():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;padding:40px 0 20px">
            <h1 style="font-size:2.5rem;background:linear-gradient(135deg,#4f8ef7,#10b981);
                -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
                🌐 Buyera AI
            </h1>
            <p style="color:#64748b;font-size:1rem;">Global B2B Lead Discovery Engine</p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_register = st.tabs(["🔑 Sign In", "📝 Create Account"])

        with tab_login:
            with st.form("login_form"):
                uname = st.text_input("Username", placeholder="your_username")
                pwd   = st.text_input("Password", type="password", placeholder="••••••••")
                submitted = st.form_submit_button("Sign In", use_container_width=True)
            if submitted:
                if not uname or not pwd:
                    st.error("Please enter username and password.")
                else:
                    try:
                        r = _api_post("/auth/login",
                            json={"username": uname.strip().lower(), "password": pwd},
                            timeout=10)
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
                new_user  = st.text_input("Username", placeholder="choose_username")
                new_email = st.text_input("Email (optional)", placeholder="you@company.com")
                new_pwd   = st.text_input("Password (min 6 chars)", type="password")
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
                            timeout=10)
                        if r.status_code == 200:
                            data = r.json()
                            st.session_state.auth_token    = data["token"]
                            st.session_state.auth_user_id  = data["user_id"]
                            st.session_state.auth_username = data["username"]
                            st.session_state.auth_role     = data.get("role", "user")
                            st.success(f"Welcome, {data['username']}! 🎉")
                            st.rerun()
                        else:
                            st.error(r.json().get("detail", "Registration failed"))
                    except Exception as e:
                        st.error(f"Cannot reach backend: {e}")

# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------
if "auth_token" not in st.session_state:
    st.session_state.auth_token    = ""
    st.session_state.auth_user_id  = ""
    st.session_state.auth_username = ""
    st.session_state.auth_role     = "user"

if not st.session_state.auth_token:
    _show_login_page()
    st.stop()

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

ALL_INDUSTRIES = [
    "Electronics", "Pharmaceuticals", "Textiles", "Chemicals", "Machinery",
    "Food & Beverage", "Automotive", "Construction", "IT & Software",
    "Healthcare", "Logistics", "Agriculture", "Energy", "Retail",
]

COUNTRY_STATES = {
    "India": [
        "Andhra Pradesh","Arunachal Pradesh","Assam","Bihar","Chhattisgarh",
        "Goa","Gujarat","Haryana","Himachal Pradesh","Jharkhand","Karnataka",
        "Kerala","Madhya Pradesh","Maharashtra","Manipur","Meghalaya","Mizoram",
        "Nagaland","Odisha","Punjab","Rajasthan","Sikkim","Tamil Nadu","Telangana",
        "Tripura","Uttar Pradesh","Uttarakhand","West Bengal","Delhi",
        "Jammu & Kashmir","Ladakh","Chandigarh","Puducherry",
    ],
    "UAE":       ["Dubai","Abu Dhabi","Sharjah","Ajman","Ras Al Khaimah","Fujairah"],
    "USA":       ["California","New York","Texas","Florida","Illinois","Washington","Georgia"],
    "UK":        ["England","Scotland","Wales","Northern Ireland","London","Manchester"],
    "Germany":   ["Bavaria","Berlin","Hamburg","North Rhine-Westphalia","Baden-Württemberg"],
    "Canada":    ["Ontario","Quebec","British Columbia","Alberta","Manitoba"],
    "Australia": ["New South Wales","Victoria","Queensland","South Australia","Western Australia"],
    "Singapore": ["Central Region","East Region","North Region","West Region"],
    "China":     ["Beijing","Shanghai","Guangdong","Zhejiang","Jiangsu"],
    "Italy":     ["Lombardy","Lazio","Veneto","Emilia-Romagna","Piedmont"],
    "France":    ["Île-de-France","Auvergne-Rhône-Alpes","Provence-Alpes-Côte d'Azur"],
    "Japan":     ["Tokyo","Osaka","Kanagawa","Aichi","Saitama"],
}

ALL_COUNTRIES = ["Any"] + sorted(COUNTRY_STATES.keys())

DISPLAY_COLS = [
    "company","city","country_detected","industry_detected","product_type",
    "channel_type","company_size","incorporation_date","importance","final_score",
    "compliance_gaps","bis_certified","gst_registered","iec_found","mca_active",
    "contact_person","contact_email","email","phone","linkedin_url",
    "active_website","website","ai_summary","products","mca_company_type",
    "domain_authority","contact_presence","semantic_score","keyword_score",
    "country_filter","searched_query","created_at",
]

COLUMN_LABELS = {
    "company":"Company","city":"City","country_detected":"Country",
    "industry_detected":"Industry","product_type":"Product Type",
    "channel_type":"Channel","company_size":"Size","incorporation_date":"Founded",
    "importance":"Priority","final_score":"Score","compliance_gaps":"Gaps",
    "bis_certified":"BIS","gst_registered":"GST","iec_found":"IEC",
    "mca_active":"MCA","contact_person":"Contact","contact_email":"Contact Email",
    "email":"Email","phone":"Phone","linkedin_url":"LinkedIn",
    "active_website":"Website","website":"URL","ai_summary":"Summary",
    "products":"Products","mca_company_type":"MCA Type","domain_authority":"DA",
    "contact_presence":"Contact Score","semantic_score":"Sem","keyword_score":"KW",
    "country_filter":"Country Filter","searched_query":"Query","created_at":"Found At",
}

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "active_job_id":         "",
    "active_query":          "",
    "live_results":          [],
    "live_cursor":           0,
    "new_result_indexes":    [],
    "notified_jobs":         [],
    "mlt_results":           [],
    "mlt_seed_result_index": None,
    "mlt_seed_company":      "",
    "sf_query":              "",
    "sf_country":            "Any",
    "sf_state":              "Any",
    "sf_industry":           "Any",
    "sf_channel":            "Any",
    "sf_importance":         "Any",
    "sf_min_score":          0.0,
    "sf_sort_by":            "Score (High→Low)",
    "visible_cols":          [],
    "view_mode":             "Table",
    "selected_lead":         None,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    # Logo / title
    st.markdown("""
    <div style="padding:12px 0 20px">
        <h2 style="background:linear-gradient(135deg,#4f8ef7,#10b981);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;
            font-size:1.4rem;margin:0;">🌐 Buyera AI</h2>
        <p style="color:#4a5568;font-size:0.75rem;margin:2px 0 0;">B2B Lead Discovery</p>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"👤 **{st.session_state.auth_username}**")
    if st.button("🚪 Logout", use_container_width=True):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

    st.divider()

    # --- Search ---
    st.markdown("### 🔍 Search")
    query = st.text_input("Query", value=st.session_state.sf_query,
                          placeholder="electronics importers india",
                          key="sf_query", label_visibility="collapsed")

    sel_country = st.selectbox("🌍 Country", ALL_COUNTRIES,
        index=ALL_COUNTRIES.index(st.session_state.sf_country)
              if st.session_state.sf_country in ALL_COUNTRIES else 0,
        key="sf_country")

    state_options = ["Any"] + COUNTRY_STATES.get(sel_country, []) \
                    if sel_country != "Any" else ["Any"]
    if st.session_state.sf_state not in state_options:
        st.session_state.sf_state = "Any"

    sel_state = st.selectbox("📍 State / Region", state_options,
        index=state_options.index(st.session_state.sf_state)
              if st.session_state.sf_state in state_options else 0,
        key="sf_state", disabled=(sel_country == "Any"))

    sel_industry = st.selectbox("🏭 Industry", ["Any"] + ALL_INDUSTRIES,
        index=(["Any"] + ALL_INDUSTRIES).index(st.session_state.sf_industry)
              if st.session_state.sf_industry in ["Any"] + ALL_INDUSTRIES else 0,
        key="sf_industry")

    col_a, col_b = st.columns(2)
    with col_a:
        scan_all = st.checkbox("All pages", value=False, key="scan_all_remaining")
    with col_b:
        trusted  = st.checkbox("Trusted only", value=False, key="trusted_only")

    country_filter  = "" if sel_country == "Any" else sel_country.lower()
    state_suffix    = "" if sel_state    == "Any" else sel_state
    industry_suffix = "" if sel_industry == "Any" else sel_industry

    def _build_search_query() -> str:
        parts = [query.strip()]
        if industry_suffix and industry_suffix.lower() not in query.lower():
            parts.append(industry_suffix)
        if state_suffix and state_suffix.lower() not in query.lower():
            parts.append(state_suffix)
        if country_filter and country_filter not in query.lower():
            parts.append(country_filter)
        return " ".join(p for p in parts if p).strip()

    if st.button("🔍 Start Search", use_container_width=True, type="primary"):
        fq = _build_search_query()
        if not fq:
            st.warning("Enter a search query")
        else:
            cf = "" if sel_country == "Any" else sel_country.lower()
            try:
                r = _api_post("/search/start", params={
                    "query": fq, "continue_search": "false",
                    "scan_all_remaining": str(scan_all).lower(),
                    "country_filter": cf,
                    "trusted_only": str(trusted).lower(),
                }, timeout=30)
                if r.status_code == 200:
                    data = r.json()
                    st.session_state.active_job_id = data.get("job_id", "")
                    st.session_state.active_query  = fq
                    for k in ["live_results","new_result_indexes","mlt_results"]:
                        st.session_state[k] = []
                    st.session_state.live_cursor = 0
                    st.success("Search started!")
                else:
                    st.error(f"Error: {r.text}")
            except Exception as e:
                st.error(f"Cannot reach backend: {e}")

    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()

    st.divider()

    # --- Filters ---
    st.markdown("### 🎛️ Filters")

    sel_channel = st.selectbox("Channel Type",
        ["Any","Manufacturer","Importer","Trader","Wholesaler","Distributor","Retailer"],
        key="sf_channel")

    sel_importance = st.selectbox("Priority",
        ["Any","high","medium","low"], key="sf_importance")

    min_score = st.slider("Min Score", 0.0, 1.0, 0.0, 0.05, key="sf_min_score")

    sort_by = st.selectbox("Sort By", [
        "Score (High→Low)", "Score (Low→High)",
        "Company A→Z", "Company Z→A",
        "Newest First", "Importance",
    ], key="sf_sort_by")

    if st.button("🗑️ Clear Filters", use_container_width=True):
        for k in ["sf_industry","sf_country","sf_state","sf_channel",
                  "sf_importance","sf_min_score"]:
            st.session_state[k] = _DEFAULTS[k]
        st.rerun()

    st.divider()

    # --- Dashboard options ---
    st.markdown("### ⚙️ Dashboard")

    view_mode = st.radio("View Mode", ["Table","Cards"], key="view_mode", horizontal=True)

    all_col_keys = [c for c in DISPLAY_COLS if c in COLUMN_LABELS]
    default_cols = ["company","city","country_detected","industry_detected",
                    "channel_type","importance","final_score","compliance_gaps",
                    "email","phone","website","ai_summary"]

    if not st.session_state.visible_cols:
        st.session_state.visible_cols = default_cols

    with st.expander("📋 Columns", expanded=False):
        selected_cols = st.multiselect(
            "Visible columns",
            options=all_col_keys,
            default=st.session_state.visible_cols,
            format_func=lambda x: COLUMN_LABELS.get(x, x),
        )
        if selected_cols:
            st.session_state.visible_cols = selected_cols
        if st.button("Reset Columns"):
            st.session_state.visible_cols = default_cols
            st.rerun()

    st.divider()

    # --- Compliance ---
    st.markdown("### 🔬 Compliance")
    enrich_limit = st.slider("Max leads", 10, 200, 50, key="enrich_limit")
    if st.button("▶️ Run Checks", use_container_width=True):
        try:
            r = _api_post("/leads/enrich-compliance",
                params={"limit": enrich_limit, "country_filter": country_filter},
                timeout=300)
            if r.status_code == 200:
                st.success(f"✅ {r.json().get('checked',0)} leads checked")
            else:
                st.error("Failed")
        except Exception as e:
            st.error(str(e))

    if st.button("🗑️ Clear All Leads", use_container_width=True):
        try:
            _api_delete("/clear", timeout=15)
            for k, v in _DEFAULTS.items():
                st.session_state[k] = v
            st.warning("Leads cleared")
            st.rerun()
        except Exception as e:
            st.error(str(e))

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _bool_icon(val) -> str:
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"

def _importance_badge(imp: str) -> str:
    imp = str(imp).lower()
    if imp == "high":   return '<span class="badge badge-green">HIGH</span>'
    if imp == "medium": return '<span class="badge badge-yellow">MED</span>'
    return '<span class="badge badge-grey">LOW</span>'

def _score_color(score: float) -> str:
    if score >= 0.6: return "#10b981"
    if score >= 0.4: return "#f59e0b"
    return "#ef4444"

def _gap_badge(gaps) -> str:
    if not isinstance(gaps, list) or not gaps:
        return '<span class="badge badge-green">Clean</span>'
    return f'<span class="badge badge-red">{len(gaps)} Gap(s)</span>'


def _apply_filters(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df

    if st.session_state.sf_channel != "Any" and "channel_type" in df.columns:
        df = df[df["channel_type"].astype(str) == st.session_state.sf_channel]

    if st.session_state.sf_importance != "Any" and "importance" in df.columns:
        df = df[df["importance"].astype(str).str.lower() == st.session_state.sf_importance]

    if st.session_state.sf_min_score > 0 and "final_score" in df.columns:
        df = df[pd.to_numeric(df["final_score"], errors="coerce").fillna(0)
                >= st.session_state.sf_min_score]

    # Sort
    sort = st.session_state.sf_sort_by
    if "final_score" in df.columns:
        score_col = pd.to_numeric(df["final_score"], errors="coerce").fillna(0)
        if sort == "Score (High→Low)":
            df = df.iloc[score_col.argsort()[::-1]]
        elif sort == "Score (Low→High)":
            df = df.iloc[score_col.argsort()]
    if sort == "Company A→Z" and "company" in df.columns:
        df = df.sort_values("company")
    elif sort == "Company Z→A" and "company" in df.columns:
        df = df.sort_values("company", ascending=False)
    elif sort == "Newest First" and "created_at" in df.columns:
        df = df.sort_values("created_at", ascending=False)
    elif sort == "Importance" and "importance" in df.columns:
        order = {"high": 0, "medium": 1, "low": 2}
        df = df.iloc[df["importance"].astype(str).str.lower().map(order).fillna(3).argsort()]

    return df.reset_index(drop=True)


def _prep_df(df_in: pd.DataFrame) -> pd.DataFrame:
    vis_cols = st.session_state.visible_cols or DISPLAY_COLS
    cols     = [c for c in vis_cols if c in df_in.columns]
    df       = df_in[cols].copy()
    df.rename(columns={c: COLUMN_LABELS.get(c, c) for c in df.columns}, inplace=True)

    for col_key, col_label in [
        ("compliance_gaps", "Gaps"),
        ("products",        "Products"),
    ]:
        if col_label in df.columns:
            df[col_label] = df[col_label].apply(
                lambda v: ", ".join(str(x) for x in v) if isinstance(v, list) else str(v or "")
            )
    for col_key in ["bis_certified","gst_registered","iec_found","mca_active"]:
        lbl = COLUMN_LABELS.get(col_key, col_key)
        if lbl in df.columns:
            df[lbl] = df[lbl].apply(_bool_icon)
    for col_key in ["final_score","semantic_score","keyword_score",
                    "domain_authority","contact_presence"]:
        lbl = COLUMN_LABELS.get(col_key, col_key)
        if lbl in df.columns:
            df[lbl] = pd.to_numeric(df[lbl], errors="coerce").round(3)
    return df


def _show_table(df_in: pd.DataFrame, key_suffix: str = "") -> None:
    if df_in.empty:
        st.info("No leads in this category yet.")
        return

    df_filt = _apply_filters(df_in)
    if df_filt.empty:
        st.info("No leads match the current filters.")
        return

    if st.session_state.view_mode == "Cards":
        _show_cards(df_filt, key_suffix)
    else:
        _show_dataframe(df_filt, key_suffix)


def _show_dataframe(df_in: pd.DataFrame, key_suffix: str = "") -> None:
    df = _prep_df(df_in)

    def _row_style(row):
        imp     = str(row.get("Priority", row.get("Importance", ""))).lower()
        gaps    = str(row.get("Gaps", ""))
        has_gap = bool(gaps and gaps not in ("", "nan", "None", "[]", "Clean"))
        if has_gap:         bg, color = "#3b0a0a", "#fca5a5"
        elif imp == "high": bg, color = "#052e16", "#6ee7b7"
        elif imp == "medium": bg, color = "#451a03", "#fcd34d"
        else:               bg, color = "#111827", "#94a3b8"
        return [f"background-color:{bg};color:{color}"] * len(row)

    styled = (
        df.style.apply(_row_style, axis=1)
        .set_properties(**{"font-size": "12px", "font-family": "monospace"})
        .set_table_styles([
            {"selector": "th", "props": [
                ("background", "#0f172a"), ("color", "#94a3b8"),
                ("font-size", "11px"), ("font-weight", "700"),
                ("text-transform", "uppercase"), ("letter-spacing", "0.06em"),
                ("padding", "8px 12px"), ("border-bottom", "2px solid #1e293b"),
            ]},
            {"selector": "td", "props": [
                ("padding", "7px 12px"), ("border-bottom", "1px solid #1e293b"),
                ("max-width", "240px"), ("overflow", "hidden"),
                ("text-overflow", "ellipsis"), ("white-space", "nowrap"),
            ]},
            {"selector": "tr:hover td", "props": [("filter", "brightness(1.3)")]},
        ])
    )
    st.dataframe(styled, use_container_width=True, height=min(60 + len(df) * 36, 650))

    # Download
    csv_df = df_in[[c for c in (st.session_state.visible_cols or DISPLAY_COLS)
                    if c in df_in.columns]].copy()
    for col in ["compliance_gaps","products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(
                lambda v: ", ".join(v) if isinstance(v, list) else str(v or ""))
    csv = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download CSV", csv,
                       f"leads_{key_suffix}.csv", "text/csv",
                       key=f"dl_{key_suffix}_{len(df_in)}")


def _show_cards(df_in: pd.DataFrame, key_suffix: str = "") -> None:
    """Card view for leads."""
    for idx, row in df_in.iterrows():
        score   = float(row.get("final_score", 0) or 0)
        imp     = str(row.get("importance", "low"))
        gaps    = row.get("compliance_gaps", [])
        company = str(row.get("company", "Unknown"))
        city    = str(row.get("city", ""))
        country = str(row.get("country_detected", ""))
        industry= str(row.get("industry_detected", ""))
        channel = str(row.get("channel_type", ""))
        email   = str(row.get("email", ""))
        phone   = str(row.get("phone", ""))
        website = str(row.get("active_website", row.get("website", "")))
        summary = str(row.get("ai_summary", ""))[:180]
        linkedin= str(row.get("linkedin_url", ""))

        sc = _score_color(score)
        location = ", ".join(filter(None, [city, country]))
        gap_html = _gap_badge(gaps)
        imp_html = _importance_badge(imp)

        st.markdown(f"""
        <div class="lead-card">
          <div style="display:flex;justify-content:space-between;align-items:start;margin-bottom:8px">
            <div>
              <span style="font-size:1.05rem;font-weight:700;color:#e2e8f0;">{company}</span>
              <span style="color:#64748b;font-size:0.8rem;margin-left:8px;">📍 {location}</span>
            </div>
            <div style="display:flex;gap:6px;align-items:center">
              {imp_html} {gap_html}
              <span style="background:#1f2937;color:{sc};padding:2px 10px;
                border-radius:20px;font-size:0.8rem;font-weight:700;">
                {score:.2f}
              </span>
            </div>
          </div>
          <div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;font-size:0.78rem;color:#64748b">
            {"<span>🏭 "+industry+"</span>" if industry else ""}
            {"<span>🔗 "+channel+"</span>" if channel else ""}
            {"<span>📧 "+email+"</span>" if email else ""}
            {"<span>📞 "+phone+"</span>" if phone else ""}
          </div>
          {"<p style='font-size:0.8rem;color:#94a3b8;margin:4px 0;'>"+summary+"</p>" if summary else ""}
          <div style="display:flex;gap:12px;margin-top:8px;font-size:0.78rem">
            {"<a href='"+website+"' target='_blank' style='color:#4f8ef7;'>🌐 Website</a>" if website and website != "nan" else ""}
            {"<a href='"+linkedin+"' target='_blank' style='color:#4f8ef7;'>💼 LinkedIn</a>" if linkedin and linkedin != "nan" else ""}
          </div>
          <div style="margin-top:8px">
            <div class="score-bar-bg"><div class="score-bar-fill" style="width:{int(score*100)}%"></div></div>
          </div>
        </div>
        """, unsafe_allow_html=True)


def _tab_metrics(df_in: pd.DataFrame) -> None:
    if df_in.empty:
        return
    high_n = int((df_in.get("importance", pd.Series(dtype=str))
                  .astype(str).str.lower() == "high").sum()) if "importance" in df_in.columns else 0
    gap_n  = int(df_in["compliance_gaps"].apply(
                 lambda g: isinstance(g, list) and len(g) > 0).sum()) \
             if "compliance_gaps" in df_in.columns else 0
    mfg_n  = int((df_in.get("channel_type", pd.Series(dtype=str))
                  .astype(str) == "Manufacturer").sum()) if "channel_type" in df_in.columns else 0
    imp_n  = int((df_in.get("channel_type", pd.Series(dtype=str))
                  .astype(str) == "Importer").sum()) if "channel_type" in df_in.columns else 0
    has_email = int(df_in["email"].astype(str).str.contains("@").sum()) \
                if "email" in df_in.columns else 0

    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("Total",       len(df_in))
    m2.metric("🟢 High",     high_n)
    m3.metric("🔴 Gaps",     gap_n)
    m4.metric("🏭 Mfg",      mfg_n)
    m5.metric("📦 Importers",imp_n)
    m6.metric("📧 With Email",has_email)


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
                      "company","companies","service","services","business","global"}
        tokens = [t for t in re.findall(r"[a-zA-Z]{4,}", ai_summary.lower())
                  if t not in stop_words]
        product_text = " ".join(list(dict.fromkeys(tokens))[:4])
    q = " ".join(p for p in [searched_query, product_text] if p).strip()
    return q or company


# ===========================================================================
# MAIN CONTENT
# ===========================================================================

# Header
st.markdown("""
<div style="padding:8px 0 16px">
    <h1 style="font-size:1.6rem;color:#e2e8f0;margin:0;">
        🌐 Global B2B Lead Discovery
    </h1>
    <p style="color:#64748b;font-size:0.85rem;margin:4px 0 0;">
        AI-powered lead discovery · Compliance checks · Deep research
    </p>
</div>
""", unsafe_allow_html=True)

# Active filters strip
active_parts = []
if sel_country   != "Any": active_parts.append(f"🌍 {sel_country}")
if sel_state     != "Any": active_parts.append(f"📍 {sel_state}")
if sel_industry  != "Any": active_parts.append(f"🏭 {sel_industry}")
if st.session_state.sf_channel    != "Any": active_parts.append(f"🔗 {st.session_state.sf_channel}")
if st.session_state.sf_importance != "Any": active_parts.append(f"⚡ {st.session_state.sf_importance}")
if st.session_state.sf_min_score  > 0:      active_parts.append(f"📊 ≥{st.session_state.sf_min_score:.2f}")
if active_parts:
    st.markdown(
        "**Active filters:** " + " · ".join(
            f'<span class="badge badge-blue">{p}</span>' for p in active_parts
        ), unsafe_allow_html=True
    )

# Backend status (collapsed)
with st.expander("🔌 Backend Status", expanded=False):
    try:
        ping = requests.get(f"{API}/", timeout=5)
        if ping.status_code == 200:
            st.success(f"✅ Connected — {ping.json().get('service','')}")
            try:
                prov = requests.get(f"{API}/llm/provider", timeout=5).json()
                if prov.get("status") == "active":
                    st.info(f"🤖 LLM: **{prov.get('provider','').upper()}** — `{prov.get('model','')}`")
                else:
                    st.warning("⚠️ No LLM key configured")
            except Exception:
                pass
        else:
            st.error(f"❌ HTTP {ping.status_code}")
    except Exception as e:
        st.error(f"❌ {e}")

st.divider()

# ===========================================================================
# LIVE SEARCH SECTION
# ===========================================================================
if st.session_state.active_job_id:
    st.markdown("### 🔴 Live Search")

    status = None
    try:
        sr = _api_get(f"/search/status/{st.session_state.active_job_id}", timeout=20)
        if sr.status_code == 200:
            status = sr.json()
        else:
            st.error(f"Status error: {sr.text}")
    except Exception as e:
        st.error(f"Backend not reachable: {e}")

    if status:
        try:
            rr = _api_get(f"/search/results/{st.session_state.active_job_id}",
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
            st.error(f"Results fetch error: {e}")

        company_live = [x for x in st.session_state.live_results
                        if x.get("source") != "linkedin_semantic"]

        # Metrics
        high_n   = sum(1 for x in company_live if str(x.get("importance","")).lower()=="high")
        medium_n = sum(1 for x in company_live if str(x.get("importance","")).lower()=="medium")
        gap_n    = sum(1 for x in company_live if isinstance(x.get("compliance_gaps"), list) and x["compliance_gaps"])
        mfg_n    = sum(1 for x in company_live if x.get("channel_type") == "Manufacturer")
        imp_n    = sum(1 for x in company_live if x.get("channel_type") == "Importer")

        c1,c2,c3,c4,c5,c6 = st.columns(6)
        c1.metric("Found",        len(company_live))
        c2.metric("🟢 High",      high_n)
        c3.metric("🟡 Medium",    medium_n)
        c4.metric("🔴 Gaps",      gap_n)
        c5.metric("🏭 Mfg",       mfg_n)
        c6.metric("📦 Importers", imp_n)

        sv = status.get("status")
        st.caption(
            f"**{sv.upper()}** · Pages: {status.get('pages_scanned',0)} "
            f"· Saved: {status.get('saved_total',0)}"
        )

        if company_live:
            live_df = pd.DataFrame(company_live)
            _show_table(live_df, key_suffix="live")

            with st.expander("🔁 Find Similar Leads"):
                selectable = [r for r in company_live if r.get("result_index") is not None]
                if selectable:
                    options = {}
                    for row in sorted(selectable, key=lambda r: float(r.get("final_score",0) or 0), reverse=True):
                        idx   = int(row.get("result_index"))
                        name  = row.get("company","Unknown")
                        score = float(row.get("final_score",0) or 0)
                        gaps  = row.get("compliance_gaps",[])
                        tag   = " ⚠️" if isinstance(gaps,list) and gaps else ""
                        options[f"#{idx} | {name}{tag} | {score:.3f}"] = idx

                    sel_label = st.selectbox("Pick a lead", list(options.keys()), key="mlt_lead")
                    sel_idx   = options[sel_label]
                    sel_seed  = _seed_by_result_index(selectable, sel_idx)
                    sim_limit = st.slider("How many similar?", 3, 20, 8, key="mlt_lim")

                    b1, b2 = st.columns(2)
                    with b1:
                        if st.button("🔍 Find Similar", key="mlt_btn"):
                            try:
                                resp = _api_get(
                                    f"/search/more-like-this/{st.session_state.active_job_id}",
                                    params={"result_index": sel_idx, "limit": sim_limit},
                                    timeout=30)
                                if resp.status_code == 200:
                                    st.session_state.mlt_results      = resp.json().get("results",[])
                                    st.session_state.mlt_seed_company = sel_seed.get("company","")
                                else:
                                    st.error("Could not find similar leads")
                            except Exception as e:
                                st.error(str(e))
                    with b2:
                        if st.button("🚀 New Search Like This", key="mlt_new"):
                            gq = _build_more_like_query(sel_seed)
                            if gq:
                                cf = "" if sel_country == "Any" else sel_country.lower()
                                try:
                                    r = _api_post("/search/start", params={
                                        "query": gq, "continue_search": "false",
                                        "country_filter": cf,
                                    }, timeout=30)
                                    if r.status_code == 200:
                                        d = r.json()
                                        st.session_state.active_job_id = d.get("job_id","")
                                        st.session_state.active_query  = gq
                                        for k in ["live_results","new_result_indexes","mlt_results"]:
                                            st.session_state[k] = []
                                        st.session_state.live_cursor = 0
                                        st.info(f'Searching: "{gq}"')
                                        st.rerun()
                                except Exception as e:
                                    st.error(str(e))

                    if st.session_state.mlt_results:
                        st.caption(f"Similar to: {st.session_state.mlt_seed_company}")
                        _show_table(pd.DataFrame(st.session_state.mlt_results), key_suffix="similar")

        if sv in ("running","queued"):
            st.info("⏳ Searching… auto-refreshing")
            time.sleep(POLL_SECONDS)
            st.rerun()
        elif sv == "completed":
            jid = status.get("job_id","")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast("✅ Search complete!")
                st.session_state.notified_jobs.append(jid)
            if status.get("ask_continue"):
                st.warning("Batch done. Continue to next page?")
                cc1, cc2 = st.columns(2)
                with cc1:
                    if st.button("▶️ Continue"):
                        cf = "" if sel_country == "Any" else sel_country.lower()
                        try:
                            r = _api_post("/search/start", params={
                                "query": st.session_state.active_query,
                                "continue_search": "true",
                                "country_filter": cf,
                            }, timeout=30)
                            if r.status_code == 200:
                                d = r.json()
                                st.session_state.active_job_id = d.get("job_id","")
                                st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with cc2:
                    if st.button("⏹️ Stop"):
                        st.session_state.active_job_id = ""
                        st.rerun()
            else:
                st.success("✅ Search complete.")
        elif sv == "failed":
            st.error(f"Search failed: {status.get('error','Unknown')}")

    st.divider()

# ===========================================================================
# SAVED LEADS SECTION
# ===========================================================================
st.markdown("### 📁 Saved Leads")

try:
    lead_params = {"limit": 1000}
    if country_filter:
        lead_params["country_filter"] = country_filter
    res  = _api_get("/leads", params=lead_params, timeout=20)
    data = res.json()
except Exception as e:
    st.error(f"Backend not reachable: {e}")
    st.stop()

# Summary cards
col_gap, col_ch = st.columns(2)
with col_gap:
    try:
        gp = {"country_filter": country_filter} if country_filter else {}
        gr = _api_get("/leads/gap-summary", params=gp, timeout=10)
        gap_summ = gr.json() if gr.status_code == 200 else {}
        if gap_summ:
            st.markdown("##### 🔴 Compliance Gaps")
            gcols = st.columns(min(len(gap_summ), 5) or 1)
            for i, (gc, cnt) in enumerate(gap_summ.items()):
                gcols[i % len(gcols)].metric(GAP_LABELS.get(gc, gc), cnt)
    except Exception:
        pass

with col_ch:
    try:
        cp = {"country_filter": country_filter} if country_filter else {}
        cr = _api_get("/leads/channel-summary", params=cp, timeout=10)
        ch_summ = cr.json() if cr.status_code == 200 else {}
        if ch_summ:
            ch_icons = {"Manufacturer":"🏭","Importer":"📦","Trader":"🤝",
                        "Wholesaler":"🏢","Distributor":"🚚","Retailer":"🛍️"}
            st.markdown("##### 📊 Channel Breakdown")
            ccols = st.columns(min(len(ch_summ), 6) or 1)
            for i, (ch, cnt) in enumerate(ch_summ.items()):
                ccols[i % len(ccols)].metric(f"{ch_icons.get(ch,'')} {ch}", cnt)
    except Exception:
        pass

if data:
    df = pd.DataFrame(data)
    company_df  = df[df["source"] != "linkedin_semantic"].copy() \
                  if "source" in df.columns else df.copy()
    linkedin_df = df[df["source"] == "linkedin_semantic"].copy() \
                  if "source" in df.columns else pd.DataFrame()

    def _filter_gap(df_in, gap_code):
        if "compliance_gaps" not in df_in.columns: return pd.DataFrame()
        return df_in[df_in["compliance_gaps"].apply(
            lambda g: isinstance(g, list) and gap_code in g)].copy()

    def _filter_any_gap(df_in):
        if "compliance_gaps" not in df_in.columns: return pd.DataFrame()
        return df_in[df_in["compliance_gaps"].apply(
            lambda g: isinstance(g, list) and len(g) > 0)].copy()

    def _filter_channel(df_in, channel):
        if "channel_type" not in df_in.columns: return pd.DataFrame()
        return df_in[df_in["channel_type"].astype(str) == channel].copy()

    tabs = st.tabs([
        "📋 All", "🎯 Compliance Gaps", "🏭 Manufacturers",
        "📦 Importers", "🤝 Traders", "🔴 No BIS", "📦 No IEC",
        "🧾 No GST", "🔬 Deep Research", "✅ Verify",
    ])

    with tabs[0]:
        _tab_metrics(company_df)
        _show_table(company_df, key_suffix="all")

    with tabs[1]:
        st.info("Companies with at least one compliance gap — highest priority prospects.")
        gdf = _filter_any_gap(company_df)
        _tab_metrics(gdf)
        _show_table(gdf, key_suffix="gaps")

    with tabs[2]:
        mdf = _filter_channel(company_df, "Manufacturer")
        _tab_metrics(mdf)
        _show_table(mdf, key_suffix="manufacturer")

    with tabs[3]:
        idf = _filter_channel(company_df, "Importer")
        _tab_metrics(idf)
        _show_table(idf, key_suffix="importer")

    with tabs[4]:
        tdf = pd.concat([
            _filter_channel(company_df, c)
            for c in ["Trader","Distributor","Wholesaler","Retailer"]
        ], ignore_index=True) if not company_df.empty else pd.DataFrame()
        _tab_metrics(tdf)
        _show_table(tdf, key_suffix="traders")

    with tabs[5]:
        _show_table(_filter_gap(company_df, "no_bis"), key_suffix="no_bis")

    with tabs[6]:
        _show_table(_filter_gap(company_df, "no_iec"), key_suffix="no_iec")

    with tabs[7]:
        _show_table(_filter_gap(company_df, "no_gst"), key_suffix="no_gst")

    # -----------------------------------------------------------------------
    # Deep Research Tab
    # -----------------------------------------------------------------------
    with tabs[8]:
        st.markdown("#### 🔬 Deep Research")
        st.caption("Multi-source intelligence: news, trade data, social media, government registries, job signals")

        if not company_df.empty:
            company_names = company_df["company"].dropna().unique().tolist()
            sel_company = st.selectbox("Select company to research", company_names, key="dr_company")

            if sel_company:
                row = company_df[company_df["company"] == sel_company].iloc[0]
                website = str(row.get("active_website", row.get("website", "")))
                country = str(row.get("country_detected", "india"))

                if st.button("🔬 Run Deep Research", key="dr_btn", type="primary"):
                    with st.spinner(f"Researching {sel_company} across 8+ sources…"):
                        try:
                            r = _api_post("/research/deep",
                                json={"company": sel_company, "website": website,
                                      "country": country},
                                timeout=60)
                            if r.status_code == 200:
                                st.session_state["dr_result"] = r.json()
                            else:
                                st.error(f"Research failed: {r.text}")
                        except Exception as e:
                            st.error(f"Cannot reach backend: {e}")

                if st.session_state.get("dr_result"):
                    dr = st.session_state["dr_result"]

                    # Signals
                    if dr.get("signals"):
                        st.markdown("**📡 Key Signals**")
                        for sig in dr["signals"]:
                            st.markdown(f"- {sig}")

                    # Social media
                    if dr.get("social"):
                        st.markdown("**🌐 Social Media**")
                        scols = st.columns(5)
                        icons = {"linkedin":"💼","twitter":"🐦","facebook":"📘",
                                 "instagram":"📸","youtube":"▶️"}
                        for i, (platform, url_val) in enumerate(dr["social"].items()):
                            if url_val and url_val != "nan":
                                scols[i % 5].markdown(
                                    f"[{icons.get(platform,'')} {platform.title()}]({url_val})")
                            else:
                                scols[i % 5].markdown(
                                    f'<span style="color:#4a5568">{icons.get(platform,"")} {platform.title()}: —</span>',
                                    unsafe_allow_html=True)

                    # Sources
                    sources = dr.get("sources", {})
                    source_tabs = st.tabs([
                        "📰 News", "🏛️ MCA", "📦 Trade", "💼 Jobs",
                        "🗂️ Directory", "🧾 GST", "🏛️ Tenders"
                    ])
                    source_keys = ["news","mca","trade","jobs","kompass","gst","gem"]
                    for i, key in enumerate(source_keys):
                        with source_tabs[i]:
                            items = sources.get(key, [])
                            if not items:
                                st.info("No data found from this source.")
                            else:
                                for item in items:
                                    st.markdown(f"**{item.get('title','')}**")
                                    if item.get("date"):
                                        st.caption(f"📅 {item['date']}")
                                    if item.get("snippet"):
                                        st.markdown(f"> {item['snippet']}")
                                    if item.get("url"):
                                        st.markdown(f"[🔗 View source]({item['url']})")
                                    st.divider()
        else:
            st.info("No leads saved yet. Run a search first.")

    # -----------------------------------------------------------------------
    # Verify Tab
    # -----------------------------------------------------------------------
    with tabs[9]:
        st.markdown("#### ✅ Lead Verification")
        st.caption("Verify email deliverability, website status, and phone format")

        if not company_df.empty:
            company_names_v = company_df["company"].dropna().unique().tolist()
            sel_v = st.selectbox("Select company to verify", company_names_v, key="vf_company")

            if sel_v:
                row_v   = company_df[company_df["company"] == sel_v].iloc[0]
                email_v = str(row_v.get("email", ""))
                phone_v = str(row_v.get("phone", ""))
                web_v   = str(row_v.get("active_website", row_v.get("website", "")))

                c1v, c2v, c3v = st.columns(3)
                c1v.text_input("Email", value=email_v, key="vf_email")
                c2v.text_input("Phone", value=phone_v, key="vf_phone")
                c3v.text_input("Website", value=web_v, key="vf_website")

                if st.button("✅ Verify", key="vf_btn", type="primary"):
                    with st.spinner("Verifying…"):
                        try:
                            r = _api_post("/verify/lead",
                                json={
                                    "email":   st.session_state.vf_email,
                                    "phone":   st.session_state.vf_phone,
                                    "website": st.session_state.vf_website,
                                },
                                timeout=30)
                            if r.status_code == 200:
                                st.session_state["vf_result"] = r.json()
                            else:
                                st.error(f"Verification failed: {r.text}")
                        except Exception as e:
                            st.error(f"Cannot reach backend: {e}")

                if st.session_state.get("vf_result"):
                    vr = st.session_state["vf_result"]
                    v1, v2, v3 = st.columns(3)

                    # Email result
                    with v1:
                        er = vr.get("email", {})
                        verdict = er.get("verdict","unknown")
                        color   = {"valid":"#6ee7b7","risky":"#fcd34d",
                                   "invalid":"#fca5a5","unknown":"#94a3b8"}.get(verdict,"#94a3b8")
                        st.markdown(f"""
                        <div class="lead-card">
                          <h4 style="color:#e2e8f0;margin:0 0 8px">📧 Email</h4>
                          <span class="badge" style="background:#1f2937;color:{color};font-size:1rem">
                            {verdict.upper()}
                          </span>
                          <div style="margin-top:10px;font-size:0.8rem;color:#94a3b8">
                            <div>Format: {"✅" if er.get("valid_format") else "❌"}</div>
                            <div>MX Record: {"✅" if er.get("mx_found") else "❌"}</div>
                            <div>Free provider: {"Yes" if er.get("is_free") else "No"}</div>
                            <div>Score: {er.get("score",0)}/100</div>
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                    # Website result
                    with v2:
                        wr = vr.get("website", {})
                        verdict_w = wr.get("verdict","unknown")
                        color_w   = {"verified":"#6ee7b7","partial":"#fcd34d",
                                     "unverified":"#fca5a5"}.get(verdict_w,"#94a3b8")
                        st.markdown(f"""
                        <div class="lead-card">
                          <h4 style="color:#e2e8f0;margin:0 0 8px">🌐 Website</h4>
                          <span class="badge" style="background:#1f2937;color:{color_w};font-size:1rem">
                            {verdict_w.upper()}
                          </span>
                          <div style="margin-top:10px;font-size:0.8rem;color:#94a3b8">
                            <div>Live: {"✅" if wr.get("is_live") else "❌"}</div>
                            <div>SSL: {"✅" if wr.get("has_ssl") else "❌"}</div>
                            <div>Response: {wr.get("response_ms","—")}ms</div>
                            <div>Score: {wr.get("score",0)}/100</div>
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

                    # Phone result
                    with v3:
                        pr = vr.get("phone", {})
                        verdict_p = pr.get("verdict","unknown")
                        color_p   = {"valid":"#6ee7b7","invalid":"#fca5a5"}.get(verdict_p,"#94a3b8")
                        st.markdown(f"""
                        <div class="lead-card">
                          <h4 style="color:#e2e8f0;margin:0 0 8px">📞 Phone</h4>
                          <span class="badge" style="background:#1f2937;color:{color_p};font-size:1rem">
                            {verdict_p.upper()}
                          </span>
                          <div style="margin-top:10px;font-size:0.8rem;color:#94a3b8">
                            <div>Format: {"✅" if pr.get("valid_format") else "❌"}</div>
                            <div>Country: {pr.get("country","—")}</div>
                            <div>Mobile: {"✅" if pr.get("is_mobile") else "—"}</div>
                            <div>Score: {pr.get("score",0)}/100</div>
                          </div>
                        </div>
                        """, unsafe_allow_html=True)

    if not linkedin_df.empty:
        with st.expander("👤 LinkedIn Profiles"):
            linkedin_cols = ["name","profile","snippet","searched_query","created_at"]
            ld = linkedin_df[[c for c in linkedin_cols if c in linkedin_df.columns]]
            st.dataframe(ld, use_container_width=True)

else:
    st.markdown("""
    <div style="text-align:center;padding:60px 20px;color:#4a5568">
        <div style="font-size:3rem">🔍</div>
        <h3 style="color:#64748b">No leads yet</h3>
        <p>Use the search panel on the left to discover B2B leads</p>
    </div>
    """, unsafe_allow_html=True)
