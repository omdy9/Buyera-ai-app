import time

import re

import pandas as pd
import requests
import streamlit as st

API = "http://127.0.0.1:8000"
POLL_SECONDS = 2

st.set_page_config(page_title="Global B2B Lead Discovery", layout="wide")


if "active_job_id" not in st.session_state:
    st.session_state.active_job_id = ""
if "active_query" not in st.session_state:
    st.session_state.active_query = ""
if "live_results" not in st.session_state:
    st.session_state.live_results = []
if "live_cursor" not in st.session_state:
    st.session_state.live_cursor = 0
if "new_result_indexes" not in st.session_state:
    st.session_state.new_result_indexes = []
if "notified_jobs" not in st.session_state:
    st.session_state.notified_jobs = []
if "mlt_results" not in st.session_state:
    st.session_state.mlt_results = []
if "mlt_seed_result_index" not in st.session_state:
    st.session_state.mlt_seed_result_index = None
if "mlt_seed_company" not in st.session_state:
    st.session_state.mlt_seed_company = ""


st.title("Global B2B Lead Discovery Engine")
st.caption("Background search with live results")


# ==========================
# Query Input
# ==========================
query = st.text_input(
    "Enter query (example: exporters in dubai)",
    value=st.session_state.active_query,
)
country_options = [
    "Any",
    "canada",
    "italy",
    "dubai",
    "UAE",
    "china",
    "singapore",
    "Custom",
]
selected_country = st.selectbox("Country filter", options=country_options, index=0)
custom_country = ""
if selected_country == "Custom":
    custom_country = st.text_input("Custom country", value="")

country_filter = ""
if selected_country not in {"Any", "Custom"}:
    country_filter = selected_country
elif selected_country == "Custom":
    country_filter = custom_country.strip().lower()
scan_all_remaining = st.checkbox("Continue until no pages", value=False)
trusted_only = st.checkbox("Trusted domains only", value=False)


def _start_background_search(search_query, continue_search=False, reset_results=False):
    try:
        response = requests.post(
            f"{API}/search/start",
            params={
                "query": search_query,
                "continue_search": str(continue_search).lower(),
                "scan_all_remaining": str(scan_all_remaining).lower(),
                "country_filter": country_filter.strip().lower(),
                "trusted_only": str(trusted_only).lower(),
            },
            timeout=30,
        )
        if response.status_code != 200:
            st.error("Backend error while starting background search")
            return False

        data = response.json()
        st.session_state.active_job_id = data.get("job_id", "")
        st.session_state.active_query = search_query

        if reset_results:
            st.session_state.live_results = []
            st.session_state.live_cursor = 0
            st.session_state.new_result_indexes = []
            st.session_state.mlt_results = []
            st.session_state.mlt_seed_result_index = None
            st.session_state.mlt_seed_company = ""

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
    products = seed_row.get("products", [])
    ai_summary = str(seed_row.get("ai_summary", "")).strip()
    company = str(seed_row.get("company", "")).strip()

    product_text = ""
    if isinstance(products, list):
        product_text = " ".join(str(p).strip() for p in products[:2] if str(p).strip())

    if not product_text and ai_summary:
        stop_words = {
            "about", "their", "there", "which", "where", "while", "would", "could",
            "company", "companies", "service", "services", "business", "global",
            "offers", "offer", "provides", "provide", "based", "using", "with",
        }
        tokens = [
            t for t in re.findall(r"[a-zA-Z]{4,}", ai_summary.lower())
            if t not in stop_words
        ]
        product_text = " ".join(list(dict.fromkeys(tokens))[:4])

    query_parts = [searched_query, product_text]
    query = " ".join(p for p in query_parts if p).strip()
    if not query:
        query = company
    return query


col1, col2, col3 = st.columns(3)

with col1:
    if st.button("Start Background Search"):
        if not query.strip():
            st.warning("Please enter a query")
        else:
            _start_background_search(query.strip(), continue_search=False, reset_results=True)

with col2:
    if st.button("Refresh"):
        st.rerun()

with col3:
    if st.button("Clear All Leads"):
        try:
            requests.delete(f"{API}/clear", timeout=15)
            st.session_state.active_job_id = ""
            st.session_state.active_query = ""
            st.session_state.live_results = []
            st.session_state.live_cursor = 0
            st.session_state.new_result_indexes = []
            st.session_state.notified_jobs = []
            st.session_state.mlt_results = []
            st.session_state.mlt_seed_result_index = None
            st.session_state.mlt_seed_company = ""
            st.warning("All leads and search state cleared")
            st.rerun()
        except Exception:
            st.error("Backend not running")

st.divider()


# ==========================
# Live Background Job
# ==========================
if st.session_state.active_job_id:
    st.subheader("Background Search Progress")

    status = None
    try:
        status_resp = requests.get(
            f"{API}/search/status/{st.session_state.active_job_id}",
            timeout=20,
        )
        if status_resp.status_code == 200:
            status = status_resp.json()
        else:
            st.error("Unable to read background search status")
    except Exception:
        st.error("Backend not reachable for background status")

    if status:
        try:
            result_resp = requests.get(
                f"{API}/search/results/{st.session_state.active_job_id}",
                params={"since": st.session_state.live_cursor},
                timeout=20,
            )
            if result_resp.status_code == 200:
                payload = result_resp.json()
                new_items = payload.get("results", [])
                if new_items:
                    st.session_state.live_results.extend(new_items)
                st.session_state.new_result_indexes = [
                    item.get("result_index")
                    for item in new_items
                    if item.get("result_index") is not None
                ]
                st.session_state.live_cursor = int(payload.get("next_since", st.session_state.live_cursor))
        except Exception:
            st.error("Backend not reachable for incremental results")

        company_live = [
            x for x in st.session_state.live_results
            if x.get("source") != "linkedin_semantic"
        ]

        high_count = sum(1 for x in company_live if str(x.get("importance", "")).lower() == "high")
        medium_count = sum(1 for x in company_live if str(x.get("importance", "")).lower() == "medium")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Live Company Results", len(company_live))
        with c2:
            st.metric("High Importance", high_count)
        with c3:
            st.metric("Medium Importance", medium_count)
        st.caption(
            f"Status: {status.get('status')} | Pages scanned: {status.get('pages_scanned', 0)} | "
            f"Saved total: {status.get('saved_total', 0)}"
        )

        if company_live:
            live_df = pd.DataFrame(company_live)

            if "final_score" in live_df.columns:
                live_df = live_df.sort_values("final_score", ascending=False)
            elif "result_index" in live_df.columns:
                live_df = live_df.sort_values("result_index", ascending=False)
                live_df = live_df.set_index("result_index", drop=False)

            live_cols = [
                "company",
                "importance",
                "final_score",
                "domain_authority",
                "contact_presence",
                "email",
                "phone",
                "website",
                "ai_summary",
                "products",
                "llm_relevant",
                "semantic_score",
                "keyword_score",
                "country_filter",
                "searched_query",
                "created_at",
                "source",
            ]
            live_df = live_df[[c for c in live_cols if c in live_df.columns]]

            if "result_index" in pd.DataFrame(company_live).columns:
                highlight_set = set(st.session_state.new_result_indexes)

                def _highlight_new(row):
                    styles = [""] * len(row)
                    row_index = row.name
                    if row_index in highlight_set:
                        styles = ["background-color: #fff3cd"] * len(row)

                    importance = str(row.get("importance", "")).lower()
                    if importance == "high":
                        styles = [
                            f"{s}; background-color: #d1fae5" if s else "background-color: #d1fae5"
                            for s in styles
                        ]
                    elif importance == "medium":
                        styles = [
                            f"{s}; background-color: #fef3c7" if s else "background-color: #fef3c7"
                            for s in styles
                        ]
                    return styles

                st.dataframe(
                    live_df.style.apply(_highlight_new, axis=1),
                    use_container_width=True,
                )
            else:
                st.dataframe(live_df, use_container_width=True)

            selectable_rows = [
                row for row in company_live
                if row.get("result_index") is not None
            ]
            if selectable_rows:
                st.markdown("#### Like a Lead and Find Similar")
                option_labels = []
                label_to_index = {}

                for row in sorted(
                    selectable_rows,
                    key=lambda r: float(r.get("final_score", 0) or 0),
                    reverse=True,
                ):
                    idx = int(row.get("result_index"))
                    company_name = row.get("company", "Unknown")
                    score = float(row.get("final_score", 0) or 0)
                    label = f"#{idx} | {company_name} | score {score:.3f}"
                    option_labels.append(label)
                    label_to_index[label] = idx

                selected_label = st.selectbox(
                    "Select a lead you like",
                    options=option_labels,
                    key="mlt_selected_lead",
                )
                selected_result_index = int(label_to_index[selected_label])
                selected_seed = _seed_by_result_index(selectable_rows, selected_result_index)
                similar_limit = st.slider(
                    "How many similar leads?",
                    min_value=3,
                    max_value=20,
                    value=8,
                    key="mlt_limit",
                )

                b1, b2 = st.columns(2)
                with b1:
                    if st.button("Find Similar (Current Results)", key="mlt_btn"):
                        try:
                            resp = requests.get(
                                f"{API}/search/more-like-this/{st.session_state.active_job_id}",
                                params={
                                    "result_index": selected_result_index,
                                    "limit": int(similar_limit),
                                },
                                timeout=30,
                            )
                            if resp.status_code == 200:
                                payload = resp.json()
                                st.session_state.mlt_results = payload.get("results", [])
                                st.session_state.mlt_seed_result_index = selected_result_index
                                st.session_state.mlt_seed_company = selected_seed.get("company", "")
                            else:
                                st.error("Unable to find similar leads from current results")
                        except Exception:
                            st.error("Backend not reachable for similar-leads search")

                with b2:
                    if st.button("Start New Search Like This Lead", key="mlt_new_search_btn"):
                        generated_query = _build_more_like_query(selected_seed)
                        if not generated_query:
                            st.warning("Could not build a query from this lead")
                        else:
                            started = _start_background_search(
                                generated_query,
                                continue_search=False,
                                reset_results=True,
                            )
                            if started:
                                st.info(f'Started new search from liked lead: "{generated_query}"')
                                st.rerun()

                if st.session_state.mlt_results:
                    seed_name = st.session_state.mlt_seed_company or "selected lead"
                    st.caption(f'Similar leads for: {seed_name}')
                    sim_df = pd.DataFrame(st.session_state.mlt_results)
                    sim_cols = [
                        "company",
                        "more_like_this_score",
                        "similarity_score",
                        "importance",
                        "final_score",
                        "email",
                        "phone",
                        "website",
                        "ai_summary",
                        "products",
                    ]
                    sim_df = sim_df[[c for c in sim_cols if c in sim_df.columns]]
                    st.dataframe(sim_df, use_container_width=True)

        status_value = status.get("status")

        if status_value == "running" or status_value == "queued":
            st.info("Search is running in background. New results will appear automatically.")
            time.sleep(POLL_SECONDS)
            st.rerun()

        elif status_value == "completed":
            job_id = status.get("job_id", "")
            if job_id and job_id not in st.session_state.notified_jobs:
                st.toast("Search complete")
                st.session_state.notified_jobs.append(job_id)

            if status.get("ask_continue"):
                st.warning("Search complete for this batch. Do you want to continue?")
                c1, c2 = st.columns(2)
                with c1:
                    if st.button("Yes, Continue Search"):
                        _start_background_search(
                            st.session_state.active_query,
                            continue_search=True,
                            reset_results=False,
                        )
                        st.rerun()
                with c2:
                    if st.button("No, Stop"):
                        st.session_state.active_job_id = ""
                        st.success("Search stopped")
            else:
                st.success("Search complete. No more pages left.")

        elif status_value == "failed":
            st.error(f"Search failed: {status.get('error', 'Unknown error')}")

st.divider()


# ==========================
# Saved Leads (Database)
# ==========================
st.subheader("Saved Leads")

try:
    lead_params = {"limit": 1000}
    if country_filter.strip():
        lead_params["country_filter"] = country_filter.strip().lower()
    res = requests.get(f"{API}/leads", params=lead_params, timeout=20)
    data = res.json()
except Exception:
    st.error("Backend not reachable. Start FastAPI first.")
    st.stop()

if data:
    df = pd.DataFrame(data)

    if "source" in df.columns:
        company_df = df[df["source"] != "linkedin_semantic"].copy()
        linkedin_df = df[df["source"] == "linkedin_semantic"].copy()
    else:
        company_df = df.copy()
        linkedin_df = pd.DataFrame()

    company_cols = [
        "company",
        "importance",
        "final_score",
        "domain_authority",
        "contact_presence",
        "email",
        "phone",
        "website",
        "ai_summary",
        "products",
        "llm_relevant",
        "semantic_score",
        "keyword_score",
        "country_filter",
        "searched_query",
        "created_at",
        "source",
    ]
    company_df = company_df[[c for c in company_cols if c in company_df.columns]]

    if "final_score" in company_df.columns:
        company_df = company_df.sort_values("final_score", ascending=False)

    high_total = 0
    if "importance" in company_df.columns:
        high_total = int((company_df["importance"].astype(str).str.lower() == "high").sum())

    m1, m2 = st.columns(2)
    with m1:
        st.metric("Total Company Leads", len(company_df))
    with m2:
        st.metric("High Importance Leads", high_total)
    st.dataframe(company_df, use_container_width=True)

    csv = company_df.to_csv(index=False).encode("utf-8")
    st.download_button("Download Company CSV", csv, "company_leads.csv", "text/csv")

    if not linkedin_df.empty:
        with st.expander("LinkedIn Profiles"):
            linkedin_cols = [
                "name",
                "profile",
                "snippet",
                "searched_query",
                "created_at",
                "source",
            ]
            linkedin_df = linkedin_df[[c for c in linkedin_cols if c in linkedin_df.columns]]
            st.dataframe(linkedin_df, use_container_width=True)
else:
    st.info("No leads yet. Run discovery.")
