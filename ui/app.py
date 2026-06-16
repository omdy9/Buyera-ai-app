"""
ui/app.py  —  Buyera AI  (Minimalist Redesign)
================================================
Clean inbox-style master-detail layout.
Sidebar = all filters. Main = search + results.
"""

import os
import time
import re

import pandas as pd
import requests
import streamlit as st

# ---------------------------------------------------------------------------
# Config
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
    page_title="Buyera — Lead Discovery",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS — minimal, intentional
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html, body, [data-testid="stAppViewContainer"] { font-family: 'Inter', sans-serif; }

/* ── App shell ── */
.stApp { background: #F9FAFB; }
#MainMenu, footer, header, [data-testid="stToolbar"] { display: none !important; }
[data-testid="stAppViewContainer"] > .main { padding-top: 0 !important; }
.block-container { padding: 0 !important; max-width: 100% !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #FFFFFF !important;
    border-right: 1px solid #E5E7EB !important;
    padding: 0 !important;
}
[data-testid="stSidebar"] > div { padding: 20px 16px !important; }
[data-testid="stSidebar"] section { padding: 0 !important; }

/* Sidebar labels */
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 11px !important;
    font-weight: 600 !important;
    color: #6B7280 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
}

/* Sidebar inputs */
[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] .stTextInput input {
    background: #F9FAFB !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 6px !important;
    font-size: 13px !important;
    color: #111827 !important;
}

/* ── Global text ── */
p, span, div, label, td, th { color: #111827; }

/* ── Inputs ── */
.stTextInput input {
    border-radius: 8px !important;
    border: 1.5px solid #E5E7EB !important;
    font-size: 14px !important;
    padding: 10px 14px !important;
    background: white !important;
    color: #111827 !important;
    transition: border-color .15s !important;
}
.stTextInput input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.08) !important;
    outline: none !important;
}
.stTextInput input::placeholder { color: #9CA3AF !important; }

/* ── Buttons ── */
.stButton > button {
    border-radius: 7px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 8px 16px !important;
    border: 1.5px solid #E5E7EB !important;
    background: white !important;
    color: #374151 !important;
    transition: all .12s !important;
    cursor: pointer !important;
}
.stButton > button:hover {
    border-color: #2563EB !important;
    color: #2563EB !important;
    background: #EFF6FF !important;
}
.stButton > button[kind="primary"] {
    background: #2563EB !important;
    color: white !important;
    border-color: #2563EB !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: white !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    border-radius: 7px !important;
    border: 1.5px solid #E5E7EB !important;
    background: white !important;
    font-size: 13px !important;
    color: #111827 !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] [class*="singleValue"] { color: #111827 !important; }

/* Dropdown */
ul[role="listbox"], div[role="listbox"],
[data-baseweb="popover"] > div {
    background: white !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.1) !important;
}
[role="option"] { background: white !important; color: #111827 !important; }
[role="option"]:hover { background: #EFF6FF !important; color: #2563EB !important; }

/* ── Slider ── */
.stSlider [data-testid="stWidgetLabel"] p { color: #6B7280 !important; }

/* ── Checkbox ── */
.stCheckbox label span, .stCheckbox [data-testid="stMarkdownContainer"] p {
    font-size: 13px !important;
    color: #374151 !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    border-bottom: 1px solid #E5E7EB !important;
    background: transparent !important;
    gap: 0 !important;
    padding: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    border-radius: 0 !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    padding: 10px 16px !important;
    font-size: 13px !important;
    font-weight: 500 !important;
    color: #6B7280 !important;
    background: transparent !important;
    margin-bottom: -1px !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #2563EB !important;
    border-bottom-color: #2563EB !important;
    font-weight: 600 !important;
    background: transparent !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: white !important;
    border: 1px solid #E5E7EB !important;
    border-radius: 10px !important;
    padding: 14px 16px !important;
}
[data-testid="stMetricValue"] { font-size: 1.6rem !important; font-weight: 700 !important; color: #111827 !important; }
[data-testid="stMetricLabel"] { font-size: 11px !important; color: #6B7280 !important; text-transform: uppercase; letter-spacing: .05em; }

/* ── Alert ── */
[data-testid="stAlert"] { border-radius: 8px !important; }

/* ── Download button ── */
.stDownloadButton > button {
    background: white !important;
    border: 1.5px solid #E5E7EB !important;
    color: #374151 !important;
    font-size: 12px !important;
    border-radius: 6px !important;
    padding: 6px 12px !important;
}
.stDownloadButton > button:hover {
    border-color: #2563EB !important;
    color: #2563EB !important;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    border: 1px solid #E5E7EB !important;
    border-radius: 8px !important;
    background: white !important;
}
[data-testid="stExpander"] summary p { font-weight: 600 !important; font-size: 13px !important; color: #374151 !important; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; border: 1px solid #E5E7EB; }

/* ── Divider ── */
hr { border: none !important; border-top: 1px solid #E5E7EB !important; margin: 0 !important; }

/* ── Progress bar ── */
.stProgress > div > div { background: #2563EB !important; border-radius: 4px; }

/* ── Custom components ── */

/* Top bar */
.topbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 24px;
    background: white;
    border-bottom: 1px solid #E5E7EB;
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-brand { font-size: 15px; font-weight: 700; color: #111827; letter-spacing: -.02em; }
.topbar-brand em { color: #2563EB; font-style: normal; }

/* Search bar wrapper */
.search-bar-wrap {
    background: white;
    border-bottom: 1px solid #E5E7EB;
    padding: 16px 24px;
    display: flex;
    gap: 10px;
    align-items: center;
}

/* Status bar */
.status-bar {
    background: #EFF6FF;
    border-bottom: 1px solid #BFDBFE;
    padding: 8px 24px;
    font-size: 12px;
    color: #1E40AF;
    display: flex;
    align-items: center;
    gap: 8px;
}

/* Section heading */
.section-head {
    padding: 12px 24px 0;
    font-size: 11px;
    font-weight: 700;
    color: #9CA3AF;
    text-transform: uppercase;
    letter-spacing: .07em;
}

/* Metrics row */
.metrics-row { padding: 12px 24px; }

/* Results area */
.results-area { padding: 0 24px 24px; }

/* ── Lead row (inbox style) ── */
.lead-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 11px 14px;
    background: white;
    border: 1px solid #E5E7EB;
    border-radius: 8px;
    margin-bottom: 4px;
    cursor: pointer;
    transition: border-color .12s, background .1s;
}
.lead-row:hover { border-color: #93C5FD; background: #F8FAFF; }
.lead-row.selected { border-color: #2563EB; background: #EFF6FF; }

.row-icon {
    width: 32px; height: 32px;
    background: #F3F4F6;
    border-radius: 7px;
    display: flex; align-items: center; justify-content: center;
    font-size: 14px; flex-shrink: 0;
}
.row-body { flex: 1; min-width: 0; }
.row-name {
    font-size: 13px; font-weight: 600; color: #111827;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.row-meta {
    font-size: 11px; color: #9CA3AF; margin-top: 1px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.row-right { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }

/* ── Badges ── */
.badge {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 11px;
    font-weight: 600;
    letter-spacing: .01em;
    white-space: nowrap;
}
.badge-high    { background: #D1FAE5; color: #065F46; }
.badge-medium  { background: #FEF3C7; color: #92400E; }
.badge-low     { background: #F3F4F6; color: #6B7280; }
.badge-gap     { background: #FEE2E2; color: #991B1B; }
.badge-clean   { background: #D1FAE5; color: #065F46; }
.badge-score   { background: #EFF6FF; color: #1E40AF; border: 1px solid #BFDBFE; font-weight: 700; }
.badge-dir     { background: #F3E8FF; color: #6B21A8; }

/* ── Detail panel ── */
.detail-pane {
    background: white;
    border: 1px solid #E5E7EB;
    border-radius: 10px;
    padding: 20px;
    height: fit-content;
    position: sticky;
    top: 80px;
}
.detail-empty {
    background: white;
    border: 1.5px dashed #E5E7EB;
    border-radius: 10px;
    padding: 48px 20px;
    text-align: center;
    color: #9CA3AF;
}
.detail-empty .icon { font-size: 2.2rem; margin-bottom: 8px; }
.detail-empty p { font-size: 13px; line-height: 1.5; }

.detail-title { font-size: 16px; font-weight: 700; color: #111827; margin-bottom: 2px; }
.detail-sub { font-size: 12px; color: #6B7280; margin-bottom: 14px; }

.detail-section {
    font-size: 10px; font-weight: 700; color: #9CA3AF;
    text-transform: uppercase; letter-spacing: .08em;
    margin-top: 14px; margin-bottom: 4px;
    padding-top: 12px; border-top: 1px solid #F3F4F6;
}
.detail-body { font-size: 13px; color: #374151; line-height: 1.6; }
.detail-link { font-size: 12px; font-weight: 600; color: #2563EB; text-decoration: none; margin-right: 12px; }
.detail-link:hover { text-decoration: underline; }

.info-chip {
    display: inline-block;
    background: #F3F4F6;
    color: #374151;
    padding: 3px 9px;
    border-radius: 5px;
    font-size: 11px;
    font-weight: 500;
    margin: 2px 2px 2px 0;
}

/* ── Dir item ── */
.dir-item {
    background: #F9FAFB;
    border: 1px solid #E5E7EB;
    border-radius: 6px;
    padding: 7px 10px;
    margin-bottom: 3px;
    font-size: 12px;
    color: #374151;
}
.dir-item strong { color: #111827; }

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #9CA3AF;
}
.empty-state .icon { font-size: 2.5rem; margin-bottom: 10px; }
.empty-state h3 { font-size: 15px; color: #6B7280; margin-bottom: 4px; font-weight: 600; }
.empty-state p { font-size: 13px; }

/* ── Sidebar brand ── */
.sb-brand { font-size: 16px; font-weight: 700; color: #111827; margin-bottom: 4px; }
.sb-brand em { color: #2563EB; font-style: normal; }
.sb-user { font-size: 11px; color: #9CA3AF; margin-bottom: 16px; }
.sb-divider { height: 1px; background: #F3F4F6; margin: 12px 0; }
.sb-section { font-size: 10px; font-weight: 700; color: #9CA3AF; text-transform: uppercase; letter-spacing: .07em; margin: 14px 0 6px; }

/* ── List master panel ── */
.master-panel {
    max-height: calc(100vh - 220px);
    overflow-y: auto;
    padding-right: 2px;
    scrollbar-width: thin;
    scrollbar-color: #E5E7EB transparent;
}
.master-panel::-webkit-scrollbar { width: 3px; }
.master-panel::-webkit-scrollbar-thumb { background: #E5E7EB; border-radius: 3px; }

/* ── Override Streamlit specifics that bleed through ── */
[data-testid="stVerticalBlock"] { gap: 0 !important; }
div[data-testid="column"] { padding: 0 6px !important; }
.stMarkdown p { color: #374151 !important; font-size: 13px; }
.stCaption, [data-testid="stCaptionContainer"] p { color: #9CA3AF !important; font-size: 11px !important; }
[data-testid="stAlert"] p { color: #111827 !important; }
[data-testid="stSidebar"] * { color: #111827 !important; }

/* ── Scan all / quality toggle area ── */
.search-options {
    display: flex;
    gap: 16px;
    align-items: center;
    padding: 8px 24px;
    background: #F9FAFB;
    border-bottom: 1px solid #E5E7EB;
    font-size: 12px;
    color: #6B7280;
}
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def _auth_headers() -> dict:
    token = st.session_state.get("auth_token", "")
    return {"X-User-Token": token} if token else {}

def _api_post(path, **kwargs):
    return requests.post(f"{API}{path}", headers=_auth_headers(),
                         timeout=kwargs.pop("timeout", 30), **kwargs)

def _api_get(path, **kwargs):
    return requests.get(f"{API}{path}", headers=_auth_headers(),
                        timeout=kwargs.pop("timeout", 20), **kwargs)

def _api_delete(path, **kwargs):
    return requests.delete(f"{API}{path}", headers=_auth_headers(),
                           timeout=kwargs.pop("timeout", 15), **kwargs)

# ---------------------------------------------------------------------------
# Login page
# ---------------------------------------------------------------------------
def _show_login_page():
    st.markdown("""
    <div style="min-height:100vh;display:flex;align-items:center;justify-content:center;background:#F9FAFB;">
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.markdown("""
        <div style="text-align:center;margin-bottom:28px">
          <div style="font-size:24px;font-weight:700;color:#111827;letter-spacing:-.03em">
            Buyera<em style="color:#2563EB;font-style:normal">.</em>
          </div>
          <p style="font-size:13px;color:#6B7280;margin-top:4px">
            Find business leads, faster.
          </p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_reg = st.tabs(["Sign in", "Create account"])

        with tab_login:
            with st.form("lf"):
                uname = st.text_input("Username")
                pwd   = st.text_input("Password", type="password")
                sub   = st.form_submit_button("Sign in", use_container_width=True, type="primary")
            if sub:
                if not uname or not pwd:
                    st.error("Enter username and password.")
                else:
                    try:
                        r = _api_post("/auth/login",
                            json={"username": uname.strip().lower(), "password": pwd},
                            timeout=10)
                        if r.status_code == 200:
                            d = r.json()
                            st.session_state.auth_token    = d["token"]
                            st.session_state.auth_user_id  = d["user_id"]
                            st.session_state.auth_username = d["username"]
                            st.session_state.auth_role     = d.get("role", "user")
                            st.rerun()
                        else:
                            try:
                                err = r.json().get("detail", "Sign in failed.")
                            except Exception:
                                err = f"HTTP {r.status_code}"
                            st.error(err)
                    except Exception as e:
                        st.error(f"Can't reach server: {e}")

        with tab_reg:
            with st.form("rf"):
                nu   = st.text_input("Username")
                ne   = st.text_input("Email (optional)")
                np   = st.text_input("Password", type="password")
                np2  = st.text_input("Confirm password", type="password")
                sub2 = st.form_submit_button("Create account", use_container_width=True, type="primary")
            if sub2:
                if not nu or not np:
                    st.error("Username and password are required.")
                elif np != np2:
                    st.error("Passwords don't match.")
                elif len(np) < 6:
                    st.error("Password must be 6+ characters.")
                else:
                    try:
                        r = _api_post("/auth/register",
                            json={"username": nu.strip().lower(),
                                  "password": np, "email": ne.strip()},
                            timeout=10)
                        if r.status_code == 200:
                            d = r.json()
                            st.session_state.auth_token    = d["token"]
                            st.session_state.auth_user_id  = d["user_id"]
                            st.session_state.auth_username = d["username"]
                            st.session_state.auth_role     = d.get("role", "user")
                            st.rerun()
                        else:
                            try:
                                err = r.json().get("detail", "Registration failed.")
                            except Exception:
                                err = f"HTTP {r.status_code}"
                            st.error(err)
                    except Exception as e:
                        st.error(f"Can't reach server: {e}")

    st.markdown("</div>", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------
for k, v in [("auth_token",""),("auth_user_id",""),
              ("auth_username",""),("auth_role","user")]:
    if k not in st.session_state:
        st.session_state[k] = v

if not st.session_state.auth_token:
    _show_login_page()
    st.stop()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GAP_LABELS = {
    "no_bis":        "No BIS Licence",
    "no_gst":        "No GST",
    "no_iec":        "No IEC Code",
    "mca_not_found": "Not on MCA",
    "mca_inactive":  "Struck Off",
}

CHANNEL_TYPES = ["Manufacturer","Importer","Trader","Wholesaler","Distributor","Retailer"]
ALL_INDUSTRIES = [
    "Electronics","Pharmaceuticals","Textiles","Chemicals","Machinery",
    "Food & Beverage","Automotive","Construction","IT & Software",
    "Healthcare","Logistics","Agriculture","Energy","Retail",
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
    "USA":       ["California","New York","Texas","Florida","Illinois","Washington"],
    "UK":        ["England","Scotland","Wales","Northern Ireland","London","Manchester"],
    "Germany":   ["Bavaria","Berlin","Hamburg","North Rhine-Westphalia"],
    "Canada":    ["Ontario","Quebec","British Columbia","Alberta"],
    "Australia": ["New South Wales","Victoria","Queensland","South Australia"],
    "Singapore": ["Central Region","East Region","North Region","West Region"],
    "China":     ["Beijing","Shanghai","Guangdong","Zhejiang","Jiangsu"],
    "Italy":     ["Lombardy","Lazio","Veneto","Emilia-Romagna"],
}
ALL_COUNTRIES = ["Any Country"] + sorted(COUNTRY_STATES.keys())

ALL_COLUMNS = {
    "company":"Company","city":"City","country_detected":"Country",
    "industry_detected":"Industry","product_type":"Products",
    "channel_type":"Type","company_size":"Size","incorporation_date":"Founded",
    "importance":"Priority","final_score":"Score","compliance_gaps":"Compliance",
    "bis_certified":"BIS","gst_registered":"GST","iec_found":"IEC","mca_active":"MCA",
    "contact_person":"Contact","contact_email":"Contact Email","email":"Email",
    "phone":"Phone","linkedin_url":"LinkedIn","active_website":"Website",
    "ai_summary":"About","products":"Product List","annual_turnover":"Turnover",
    "certifications":"Certifications","export_markets":"Export Markets",
    "usp":"USP","key_customers":"Customers","searched_query":"Query","created_at":"Date",
}
DEFAULT_COLUMNS = [
    "company","city","country_detected","channel_type","importance",
    "final_score","compliance_gaps","email","phone","active_website","ai_summary",
]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "active_job_id":"","active_query":"",
    "live_results":[],"live_cursor":0,"notified_jobs":[],
    "sf_query":"","sf_country":"Any Country","sf_state":"Any",
    "sf_industry":"Any","sf_channel":"Any","sf_importance":"Any",
    "sf_min_score":0.0,"sf_sort":"Best Match First",
    "sf_has_email":False,"sf_has_phone":False,"sf_gaps_only":False,
    "visible_cols":DEFAULT_COLUMNS[:],"scan_all":False,"quality_threshold":0,
    "selected_card":None,"selected_tab":"",
    "card_details":{},"expanded_cards":{},
    "_reset_filters":False,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()

if st.session_state.get("_reset_filters"):
    st.session_state["_reset_filters"] = False
    for _k, _v in {
        "sf_country":"Any Country","sf_state":"Any","sf_industry":"Any",
        "sf_channel":"Any","sf_importance":"Any","sf_min_score":0.0,
        "sf_has_email":False,"sf_has_phone":False,"sf_gaps_only":False,
        "quality_threshold":0,"scan_all":False,
        "sf_sort":"Best Match First","sf_query":"",
    }.items():
        st.session_state[_k] = _v
    st.rerun()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
    <div class="sb-brand">Buyera<em>.</em></div>
    <div class="sb-user">Signed in as {st.session_state.auth_username}</div>
    """, unsafe_allow_html=True)

    if st.button("Sign out", use_container_width=True, key="sb_logout"):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-section">Location</div>', unsafe_allow_html=True)

    _ctr_idx = ALL_COUNTRIES.index(st.session_state.sf_country) \
               if st.session_state.sf_country in ALL_COUNTRIES else 0
    st.session_state.sf_country = st.selectbox(
        "Country", ALL_COUNTRIES, index=_ctr_idx, key="sb_country")

    _state_opts = (["Any"] + COUNTRY_STATES.get(st.session_state.sf_country, [])
                   if st.session_state.sf_country != "Any Country" else ["Any"])
    if st.session_state.sf_state not in _state_opts:
        st.session_state.sf_state = "Any"
    st.session_state.sf_state = st.selectbox(
        "State", _state_opts,
        index=_state_opts.index(st.session_state.sf_state),
        key="sb_state",
        disabled=(st.session_state.sf_country == "Any Country"))

    st.markdown('<div class="sb-section">Business</div>', unsafe_allow_html=True)

    _ind_opts = ["Any"] + ALL_INDUSTRIES
    _ind_idx  = _ind_opts.index(st.session_state.sf_industry) \
                if st.session_state.sf_industry in _ind_opts else 0
    st.session_state.sf_industry = st.selectbox(
        "Industry", _ind_opts, index=_ind_idx, key="sb_industry")

    _ch_opts = ["Any"] + CHANNEL_TYPES
    _ch_idx  = _ch_opts.index(st.session_state.sf_channel) \
               if st.session_state.sf_channel in _ch_opts else 0
    st.session_state.sf_channel = st.selectbox(
        "Type", _ch_opts, index=_ch_idx, key="sb_channel")

    st.markdown('<div class="sb-section">Filters</div>', unsafe_allow_html=True)

    _imp_opts = ["Any","High","Medium","Low"]
    _imp_idx  = _imp_opts.index(st.session_state.sf_importance) \
                if st.session_state.sf_importance in _imp_opts else 0
    st.session_state.sf_importance = st.selectbox(
        "Priority", _imp_opts, index=_imp_idx, key="sb_importance")

    _sort_opts = ["Best Match First","Priority High→Low","Name A→Z","Name Z→A","Newest First"]
    _sort_idx  = _sort_opts.index(st.session_state.sf_sort) \
                 if st.session_state.sf_sort in _sort_opts else 0
    st.session_state.sf_sort = st.selectbox(
        "Sort by", _sort_opts, index=_sort_idx, key="sb_sort")

    st.session_state.sf_min_score = st.slider(
        "Min score", 0.0, 1.0, st.session_state.sf_min_score, 0.05, key="sb_score")

    st.session_state.sf_has_email = st.checkbox("Has email", key="sb_email",
                                                 value=st.session_state.sf_has_email)
    st.session_state.sf_has_phone = st.checkbox("Has phone", key="sb_phone",
                                                 value=st.session_state.sf_has_phone)
    st.session_state.sf_gaps_only = st.checkbox("Compliance issues only", key="sb_gaps",
                                                 value=st.session_state.sf_gaps_only)

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-section">Search options</div>', unsafe_allow_html=True)

    st.session_state.scan_all = st.checkbox("Scan all pages (slower)", key="sb_scan",
                                             value=st.session_state.scan_all)
    _qt_labels = ["All","Basic","Good","Best"]
    _qt_map    = {"All":0,"Basic":1,"Good":2,"Best":3}
    _qt_rev    = {0:"All",1:"Basic",2:"Good",3:"Best"}
    _qt_sel    = st.select_slider("Result quality", _qt_labels,
                                   value=_qt_rev.get(st.session_state.quality_threshold,"All"),
                                   key="sb_qt")
    st.session_state.quality_threshold = _qt_map[_qt_sel]

    st.markdown('<div class="sb-divider"></div>', unsafe_allow_html=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear filters", use_container_width=True, key="sb_clear"):
            st.session_state["_reset_filters"] = True
            st.rerun()
    with c2:
        if st.button("Delete leads", use_container_width=True, key="sb_del"):
            try:
                _api_delete("/clear", timeout=15)
                for k in ["active_job_id","active_query","live_results","live_cursor",
                           "notified_jobs","card_details","selected_card","selected_tab"]:
                    st.session_state[k] = "" if isinstance(st.session_state[k], str) else \
                                           [] if isinstance(st.session_state[k], list) else \
                                           {} if isinstance(st.session_state[k], dict) else None
                st.rerun()
            except Exception as e:
                st.error(str(e))


# ---------------------------------------------------------------------------
# Session restore
# ---------------------------------------------------------------------------
if st.session_state.auth_token and not st.session_state.active_job_id:
    try:
        rj = _api_get("/jobs/recent", timeout=10)
        if rj.status_code == 200:
            for job in rj.json()[:5]:
                if job.get("status") in ("completed","running","queued"):
                    st.session_state.active_job_id = job.get("job_id","")
                    st.session_state.active_query  = job.get("query","")
                    break
    except Exception:
        pass

# ---------------------------------------------------------------------------
# Top bar + Search
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="topbar">
  <div class="topbar-brand">Buyera<em>.</em></div>
  <div style="font-size:12px;color:#9CA3AF;">{st.session_state.auth_username}</div>
</div>
""", unsafe_allow_html=True)

# Search row
with st.container():
    st.markdown('<div style="padding:16px 24px 0;">', unsafe_allow_html=True)
    sc1, sc2, sc3 = st.columns([6, 1, 1])
    with sc1:
        query = st.text_input(
            "search",
            value=st.session_state.sf_query,
            placeholder='Search: "LED importers Gujarat" or "pharma distributors Mumbai"',
            label_visibility="collapsed",
            key="search_box",
        )
        st.session_state.sf_query = query
    with sc2:
        search_clicked = st.button("Search", use_container_width=True,
                                   type="primary", key="search_btn")
    with sc3:
        refresh_clicked = st.button("↺ Refresh", use_container_width=True, key="refresh_btn")
        if refresh_clicked:
            st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# Quick example chips
st.markdown("""
<div style="padding:8px 24px 14px;display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
  <span style="font-size:11px;color:#9CA3AF;">Try:</span>
  <span style="font-size:11px;background:#EFF6FF;color:#2563EB;padding:3px 10px;border-radius:20px;border:1px solid #BFDBFE;">Electronics importers Delhi</span>
  <span style="font-size:11px;background:#F0FDF4;color:#065F46;padding:3px 10px;border-radius:20px;border:1px solid #A7F3D0;">Textile manufacturers Surat</span>
  <span style="font-size:11px;background:#FDF4FF;color:#6B21A8;padding:3px 10px;border-radius:20px;border:1px solid #E9D5FF;">Pharma distributors Mumbai</span>
  <span style="font-size:11px;background:#FFF7ED;color:#9A3412;padding:3px 10px;border-radius:20px;border:1px solid #FED7AA;">Steel traders UAE</span>
</div>
<hr>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Build final query
# ---------------------------------------------------------------------------
def _build_final_query() -> str:
    parts = [st.session_state.sf_query.strip()]
    for val, key in [
        (st.session_state.sf_industry, "sf_industry"),
        (st.session_state.sf_state,    "sf_state"),
        (st.session_state.sf_country,  "sf_country"),
    ]:
        if val and val not in ("Any","Any Country",""):
            if val.lower() not in st.session_state.sf_query.lower():
                parts.append(val)
    return " ".join(p for p in parts if p).strip()

if search_clicked:
    fq = _build_final_query()
    if not fq:
        st.warning("Type something to search for.")
    else:
        cf = "" if st.session_state.sf_country == "Any Country" \
             else st.session_state.sf_country.lower()
        try:
            r = _api_post("/search/start", params={
                "query":              fq,
                "continue_search":    "false",
                "scan_all_remaining": str(st.session_state.scan_all).lower(),
                "country_filter":     cf,
                "trusted_only":       "false",
                "quality_threshold":  st.session_state.quality_threshold,
            }, timeout=30)
            if r.status_code == 200:
                d = r.json()
                st.session_state.active_job_id  = d.get("job_id","")
                st.session_state.active_query   = fq
                st.session_state.live_results   = []
                st.session_state.live_cursor    = 0
                st.session_state.card_details   = {}
                st.session_state.selected_card  = None
                st.session_state.selected_tab   = ""
                st.rerun()
            else:
                st.error(f"Search error: {r.text}")
        except Exception as e:
            st.error(f"Cannot reach server: {e}")


# ---------------------------------------------------------------------------
# Fetch leads
# ---------------------------------------------------------------------------
def _get_all_leads() -> list:
    cf = "" if st.session_state.sf_country == "Any Country" \
         else st.session_state.sf_country.lower()
    try:
        params = {"limit": 2000}
        if cf:
            params["country_filter"] = cf
        r = _api_get("/leads", params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

raw_leads     = _get_all_leads()
company_leads = [x for x in raw_leads if x.get("source") != "linkedin_semantic"]

# ---------------------------------------------------------------------------
# Live job status
# ---------------------------------------------------------------------------
if st.session_state.active_job_id:
    status = None
    try:
        sr = _api_get(f"/search/status/{st.session_state.active_job_id}", timeout=20)
        if sr.status_code == 200:
            status = sr.json()
    except Exception as e:
        st.error(f"Cannot reach server: {e}")

    if status:
        sv    = status.get("status","")
        saved = status.get("saved_total",0)
        pages = status.get("pages_scanned",0)

        if sv in ("running","queued"):
            st.markdown(f"""
            <div class="status-bar">
              <span>⏳</span>
              <span><strong>Searching…</strong> — {saved} companies found · Page {pages} · Refreshing every {POLL_SECONDS}s</span>
            </div>
            """, unsafe_allow_html=True)
            time.sleep(POLL_SECONDS)
            st.rerun()

        elif sv == "completed":
            jid = status.get("job_id","")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast(f"✅ Done — {saved} companies found")
                st.session_state.notified_jobs.append(jid)

            if status.get("ask_continue"):
                c1, c2, c3 = st.columns([3,1,1])
                with c1:
                    st.info(f"Found {saved} companies. Want to search more pages?")
                with c2:
                    if st.button("▶ Find more", use_container_width=True, type="primary"):
                        cf = "" if st.session_state.sf_country == "Any Country" \
                             else st.session_state.sf_country.lower()
                        try:
                            r = _api_post("/search/start", params={
                                "query": st.session_state.active_query,
                                "continue_search": "true",
                                "country_filter": cf,
                            }, timeout=30)
                            if r.status_code == 200:
                                st.session_state.active_job_id = r.json().get("job_id","")
                                st.rerun()
                        except Exception as e:
                            st.error(str(e))
                with c3:
                    if st.button("Done", use_container_width=True):
                        st.session_state.active_job_id = ""
                        st.rerun()
            else:
                st.success(f"✅ Search complete — {saved} companies found.")
                st.session_state.active_job_id = ""

        elif sv == "failed":
            st.error(f"Search failed: {status.get('error','Unknown')}")
            st.session_state.active_job_id = ""


# ---------------------------------------------------------------------------
# Filter logic
# ---------------------------------------------------------------------------
def _apply_filters(leads: list) -> list:
    if not leads:
        return []
    df = pd.DataFrame(leads)

    if st.session_state.sf_channel != "Any" and "channel_type" in df.columns:
        df = df[df["channel_type"].astype(str) == st.session_state.sf_channel]

    imp_map = {"High":"high","Medium":"medium","Low":"low"}
    imp_val = imp_map.get(st.session_state.sf_importance)
    if imp_val and "importance" in df.columns:
        df = df[df["importance"].astype(str).str.lower() == imp_val]

    if st.session_state.sf_min_score > 0 and "final_score" in df.columns:
        df = df[pd.to_numeric(df["final_score"],errors="coerce").fillna(0) >= st.session_state.sf_min_score]

    if st.session_state.sf_has_email and "email" in df.columns:
        df = df[df["email"].astype(str).str.contains("@",na=False)]

    if st.session_state.sf_has_phone and "phone" in df.columns:
        df = df[df["phone"].astype(str).str.strip().ne("").ne("nan")]

    if st.session_state.sf_gaps_only and "compliance_gaps" in df.columns:
        df = df[df["compliance_gaps"].apply(lambda g: isinstance(g,list) and len(g)>0)]

    if st.session_state.sf_industry != "Any" and "industry_detected" in df.columns:
        df = df[df["industry_detected"].astype(str).str.lower()
                .str.contains(st.session_state.sf_industry.lower(),na=False)]

    sort = st.session_state.sf_sort
    if "final_score" in df.columns:
        sc = pd.to_numeric(df["final_score"],errors="coerce").fillna(0)
        if sort == "Best Match First":
            df = df.iloc[sc.argsort()[::-1]]
        elif sort == "Priority High→Low":
            order = {"high":0,"medium":1,"low":2}
            df = df.iloc[df["importance"].astype(str).str.lower().map(order).fillna(3).argsort()]
    if sort == "Name A→Z" and "company" in df.columns:
        df = df.sort_values("company")
    elif sort == "Name Z→A" and "company" in df.columns:
        df = df.sort_values("company",ascending=False)
    elif sort == "Newest First" and "created_at" in df.columns:
        df = df.sort_values("created_at",ascending=False)

    return df.reset_index(drop=True).to_dict("records")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------
def _safe(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan","none","") else s

def _bool_icon(val):
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"

def _ch_emoji(ch):
    return {"Manufacturer":"🏭","Importer":"📦","Trader":"🤝",
            "Wholesaler":"🏪","Distributor":"🚚","Retailer":"🛍️"}.get(ch,"🏢")

def _imp_badge(imp):
    imp = str(imp).lower()
    if imp == "high":   return '<span class="badge badge-high">High</span>'
    if imp == "medium": return '<span class="badge badge-medium">Medium</span>'
    return '<span class="badge badge-low">Low</span>'

def _gap_badge(gaps):
    if not isinstance(gaps, list) or not gaps:
        return '<span class="badge badge-clean">✓ Clean</span>'
    return f'<span class="badge badge-gap">⚠ {len(gaps)} issue{"s" if len(gaps)>1 else ""}</span>'

def _card_id(row, idx):
    return str(row.get("_id") or f"{str(row.get('company',''))[:16]}_{idx}")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def _show_metrics(leads: list):
    if not leads: return
    df     = pd.DataFrame(leads)
    total  = len(df)
    high   = int((df.get("importance",pd.Series(dtype=str)).astype(str).str.lower()=="high").sum()) \
             if "importance" in df.columns else 0
    w_email= int(df["email"].astype(str).str.contains("@",na=False).sum()) \
             if "email" in df.columns else 0
    w_gap  = int(df["compliance_gaps"].apply(lambda g:isinstance(g,list) and len(g)>0).sum()) \
             if "compliance_gaps" in df.columns else 0
    mfg    = int((df.get("channel_type",pd.Series(dtype=str)).astype(str)=="Manufacturer").sum()) \
             if "channel_type" in df.columns else 0

    st.markdown('<div style="padding:14px 24px 0;">', unsafe_allow_html=True)
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Companies",  total)
    m2.metric("⭐ High",     high)
    m3.metric("📧 Email",   w_email)
    m4.metric("⚠ Gaps",    w_gap)
    m5.metric("🏭 Mfg",    mfg)
    st.markdown('</div>', unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Table view
# ---------------------------------------------------------------------------
def _show_table(leads, key_suffix=""):
    if not leads:
        st.info("No results.")
        return
    df  = pd.DataFrame(leads)
    vis = [c for c in st.session_state.visible_cols if c in df.columns]
    if not vis:
        vis = [c for c in DEFAULT_COLUMNS if c in df.columns]

    disp = df[vis].copy()
    for col in ["bis_certified","gst_registered","iec_found","mca_active"]:
        if col in disp.columns:
            disp[col] = disp[col].apply(_bool_icon)
    if "compliance_gaps" in disp.columns:
        disp["compliance_gaps"] = disp["compliance_gaps"].apply(
            lambda g: ", ".join(GAP_LABELS.get(x,x) for x in g) if isinstance(g,list) else "")
    if "products" in disp.columns:
        disp["products"] = disp["products"].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p,list) else str(p or ""))
    if "final_score" in disp.columns:
        disp["final_score"] = pd.to_numeric(disp["final_score"],errors="coerce").round(3)
    if "created_at" in disp.columns:
        disp["created_at"] = pd.to_datetime(disp["created_at"],errors="coerce").dt.strftime("%d %b %Y")
    disp.rename(columns={c: ALL_COLUMNS.get(c,c) for c in disp.columns}, inplace=True)

    st.dataframe(disp, use_container_width=True, height=min(60+len(disp)*36, 600))

    csv_df = df[vis].copy()
    for col in ["compliance_gaps","products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(lambda v: ", ".join(v) if isinstance(v,list) else str(v or ""))
    st.download_button("⬇ Download CSV",
                       data=csv_df.to_csv(index=False).encode("utf-8"),
                       file_name=f"leads_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_{key_suffix}_{len(leads)}")


# ---------------------------------------------------------------------------
# AI detail fetch
# ---------------------------------------------------------------------------
def _fetch_ai_detail(row: dict) -> dict:
    company = row.get("company","")
    website = row.get("active_website", row.get("website",""))
    if not company:
        return row
    try:
        r = _api_post("/research/deep",
                      json={"company":company,"website":website,
                            "country":row.get("country_detected","india"),
                            "query":st.session_state.active_query},
                      timeout=45)
        if r.status_code == 200:
            d = r.json()
            enriched = dict(row)
            enriched["_signals"] = d.get("signals",[])
            enriched["_news"]    = d.get("sources",{}).get("news",[])[:3]
            enriched["_social"]  = d.get("social",{})
            return enriched
    except Exception:
        pass
    return row


# ---------------------------------------------------------------------------
# Lead row (compact, inbox-style)
# ---------------------------------------------------------------------------
def _render_lead_row(row, cid, idx, key_suffix):
    is_sel  = (st.session_state.get("selected_card") == cid
               and st.session_state.get("selected_tab") == key_suffix)
    company = _safe(row.get("company","Unknown"))
    city    = _safe(row.get("city",""))
    country = _safe(row.get("country_detected",""))
    channel = _safe(row.get("channel_type",""))
    imp     = _safe(row.get("importance","low")) or "low"
    score   = float(row.get("final_score",0) or 0)
    gaps    = row.get("compliance_gaps",[]) or []
    email   = _safe(row.get("email",""))
    is_dir  = bool(row.get("is_directory",False))
    loc     = ", ".join(filter(None,[city,country]))
    emoji   = "📂" if is_dir else _ch_emoji(channel)

    imp_lower = imp.lower()
    if imp_lower == "high":
        imp_badge_html = '<span class="badge badge-high">High</span>'
    elif imp_lower == "medium":
        imp_badge_html = '<span class="badge badge-medium">Med</span>'
    else:
        imp_badge_html = '<span class="badge badge-low">Low</span>'

    if isinstance(gaps,list) and gaps:
        gap_badge_html = f'<span class="badge badge-gap">⚠ {len(gaps)}</span>'
    else:
        gap_badge_html = '<span class="badge badge-clean">✓</span>'

    email_dot = ' <span style="color:#10B981;font-size:10px;">●</span>' if "@" in email else ""
    border    = "2px solid #2563EB" if is_sel else "1px solid #E5E7EB"
    bg        = "#EFF6FF" if is_sel else "white"

    st.markdown(f"""
    <div style="background:{bg};border:{border};border-radius:8px;
                padding:10px 12px;margin-bottom:4px;">
      <div style="display:flex;align-items:center;gap:10px;">
        <div style="width:30px;height:30px;background:#F3F4F6;border-radius:6px;
                    display:flex;align-items:center;justify-content:center;
                    font-size:13px;flex-shrink:0;">{emoji}</div>
        <div style="flex:1;min-width:0;">
          <div style="font-size:13px;font-weight:600;color:#111827;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            {company}{email_dot}
          </div>
          <div style="font-size:11px;color:#9CA3AF;margin-top:1px;
                      white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
            {"📍 "+loc+"  ·  " if loc else ""}{channel}
          </div>
        </div>
        <div style="display:flex;align-items:center;gap:4px;flex-shrink:0;">
          {imp_badge_html}
          {gap_badge_html}
          <span class="badge badge-score">{score:.2f}</span>
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    btn_label = "✓ Open" if is_sel else "Open"
    if st.button(btn_label, key=f"open_{key_suffix}_{cid}_{idx}",
                 use_container_width=True):
        if not is_sel:
            st.session_state.selected_card = cid
            st.session_state.selected_tab  = key_suffix
            if cid not in st.session_state.card_details:
                with st.spinner(f"Loading {company[:20]}…"):
                    enriched = _fetch_ai_detail(row)
                    st.session_state.card_details[cid] = enriched
        else:
            st.session_state.selected_card = None
            st.session_state.selected_tab  = ""
        st.rerun()


# ---------------------------------------------------------------------------
# Detail panel
# ---------------------------------------------------------------------------
def _render_detail_panel(cid: str):
    row = st.session_state.card_details.get(cid)
    if not row:
        st.markdown("""
        <div class="detail-empty">
          <div class="icon">👈</div>
          <p>Select a company on the left<br>to see full details here.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    company  = _safe(row.get("company","")) or "Unknown"
    city     = _safe(row.get("city",""))
    country  = _safe(row.get("country_detected",""))
    industry = _safe(row.get("industry_detected",""))
    channel  = _safe(row.get("channel_type",""))
    score    = float(row.get("final_score",0) or 0)
    imp      = _safe(row.get("importance","low")) or "low"
    gaps     = row.get("compliance_gaps",[]) or []
    email    = _safe(row.get("email",""))
    phone    = _safe(row.get("phone",""))
    website  = _safe(row.get("active_website",row.get("website","")))
    linkedin = _safe(row.get("linkedin_url",""))
    summary  = _safe(row.get("ai_summary",""))
    products = [_safe(str(p)) for p in (row.get("products") or []) if _safe(str(p))]
    size     = _safe(row.get("company_size",""))
    founded  = _safe(row.get("incorporation_date",""))
    turnover = _safe(row.get("annual_turnover",""))
    certs    = [_safe(str(c)) for c in (row.get("certifications") or []) if _safe(str(c))]
    exports  = [_safe(str(e)) for e in (row.get("export_markets") or []) if _safe(str(e))]
    usp      = _safe(row.get("usp",""))
    key_cust = [_safe(str(k)) for k in (row.get("key_customers") or []) if _safe(str(k))]
    contact  = _safe(row.get("contact_person",""))
    c_title  = _safe(row.get("contact_title",""))
    c_conf   = _safe(row.get("contact_confidence",""))
    c_email  = _safe(row.get("contact_email",""))
    is_dir   = bool(row.get("is_directory",False))
    dir_cos  = row.get("directory_companies",[]) or []
    dir_ct   = int(row.get("directory_count",0) or 0)
    is_valid = bool(row.get("is_valid_lead",True))
    rejection= _safe(row.get("rejection_reason",""))
    signals  = [_safe(str(s)) for s in (row.get("_signals") or []) if _safe(str(s))]
    news     = row.get("_news") or []
    social_r = row.get("_social") or {}

    loc = ", ".join(filter(None,[city,country]))

    # ── Build single HTML block ──
    parts = []

    # Header
    imp_lower = imp.lower()
    if imp_lower == "high":
        ib = '<span class="badge badge-high" style="font-size:11px">High</span>'
    elif imp_lower == "medium":
        ib = '<span class="badge badge-medium" style="font-size:11px">Med</span>'
    else:
        ib = '<span class="badge badge-low" style="font-size:11px">Low</span>'

    dir_badge = '<span class="badge badge-dir" style="font-size:11px">📂 Dir</span>' if is_dir else ""

    parts.append(f"""
    <div class="detail-pane">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:4px;">
        <div style="flex:1;min-width:0;">
          <div class="detail-title">{company}</div>
          <div class="detail-sub">
            {"📍 "+loc+"  ·  " if loc else ""}{(_ch_emoji(channel)+" "+channel) if channel else ""}
          </div>
        </div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;justify-content:flex-end;flex-shrink:0;">
          {ib}
          {dir_badge}
          <span class="badge badge-score">{score:.2f}</span>
        </div>
      </div>
    """)

    # Tags row
    chips = [t for t in [industry, size, f"Est. {founded}" if founded else "", turnover] if t]
    if chips:
        chips_html = "".join(f'<span class="info-chip">{c}</span>' for c in chips)
        parts.append(f'<div style="margin:8px 0 0;">{chips_html}</div>')

    def section(title, content):
        return (f'<div class="detail-section">{title}</div>'
                f'<div class="detail-body">{content}</div>')

    if summary:
        parts.append(section("About", summary))
    if usp:
        parts.append(section("Unique Edge", f"<em>{usp}</em>"))
    if products:
        parts.append(section("Products", "  ·  ".join(products[:8])))

    if contact:
        conf_html = (f' <span style="color:#10B981;font-size:11px;">({c_conf} confidence)</span>'
                     if c_conf not in ("","low") else "")
        ct_html   = f'<strong>{contact}</strong>'
        if c_title: ct_html += f'  —  {c_title}'
        ct_html += conf_html
        if c_email and "@" in c_email and c_email != email:
            ct_html += f'<br><a href="mailto:{c_email}" class="detail-link">📧 {c_email}</a>'
        parts.append(section("Key Contact", ct_html))

    # Compliance
    if isinstance(gaps,list) and gaps:
        gap_html = " ".join(
            f'<span class="badge badge-gap" style="margin-right:3px;">'
            f'⚠ {GAP_LABELS.get(g,g)}</span>'
            for g in gaps)
    else:
        gap_html = '<span class="badge badge-clean">✓ No compliance issues</span>'
    parts.append(section("Compliance", gap_html))

    if certs:
        parts.append(section("Certifications", " · ".join(certs[:8])))
    if exports:
        parts.append(section("Export Markets", " · ".join(exports[:6])))
    if key_cust:
        parts.append(section("Key Customers", " · ".join(key_cust[:4])))
    if signals:
        parts.append(section("Signals", "  ".join(signals)))

    if news:
        news_html = "<br>".join(
            f'<a href="{n.get("url","#")}" target="_blank" class="detail-link">'
            f'📰 {str(n.get("title",""))[:70]}</a>'
            for n in news[:3] if n.get("title"))
        if news_html:
            parts.append(section("Recent News", news_html))

    # Links
    link_parts = []
    if website:
        link_parts.append(f'<a href="{website}" target="_blank" class="detail-link">🌐 Website</a>')
    if email and "@" in email:
        link_parts.append(f'<a href="mailto:{email}" class="detail-link">📧 {email}</a>')
    if phone:
        link_parts.append(f'<span class="detail-link">📞 {phone}</span>')
    if linkedin:
        link_parts.append(f'<a href="{linkedin}" target="_blank" class="detail-link">💼 LinkedIn</a>')
    for field, icon, label in [
        ("twitter_url","🐦","X"),("facebook_url","📘","FB"),
        ("instagram_url","📸","IG"),("youtube_url","▶️","YT"),
        ("whatsapp_url","💬","WA"),
    ]:
        v = _safe(str(row.get(field,"")))
        if v:
            link_parts.append(f'<a href="{v}" target="_blank" class="detail-link">{icon} {label}</a>')
    for plat, icon in [("linkedin","💼"),("twitter","🐦"),("facebook","📘"),("instagram","📸")]:
        v = _safe(str(social_r.get(plat,"")))
        if v and not _safe(str(row.get(plat+"_url",""))):
            link_parts.append(f'<a href="{v}" target="_blank" class="detail-link">{icon}</a>')

    if link_parts:
        parts.append(
            '<div style="margin-top:14px;padding-top:12px;border-top:1px solid #F3F4F6;">'
            + "".join(link_parts) + '</div>')

    if not is_valid and rejection:
        parts.append(
            f'<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:6px;'
            f'padding:8px 10px;font-size:12px;color:#B91C1C;margin-top:10px;">'
            f'⚠️ {rejection}</div>')

    parts.append("</div>")  # close detail-pane

    st.markdown("".join(parts), unsafe_allow_html=True)

    # Directory section (uses st widgets — after HTML)
    if is_dir:
        st.markdown(
            f'<div style="background:#F3E8FF;border:1px solid #E9D5FF;border-radius:7px;'
            f'padding:10px 12px;margin-top:8px;font-size:12px;color:#6B21A8;">'
            f'📂 Directory page — ~{dir_ct} companies listed</div>',
            unsafe_allow_html=True)

        if dir_cos:
            # Render as one HTML block
            dir_html = []
            for c in dir_cos[:30]:
                cn   = _safe(str(c.get("company",""))) or "—"
                cc   = _safe(str(c.get("city","")))
                ce   = _safe(str(c.get("email","")))
                cw   = _safe(str(c.get("website","")))
                cprod= _safe(str(c.get("products","")))[:60]
                lnk  = ""
                if cw: lnk += f' <a href="{cw}" target="_blank" style="color:#2563EB;font-size:11px;">🌐</a>'
                if ce and "@" in ce: lnk += f' <a href="mailto:{ce}" style="color:#2563EB;font-size:11px;">📧</a>'
                loc_str = f"  ·  📍{cc}" if cc else ""
                prod_str_c = f'<br><span style="color:#6B7280;font-size:11px;">{cprod}</span>' if cprod else ""
                dir_html.append(
                    f'<div class="dir-item"><strong>{cn}</strong>{loc_str}{lnk}{prod_str_c}</div>')
            st.markdown("".join(dir_html), unsafe_allow_html=True)

            if len(dir_cos) > 30:
                st.caption(f"…and {len(dir_cos)-30} more")
            df_dir = pd.DataFrame([{
                "Company":c.get("company",""),"City":c.get("city",""),
                "Phone":c.get("phone",""),"Email":c.get("email",""),
                "Website":c.get("website",""),"Products":c.get("products",""),
            } for c in dir_cos])
            st.download_button("⬇ Download companies",
                               data=df_dir.to_csv(index=False).encode("utf-8"),
                               file_name=f"dir_{cid[:8]}.csv", mime="text/csv",
                               key=f"dl_det_dir_{cid}")
        else:
            if st.button("⚡ Extract all companies from directory",
                         key=f"det_extract_{cid}", type="primary", use_container_width=True):
                with st.spinner("Extracting with AI…"):
                    try:
                        r = _api_post("/leads/extract-directory",
                                      json={"website":website,
                                            "content":row.get("content",""),
                                            "query":st.session_state.active_query},
                                      timeout=120)
                        if r.status_code == 200:
                            cos = r.json().get("companies",[])
                            updated = dict(st.session_state.card_details.get(cid,row))
                            updated["directory_companies"] = cos
                            st.session_state.card_details[cid] = updated
                            st.success(f"✅ Extracted {len(cos)} companies!")
                            st.rerun()
                        else:
                            st.error(f"Failed: {r.text}")
                    except Exception as e:
                        st.error(str(e))


# ---------------------------------------------------------------------------
# Master list
# ---------------------------------------------------------------------------
def _render_list(leads, key_suffix):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="icon">🔍</div>
          <h3>No results for these filters</h3>
          <p>Try removing some filters or adjusting your search.</p>
        </div>
        """, unsafe_allow_html=True)
        return
    for idx, row in enumerate(leads):
        cid = _card_id(row, idx)
        _render_lead_row(row, cid, idx, key_suffix)


# ---------------------------------------------------------------------------
# Main results view
# ---------------------------------------------------------------------------
def _show_results(leads, key_suffix="tab"):
    filtered = _apply_filters(leads)
    count_txt = (f"{len(filtered)} of {len(leads)}" if len(filtered)!=len(leads)
                 else str(len(leads)))

    hc1, hc2, hc3 = st.columns([4, 1, 1])
    with hc1:
        st.caption(f"**{count_txt} companies** · Click Open → to view details")
    with hc2:
        view = st.radio("View", ["List","Table"], horizontal=True,
                        key=f"view_{key_suffix}", index=0)
    with hc3:
        if filtered:
            df_exp = pd.DataFrame(filtered)
            for c in ["compliance_gaps","products","certifications","export_markets","key_customers"]:
                if c in df_exp.columns:
                    df_exp[c] = df_exp[c].apply(
                        lambda v: ", ".join(str(x) for x in v) if isinstance(v,list) else str(v or ""))
            st.download_button("⬇ CSV",
                               data=df_exp.to_csv(index=False).encode("utf-8"),
                               file_name=f"leads_{key_suffix}.csv", mime="text/csv",
                               key=f"dl_exp_{key_suffix}_{len(filtered)}")

    if view == "Table":
        _show_table(filtered, key_suffix=key_suffix)
        return

    # Master-detail
    selected_cid = st.session_state.get("selected_card")
    show_detail  = (
        selected_cid is not None
        and selected_cid in st.session_state.card_details
        and st.session_state.get("selected_tab","") == key_suffix
    )

    if show_detail:
        col_left, col_right = st.columns([2, 3], gap="medium")
        with col_left:
            _render_list(filtered, key_suffix)
        with col_right:
            _render_detail_panel(selected_cid)
    else:
        _render_list(filtered, key_suffix)


# ===========================================================================
# RESULTS SECTION
# ===========================================================================
if company_leads:
    st.markdown("---")
    _show_metrics(company_leads)

    st.markdown('<div style="padding:14px 24px 0;">', unsafe_allow_html=True)

    tab_all, tab_high, tab_gaps, tab_mfg, tab_imp, tab_trade, tab_dir = st.tabs([
        f"All ({len(company_leads)})",
        "⭐ High Priority",
        "⚠ Compliance Gaps",
        "🏭 Manufacturers",
        "📦 Importers",
        "🤝 Traders",
        "📂 Directories",
    ])

    with tab_all:
        _show_results(company_leads, "all")

    with tab_high:
        high_leads = [x for x in company_leads if str(x.get("importance","")).lower()=="high"]
        _show_results(high_leads, "high")

    with tab_gaps:
        st.markdown(
            '<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:7px;'
            'padding:10px 14px;font-size:12px;color:#991B1B;margin-bottom:10px;">'
            '⚠️ Companies missing BIS, GST, IEC, or MCA registrations — prime prospects for compliance services.</div>',
            unsafe_allow_html=True)
        gap_leads = [x for x in company_leads
                     if isinstance(x.get("compliance_gaps"),list) and len(x["compliance_gaps"])>0]
        _show_results(gap_leads, "gaps")

    with tab_mfg:
        mfg_leads = [x for x in company_leads if x.get("channel_type")=="Manufacturer"]
        _show_results(mfg_leads, "mfg")

    with tab_imp:
        imp_leads = [x for x in company_leads if x.get("channel_type")=="Importer"]
        _show_results(imp_leads, "imp")

    with tab_trade:
        trade_leads = [x for x in company_leads
                       if x.get("channel_type") in ("Trader","Distributor","Wholesaler","Retailer")]
        _show_results(trade_leads, "trade")

    with tab_dir:
        st.caption("Pages that list multiple companies — expand to extract all leads inside.")
        dir_leads = [x for x in company_leads if x.get("is_directory")]

        with st.expander("📥 Scan a directory URL manually", expanded=False):
            manual_url   = st.text_input("Directory URL", placeholder="https://www.indiamart.com/...", key="manual_dir_url")
            manual_query = st.text_input("What companies are listed here?", placeholder="electronics importers", key="manual_dir_query")
            if st.button("Scan", key="manual_dir_btn", type="primary"):
                if manual_url:
                    with st.spinner("Scanning…"):
                        try:
                            r = _api_post("/leads/extract-directory",
                                json={"website":manual_url,"content":"",
                                      "query":manual_query or st.session_state.active_query},
                                timeout=90)
                            if r.status_code == 200:
                                st.session_state["manual_dir_result"] = r.json()
                        except Exception as e:
                            st.error(str(e))

            if st.session_state.get("manual_dir_result"):
                res   = st.session_state["manual_dir_result"]
                found = res.get("extracted",0)
                saved = res.get("saved",0)
                cos   = res.get("companies",[])
                st.success(f"✅ Found {found} companies, saved {saved}")
                if cos:
                    rows = [{"Company":c.get("company",""),"City":c.get("city",""),
                             "Phone":c.get("phone",""),"Email":c.get("email",""),
                             "Website":c.get("website",""),"Products":c.get("products","")} for c in cos]
                    st.dataframe(pd.DataFrame(rows), use_container_width=True)

        if not dir_leads:
            st.markdown("""
            <div style="background:#FFFBEB;border:1px solid #FCD34D;border-radius:8px;
                 padding:14px 16px;font-size:13px;color:#78350F;">
              <strong>No directories detected yet.</strong> Try searching for terms like
              <em>electronics importers list india</em> or
              <em>manufacturers directory Gujarat</em>.
            </div>
            """, unsafe_allow_html=True)
        else:
            _show_results(dir_leads, "dir")

    st.markdown('</div>', unsafe_allow_html=True)

    # LinkedIn
    linkedin_leads = [x for x in raw_leads if x.get("source")=="linkedin_semantic"]
    if linkedin_leads:
        st.markdown('<div style="padding:0 24px;">', unsafe_allow_html=True)
        with st.expander(f"👤 LinkedIn Contacts ({len(linkedin_leads)})", expanded=False):
            ld   = pd.DataFrame(linkedin_leads)
            cols = ["name","profile","snippet","searched_query","created_at"]
            st.dataframe(ld[[c for c in cols if c in ld.columns]], use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # Compliance enrichment
    st.markdown('<div style="padding:0 24px 24px;">', unsafe_allow_html=True)
    with st.expander("🔬 Check Licences & Registrations (BIS · GST · IEC · MCA)", expanded=False):
        st.caption("Check which companies are missing Indian business registrations. Takes 1–2 minutes.")
        n = st.slider("Companies to check", 5, 100, 20, key="enrich_n")
        cf_e = "" if st.session_state.sf_country=="Any Country" else st.session_state.sf_country.lower()
        if st.button("▶ Start checking", key="enrich_btn", type="primary"):
            with st.spinner("Checking registrations…"):
                try:
                    r = _api_post("/leads/enrich-compliance",
                                  params={"limit":n,"country_filter":cf_e},
                                  timeout=300)
                    if r.status_code == 200:
                        st.success(f"✅ Checked {r.json().get('checked',0)} companies. Refresh to see results.")
                    else:
                        st.error("Check failed.")
                except Exception as e:
                    st.error(str(e))
    st.markdown('</div>', unsafe_allow_html=True)

elif not st.session_state.active_job_id:
    st.markdown("""
    <div class="empty-state" style="margin-top:40px">
      <div class="icon">🌐</div>
      <h3>Ready to find leads</h3>
      <p>Search for any type of business above.<br>
         Try: <em>"electronics importers Gujarat"</em></p>
    </div>
    """, unsafe_allow_html=True)
