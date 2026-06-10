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
    page_title="Buyera — Find Business Leads",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* { font-family: 'Inter', sans-serif; box-sizing: border-box; }

.stApp { background: #f8fafc; }

/* Hide default streamlit chrome */
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* Top nav bar */
.topbar {
    background: white;
    border-bottom: 1px solid #e2e8f0;
    padding: 14px 32px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: -1rem -1rem 0 -1rem;
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-logo {
    font-size: 1.3rem;
    font-weight: 700;
    color: #1e40af;
}
.topbar-logo span { color: #10b981; }
.topbar-user {
    font-size: 0.82rem;
    color: #64748b;
    background: #f1f5f9;
    padding: 6px 14px;
    border-radius: 20px;
}

/* Hero search area */
.search-hero {
    background: linear-gradient(135deg, #1e3a5f 0%, #1e40af 50%, #0f766e 100%);
    border-radius: 16px;
    padding: 40px 32px;
    margin: 20px 0 16px;
    text-align: center;
}
.search-hero h1 {
    color: white;
    font-size: 1.8rem;
    font-weight: 700;
    margin: 0 0 6px;
}
.search-hero p {
    color: rgba(255,255,255,0.75);
    font-size: 0.95rem;
    margin: 0 0 24px;
}

/* Example chips */
.chip-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    justify-content: center;
    margin-top: 12px;
}
.chip {
    background: rgba(255,255,255,0.15);
    color: rgba(255,255,255,0.9);
    border: 1px solid rgba(255,255,255,0.25);
    padding: 5px 14px;
    border-radius: 20px;
    font-size: 0.78rem;
    cursor: pointer;
}

/* Filter bar */
.filter-bar {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 16px;
}
.filter-label {
    font-size: 0.75rem;
    font-weight: 600;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-bottom: 6px;
}

/* Metric cards */
[data-testid="metric-container"] {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px !important;
    box-shadow: 0 1px 3px rgba(0,0,0,0.06);
}
[data-testid="stMetricValue"] {
    font-size: 1.9rem !important;
    font-weight: 700 !important;
    color: #1e293b !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.72rem !important;
    color: #94a3b8 !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}

/* Buttons */
.stButton > button {
    border-radius: 8px !important;
    font-weight: 600 !important;
    font-size: 0.85rem !important;
    padding: 8px 18px !important;
    transition: all 0.15s !important;
}
div[data-testid="stHorizontalBlock"] .stButton > button {
    width: 100%;
}

/* Primary search button */
.search-btn .stButton > button {
    background: #1e40af !important;
    color: white !important;
    border: none !important;
    font-size: 1rem !important;
    padding: 12px 32px !important;
    border-radius: 10px !important;
}
.search-btn .stButton > button:hover {
    background: #1d4ed8 !important;
    box-shadow: 0 4px 12px rgba(30,64,175,0.35) !important;
}

/* Tabs */
[data-testid="stTabs"] [role="tablist"] {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    padding: 4px;
    gap: 2px;
}
[data-testid="stTabs"] [role="tab"] {
    border-radius: 7px !important;
    color: #64748b !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 7px 14px !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    background: #1e40af !important;
    color: white !important;
}

/* Status pill */
.status-pill {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.03em;
}
.pill-high    { background: #dcfce7; color: #166534; }
.pill-medium  { background: #fef9c3; color: #854d0e; }
.pill-low     { background: #f1f5f9; color: #64748b; }
.pill-gap     { background: #fee2e2; color: #991b1b; }
.pill-clean   { background: #dcfce7; color: #166534; }
.pill-running { background: #dbeafe; color: #1e40af; }

/* Result card */
.result-card {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 18px 20px;
    margin-bottom: 10px;
    transition: box-shadow 0.15s, border-color 0.15s;
}
.result-card:hover {
    box-shadow: 0 4px 16px rgba(0,0,0,0.08);
    border-color: #93c5fd;
}
.card-company { font-size: 1rem; font-weight: 700; color: #1e293b; }
.card-meta    { font-size: 0.78rem; color: #64748b; margin: 4px 0 8px; }
.card-summary { font-size: 0.82rem; color: #475569; line-height: 1.5; margin: 6px 0; }
.card-tags    { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
.card-tag {
    background: #f1f5f9;
    color: #475569;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.72rem;
    font-weight: 500;
}
.card-links   { margin-top: 10px; display: flex; gap: 14px; }
.card-link    { font-size: 0.78rem; color: #1e40af; text-decoration: none; }

/* Score badge */
.score-badge {
    background: #eff6ff;
    color: #1e40af;
    border: 1px solid #bfdbfe;
    padding: 3px 10px;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 700;
}

/* Column picker */
.col-picker-wrap {
    background: white;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 16px;
}

/* Input override */
.stTextInput input {
    border-radius: 10px !important;
    border: 1.5px solid #e2e8f0 !important;
    font-size: 1rem !important;
    padding: 12px 16px !important;
    background: white !important;
}
.stTextInput input:focus {
    border-color: #1e40af !important;
    box-shadow: 0 0 0 3px rgba(30,64,175,0.1) !important;
}

/* Selectbox */
.stSelectbox > div > div {
    border-radius: 8px !important;
    border: 1.5px solid #e2e8f0 !important;
    background: white !important;
    font-size: 0.85rem !important;
}

/* Checkbox */
.stCheckbox { font-size: 0.85rem !important; color: #475569 !important; }

/* Expander */
[data-testid="stExpander"] {
    background: white;
    border: 1px solid #e2e8f0 !important;
    border-radius: 12px !important;
}

/* Dataframe */
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; }

/* Alert */
.stAlert { border-radius: 10px !important; }

/* Divider */
hr { border-color: #e2e8f0 !important; margin: 12px 0 !important; }

/* Progress */
.stProgress > div > div { background: #1e40af !important; border-radius: 4px; }

/* Info box */
.info-box {
    background: #eff6ff;
    border: 1px solid #bfdbfe;
    border-radius: 10px;
    padding: 12px 16px;
    font-size: 0.83rem;
    color: #1e40af;
    margin-bottom: 12px;
}

/* Empty state */
.empty-state {
    text-align: center;
    padding: 64px 20px;
    color: #94a3b8;
}
.empty-state .icon { font-size: 3.5rem; margin-bottom: 12px; }
.empty-state h3 { color: #64748b; font-size: 1.1rem; margin: 0 0 6px; }
.empty-state p  { font-size: 0.85rem; margin: 0; }

/* All input/widget labels black */
label, .stSelectbox label, .stTextInput label,
.stCheckbox label, .stSlider label, .stRadio label,
.stMultiSelect label, .stTextArea label,
[data-testid="stWidgetLabel"] p,
[data-testid="stWidgetLabel"],
.stSlider [data-testid="stWidgetLabel"],
.stCheckbox [data-testid="stWidgetLabel"],
.stRadio [data-testid="stWidgetLabel"],
.element-container label {
    color: #111827 !important;
    font-weight: 600 !important;
}

/* Expander header text black */
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] summary {
    color: #111827 !important;
    font-weight: 600 !important;
}

/* Tab labels */
[data-testid="stTabs"] [role="tab"] {
    color: #111827 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: white !important;
}

/* Radio options */
.stRadio div[role="radiogroup"] label {
    color: #111827 !important;
    font-weight: 500 !important;
}

/* Slider label */
.stSlider > label {
    color: #111827 !important;
    font-weight: 600 !important;
}

/* Section headers inside expanders */
.stMarkdown p, .stMarkdown strong {
    color: #111827 !important;
}


/* =====================================================
   GLOBAL TEXT COLOR FIXES — all text black on white
   ===================================================== */

/* Body and app background */
.stApp, .stApp * {
    color: #111827;
}

/* Input text — typing color */
.stTextInput input,
.stTextInput input::placeholder,
input[type="text"],
input[type="password"],
textarea {
    color: #111827 !important;
    background: white !important;
    -webkit-text-fill-color: #111827 !important;
}
.stTextInput input::placeholder {
    color: #9ca3af !important;
    -webkit-text-fill-color: #9ca3af !important;
}

/* Selectbox text */
.stSelectbox div[data-baseweb="select"] span,
.stSelectbox div[data-baseweb="select"] div,
.stSelectbox [data-testid="stMarkdownContainer"] p,
div[data-baseweb="select"] > div {
    color: #111827 !important;
    background-color: white !important;
}

/* Selectbox dropdown options */
ul[role="listbox"] li,
ul[role="listbox"] li span,
div[role="option"],
div[role="option"] span {
    color: #111827 !important;
    background: white !important;
}
ul[role="listbox"] li:hover,
div[role="option"]:hover {
    background: #eff6ff !important;
    color: #1e40af !important;
}

/* All labels — every widget */
label, p, span, div,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
.stMarkdown p,
.stMarkdown span,
.stCheckbox label span,
.stRadio label span,
[data-baseweb="checkbox"] span,
[data-baseweb="radio"] span {
    color: #111827 !important;
}

/* Metric cards — keep numbers dark */
[data-testid="stMetricValue"] {
    color: #111827 !important;
}
[data-testid="stMetricLabel"] {
    color: #6b7280 !important;
}

/* Caption / small text */
.stCaption, [data-testid="stCaptionContainer"] p {
    color: #6b7280 !important;
}

/* Tab text */
[data-testid="stTabs"] [role="tab"] {
    color: #374151 !important;
    font-weight: 600 !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: white !important;
    background: #1e40af !important;
}

/* Expander header */
[data-testid="stExpander"] details summary p,
[data-testid="stExpander"] summary p {
    color: #111827 !important;
    font-weight: 600 !important;
}

/* Slider labels and values */
.stSlider label,
.stSlider [data-testid="stWidgetLabel"] p,
.stSlider div[data-testid="stTickBarMin"],
.stSlider div[data-testid="stTickBarMax"],
[data-testid="stTickBar"] span {
    color: #111827 !important;
}

/* Radio button labels */
.stRadio > div label p,
.stRadio > div [data-testid="stMarkdownContainer"] p {
    color: #111827 !important;
    font-weight: 500 !important;
}

/* Checkbox labels */
.stCheckbox > label > div p,
.stCheckbox [data-testid="stMarkdownContainer"] p {
    color: #111827 !important;
}

/* Info/success/warning/error boxes */
[data-testid="stAlert"] p,
[data-testid="stAlert"] div {
    color: #111827 !important;
}

/* Download button text */
.stDownloadButton button {
    color: #111827 !important;
    background: white !important;
    border: 1.5px solid #e2e8f0 !important;
}
.stDownloadButton button:hover {
    background: #f8fafc !important;
    border-color: #1e40af !important;
}

/* Override the blue highlight issue from screenshot 1 */
::selection {
    background: #bfdbfe;
    color: #1e40af;
}

/* Sidebar and main area text */
[data-testid="stSidebar"] * { color: #111827 !important; }

/* Dataframe text */
[data-testid="stDataFrame"] table,
[data-testid="stDataFrame"] th,
[data-testid="stDataFrame"] td {
    color: #111827 !important;
}

/* Toast notifications */
[data-testid="stToast"] p { color: #111827 !important; }

/* Buttons keep white text */
.stButton > button {
    color: white !important;
}
.stButton > button:hover {
    color: white !important;
}


/* =====================================================
   DROPDOWN + BUTTON FIXES
   ===================================================== */

/* Selectbox trigger box — white background, black text */
div[data-baseweb="select"],
div[data-baseweb="select"] > div,
div[data-baseweb="select"] > div > div,
.stSelectbox div[data-baseweb="select"],
[data-testid="stSelectbox"] div[data-baseweb="select"] > div {
    background-color: white !important;
    color: #111827 !important;
    border-color: #e2e8f0 !important;
}

/* Selectbox selected value text */
div[data-baseweb="select"] span,
div[data-baseweb="select"] [class*="placeholder"],
div[data-baseweb="select"] [class*="singleValue"],
div[data-baseweb="select"] input {
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    background: transparent !important;
}

/* Dropdown popup menu — white background */
ul[role="listbox"],
div[role="listbox"],
[data-baseweb="popover"],
[data-baseweb="menu"],
[data-baseweb="popover"] > div,
[data-baseweb="menu"] > div,
[data-baseweb="menu"] ul {
    background-color: white !important;
    border: 1px solid #e2e8f0 !important;
    border-radius: 10px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.12) !important;
}

/* Dropdown individual options */
ul[role="listbox"] li,
[data-baseweb="menu"] li,
[role="option"],
div[role="option"],
li[role="option"] {
    background-color: white !important;
    color: #111827 !important;
}
ul[role="listbox"] li *,
[role="option"] *,
div[role="option"] *,
li[role="option"] * {
    color: #111827 !important;
    background-color: transparent !important;
}

/* Dropdown option hover */
ul[role="listbox"] li:hover,
[role="option"]:hover,
div[role="option"]:hover,
li[role="option"]:hover,
[aria-selected="true"][role="option"],
[data-baseweb="menu"] li:hover {
    background-color: #eff6ff !important;
    color: #1e40af !important;
}
ul[role="listbox"] li:hover *,
[role="option"]:hover *,
div[role="option"]:hover * {
    color: #1e40af !important;
}

/* =====================================================
   BUTTON FIXES — white background, dark text
   (for non-primary action buttons)
   ===================================================== */

/* Default (secondary) buttons — white bg, black text */
.stButton > button[kind="secondary"],
.stButton > button:not([kind="primary"]) {
    background: white !important;
    color: #111827 !important;
    border: 1.5px solid #d1d5db !important;
}
.stButton > button[kind="secondary"]:hover,
.stButton > button:not([kind="primary"]):hover {
    background: #f8fafc !important;
    color: #111827 !important;
    border-color: #1e40af !important;
}

/* Primary buttons stay blue with white text */
.stButton > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"] {
    background: #1e40af !important;
    color: white !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1d4ed8 !important;
    color: white !important;
}

/* Search button specifically */
.search-btn .stButton > button {
    background: #1e40af !important;
    color: white !important;
    border: none !important;
}

/* Refresh / logout / clear / small action buttons — white bg dark text */
button[data-testid="baseButton-secondary"],
.stButton > button[data-testid="baseButton-secondary"] {
    background: white !important;
    color: #111827 !important;
    border: 1.5px solid #d1d5db !important;
}

/* Logout button */
div[data-testid="stButton"]:has(button#logout_btn) button,
#logout_btn {
    background: white !important;
    color: #374151 !important;
    border: 1.5px solid #d1d5db !important;
}

/* Download button */
.stDownloadButton > button {
    background: white !important;
    color: #111827 !important;
    border: 1.5px solid #d1d5db !important;
    font-weight: 500 !important;
}
.stDownloadButton > button:hover {
    background: #f8fafc !important;
    border-color: #1e40af !important;
    color: #1e40af !important;
}

/* Compliance check button — keep primary style */
button[key="enrich_btn"],
div[data-testid="stButton"]:has(button[key="enrich_btn"]) button {
    background: #1e40af !important;
    color: white !important;
}

/* Tab selected stays white text */
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: white !important;
    background: #1e40af !important;
}

/* Multiselect tags */
[data-baseweb="tag"] {
    background: #eff6ff !important;
    color: #1e40af !important;
}
[data-baseweb="tag"] span { color: #1e40af !important; }

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
    <div style="max-width:440px;margin:80px auto 0;padding:0 16px">
      <div style="text-align:center;margin-bottom:32px">
        <div style="font-size:2.4rem;font-weight:800;color:#1e40af;margin-bottom:6px">
          🌐 Buyera
        </div>
        <p style="color:#64748b;font-size:0.95rem;margin:0">
          Find business leads from around the world — fast.
        </p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_login, tab_reg = st.tabs(["Sign In", "Create Account"])

        with tab_login:
            with st.form("lf"):
                uname = st.text_input("Username")
                pwd   = st.text_input("Password", type="password")
                sub   = st.form_submit_button("Sign In", use_container_width=True)
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
                            st.error(d.get("detail", "Sign in failed. Check your details."))
                    except Exception as e:
                        st.error(f"Can't connect to server: {e}")

        with tab_reg:
            with st.form("rf"):
                nu  = st.text_input("Choose a username")
                ne  = st.text_input("Email (optional)")
                np  = st.text_input("Choose a password", type="password")
                np2 = st.text_input("Confirm password", type="password")
                sub2 = st.form_submit_button("Create Account", use_container_width=True)
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
                            st.error(r.json().get("detail", "Registration failed."))
                    except Exception as e:
                        st.error(f"Can't connect to server: {e}")

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

# ---------------------------------------------------------------------------
# Column definitions — human-friendly names
# ---------------------------------------------------------------------------
ALL_COLUMNS = {
    "company":            "Company Name",
    "city":               "City",
    "country_detected":   "Country",
    "industry_detected":  "Industry",
    "product_type":       "Products / Services",
    "channel_type":       "Business Type",
    "company_size":       "Company Size",
    "incorporation_date": "Year Founded",
    "importance":         "Priority",
    "final_score":        "Match Score",
    "compliance_gaps":    "Compliance Issues",
    "bis_certified":      "BIS Certified",
    "gst_registered":     "GST Registered",
    "iec_found":          "IEC Code",
    "mca_active":         "MCA Status",
    "contact_person":     "Contact Name",
    "contact_email":      "Contact Email",
    "email":              "Email Address",
    "phone":              "Phone Number",
    "linkedin_url":       "LinkedIn",
    "active_website":     "Website",
    "ai_summary":         "About the Company",
    "products":           "Product List",
    "mca_company_type":   "Company Category",
    "domain_authority":   "Website Authority",
    "searched_query":     "Search Query Used",
    "created_at":         "Date Found",
    "annual_turnover":    "Annual Turnover / Revenue",
    "certifications":     "Certifications (ISO, BIS etc)",
    "export_markets":     "Export Markets",
    "usp":                "Unique Selling Point",
    "key_customers":      "Key Customers / Clients",
    "llm_score":          "AI Relevance Score",
    "grok_score":         "Grok Validation Score",
    "contact_title":      "Contact Job Title",
    "contact_confidence": "Contact Confidence",
    "is_valid_lead":      "Valid Lead (Grok)",
    "rejection_reason":   "Rejection Reason",
    "twitter_url":        "X (Twitter)",
    "facebook_url":       "Facebook",
    "instagram_url":      "Instagram",
    "youtube_url":        "YouTube",
    "whatsapp_url":       "WhatsApp",
    "is_directory":       "Is Directory Page",
    "directory_count":    "Companies in Directory",
}

DEFAULT_COLUMNS = [
    "company", "city", "country_detected", "industry_detected",
    "channel_type", "importance", "final_score", "compliance_gaps",
    "email", "phone", "active_website", "ai_summary",
]

# ---------------------------------------------------------------------------
# Session state
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "active_job_id":      "",
    "active_query":       "",
    "live_results":       [],
    "live_cursor":        0,
    "notified_jobs":      [],
    "sf_query":           "",
    "sf_country":         "Any Country",
    "sf_state":           "Any",
    "sf_industry":        "Any",
    "sf_channel":         "Any",
    "sf_importance":      "Any",
    "sf_min_score":       0.0,
    "sf_sort":            "Best Match First",
    "sf_has_email":       False,
    "sf_has_phone":       False,
    "sf_gaps_only":       False,
    "visible_cols":       DEFAULT_COLUMNS[:],
    "view_mode":          "Cards",
    "scan_all":           False,
    "quality_threshold":  0,
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, list) else v[:]

# ---------------------------------------------------------------------------
# Top nav bar
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="topbar">
  <div class="topbar-logo">🌐 Bue<span>ra</span></div>
  <div class="topbar-user">👤 {st.session_state.auth_username}</div>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Logout (small, top right via button)
# ---------------------------------------------------------------------------
lcol = st.columns([8, 1])[1]
with lcol:
    if st.button("Logout", key="logout_btn"):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

# ===========================================================================
# SESSION RESTORE — reload last active job after browser refresh / session reset
# ===========================================================================
if st.session_state.auth_token and not st.session_state.active_job_id:
    try:
        rj = _api_get("/jobs/recent", timeout=10)
        if rj.status_code == 200:
            recent = rj.json()
            # Find the most recent completed or running job
            for job in recent[:5]:
                if job.get("status") in ("completed", "running", "queued"):
                    st.session_state.active_job_id = job.get("job_id", "")
                    st.session_state.active_query  = job.get("query", "")
                    break
    except Exception:
        pass

# ===========================================================================
# HERO SEARCH SECTION
# ===========================================================================
st.markdown("""
<div class="search-hero">
  <h1>Find Your Next Business Customer</h1>
  <p>Search for companies, importers, manufacturers, distributors — anywhere in the world</p>
</div>
""", unsafe_allow_html=True)

# Search bar row
sc1, sc2, sc3 = st.columns([5, 1, 1])
with sc1:
    query = st.text_input(
        "search_input",
        value=st.session_state.sf_query,
        placeholder='Try: "LED light importers Gujarat" or "pharma distributors Mumbai"',
        label_visibility="collapsed",
        key="search_input_box",
    )
    # Keep sf_query in sync without assigning directly to widget key
    st.session_state.sf_query = query
with sc2:
    st.markdown('<div class="search-btn">', unsafe_allow_html=True)
    search_clicked = st.button("🔍 Search", use_container_width=True, key="main_search_btn")
    st.markdown('</div>', unsafe_allow_html=True)
with sc3:
    refresh_clicked = st.button("↺ Refresh", use_container_width=True, key="refresh_btn")
    if refresh_clicked:
        st.rerun()

# Example queries
st.markdown("""
<div class="chip-row" style="justify-content:flex-start;margin:8px 0 4px">
  <span style="font-size:0.78rem;color:#94a3b8;margin-right:4px">Try:</span>
  <span class="chip" style="background:#eff6ff;color:#1e40af;border-color:#bfdbfe">
    Electronics importers Delhi
  </span>
  <span class="chip" style="background:#f0fdf4;color:#166534;border-color:#bbf7d0">
    Textile manufacturers Surat
  </span>
  <span class="chip" style="background:#fdf4ff;color:#7e22ce;border-color:#e9d5ff">
    Pharma distributors Mumbai
  </span>
  <span class="chip" style="background:#fff7ed;color:#9a3412;border-color:#fed7aa">
    Steel traders UAE
  </span>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Build and trigger search
# ---------------------------------------------------------------------------
def _build_final_query() -> str:
    parts = [st.session_state.sf_query.strip()]
    ind = st.session_state.sf_industry
    if ind and ind != "Any":
        if ind.lower() not in st.session_state.sf_query.lower():
            parts.append(ind)
    st8 = st.session_state.sf_state
    if st8 and st8 != "Any":
        if st8.lower() not in st.session_state.sf_query.lower():
            parts.append(st8)
    ctr = st.session_state.sf_country
    if ctr and ctr != "Any Country":
        if ctr.lower() not in st.session_state.sf_query.lower():
            parts.append(ctr)
    return " ".join(p for p in parts if p).strip()

if search_clicked:
    fq = _build_final_query()
    if not fq:
        st.warning("Please type something to search for.")
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
            }, timeout=30)
            if r.status_code == 200:
                d = r.json()
                st.session_state.active_job_id = d.get("job_id", "")
                st.session_state.active_query  = fq
                st.session_state.live_results  = []
                st.session_state.live_cursor   = 0
                st.rerun()
            else:
                st.error(f"Search error: {r.text}")
        except Exception as e:
            st.error(f"Cannot reach server: {e}")

# ===========================================================================
# FILTER BAR  (shown only when there are results)
# ===========================================================================
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

raw_leads = _get_all_leads()
company_leads = [x for x in raw_leads if x.get("source") != "linkedin_semantic"]

if company_leads or st.session_state.active_job_id:
    st.markdown("---")

    # -----------------------------------------------------------------------
    # FILTER SECTION
    # -----------------------------------------------------------------------
    with st.expander("🎛️  Filters & Options", expanded=False):
        st.markdown("**Narrow down your results**")
        f1, f2, f3, f4 = st.columns(4)

        with f1:
            sel_country = st.selectbox("Country", ALL_COUNTRIES,
                index=ALL_COUNTRIES.index(st.session_state.sf_country)
                      if st.session_state.sf_country in ALL_COUNTRIES else 0,
                key="sf_country")
            state_opts = (["Any"] + COUNTRY_STATES.get(sel_country, [])
                          if sel_country != "Any Country" else ["Any"])
            if st.session_state.sf_state not in state_opts:
                st.session_state.sf_state = "Any"
            sel_state = st.selectbox("State / Region", state_opts,
                index=state_opts.index(st.session_state.sf_state)
                      if st.session_state.sf_state in state_opts else 0,
                key="sf_state",
                disabled=(sel_country == "Any Country"))

        with f2:
            sel_industry = st.selectbox("Industry",
                ["Any"] + ALL_INDUSTRIES,
                index=(["Any"] + ALL_INDUSTRIES).index(st.session_state.sf_industry)
                      if st.session_state.sf_industry in ["Any"] + ALL_INDUSTRIES else 0,
                key="sf_industry")
            sel_channel = st.selectbox("Business Type",
                ["Any"] + CHANNEL_TYPES,
                index=(["Any"] + CHANNEL_TYPES).index(st.session_state.sf_channel)
                      if st.session_state.sf_channel in ["Any"] + CHANNEL_TYPES else 0,
                key="sf_channel")

        with f3:
            sel_importance = st.selectbox("Priority Level",
                ["Any", "High ⭐", "Medium", "Low"],
                index=0, key="sf_importance")
            min_score = st.slider("Minimum Match Score",
                0.0, 1.0, st.session_state.sf_min_score, 0.05,
                key="sf_min_score",
                help="0 = show everything, 1 = only perfect matches")

        with f4:
            sort_by = st.selectbox("Sort Results By", [
                "Best Match First",
                "Priority (High → Low)",
                "Company Name A → Z",
                "Company Name Z → A",
                "Newest First",
            ], key="sf_sort")
            st.markdown("**Quick filters**")
            has_email = st.checkbox("Has email address", key="sf_has_email")
            has_phone = st.checkbox("Has phone number",  key="sf_has_phone")
            gaps_only = st.checkbox("Show compliance issues only", key="sf_gaps_only")

        ca, cb, cc = st.columns(3)
        with ca:
            st.checkbox("Search all pages (slower)", key="scan_all")
        with cb:
            if st.button("❌ Clear All Filters", use_container_width=True):
                for k in ["sf_country","sf_state","sf_industry","sf_channel",
                          "sf_importance","sf_min_score","sf_has_email",
                          "sf_has_phone","sf_gaps_only"]:
                    st.session_state[k] = _DEFAULTS[k]
                st.rerun()
        with cc:
            if st.button("🗑️ Delete All Leads", use_container_width=True):
                try:
                    _api_delete("/clear", timeout=15)
                    for k, v in _DEFAULTS.items():
                        st.session_state[k] = v if not isinstance(v, list) else v[:]
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # -----------------------------------------------------------------------
    # COLUMN PICKER
    # -----------------------------------------------------------------------
    with st.expander("📋  Choose Which Columns to Show", expanded=False):
        st.markdown("**Pick exactly what information you want to see in the table**")

        # Group columns for easier understanding
        col_groups = {
            "🏢 Company Info": ["company","city","country_detected","industry_detected",
                                "product_type","channel_type","company_size","incorporation_date"],
            "📊 Scores & Priority": ["importance","final_score","domain_authority"],
            "✅ Compliance": ["compliance_gaps","bis_certified","gst_registered",
                              "iec_found","mca_active","mca_company_type"],
            "📞 Contact Details": ["contact_person","contact_email","email","phone","linkedin_url"],
            "🌐 Online Presence": ["active_website"],
            "🤖 AI Analysis": ["ai_summary","products","usp","key_customers"],
            "💰 Business Details": ["annual_turnover","certifications","export_markets","grok_score"],
            "📱 Social Media": ["linkedin_url","twitter_url","facebook_url","instagram_url","youtube_url","whatsapp_url"],
            "🔍 Lead Validation": ["is_valid_lead","rejection_reason","contact_title","contact_confidence","is_directory","directory_count"],
            "🔍 Search Info": ["searched_query","created_at"],
        }

        new_visible = []
        seen_keys = set()
        for group_name, group_cols in col_groups.items():
            st.markdown(f"**{group_name}**")
            gcols = st.columns(4)
            # make a safe group prefix from the group name
            grp_prefix = re.sub(r"[^a-z0-9]", "_", group_name.lower())[:12]
            for i, col_key in enumerate(group_cols):
                widget_key = f"col_{grp_prefix}_{col_key}"
                if widget_key in seen_keys:
                    widget_key = f"col_{grp_prefix}_{col_key}_{i}"
                seen_keys.add(widget_key)
                with gcols[i % 4]:
                    checked = st.checkbox(
                        ALL_COLUMNS.get(col_key, col_key),
                        value=(col_key in st.session_state.visible_cols),
                        key=widget_key,
                    )
                    if checked and col_key not in new_visible:
                        new_visible.append(col_key)

        col_btn1, col_btn2 = st.columns(2)
        with col_btn1:
            if st.button("✅ Apply Column Selection", use_container_width=True):
                st.session_state.visible_cols = new_visible if new_visible else DEFAULT_COLUMNS[:]
                st.rerun()
        with col_btn2:
            if st.button("↺ Reset to Default Columns", use_container_width=True):
                st.session_state.visible_cols = DEFAULT_COLUMNS[:]
                st.rerun()

# ===========================================================================
# LIVE SEARCH STATUS
# ===========================================================================
if st.session_state.active_job_id:
    status = None
    try:
        sr = _api_get(f"/search/status/{st.session_state.active_job_id}", timeout=20)
        if sr.status_code == 200:
            status = sr.json()
    except Exception as e:
        st.error(f"Cannot reach server: {e}")

    if status:
        sv = status.get("status", "")
        saved = status.get("saved_total", 0)
        pages = status.get("pages_scanned", 0)

        if sv in ("running", "queued"):
            st.markdown(f"""
            <div class="info-box">
              ⏳ <strong>Searching…</strong> — Found {saved} companies so far
              · Page {pages} scanned · Auto-refreshing every {POLL_SECONDS}s
            </div>
            """, unsafe_allow_html=True)
            time.sleep(POLL_SECONDS)
            st.rerun()

        elif sv == "completed":
            jid = status.get("job_id", "")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast(f"✅ Search done — {saved} companies found!")
                st.session_state.notified_jobs.append(jid)
            if status.get("ask_continue"):
                c1, c2 = st.columns(2)
                with c1:
                    st.info(f"Found {saved} companies. Want to search more pages?")
                with c2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("▶️ Yes, find more", use_container_width=True):
                            cf = "" if st.session_state.sf_country == "Any Country" \
                                 else st.session_state.sf_country.lower()
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
                        if st.button("⏹️ No thanks", use_container_width=True):
                            st.session_state.active_job_id = ""
                            st.rerun()
            else:
                st.success(f"✅ Search complete — {saved} companies found. Use filters to narrow down.")
                st.session_state.active_job_id = ""

        elif sv == "failed":
            st.error(f"Search failed: {status.get('error', 'Unknown error')}")
            st.session_state.active_job_id = ""

# ===========================================================================
# APPLY FILTERS TO LEADS
# ===========================================================================
def _apply_filters(leads: list) -> list:
    df = pd.DataFrame(leads) if leads else pd.DataFrame()
    if df.empty:
        return []

    if st.session_state.sf_channel != "Any" and "channel_type" in df.columns:
        df = df[df["channel_type"].astype(str) == st.session_state.sf_channel]

    imp_map = {"High ⭐": "high", "Medium": "medium", "Low": "low"}
    imp_val = imp_map.get(st.session_state.sf_importance)
    if imp_val and "importance" in df.columns:
        df = df[df["importance"].astype(str).str.lower() == imp_val]

    if st.session_state.sf_min_score > 0 and "final_score" in df.columns:
        df = df[pd.to_numeric(df["final_score"], errors="coerce").fillna(0)
                >= st.session_state.sf_min_score]

    if st.session_state.sf_has_email and "email" in df.columns:
        df = df[df["email"].astype(str).str.contains("@", na=False)]

    if st.session_state.sf_has_phone and "phone" in df.columns:
        df = df[df["phone"].astype(str).str.strip().ne("").ne("nan")]

    if st.session_state.sf_gaps_only and "compliance_gaps" in df.columns:
        df = df[df["compliance_gaps"].apply(
            lambda g: isinstance(g, list) and len(g) > 0)]

    if st.session_state.sf_industry != "Any" and "industry_detected" in df.columns:
        df = df[df["industry_detected"].astype(str).str.lower()
                .str.contains(st.session_state.sf_industry.lower(), na=False)]

    # Sort
    sort = st.session_state.sf_sort
    if "final_score" in df.columns:
        scores = pd.to_numeric(df["final_score"], errors="coerce").fillna(0)
        if sort == "Best Match First":
            df = df.iloc[scores.argsort()[::-1]]
        elif sort == "Priority (High → Low)":
            order = {"high": 0, "medium": 1, "low": 2}
            df = df.iloc[df["importance"].astype(str).str.lower()
                         .map(order).fillna(3).argsort()]
    if sort == "Company Name A → Z" and "company" in df.columns:
        df = df.sort_values("company")
    elif sort == "Company Name Z → A" and "company" in df.columns:
        df = df.sort_values("company", ascending=False)
    elif sort == "Newest First" and "created_at" in df.columns:
        df = df.sort_values("created_at", ascending=False)

    return df.reset_index(drop=True).to_dict("records")

# ===========================================================================
# DISPLAY HELPERS
# ===========================================================================
def _bool_icon(val):
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"

def _importance_pill(imp):
    imp = str(imp).lower()
    if imp == "high":   return '<span class="status-pill pill-high">⭐ High</span>'
    if imp == "medium": return '<span class="status-pill pill-medium">Medium</span>'
    return '<span class="status-pill pill-low">Low</span>'

def _gap_pill(gaps):
    if not isinstance(gaps, list) or not gaps:
        return '<span class="status-pill pill-clean">✓ No Issues</span>'
    labels = [GAP_LABELS.get(g, g) for g in gaps]
    return f'<span class="status-pill pill-gap">⚠ {", ".join(labels)}</span>'

def _show_metrics(leads: list):
    if not leads:
        return
    df = pd.DataFrame(leads)
    total  = len(df)
    high   = int((df.get("importance", pd.Series(dtype=str)).astype(str).str.lower() == "high").sum()) \
             if "importance" in df.columns else 0
    w_email= int(df["email"].astype(str).str.contains("@", na=False).sum()) \
             if "email" in df.columns else 0
    w_gap  = int(df["compliance_gaps"].apply(
                 lambda g: isinstance(g, list) and len(g) > 0).sum()) \
             if "compliance_gaps" in df.columns else 0
    mfg    = int((df.get("channel_type", pd.Series(dtype=str)).astype(str) == "Manufacturer").sum()) \
             if "channel_type" in df.columns else 0

    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Companies Found", total)
    m2.metric("⭐ High Priority",  high)
    m3.metric("📧 Have Email",     w_email)
    m4.metric("⚠️ Compliance Issues", w_gap)
    m5.metric("🏭 Manufacturers",  mfg)


def _show_cards(leads: list):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="icon">🔍</div>
          <h3>No results for these filters</h3>
          <p>Try removing some filters or searching with different keywords.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    for row in leads:
        company = str(row.get("company", "Unknown Company"))
        city    = str(row.get("city", ""))
        country = str(row.get("country_detected", ""))
        industry= str(row.get("industry_detected", ""))
        channel = str(row.get("channel_type", ""))
        score   = float(row.get("final_score", 0) or 0)
        imp     = str(row.get("importance", "low"))
        gaps    = row.get("compliance_gaps", [])
        email   = str(row.get("email", ""))
        phone   = str(row.get("phone", ""))
        website = str(row.get("active_website", row.get("website", "")))
        linkedin= str(row.get("linkedin_url", ""))
        summary = str(row.get("ai_summary", ""))[:200]
        products= row.get("products", [])
        size    = str(row.get("company_size", ""))
        founded = str(row.get("incorporation_date", ""))

        location = ", ".join(filter(None, [city, country]))
        tags     = [t for t in [industry, channel, size,
                                 f"Est. {founded}" if founded else ""]
                    if t and t != "nan"]
        prod_str = ""
        if isinstance(products, list) and products:
            prod_str = ", ".join(str(p) for p in products[:4])

        turnover  = str(row.get("annual_turnover", ""))
        certs     = row.get("certifications", [])
        exports   = row.get("export_markets", [])
        usp       = str(row.get("usp", ""))[:120]
        key_cust  = row.get("key_customers", [])

        twitter   = str(row.get("twitter_url",   ""))
        facebook  = str(row.get("facebook_url",  ""))
        instagram = str(row.get("instagram_url", ""))
        youtube   = str(row.get("youtube_url",   ""))
        whatsapp  = str(row.get("whatsapp_url",  ""))
        ctitle    = str(row.get("contact_title",    ""))
        cconfidence = str(row.get("contact_confidence",""))
        is_dir    = bool(row.get("is_directory", False))
        dir_count = int(row.get("directory_count", 0) or 0)
        is_valid  = bool(row.get("is_valid_lead", True))
        rejection = str(row.get("rejection_reason",""))

        links_html = ""
        if website and website not in ("nan", ""):
            links_html += f'<a class="card-link" href="{website}" target="_blank">🌐 Website</a>'
        if email and "@" in email:
            links_html += f'<a class="card-link" href="mailto:{email}">📧 {email}</a>'
        if phone and phone not in ("nan",""):
            links_html += f'<span class="card-link">📞 {phone}</span>'
        if linkedin and linkedin not in ("nan",""):
            links_html += f'<a class="card-link" href="{linkedin}" target="_blank">💼 LinkedIn</a>'
        if twitter and twitter not in ("nan",""):
            links_html += f'<a class="card-link" href="{twitter}" target="_blank">🐦 X/Twitter</a>'
        if facebook and facebook not in ("nan",""):
            links_html += f'<a class="card-link" href="{facebook}" target="_blank">📘 Facebook</a>'
        if instagram and instagram not in ("nan",""):
            links_html += f'<a class="card-link" href="{instagram}" target="_blank">📸 Instagram</a>'
        if youtube and youtube not in ("nan",""):
            links_html += f'<a class="card-link" href="{youtube}" target="_blank">▶️ YouTube</a>'
        if whatsapp and whatsapp not in ("nan",""):
            links_html += f'<a class="card-link" href="{whatsapp}" target="_blank">💬 WhatsApp</a>' 

        extra_html = ""
        if turnover and turnover not in ("nan",""):
            extra_html += f'<span class="card-tag" style="background:#f0fdf4;color:#166534">💰 {turnover}</span>'
        if isinstance(certs, list) and certs:
            extra_html += f'<span class="card-tag" style="background:#eff6ff;color:#1e40af">✅ {", ".join(certs[:3])}</span>'
        if isinstance(exports, list) and exports:
            extra_html += f'<span class="card-tag" style="background:#fdf4ff;color:#7e22ce">🌍 Exports: {", ".join(exports[:3])}</span>'
        if isinstance(key_cust, list) and key_cust:
            extra_html += f'<span class="card-tag" style="background:#fff7ed;color:#9a3412">👥 {", ".join(key_cust[:2])}</span>' 

        tags_html = "".join(f'<span class="card-tag">{t}</span>' for t in tags)

        st.markdown(f"""
        <div class="result-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
            <div style="flex:1;min-width:0">
              <div class="card-company">{company}</div>
              <div class="card-meta">{'📍 ' + location if location else ''}</div>
            </div>
            <div style="display:flex;gap:6px;flex-shrink:0;align-items:center;flex-wrap:wrap;justify-content:flex-end">
              {_importance_pill(imp)}
              {_gap_pill(gaps)}
              <span class="score-badge">{score:.2f}</span>
            </div>
          </div>
          {'<div class="card-tags">'+tags_html+'</div>' if tags_html else ''}
          {'<div class="card-summary">'+summary+'</div>' if summary and summary != "nan" else ''}
          {'<div class="card-summary" style="color:#1e40af;font-size:0.78rem">📦 '+prod_str+'</div>' if prod_str else ''}
          {'<div class="card-summary" style="color:#6b7280;font-size:0.78rem;font-style:italic">💡 '+usp+'</div>' if usp and usp != "nan" else ''}
          {'<div style="font-size:0.75rem;color:#374151;margin:4px 0"><strong>👤 Contact:</strong> '+company.get("contact_person","")+(" — "+ctitle if ctitle and ctitle!="nan" else "")+(" <span style=\'color:#10b981\'>("+cconfidence+" confidence)</span>" if cconfidence not in ("","nan","low") else "")+"</div>" if row.get("contact_person") else ''}
          {'<div style="font-size:0.73rem;background:#fef9c3;color:#854d0e;padding:4px 10px;border-radius:6px;margin:4px 0;">📂 Directory — contains <strong>'+str(dir_count)+' companies</strong>. Use the Extract button below.</div>' if is_dir and dir_count > 0 else ''}
          {'<div style="font-size:0.73rem;background:#fee2e2;color:#991b1b;padding:4px 10px;border-radius:6px;margin:4px 0;">⚠️ Grok flagged: '+rejection+'</div>' if not is_valid and rejection and rejection!="nan" else ''}
          {'<div class="card-tags" style="margin-top:6px">'+extra_html+'</div>' if extra_html else ''}
          {'<div class="card-links">'+links_html+'</div>' if links_html else ''}
        </div>
        """, unsafe_allow_html=True)


def _show_table(leads: list, key_suffix: str = ""):
    if not leads:
        st.info("No results. Try adjusting your filters.")
        return

    df = pd.DataFrame(leads)
    vis = [c for c in st.session_state.visible_cols if c in df.columns]
    if not vis:
        vis = [c for c in DEFAULT_COLUMNS if c in df.columns]

    display_df = df[vis].copy()

    # Format columns
    for col_key in ["bis_certified","gst_registered","iec_found","mca_active"]:
        if col_key in display_df.columns:
            display_df[col_key] = display_df[col_key].apply(_bool_icon)
    if "compliance_gaps" in display_df.columns:
        display_df["compliance_gaps"] = display_df["compliance_gaps"].apply(
            lambda g: ", ".join(GAP_LABELS.get(x,x) for x in g)
            if isinstance(g, list) else "")
    if "products" in display_df.columns:
        display_df["products"] = display_df["products"].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p, list) else str(p or ""))
    if "final_score" in display_df.columns:
        display_df["final_score"] = pd.to_numeric(
            display_df["final_score"], errors="coerce").round(3)
    if "created_at" in display_df.columns:
        display_df["created_at"] = pd.to_datetime(
            display_df["created_at"], errors="coerce").dt.strftime("%d %b %Y")

    # Rename to friendly names
    display_df.rename(columns={c: ALL_COLUMNS.get(c, c) for c in display_df.columns},
                      inplace=True)

    st.dataframe(display_df, use_container_width=True,
                 height=min(60 + len(display_df) * 36, 600))

    # Download CSV
    csv_df = df[vis].copy()
    for col in ["compliance_gaps","products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(
                lambda v: ", ".join(v) if isinstance(v, list) else str(v or ""))
    csv = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download as CSV",
        data=csv,
        file_name=f"leads_{key_suffix}.csv",
        mime="text/csv",
        key=f"dl_{key_suffix}_{len(leads)}",
    )


def _show_results(leads: list, key_suffix: str = "tab"):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="icon">📭</div>
          <h3>No companies here yet</h3>
          <p>Try a different filter or run a new search.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    filtered = _apply_filters(leads)
    count_txt = f"{len(filtered)} of {len(leads)} companies" \
                if len(filtered) != len(leads) else f"{len(leads)} companies"

    top_left, top_right = st.columns([3, 1])
    with top_left:
        st.caption(f"Showing **{count_txt}**")
    with top_right:
        view = st.radio("View as", ["Cards", "Table"],
                        horizontal=True, key=f"view_{key_suffix}",
                        index=0 if st.session_state.view_mode == "Cards" else 1)
        st.session_state.view_mode = view

    if view == "Cards":
        _show_cards(filtered)
    else:
        _show_table(filtered, key_suffix=key_suffix)

# ===========================================================================
# RESULTS SECTION
# ===========================================================================
if company_leads:
    st.markdown("---")

    # Summary metrics
    _show_metrics(company_leads)
    st.markdown("<br>", unsafe_allow_html=True)

    # Tabs
    tab_all, tab_high, tab_gaps, tab_mfg, tab_imp, tab_trade, tab_dir = st.tabs([
        f"🌐 All ({len(company_leads)})",
        "⭐ High Priority",
        "⚠️ Compliance Issues",
        "🏭 Manufacturers",
        "📦 Importers",
        "🤝 Traders & Distributors",
        "📂 Directories",
    ])

    with tab_all:
        _show_results(company_leads, "all")

    with tab_high:
        st.caption("Companies most likely to be a good fit based on your search")
        high_leads = [x for x in company_leads
                      if str(x.get("importance","")).lower() == "high"]
        _show_results(high_leads, "high")

    with tab_gaps:
        st.markdown("""
        <div class="info-box">
          ⚠️ These companies have <strong>missing licences or registrations</strong>
          (BIS, GST, IEC, MCA). They may need compliance services — great sales prospects.
        </div>
        """, unsafe_allow_html=True)
        gap_leads = [x for x in company_leads
                     if isinstance(x.get("compliance_gaps"), list)
                     and len(x["compliance_gaps"]) > 0]
        _show_results(gap_leads, "gaps")

    with tab_mfg:
        st.caption("Companies that make / produce goods themselves")
        mfg_leads = [x for x in company_leads if x.get("channel_type") == "Manufacturer"]
        _show_results(mfg_leads, "mfg")

    with tab_imp:
        st.caption("Companies that bring goods in from other countries")
        imp_leads = [x for x in company_leads if x.get("channel_type") == "Importer"]
        _show_results(imp_leads, "imp")

    with tab_trade:
        st.caption("Traders, distributors, wholesalers and retailers")
        trade_leads = [x for x in company_leads
                       if x.get("channel_type") in
                       ("Trader","Distributor","Wholesaler","Retailer")]
        _show_results(trade_leads, "trade")

    with tab_dir:
        st.markdown("#### 📂 Directory Pages Found")
        st.caption(
            "When Grok detects that a search result is a **business directory** "
            "(a page listing multiple companies), it appears here. "
            "You can extract all the companies from it as individual leads."
        )

        dir_leads = [x for x in company_leads if x.get("is_directory")]
        if not dir_leads:
            st.info("No directory pages detected in current results. "
                    "Try searching for terms like 'electronics importers list' or "
                    "'manufacturers directory Gujarat'.")
        else:
            for dl in dir_leads:
                dname   = dl.get("company","Unknown")
                durl    = dl.get("active_website", dl.get("website",""))
                dcount  = int(dl.get("directory_count", 0) or 0)
                dsum    = dl.get("ai_summary","")[:150]

                st.markdown(f"""
                <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;
                     padding:16px 20px;margin-bottom:10px;">
                  <div style="font-weight:700;color:#1e293b;font-size:1rem;">
                    📂 {dname}
                  </div>
                  <div style="font-size:0.8rem;color:#64748b;margin:4px 0">
                    🌐 <a href="{durl}" target="_blank">{durl}</a>
                  </div>
                  {"<div style='font-size:0.82rem;color:#475569;margin:6px 0'>"+dsum+"</div>" if dsum else ""}
                  <div style="background:#fef9c3;color:#854d0e;padding:4px 12px;
                       border-radius:6px;font-size:0.8rem;display:inline-block;margin-top:6px;">
                    📊 ~{dcount} companies listed inside
                  </div>
                </div>
                """, unsafe_allow_html=True)

                col_x, col_y = st.columns([2,3])
                with col_x:
                    if st.button(f"⚡ Extract All Companies from this Directory",
                                 key=f"extract_{durl[:30]}"):
                        with st.spinner(f"Extracting companies from {dname}…"):
                            try:
                                r = _api_post("/leads/extract-directory",
                                    json={
                                        "website": durl,
                                        "content": dl.get("content",""),
                                        "query":   st.session_state.active_query,
                                    }, timeout=60)
                                if r.status_code == 200:
                                    result = r.json()
                                    saved  = result.get("saved", 0)
                                    found  = result.get("extracted", 0)
                                    st.success(
                                        f"✅ Extracted **{found}** companies, "
                                        f"saved **{saved}** as leads! Refresh to see them."
                                    )
                                    if result.get("companies"):
                                        st.dataframe(
                                            pd.DataFrame(result["companies"]),
                                            use_container_width=True,
                                        )
                                else:
                                    st.error(f"Extraction failed: {r.text}")
                            except Exception as e:
                                st.error(f"Cannot reach server: {e}")

    # LinkedIn profiles
    linkedin_leads = [x for x in raw_leads if x.get("source") == "linkedin_semantic"]
    if linkedin_leads:
        with st.expander(f"👤 LinkedIn Contacts Found ({len(linkedin_leads)})"):
            ld = pd.DataFrame(linkedin_leads)
            cols = ["name","profile","snippet","searched_query","created_at"]
            st.dataframe(ld[[c for c in cols if c in ld.columns]],
                         use_container_width=True)

    # Compliance checker
    st.markdown("---")
    with st.expander("🔬 Check Licences & Registrations (BIS, GST, IEC, MCA)", expanded=False):
        st.markdown("""
        Automatically check which companies are missing important Indian business registrations.
        Companies with missing licences are highlighted — these are high-value prospects.
        """)
        n = st.slider("How many companies to check?", 5, 100, 20, key="enrich_n")
        cf_enrich = "" if st.session_state.sf_country == "Any Country" \
                    else st.session_state.sf_country.lower()
        if st.button("▶️ Start Checking", key="enrich_btn", type="primary"):
            with st.spinner("Checking registrations… this takes 1-2 minutes"):
                try:
                    r = _api_post("/leads/enrich-compliance",
                        params={"limit": n, "country_filter": cf_enrich},
                        timeout=300)
                    if r.status_code == 200:
                        st.success(f"✅ Checked {r.json().get('checked',0)} companies. Refresh to see results.")
                    else:
                        st.error("Check failed.")
                except Exception as e:
                    st.error(str(e))

elif not st.session_state.active_job_id:
    # No leads, not searching — show empty state
    st.markdown("""
    <div class="empty-state" style="margin-top:40px">
      <div class="icon">🌐</div>
      <h3>Ready to find leads</h3>
      <p>Type what kind of business you're looking for in the search bar above.<br>
         For example: <em>"electronics importers Gujarat"</em> or <em>"pharma manufacturers Mumbai"</em></p>
    </div>
    """, unsafe_allow_html=True)
