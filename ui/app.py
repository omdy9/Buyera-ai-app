import time
import re

import pandas as pd
import requests
import streamlit as st

API          = "http://127.0.0.1:8000"
POLL_SECONDS = 2

st.set_page_config(page_title="Global B2B Lead Discovery", layout="wide")

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
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------

# Columns shown in every table — ordered by usefulness
DISPLAY_COLS = [
    "company", "importance", "final_score",
    "compliance_gaps",
    "bis_certified", "gst_registered", "iec_found", "mca_active",
    "email", "phone", "website",
    "ai_summary", "products",
    "domain_authority", "contact_presence",
    "semantic_score", "keyword_score",
    "country_filter", "searched_query", "created_at",
]


def _bool_icon(val) -> str:
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"


def _prep_df(df_in: pd.DataFrame) -> pd.DataFrame:
    """Clean up a leads dataframe for display."""
    df = df_in[[c for c in DISPLAY_COLS if c in df_in.columns]].copy()

    # Flatten list columns to readable strings
    if "compliance_gaps" in df.columns:
        df["compliance_gaps"] = df["compliance_gaps"].apply(
            lambda g: ", ".join(GAP_LABELS.get(x, x) for x in g)
            if isinstance(g, list) else ""
        )
    if "products" in df.columns:
        df["products"] = df["products"].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p, list) else str(p or "")
        )

    # Boolean icons
    for col in ["bis_certified", "gst_registered", "iec_found", "mca_active"]:
        if col in df.columns:
            df[col] = df[col].apply(_bool_icon)

    # Round floats
    for col in ["final_score", "semantic_score", "keyword_score",
                "domain_authority", "contact_presence"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").round(3)

    # Sort best first
    if "final_score" in df.columns:
        df = df.sort_values("final_score", ascending=False)

    return df


def _row_style(row):
    """
    High-contrast row colours that work in both light AND dark Streamlit themes.
    Priority order: compliance gap > high > medium > low
    """
    imp     = str(row.get("importance", "")).lower()
    gaps    = str(row.get("compliance_gaps", ""))
    has_gap = bool(gaps and gaps not in ("", "nan", "None", "[]"))

    if has_gap:
        # Dark red background, light red text
        bg, color = "#4a0d0d", "#ffb3b3"
    elif imp == "high":
        # Dark green background, light green text
        bg, color = "#0d3320", "#6dffb0"
    elif imp == "medium":
        # Dark amber background, light yellow text
        bg, color = "#3d2200", "#ffd980"
    else:
        # Neutral dark background, muted text
        bg, color = "#1a1f2e", "#a0aec0"

    return [f"background-color: {bg}; color: {color}"] * len(row)


def _show_table(df_in: pd.DataFrame, key_suffix: str = "") -> None:
    """Prepare, style, and display a leads dataframe."""
    if df_in.empty:
        st.info("No leads in this category yet.")
        return

    df = _prep_df(df_in)

    styled = (
        df.style
        .apply(_row_style, axis=1)
        .set_properties(**{
            "font-size":    "13px",
            "font-family":  "monospace",
            "border-color": "#2d3748",
        })
        .set_table_styles([
            {"selector": "th", "props": [
                ("background-color", "#0f172a"),
                ("color",            "#e2e8f0"),
                ("font-size",        "12px"),
                ("font-weight",      "700"),
                ("text-transform",   "uppercase"),
                ("letter-spacing",   "0.05em"),
                ("padding",          "8px 12px"),
                ("border-bottom",    "2px solid #334155"),
            ]},
            {"selector": "td", "props": [
                ("padding",          "7px 12px"),
                ("border-bottom",    "1px solid #1e293b"),
                ("max-width",        "300px"),
                ("overflow",         "hidden"),
                ("text-overflow",    "ellipsis"),
                ("white-space",      "nowrap"),
            ]},
            {"selector": "tr:hover td", "props": [
                ("filter", "brightness(1.25)"),
            ]},
        ])
    )

    st.dataframe(
        styled,
        use_container_width=True,
        height=min(60 + len(df) * 38, 700),
    )

    # CSV download
    csv_df = df_in[[c for c in DISPLAY_COLS if c in df_in.columns]].copy()
    for col in ["compliance_gaps", "products"]:
        if col in csv_df.columns:
            csv_df[col] = csv_df[col].apply(
                lambda v: ", ".join(v) if isinstance(v, list) else str(v or ""))
    csv = csv_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️ Download CSV", csv,
        f"leads_{key_suffix}.csv", "text/csv",
        key=f"dl_{key_suffix}_{len(df_in)}",
    )


def _tab_metrics(df_in: pd.DataFrame) -> None:
    if df_in.empty:
        return
    high_n = int((df_in.get("importance", pd.Series(dtype=str))
                  .astype(str).str.lower() == "high").sum()) \
             if "importance" in df_in.columns else 0
    gap_n  = int(df_in["compliance_gaps"].apply(
                 lambda g: isinstance(g, list) and len(g) > 0).sum()) \
             if "compliance_gaps" in df_in.columns else 0
    m1, m2, m3 = st.columns(3)
    m1.metric("Total",          len(df_in))
    m2.metric("🟢 High",        high_n)
    m3.metric("🔴 With Gaps",   gap_n)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _start_background_search(search_query, continue_search=False, reset_results=False):
    try:
        response = requests.post(
            f"{API}/search/start",
            params={
                "query":              search_query,
                "continue_search":    str(continue_search).lower(),
                "scan_all_remaining": str(scan_all_remaining).lower(),
                "country_filter":     country_filter.strip().lower(),
                "trusted_only":       str(trusted_only).lower(),
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
    except Exception:
        st.error("Backend not running")
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
# Page header
# ---------------------------------------------------------------------------
st.title("🌐 Global B2B Lead Discovery Engine")
st.caption("Background search · Live results · Compliance gap detection")

# LLM provider status badge
try:
    prov = requests.get(f"{API}/llm/provider", timeout=5).json()
    pname  = prov.get("provider", "none").upper()
    pmodel = prov.get("model", "—")
    pstat  = prov.get("status", "")
    if pstat == "active":
        st.success(f"🤖 LLM: **{pname}** — `{pmodel}`", icon=None)
    else:
        st.warning("⚠️ No LLM provider configured — set DEEPSEEK_API_KEY, GROK_API_KEY, or OPENROUTER_API_KEY in .env")
except Exception:
    pass

# ---------------------------------------------------------------------------
# Query input
# ---------------------------------------------------------------------------
query = st.text_input(
    "Search query  (e.g.  electronics importers india)",
    value=st.session_state.active_query,
    placeholder="furniture manufacturers india",
)

country_options  = ["Any","india","canada","italy","dubai","UAE","china","singapore","Custom"]
selected_country = st.selectbox("Country filter", options=country_options, index=0)
custom_country   = ""
if selected_country == "Custom":
    custom_country = st.text_input("Custom country", value="")

country_filter = ""
if selected_country not in {"Any", "Custom"}:
    country_filter = selected_country
elif selected_country == "Custom":
    country_filter = custom_country.strip().lower()

col_a, col_b = st.columns(2)
with col_a:
    scan_all_remaining = st.checkbox("Continue until no pages", value=False)
with col_b:
    trusted_only = st.checkbox("Trusted domains only", value=False)

# Action buttons
col1, col2, col3 = st.columns(3)
with col1:
    if st.button("🔍 Start Search", use_container_width=True):
        if not query.strip():
            st.warning("Please enter a query")
        else:
            _start_background_search(query.strip(), continue_search=False, reset_results=True)
with col2:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()
with col3:
    if st.button("🗑️ Clear All", use_container_width=True):
        try:
            requests.delete(f"{API}/clear", timeout=15)
            for k, v in _DEFAULTS.items():
                st.session_state[k] = v
            st.warning("All leads cleared")
            st.rerun()
        except Exception:
            st.error("Backend not running")

# Compliance enrichment
with st.expander("🔬 Run Compliance Checks on Saved Leads", expanded=False):
    st.caption("Compliance checks (BIS · GST · DGFT · MCA) run separately so search stays fast.")
    enrich_limit = st.slider("Max leads to check", 10, 200, 50, key="enrich_limit")
    if st.button("▶️ Start Compliance Checks", key="enrich_btn"):
        try:
            r = requests.post(
                f"{API}/leads/enrich-compliance",
                params={"limit": enrich_limit,
                        "country_filter": country_filter.strip().lower()},
                timeout=300,
            )
            if r.status_code == 200:
                st.success(f"Done — {r.json().get('checked', 0)} leads checked. Refresh to see gaps.")
            else:
                st.error("Compliance check failed")
        except Exception:
            st.error("Backend not reachable")

st.divider()

# ---------------------------------------------------------------------------
# Colour legend
# ---------------------------------------------------------------------------
st.markdown(
    """
    <div style="display:flex; gap:16px; flex-wrap:wrap; margin-bottom:8px; font-size:13px;">
      <span style="background:#0d3320; color:#6dffb0; padding:3px 12px; border-radius:4px;">🟢 High importance</span>
      <span style="background:#3d2200; color:#ffd980; padding:3px 12px; border-radius:4px;">🟡 Medium importance</span>
      <span style="background:#4a0d0d; color:#ffb3b3; padding:3px 12px; border-radius:4px;">🔴 Has compliance gap</span>
      <span style="background:#1a1f2e; color:#a0aec0; padding:3px 12px; border-radius:4px;">⚪ Low / unchecked</span>
    </div>
    """,
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Live background job
# ---------------------------------------------------------------------------
if st.session_state.active_job_id:
    st.subheader("🔴 Live Search Results")

    status = None
    try:
        sr = requests.get(
            f"{API}/search/status/{st.session_state.active_job_id}", timeout=20)
        if sr.status_code == 200:
            status = sr.json()
    except Exception:
        st.error("Backend not reachable")

    if status:
        try:
            rr = requests.get(
                f"{API}/search/results/{st.session_state.active_job_id}",
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
        except Exception:
            st.error("Backend not reachable for results")

        company_live = [x for x in st.session_state.live_results
                        if x.get("source") != "linkedin_semantic"]

        high_n   = sum(1 for x in company_live if str(x.get("importance","")).lower()=="high")
        medium_n = sum(1 for x in company_live if str(x.get("importance","")).lower()=="medium")
        gap_n    = sum(1 for x in company_live
                       if isinstance(x.get("compliance_gaps"), list)
                       and len(x["compliance_gaps"]) > 0)

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Results",     len(company_live))
        c2.metric("🟢 High",     high_n)
        c3.metric("🟡 Medium",   medium_n)
        c4.metric("🔴 Has Gaps", gap_n)

        st.caption(
            f"Status: **{status.get('status','—')}** | "
            f"Pages scanned: {status.get('pages_scanned',0)} | "
            f"Saved total: {status.get('saved_total',0)}"
        )

        if company_live:
            live_df = pd.DataFrame(company_live)
            _show_table(live_df, key_suffix="live")

            # Find similar section
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
                            resp = requests.get(
                                f"{API}/search/more-like-this/{st.session_state.active_job_id}",
                                params={"result_index": selected_result_index,
                                        "limit": similar_limit},
                                timeout=30)
                            if resp.status_code == 200:
                                st.session_state.mlt_results           = resp.json().get("results",[])
                                st.session_state.mlt_seed_result_index = selected_result_index
                                st.session_state.mlt_seed_company      = selected_seed.get("company","")
                            else:
                                st.error("Could not find similar leads")
                        except Exception:
                            st.error("Backend not reachable")
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
    if country_filter.strip():
        lead_params["country_filter"] = country_filter.strip().lower()
    res  = requests.get(f"{API}/leads", params=lead_params, timeout=20)
    data = res.json()
except Exception:
    st.error("Backend not reachable. Start FastAPI first.")
    st.stop()

# Gap summary metrics
try:
    gp = {}
    if country_filter.strip():
        gp["country_filter"] = country_filter.strip().lower()
    gr       = requests.get(f"{API}/leads/gap-summary", params=gp, timeout=10)
    gap_summ = gr.json() if gr.status_code == 200 else {}
except Exception:
    gap_summ = {}

if gap_summ:
    st.markdown("##### Compliance Gap Summary")
    gcols = st.columns(min(len(gap_summ), 5) or 1)
    for i, (gc, cnt) in enumerate(gap_summ.items()):
        gcols[i % len(gcols)].metric(GAP_LABELS.get(gc, gc), cnt)

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

    tab_all, tab_gaps, tab_no_bis, tab_no_iec, tab_no_gst = st.tabs([
        "📋 All Leads",
        "🎯 Compliance Gaps",
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