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

st.set_page_config(
    page_title="Buyera",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# DESIGN SYSTEM — Minimalist, high-signal, zero clutter
# Token palette: near-white surface, ink text, single blue accent, semantic colours
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=DM+Sans:wght@700;800&display=swap');

/* ── Reset & base ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body, .stApp {
    font-family: 'Inter', sans-serif;
    font-size: 14px;
    color: #0f172a;
    background: #f8f9fb;
    line-height: 1.6;
}

/* Hide Streamlit chrome */
#MainMenu, footer, header,
[data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; visibility: hidden !important; }

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #ffffff !important;
    border-right: 1px solid #e8eaed !important;
    padding-top: 0 !important;
}
[data-testid="stSidebar"] > div:first-child { padding: 0 !important; }
[data-testid="stSidebar"] * { color: #0f172a !important; }
[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] .stTextInput input {
    background: #f8f9fb !important;
    border: 1px solid #e8eaed !important;
    font-size: 0.8rem !important;
    border-radius: 6px !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 0.7rem !important;
    font-weight: 600 !important;
    color: #64748b !important;
    text-transform: uppercase;
    letter-spacing: 0.06em;
}

/* ── Sidebar brand header ── */
.sb-brand {
    padding: 20px 20px 16px;
    border-bottom: 1px solid #e8eaed;
    margin-bottom: 4px;
}
.sb-brand-name {
    font-family: 'DM Sans', sans-serif;
    font-size: 1.1rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.03em;
}
.sb-brand-name span { color: #2563eb; }
.sb-user {
    font-size: 0.72rem;
    color: #94a3b8;
    margin-top: 3px;
}
.sb-section-label {
    font-size: 0.65rem;
    font-weight: 700;
    color: #94a3b8;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 14px 20px 6px;
}

/* ── Topbar ── */
.topbar {
    background: #ffffff;
    border-bottom: 1px solid #e8eaed;
    padding: 12px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: -1rem -1rem 0 -1rem;
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-brand {
    font-family: 'DM Sans', sans-serif;
    font-size: 1rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.03em;
}
.topbar-brand span { color: #2563eb; }
.topbar-user {
    font-size: 0.75rem;
    color: #64748b;
    background: #f1f5f9;
    padding: 5px 12px;
    border-radius: 100px;
    font-weight: 500;
}

/* ── Search bar area ── */
.search-wrap {
    padding: 28px 0 16px;
}
.search-heading {
    font-family: 'DM Sans', sans-serif;
    font-size: 1.5rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.04em;
    margin-bottom: 4px;
}
.search-sub {
    font-size: 0.82rem;
    color: #64748b;
    margin-bottom: 16px;
}
.search-chips {
    display: flex;
    gap: 6px;
    flex-wrap: wrap;
    margin-top: 10px;
}
.search-chip {
    font-size: 0.72rem;
    color: #2563eb;
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    padding: 3px 10px;
    border-radius: 100px;
    cursor: pointer;
    font-weight: 500;
}

/* ── Inputs ── */
.stTextInput input {
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 8px !important;
    font-size: 0.9rem !important;
    padding: 10px 14px !important;
    background: #ffffff !important;
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
    transition: border-color 0.15s !important;
}
.stTextInput input:focus {
    border-color: #2563eb !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.08) !important;
}
.stTextInput input::placeholder {
    color: #94a3b8 !important;
    -webkit-text-fill-color: #94a3b8 !important;
}

/* ── Buttons ── */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    border-radius: 7px !important;
    padding: 8px 16px !important;
    transition: all 0.13s !important;
    border: 1.5px solid #e2e8f0 !important;
    background: #ffffff !important;
    color: #0f172a !important;
}
.stButton > button:hover {
    border-color: #2563eb !important;
    color: #2563eb !important;
    background: #eff6ff !important;
}
/* Primary action button */
.btn-primary .stButton > button {
    background: #2563eb !important;
    color: #ffffff !important;
    border-color: #2563eb !important;
}
.btn-primary .stButton > button:hover {
    background: #1d4ed8 !important;
    border-color: #1d4ed8 !important;
    color: #ffffff !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div {
    border: 1.5px solid #e2e8f0 !important;
    border-radius: 7px !important;
    background: #ffffff !important;
    font-size: 0.82rem !important;
    color: #0f172a !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] [class*="singleValue"],
div[data-baseweb="select"] input {
    color: #0f172a !important;
    -webkit-text-fill-color: #0f172a !important;
}
ul[role="listbox"],
[data-baseweb="popover"],
[data-baseweb="menu"] > div {
    background: #ffffff !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.1) !important;
}
[role="option"] { background: #ffffff !important; color: #0f172a !important; }
[role="option"]:hover,
[aria-selected="true"][role="option"] {
    background: #eff6ff !important;
    color: #2563eb !important;
}
[role="option"] * { color: inherit !important; }

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    background: white !important;
    border: none !important;
    gap: 0 !important;
    border-bottom: 1px solid #e2e8f0;
    padding: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    border-radius: 0 !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 8px 16px !important;
    color: #64748b !important;
    border-bottom: 2px solid transparent !important;
    background: white !important;
    margin-bottom: -1px;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #2563eb !important;
    border-bottom-color: #2563eb !important;
    background: white !important;
    font-weight: 600 !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #ffffff !important;
    border: 1px solid #e8eaed !important;
    border-radius: 10px !important;
    padding: 14px 18px !important;
}
[data-testid="stMetricValue"] {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 1.6rem !important;
    font-weight: 800 !important;
    color: #0f172a !important;
    letter-spacing: -0.03em !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important;
    color: #94a3b8 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.06em !important;
    font-weight: 600 !important;
}

/* ── Lead card — compact row ── */
.lead-row {
    background: #ffffff;
    border: 1px solid #e8eaed;
    border-radius: 8px;
    padding: 10px 14px;
    margin-bottom: 4px;
    display: flex;
    align-items: center;
    gap: 10px;
    transition: border-color 0.12s, box-shadow 0.12s;
}
.lead-row:hover {
    border-color: #93c5fd;
    box-shadow: 0 2px 8px rgba(37,99,235,0.06);
}
.lead-row.sel {
    border-color: #2563eb;
    background: #f0f7ff;
}
.lead-icon {
    width: 32px; height: 32px;
    border-radius: 7px;
    background: #f1f5f9;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.95rem; flex-shrink: 0;
}
.lead-body { flex: 1; min-width: 0; }
.lead-name {
    font-size: 0.83rem; font-weight: 600; color: #0f172a;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.lead-meta {
    font-size: 0.68rem; color: #94a3b8; margin-top: 1px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.lead-badges { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }

/* ── Badges / pills ── */
.badge {
    display: inline-flex; align-items: center;
    padding: 2px 7px;
    border-radius: 100px;
    font-size: 0.65rem;
    font-weight: 600;
    letter-spacing: 0.02em;
    white-space: nowrap;
}
.badge-high    { background: #dcfce7; color: #15803d; }
.badge-medium  { background: #fef9c3; color: #92400e; }
.badge-low     { background: #f1f5f9; color: #64748b; }
.badge-gap     { background: #fee2e2; color: #b91c1c; }
.badge-clean   { background: #f0fdf4; color: #15803d; }
.badge-score   {
    background: #eff6ff; color: #2563eb;
    border: 1px solid #bfdbfe;
    font-family: 'DM Sans', sans-serif;
    font-weight: 700;
}
.badge-dir     { background: #faf5ff; color: #7c3aed; }

/* ── Detail panel ── */
.detail-card {
    background: #ffffff;
    border: 1px solid #e8eaed;
    border-radius: 10px;
    padding: 20px 22px;
    position: sticky;
    top: 60px;
    max-height: calc(100vh - 140px);
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #e2e8f0 transparent;
}
.detail-card::-webkit-scrollbar { width: 3px; }
.detail-card::-webkit-scrollbar-thumb { background: #e2e8f0; border-radius: 3px; }

.detail-empty {
    background: #ffffff;
    border: 1.5px dashed #e2e8f0;
    border-radius: 10px;
    padding: 48px 24px;
    text-align: center;
    color: #94a3b8;
}
.detail-empty .de-icon { font-size: 2rem; margin-bottom: 10px; }
.detail-empty p { font-size: 0.78rem; line-height: 1.5; color: #94a3b8; }

.d-company {
    font-family: 'DM Sans', sans-serif;
    font-size: 1.05rem;
    font-weight: 800;
    color: #0f172a;
    letter-spacing: -0.02em;
    margin-bottom: 2px;
}
.d-sub { font-size: 0.74rem; color: #64748b; margin-bottom: 12px; }
.d-tags { display: flex; flex-wrap: wrap; gap: 4px; margin-bottom: 12px; }
.d-tag {
    font-size: 0.66rem; font-weight: 500;
    background: #f1f5f9; color: #475569;
    padding: 2px 8px; border-radius: 5px;
}
.d-section {
    font-size: 0.62rem; font-weight: 700;
    color: #94a3b8; text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 14px 0 5px;
    padding-top: 12px;
    border-top: 1px solid #f1f5f9;
}
.d-body { font-size: 0.79rem; color: #334155; line-height: 1.65; }
.d-links { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; padding-top: 12px; border-top: 1px solid #f1f5f9; }
.d-link {
    font-size: 0.75rem; font-weight: 600;
    color: #2563eb; text-decoration: none;
}

/* ── Info / status bar ── */
.info-bar {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 7px;
    padding: 10px 14px;
    font-size: 0.78rem;
    color: #1d4ed8;
    margin-bottom: 12px;
}
.warn-bar {
    background: #fefce8;
    border: 1px solid #fde68a;
    border-radius: 7px;
    padding: 10px 14px;
    font-size: 0.78rem;
    color: #78350f;
    margin-bottom: 8px;
}

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #ffffff !important;
    border: 1px solid #e8eaed !important;
    border-radius: 8px !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary {
    color: #0f172a !important; font-weight: 600 !important; font-size: 0.82rem !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
[data-testid="stDataFrame"] table,
[data-testid="stDataFrame"] th,
[data-testid="stDataFrame"] td { color: #0f172a !important; font-size: 0.78rem !important; }

/* ── Alert / toast ── */
.stAlert { border-radius: 7px !important; }
[data-testid="stToast"] p { color: #0f172a !important; }

/* ── Download button ── */
.stDownloadButton > button {
    background: #ffffff !important;
    color: #0f172a !important;
    border: 1.5px solid #e2e8f0 !important;
    font-size: 0.78rem !important;
    border-radius: 7px !important;
}
.stDownloadButton > button:hover {
    border-color: #2563eb !important;
    color: #2563eb !important;
}

/* ── Slider ── */
.stProgress > div > div,
.stSlider .st-b3 { background: #2563eb !important; }

/* ── Checkbox ── */
.stCheckbox label span { color: #0f172a !important; font-size: 0.82rem !important; }

/* ── Global colour blanket (keep labels readable) ── */
label, p, span, div,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
.stMarkdown p { color: #0f172a; }
.stCaption, [data-testid="stCaptionContainer"] p { color: #64748b !important; }
::selection { background: #bfdbfe; color: #1e40af; }

/* ── Dir item ── */
.dir-row {
    background: #f8f9fb; border: 1px solid #e8eaed;
    border-radius: 6px; padding: 7px 11px; margin-bottom: 3px;
    font-size: 0.75rem; color: #334155;
}
.dir-row strong { color: #0f172a; }

/* ── Empty state ── */
.empty-state {
    text-align: center;
    padding: 60px 20px;
    color: #94a3b8;
}
.empty-state .ei { font-size: 2.5rem; margin-bottom: 10px; }
.empty-state h3 { font-size: 0.95rem; color: #64748b; font-weight: 600; margin-bottom: 4px; }
.empty-state p  { font-size: 0.78rem; }

/* ── Logout secondary button special case ── */
div[data-testid="stButton"]:has(button[key="logout_btn"]) button,
div[data-testid="stButton"]:has(button[key="sb_logout_btn"]) button {
    background: white !important;
    border: 1px solid #e2e8f0 !important;
    color: #64748b !important;
    font-size: 0.75rem !important;
    padding: 5px 12px !important;
}
div[data-testid="stButton"]:has(button[key="logout_btn"]) button:hover,
div[data-testid="stButton"]:has(button[key="sb_logout_btn"]) button:hover {
    border-color: #f87171 !important;
    color: #b91c1c !important;
    background: #fef2f2 !important;
}

/* ── Radio (Cards / Table toggle) ── */
.stRadio > div label p { font-size: 0.78rem !important; color: #0f172a !important; }

/* ── Tag for money / green ── */
.d-tag-green { background: #f0fdf4 !important; color: #15803d !important; }

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
    _, mid, _ = st.columns([1, 1.2, 1])
    with mid:
        st.markdown("""
        <div style="text-align:center;padding:48px 0 28px">
            <div style="font-family:'DM Sans',sans-serif;font-size:1.8rem;font-weight:800;
                        color:#0f172a;letter-spacing:-0.04em;margin-bottom:6px">
                Bue<span style="color:#2563eb">ra</span>
            </div>
            <p style="color:#64748b;font-size:0.85rem;margin:0">
                Find business leads — fast.
            </p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_reg = st.tabs(["Sign in", "Create account"])

        with tab_login:
            with st.form("lf"):
                uname = st.text_input("Username")
                pwd   = st.text_input("Password", type="password")
                sub   = st.form_submit_button("Sign in", use_container_width=True)
            if sub:
                if not uname or not pwd:
                    st.error("Enter your username and password.")
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
                            try:    err = r.json().get("detail", "Sign in failed.")
                            except: err = f"Sign in failed (HTTP {r.status_code})"
                            st.error(err)
                    except Exception as e:
                        st.error(f"Can't reach server: {e}")

        with tab_reg:
            with st.form("rf"):
                nu  = st.text_input("Username")
                ne  = st.text_input("Email (optional)")
                np  = st.text_input("Password", type="password")
                np2 = st.text_input("Confirm password", type="password")
                sub2 = st.form_submit_button("Create account", use_container_width=True)
            if sub2:
                if not nu or not np:
                    st.error("Username and password are required.")
                elif np != np2:
                    st.error("Passwords don't match.")
                elif len(np) < 6:
                    st.error("Password must be at least 6 characters.")
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
                            try:    err = r.json().get("detail", "Registration failed.")
                            except: err = f"Registration failed (HTTP {r.status_code})"
                            st.error(err)
                    except Exception as e:
                        st.error(f"Can't reach server: {e}")

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
    "no_gst":        "No GST Registration",
    "no_iec":        "No IEC Code",
    "mca_not_found": "Not Registered (MCA)",
    "mca_inactive":  "Company Struck Off",
}

ALL_INDUSTRIES = [
    "Electronics","Pharmaceuticals","Textiles","Chemicals","Machinery",
    "Food & Beverage","Automotive","Construction","IT & Software",
    "Healthcare","Logistics","Agriculture","Energy","Retail",
]

CHANNEL_TYPES = ["Manufacturer","Importer","Trader","Wholesaler","Distributor","Retailer"]

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
    "France":    ["Île-de-France","Auvergne-Rhône-Alpes","Provence-Alpes-Côte d'Azur"],
    "Japan":     ["Tokyo","Osaka","Kanagawa","Aichi"],
}
ALL_COUNTRIES = ["Any Country"] + sorted(COUNTRY_STATES.keys())

ALL_COLUMNS = {
    "company":"Company Name","city":"City","country_detected":"Country",
    "industry_detected":"Industry","product_type":"Products / Services",
    "channel_type":"Business Type","company_size":"Company Size",
    "incorporation_date":"Year Founded","importance":"Priority",
    "final_score":"Match Score","compliance_gaps":"Compliance Issues",
    "bis_certified":"BIS Certified","gst_registered":"GST Registered",
    "iec_found":"IEC Code","mca_active":"MCA Status",
    "contact_person":"Contact Name","contact_email":"Contact Email",
    "email":"Email Address","phone":"Phone Number","linkedin_url":"LinkedIn",
    "active_website":"Website","ai_summary":"About the Company",
    "products":"Product List","mca_company_type":"Company Category",
    "domain_authority":"Website Authority","searched_query":"Search Query Used",
    "created_at":"Date Found","annual_turnover":"Annual Turnover / Revenue",
    "certifications":"Certifications","export_markets":"Export Markets",
    "usp":"Unique Selling Point","key_customers":"Key Customers",
    "llm_score":"AI Relevance Score","grok_score":"Grok Score",
    "contact_title":"Contact Title","contact_confidence":"Contact Confidence",
    "is_valid_lead":"Valid Lead","rejection_reason":"Rejection Reason",
    "twitter_url":"X (Twitter)","facebook_url":"Facebook",
    "instagram_url":"Instagram","youtube_url":"YouTube","whatsapp_url":"WhatsApp",
    "is_directory":"Is Directory","directory_count":"Directory Size",
}

DEFAULT_COLUMNS = [
    "company","city","country_detected","industry_detected",
    "channel_type","importance","final_score","compliance_gaps",
    "email","phone","active_website","ai_summary",
]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "active_job_id": "", "active_query": "",
    "live_results": [], "live_cursor": 0, "notified_jobs": [],
    "sf_query": "", "sf_country": "Any Country", "sf_state": "Any",
    "sf_industry": "Any", "sf_channel": "Any", "sf_importance": "Any",
    "sf_min_score": 0.0, "sf_sort": "Best Match First",
    "sf_has_email": False, "sf_has_phone": False, "sf_gaps_only": False,
    "visible_cols": DEFAULT_COLUMNS[:], "view_mode": "Cards",
    "scan_all": False, "quality_threshold": 0, "sf_city": "Any",
    "_reset_filters": False,
    "expanded_cards": {}, "card_details": {},
    "selected_card": None, "selected_tab": "",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()

if st.session_state.get("_reset_filters"):
    st.session_state["_reset_filters"] = False
    for _k, _v in {
        "sf_country":"Any Country","sf_state":"Any","sf_city":"Any",
        "sf_industry":"Any","sf_channel":"Any","sf_importance":"Any",
        "sf_min_score":0.0,"sf_has_email":False,"sf_has_phone":False,
        "sf_gaps_only":False,"quality_threshold":0,"scan_all":False,
        "sf_sort":"Best Match First","sf_query":"",
    }.items():
        st.session_state[_k] = _v
    st.rerun()

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"""
    <div class="sb-brand">
        <div class="sb-brand-name">Bue<span>ra</span></div>
        <div class="sb-user">{st.session_state.auth_username}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Sign out", key="sb_logout_btn", use_container_width=True):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

    st.markdown('<div class="sb-section-label">Filters</div>', unsafe_allow_html=True)

    _ctr_idx = ALL_COUNTRIES.index(st.session_state.sf_country) \
               if st.session_state.sf_country in ALL_COUNTRIES else 0
    st.session_state.sf_country = st.selectbox(
        "Country", ALL_COUNTRIES, index=_ctr_idx, key="sb_country_sel")

    _state_opts = (["Any"] + COUNTRY_STATES.get(st.session_state.sf_country, [])
                   if st.session_state.sf_country != "Any Country" else ["Any"])
    if st.session_state.sf_state not in _state_opts:
        st.session_state.sf_state = "Any"
    st.session_state.sf_state = st.selectbox(
        "State / Region", _state_opts,
        index=_state_opts.index(st.session_state.sf_state),
        key="sb_state_sel",
        disabled=(st.session_state.sf_country == "Any Country"))

    _ind_opts = ["Any"] + ALL_INDUSTRIES
    st.session_state.sf_industry = st.selectbox(
        "Industry", _ind_opts,
        index=_ind_opts.index(st.session_state.sf_industry)
              if st.session_state.sf_industry in _ind_opts else 0,
        key="sb_industry_sel")

    _ch_opts = ["Any"] + CHANNEL_TYPES
    st.session_state.sf_channel = st.selectbox(
        "Business type", _ch_opts,
        index=_ch_opts.index(st.session_state.sf_channel)
              if st.session_state.sf_channel in _ch_opts else 0,
        key="sb_channel_sel")

    _imp_opts = ["Any", "High ⭐", "Medium", "Low"]
    st.session_state.sf_importance = st.selectbox(
        "Priority", _imp_opts,
        index=_imp_opts.index(st.session_state.sf_importance)
              if st.session_state.sf_importance in _imp_opts else 0,
        key="sb_importance_sel")

    _sort_opts = ["Best Match First","Priority (High → Low)",
                  "Company Name A → Z","Company Name Z → A","Newest First"]
    st.session_state.sf_sort = st.selectbox(
        "Sort by", _sort_opts,
        index=_sort_opts.index(st.session_state.sf_sort)
              if st.session_state.sf_sort in _sort_opts else 0,
        key="sb_sort_sel")

    st.session_state.sf_min_score = st.slider(
        "Min score", 0.0, 1.0, st.session_state.sf_min_score, 0.05, key="sb_score_sl")

    st.markdown('<div class="sb-section-label">Quick filters</div>', unsafe_allow_html=True)
    st.session_state.sf_has_email = st.checkbox("Has email",  key="sb_email_cb",
                                                 value=st.session_state.sf_has_email)
    st.session_state.sf_has_phone = st.checkbox("Has phone",  key="sb_phone_cb",
                                                 value=st.session_state.sf_has_phone)
    st.session_state.sf_gaps_only = st.checkbox("Compliance issues only", key="sb_gaps_cb",
                                                  value=st.session_state.sf_gaps_only)

    st.markdown('<div class="sb-section-label">Search options</div>', unsafe_allow_html=True)
    st.session_state.scan_all = st.checkbox("Scan all pages (slower)", key="sb_scan_cb",
                                             value=st.session_state.scan_all)
    _qt_labels = ["All","Basic","Good","Best"]
    _qt_map    = {"All":0,"Basic":1,"Good":2,"Best":3}
    _qt_rev    = {0:"All",1:"Basic",2:"Good",3:"Best"}
    _qt_cur    = _qt_rev.get(st.session_state.quality_threshold, "All")
    _qt_sel    = st.select_slider("Result quality", _qt_labels, value=_qt_cur, key="sb_qt_sl")
    st.session_state.quality_threshold = _qt_map[_qt_sel]

    st.markdown("---")
    c1, c2 = st.columns(2)
    with c1:
        if st.button("Clear filters", use_container_width=True, key="sb_clear_btn"):
            st.session_state["_reset_filters"] = True
            st.rerun()
    with c2:
        if st.button("Delete leads", use_container_width=True, key="sb_del_btn"):
            try:
                _api_delete("/clear", timeout=15)
                for _k in ["active_job_id","active_query","live_results","live_cursor",
                            "notified_jobs","expanded_cards","card_details",
                            "selected_card","selected_tab"]:
                    st.session_state[_k] = _DEFAULTS[_k] if not isinstance(
                        _DEFAULTS[_k], (list,dict)) else type(_DEFAULTS[_k])()
                st.rerun()
            except Exception as e:
                st.error(str(e))

# ---------------------------------------------------------------------------
# Top nav
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="topbar">
  <div class="topbar-brand">Bue<span>ra</span></div>
  <div class="topbar-user">👤 {st.session_state.auth_username}</div>
</div>
""", unsafe_allow_html=True)

lcol = st.columns([8, 1])[1]
with lcol:
    if st.button("Sign out", key="logout_btn"):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

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
# Search bar
# ---------------------------------------------------------------------------
st.markdown("""
<div class="search-wrap">
  <div class="search-heading">Find your next customer</div>
  <div class="search-sub">Search for importers, manufacturers, distributors — anywhere.</div>
</div>
""", unsafe_allow_html=True)

sc1, sc2, sc3 = st.columns([6, 1, 1])
with sc1:
    query = st.text_input(
        "q", value=st.session_state.sf_query,
        placeholder='e.g. "LED importers Gujarat" or "pharma distributors Mumbai"',
        label_visibility="collapsed", key="search_input_box")
    st.session_state.sf_query = query

with sc2:
    st.markdown('<div class="btn-primary">', unsafe_allow_html=True)
    search_clicked = st.button("Search", use_container_width=True, key="main_search_btn")
    st.markdown('</div>', unsafe_allow_html=True)

with sc3:
    refresh_clicked = st.button("Refresh", use_container_width=True, key="refresh_btn")
    if refresh_clicked:
        st.rerun()

st.markdown("""
<div class="search-chips">
  <span class="search-chip">Electronics importers Delhi</span>
  <span class="search-chip">Textile manufacturers Surat</span>
  <span class="search-chip">Pharma distributors Mumbai</span>
  <span class="search-chip">Steel traders UAE</span>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Build and trigger search
# ---------------------------------------------------------------------------
def _build_final_query() -> str:
    parts = [st.session_state.sf_query.strip()]
    for val, key in [(st.session_state.sf_industry,"sf_industry"),
                     (st.session_state.sf_state,"sf_state"),
                     (st.session_state.get("sf_city","Any"),"sf_city"),
                     (st.session_state.sf_country,"sf_country")]:
        skip = val in ("Any","Any Country","")
        if not skip and val.lower() not in st.session_state.sf_query.lower():
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
                "query": fq, "continue_search": "false",
                "scan_all_remaining": str(st.session_state.scan_all).lower(),
                "country_filter": cf, "trusted_only": "false",
                "quality_threshold": st.session_state.quality_threshold,
            }, timeout=30)
            if r.status_code == 200:
                d = r.json()
                st.session_state.active_job_id  = d.get("job_id","")
                st.session_state.active_query   = fq
                st.session_state.live_results   = []
                st.session_state.live_cursor    = 0
                st.session_state.expanded_cards = {}
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
        if cf: params["country_filter"] = cf
        r = _api_get("/leads", params=params, timeout=20)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return []

raw_leads     = _get_all_leads()
company_leads = [x for x in raw_leads if x.get("source") != "linkedin_semantic"]

# ---------------------------------------------------------------------------
# Live search status
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
        saved = status.get("saved_total", 0)
        pages = status.get("pages_scanned", 0)

        if sv in ("running","queued"):
            st.markdown(f"""
            <div class="info-bar">
              Searching — {saved} companies found so far · {pages} pages scanned · refreshing every {POLL_SECONDS}s
            </div>""", unsafe_allow_html=True)
            time.sleep(POLL_SECONDS)
            st.rerun()

        elif sv == "completed":
            jid = status.get("job_id","")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast(f"Done — {saved} companies found")
                st.session_state.notified_jobs.append(jid)
            if status.get("ask_continue"):
                c1, c2 = st.columns([3,2])
                with c1:
                    st.info(f"Found {saved} companies. Search more pages?")
                with c2:
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Find more", use_container_width=True):
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
                                else:
                                    st.error(f"Failed: HTTP {r.status_code}")
                            except Exception as e:
                                st.error(str(e))
                    with cc2:
                        if st.button("Done", use_container_width=True):
                            st.session_state.active_job_id = ""
                            st.rerun()
            else:
                st.success(f"Search complete — {saved} companies found.")
                st.session_state.active_job_id = ""

        elif sv == "failed":
            st.error(f"Search failed: {status.get('error','Unknown error')}")
            st.session_state.active_job_id = ""

# ---------------------------------------------------------------------------
# Apply filters
# ---------------------------------------------------------------------------
def _apply_filters(leads: list) -> list:
    df = pd.DataFrame(leads) if leads else pd.DataFrame()
    if df.empty:
        return []

    if st.session_state.sf_channel != "Any" and "channel_type" in df.columns:
        df = df[df["channel_type"].astype(str) == st.session_state.sf_channel]
    if st.session_state.get("sf_city","Any") not in ("Any","") and "city" in df.columns:
        df = df[df["city"].astype(str).str.lower().str.contains(
            st.session_state.sf_city.lower(), na=False)]
    imp_map = {"High ⭐":"high","Medium":"medium","Low":"low"}
    imp_val = imp_map.get(st.session_state.sf_importance)
    if imp_val and "importance" in df.columns:
        df = df[df["importance"].astype(str).str.lower() == imp_val]
    if st.session_state.sf_min_score > 0 and "final_score" in df.columns:
        df = df[pd.to_numeric(df["final_score"],errors="coerce").fillna(0)
                >= st.session_state.sf_min_score]
    if st.session_state.sf_has_email and "email" in df.columns:
        df = df[df["email"].astype(str).str.contains("@",na=False)]
    if st.session_state.sf_has_phone and "phone" in df.columns:
        df = df[df["phone"].astype(str).str.strip().ne("").ne("nan")]
    if st.session_state.sf_gaps_only and "compliance_gaps" in df.columns:
        df = df[df["compliance_gaps"].apply(lambda g: isinstance(g,list) and len(g)>0)]
    if st.session_state.sf_industry != "Any" and "industry_detected" in df.columns:
        df = df[df["industry_detected"].astype(str).str.lower()
                .str.contains(st.session_state.sf_industry.lower(), na=False)]

    sort = st.session_state.sf_sort
    if "final_score" in df.columns:
        scores = pd.to_numeric(df["final_score"],errors="coerce").fillna(0)
        if sort == "Best Match First":
            df = df.iloc[scores.argsort()[::-1]]
        elif sort == "Priority (High → Low)":
            order = {"high":0,"medium":1,"low":2}
            df = df.iloc[df["importance"].astype(str).str.lower()
                         .map(order).fillna(3).argsort()]
    if sort == "Company Name A → Z" and "company" in df.columns:
        df = df.sort_values("company")
    elif sort == "Company Name Z → A" and "company" in df.columns:
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

def _imp_badge(imp: str) -> str:
    imp = str(imp).lower()
    if imp == "high":   return '<span class="badge badge-high">High</span>'
    if imp == "medium": return '<span class="badge badge-medium">Med</span>'
    return '<span class="badge badge-low">Low</span>'

def _gap_badge(gaps) -> str:
    if not isinstance(gaps,list) or not gaps:
        return '<span class="badge badge-clean">✓ Clean</span>'
    return '<span class="badge badge-gap">⚠ Issues</span>'

def _channel_emoji(ch: str) -> str:
    return {"Manufacturer":"🏭","Importer":"📦","Trader":"🤝",
            "Wholesaler":"🏪","Distributor":"🚚","Retailer":"🛍️"}.get(ch,"🏢")

def _card_id(row: dict, idx: int) -> str:
    return str(row.get("_id") or f"{str(row.get('company','?'))[:20]}_{idx}")

def _fetch_ai_detail(row: dict) -> dict:
    company = row.get("company","")
    website = row.get("active_website", row.get("website",""))
    if not company:
        return row
    try:
        r = _api_post("/research/deep",
                      json={"company": company, "website": website,
                            "country": row.get("country_detected","india"),
                            "query": st.session_state.active_query},
                      timeout=45)
        if r.status_code == 200:
            data = r.json()
            enriched = dict(row)
            enriched["_research_signals"] = data.get("signals",[])
            enriched["_research_news"]    = data.get("sources",{}).get("news",[])[:3]
            enriched["_research_social"]  = data.get("social",{})
            return enriched
    except Exception:
        pass
    return row

# ---------------------------------------------------------------------------
# Metrics bar
# ---------------------------------------------------------------------------
def _show_metrics(leads: list):
    if not leads:
        return
    df    = pd.DataFrame(leads)
    total = len(df)
    high  = int((df.get("importance",pd.Series(dtype=str)).astype(str).str.lower()=="high").sum()) \
            if "importance" in df.columns else 0
    emails= int(df["email"].astype(str).str.contains("@",na=False).sum()) \
            if "email" in df.columns else 0
    gaps  = int(df["compliance_gaps"].apply(lambda g: isinstance(g,list) and len(g)>0).sum()) \
            if "compliance_gaps" in df.columns else 0
    mfg   = int((df.get("channel_type",pd.Series(dtype=str)).astype(str)=="Manufacturer").sum()) \
            if "channel_type" in df.columns else 0
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Companies",       total)
    m2.metric("High priority",   high)
    m3.metric("Have email",      emails)
    m4.metric("Compliance gaps", gaps)
    m5.metric("Manufacturers",   mfg)

# ---------------------------------------------------------------------------
# Card list (left master panel)
# ---------------------------------------------------------------------------
def _render_card_list(leads: list, key_suffix: str = ""):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="ei">🔍</div>
          <h3>No results</h3>
          <p>Try adjusting your filters or searching with different keywords.</p>
        </div>""", unsafe_allow_html=True)
        return

    selected = st.session_state.get("selected_card")

    for idx, row in enumerate(leads):
        cid      = _card_id(row, idx)
        is_sel   = (selected == cid)
        company  = _safe(row.get("company","Unknown")) or "Unknown"
        city     = _safe(row.get("city",""))
        country  = _safe(row.get("country_detected",""))
        channel  = _safe(row.get("channel_type",""))
        imp      = _safe(row.get("importance","low")) or "low"
        score    = float(row.get("final_score",0) or 0)
        gaps     = row.get("compliance_gaps",[])
        email    = _safe(row.get("email",""))
        is_dir   = bool(row.get("is_directory",False))
        loc      = ", ".join(filter(None,[city,country]))
        emoji    = "📂" if is_dir else _channel_emoji(channel)
        has_email_dot = " · 📧" if "@" in email else ""
        sel_cls  = " sel" if is_sel else ""

        meta_parts = []
        if loc:       meta_parts.append(f"📍 {loc}")
        if channel:   meta_parts.append(channel)
        if has_email_dot: meta_parts.append("has email")
        meta_str = "  ·  ".join(meta_parts)

        imp_l = imp.lower()
        if imp_l == "high":
            ib = '<span class="badge badge-high">High</span>'
        elif imp_l == "medium":
            ib = '<span class="badge badge-medium">Med</span>'
        else:
            ib = '<span class="badge badge-low">Low</span>'

        if isinstance(gaps,list) and gaps:
            gb = '<span class="badge badge-gap">⚠</span>'
        else:
            gb = '<span class="badge badge-clean">✓</span>'

        border = "#2563eb" if is_sel else "#e8eaed"
        bg     = "#f0f7ff" if is_sel else "#ffffff"

        st.markdown(f"""
        <div class="lead-row{sel_cls}" style="border-color:{border};background:{bg};">
          <div class="lead-icon">{emoji}</div>
          <div class="lead-body">
            <div class="lead-name">{company}</div>
            <div class="lead-meta">{meta_str}</div>
          </div>
          <div class="lead-badges">
            {ib} {gb}
            <span class="badge badge-score">{score:.2f}</span>
            {"<span class='badge badge-dir'>Dir</span>" if is_dir else ""}
          </div>
        </div>
        """, unsafe_allow_html=True)

        btn_label = "✓ Open" if is_sel else "Open"
        if st.button(btn_label, key=f"sel_{key_suffix}_{cid}_{idx}",
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
# Detail panel (right)
# ---------------------------------------------------------------------------
def _render_detail_panel(cid: str):
    row = st.session_state.card_details.get(cid)
    if not row:
        st.markdown("""
        <div class="detail-empty">
          <div class="de-icon">👈</div>
          <p>Select a company on the left to see details here.</p>
        </div>""", unsafe_allow_html=True)
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
    website  = _safe(row.get("active_website", row.get("website","")))
    linkedin = _safe(row.get("linkedin_url",""))
    summary  = _safe(row.get("ai_summary",""))
    products = [_safe(str(p)) for p in (row.get("products") or []) if _safe(str(p))]
    size     = _safe(row.get("company_size",""))
    founded  = _safe(row.get("incorporation_date",""))
    turnover = _safe(row.get("annual_turnover",""))
    certs    = [x for x in (row.get("certifications") or []) if _safe(str(x))]
    exports  = [x for x in (row.get("export_markets") or []) if _safe(str(x))]
    usp      = _safe(row.get("usp",""))
    key_cust = [x for x in (row.get("key_customers") or []) if _safe(str(x))]
    contact  = _safe(row.get("contact_person",""))
    c_title  = _safe(row.get("contact_title",""))
    c_conf   = _safe(row.get("contact_confidence",""))
    c_email  = _safe(row.get("contact_email",""))
    is_dir   = bool(row.get("is_directory",False))
    dir_cos  = row.get("directory_companies",[]) or []
    dir_count= int(row.get("directory_count",0) or 0)
    is_valid = bool(row.get("is_valid_lead",True))
    rejection= _safe(row.get("rejection_reason",""))
    signals  = [x for x in (row.get("_research_signals") or []) if _safe(str(x))]
    news     = row.get("_research_news") or []
    social_r = row.get("_research_social") or {}
    loc      = ", ".join(filter(None,[city,country]))

    # Importance badge
    imp_l = imp.lower()
    if imp_l == "high":
        ib = '<span class="badge badge-high">⭐ High</span>'
    elif imp_l == "medium":
        ib = '<span class="badge badge-medium">Medium</span>'
    else:
        ib = '<span class="badge badge-low">Low</span>'

    # Tags row
    tag_parts = [t for t in [industry, channel, size,
                              f"Est. {founded}" if founded else ""] if t]
    tags_html = "".join(f'<span class="d-tag">{t}</span>' for t in tag_parts)
    if turnover:
        tags_html += f'<span class="d-tag d-tag-green">💰 {turnover}</span>'

    # Compliance
    if isinstance(gaps,list) and gaps:
        gap_html = " ".join(
            f'<span class="badge badge-gap" style="margin-right:3px">⚠ {GAP_LABELS.get(g,g)}</span>'
            for g in gaps)
    else:
        gap_html = '<span class="badge badge-clean">✓ No compliance issues</span>'

    # Links
    links_parts = []
    if website:
        links_parts.append(f'<a class="d-link" href="{website}" target="_blank">🌐 Website</a>')
    if email and "@" in email:
        links_parts.append(f'<a class="d-link" href="mailto:{email}">📧 {email}</a>')
    if phone:
        links_parts.append(f'<span class="d-link">📞 {phone}</span>')
    if linkedin:
        links_parts.append(f'<a class="d-link" href="{linkedin}" target="_blank">💼 LinkedIn</a>')
    for field, icon, label in [("twitter_url","🐦","X"),("facebook_url","📘","FB"),
                                ("instagram_url","📸","IG"),("youtube_url","▶️","YT"),
                                ("whatsapp_url","💬","WA")]:
        v = _safe(str(row.get(field,"")))
        if v: links_parts.append(f'<a class="d-link" href="{v}" target="_blank">{icon} {label}</a>')
    for plat, icon in [("linkedin","💼"),("twitter","🐦"),("facebook","📘"),
                       ("instagram","📸"),("youtube","▶️")]:
        v = _safe(str(social_r.get(plat,"")))
        if v and not _safe(str(row.get(plat+"_url",""))):
            links_parts.append(f'<a class="d-link" href="{v}" target="_blank">{icon}</a>')
    links_html = "".join(links_parts)

    def _sec(title, content):
        return (f'<div class="d-section">{title}</div>'
                f'<div class="d-body">{content}</div>')

    prod_str = " · ".join(products[:8])

    html = [f"""
    <div class="detail-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;
                  gap:8px;flex-wrap:wrap;margin-bottom:4px;">
        <div style="flex:1;min-width:0;">
          <div class="d-company">{company}</div>
          <div class="d-sub">
            {"📍 "+loc+"  ·  " if loc else ""}{(channel+" "+_channel_emoji(channel)) if channel else ""}
          </div>
        </div>
        <div style="display:flex;gap:4px;align-items:center;flex-wrap:wrap;">
          {ib}
          <span class="badge badge-score">{score:.2f}</span>
          {"<span class='badge badge-dir'>📂 Dir</span>" if is_dir else ""}
        </div>
      </div>
    """]

    if tags_html:
        html.append(f'<div class="d-tags">{tags_html}</div>')
    if summary:
        html.append(_sec("About", summary))
    if usp:
        html.append(_sec("Selling point", f"<em>{usp}</em>"))
    if prod_str:
        html.append(_sec("Products &amp; services", f"📦 {prod_str}"))
    if contact:
        conf = (f' <span style="color:#059669;font-size:0.68rem">({c_conf} confidence)</span>'
                if c_conf not in ("","low") else "")
        ct = f'<strong>{contact}</strong>'
        if c_title: ct += f'  —  {c_title}'
        ct += conf
        if c_email and "@" in c_email and c_email != email:
            ct += f'<br>📧 {c_email}'
        html.append(_sec("Contact", ct))
    html.append(_sec("Compliance", gap_html))
    if certs:
        html.append(_sec("Certifications", " · ".join(certs[:8])))
    if exports:
        html.append(_sec("Export markets", " · ".join(exports[:6])))
    if key_cust:
        html.append(_sec("Key customers", " · ".join(key_cust[:4])))
    if signals:
        html.append(_sec("Signals", "  ".join(signals)))
    if news:
        news_html = "<br>".join(
            f'<a href="{n.get("url","#")}" target="_blank" class="d-link">'
            f'📰 {str(n.get("title",""))[:70]}</a>'
            for n in news[:3] if n.get("title"))
        if news_html:
            html.append(_sec("Recent news", news_html))
    if not is_valid and rejection:
        html.append(f'<div style="background:#fef2f2;border:1px solid #fecaca;border-radius:6px;'
                    f'padding:8px 11px;font-size:0.75rem;color:#b91c1c;margin-top:10px;">'
                    f'⚠ AI note: {rejection}</div>')
    if links_html:
        html.append(f'<div class="d-links">{links_html}</div>')
    html.append("</div>")

    st.markdown("".join(html), unsafe_allow_html=True)

    # Directory extraction (needs Streamlit widgets, so outside the HTML block)
    if is_dir:
        st.markdown(
            f'<div class="warn-bar">📂 Directory page — lists ~{dir_count} companies</div>',
            unsafe_allow_html=True)
        if dir_cos:
            st.markdown(f"**{len(dir_cos)} companies extracted:**")
            dir_html = []
            for c in dir_cos[:30]:
                n  = _safe(str(c.get("company",""))) or "—"
                cy = _safe(str(c.get("city","")))
                em = _safe(str(c.get("email","")))
                wb = _safe(str(c.get("website","")))
                pr = _safe(str(c.get("products","")))[:60]
                lk = ""
                if wb: lk += f' <a href="{wb}" target="_blank" class="d-link">🌐</a>'
                if em and "@" in em: lk += f' <a href="mailto:{em}" class="d-link">📧</a>'
                loc2 = f"  ·  📍 {cy}" if cy else ""
                pr2  = f'<br><span style="color:#64748b;">{pr}</span>' if pr else ""
                dir_html.append(f'<div class="dir-row"><strong>{n}</strong>{loc2}{lk}{pr2}</div>')
            st.markdown("".join(dir_html), unsafe_allow_html=True)
            if len(dir_cos) > 30:
                st.caption(f"…and {len(dir_cos)-30} more")
            df_dir = pd.DataFrame([{"Company":c.get("company",""),"City":c.get("city",""),
                "Phone":c.get("phone",""),"Email":c.get("email",""),
                "Website":c.get("website",""),"Products":c.get("products","")}
                for c in dir_cos])
            st.download_button("Download as CSV",
                               data=df_dir.to_csv(index=False).encode("utf-8"),
                               file_name=f"dir_{cid[:8]}.csv", mime="text/csv",
                               key=f"dl_det_dir_{cid}")
        else:
            if st.button("Extract all companies from directory",
                         key=f"det_extract_{cid}", type="primary",
                         use_container_width=True):
                with st.spinner("Extracting with AI…"):
                    try:
                        r = _api_post("/leads/extract-directory",
                                      json={"website": website,
                                            "content": row.get("content",""),
                                            "query": st.session_state.active_query},
                                      timeout=120)
                        if r.status_code == 200:
                            cos = r.json().get("companies",[])
                            updated = dict(st.session_state.card_details.get(cid, row))
                            updated["directory_companies"] = cos
                            st.session_state.card_details[cid] = updated
                            st.success(f"Extracted {len(cos)} companies!")
                            st.rerun()
                        else:
                            st.error(f"Extraction failed: {r.text}")
                    except Exception as e:
                        st.error(str(e))

# ---------------------------------------------------------------------------
# Table view
# ---------------------------------------------------------------------------
def _show_table(leads: list, key_suffix: str = ""):
    if not leads:
        st.info("No results. Try adjusting your filters.")
        return
    df  = pd.DataFrame(leads)
    vis = [c for c in st.session_state.visible_cols if c in df.columns]
    if not vis:
        vis = [c for c in DEFAULT_COLUMNS if c in df.columns]
    display_df = df[vis].copy()
    for col_key in ["bis_certified","gst_registered","iec_found","mca_active"]:
        if col_key in display_df.columns:
            display_df[col_key] = display_df[col_key].apply(_bool_icon)
    if "compliance_gaps" in display_df.columns:
        display_df["compliance_gaps"] = display_df["compliance_gaps"].apply(
            lambda g: ", ".join(GAP_LABELS.get(x,x) for x in g) if isinstance(g,list) else "")
    if "products" in display_df.columns:
        display_df["products"] = display_df["products"].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p,list) else str(p or ""))
    if "final_score" in display_df.columns:
        display_df["final_score"] = pd.to_numeric(display_df["final_score"],errors="coerce").round(3)
    if "created_at" in display_df.columns:
        display_df["created_at"] = pd.to_datetime(
            display_df["created_at"],errors="coerce").dt.strftime("%d %b %Y")
    display_df.rename(columns={c: ALL_COLUMNS.get(c,c) for c in display_df.columns}, inplace=True)
    st.dataframe(display_df, use_container_width=True,
                 height=min(60 + len(display_df)*36, 600))
    csv_df = df[vis].copy()
    for col in ["compliance_gaps","products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(
                lambda v: ", ".join(v) if isinstance(v,list) else str(v or ""))
    st.download_button("Download CSV", data=csv_df.to_csv(index=False).encode("utf-8"),
                       file_name=f"leads_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_{key_suffix}_{len(leads)}")

# ---------------------------------------------------------------------------
# Main results renderer
# ---------------------------------------------------------------------------
def _show_results(leads: list, key_suffix: str = "tab"):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="ei">📭</div>
          <h3>Nothing here yet</h3>
          <p>Try a different filter or run a new search.</p>
        </div>""", unsafe_allow_html=True)
        return

    filtered  = _apply_filters(leads)
    count_txt = (f"{len(filtered)} of {len(leads)}" if len(filtered) != len(leads)
                 else str(len(leads)))

    hc1, hc2 = st.columns([4,1])
    with hc1:
        st.caption(f"**{count_txt} companies** · click Open to view details")
    with hc2:
        view = st.radio("View", ["Cards","Table"], horizontal=True,
                        key=f"view_{key_suffix}",
                        index=0 if st.session_state.view_mode == "Cards" else 1)
        st.session_state.view_mode = view

    if view == "Table":
        _show_table(filtered, key_suffix=key_suffix)
        return

    # Master-detail
    selected_cid = st.session_state.get("selected_card")
    show_detail  = (selected_cid is not None
                    and selected_cid in st.session_state.card_details
                    and st.session_state.get("selected_tab","") == key_suffix)

    if show_detail:
        col_left, col_right = st.columns([2,3], gap="medium")
        with col_left:
            _render_card_list(filtered, key_suffix=key_suffix)
        with col_right:
            _render_detail_panel(selected_cid)
    else:
        _render_card_list(filtered, key_suffix=key_suffix)

    if filtered:
        df_exp = pd.DataFrame(filtered)
        for c in ["compliance_gaps","products","certifications","export_markets","key_customers"]:
            if c in df_exp.columns:
                df_exp[c] = df_exp[c].apply(
                    lambda v: ", ".join(str(x) for x in v) if isinstance(v,list) else str(v or ""))
        st.download_button("Export CSV",
                           data=df_exp.to_csv(index=False).encode("utf-8"),
                           file_name=f"leads_{key_suffix}.csv", mime="text/csv",
                           key=f"dl_exp_{key_suffix}_{len(filtered)}")

# ---------------------------------------------------------------------------
# Extracted companies helper
# ---------------------------------------------------------------------------
def _show_extracted_companies(companies: list, key_suffix: str = "", query: str = ""):
    if not companies:
        st.info("No companies extracted yet.")
        return
    st.markdown(f"**{len(companies)} companies extracted**")
    rows = [{"Company":str(c.get("company","—")),"City":str(c.get("city","—")),
             "Phone":str(c.get("phone","—")),"Email":str(c.get("email","—")),
             "Website":str(c.get("website","—")),"Products":str(c.get("products","—"))[:80],
             "About":str(c.get("snippet","—"))[:100]} for c in companies]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=min(60+len(df)*36,500))
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download CSV", data=csv,
                       file_name=f"directory_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_dir_{key_suffix}_{len(companies)}")

# ===========================================================================
# MAIN RESULTS SECTION
# ===========================================================================
if company_leads or st.session_state.active_job_id:
    st.markdown("---")

    # Inline filter expander (collapsed by default)
    with st.expander("Filters & columns", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            sel_country = st.selectbox("Country", ALL_COUNTRIES,
                index=ALL_COUNTRIES.index(st.session_state.sf_country)
                      if st.session_state.sf_country in ALL_COUNTRIES else 0,
                key="sf_country")
            state_opts = (["Any"] + COUNTRY_STATES.get(sel_country,[])
                          if sel_country != "Any Country" else ["Any"])
            if st.session_state.sf_state not in state_opts:
                st.session_state.sf_state = "Any"
            sel_state = st.selectbox("State / Region", state_opts,
                index=state_opts.index(st.session_state.sf_state)
                      if st.session_state.sf_state in state_opts else 0,
                key="sf_state", disabled=(sel_country=="Any Country"))
        with f2:
            st.selectbox("Industry", ["Any"]+ALL_INDUSTRIES,
                index=(["Any"]+ALL_INDUSTRIES).index(st.session_state.sf_industry)
                      if st.session_state.sf_industry in ["Any"]+ALL_INDUSTRIES else 0,
                key="sf_industry")
            st.selectbox("Business type", ["Any"]+CHANNEL_TYPES,
                index=(["Any"]+CHANNEL_TYPES).index(st.session_state.sf_channel)
                      if st.session_state.sf_channel in ["Any"]+CHANNEL_TYPES else 0,
                key="sf_channel")
        with f3:
            st.selectbox("Priority", ["Any","High ⭐","Medium","Low"],
                index=0, key="sf_importance")
            st.slider("Min score", 0.0, 1.0,
                st.session_state.sf_min_score, 0.05, key="sf_min_score")
        with f4:
            st.selectbox("Sort by", ["Best Match First","Priority (High → Low)",
                "Company Name A → Z","Company Name Z → A","Newest First"],
                key="sf_sort")
            st.checkbox("Has email",    key="sf_has_email")
            st.checkbox("Has phone",    key="sf_has_phone")
            st.checkbox("Compliance issues only", key="sf_gaps_only")

        ca, cb, cc = st.columns(3)
        with ca: st.checkbox("Scan all pages (slower)", key="scan_all")
        with cb:
            if st.button("Clear filters", use_container_width=True):
                st.session_state["_reset_filters"] = True
                st.rerun()
        with cc:
            if st.button("Delete all leads", use_container_width=True):
                try:
                    _api_delete("/clear", timeout=15)
                    for _k in ["active_job_id","active_query","live_results","live_cursor",
                                "notified_jobs","expanded_cards","card_details",
                                "selected_card","selected_tab"]:
                        st.session_state[_k] = _DEFAULTS[_k] if not isinstance(
                            _DEFAULTS[_k],(list,dict)) else type(_DEFAULTS[_k])()
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

        # Column picker (collapsed inside expander)
        st.markdown("---")
        st.markdown("**Choose columns for table view**")
        col_groups = {
            "Company": ["company","city","country_detected","industry_detected","product_type","channel_type","company_size","incorporation_date"],
            "Scores": ["importance","final_score","domain_authority"],
            "Compliance": ["compliance_gaps","bis_certified","gst_registered","iec_found","mca_active","mca_company_type"],
            "Contact": ["contact_person","contact_email","email","phone","linkedin_url"],
            "AI": ["ai_summary","products","usp","key_customers"],
            "Business": ["annual_turnover","certifications","export_markets","grok_score"],
            "Social": ["linkedin_url","twitter_url","facebook_url","instagram_url","youtube_url","whatsapp_url"],
            "Validation": ["is_valid_lead","rejection_reason","contact_title","contact_confidence","is_directory","directory_count"],
            "Meta": ["searched_query","created_at"],
        }
        new_visible = []
        seen_keys = set()
        for grp_name, grp_cols in col_groups.items():
            st.markdown(f"**{grp_name}**")
            gcols = st.columns(4)
            grp_prefix = re.sub(r"[^a-z0-9]","_",grp_name.lower())[:10]
            for i, col_key in enumerate(grp_cols):
                wkey = f"col_{grp_prefix}_{col_key}"
                if wkey in seen_keys: wkey = f"{wkey}_{i}"
                seen_keys.add(wkey)
                with gcols[i % 4]:
                    checked = st.checkbox(ALL_COLUMNS.get(col_key, col_key),
                                          value=(col_key in st.session_state.visible_cols),
                                          key=wkey)
                    if checked and col_key not in new_visible:
                        new_visible.append(col_key)
        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("Apply columns", use_container_width=True):
                st.session_state.visible_cols = new_visible if new_visible else DEFAULT_COLUMNS[:]
                st.rerun()
        with col_b2:
            if st.button("Reset columns", use_container_width=True):
                st.session_state.visible_cols = DEFAULT_COLUMNS[:]
                st.rerun()

if company_leads:
    _show_metrics(company_leads)
    st.markdown("<br>", unsafe_allow_html=True)

    tab_all, tab_high, tab_gaps, tab_mfg, tab_imp, tab_trade, tab_dir = st.tabs([
        f"All ({len(company_leads)})", "High priority", "Compliance gaps",
        "Manufacturers", "Importers", "Traders & distributors", "Directories",
    ])

    with tab_all:
        _show_results(company_leads, "all")

    with tab_high:
        high_leads = [x for x in company_leads if str(x.get("importance","")).lower() == "high"]
        _show_results(high_leads, "high")

    with tab_gaps:
        st.markdown(
            '<div class="warn-bar">These companies are missing BIS, GST, IEC or MCA registrations — '
            'strong prospects for compliance services.</div>',
            unsafe_allow_html=True)
        gap_leads = [x for x in company_leads
                     if isinstance(x.get("compliance_gaps"),list) and len(x["compliance_gaps"])>0]
        _show_results(gap_leads, "gaps")

    with tab_mfg:
        mfg_leads = [x for x in company_leads if x.get("channel_type") == "Manufacturer"]
        _show_results(mfg_leads, "mfg")

    with tab_imp:
        imp_leads = [x for x in company_leads if x.get("channel_type") == "Importer"]
        _show_results(imp_leads, "imp")

    with tab_trade:
        trade_leads = [x for x in company_leads
                       if x.get("channel_type") in ("Trader","Distributor","Wholesaler","Retailer")]
        _show_results(trade_leads, "trade")

    with tab_dir:
        dir_leads = [x for x in company_leads if x.get("is_directory")]

        with st.expander("Manually scan a directory URL", expanded=False):
            manual_url   = st.text_input("Directory URL",
                                         placeholder="https://www.indiamart.com/...",
                                         key="manual_dir_url")
            manual_query = st.text_input("What kind of companies are listed?",
                                         placeholder="electronics importers india",
                                         key="manual_dir_query")
            if st.button("Scan", key="manual_dir_btn", type="primary"):
                if manual_url:
                    with st.spinner("Scanning…"):
                        try:
                            r = _api_post("/leads/extract-directory",
                                json={"website": manual_url, "content": "",
                                      "query": manual_query or st.session_state.active_query},
                                timeout=90)
                            if r.status_code == 200:
                                st.session_state["manual_dir_result"] = r.json()
                            else:
                                st.error(f"Scan failed: {r.text}")
                        except Exception as e:
                            st.error(f"Cannot reach server: {e}")
            if st.session_state.get("manual_dir_result"):
                res = st.session_state["manual_dir_result"]
                st.success(f"Found {res.get('extracted',0)} companies, "
                           f"saved {res.get('saved',0)}")
                if res.get("companies"):
                    _show_extracted_companies(res["companies"], key_suffix="manual",
                                              query=manual_query or st.session_state.active_query)

        if not dir_leads:
            st.markdown("""
            <div class="warn-bar">
              No directory pages detected yet. Try searches like
              <em>electronics importers list india</em> or
              <em>manufacturers directory Gujarat</em>,
              or paste a URL in the scanner above.
            </div>""", unsafe_allow_html=True)
        else:
            _show_results(dir_leads, "dir")

    # LinkedIn contacts
    linkedin_leads = [x for x in raw_leads if x.get("source") == "linkedin_semantic"]
    if linkedin_leads:
        with st.expander(f"LinkedIn contacts ({len(linkedin_leads)})", expanded=False):
            ld   = pd.DataFrame(linkedin_leads)
            cols = ["name","profile","snippet","searched_query","created_at"]
            st.dataframe(ld[[c for c in cols if c in ld.columns]], use_container_width=True)

    # Compliance checker
    st.markdown("---")
    with st.expander("Check licences & registrations (BIS, GST, IEC, MCA)", expanded=False):
        st.markdown(
            "Check which companies are missing key Indian registrations. "
            "Companies with gaps are high-value prospects for compliance services.")
        n_check = st.slider("How many to check?", 5, 100, 20, key="enrich_n")
        cf_enrich = "" if st.session_state.sf_country == "Any Country" \
                    else st.session_state.sf_country.lower()
        if st.button("Start checking", key="enrich_btn", type="primary"):
            with st.spinner("Checking registrations… 1–2 minutes"):
                try:
                    r = _api_post("/leads/enrich-compliance",
                        params={"limit": n_check, "country_filter": cf_enrich},
                        timeout=300)
                    if r.status_code == 200:
                        st.success(f"Checked {r.json().get('checked',0)} companies. Refresh to see results.")
                    else:
                        st.error("Check failed.")
                except Exception as e:
                    st.error(str(e))

elif not st.session_state.active_job_id:
    st.markdown("""
    <div class="empty-state" style="margin-top:32px">
      <div class="ei">🌐</div>
      <h3>Ready to search</h3>
      <p>Type what you're looking for above — for example:<br>
         <em>electronics importers Gujarat</em> or <em>pharma manufacturers Mumbai</em></p>
    </div>
    """, unsafe_allow_html=True)
