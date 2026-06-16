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
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

*, *::before, *::after { font-family: 'Inter', sans-serif; box-sizing: border-box; }

/* ── Page ── */
.stApp { background: #f9fafb; }
#MainMenu, footer, header { visibility: hidden; }
[data-testid="stToolbar"] { display: none; }

/* ── All text black ── */
.stApp, .stApp * { color: #111827; }
label, p, span, div,
[data-testid="stWidgetLabel"] p,
[data-testid="stMarkdownContainer"] p,
.stMarkdown p, .stMarkdown strong,
.stCheckbox label span, .stRadio label span,
[data-baseweb="checkbox"] span, [data-baseweb="radio"] span,
[data-testid="stWidgetLabel"],
.stSlider [data-testid="stWidgetLabel"] p,
.stRadio > div label p,
.stCheckbox > label > div p { color: #111827 !important; }

/* ── Topbar ── */
.topbar {
    background: #fff;
    border-bottom: 1px solid #e5e7eb;
    padding: 12px 28px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    margin: -1rem -1rem 0 -1rem;
    position: sticky;
    top: 0;
    z-index: 100;
}
.topbar-logo { font-size: 1.15rem; font-weight: 700; color: #111827; letter-spacing: -0.02em; }
.topbar-logo span { color: #6366f1; }
.topbar-user {
    font-size: 0.78rem; color: #6b7280;
    background: #f3f4f6; padding: 5px 12px; border-radius: 20px;
}

/* ── Hero ── */
.search-hero {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 14px;
    padding: 32px 28px 24px;
    margin: 16px 0 14px;
    text-align: center;
}
.search-hero h1 {
    color: #111827; font-size: 1.55rem; font-weight: 700;
    margin: 0 0 5px; letter-spacing: -0.02em;
}
.search-hero p { color: #6b7280; font-size: 0.88rem; margin: 0; }

/* ── Chips ── */
.chip {
    display: inline-block;
    background: #f3f4f6; color: #374151;
    border: 1px solid #e5e7eb;
    padding: 4px 12px; border-radius: 20px;
    font-size: 0.75rem; cursor: pointer;
    transition: border-color 0.12s;
}
.chip:hover { border-color: #9ca3af; }

/* ── Inputs ── */
.stTextInput input, input[type="text"], input[type="password"], textarea {
    background: #fff !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 8px !important;
    color: #111827 !important;
    font-size: 0.9rem !important;
    padding: 10px 14px !important;
    -webkit-text-fill-color: #111827 !important;
    transition: border-color 0.15s !important;
    box-shadow: none !important;
}
.stTextInput input:focus {
    border-color: #6366f1 !important;
    box-shadow: 0 0 0 3px rgba(99,102,241,0.08) !important;
}
.stTextInput input::placeholder {
    color: #9ca3af !important;
    -webkit-text-fill-color: #9ca3af !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div,
div[data-baseweb="select"] > div {
    border-radius: 8px !important;
    border: 1.5px solid #e5e7eb !important;
    background: #fff !important;
    color: #111827 !important;
    font-size: 0.85rem !important;
}
div[data-baseweb="select"] span,
div[data-baseweb="select"] [class*="singleValue"],
div[data-baseweb="select"] [class*="placeholder"],
div[data-baseweb="select"] input {
    color: #111827 !important;
    -webkit-text-fill-color: #111827 !important;
    background: transparent !important;
}

/* ── Dropdown popup ── */
ul[role="listbox"], div[role="listbox"],
[data-baseweb="popover"], [data-baseweb="menu"],
[data-baseweb="popover"] > div, [data-baseweb="menu"] > div,
[data-baseweb="menu"] ul {
    background: #fff !important;
    border: 1px solid #e5e7eb !important;
    border-radius: 10px !important;
    box-shadow: 0 4px 16px rgba(0,0,0,0.08) !important;
}
ul[role="listbox"] li, [data-baseweb="menu"] li,
[role="option"], div[role="option"], li[role="option"] {
    background: #fff !important; color: #111827 !important;
}
ul[role="listbox"] li *, [role="option"] *, div[role="option"] * {
    color: #111827 !important; background: transparent !important;
}
ul[role="listbox"] li:hover, [role="option"]:hover,
div[role="option"]:hover, li[role="option"]:hover,
[aria-selected="true"][role="option"] {
    background: #eef2ff !important; color: #4f46e5 !important;
}
ul[role="listbox"] li:hover *, [role="option"]:hover * { color: #4f46e5 !important; }

/* ── Buttons — default ghost ── */
.stButton > button {
    background: #fff !important;
    color: #111827 !important;
    border: 1.5px solid #e5e7eb !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    font-size: 0.84rem !important;
    padding: 8px 16px !important;
    transition: border-color 0.12s, color 0.12s !important;
    box-shadow: none !important;
}
.stButton > button:hover {
    border-color: #6366f1 !important;
    color: #4f46e5 !important;
    box-shadow: none !important;
}

/* ── Primary search button ── */
.search-btn .stButton > button {
    background: #111827 !important;
    color: #fff !important;
    border: none !important;
    font-size: 0.92rem !important;
    padding: 11px 24px !important;
    border-radius: 8px !important;
}
.search-btn .stButton > button:hover {
    background: #1f2937 !important;
    color: #fff !important;
    border: none !important;
}

/* ── Type="primary" buttons ── */
.stButton > button[kind="primary"] {
    background: #111827 !important;
    color: #fff !important;
    border: none !important;
}
.stButton > button[kind="primary"]:hover {
    background: #1f2937 !important;
    color: #fff !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    background: transparent;
    border: none;
    border-bottom: 1px solid #e5e7eb;
    border-radius: 0;
    padding: 0;
    gap: 0;
}
[data-testid="stTabs"] [role="tab"] {
    border-radius: 0 !important;
    color: #6b7280 !important;
    font-size: 0.82rem !important;
    font-weight: 500 !important;
    padding: 10px 16px !important;
    border: none !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #111827 !important;
    background: transparent !important;
    border-bottom: 2px solid #111827 !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 14px 16px !important;
    box-shadow: none;
}
[data-testid="stMetricValue"] { font-size: 1.7rem !important; font-weight: 700 !important; color: #111827 !important; }
[data-testid="stMetricLabel"] { font-size: 0.69rem !important; color: #9ca3af !important; text-transform: uppercase; letter-spacing: 0.06em; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #fff;
    border: 1px solid #e5e7eb !important;
    border-radius: 10px !important;
    box-shadow: none !important;
}
[data-testid="stExpander"] summary p,
[data-testid="stExpander"] details summary p { color: #111827 !important; font-weight: 600 !important; }

/* ── Checkbox / Radio / Slider ── */
.stCheckbox { font-size: 0.84rem !important; }
.stSlider label, .stSlider [data-testid="stWidgetLabel"] p,
.stSlider div[data-testid="stTickBarMin"],
.stSlider div[data-testid="stTickBarMax"],
[data-testid="stTickBar"] span { color: #111827 !important; }

/* ── Status pills ── */
.status-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.7rem;
    font-weight: 600;
    letter-spacing: 0.02em;
}
.pill-high   { background: #dcfce7; color: #166534; }
.pill-medium { background: #fef9c3; color: #854d0e; }
.pill-low    { background: #f3f4f6; color: #6b7280; }
.pill-gap    { background: #fee2e2; color: #991b1b; }
.pill-clean  { background: #dcfce7; color: #166534; }

/* ── Lead cell (collapsed) ── */
.lead-cell {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 5px;
    transition: border-color 0.12s, box-shadow 0.12s;
}
.lead-cell:hover {
    border-color: #c7d2fe;
    box-shadow: 0 2px 8px rgba(99,102,241,0.06);
}
.cell-icon {
    width: 34px; height: 34px; border-radius: 8px;
    background: #f3f4f6;
    display: flex; align-items: center; justify-content: center;
    font-size: 1rem; flex-shrink: 0;
}
.cell-body { flex: 1; min-width: 0; }
.cell-name {
    font-size: 0.88rem; font-weight: 600; color: #111827;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cell-meta {
    font-size: 0.72rem; color: #6b7280; margin-top: 2px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.cell-right { display: flex; align-items: center; gap: 5px; flex-shrink: 0; }

/* ── Score badge ── */
.score-badge {
    background: #f3f4f6; color: #374151;
    border: 1px solid #e5e7eb;
    padding: 2px 9px; border-radius: 20px;
    font-size: 0.72rem; font-weight: 700;
}

/* ── Expanded card ── */
.expanded-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 12px;
    padding: 20px 22px 16px;
    margin-bottom: 8px;
    box-shadow: 0 2px 12px rgba(0,0,0,0.04);
}
.expanded-title { font-size: 1.05rem; font-weight: 700; color: #111827; margin: 0 0 3px; }
.expanded-sub   { font-size: 0.76rem; color: #6b7280; margin-bottom: 12px; }
.expanded-section {
    font-size: 0.66rem; font-weight: 700; color: #9ca3af;
    text-transform: uppercase; letter-spacing: .08em;
    margin: 14px 0 4px; border-top: 1px solid #f3f4f6; padding-top: 10px;
}
.expanded-body { font-size: 0.82rem; color: #374151; line-height: 1.6; }
.dir-item {
    background: #f9fafb; border: 1px solid #e5e7eb;
    border-radius: 7px; padding: 8px 12px; margin-bottom: 4px;
    font-size: 0.78rem; color: #374151;
}
.dir-item strong { color: #111827; }

/* ── Result card (full cards view) ── */
.result-card {
    background: #fff;
    border: 1px solid #e5e7eb;
    border-radius: 10px;
    padding: 16px 18px;
    margin-bottom: 8px;
    transition: border-color 0.12s, box-shadow 0.12s;
}
.result-card:hover { box-shadow: 0 2px 10px rgba(0,0,0,0.05); border-color: #c7d2fe; }
.card-company { font-size: 0.95rem; font-weight: 600; color: #111827; }
.card-meta    { font-size: 0.76rem; color: #6b7280; margin: 3px 0 7px; }
.card-summary { font-size: 0.81rem; color: #4b5563; line-height: 1.5; margin: 5px 0; }
.card-tags    { display: flex; gap: 5px; flex-wrap: wrap; margin-top: 7px; }
.card-tag     { background: #f3f4f6; color: #4b5563; padding: 2px 9px; border-radius: 6px; font-size: 0.7rem; font-weight: 500; }
.card-links   { margin-top: 10px; display: flex; gap: 12px; flex-wrap: wrap; }
.card-link    { font-size: 0.77rem; color: #4f46e5; text-decoration: none; }
.card-link:hover { text-decoration: underline; }

/* ── Master-detail panels ── */
.master-panel {
    height: calc(100vh - 240px);
    overflow-y: auto; overflow-x: hidden;
    padding-right: 4px;
    scrollbar-width: thin; scrollbar-color: #e5e7eb transparent;
}
.master-panel::-webkit-scrollbar { width: 4px; }
.master-panel::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 4px; }

.detail-panel {
    position: sticky; top: 70px;
    max-height: calc(100vh - 180px);
    overflow-y: auto; overflow-x: hidden;
    scrollbar-width: thin; scrollbar-color: #e5e7eb transparent;
}
.detail-panel::-webkit-scrollbar { width: 4px; }
.detail-panel::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 4px; }

/* ── Detail card ── */
.detail-card {
    background: #fff; border: 1px solid #e5e7eb;
    border-radius: 12px; padding: 20px 22px 22px;
    box-shadow: 0 1px 8px rgba(0,0,0,0.04);
}
.detail-title  { font-size: 1.08rem; font-weight: 700; color: #111827; margin: 0 0 3px; }
.detail-sub    { font-size: 0.76rem; color: #6b7280; margin-bottom: 12px; }
.detail-section {
    font-size: 0.65rem; font-weight: 700; color: #9ca3af;
    text-transform: uppercase; letter-spacing: .08em;
    margin: 14px 0 4px; border-top: 1px solid #f3f4f6; padding-top: 10px;
}
.detail-body  { font-size: 0.81rem; color: #374151; line-height: 1.65; }
.detail-links { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }
.detail-link  { font-size: 0.77rem; color: #4f46e5; text-decoration: none; font-weight: 600; }
.detail-link:hover { text-decoration: underline; }
.detail-empty {
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    min-height: 280px; color: #9ca3af; text-align: center;
    padding: 40px 20px; background: #fff;
    border: 1.5px dashed #e5e7eb; border-radius: 12px;
}
.detail-empty p { font-size: 0.81rem; margin: 0; line-height: 1.5; }
.detail-dir-item {
    background: #f9fafb; border: 1px solid #e5e7eb;
    border-radius: 7px; padding: 7px 11px; margin-bottom: 4px;
    font-size: 0.77rem; color: #374151;
}
.detail-dir-item strong { color: #111827; }

/* ── Info box ── */
.info-box {
    background: #f0f9ff; border: 1px solid #bae6fd;
    border-radius: 8px; padding: 10px 14px;
    font-size: 0.82rem; color: #0369a1; margin-bottom: 10px;
}

/* ── Empty state ── */
.empty-state { text-align: center; padding: 56px 20px; }
.empty-state .icon { font-size: 2.8rem; margin-bottom: 10px; }
.empty-state h3 { color: #374151; font-size: 1rem; margin: 0 0 5px; font-weight: 600; }
.empty-state p  { font-size: 0.83rem; color: #6b7280; margin: 0; }

/* ── Column picker ── */
.col-picker-wrap {
    background: #fff; border: 1px solid #e5e7eb;
    border-radius: 10px; padding: 16px 18px; margin-bottom: 14px;
}

/* ── Sidebar ── */
[data-testid="stSidebar"] {
    background: #fff !important;
    border-right: 1px solid #e5e7eb !important;
}
[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] .stTextInput input {
    background: #f9fafb !important;
    border: 1px solid #e5e7eb !important;
    font-size: 0.82rem !important;
}
[data-testid="stSidebar"] label,
[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    color: #374151 !important;
    text-transform: uppercase;
    letter-spacing: .05em;
}
[data-testid="stSidebar"] * { color: #111827 !important; }

/* ── Download button ── */
.stDownloadButton > button {
    background: #fff !important; color: #111827 !important;
    border: 1.5px solid #e5e7eb !important; border-radius: 8px !important;
    font-weight: 500 !important; font-size: 0.81rem !important;
}
.stDownloadButton > button:hover {
    border-color: #6366f1 !important; color: #4f46e5 !important;
}

/* ── Alert / toast ── */
.stAlert { border-radius: 8px !important; }
[data-testid="stAlert"] p, [data-testid="stAlert"] div { color: #111827 !important; }
[data-testid="stToast"] p { color: #111827 !important; }

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }
[data-testid="stDataFrame"] table,
[data-testid="stDataFrame"] th,
[data-testid="stDataFrame"] td { color: #111827 !important; }

/* ── Divider ── */
hr { border-color: #e5e7eb !important; margin: 10px 0 !important; }

/* ── Progress ── */
.stProgress > div > div { background: #6366f1 !important; border-radius: 3px; }

/* ── Scrollbar ── */
::-webkit-scrollbar { width: 5px; height: 5px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #d1d5db; }

/* ── Multiselect tags ── */
[data-baseweb="tag"] { background: #eef2ff !important; color: #4f46e5 !important; }
[data-baseweb="tag"] span { color: #4f46e5 !important; }

/* ── Caption ── */
.stCaption, [data-testid="stCaptionContainer"] p { color: #6b7280 !important; font-size: 0.76rem !important; }

/* ── Selection ── */
::selection { background: #e0e7ff; color: #3730a3; }
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
    <div style="max-width:420px;margin:72px auto 0;padding:0 16px">
      <div style="text-align:center;margin-bottom:28px">
        <div style="font-size:1.6rem;font-weight:700;color:#111827;letter-spacing:-0.02em;margin-bottom:4px">
          Buyera
        </div>
        <p style="color:#6b7280;font-size:0.88rem;margin:0">
          Find business leads from around the world
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
                            try:
                                err = r.json().get("detail", "Sign in failed. Check your details.")
                            except Exception:
                                err = f"Sign in failed (HTTP {r.status_code})"
                            st.error(err)
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
                            try:
                                err = r.json().get("detail", "Registration failed.")
                            except Exception:
                                err = f"Registration failed (HTTP {r.status_code})"
                            st.error(err)
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

ALL_CITIES = {
    "India": [
        "Mumbai","Delhi","Bangalore","Bengaluru","Hyderabad","Ahmedabad","Chennai",
        "Kolkata","Surat","Pune","Jaipur","Lucknow","Nagpur","Indore","Thane",
        "Bhopal","Patna","Vadodara","Ghaziabad","Ludhiana","Agra","Nashik",
        "Faridabad","Meerut","Rajkot","Varanasi","Aurangabad","Coimbatore",
        "Vijayawada","Noida","Gurgaon","Gurugram","Chandigarh","Mysore","Mysuru",
        "Amritsar","Kochi","Cochin","Ernakulam",
    ],
    "UAE":       ["Dubai","Abu Dhabi","Sharjah","Ajman","Ras Al Khaimah","Fujairah"],
    "USA":       ["New York","Los Angeles","Chicago","Houston","Phoenix","Philadelphia",
                  "San Antonio","San Diego","Dallas","San Jose","Austin","Jacksonville"],
    "UK":        ["London","Manchester","Birmingham","Leeds","Glasgow","Liverpool",
                  "Bristol","Sheffield","Edinburgh","Cardiff"],
    "Germany":   ["Berlin","Hamburg","Munich","Cologne","Frankfurt","Stuttgart",
                  "Düsseldorf","Dortmund","Essen","Leipzig"],
    "Canada":    ["Toronto","Montreal","Vancouver","Calgary","Edmonton","Ottawa",
                  "Winnipeg","Quebec City","Hamilton","Kitchener"],
    "Australia": ["Sydney","Melbourne","Brisbane","Perth","Adelaide","Gold Coast",
                  "Newcastle","Canberra","Sunshine Coast","Wollongong"],
    "Singapore": ["Singapore"],
    "China":     ["Beijing","Shanghai","Guangzhou","Shenzhen","Chengdu","Hangzhou",
                  "Wuhan","Xi'an","Nanjing","Tianjin"],
    "Italy":     ["Rome","Milan","Naples","Turin","Palermo","Genoa","Bologna",
                  "Florence","Bari","Catania"],
    "France":    ["Paris","Marseille","Lyon","Toulouse","Nice","Nantes","Strasbourg",
                  "Montpellier","Bordeaux","Lille"],
    "Japan":     ["Tokyo","Osaka","Nagoya","Sapporo","Fukuoka","Kobe","Kyoto",
                  "Kawasaki","Saitama","Hiroshima"],
}

QUALITY_LABELS = {
    0: ("Show Everything",   "Includes directories, social pages, low-relevance results"),
    1: ("Basic Filter",      "Removes obvious junk, keeps directories and borderline leads"),
    2: ("Good Leads Only",   "Medium+ relevance — solid business prospects"),
    3: ("Best Matches Only", "High relevance only — verified, enriched, AI-approved"),
}

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
    "sf_city":            "Any",
    "_reset_filters":     False,
    "expanded_cards":     {},
    "card_details":       {},
    "selected_card":      None,
    "selected_tab":       "",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()

# ---------------------------------------------------------------------------
# Process pending filter reset BEFORE any widgets render
# ---------------------------------------------------------------------------
if st.session_state.get("_reset_filters"):
    st.session_state["_reset_filters"] = False
    for _k, _v in {
        "sf_country":        "Any Country",
        "sf_state":          "Any",
        "sf_city":           "Any",
        "sf_industry":       "Any",
        "sf_channel":        "Any",
        "sf_importance":     "Any",
        "sf_min_score":      0.0,
        "sf_has_email":      False,
        "sf_has_phone":      False,
        "sf_gaps_only":      False,
        "quality_threshold": 0,
        "scan_all":          False,
        "sf_sort":           "Best Match First",
        "sf_query":          "",
    }.items():
        st.session_state[_k] = _v
    st.rerun()

# ===========================================================================
# SIDEBAR
# ===========================================================================
with st.sidebar:
    st.markdown(f"""
    <div style="padding:4px 0 14px;border-bottom:1px solid #f3f4f6">
      <div style="font-size:1.1rem;font-weight:700;color:#111827;letter-spacing:-.02em">Buyera</div>
      <div style="font-size:0.72rem;color:#9ca3af;margin-top:2px">
        Signed in as <strong style="color:#374151">{st.session_state.auth_username}</strong>
      </div>
    </div>
    """, unsafe_allow_html=True)

    if st.button("Sign out", key="sb_logout_btn", use_container_width=True):
        for k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[k] = ""
        st.rerun()

    st.markdown("---")
    st.markdown("**Filters**")

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

    _city_opts = (["Any"] + ALL_CITIES.get(st.session_state.sf_country, [])
                  if st.session_state.sf_country != "Any Country" else ["Any"])
    if st.session_state.sf_city not in _city_opts:
        st.session_state.sf_city = "Any"
    st.session_state.sf_city = st.selectbox(
        "City", _city_opts,
        index=_city_opts.index(st.session_state.sf_city),
        key="sb_city_sel",
        disabled=(st.session_state.sf_country == "Any Country"))

    _ind_opts = ["Any"] + ALL_INDUSTRIES
    _ind_idx  = _ind_opts.index(st.session_state.sf_industry) \
                if st.session_state.sf_industry in _ind_opts else 0
    st.session_state.sf_industry = st.selectbox(
        "Industry", _ind_opts, index=_ind_idx, key="sb_industry_sel")

    _ch_opts = ["Any"] + CHANNEL_TYPES
    _ch_idx  = _ch_opts.index(st.session_state.sf_channel) \
               if st.session_state.sf_channel in _ch_opts else 0
    st.session_state.sf_channel = st.selectbox(
        "Business Type", _ch_opts, index=_ch_idx, key="sb_channel_sel")

    _imp_opts = ["Any", "High", "Medium", "Low"]
    _imp_idx  = _imp_opts.index(st.session_state.sf_importance) \
                if st.session_state.sf_importance in _imp_opts else 0
    st.session_state.sf_importance = st.selectbox(
        "Priority", _imp_opts, index=_imp_idx, key="sb_importance_sel")

    _sort_opts = ["Best Match First","Priority (High → Low)",
                  "Company Name A → Z","Company Name Z → A","Newest First"]
    _sort_idx  = _sort_opts.index(st.session_state.sf_sort) \
                 if st.session_state.sf_sort in _sort_opts else 0
    st.session_state.sf_sort = st.selectbox(
        "Sort by", _sort_opts, index=_sort_idx, key="sb_sort_sel")

    st.session_state.sf_min_score = st.slider(
        "Min score", 0.0, 1.0, st.session_state.sf_min_score, 0.05,
        key="sb_score_sl")

    st.markdown("**Quick filters**")
    st.session_state.sf_has_email = st.checkbox("Has email",  key="sb_email_cb",
                                                 value=st.session_state.sf_has_email)
    st.session_state.sf_has_phone = st.checkbox("Has phone",  key="sb_phone_cb",
                                                 value=st.session_state.sf_has_phone)
    st.session_state.sf_gaps_only = st.checkbox("Compliance issues only",
                                                  key="sb_gaps_cb",
                                                  value=st.session_state.sf_gaps_only)

    st.markdown("---")
    st.markdown("**Search options**")
    st.session_state.scan_all = st.checkbox(
        "Scan all pages (slower)", key="sb_scan_cb",
        value=st.session_state.scan_all)

    _qt_labels = ["All","Basic","Good","Best"]
    _qt_map    = {"All":0,"Basic":1,"Good":2,"Best":3}
    _qt_rev    = {0:"All",1:"Basic",2:"Good",3:"Best"}
    _qt_cur    = _qt_rev.get(st.session_state.quality_threshold, "All")
    _qt_sel    = st.select_slider("Output quality", _qt_labels,
                                   value=_qt_cur, key="sb_qt_sl")
    st.session_state.quality_threshold = _qt_map[_qt_sel]

    q_lbl, q_desc = QUALITY_LABELS.get(st.session_state.quality_threshold, ("",""))
    st.caption(f"{q_lbl} — {q_desc}")

    st.markdown("---")
    if st.button("Clear filters", use_container_width=True, key="sb_clear_btn"):
        st.session_state["_reset_filters"] = True
        st.rerun()
    if st.button("Delete all leads", use_container_width=True, key="sb_del_btn"):
        try:
            _api_delete("/clear", timeout=15)
            st.session_state.active_job_id  = ""
            st.session_state.active_query   = ""
            st.session_state.live_results   = []
            st.session_state.live_cursor    = 0
            st.session_state.notified_jobs  = []
            st.session_state.expanded_cards = {}
            st.session_state.card_details   = {}
            st.session_state.selected_card  = None
            st.session_state.selected_tab   = ""
            st.rerun()
        except Exception as e:
            st.error(str(e))

# ---------------------------------------------------------------------------
# Top nav bar
# ---------------------------------------------------------------------------
st.markdown(f"""
<div class="topbar">
  <div class="topbar-logo">Bue<span>ra</span></div>
  <div class="topbar-user">{st.session_state.auth_username}</div>
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
            recent = rj.json()
            for job in recent[:5]:
                if job.get("status") in ("completed", "running", "queued"):
                    st.session_state.active_job_id = job.get("job_id", "")
                    st.session_state.active_query  = job.get("query", "")
                    break
    except Exception:
        pass

# ===========================================================================
# HERO SEARCH
# ===========================================================================
st.markdown("""
<div class="search-hero">
  <h1>Find Your Next Business Customer</h1>
  <p>Search for companies, importers, manufacturers, distributors — anywhere in the world</p>
</div>
""", unsafe_allow_html=True)

sc1, sc2, sc3 = st.columns([5, 1, 1])
with sc1:
    query = st.text_input(
        "search_input",
        value=st.session_state.sf_query,
        placeholder='e.g. "LED light importers Gujarat" or "pharma distributors Mumbai"',
        label_visibility="collapsed",
        key="search_input_box",
    )
    st.session_state.sf_query = query
with sc2:
    st.markdown('<div class="search-btn">', unsafe_allow_html=True)
    search_clicked = st.button("Search", use_container_width=True, key="main_search_btn")
    st.markdown('</div>', unsafe_allow_html=True)
with sc3:
    refresh_clicked = st.button("Refresh", use_container_width=True, key="refresh_btn")
    if refresh_clicked:
        st.rerun()

st.markdown("""
<div style="display:flex;gap:6px;flex-wrap:wrap;margin:7px 0 3px;align-items:center">
  <span style="font-size:0.74rem;color:#9ca3af">Try:</span>
  <span class="chip">Electronics importers Delhi</span>
  <span class="chip">Textile manufacturers Surat</span>
  <span class="chip">Pharma distributors Mumbai</span>
  <span class="chip">Steel traders UAE</span>
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
    city = st.session_state.get("sf_city","Any")
    if city and city not in ("Any",""):
        if city.lower() not in st.session_state.sf_query.lower():
            parts.append(city)
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
                "quality_threshold":  st.session_state.quality_threshold,
            }, timeout=30)
            if r.status_code == 200:
                d = r.json()
                st.session_state.active_job_id  = d.get("job_id", "")
                st.session_state.active_query   = fq
                st.session_state.live_results   = []
                st.session_state.live_cursor    = 0
                st.session_state.expanded_cards = {}
                st.session_state.card_details   = {}
                st.session_state.selected_card  = None
                st.session_state.selected_tab   = ""
                st.rerun()
            else:
                try:
                    err = r.json().get("detail", r.text)
                except Exception:
                    err = f"HTTP {r.status_code}"
                st.error(f"Search error: {err}")
        except Exception as e:
            st.error(f"Cannot reach server: {e}")

# ---------------------------------------------------------------------------
# Fetch all leads
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

if company_leads or st.session_state.active_job_id:
    st.markdown("---")

    # -----------------------------------------------------------------------
    # FILTER EXPANDER
    # -----------------------------------------------------------------------
    def _clear_filters_cb():
        st.session_state["_reset_filters"] = True

    with st.expander("Filters & Options", expanded=False):
        st.markdown("**Narrow down your results** *(also available in the sidebar)*")
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
                ["Any", "High", "Medium", "Low"],
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
            if st.button("Clear All Filters", use_container_width=True):
                st.session_state["_reset_filters"] = True
                st.rerun()
        with cc:
            if st.button("Delete All Leads", use_container_width=True):
                try:
                    _api_delete("/clear", timeout=15)
                    st.session_state.active_job_id  = ""
                    st.session_state.active_query   = ""
                    st.session_state.live_results   = []
                    st.session_state.live_cursor    = 0
                    st.session_state.notified_jobs  = []
                    st.session_state.expanded_cards = {}
                    st.session_state.card_details   = {}
                    st.session_state.selected_card  = None
                    st.session_state.selected_tab   = ""
                    st.rerun()
                except Exception as e:
                    st.error(str(e))

    # -----------------------------------------------------------------------
    # COLUMN PICKER
    # -----------------------------------------------------------------------
    with st.expander("Choose Which Columns to Show", expanded=False):
        st.markdown("**Pick exactly what information you want to see in the table**")

        col_groups = {
            "Company Info": ["company","city","country_detected","industry_detected",
                                "product_type","channel_type","company_size","incorporation_date"],
            "Scores & Priority": ["importance","final_score","domain_authority"],
            "Compliance": ["compliance_gaps","bis_certified","gst_registered",
                              "iec_found","mca_active","mca_company_type"],
            "Contact Details": ["contact_person","contact_email","email","phone","linkedin_url"],
            "Online Presence": ["active_website"],
            "AI Analysis": ["ai_summary","products","usp","key_customers"],
            "Business Details": ["annual_turnover","certifications","export_markets","grok_score"],
            "Social Media": ["linkedin_url","twitter_url","facebook_url","instagram_url","youtube_url","whatsapp_url"],
            "Lead Validation": ["is_valid_lead","rejection_reason","contact_title","contact_confidence","is_directory","directory_count"],
            "Search Info": ["searched_query","created_at"],
        }

        new_visible = []
        seen_keys = set()
        for group_name, group_cols in col_groups.items():
            st.markdown(f"**{group_name}**")
            gcols = st.columns(4)
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
            if st.button("Apply Column Selection", use_container_width=True):
                st.session_state.visible_cols = new_visible if new_visible else DEFAULT_COLUMNS[:]
                st.rerun()
        with col_btn2:
            if st.button("Reset to Default Columns", use_container_width=True):
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
        sv    = status.get("status", "")
        saved = status.get("saved_total", 0)
        pages = status.get("pages_scanned", 0)

        if sv in ("running", "queued"):
            st.markdown(f"""
            <div class="info-box">
              Searching — {saved} companies found so far
              &nbsp;·&nbsp; {pages} pages scanned &nbsp;·&nbsp; auto-refreshing
            </div>
            """, unsafe_allow_html=True)
            time.sleep(POLL_SECONDS)
            st.rerun()

        elif sv == "completed":
            jid = status.get("job_id", "")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast(f"Search done — {saved} companies found!")
                st.session_state.notified_jobs.append(jid)
            if status.get("ask_continue"):
                c1, c2 = st.columns(2)
                with c1:
                    st.info(f"Found {saved} companies. Want to search more pages?")
                with c2:
                    st.markdown("<br>", unsafe_allow_html=True)
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Yes, find more", use_container_width=True):
                            cf = "" if st.session_state.sf_country == "Any Country" \
                                 else st.session_state.sf_country.lower()
                            try:
                                r = _api_post("/search/start", params={
                                    "query": st.session_state.active_query,
                                    "continue_search": "true",
                                    "country_filter": cf,
                                }, timeout=30)
                                if r.status_code == 200:
                                    resp_data = r.json()
                                    st.session_state.active_job_id = resp_data.get("job_id","")
                                    st.rerun()
                                else:
                                    st.error(f"Continue failed: HTTP {r.status_code}")
                            except Exception as e:
                                st.error(str(e))
                    with cc2:
                        if st.button("No thanks", use_container_width=True):
                            st.session_state.active_job_id = ""
                            st.rerun()
            else:
                st.success(f"Search complete — {saved} companies found.")
                st.session_state.active_job_id = ""

        elif sv == "failed":
            st.error(f"Search failed: {status.get('error', 'Unknown error')}")
            st.session_state.active_job_id = ""

# ===========================================================================
# APPLY FILTERS
# ===========================================================================
def _apply_filters(leads: list) -> list:
    df = pd.DataFrame(leads) if leads else pd.DataFrame()
    if df.empty:
        return []

    if st.session_state.sf_channel != "Any" and "channel_type" in df.columns:
        df = df[df["channel_type"].astype(str) == st.session_state.sf_channel]

    if st.session_state.get("sf_city","Any") not in ("Any","") and "city" in df.columns:
        city_val = st.session_state.sf_city.lower()
        df = df[df["city"].astype(str).str.lower().str.contains(city_val, na=False)]

    imp_map = {"High": "high", "Medium": "medium", "Low": "low"}
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
        df = df[df["compliance_gaps"].apply(lambda g: isinstance(g, list) and len(g) > 0)]

    if st.session_state.sf_industry != "Any" and "industry_detected" in df.columns:
        df = df[df["industry_detected"].astype(str).str.lower()
                .str.contains(st.session_state.sf_industry.lower(), na=False)]

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
    if imp == "high":   return '<span class="status-pill pill-high">High</span>'
    if imp == "medium": return '<span class="status-pill pill-medium">Medium</span>'
    return '<span class="status-pill pill-low">Low</span>'

def _gap_pill(gaps):
    if not isinstance(gaps, list) or not gaps:
        return '<span class="status-pill pill-clean">Clean</span>'
    labels = [GAP_LABELS.get(g, g) for g in gaps]
    return f'<span class="status-pill pill-gap">⚠ {", ".join(labels)}</span>'

def _show_metrics(leads: list):
    if not leads:
        return
    df     = pd.DataFrame(leads)
    total  = len(df)
    high   = int((df.get("importance", pd.Series(dtype=str)).astype(str).str.lower() == "high").sum()) \
             if "importance" in df.columns else 0
    w_email= int(df["email"].astype(str).str.contains("@", na=False).sum()) \
             if "email" in df.columns else 0
    w_gap  = int(df["compliance_gaps"].apply(lambda g: isinstance(g, list) and len(g) > 0).sum()) \
             if "compliance_gaps" in df.columns else 0
    mfg    = int((df.get("channel_type", pd.Series(dtype=str)).astype(str) == "Manufacturer").sum()) \
             if "channel_type" in df.columns else 0
    m1,m2,m3,m4,m5 = st.columns(5)
    m1.metric("Companies found", total)
    m2.metric("High priority",   high)
    m3.metric("Have email",      w_email)
    m4.metric("Compliance issues", w_gap)
    m5.metric("Manufacturers",   mfg)


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
        company  = str(row.get("company", "Unknown Company"))
        city     = str(row.get("city", ""))
        country  = str(row.get("country_detected", ""))
        industry = str(row.get("industry_detected", ""))
        channel  = str(row.get("channel_type", ""))
        score    = float(row.get("final_score", 0) or 0)
        imp      = str(row.get("importance", "low"))
        gaps     = row.get("compliance_gaps", [])
        email    = str(row.get("email", ""))
        phone    = str(row.get("phone", ""))
        website  = str(row.get("active_website", row.get("website", "")))
        linkedin = str(row.get("linkedin_url", ""))
        summary  = str(row.get("ai_summary", ""))[:200]
        products = row.get("products", [])
        size     = str(row.get("company_size", ""))
        founded  = str(row.get("incorporation_date", ""))
        location = ", ".join(filter(None, [city, country]))
        tags     = [t for t in [industry, channel, size, f"Est. {founded}" if founded else ""]
                    if t and t != "nan"]
        prod_str = ""
        if isinstance(products, list) and products:
            prod_str = ", ".join(str(p) for p in products[:4])
        turnover   = str(row.get("annual_turnover", ""))
        certs      = row.get("certifications", [])
        exports    = row.get("export_markets", [])
        usp        = str(row.get("usp", ""))[:120]
        key_cust   = row.get("key_customers", [])
        twitter    = str(row.get("twitter_url",   ""))
        facebook   = str(row.get("facebook_url",  ""))
        instagram  = str(row.get("instagram_url", ""))
        youtube    = str(row.get("youtube_url",   ""))
        whatsapp   = str(row.get("whatsapp_url",  ""))
        ctitle     = str(row.get("contact_title", ""))
        cconfidence= str(row.get("contact_confidence",""))
        is_dir     = bool(row.get("is_directory", False))
        dir_count  = int(row.get("directory_count", 0) or 0)
        is_valid   = bool(row.get("is_valid_lead", True))
        rejection  = str(row.get("rejection_reason",""))

        links_html = ""
        if website and website not in ("nan", ""):
            links_html += f'<a class="card-link" href="{website}" target="_blank">Website</a>'
        if email and "@" in email:
            links_html += f'<a class="card-link" href="mailto:{email}">{email}</a>'
        if phone and phone not in ("nan",""):
            links_html += f'<span class="card-link">{phone}</span>'
        if linkedin and linkedin not in ("nan",""):
            links_html += f'<a class="card-link" href="{linkedin}" target="_blank">LinkedIn</a>'
        if twitter and twitter not in ("nan",""):
            links_html += f'<a class="card-link" href="{twitter}" target="_blank">X</a>'
        if facebook and facebook not in ("nan",""):
            links_html += f'<a class="card-link" href="{facebook}" target="_blank">Facebook</a>'
        if instagram and instagram not in ("nan",""):
            links_html += f'<a class="card-link" href="{instagram}" target="_blank">Instagram</a>'
        if youtube and youtube not in ("nan",""):
            links_html += f'<a class="card-link" href="{youtube}" target="_blank">YouTube</a>'
        if whatsapp and whatsapp not in ("nan",""):
            links_html += f'<a class="card-link" href="{whatsapp}" target="_blank">WhatsApp</a>'

        extra_html = ""
        if turnover and turnover not in ("nan",""):
            extra_html += f'<span class="card-tag">{turnover}</span>'
        if isinstance(certs, list) and certs:
            extra_html += f'<span class="card-tag">{", ".join(certs[:3])}</span>'
        if isinstance(exports, list) and exports:
            extra_html += f'<span class="card-tag">Exports: {", ".join(exports[:3])}</span>'
        if isinstance(key_cust, list) and key_cust:
            extra_html += f'<span class="card-tag">{", ".join(key_cust[:2])}</span>'

        tags_html = "".join(f'<span class="card-tag">{t}</span>' for t in tags)
        contact_name = row.get("contact_person","")

        st.markdown(f"""
        <div class="result-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px">
            <div style="flex:1;min-width:0">
              <div class="card-company">{company}</div>
              <div class="card-meta">{'📍 ' + location if location else ''}</div>
            </div>
            <div style="display:flex;gap:5px;flex-shrink:0;align-items:center;flex-wrap:wrap;justify-content:flex-end">
              {_importance_pill(imp)}
              {_gap_pill(gaps)}
              <span class="score-badge">{score:.2f}</span>
            </div>
          </div>
          {'<div class="card-tags">'+tags_html+'</div>' if tags_html else ''}
          {'<div class="card-summary">'+summary+'</div>' if summary and summary != "nan" else ''}
          {'<div class="card-summary" style="font-size:0.78rem;color:#4b5563">'+prod_str+'</div>' if prod_str else ''}
          {'<div class="card-summary" style="font-size:0.77rem;color:#6b7280;font-style:italic">'+usp+'</div>' if usp and usp != "nan" else ''}
          {'<div style="font-size:0.75rem;color:#374151;margin:4px 0"><strong>Contact:</strong> '+str(contact_name)+(" — "+ctitle if ctitle and ctitle!="nan" else "")+(" ("+cconfidence+" confidence)" if cconfidence not in ("","nan","low") else "")+"</div>" if contact_name else ""}
          {'<div style="font-size:0.73rem;background:#fef9c3;color:#854d0e;padding:4px 10px;border-radius:6px;margin:4px 0;">Directory — contains '+str(dir_count)+' companies</div>' if is_dir and dir_count > 0 else ''}
          {'<div style="font-size:0.73rem;background:#fee2e2;color:#991b1b;padding:4px 10px;border-radius:6px;margin:4px 0;">AI note: '+rejection+'</div>' if not is_valid and rejection and rejection!="nan" else ''}
          {'<div class="card-tags" style="margin-top:6px">'+extra_html+'</div>' if extra_html else ''}
          {'<div class="card-links">'+links_html+'</div>' if links_html else ''}
        </div>
        """, unsafe_allow_html=True)


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
            lambda g: ", ".join(GAP_LABELS.get(x,x) for x in g) if isinstance(g, list) else "")
    if "products" in display_df.columns:
        display_df["products"] = display_df["products"].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p, list) else str(p or ""))
    if "final_score" in display_df.columns:
        display_df["final_score"] = pd.to_numeric(display_df["final_score"], errors="coerce").round(3)
    if "created_at" in display_df.columns:
        display_df["created_at"] = pd.to_datetime(display_df["created_at"], errors="coerce").dt.strftime("%d %b %Y")
    display_df.rename(columns={c: ALL_COLUMNS.get(c, c) for c in display_df.columns}, inplace=True)

    st.dataframe(display_df, use_container_width=True, height=min(60 + len(display_df) * 36, 600))

    csv_df = df[vis].copy()
    for col in ["compliance_gaps","products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(lambda v: ", ".join(v) if isinstance(v, list) else str(v or ""))
    csv = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download as CSV", data=csv,
                       file_name=f"leads_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_{key_suffix}_{len(leads)}")


def _show_extracted_companies(companies: list, key_suffix: str = "", query: str = "") -> None:
    if not companies:
        st.info("No companies extracted yet.")
        return
    st.markdown(f"**{len(companies)} companies extracted**")
    rows = []
    for c in companies:
        rows.append({
            "Company": str(c.get("company","—")),
            "City":    str(c.get("city","—")),
            "Phone":   str(c.get("phone","—")),
            "Email":   str(c.get("email","—")),
            "Website": str(c.get("website","—")),
            "Products":str(c.get("products","—"))[:80],
            "About":   str(c.get("snippet","—"))[:100],
        })
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=min(60 + len(df)*36, 500))
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("Download All as CSV", data=csv,
                       file_name=f"directory_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_dir_{key_suffix}_{len(companies)}")
    if st.checkbox("Show as cards", key=f"cards_dir_{key_suffix}"):
        for ci, c in enumerate(companies):
            name    = str(c.get("company","Unknown"))
            city    = str(c.get("city",""))
            phone   = str(c.get("phone",""))
            email   = str(c.get("email",""))
            website = str(c.get("website",""))
            prods   = str(c.get("products",""))[:120]
            snippet = str(c.get("snippet",""))[:150]
            links = ""
            if website and website not in ("nan","—",""):
                links += f'<a class="card-link" href="{website}" target="_blank">Website</a>'
            if email and "@" in email:
                links += f'<a class="card-link" href="mailto:{email}">{email}</a>'
            if phone and phone not in ("nan","—",""):
                links += f'<span class="card-link">{phone}</span>'
            st.markdown(f"""
            <div class="result-card">
              <div class="card-company">{name}</div>
              <div class="card-meta">{"📍 "+city if city and city not in ("nan","—") else ""}</div>
              {"<div class='card-summary'>"+prods+"</div>" if prods and prods not in ("nan","—") else ""}
              {"<div class='card-summary' style='color:#6b7280'>"+snippet+"</div>" if snippet and snippet not in ("nan","—") else ""}
              {"<div class='card-links'>"+links+"</div>" if links else ""}
            </div>
            """, unsafe_allow_html=True)

# ===========================================================================
# COLLAPSED CELL + EXPAND
# ===========================================================================

def _card_id(row: dict, idx: int) -> str:
    return str(row.get("_id") or f"{str(row.get('company','?'))[:20]}_{idx}")


def _channel_emoji(ch: str) -> str:
    return {"Manufacturer":"🏭","Importer":"📦","Trader":"🤝",
            "Wholesaler":"🏪","Distributor":"🚚","Retailer":"🛍️"}.get(ch, "🏢")


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
            enriched["_research_signals"] = data.get("signals", [])
            enriched["_research_news"]    = data.get("sources", {}).get("news", [])[:3]
            enriched["_research_social"]  = data.get("social", {})
            enriched["_research_trade"]   = data.get("sources", {}).get("trade", [])[:2]
            return enriched
    except Exception:
        pass
    return row


def _render_card_list(leads: list, key_suffix: str = ""):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="icon">🔍</div>
          <h3>No results for these filters</h3>
          <p>Try removing some filters or searching with different keywords.</p>
        </div>
        """, unsafe_allow_html=True)
        return

    selected = st.session_state.get("selected_card")

    for idx, row in enumerate(leads):
        cid       = _card_id(row, idx)
        is_sel    = (selected == cid)
        company   = str(row.get("company", "Unknown"))
        city      = str(row.get("city", ""))
        country   = str(row.get("country_detected", ""))
        channel   = str(row.get("channel_type", ""))
        imp       = str(row.get("importance", "low"))
        score     = float(row.get("final_score", 0) or 0)
        gaps      = row.get("compliance_gaps", [])
        email     = str(row.get("email", ""))
        is_dir    = bool(row.get("is_directory", False))
        loc       = ", ".join(filter(None, [city, country]))
        emoji     = "📂" if is_dir else _channel_emoji(channel)
        has_email = " ·  email" if "@" in email else ""

        if isinstance(gaps, list) and gaps:
            gap_badge = '<span class="status-pill pill-gap">⚠ Issues</span>'
        else:
            gap_badge = '<span class="status-pill pill-clean">Clean</span>'

        imp_lower = imp.lower()
        if imp_lower == "high":
            imp_badge = '<span class="status-pill pill-high">High</span>'
        elif imp_lower == "medium":
            imp_badge = '<span class="status-pill pill-medium">Medium</span>'
        else:
            imp_badge = '<span class="status-pill pill-low">Low</span>'

        border_color = "#6366f1" if is_sel else "#e5e7eb"
        bg_color     = "#eef2ff" if is_sel else "#fff"

        st.markdown(f"""
        <div style="background:{bg_color};border:1.5px solid {border_color};border-radius:10px;
                    padding:11px 14px;margin-bottom:5px;cursor:pointer;">
          <div style="display:flex;align-items:center;gap:10px;">
            <div style="width:34px;height:34px;border-radius:8px;background:#f3f4f6;
                        display:flex;align-items:center;justify-content:center;
                        font-size:1rem;flex-shrink:0;">{emoji}</div>
            <div style="flex:1;min-width:0;">
              <div style="font-size:0.88rem;font-weight:600;color:#111827;
                          white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{company}</div>
              <div style="font-size:0.72rem;color:#6b7280;margin-top:1px;
                          white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">
                {"📍 "+loc+"  ·  " if loc else ""}{channel}{has_email}
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:5px;flex-shrink:0;">
              {imp_badge}
              {gap_badge}
              <span class="score-badge">{score:.2f}</span>
            </div>
          </div>
        </div>
        """, unsafe_allow_html=True)

        btn_label = "Close" if is_sel else "Open →"
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


def _safe(v: str) -> str:
    return "" if str(v).strip().lower() in ("nan", "none", "") else str(v).strip()


def _render_detail_panel(cid: str):
    row = st.session_state.card_details.get(cid)
    if not row:
        st.markdown("""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;min-height:260px;
                    border:1.5px dashed #e5e7eb;border-radius:12px;
                    background:#fff;text-align:center;padding:40px 20px;">
          <p style="color:#9ca3af;font-size:0.83rem;margin:0;line-height:1.5;">
            Select a company on the left to see full details here.
          </p>
        </div>
        """, unsafe_allow_html=True)
        return

    company   = _safe(row.get("company", ""))   or "Unknown"
    city      = _safe(row.get("city", ""))
    country   = _safe(row.get("country_detected", ""))
    industry  = _safe(row.get("industry_detected", ""))
    channel   = _safe(row.get("channel_type", ""))
    score     = float(row.get("final_score", 0) or 0)
    imp       = _safe(row.get("importance", "low")) or "low"
    gaps      = row.get("compliance_gaps", []) or []
    email     = _safe(row.get("email", ""))
    phone     = _safe(row.get("phone", ""))
    website   = _safe(row.get("active_website", row.get("website", "")))
    linkedin  = _safe(row.get("linkedin_url", ""))
    summary   = _safe(row.get("ai_summary", ""))
    products  = row.get("products", []) or []
    size      = _safe(row.get("company_size", ""))
    founded   = _safe(row.get("incorporation_date", ""))
    turnover  = _safe(row.get("annual_turnover", ""))
    certs     = [x for x in (row.get("certifications") or []) if _safe(str(x))]
    exports   = [x for x in (row.get("export_markets") or []) if _safe(str(x))]
    usp       = _safe(row.get("usp", ""))
    key_cust  = [x for x in (row.get("key_customers") or []) if _safe(str(x))]
    contact   = _safe(row.get("contact_person", ""))
    c_title   = _safe(row.get("contact_title", ""))
    c_conf    = _safe(row.get("contact_confidence", ""))
    c_email   = _safe(row.get("contact_email", ""))
    is_dir    = bool(row.get("is_directory", False))
    dir_cos   = row.get("directory_companies", []) or []
    dir_count = int(row.get("directory_count", 0) or 0)
    is_valid  = bool(row.get("is_valid_lead", True))
    rejection = _safe(row.get("rejection_reason", ""))
    signals   = [x for x in (row.get("_research_signals") or []) if _safe(str(x))]
    news      = row.get("_research_news") or []
    social_r  = row.get("_research_social") or {}

    loc      = ", ".join(filter(None, [city, country]))
    prod_str = "  ·  ".join(str(p) for p in products[:8] if _safe(str(p)))

    imp_lower = imp.lower()
    if imp_lower == "high":
        imp_badge = '<span class="status-pill pill-high">High</span>'
    elif imp_lower == "medium":
        imp_badge = '<span class="status-pill pill-medium">Medium</span>'
    else:
        imp_badge = '<span class="status-pill pill-low">Low</span>'

    tag_items = [t for t in [industry, channel, size,
                              f"Est. {founded}" if founded else ""] if t]
    if turnover:
        tags_html = "".join(f'<span class="card-tag">{t}</span>' for t in tag_items)
        tags_html += f'<span class="card-tag">{turnover}</span>'
    else:
        tags_html = "".join(f'<span class="card-tag">{t}</span>' for t in tag_items)

    if isinstance(gaps, list) and gaps:
        gap_html = " ".join(f'<span class="status-pill pill-gap" style="margin-right:4px;margin-bottom:4px;">⚠ {GAP_LABELS.get(g,g)}</span>' for g in gaps)
    else:
        gap_html = '<span class="status-pill pill-clean">No compliance issues</span>'

    links_parts = []
    if website:
        links_parts.append(f'<a href="{website}" target="_blank" class="detail-link">Website</a>')
    if email and "@" in email:
        links_parts.append(f'<a href="mailto:{email}" class="detail-link">{email}</a>')
    if phone:
        links_parts.append(f'<span class="detail-link">{phone}</span>')
    if linkedin:
        links_parts.append(f'<a href="{linkedin}" target="_blank" class="detail-link">LinkedIn</a>')
    for field, label in [("twitter_url","X"),("facebook_url","Facebook"),
                         ("instagram_url","Instagram"),("youtube_url","YouTube"),
                         ("whatsapp_url","WhatsApp")]:
        v = _safe(str(row.get(field,"")))
        if v:
            links_parts.append(f'<a href="{v}" target="_blank" class="detail-link">{label}</a>')
    for plat, label in [("linkedin","LinkedIn"),("twitter","X"),("facebook","Facebook"),
                        ("instagram","Instagram"),("youtube","YouTube")]:
        v = _safe(str(social_r.get(plat,"")))
        if v and not _safe(str(row.get(plat+"_url",""))):
            links_parts.append(f'<a href="{v}" target="_blank" class="detail-link">{label}</a>')
    links_html = "".join(links_parts)

    def section(title: str, content: str) -> str:
        return (f'<div class="detail-section">{title}</div>'
                f'<div class="detail-body">{content}</div>')

    html_parts = []
    html_parts.append(f"""
    <div class="detail-card">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;
                  gap:10px;flex-wrap:wrap;margin-bottom:6px;">
        <div style="flex:1;min-width:0;">
          <div class="detail-title">{company}</div>
          <div class="detail-sub">
            {"📍 "+loc+"  ·  " if loc else ""}{(channel+" "+_channel_emoji(channel)) if channel else ""}
          </div>
        </div>
        <div style="display:flex;gap:5px;align-items:center;flex-wrap:wrap;justify-content:flex-end;">
          {imp_badge}
          <span class="score-badge">{score:.2f}</span>
          {"<span class='status-pill' style='background:#fdf4ff;color:#7e22ce;border:1px solid #e9d5ff'>Directory</span>" if is_dir else ""}
        </div>
      </div>
    """)

    if tags_html:
        html_parts.append(f'<div class="card-tags" style="margin:6px 0 0">{tags_html}</div>')
    if summary:
        html_parts.append(section("About", summary))
    if usp:
        html_parts.append(section("Unique Selling Point", f"<em>{usp}</em>"))
    if prod_str:
        html_parts.append(section("Products & Services", prod_str))
    if contact:
        conf_badge = (f' ({c_conf} confidence)' if c_conf not in ("","low") else "")
        contact_html = f'<strong>{contact}</strong>'
        if c_title: contact_html += f'  —  {c_title}'
        contact_html += conf_badge
        if c_email and "@" in c_email and c_email != email:
            contact_html += f'<br>{c_email}'
        html_parts.append(section("Key Contact", contact_html))

    html_parts.append(section("Compliance", gap_html))
    if certs:
        html_parts.append(section("Certifications", " · ".join(certs[:8])))
    if exports:
        html_parts.append(section("Export Markets", " · ".join(exports[:6])))
    if key_cust:
        html_parts.append(section("Key Customers", " · ".join(key_cust[:4])))
    if signals:
        html_parts.append(section("Intelligence Signals", "  ".join(signals)))
    if news:
        news_html = "<br>".join(
            f'<a href="{n.get("url","#")}" target="_blank" class="detail-link">{str(n.get("title",""))[:70]}</a>'
            for n in news[:3] if n.get("title"))
        if news_html:
            html_parts.append(section("Recent News", news_html))
    if not is_valid and rejection:
        html_parts.append(
            f'<div style="background:#fff1f2;border:1px solid #fecdd3;border-radius:7px;'
            f'padding:8px 12px;font-size:0.77rem;color:#be123c;margin-top:12px;">AI note: {rejection}</div>')
    if links_html:
        html_parts.append(
            f'<div class="detail-links" style="margin-top:14px;padding-top:12px;border-top:1px solid #f3f4f6">{links_html}</div>')

    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

    # Directory section
    if is_dir:
        st.markdown(
            f'<div style="background:#faf5ff;border:1px solid #e9d5ff;border-radius:8px;'
            f'padding:10px 14px;margin-top:8px;font-size:0.82rem;color:#7e22ce;">'
            f'Directory page — lists ~{dir_count} companies inside</div>',
            unsafe_allow_html=True)

        if dir_cos:
            st.markdown(f"**{len(dir_cos)} companies extracted:**")
            dir_html_parts = []
            for c in dir_cos[:30]:
                c_name = _safe(str(c.get("company",""))) or "—"
                c_city = _safe(str(c.get("city","")))
                c_em   = _safe(str(c.get("email","")))
                c_web  = _safe(str(c.get("website","")))
                c_prod = _safe(str(c.get("products","")))[:60]
                lnk = ""
                if c_web:
                    lnk += f' <a href="{c_web}" target="_blank" class="detail-link">Web</a>'
                if c_em and "@" in c_em:
                    lnk += f' <a href="mailto:{c_em}" class="detail-link">Email</a>'
                loc_str = f"  ·  📍{c_city}" if c_city else ""
                prod_str_c = f'<br><span style="color:#6b7280;">{c_prod}</span>' if c_prod else ""
                dir_html_parts.append(
                    f'<div class="detail-dir-item">'
                    f'<strong>{c_name}</strong>{loc_str}{lnk}{prod_str_c}</div>'
                )
            st.markdown("".join(dir_html_parts), unsafe_allow_html=True)
            if len(dir_cos) > 30:
                st.caption(f"…and {len(dir_cos)-30} more")
            df_dir = pd.DataFrame([{
                "Company":c.get("company",""), "City":c.get("city",""),
                "Phone":c.get("phone",""), "Email":c.get("email",""),
                "Website":c.get("website",""), "Products":c.get("products",""),
            } for c in dir_cos])
            st.download_button("Download all as CSV",
                               data=df_dir.to_csv(index=False).encode("utf-8"),
                               file_name=f"dir_{cid[:8]}.csv", mime="text/csv",
                               key=f"dl_det_dir_{cid}")
        else:
            if st.button("Extract all companies from directory",
                         key=f"det_extract_{cid}", type="primary",
                         use_container_width=True):
                with st.spinner("Extracting with AI… 30–60 seconds"):
                    try:
                        r = _api_post("/leads/extract-directory",
                                      json={"website": website,
                                            "content": row.get("content",""),
                                            "query": st.session_state.active_query},
                                      timeout=120)
                        if r.status_code == 200:
                            cos = r.json().get("companies", [])
                            updated = dict(st.session_state.card_details.get(cid, row))
                            updated["directory_companies"] = cos
                            st.session_state.card_details[cid] = updated
                            st.success(f"Extracted {len(cos)} companies!")
                            st.rerun()
                        else:
                            st.error(f"Extraction failed: {r.text}")
                    except Exception as e:
                        st.error(str(e))


# ===========================================================================
# _show_results — master-detail layout
# ===========================================================================
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

    filtered  = _apply_filters(leads)
    count_txt = (f"{len(filtered)} of {len(leads)} companies"
                 if len(filtered) != len(leads) else f"{len(leads)} companies")

    hc1, hc2 = st.columns([4, 1])
    with hc1:
        st.caption(f"Showing **{count_txt}** · Click **Open →** to view details")
    with hc2:
        view = st.radio("View", ["Cards", "Table"], horizontal=True,
                        key=f"view_{key_suffix}",
                        index=0 if st.session_state.view_mode == "Cards" else 1)
        st.session_state.view_mode = view

    if view == "Table":
        _show_table(filtered, key_suffix=key_suffix)
        return

    selected_cid = st.session_state.get("selected_card")
    show_detail  = (
        selected_cid is not None
        and selected_cid in st.session_state.card_details
        and st.session_state.get("selected_tab", "") == key_suffix
    )

    if show_detail:
        col_left, col_right = st.columns([2, 3], gap="medium")
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
                    lambda v: ", ".join(str(x) for x in v) if isinstance(v, list) else str(v or ""))
        st.download_button(
            "Export as CSV",
            data=df_exp.to_csv(index=False).encode("utf-8"),
            file_name=f"leads_{key_suffix}.csv", mime="text/csv",
            key=f"dl_exp_{key_suffix}_{len(filtered)}"
        )


# ===========================================================================
# RESULTS SECTION
# ===========================================================================
if company_leads:
    st.markdown("---")
    _show_metrics(company_leads)
    st.markdown("<br>", unsafe_allow_html=True)

    tab_all, tab_high, tab_gaps, tab_mfg, tab_imp, tab_trade, tab_dir = st.tabs([
        f"All ({len(company_leads)})",
        "High Priority",
        "Compliance Issues",
        "Manufacturers",
        "Importers",
        "Traders & Distributors",
        "Directories",
    ])

    with tab_all:
        _show_results(company_leads, "all")

    with tab_high:
        st.caption("Companies most likely to be a good fit based on your search")
        high_leads = [x for x in company_leads if str(x.get("importance","")).lower() == "high"]
        _show_results(high_leads, "high")

    with tab_gaps:
        st.markdown("""
        <div class="info-box">
          These companies have <strong>missing licences or registrations</strong>
          (BIS, GST, IEC, MCA). They may need compliance services — great sales prospects.
        </div>
        """, unsafe_allow_html=True)
        gap_leads = [x for x in company_leads
                     if isinstance(x.get("compliance_gaps"), list) and len(x["compliance_gaps"]) > 0]
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
                       if x.get("channel_type") in ("Trader","Distributor","Wholesaler","Retailer")]
        _show_results(trade_leads, "trade")

    with tab_dir:
        st.markdown("#### Directories")
        st.caption(
            "When AI detects a page that lists multiple companies, it appears here. "
            "Expand any directory card to extract all companies inline."
        )

        dir_leads = [x for x in company_leads if x.get("is_directory")]

        with st.expander("Manually scan a directory URL", expanded=False):
            manual_url   = st.text_input("Paste a directory URL",
                                          placeholder="https://www.indiamart.com/proddetail/...",
                                          key="manual_dir_url")
            manual_query = st.text_input("What kind of companies are listed here?",
                                          placeholder="electronics importers india",
                                          key="manual_dir_query")
            if st.button("Scan this URL", key="manual_dir_btn", type="primary"):
                if manual_url:
                    with st.spinner("Scanning directory…"):
                        try:
                            r = _api_post("/leads/extract-directory",
                                json={"website": manual_url, "content": "",
                                      "query": manual_query or st.session_state.active_query},
                                timeout=90)
                            if r.status_code == 200:
                                res = r.json()
                                st.session_state["manual_dir_result"] = res
                                st.session_state["manual_dir_url_done"] = manual_url
                            else:
                                st.error(f"Scan failed: {r.text}")
                        except Exception as e:
                            st.error(f"Cannot reach server: {e}")

            if st.session_state.get("manual_dir_result"):
                res       = st.session_state["manual_dir_result"]
                found     = res.get("extracted", 0)
                saved_n   = res.get("saved", 0)
                companies = res.get("companies", [])
                st.success(f"Found **{found}** companies, saved **{saved_n}** as leads")
                if companies:
                    _show_extracted_companies(companies,
                        key_suffix="manual",
                        query=manual_query or st.session_state.active_query)

        if not dir_leads:
            st.markdown("""
            <div style="background:#fffbeb;border:1px solid #fde68a;border-radius:8px;
                 padding:14px 18px;font-size:0.83rem;color:#92400e">
              No directories detected yet. Try searching for terms like
              <em>electronics importers list india</em> or <em>manufacturers directory Gujarat</em>.
              Or paste any directory URL in the scanner above.
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown(f"**{len(dir_leads)} director{'y' if len(dir_leads)==1 else 'ies'} found**")
            _show_results(dir_leads, "dir")

    linkedin_leads = [x for x in raw_leads if x.get("source") == "linkedin_semantic"]
    if linkedin_leads:
        with st.expander(f"LinkedIn Contacts ({len(linkedin_leads)})"):
            ld   = pd.DataFrame(linkedin_leads)
            cols = ["name","profile","snippet","searched_query","created_at"]
            st.dataframe(ld[[c for c in cols if c in ld.columns]], use_container_width=True)

    st.markdown("---")
    with st.expander("Check Licences & Registrations (BIS, GST, IEC, MCA)", expanded=False):
        st.markdown("""
        Automatically check which companies are missing important Indian business registrations.
        Companies with missing licences are highlighted — these are high-value prospects.
        """)
        n        = st.slider("How many companies to check?", 5, 100, 20, key="enrich_n")
        cf_enrich = "" if st.session_state.sf_country == "Any Country" \
                    else st.session_state.sf_country.lower()
        if st.button("Start Checking", key="enrich_btn", type="primary"):
            with st.spinner("Checking registrations… this takes 1-2 minutes"):
                try:
                    r = _api_post("/leads/enrich-compliance",
                        params={"limit": n, "country_filter": cf_enrich},
                        timeout=300)
                    if r.status_code == 200:
                        st.success(f"Checked {r.json().get('checked',0)} companies. Refresh to see results.")
                    else:
                        st.error("Check failed.")
                except Exception as e:
                    st.error(str(e))

elif not st.session_state.active_job_id:
    st.markdown("""
    <div class="empty-state" style="margin-top:48px">
      <div class="icon">🌐</div>
      <h3>Ready to find leads</h3>
      <p>Type what kind of business you're looking for in the search bar above.<br>
         For example: <em>"electronics importers Gujarat"</em> or <em>"pharma manufacturers Mumbai"</em></p>
    </div>
    """, unsafe_allow_html=True)
