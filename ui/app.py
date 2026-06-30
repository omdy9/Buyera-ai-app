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
    page_title="Buyera — B2B Lead Discovery",
    layout="wide",
    initial_sidebar_state="expanded",
    page_icon="🎯",
)

# ---------------------------------------------------------------------------
# DESIGN SYSTEM
# Palette: slate-50 page, white cards, blue-600 accent, slate ink text
# Signature element: score ring on each lead card
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:ital,wght@0,400;0,500;0,600;0,700;1,400&display=swap');

/* ── Reset ── */
*, *::before, *::after { box-sizing: border-box; }

html, body, .stApp {
    font-family: 'Inter', system-ui, sans-serif;
    font-size: 17px;
    background: #F1F5F9;
    color: #0F172A;
    line-height: 1.55;
}

/* ── Hide Streamlit chrome ──
   IMPORTANT: do NOT hide the whole <header> — the sidebar's
   expand/collapse arrow lives inside it. Hiding header entirely
   makes the sidebar unrecoverable once collapsed (no way to
   reopen it). Only hide the specific decorative bits instead. */
#MainMenu, footer, [data-testid="stToolbar"],
[data-testid="stDecoration"] { display: none !important; }

/* Keep header present (so the sidebar toggle still works) but
   make it visually blend in instead of showing Streamlit's bar.
   IMPORTANT: do NOT set height:auto here — Streamlit positions its
   sidebar collapse/expand toggle button using the header's natural
   fixed height. Collapsing that height breaks the toggle's position
   and can leave the sidebar stuck at 0 width with no way to reopen it. */

header[data-testid="stHeader"] {
    background: transparent !important;
    z-index: 998 !important;
}

/* ─────────────────────────────────────────

   SIDEBAR

   NOTE: collapsing is intentionally disabled. Every attempt to make

   it collapsible (fighting aria-expanded, then a custom display

   toggle) ran into Streamlit internals that vary by version and left

   the panel hidden/empty with no reliable way back. Locking it open

   removes the failure mode entirely — there is nothing to "reopen"

   because it can never close.

───────────────────────────────────────── */

[data-testid="stSidebar"] {

    display: flex !important;

    flex-direction: column !important;

    background: #0F172A !important;

    border-right: none !important;

    min-width: 21rem !important;

    width: 21rem !important;

    visibility: visible !important;

    transform: none !important;

}

[data-testid="stSidebar"] > div:first-child {

    padding: 0 !important;

}

/* Hide Streamlit's native collapse arrow so it can't be triggered

   accidentally and put the sidebar back into a broken state. */

[data-testid="collapsedControl"],

[data-testid="stSidebarCollapsedControl"] {

    display: none !important;

}

/* Sidebar text universally light */

/* Sidebar text universally light */

[data-testid="stSidebar"] *:not(button) {

    color: #CBD5E1 !important;

}

[data-testid="stSidebar"] label,

[data-testid="stSidebar"] [data-testid="stWidgetLabel"] p {

    font-size: 0.68rem !important;

    font-weight: 600 !important;

    letter-spacing: 0.07em !important;

    text-transform: uppercase !important;

    color: #64748B !important;

}

/* Sidebar inputs */

[data-testid="stSidebar"] .stTextInput input,
[data-testid="stSidebar"] .stSelectbox > div > div,
[data-testid="stSidebar"] [data-baseweb="select"] > div {
    background: #1E293B !important;
    border: 1px solid #334155 !important;
    color: #E2E8F0 !important;
    border-radius: 6px !important;
    font-size: 0.82rem !important;
}

/* Sidebar checkboxes */
[data-testid="stSidebar"] .stCheckbox label span { color: #CBD5E1 !important; font-size: 0.82rem !important; }
[data-testid="stSidebar"] .stCheckbox [data-testid="stWidgetLabel"] p { color: #CBD5E1 !important; text-transform: none !important; letter-spacing: 0 !important; font-size: 0.82rem !important; }

/* Sidebar slider */
[data-testid="stSidebar"] .stSlider [data-testid="stWidgetLabel"] p { color: #64748B !important; }

/* Sidebar selectbox dropdown */
[data-testid="stSidebar"] div[data-baseweb="select"] span,
[data-testid="stSidebar"] [class*="singleValue"] { color: #E2E8F0 !important; }

/* Dropdown menus — white by default (main content) */
ul[role="listbox"], [data-baseweb="popover"] > div, [data-baseweb="menu"] > div {
    background: #fff !important;
    border: 1px solid #E2E8F0 !important;
    border-radius: 8px !important;
    box-shadow: 0 8px 24px rgba(0,0,0,0.10) !important;
}
[role="option"] { background: #fff !important; color: #0F172A !important; }
[role="option"]:hover, [aria-selected="true"][role="option"] {
    background: #EFF6FF !important; color: #2563EB !important;
}
[role="option"] * { color: inherit !important; }
/* Sidebar dropdowns stay dark */
[data-testid="stSidebar"] ul[role="listbox"],
[data-testid="stSidebar"] [data-baseweb="popover"] > div,
[data-testid="stSidebar"] [data-baseweb="menu"] > div {
    background: #1E293B !important;
    border-color: #334155 !important;
    box-shadow: 0 12px 32px rgba(0,0,0,0.4) !important;
}
[data-testid="stSidebar"] [role="option"] { background: #1E293B !important; color: #CBD5E1 !important; }
[data-testid="stSidebar"] [role="option"]:hover,
[data-testid="stSidebar"] [aria-selected="true"][role="option"] {
    background: #2563EB !important; color: #fff !important;
}

/* Sidebar brand block */
.sb-brand {
    padding: 22px 20px 18px;
    border-bottom: 1px solid #1E293B;
    margin-bottom: 8px;
}
.sb-logo {
    font-size: 1.25rem;
    font-weight: 700;
    color: #F8FAFC !important;
    letter-spacing: -0.04em;
}
.sb-logo em { color: #3B82F6 !important; font-style: normal; }
.sb-user-pill {
    display: inline-block;
    margin-top: 6px;
    font-size: 0.7rem;
    background: #1E293B;
    color: #94A3B8 !important;
    padding: 3px 10px;
    border-radius: 20px;
    border: 1px solid #334155;
}
.sb-section {
    font-size: 0.62rem;
    font-weight: 700;
    color: #475569 !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    padding: 16px 20px 6px;
}

/* Sidebar buttons */
[data-testid="stSidebar"] .stButton > button {
    background: #1E293B !important;
    color: #CBD5E1 !important;
    border: 1px solid #334155 !important;
    border-radius: 7px !important;
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    padding: 7px 14px !important;
    width: 100% !important;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #3B82F6 !important;
    color: #60A5FA !important;
}

/* ─────────────────────────────────────────
   MAIN CONTENT
───────────────────────────────────────── */
.block-container {
    padding: 0 2rem 2rem !important;
    max-width: 100% !important;
}

/* ── Page header ── */
.page-header {
    background: #fff;
    border-bottom: 1px solid #E2E8F0;
    padding: 18px 0 16px;
    margin: 0 -2rem 24px;
    padding-left: 2rem;
    padding-right: 2rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    position: sticky;
    top: 0;
    z-index: 200;
}
.ph-brand {
    font-size: 1.1rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.04em;
}
.ph-brand em { color: #2563EB; font-style: normal; }
.ph-actions {
    display: flex;
    align-items: center;
    gap: 10px;
}
.ph-user {
    font-size: 0.75rem;
    color: #64748B;
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
    padding: 5px 12px;
    border-radius: 20px;
    font-weight: 500;
}

/* ── Search section ── */
.search-hero {
    padding: 8px 0 20px;
}
.search-eyebrow {
    font-size: 0.68rem;
    font-weight: 700;
    color: #2563EB;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    margin-bottom: 6px;
}
.search-headline {
    font-size: 1.6rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.04em;
    line-height: 1.2;
    margin-bottom: 6px;
}
.search-sub {
    font-size: 0.82rem;
    color: #64748B;
    margin-bottom: 18px;
}

/* Search input */
.stTextInput input {
    border: 1.5px solid #E2E8F0 !important;
    border-radius: 9px !important;
    font-size: 0.92rem !important;
    padding: 11px 16px !important;
    background: #fff !important;
    color: #0F172A !important;
    -webkit-text-fill-color: #0F172A !important;
    box-shadow: 0 1px 4px rgba(0,0,0,0.04) !important;
    transition: border-color 0.15s, box-shadow 0.15s !important;
}
.stTextInput input:focus {
    border-color: #2563EB !important;
    box-shadow: 0 0 0 3px rgba(37,99,235,0.1) !important;
}
.stTextInput input::placeholder {
    color: #94A3B8 !important;
    -webkit-text-fill-color: #94A3B8 !important;
}

/* Suggestion chips */
.chips-row {
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-top: 12px;
    margin-bottom: 18px;
}
.chip {
    font-size: 0.72rem;
    font-weight: 500;
    color: #3B82F6;
    background: #EFF6FF;
    border: 1px solid #BFDBFE;
    padding: 4px 11px;
    border-radius: 20px;
    cursor: default;
}

/* Always-visible pre-search filter row */
.presearch-label {
    font-size: 0.66rem;
    font-weight: 700;
    color: #64748B;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
    display: flex;
    align-items: center;
    gap: 6px;
}
.presearch-row {
    background: #fff;
    border: 1.5px solid #E2E8F0;
    border-radius: 10px;
    padding: 14px 16px 4px;
    margin-bottom: 18px;
}

/* ── Animations ── */
@keyframes slideInRight {
    from { opacity: 0; transform: translateX(18px); }
    to   { opacity: 1; transform: translateX(0); }
}
@keyframes fadeIn {
    from { opacity: 0; }
    to   { opacity: 1; }
}

/* ── Buttons — base (main content) ── */
.stButton > button {
    font-family: 'Inter', sans-serif !important;
    font-size: 0.82rem !important;
    font-weight: 600 !important;
    border-radius: 8px !important;
    padding: 9px 18px !important;
    transition: all 0.12s !important;
    border: 1.5px solid #E2E8F0 !important;
    background: #fff !important;
    color: #374151 !important;
}
.stButton > button:hover {
    border-color: #2563EB !important;
    color: #2563EB !important;
    background: #EFF6FF !important;
}
/* Streamlit native primary button — works for st.button(type="primary")
   and st.form_submit_button(type="primary") */
[data-testid="baseButton-primary"],
[data-testid="baseButton-primaryFormSubmit"],
button[kind="primary"],
button[kind="primaryFormSubmit"] {
    background: #2563EB !important;
    color: #fff !important;
    border: 1.5px solid #2563EB !important;
    box-shadow: 0 1px 6px rgba(37,99,235,0.28) !important;
    font-weight: 600 !important;
}
[data-testid="baseButton-primary"]:hover,
[data-testid="baseButton-primaryFormSubmit"]:hover,
button[kind="primary"]:hover,
button[kind="primaryFormSubmit"]:hover {
    background: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: #fff !important;
}
/* Legacy markdown-wrapper fallback (kept for compatibility) */
.btn-primary .stButton > button {
    background: #2563EB !important;
    color: #fff !important;
    border-color: #2563EB !important;
    box-shadow: 0 1px 6px rgba(37,99,235,0.3) !important;
}
.btn-primary .stButton > button:hover {
    background: #1D4ED8 !important;
    border-color: #1D4ED8 !important;
    color: #fff !important;
}

/* ── Tabs ── */
[data-testid="stTabs"] [role="tablist"] {
    background: transparent !important;
    border-bottom: 2px solid #E2E8F0 !important;
    gap: 0 !important;
    padding: 0 !important;
}
[data-testid="stTabs"] [role="tab"] {
    font-size: 0.78rem !important;
    font-weight: 500 !important;
    color: #64748B !important;
    padding: 8px 16px !important;
    border-radius: 0 !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    margin-bottom: -2px;
}
[data-testid="stTabs"] [role="tab"][aria-selected="true"] {
    color: #2563EB !important;
    border-bottom-color: #2563EB !important;
    font-weight: 600 !important;
}

/* ── Selectbox ── */
.stSelectbox > div > div,
div[data-baseweb="select"] > div {
    border: 1.5px solid #E2E8F0 !important;
    border-radius: 8px !important;
    background: #fff !important;
    font-size: 0.82rem !important;
    color: #0F172A !important;
}
div[data-baseweb="select"] span,
[class*="singleValue"],
div[data-baseweb="select"] input {
    color: #0F172A !important;
    -webkit-text-fill-color: #0F172A !important;
}

/* ── Metrics ── */
[data-testid="metric-container"] {
    background: #fff !important;
    border: 1px solid #E8EAED !important;
    border-radius: 12px !important;
    padding: 16px 20px !important;
}
[data-testid="stMetricValue"] {
    font-size: 1.75rem !important;
    font-weight: 700 !important;
    color: #0F172A !important;
    letter-spacing: -0.03em !important;
}
[data-testid="stMetricLabel"] {
    font-size: 0.68rem !important;
    color: #94A3B8 !important;
    text-transform: uppercase !important;
    letter-spacing: 0.07em !important;
    font-weight: 600 !important;
}
[data-testid="stMetricDelta"] { display: none !important; }

/* ── Status banners ── */
.banner-info {
    background: #EFF6FF;
    border-left: 3px solid #3B82F6;
    border-radius: 0 8px 8px 0;
    padding: 11px 16px;
    font-size: 0.8rem;
    color: #1E40AF;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.banner-warn {
    background: #FFFBEB;
    border-left: 3px solid #F59E0B;
    border-radius: 0 8px 8px 0;
    padding: 11px 16px;
    font-size: 0.8rem;
    color: #92400E;
    margin-bottom: 12px;
}
.banner-success {
    background: #F0FDF4;
    border-left: 3px solid #22C55E;
    border-radius: 0 8px 8px 0;
    padding: 11px 16px;
    font-size: 0.8rem;
    color: #14532D;
    margin-bottom: 12px;
}

/* ── Lead cards ── */
.lead-card {
    background: #fff;
    border: 1.5px solid #E8EAED;
    border-radius: 10px;
    padding: 12px 16px;
    margin-bottom: 6px;
    display: grid;
    grid-template-columns: 42px 1fr auto;
    align-items: center;
    gap: 12px;
    cursor: pointer;
    transition: border-color 0.15s ease, box-shadow 0.15s ease, background 0.15s ease;
    position: relative;
    animation: fadeIn 0.18s ease both;
}
.lead-card:hover {
    border-color: #93C5FD;
    box-shadow: 0 2px 12px rgba(37,99,235,0.07);
}
.lead-card.active {
    border-color: #2563EB;
    background: #F0F7FF;
    box-shadow: 0 2px 14px rgba(37,99,235,0.13);
}
/* Score ring — the signature element */
.score-ring {
    width: 42px;
    height: 42px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
    position: relative;
}
.score-ring.high   { background: #DCFCE7; color: #15803D; border: 2px solid #86EFAC; }
.score-ring.medium { background: #FEF9C3; color: #854D0E; border: 2px solid #FDE047; }
.score-ring.low    { background: #F1F5F9; color: #64748B; border: 2px solid #CBD5E1; }
.lc-body { min-width: 0; }
.lc-name {
    font-size: 0.86rem;
    font-weight: 600;
    color: #0F172A;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    margin-bottom: 3px;
}
.lc-meta {
    font-size: 0.7rem;
    color: #94A3B8;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
.lc-badges { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; }

/* ── Badges ── */
.badge {
    display: inline-flex;
    align-items: center;
    padding: 2px 8px;
    border-radius: 20px;
    font-size: 0.65rem;
    font-weight: 600;
    white-space: nowrap;
    letter-spacing: 0.02em;
}
.b-high    { background: #DCFCE7; color: #15803D; }
.b-medium  { background: #FEF9C3; color: #92400E; }
.b-low     { background: #F1F5F9; color: #64748B; }
.b-gap     { background: #FEE2E2; color: #B91C1C; }
.b-clean   { background: #F0FDF4; color: #15803D; }
.b-dir     { background: #F5F3FF; color: #6D28D9; }
.b-channel { background: #F0F9FF; color: #0369A1; }

/* ── Detail panel ── */
.detail-panel {
    background: #fff;
    border: 1.5px solid #E2E8F0;
    border-radius: 12px;
    padding: 22px;
    position: sticky;
    top: 80px;
    max-height: calc(100vh - 120px);
    overflow-y: auto;
    scrollbar-width: thin;
    scrollbar-color: #E2E8F0 transparent;
    animation: slideInRight 0.22s cubic-bezier(0.22,1,0.36,1) both;
}
.detail-panel::-webkit-scrollbar { width: 3px; }
.detail-panel::-webkit-scrollbar-thumb { background: #E2E8F0; border-radius: 3px; }

.dp-empty {
    background: #fff;
    border: 1.5px dashed #E2E8F0;
    border-radius: 12px;
    padding: 56px 24px;
    text-align: center;
}
.dp-empty-icon { font-size: 2.2rem; margin-bottom: 10px; }
.dp-empty-text { font-size: 0.8rem; color: #94A3B8; line-height: 1.6; }

.dp-company-name {
    font-size: 1.05rem;
    font-weight: 700;
    color: #0F172A;
    letter-spacing: -0.02em;
    margin-bottom: 3px;
    word-break: break-word;
    overflow-wrap: anywhere;
    line-height: 1.3;
}
.dp-location {
    font-size: 0.76rem;
    color: #64748B;
    margin-bottom: 14px;
}
.dp-tags { display: flex; flex-wrap: wrap; gap: 5px; margin-bottom: 16px; }
.dp-tag {
    font-size: 0.68rem;
    font-weight: 500;
    background: #F8FAFC;
    color: #475569;
    border: 1px solid #E2E8F0;
    padding: 2px 8px;
    border-radius: 5px;
}
.dp-tag-green { background: #F0FDF4 !important; color: #15803D !important; border-color: #BBF7D0 !important; }
.dp-section-label {
    font-size: 0.62rem;
    font-weight: 700;
    color: #94A3B8;
    text-transform: uppercase;
    letter-spacing: 0.09em;
    margin: 18px 0 6px;
    padding-top: 14px;
    border-top: 1px solid #F1F5F9;
}
.dp-section-label:first-of-type { margin-top: 0; padding-top: 0; border-top: none; }
.dp-body {
    font-size: 0.8rem;
    color: #374151;
    line-height: 1.65;
}
.dp-links {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 18px;
    padding-top: 14px;
    border-top: 1px solid #F1F5F9;
}
.dp-link {
    font-size: 0.75rem;
    font-weight: 600;
    color: #2563EB;
    text-decoration: none;
    padding: 4px 10px;
    background: #EFF6FF;
    border-radius: 6px;
}
.dp-link:hover { background: #DBEAFE; }

/* ── Dir row ── */
.dir-item {
    background: #F8FAFC;
    border: 1px solid #E8EAED;
    border-radius: 7px;
    padding: 8px 12px;
    margin-bottom: 4px;
    font-size: 0.76rem;
    color: #374151;
}
.dir-item strong { color: #0F172A; }

/* ── Empty states ── */
.empty-state {
    text-align: center;
    padding: 64px 20px;
    color: #94A3B8;
}
.empty-icon { font-size: 2.5rem; margin-bottom: 12px; }
.empty-title { font-size: 0.95rem; font-weight: 600; color: #64748B; margin-bottom: 4px; }
.empty-desc  { font-size: 0.78rem; }

/* ── Expander ── */
[data-testid="stExpander"] {
    background: #fff !important;
    border: 1.5px solid #E8EAED !important;
    border-radius: 10px !important;
}
[data-testid="stExpander"] summary,
[data-testid="stExpander"] summary p {
    font-size: 0.84rem !important;
    font-weight: 600 !important;
    color: #0F172A !important;
}

/* ── Dataframe ── */
[data-testid="stDataFrame"] { border-radius: 10px !important; overflow: hidden !important; }
[data-testid="stDataFrame"] th { font-size: 0.72rem !important; color: #64748B !important; font-weight: 600 !important; }
[data-testid="stDataFrame"] td { font-size: 0.78rem !important; color: #0F172A !important; }

/* ── Alerts ── */
.stAlert { border-radius: 8px !important; }

/* ── Download ── */
.stDownloadButton > button {
    background: #F8FAFC !important;
    color: #374151 !important;
    border: 1.5px solid #E2E8F0 !important;
    font-size: 0.78rem !important;
    border-radius: 8px !important;
}
.stDownloadButton > button:hover { border-color: #2563EB !important; color: #2563EB !important; }

/* ── Slider ── */
.stSlider [data-testid="stThumbValue"],
.stSlider [data-baseweb="slider"] [role="slider"] { background: #2563EB !important; }

/* ── Radio ── */
.stRadio > div label p { font-size: 0.8rem !important; color: #374151 !important; }

/* ── Checkbox ── */
.stCheckbox label span { color: #374151 !important; font-size: 0.82rem !important; }
.stCheckbox [data-testid="stWidgetLabel"] p { color: #374151 !important; }

/* ── Global text safety ── */
label, p, span:not(.badge):not(.lc-name):not(.lc-meta):not(.score-ring),
[data-testid="stWidgetLabel"] p,
.stMarkdown p { color: #0F172A; }
.stCaption, [data-testid="stCaptionContainer"] p { color: #64748B !important; font-size: 0.76rem !important; }

/* ── Divider ── */
hr { border-color: #E8EAED !important; margin: 20px 0 !important; }

/* ── Progress ── */
.stProgress > div > div { background: #2563EB !important; }

/* ── Specific logout button override ── */
div[data-testid="stButton"]:has(button[key="logout_btn"]) button,
div[data-testid="stButton"]:has(button[key="sb_logout_btn"]) button {
    background: transparent !important;
    border-color: #334155 !important;
    color: #94A3B8 !important;
    font-size: 0.74rem !important;
    padding: 5px 12px !important;
}
div[data-testid="stButton"]:has(button[key="logout_btn"]) button:hover,
div[data-testid="stButton"]:has(button[key="sb_logout_btn"]) button:hover {
    border-color: #EF4444 !important;
    color: #EF4444 !important;
    background: transparent !important;
}

/* ── Select slider ── */
[data-testid="stSlider"] [data-testid="stWidgetLabel"] p { color: #0F172A !important; }

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
    _, mid, _ = st.columns([1, 1.1, 1])
    with mid:
        st.markdown("""
        <div style="text-align:center;padding:52px 0 32px">
            <div style="font-size:2rem;font-weight:700;color:#0F172A;letter-spacing:-0.05em;margin-bottom:6px">
                Buye<em style="color:#2563EB;font-style:normal">ra</em>
            </div>
            <p style="color:#64748B;font-size:0.85rem;margin:0;font-weight:400">
                AI-powered B2B lead discovery
            </p>
        </div>
        """, unsafe_allow_html=True)

        tab_login, tab_reg = st.tabs(["Sign in", "Create account"])

        with tab_login:
            with st.form("lf"):
                uname = st.text_input("Username", placeholder="your-username")
                pwd   = st.text_input("Password", type="password", placeholder="••••••••")
                sub   = st.form_submit_button("Sign in →", use_container_width=True, type="primary")
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
                nu  = st.text_input("Username", placeholder="choose a username")
                ne  = st.text_input("Email (optional)", placeholder="you@company.com")
                np  = st.text_input("Password", type="password", placeholder="min. 6 characters")
                np2 = st.text_input("Confirm password", type="password", placeholder="repeat password")
                sub2 = st.form_submit_button("Create account →", use_container_width=True, type="primary")
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
for _k, _v in [("auth_token",""),("auth_user_id",""),
                ("auth_username",""),("auth_role","user")]:
    if _k not in st.session_state:
        st.session_state[_k] = _v

if not st.session_state.auth_token:
    _show_login_page()
    st.stop()

if "show_assistant" not in st.session_state:
    st.session_state["show_assistant"] = False

if st.session_state["show_assistant"]:
    st.markdown(
        '<div class="page-header">'
        '<div class="ph-brand">Buye<em>ra</em> · AI Assistant</div>'
        '<div class="ph-actions">'
        f'<div class="ph-user">@{st.session_state.auth_username}</div>'
        '</div></div>',
        unsafe_allow_html=True)
    if st.button("← Back to search", key="back_to_search_btn"):
        st.session_state["show_assistant"] = False
        st.rerun()

    # FIX: defensive import — same try/except relative-then-absolute pattern
    # used everywhere else in this codebase (backend/main.py, etc). The old
    # bare "from assistant import render_assistant_page" had no fallback and
    # could raise ModuleNotFoundError depending on how Streamlit resolves
    # sys.path for the entry-point script, silently breaking this whole page.
    try:
        from assistant import render_assistant_page
    except ImportError:
        from ui.assistant import render_assistant_page

    render_assistant_page()
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

CHANNEL_EMOJI = {
    "Manufacturer":"🏭","Importer":"📦","Trader":"🤝",
    "Wholesaler":"🏪","Distributor":"🚚","Retailer":"🛍️",
}

SUGGESTION_CHIPS = [
    "LED importers Delhi",
    "Textile manufacturers Surat",
    "Pharma distributors Mumbai",
    "Steel traders UAE",
    "Electronics wholesalers Gujarat",
    "Machinery exporters Chennai",
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
    st.markdown(
        '<div class="sb-brand">'
        '<div class="sb-logo">Buye<em>ra</em></div>'
        f'<div class="sb-user-pill">@{st.session_state.auth_username}</div>'
        '</div>',
        unsafe_allow_html=True)

    if st.button("Sign out", key="sb_logout_btn", use_container_width=True):
        for _k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[_k] = ""
        st.rerun()
    st.markdown('<div class="sb-section">Tools</div>', unsafe_allow_html=True)
    if st.button("🤖 AI Assistant", key="sb_assistant_btn", use_container_width=True):
        st.session_state["show_assistant"] = True
        st.rerun()
        
    st.markdown('<div class="sb-section">Filters</div>', unsafe_allow_html=True)

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
        "Minimum score", 0.0, 1.0,
        st.session_state.sf_min_score, 0.05, key="sb_score_sl")

    st.markdown('<div class="sb-section">Quick filters</div>', unsafe_allow_html=True)
    st.session_state.sf_has_email = st.checkbox("Has email",
                                                 key="sb_email_cb",
                                                 value=st.session_state.sf_has_email)
    st.session_state.sf_has_phone = st.checkbox("Has phone",
                                                 key="sb_phone_cb",
                                                 value=st.session_state.sf_has_phone)
    st.session_state.sf_gaps_only = st.checkbox("Compliance issues only",
                                                  key="sb_gaps_cb",
                                                  value=st.session_state.sf_gaps_only)

    st.markdown('<div class="sb-section">Search options</div>', unsafe_allow_html=True)
    st.session_state.scan_all = st.checkbox("Scan all pages (slower)",
                                             key="sb_scan_cb",
                                             value=st.session_state.scan_all)
    _qt_labels = ["All","Basic","Good","Best"]
    _qt_map    = {"All":0,"Basic":1,"Good":2,"Best":3}
    _qt_rev    = {0:"All",1:"Basic",2:"Good",3:"Best"}
    _qt_cur    = _qt_rev.get(st.session_state.quality_threshold, "All")
    _qt_sel    = st.select_slider("Result quality", _qt_labels,
                                   value=_qt_cur, key="sb_qt_sl")
    st.session_state.quality_threshold = _qt_map[_qt_sel]

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("Clear filters", use_container_width=True, key="sb_clear_btn"):
            st.session_state["_reset_filters"] = True
            st.rerun()
    with col2:
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
# Page header
# ---------------------------------------------------------------------------
st.markdown(
    '<div class="page-header">'
    '<div class="ph-brand">Buye<em>ra</em></div>'
    '<div class="ph-actions">'
    f'<div class="ph-user">@{st.session_state.auth_username}</div>'
    '</div>'
    '</div>',
    unsafe_allow_html=True)

# Logout button (positioned alongside header via columns trick)
_hc1, _hc2 = st.columns([10, 1])
with _hc2:
    if st.button("Sign out", key="logout_btn"):
        for _k in ["auth_token","auth_user_id","auth_username","auth_role"]:
            st.session_state[_k] = ""
        st.rerun()

# ---------------------------------------------------------------------------
# Session restore — resume the most recent active job
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
# Search hero
# ---------------------------------------------------------------------------
st.markdown("""
<div class="search-hero">
  <div class="search-eyebrow">🎯 B2B Lead Discovery</div>
  <div class="search-headline">Find your next customer</div>
  <div class="search-sub">Search for importers, manufacturers, distributors, traders — anywhere in the world.</div>
</div>
""", unsafe_allow_html=True)

sc1, sc2, sc3 = st.columns([6, 1, 1])
with sc1:
    query = st.text_input(
        "q",
        value=st.session_state.sf_query,
        placeholder='e.g. "LED importers Gujarat" or "pharma distributors Mumbai"',
        label_visibility="collapsed",
        key="search_input_box",
    )
    st.session_state.sf_query = query

with sc2:
    search_clicked = st.button("Search", use_container_width=True,
                               key="main_search_btn", type="primary")

with sc3:
    refresh_clicked = st.button("↺ Refresh", use_container_width=True, key="refresh_btn")
    if refresh_clicked:
        st.rerun()

# Suggestion chips
chips_html = "".join(f'<span class="chip">{c}</span>' for c in SUGGESTION_CHIPS)
st.markdown(f'<div class="chips-row">{chips_html}</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Always-visible filter row — usable BEFORE running any search
# (mirrors the sidebar filters; writes into the same canonical session keys
#  so sidebar / this row / post-search expander all stay in sync)
# ---------------------------------------------------------------------------
st.markdown('<div class="presearch-row">', unsafe_allow_html=True)
st.markdown('<div class="presearch-label">🎛️ Filter before you search</div>',
            unsafe_allow_html=True)

pf1, pf2, pf3, pf4 = st.columns(4)

with pf1:
    _ctr_opts = ALL_COUNTRIES
    _ctr_idx  = _ctr_opts.index(st.session_state.sf_country) \
                if st.session_state.sf_country in _ctr_opts else 0
    _ps_country = st.selectbox("Country", _ctr_opts, index=_ctr_idx, key="ps_country_sel")
    st.session_state.sf_country = _ps_country

with pf2:
    _ind_opts = ["Any"] + ALL_INDUSTRIES
    _ind_idx  = _ind_opts.index(st.session_state.sf_industry) \
                if st.session_state.sf_industry in _ind_opts else 0
    _ps_industry = st.selectbox("Industry", _ind_opts, index=_ind_idx, key="ps_industry_sel")
    st.session_state.sf_industry = _ps_industry

with pf3:
    _ch_opts = ["Any"] + CHANNEL_TYPES
    _ch_idx  = _ch_opts.index(st.session_state.sf_channel) \
               if st.session_state.sf_channel in _ch_opts else 0
    _ps_channel = st.selectbox("Business type", _ch_opts, index=_ch_idx, key="ps_channel_sel")
    st.session_state.sf_channel = _ps_channel

with pf4:
    _qt_labels = ["All","Basic","Good","Best"]
    _qt_map    = {"All":0,"Basic":1,"Good":2,"Best":3}
    _qt_rev    = {0:"All",1:"Basic",2:"Good",3:"Best"}
    _qt_cur    = _qt_rev.get(st.session_state.quality_threshold, "All")
    _ps_quality = st.selectbox("Result quality", _qt_labels,
                               index=_qt_labels.index(_qt_cur), key="ps_quality_sel")
    st.session_state.quality_threshold = _qt_map[_ps_quality]

st.markdown('</div>', unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Build and trigger search
# ---------------------------------------------------------------------------
def _build_final_query() -> str:
    parts = [st.session_state.sf_query.strip()]
    for val in [st.session_state.sf_industry,
                st.session_state.sf_state,
                st.session_state.get("sf_city","Any"),
                st.session_state.sf_country]:
        if val not in ("Any","Any Country","") and val.lower() not in st.session_state.sf_query.lower():
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
                "query": fq,
                "continue_search": "false",
                "scan_all_remaining": str(st.session_state.scan_all).lower(),
                "country_filter": cf,
                "trusted_only": "false",
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
                st.error(f"Search failed: {r.text}")
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
# Live search status banner
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
            st.markdown(
                '<div class="banner-info">'
                '<span>⏳</span>'
                f'<span>Searching — <strong>{saved}</strong> companies found so far'
                f' · {pages} pages scanned · auto-refreshing every {POLL_SECONDS}s</span>'
                '</div>',
                unsafe_allow_html=True)
            st.progress(min(saved / 50, 1.0))
            time.sleep(POLL_SECONDS)
            st.rerun()

        elif sv == "completed":
            jid = status.get("job_id","")
            if jid and jid not in st.session_state.notified_jobs:
                st.toast(f"✅ Search complete — {saved} companies found")
                st.session_state.notified_jobs.append(jid)
            if status.get("ask_continue"):
                c1, c2 = st.columns([3, 2])
                with c1:
                    st.markdown(
                        f'<div class="banner-info"><span>✅</span>'
                        f'<span>Found <strong>{saved}</strong> companies. More pages available.</span></div>',
                        unsafe_allow_html=True)
                with c2:
                    cc1, cc2 = st.columns(2)
                    with cc1:
                        if st.button("Find more →", use_container_width=True, key="continue_btn"):
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
                        if st.button("Done", use_container_width=True, key="done_btn"):
                            st.session_state.active_job_id = ""
                            st.rerun()
            else:
                st.markdown(
                    f'<div class="banner-success">✅ Search complete — {saved} companies found.</div>',
                    unsafe_allow_html=True)
                st.session_state.active_job_id = ""

        elif sv == "failed":
            st.error(f"Search failed: {status.get('error','Unknown error')}")
            st.session_state.active_job_id = ""

# ---------------------------------------------------------------------------
# Filter + sort
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
# Helpers
# ---------------------------------------------------------------------------
def _safe(v) -> str:
    s = str(v).strip()
    return "" if s.lower() in ("nan","none","") else s

def _bool_icon(val):
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"

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

    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Companies",       total)
    m2.metric("High priority",   high)
    m3.metric("Have email",      emails)
    m4.metric("Compliance gaps", gaps)
    m5.metric("Manufacturers",   mfg)

# ---------------------------------------------------------------------------
# Card list
# ---------------------------------------------------------------------------
def _render_card_list(leads: list, key_suffix: str = ""):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">🔍</div>
          <div class="empty-title">No results match your filters</div>
          <div class="empty-desc">Try adjusting the filters in the sidebar.</div>
        </div>""", unsafe_allow_html=True)
        return

    selected = st.session_state.get("selected_card")

    for idx, row in enumerate(leads):
        cid     = _card_id(row, idx)
        is_sel  = (selected == cid)
        company = _safe(row.get("company","Unknown")) or "Unknown"
        city    = _safe(row.get("city",""))
        country = _safe(row.get("country_detected",""))
        channel = _safe(row.get("channel_type",""))
        imp     = (_safe(row.get("importance","low")) or "low").lower()
        score   = float(row.get("final_score",0) or 0)
        gaps    = row.get("compliance_gaps",[])
        email   = _safe(row.get("email",""))
        is_dir  = bool(row.get("is_directory",False))

        loc     = ", ".join(filter(None,[city,country]))
        emoji   = "📂" if is_dir else CHANNEL_EMOJI.get(channel,"🏢")
        meta_p  = list(filter(None,[
            f"📍 {loc}" if loc else "",
            channel,
            "📧 email" if "@" in email else "",
        ]))
        meta_str = "  ·  ".join(meta_p)

        # Score ring class
        ring_cls = "high" if score >= 0.6 else "medium" if score >= 0.35 else "low"

        # Importance badge
        if imp == "high":
            ib = '<span class="badge b-high">High</span>'
        elif imp == "medium":
            ib = '<span class="badge b-medium">Med</span>'
        else:
            ib = '<span class="badge b-low">Low</span>'

        # Compliance
        gb = ('<span class="badge b-gap">⚠ Gaps</span>'
              if isinstance(gaps,list) and gaps
              else '<span class="badge b-clean">✓</span>')

        active_cls = " active" if is_sel else ""

        dir_icon = "  📂" if is_dir else ""
        st.markdown(
            f'<div class="lead-card{active_cls}">'
            f'<div class="score-ring {ring_cls}">{score:.2f}</div>'
            '<div class="lc-body">'
            f'<div class="lc-name">{company}{dir_icon}</div>'
            f'<div class="lc-meta">{meta_str}</div>'
            '</div>'
            f'<div class="lc-badges">{ib}{gb}</div>'
            '</div>',
            unsafe_allow_html=True)

        btn_label = "Close" if is_sel else "View →"
        if st.button(btn_label, key=f"sel_{key_suffix}_{cid}_{idx}",
                     use_container_width=True):
            if not is_sel:
                st.session_state.selected_card = cid
                st.session_state.selected_tab  = key_suffix
                if cid not in st.session_state.card_details:
                    with st.spinner(f"Loading {company[:24]}…"):
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
        <div class="dp-empty">
          <div class="dp-empty-icon">👈</div>
          <div class="dp-empty-text">Select a company from the list to see full details, contact info, and compliance status here.</div>
        </div>""", unsafe_allow_html=True)
        return

    company  = _safe(row.get("company","")) or "Unknown"
    city     = _safe(row.get("city",""))
    country  = _safe(row.get("country_detected",""))
    industry = _safe(row.get("industry_detected",""))
    channel  = _safe(row.get("channel_type",""))
    score    = float(row.get("final_score",0) or 0)
    imp      = (_safe(row.get("importance","low")) or "low").lower()
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

    # Imp badge for panel
    if imp == "high":
        ib = '<span class="badge b-high">⭐ High</span>'
    elif imp == "medium":
        ib = '<span class="badge b-medium">Medium</span>'
    else:
        ib = '<span class="badge b-low">Low</span>'

    # Tags
    tags = []
    if industry: tags.append(f'<span class="dp-tag">{industry}</span>')
    if channel:  tags.append(f'<span class="dp-tag">{CHANNEL_EMOJI.get(channel,"")} {channel}</span>')
    if size:     tags.append(f'<span class="dp-tag">{size} employees</span>')
    if founded:  tags.append(f'<span class="dp-tag">Est. {founded}</span>')
    if turnover: tags.append(f'<span class="dp-tag dp-tag-green">💰 {turnover}</span>')
    tags_html = "".join(tags)

    # Compliance
    if isinstance(gaps,list) and gaps:
        gap_html = " ".join(
            f'<span class="badge b-gap" style="margin-right:3px">⚠ {GAP_LABELS.get(g,g)}</span>'
            for g in gaps)
    else:
        gap_html = '<span class="badge b-clean">✓ No compliance issues detected</span>'

    # Links
    links = []
    if website:
        links.append(f'<a class="dp-link" href="{website}" target="_blank">🌐 Website</a>')
    if email and "@" in email:
        links.append(f'<a class="dp-link" href="mailto:{email}">📧 {email}</a>')
    if phone:
        links.append(f'<span class="dp-link">📞 {phone}</span>')
    if linkedin:
        links.append(f'<a class="dp-link" href="{linkedin}" target="_blank">💼 LinkedIn</a>')
    for field, icon, lbl in [("twitter_url","𝕏","X"),("facebook_url","📘","Facebook"),
                               ("instagram_url","📸","Instagram"),("youtube_url","▶","YouTube"),
                               ("whatsapp_url","💬","WhatsApp")]:
        v = _safe(str(row.get(field,"")))
        if v:
            links.append(f'<a class="dp-link" href="{v}" target="_blank">{icon} {lbl}</a>')
    for plat, icon in [("linkedin","💼"),("twitter","𝕏"),("facebook","📘"),
                        ("instagram","📸"),("youtube","▶")]:
        v = _safe(str(social_r.get(plat,"")))
        existing = _safe(str(row.get(plat+"_url","")))
        if v and not existing:
            links.append(f'<a class="dp-link" href="{v}" target="_blank">{icon}</a>')
    links_html = "".join(links)

    def _section(title, content):
        return (f'<div class="dp-section-label">{title}</div>'
                f'<div class="dp-body">{content}</div>')

    prod_str = " · ".join(products[:8])

    dir_badge_html = "<span class='badge b-dir'>📂 Directory</span>" if is_dir else ""
    loc_prefix = ("📍 " + loc + "  ·  ") if loc else ""

    header_html = (
        '<div class="detail-panel">'
        '<div style="margin-bottom:12px">'
        '<div style="display:flex;justify-content:flex-end;gap:5px;align-items:center;flex-wrap:wrap;margin-bottom:8px">'
        f'{ib}'
        f'<span class="badge" style="background:#EFF6FF;color:#2563EB;border:1px solid #BFDBFE;font-weight:700">{score:.2f}</span>'
        f'{dir_badge_html}'
        '</div>'
        f'<div class="dp-company-name">{company}</div>'
        f'<div class="dp-location">{loc_prefix}{channel}</div>'
        '</div>'
    )

    parts = [header_html]

    if tags_html:
        parts.append(f'<div class="dp-tags">{tags_html}</div>')
    if summary:
        parts.append(_section("About", summary))
    if usp:
        parts.append(_section("Unique selling point", f"<em>{usp}</em>"))
    if prod_str:
        parts.append(_section("Products & services", prod_str))
    if contact:
        conf_str = (f' <span style="color:#059669;font-size:0.68rem">({c_conf} confidence)</span>'
                    if c_conf and c_conf not in ("","low") else "")
        ct = f'<strong>{contact}</strong>'
        if c_title: ct += f'  —  {c_title}'
        ct += conf_str
        if c_email and "@" in c_email and c_email != email:
            ct += f'<br>📧 {c_email}'
        parts.append(_section("Key contact", ct))
    parts.append(_section("Compliance status", gap_html))
    if certs:
        parts.append(_section("Certifications", " · ".join(certs[:8])))
    if exports:
        parts.append(_section("Export markets", " · ".join(exports[:6])))
    if key_cust:
        parts.append(_section("Key customers", " · ".join(key_cust[:4])))
    if signals:
        parts.append(_section("Live signals", "  ".join(signals)))
    if news:
        news_html = "<br>".join(
            f'<a href="{n.get("url","#")}" target="_blank" class="dp-link" style="display:inline-block;margin-bottom:2px">'
            f'📰 {str(n.get("title",""))[:70]}</a>'
            for n in news[:3] if n.get("title"))
        if news_html:
            parts.append(_section("Recent news", news_html))
    if not is_valid and rejection:
        parts.append(f'<div style="background:#FEF2F2;border:1px solid #FECACA;border-radius:7px;'
                     f'padding:9px 12px;font-size:0.76rem;color:#B91C1C;margin-top:10px;">'
                     f'⚠ AI note: {rejection}</div>')
    if links_html:
        parts.append(f'<div class="dp-links">{links_html}</div>')
    parts.append("</div>")

    st.markdown("".join(parts), unsafe_allow_html=True)

    # Directory panel — needs Streamlit widgets outside HTML
    if is_dir:
        st.markdown(
            f'<div class="banner-warn">📂 Directory page — contains ~{dir_count} companies</div>',
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
                if wb: lk += f' <a href="{wb}" target="_blank" class="dp-link">🌐</a>'
                if em and "@" in em: lk += f' <a href="mailto:{em}" class="dp-link">📧</a>'
                loc2 = f"  ·  📍 {cy}" if cy else ""
                pr2  = f'<br><span style="color:#94A3B8">{pr}</span>' if pr else ""
                dir_html.append(
                    f'<div class="dir-item"><strong>{n}</strong>{loc2}{lk}{pr2}</div>')
            st.markdown("".join(dir_html), unsafe_allow_html=True)
            if len(dir_cos) > 30:
                st.caption(f"… and {len(dir_cos)-30} more")
            df_dir = pd.DataFrame([{
                "Company":c.get("company",""),"City":c.get("city",""),
                "Phone":c.get("phone",""),"Email":c.get("email",""),
                "Website":c.get("website",""),"Products":c.get("products",""),
            } for c in dir_cos])
            st.download_button("Download directory as CSV",
                               data=df_dir.to_csv(index=False).encode("utf-8"),
                               file_name=f"dir_{cid[:8]}.csv", mime="text/csv",
                               key=f"dl_det_dir_{cid}")
        else:
            if st.button("Extract all companies from this directory",
                         key=f"det_extract_{cid}", use_container_width=True,
                         type="primary"):
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
    st.download_button("Download CSV",
                       data=csv_df.to_csv(index=False).encode("utf-8"),
                       file_name=f"leads_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_{key_suffix}_{len(leads)}")

# ---------------------------------------------------------------------------
# Main results renderer
# ---------------------------------------------------------------------------
def _show_results(leads: list, key_suffix: str = "tab"):
    if not leads:
        st.markdown("""
        <div class="empty-state">
          <div class="empty-icon">📭</div>
          <div class="empty-title">Nothing here yet</div>
          <div class="empty-desc">Run a search or adjust your filters to find companies.</div>
        </div>""", unsafe_allow_html=True)
        return

    filtered  = _apply_filters(leads)
    count_str = (f"{len(filtered)} of {len(leads)}"
                 if len(filtered) != len(leads) else str(len(leads)))

    hc1, hc2 = st.columns([5, 1])
    with hc1:
        st.caption(f"**{count_str} companies** · click View to expand details")
    with hc2:
        view = st.radio("", ["Cards","Table"], horizontal=True,
                        key=f"view_{key_suffix}",
                        index=0 if st.session_state.view_mode == "Cards" else 1,
                        label_visibility="collapsed")
        st.session_state.view_mode = view

    if view == "Table":
        _show_table(filtered, key_suffix=key_suffix)
        return

    selected_cid = st.session_state.get("selected_card")
    show_detail  = (selected_cid is not None
                    and selected_cid in st.session_state.card_details
                    and st.session_state.get("selected_tab","") == key_suffix)

    if show_detail:
        col_left, col_right = st.columns([2, 3], gap="large")
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
    rows = [{
        "Company":str(c.get("company","—")),"City":str(c.get("city","—")),
        "Phone":str(c.get("phone","—")),"Email":str(c.get("email","—")),
        "Website":str(c.get("website","—")),
        "Products":str(c.get("products","—"))[:80],
        "About":str(c.get("snippet","—"))[:100],
    } for c in companies]
    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, height=min(60+len(df)*36,500))
    st.download_button("Download CSV",
                       data=df.to_csv(index=False).encode("utf-8"),
                       file_name=f"directory_{key_suffix}.csv", mime="text/csv",
                       key=f"dl_dir_{key_suffix}_{len(companies)}")

# ===========================================================================
# MAIN RESULTS SECTION
# ===========================================================================
if company_leads or st.session_state.active_job_id:
    st.markdown("---")

    # ── Column picker (collapsed) ──
    with st.expander("Filters & table columns", expanded=False):
        f1, f2, f3, f4 = st.columns(4)
        with f1:
            sel_country = st.selectbox("Country", ALL_COUNTRIES,
                index=ALL_COUNTRIES.index(st.session_state.sf_country)
                      if st.session_state.sf_country in ALL_COUNTRIES else 0,
                key="exp_country_sel")
            st.session_state.sf_country = sel_country
            state_opts = (["Any"] + COUNTRY_STATES.get(sel_country,[])
                          if sel_country != "Any Country" else ["Any"])
            if st.session_state.sf_state not in state_opts:
                st.session_state.sf_state = "Any"
            sel_state = st.selectbox("State / Region", state_opts,
                index=state_opts.index(st.session_state.sf_state)
                      if st.session_state.sf_state in state_opts else 0,
                key="exp_state_sel", disabled=(sel_country=="Any Country"))
            st.session_state.sf_state = sel_state
        with f2:
            sel_industry = st.selectbox("Industry", ["Any"]+ALL_INDUSTRIES,
                index=(["Any"]+ALL_INDUSTRIES).index(st.session_state.sf_industry)
                      if st.session_state.sf_industry in ["Any"]+ALL_INDUSTRIES else 0,
                key="exp_industry_sel")
            st.session_state.sf_industry = sel_industry
            sel_channel = st.selectbox("Business type", ["Any"]+CHANNEL_TYPES,
                index=(["Any"]+CHANNEL_TYPES).index(st.session_state.sf_channel)
                      if st.session_state.sf_channel in ["Any"]+CHANNEL_TYPES else 0,
                key="exp_channel_sel")
            st.session_state.sf_channel = sel_channel
        with f3:
            _imp_opts2 = ["Any","High ⭐","Medium","Low"]
            sel_importance = st.selectbox("Priority", _imp_opts2,
                index=_imp_opts2.index(st.session_state.sf_importance)
                      if st.session_state.sf_importance in _imp_opts2 else 0,
                key="exp_importance_sel")
            st.session_state.sf_importance = sel_importance
            sel_min_score = st.slider("Min score", 0.0, 1.0,
                st.session_state.sf_min_score, 0.05, key="exp_min_score_sl")
            st.session_state.sf_min_score = sel_min_score
        with f4:
            _sort_opts2 = ["Best Match First","Priority (High → Low)",
                           "Company Name A → Z","Company Name Z → A","Newest First"]
            sel_sort = st.selectbox("Sort by", _sort_opts2,
                index=_sort_opts2.index(st.session_state.sf_sort)
                      if st.session_state.sf_sort in _sort_opts2 else 0,
                key="exp_sort_sel")
            st.session_state.sf_sort = sel_sort
            sel_email = st.checkbox("Has email",
                value=st.session_state.sf_has_email, key="exp_has_email_cb")
            st.session_state.sf_has_email = sel_email
            sel_phone = st.checkbox("Has phone",
                value=st.session_state.sf_has_phone, key="exp_has_phone_cb")
            st.session_state.sf_has_phone = sel_phone
            sel_gaps = st.checkbox("Compliance issues only",
                value=st.session_state.sf_gaps_only, key="exp_gaps_only_cb")
            st.session_state.sf_gaps_only = sel_gaps

        ca, cb, cc = st.columns(3)
        with ca:
            sel_scan_all = st.checkbox("Scan all pages (slower)",
                value=st.session_state.scan_all, key="exp_scan_all_cb")
            st.session_state.scan_all = sel_scan_all
        with cb:
            if st.button("Clear filters", use_container_width=True, key="exp_clear"):
                st.session_state["_reset_filters"] = True
                st.rerun()
        with cc:
            if st.button("Delete all leads", use_container_width=True, key="exp_del"):
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

        st.markdown("---")
        st.markdown("**Columns for table view**")
        col_groups = {
            "Company":    ["company","city","country_detected","industry_detected","product_type","channel_type","company_size","incorporation_date"],
            "Scores":     ["importance","final_score","domain_authority"],
            "Compliance": ["compliance_gaps","bis_certified","gst_registered","iec_found","mca_active","mca_company_type"],
            "Contact":    ["contact_person","contact_email","email","phone","linkedin_url"],
            "AI":         ["ai_summary","products","usp","key_customers"],
            "Business":   ["annual_turnover","certifications","export_markets","grok_score"],
            "Social":     ["linkedin_url","twitter_url","facebook_url","instagram_url","youtube_url","whatsapp_url"],
            "Validation": ["is_valid_lead","rejection_reason","contact_title","contact_confidence","is_directory","directory_count"],
            "Meta":       ["searched_query","created_at"],
        }
        new_visible = []
        seen_keys   = set()
        for grp_name, grp_cols in col_groups.items():
            st.markdown(f"**{grp_name}**")
            gcols      = st.columns(4)
            grp_prefix = re.sub(r"[^a-z0-9]","_",grp_name.lower())[:10]
            for i, col_key in enumerate(grp_cols):
                wkey = f"col_{grp_prefix}_{col_key}"
                if wkey in seen_keys: wkey = f"{wkey}_{i}"
                seen_keys.add(wkey)
                with gcols[i % 4]:
                    checked = st.checkbox(
                        ALL_COLUMNS.get(col_key, col_key),
                        value=(col_key in st.session_state.visible_cols),
                        key=wkey)
                    if checked and col_key not in new_visible:
                        new_visible.append(col_key)

        col_b1, col_b2 = st.columns(2)
        with col_b1:
            if st.button("Apply columns", use_container_width=True, key="apply_cols"):
                st.session_state.visible_cols = new_visible if new_visible else DEFAULT_COLUMNS[:]
                st.rerun()
        with col_b2:
            if st.button("Reset to defaults", use_container_width=True, key="reset_cols"):
                st.session_state.visible_cols = DEFAULT_COLUMNS[:]
                st.rerun()

if company_leads:
    _show_metrics(company_leads)
    st.markdown("<br>", unsafe_allow_html=True)

    tab_all, tab_high, tab_gaps, tab_mfg, tab_imp, tab_trade, tab_dir = st.tabs([
        f"All ({len(company_leads)})",
        "High priority",
        "Compliance gaps",
        "Manufacturers",
        "Importers",
        "Traders & distributors",
        "Directories",
    ])

    with tab_all:
        _show_results(company_leads, "all")

    with tab_high:
        high_leads = [x for x in company_leads
                      if str(x.get("importance","")).lower() == "high"]
        _show_results(high_leads, "high")

    with tab_gaps:
        st.markdown(
            '<div class="banner-warn">These companies are missing BIS, GST, IEC or MCA registrations — '
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
                                         placeholder="https://www.indiamart.com/…",
                                         key="manual_dir_url")
            manual_query = st.text_input("What kind of companies are listed?",
                                         placeholder="electronics importers india",
                                         key="manual_dir_query")
            if st.button("Scan directory", key="manual_dir_btn",
                         use_container_width=True, type="primary"):
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
                    _show_extracted_companies(
                        res["companies"], key_suffix="manual",
                        query=manual_query or st.session_state.active_query)

        if not dir_leads:
            st.markdown(
                '<div class="banner-warn">No directory pages detected yet. Try searches like '
                '<em>electronics importers list india</em>, or paste a URL in the scanner above.</div>',
                unsafe_allow_html=True)
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
    with st.expander("Check licences & registrations — BIS, GST, IEC, MCA", expanded=False):
        st.markdown(
            "Find which companies are missing key Indian government registrations. "
            "Companies with gaps are high-value prospects for compliance consulting services.")
        n_check  = st.slider("How many companies to check?", 5, 100, 20, key="enrich_n")
        cf_enrich = "" if st.session_state.sf_country == "Any Country" \
                    else st.session_state.sf_country.lower()
        if st.button("Start checking", key="enrich_btn",
                     use_container_width=True, type="primary"):
            with st.spinner("Checking registrations… this may take 1–2 minutes"):
                try:
                    r = _api_post("/leads/enrich-compliance",
                                  params={"limit": n_check, "country_filter": cf_enrich},
                                  timeout=300)
                    if r.status_code == 200:
                        st.success(
                            f"Checked {r.json().get('checked',0)} companies. "
                            "Refresh to see compliance results.")
                    else:
                        st.error("Check failed.")
                except Exception as e:
                    st.error(str(e))

elif not st.session_state.active_job_id:
    st.markdown("""
    <div class="empty-state" style="margin-top:40px">
      <div class="empty-icon">🌐</div>
      <div class="empty-title">Ready to discover leads</div>
      <div class="empty-desc">
        Type what you're looking for above.<br>
        Examples: <em>electronics importers Gujarat</em>  ·  <em>pharma manufacturers Mumbai</em>  ·  <em>steel traders Dubai</em>
      </div>
    </div>
    """, unsafe_allow_html=True)
