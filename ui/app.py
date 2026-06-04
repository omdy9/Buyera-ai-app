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
    return os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")

API          = _get_api_url()
POLL_SECONDS = 2

st.set_page_config(page_title="Global B2B Lead Discovery", layout="wide")

GAP_LABELS = {
    "no_bis":        "No BIS Licence",
    "no_gst":        "No GST Registration",
    "no_iec":        "No IEC",
    "mca_not_found": "Not on MCA",
    "mca_inactive":  "Company Struck Off",
}

# ---------------------------------------------------------------------------
# Session-state defaults
# ---------------------------------------------------------------------------
_DEFAULTS = {
    "auth_token":    "",
    "auth_username": "",
    "auth_user_id":  "",
    "auth_role":     "user",
    "active_job_id":          "",
    "active_query":           "",
    "live_results":           [],
    "live_cursor":            0,
    "new_result_indexes":     [],
    "notified_jobs":          [],
    "mlt_results":            [],
    "mlt_seed_result_index":  None,
    "mlt_seed_company":       "",
}
for k, v in _DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ---------------------------------------------------------------------------
# FIX: auth helpers — every API call now sends X-User-Token
# ---------------------------------------------------------------------------
def _auth_headers() -> dict:
    token = st.session_state.get("auth_token", "")
    return {"X-User-Token": token} if token else {}

def _api_get(path: str, **kwargs) -> requests.Response:
    return requests.get(f"{API}{path}", headers=_auth_headers(),
                        timeout=kwargs.pop("timeout", 20), **kwargs)

def _api_post(path: str, **kwargs) -> requests.Response:
    return requests.post(f"{API}{path}", headers=_auth_headers(),
                         timeout=kwargs.pop("timeout", 30), **kwargs)

def _api_delete(path: str, **kwargs) -> requests.Response:
    return requests.delete(f"{API}{path}", headers=_auth_headers(),
                           timeout=kwargs.pop("timeout", 15), **kwargs)


# ---------------------------------------------------------------------------
# Login / register screen
# ---------------------------------------------------------------------------
def _show_auth_page():
    st.title("🌐 Global B2B Lead Discovery")
    st.markdown("#### Log in or create an account to continue.")

    tab_login, tab_reg = st.tabs(["🔑 Login", "📝 Register"])

    with tab_login:
        with st.form("login_form"):
            uname = st.text_input("Username")
            pwd   = st.text_input("Password", type="password")
            sub   = st.form_submit_button("Login", use_container_width=True)
        if sub:
            if not uname or not pwd:
                st.error("Please fill in both fields.")
            else:
                try:
                    r = requests.post(
                        f"{API}/auth/login",
                        json={"username": uname.strip().lower(), "password": pwd},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        st.session_state.auth_token    = d["token"]
                        st.session_state.auth_username = d["username"]
                        st.session_state.auth_user_id  = d["user_id"]
                        st.session_state.auth_role     = d.get("role", "user")
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", "Login failed."))
                except Exception as e:
                    st.error(f"Cannot reach backend: {e}")

    with tab_reg:
        with st.form("reg_form"):
            new_user  = st.text_input("Username (min 3 chars)")
            new_email = st.text_input("Email (optional)")
            new_pwd   = st.text_input("Password (min 6 chars)", type="password")
            new_pwd2  = st.text_input("Confirm password", type="password")
            sub2      = st.form_submit_button("Create Account", use_container_width=True)
        if sub2:
            if not new_user or not new_pwd:
                st.error("Username and password are required.")
            elif new_pwd != new_pwd2:
                st.error("Passwords do not match.")
            elif len(new_pwd) < 6:
                st.error("Password must be at least 6 characters.")
            else:
                try:
                    r = requests.post(
                        f"{API}/auth/register",
                        json={"username": new_user.strip().lower(),
                              "password": new_pwd, "email": new_email.strip()},
                        timeout=10,
                    )
                    if r.status_code == 200:
                        d = r.json()
                        st.session_state.auth_token    = d["token"]
                        st.session_state.auth_username = d["username"]
                        st.session_state.auth_user_id  = d["user_id"]
                        st.session_state.auth_role     = d.get("role", "user")
                        st.success(f"Welcome, {d['username']} 🎉")
                        st.rerun()
                    else:
                        st.error(r.json().get("detail", "Registration failed."))
                except Exception as e:
                    st.error(f"Cannot reach backend: {e}")


# ---------------------------------------------------------------------------
# Auth gate
# ---------------------------------------------------------------------------
if not st.session_state.auth_token:
    _show_auth_page()
    st.stop()


# ---------------------------------------------------------------------------
# Table helpers
# ---------------------------------------------------------------------------
DISPLAY_COLS = [
    "company", "importance", "final_score",
    "city", "country_detected", "industry_detected",
    "channel_type", "company_size", "incorporation_date",
    "compliance_gaps",
    "bis_certified", "gst_registered", "iec_found", "mca_active",
    "contact_person", "contact_email", "email", "phone",
    "linkedin_url", "active_website", "website",
    "ai_summary", "products",
    "domain_authority", "contact_presence",
    "semantic_score", "keyword_score",
    "country_filter", "searched_query", "created_at",
]

COLUMN_LABELS = {c: c.replace("_", " ").title() for c in DISPLAY_COLS}
COLUMN_LABELS.update({
    "final_score": "Score", "ai_summary": "AI Summary",
    "bis_certified": "BIS", "gst_registered": "GST",
    "iec_found": "IEC", "mca_active": "MCA Active",
    "country_detected": "Country", "industry_detected": "Industry",
})


def _bool_icon(val) -> str:
    if val is True:  return "✅"
    if val is False: return "❌"
    return "—"


def _prep_df(df_in: pd.DataFrame) -> pd.DataFrame:
    df = df_in[[c for c in DISPLAY_COLS if c in df_in.columns]].copy()
    df.rename(columns={c: COLUMN_LABELS.get(c, c) for c in df.columns}, inplace=True)
    lbl_gaps = COLUMN_LABELS["compliance_gaps"]
    if lbl_gaps in df.columns:
        df[lbl_gaps] = df[lbl_gaps].apply(
            lambda g: ", ".join(GAP_LABELS.get(x, x) for x in g)
            if isinstance(g, list) else ""
        )
    lbl_prods = COLUMN_LABELS["products"]
    if lbl_prods in df.columns:
        df[lbl_prods] = df[lbl_prods].apply(
            lambda p: ", ".join(str(x) for x in p) if isinstance(p, list) else str(p or "")
        )
    for col in ["bis_certified", "gst_registered", "iec_found", "mca_active"]:
        lbl = COLUMN_LABELS[col]
        if lbl in df.columns:
            df[lbl] = df[lbl].apply(_bool_icon)
    for col in ["final_score", "semantic_score", "keyword_score",
                "domain_authority", "contact_presence"]:
        lbl = COLUMN_LABELS[col]
        if lbl in df.columns:
            df[lbl] = pd.to_numeric(df[lbl], errors="coerce").round(3)
    lbl_score = COLUMN_LABELS["final_score"]
    if lbl_score in df.columns:
        df = df.sort_values(lbl_score, ascending=False)
    return df


def _row_style(row):
    imp     = str(row.get("Importance", "")).lower()
    gaps    = str(row.get(COLUMN_LABELS["compliance_gaps"], ""))
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
        .set_properties(**{"font-size": "13px", "font-family": "monospace"})
        .set_table_styles([
            {"selector": "th", "props": [
                ("background-color", "#0f172a"), ("color", "#e2e8f0"),
                ("font-size", "12px"), ("font-weight", "700"),
                ("text-transform", "uppercase"), ("padding", "8px 12px"),
                ("border-bottom", "2px solid #334155"),
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
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total",            len(df_in))
    m2.metric("🟢 High",          high_n)
    m3.metric("🔴 With Gaps",     gap_n)
    m4.metric("🏭 Manufacturers", mfg_n)


# ---------------------------------------------------------------------------
# FIX: _start_background_search receives all params explicitly
# ---------------------------------------------------------------------------
def _start_background_search(
    search_query: str,
    scan_all_remaining: bool,
    country_filter: str,
    trusted_only: bool,
    continue_search: bool = False,
    reset_results: bool = False,
) -> bool:
    try:
        response = _api_post(
            "/search/start",
            params={
                "query":              search_query,
                "continue_search":    str(continue_search).lower(),
                "scan_all_remaining": str(scan_all_remaining).lower(),
                "country_filter":     country_filter.strip().lower(),
                "trusted_only":       str(trusted_only).lower(),
            },
            timeout=30,
        )
        if response.status_code == 401:
            st.error("Session expired — please log in again.")
            st.session_state.auth_token = ""
            st.rerun()
            return False
        if response.status_code != 200:
            st.error(f"Backend error {response.status_code}: {response.text[:200]}")
            return False
        data = response.json()
        st.session_state.active_job_id = data.get("job_id", "")
        st.session_state.active_query  = search_query
        if reset_results:
            for k in ["live_results", "new_result_indexes", "mlt_results"]:
                st.session_state[k] = []
            st.session_state.live_cursor          = 0
            st.session_state.mlt_seed_result_index = None
            st.session_state.mlt_seed_company     = ""
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
        stop = {"about","their","there","which","where","would","could",
                "company","companies","service","services","business",
                "offers","offer","provides","provide","based","using","with"}
        tokens = [t for t in re.findall(r"[a-zA-Z]{4,}", ai_summary.lower())
                  if t not in stop]
        product_text = " ".join(list(dict.fromkeys(tokens))[:4])
    q = " ".join(p for p in [searched_query, product_text] if p).strip()
    return q or company


# ---------------------------------------------------------------------------
# Page header + logout
# ---------------------------------------------------------------------------
hcol1, hcol2 = st.columns([8, 1])
with hcol1:
    st.title("🌐 Global B2B Lead Discovery Engine")
    st.caption(
        "Background search · Enriched profiles · Compliance gap detection  |  "
        f"👤 **{st.session_state.auth_username}**"
    )
with hcol2:
    if st.button("🚪 Logout", use_container_width=True):
        for k in list(_DEFAULTS.keys()):
            st.session_state[k] = _DEFAULTS[k]
        st.rerun()

with st.expander("🔌 Backend Connection", expanded=False):
    st.code(f"Backend URL: {API}", language=None)
    try:
        ping = requests.get(f"{API}/", timeout=8)
        if ping.status_code == 200:
            st.success(f"✅ Connected — {ping.json().get('service','')}")
            try:
                prov = _api_get("/llm/provider", timeout=5).json()
                if prov.get("status") == "active":
                    st.info(f"🤖 LLM: **{prov['provider'].upper()}** — `{prov['model']}`")
                else:
                    st.warning("⚠️ No LLM API key configured on backend")
            except Exception:
                pass
        else:
            st.error(f"❌ Backend HTTP {ping.status_code}")
    except Exception as e:
        st.error(f"❌ Cannot reach backend: {e}")

st.markdown(
    """<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px;font-size:13px;">
      <span style="background:#0d3320;color:#6dffb0;padding:3px 12px;border-radius:4px;">🟢 High importance</span>
      <span style="background:#3d2200;color:#ffd980;padding:3px 12px;border-radius:4px;">🟡 Medium importance</span>
      <span style="background:#4a0d0d;color:#ffb3b3;padding:3px 12px;border-radius:4px;">🔴 Has compliance gap</span>
      <span style="background:#1a1f2e;color:#a0aec0;padding:3px 12px;border-radius:4px;">⚪ Low / unchecked</span>
    </div>""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Search controls
# ---------------------------------------------------------------------------
st.markdown("### 🔍 Search")

query = st.text_input(
    "Search query",
    value=st.session_state.active_query,
    placeholder="e.g. electronics importers india",
)

country_options  = ["Any", "india", "usa", "uk", "uae", "germany",
                    "canada", "australia", "singapore", "china", "Custom"]
selected_country = st.selectbox("🌍 Country filter", options=country_options, index=0)
custom_country   = ""
if selected_country == "Custom":
    custom_country = st.text_input("Enter country name", value="")
country_filter = "" if selected_country in {"Any", "Custom"} else selected_country
if selected_country == "Custom":
    country_filter = custom_country.strip().lower()

col_a, col_b = st.columns(2)
with col_a:
    scan_all_remaining = st.checkbox("Continue until no pages", value=False)
with col_b:
    trusted_only = st.checkbox("Trusted domains only", value=False)

col1, col2, col3, col4 = st.columns(4)
with col1:
    if st.button("🔍 Start Search", use_container_width=True):
        q = query.strip()
        if country_filter and country_filter not in q.lower():
            q = f"{q} {country_filter}"
        if not q:
            st.warning("Please enter a search query")
        else:
            _start_background_search(
                q, scan_all_remaining, country_filter, trusted_only,
                continue_search=False, reset_results=True
            )
with col2:
    if st.button("🔄 Refresh", use_container_width=True):
        st.rerun()
with col3:
    if st.button("🗑️ Clear Leads", use_container_width=True):
        try:
            _api_delete("/clear", timeout=15)
            for k in ["live_results", "new_result_indexes", "mlt_results",
                      "active_job_id", "active_query", "live_cursor"]:
                st.session_state[k] = _DEFAULTS[k]
            st.warning("Your leads cleared")
            st.rerun()
        except Exception as e:
            st.error(f"Cannot reach backend: {e}")
with col4:
    if st.button("🔬 Compliance Check", use_container_width=True):
        try:
            r = _api_post("/leads/enrich-compliance",
                params={"limit": 50,
                        "country_filter": country_filter.strip().lower()},
                timeout=300)
            if r.status_code == 200:
                st.success(f"Done — {r.json().get('checked', 0)} leads checked.")
            else:
                st.error("Compliance check failed")
        except Exception as e:
            st.error(f"Cannot reach backend: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Live job
# ---------------------------------------------------------------------------
if st.session_state.active_job_id:
    st.subheader("🔴 Live Search Results")

    status = None
    try:
        sr = _api_get(f"/search/status/{st.session_state.active_job_id}", timeout=20)
        if sr.status_code == 200:
            status = sr.json()
        elif sr.status_code == 401:
            st.error("Session expired — please log in again.")
            st.session_state.auth_token = ""
            st.rerun()
    except Exception as e:
        st.error(f"Backend not reachable: {e}")

    if status:
        try:
            rr = _api_get(
                f"/search/results/{st.session_state.active_job_id}",
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

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Results",     len(company_live))
        c2.metric("🟢 High",     high_n)
        c3.metric("🟡 Medium",   medium_n)
        c4.metric("🔴 Has Gaps", gap_n)

        st.caption(
            f"Status: **{status.get('status','—')}** | "
            f"Pages: {status.get('pages_scanned',0)} | "
            f"Saved: {status.get('saved_total',0)}"
        )

        if company_live:
            _show_table(pd.DataFrame(company_live), key_suffix="live")

            st.markdown("---")
            st.markdown("#### 🔁 Find Similar Leads")
            selectable = [r for r in company_live if r.get("result_index") is not None]
            if selectable:
                options = {}
                for row in sorted(selectable,
                                  key=lambda r: float(r.get("final_score", 0) or 0),
                                  reverse=True):
                    idx   = int(row.get("result_index"))
                    name  = row.get("company", "Unknown")
                    score = float(row.get("final_score", 0) or 0)
                    gaps  = row.get("compliance_gaps", [])
                    tag   = " ⚠️" if isinstance(gaps, list) and gaps else ""
                    options[f"#{idx} | {name}{tag} | {score:.3f}"] = idx

                selected_label        = st.selectbox("Pick a lead", list(options.keys()),
                                                     key="mlt_lead")
                selected_result_index = options[selected_label]
                selected_seed         = _seed_by_result_index(selectable, selected_result_index)
                similar_limit         = st.slider("How many similar?", 3, 20, 8, key="mlt_lim")

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Find Similar", key="mlt_btn"):
                        try:
                            resp = _api_get(
                                f"/search/more-like-this/{st.session_state.active_job_id}",
                                params={"result_index": selected_result_index,
                                        "limit": similar_limit},
                                timeout=30)
                            if resp.status_code == 200:
                                st.session_state.mlt_results           = resp.json().get("results", [])
                                st.session_state.mlt_seed_result_index = selected_result_index
                                st.session_state.mlt_seed_company      = selected_seed.get("company", "")
                            else:
                                st.error("Could not find similar leads")
                        except Exception as e:
                            st.error(f"Backend not reachable: {e}")
                with b2:
                    if st.button("New Search Like This", key="mlt_new"):
                        gq = _build_more_like_query(selected_seed)
                        if gq:
                            _start_background_search(
                                gq, scan_all_remaining, country_filter,
                                trusted_only, reset_results=True
                            )
                            st.rerun()

                if st.session_state.mlt_results:
                    st.caption(f"Similar to: {st.session_state.mlt_seed_company}")
                    _show_table(pd.DataFrame(st.session_state.mlt_results), key_suffix="sim")

        sv = status.get("status")
        if sv in ("running", "queued"):
            st.info("⏳ Search running — refreshing…")
            time.sleep(POLL_SECONDS)
            st.rerun()
        elif sv == "completed":
            jid = status.get("job_id", "")
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
                            scan_all_remaining, country_filter, trusted_only,
                            continue_search=True, reset_results=False)
                        st.rerun()
                with cc2:
                    if st.button("No, Stop"):
                        st.session_state.active_job_id = ""
                        st.success("Search stopped")
            else:
                st.success("✅ Search complete.")
        elif sv == "failed":
            st.error(f"Search failed: {status.get('error', 'Unknown error')}")

st.divider()

# ---------------------------------------------------------------------------
# Saved leads
# ---------------------------------------------------------------------------
st.subheader("📁 Saved Leads")

try:
    lead_params = {"limit": 1000}
    if country_filter.strip():
        lead_params["country_filter"] = country_filter.strip().lower()
    res  = _api_get("/leads", params=lead_params, timeout=20)
    if res.status_code == 401:
        st.error("Session expired — please log in again.")
        st.session_state.auth_token = ""
        st.rerun()
    data = res.json()
except Exception as e:
    st.error(f"Backend not reachable: {e}")
    st.stop()

try:
    gp       = {"country_filter": country_filter} if country_filter else {}
    gr       = _api_get("/leads/gap-summary", params=gp, timeout=10)
    gap_summ = gr.json() if gr.status_code == 200 else {}
except Exception:
    gap_summ = {}

if gap_summ:
    st.markdown("##### Compliance Gap Summary")
    gcols = st.columns(min(len(gap_summ), 5) or 1)
    for i, (gc, cnt) in enumerate(gap_summ.items()):
        gcols[i % len(gcols)].metric(GAP_LABELS.get(gc, gc), cnt)

try:
    cp           = {"country_filter": country_filter} if country_filter else {}
    cr           = _api_get("/leads/channel-summary", params=cp, timeout=10)
    channel_summ = cr.json() if cr.status_code == 200 else {}
except Exception:
    channel_summ = {}

if channel_summ:
    icons = {"Manufacturer":"🏭","Importer":"📦","Trader":"🤝",
             "Wholesaler":"🏢","Distributor":"🚚","Retailer":"🛍️"}
    st.markdown("##### Channel Type Breakdown")
    ccols = st.columns(min(len(channel_summ), 6) or 1)
    for i, (ch, cnt) in enumerate(channel_summ.items()):
        ccols[i % len(ccols)].metric(f"{icons.get(ch,'')} {ch}", cnt)

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

    (tab_all, tab_gaps, tab_mfg, tab_imp,
     tab_no_bis, tab_no_iec, tab_no_gst) = st.tabs([
        "📋 All", "🎯 Compliance Gaps", "🏭 Manufacturers",
        "📦 Importers", "🔴 No BIS", "📦 No IEC", "🧾 No GST",
    ])

    with tab_all:
        _tab_metrics(company_df)
        _show_table(company_df, key_suffix="all")
    with tab_gaps:
        st.info("Companies with at least one compliance gap — highest priority prospects.")
        gdf = _filter_any_gap(company_df)
        _tab_metrics(gdf)
        _show_table(gdf, key_suffix="gaps")
    with tab_mfg:
        mdf = _filter_channel(company_df, "Manufacturer")
        _tab_metrics(mdf)
        _show_table(mdf, key_suffix="mfg")
    with tab_imp:
        idf = _filter_channel(company_df, "Importer")
        _tab_metrics(idf)
        _show_table(idf, key_suffix="imp")
    with tab_no_bis:
        _show_table(_filter_gap(company_df, "no_bis"), key_suffix="no_bis")
    with tab_no_iec:
        _show_table(_filter_gap(company_df, "no_iec"), key_suffix="no_iec")
    with tab_no_gst:
        _show_table(_filter_gap(company_df, "no_gst"), key_suffix="no_gst")

    if not linkedin_df.empty:
        with st.expander("👤 LinkedIn Profiles"):
            ld_cols = ["name","profile","snippet","searched_query","created_at"]
            st.dataframe(linkedin_df[[c for c in ld_cols if c in linkedin_df.columns]],
                         use_container_width=True)
else:
    st.info("No leads yet. Enter a query above and click **Start Search**.")
