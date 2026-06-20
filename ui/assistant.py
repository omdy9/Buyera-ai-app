"""
ui/assistant.py — AI Assistant: guided research, verified contacts only
=========================================================================
A separate full-screen chat-style page. Reuses the same backend (_api_post/
_api_get helpers and auth pattern) as ui/app.py — import this module from
app.py or run it as its own Streamlit page in a multipage app.

Flow:
  1. User answers adaptive questions (LLM-driven, one at a time)
  2. Once the assistant has enough info, it kicks off /assistant/research
  3. Progress is polled and shown live (searching → verifying → done)
  4. Only leads with deliverable email AND valid phone are shown
"""

import time
import pandas as pd
import streamlit as st
import requests
import os


def _get_api_url() -> str:
    try:
        url = st.secrets.get("BACKEND_URL", "")
        if url:
            return url.rstrip("/")
    except Exception:
        pass
    return os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")


API = _get_api_url()


def _auth_headers() -> dict:
    token = st.session_state.get("auth_token", "")
    return {"X-User-Token": token} if token else {}


def _api_post(path, **kwargs):
    return requests.post(f"{API}{path}", headers=_auth_headers(),
                         timeout=kwargs.pop("timeout", 30), **kwargs)


def _api_get(path, **kwargs):
    return requests.get(f"{API}{path}", headers=_auth_headers(),
                        timeout=kwargs.pop("timeout", 20), **kwargs)


# ---------------------------------------------------------------------------
# Session state for this page
# ---------------------------------------------------------------------------
_ASSISTANT_DEFAULTS = {
    "asst_history":      [],   # [{"question":..., "answer":..., "field":...}]
    "asst_ready":        False,
    "asst_brief":        {},
    "asst_job_id":       "",
    "asst_pending_q":    "",
    "asst_pending_field":"",
}
for k, v in _ASSISTANT_DEFAULTS.items():
    if k not in st.session_state:
        st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()


def _reset_assistant():
    for k, v in _ASSISTANT_DEFAULTS.items():
        st.session_state[k] = v if not isinstance(v, (list, dict)) else type(v)()


def _fetch_next_question():
    """Call /assistant/ask with current history."""
    try:
        history_payload = [
            {"question": t["question"], "answer": t["answer"], "field": t["field"]}
            for t in st.session_state.asst_history
        ]
        r = _api_post("/assistant/ask", json={"history": history_payload}, timeout=20)
        if r.status_code == 200:
            d = r.json()
            if d.get("ready"):
                st.session_state.asst_ready = True
                st.session_state.asst_brief = d.get("brief_so_far", {})
            else:
                st.session_state.asst_pending_q     = d.get("question", "")
                st.session_state.asst_pending_field = d.get("field", "")
        else:
            st.error(f"Assistant error: {r.text}")
    except Exception as e:
        st.error(f"Cannot reach server: {e}")


def _render_chat_bubbles():
    """Render the conversation so far as chat bubbles."""
    for turn in st.session_state.asst_history:
        with st.chat_message("assistant"):
            st.write(turn["question"])
        with st.chat_message("user"):
            st.write(turn["answer"])


def _render_question_stage():
    st.markdown("""
    <div style="text-align:center;margin:10px 0 24px">
      <div style="font-size:1.6rem;font-weight:800;color:#1e40af">🤖 AI Lead Research Assistant</div>
      <div style="color:#64748b;font-size:0.9rem;margin-top:4px">
        I'll ask a few questions, then find companies with <strong>verified</strong> emails and phone numbers only.
      </div>
    </div>
    """, unsafe_allow_html=True)

    _render_chat_bubbles()

    # First load — fetch the very first question
    if not st.session_state.asst_history and not st.session_state.asst_pending_q:
        with st.spinner("Thinking of the first question..."):
            _fetch_next_question()
        st.rerun()

    if st.session_state.asst_ready:
        st.success("✅ Got everything I need. Ready to start verified research.")
        st.markdown("**Summary of what I'll search for:**")
        brief = st.session_state.asst_brief
        for k, v in brief.items():
            if v:
                st.markdown(f"- **{k.replace('_',' ').title()}:** {v}")

        c1, c2 = st.columns(2)
        with c1:
            if st.button("🔍 Start Verified Research", type="primary", use_container_width=True):
                try:
                    r = _api_post("/assistant/research",
                                 json={"brief": st.session_state.asst_brief}, timeout=20)
                    if r.status_code == 200:
                        st.session_state.asst_job_id = r.json().get("job_id", "")
                        st.rerun()
                    else:
                        st.error(f"Could not start research: {r.text}")
                except Exception as e:
                    st.error(f"Cannot reach server: {e}")
        with c2:
            if st.button("↺ Start Over", use_container_width=True):
                _reset_assistant()
                st.rerun()
        return

    # Show pending question with a text input to answer it
    with st.chat_message("assistant"):
        st.write(st.session_state.asst_pending_q or "What kind of leads are you looking for?")

    answer = st.chat_input("Type your answer...")
    if answer:
        st.session_state.asst_history.append({
            "question": st.session_state.asst_pending_q,
            "answer":   answer,
            "field":    st.session_state.asst_pending_field,
        })
        st.session_state.asst_pending_q     = ""
        st.session_state.asst_pending_field = ""
        with st.spinner("Thinking..."):
            _fetch_next_question()
        st.rerun()


def _render_research_progress():
    job_id = st.session_state.asst_job_id
    try:
        r = _api_get(f"/assistant/status/{job_id}", timeout=20)
    except Exception as e:
        st.error(f"Cannot reach server: {e}")
        return

    if r.status_code != 200:
        st.error("Could not load job status.")
        return

    status = r.json()
    stage  = status.get("stage", "queued")
    detail = status.get("stage_detail", {}) or {}
    sv     = status.get("status", "")

    st.markdown("""
    <div style="text-align:center;margin:10px 0 20px">
      <div style="font-size:1.4rem;font-weight:800;color:#1e40af">🔍 Researching with verification...</div>
    </div>
    """, unsafe_allow_html=True)

    stage_labels = {
        "queued":            "⏳ Queued...",
        "searching":         f"🔎 Searching for companies matching: *{detail.get('query','')}*",
        "found_candidates":  f"📋 Found {detail.get('count',0)} candidate companies — now verifying contacts",
        "verifying":         f"✅ Verifying contacts: {detail.get('done',0)}/{detail.get('total',0)} checked · {detail.get('verified_so_far',0)} passed so far",
        "done":              "🎉 Done!",
    }
    st.info(stage_labels.get(stage, "Working..."))

    if stage in ("verifying", "found_candidates") and detail.get("total"):
        pct = detail.get("done", 0) / max(1, detail.get("total", 1))
        st.progress(min(pct, 1.0))

    if sv == "completed":
        verified = status.get("verified_count", 0)
        total    = status.get("total_candidates", 0)
        st.success(f"✅ Research complete — **{verified} of {total}** companies have a "
                  f"verified, deliverable email AND a valid phone number.")
        _render_verified_results(job_id)

        if st.button("🔄 New Research", type="secondary"):
            _reset_assistant()
            st.rerun()

    elif sv == "failed":
        st.error(f"Research failed: {status.get('error','Unknown error')}")
        if st.button("↺ Try Again"):
            _reset_assistant()
            st.rerun()

    else:
        time.sleep(2)
        st.rerun()


def _render_verified_results(job_id: str):
    try:
        r = _api_get(f"/search/results/{job_id}", timeout=20)
    except Exception as e:
        st.error(f"Cannot reach server: {e}")
        return

    if r.status_code != 200:
        st.warning("Could not load results.")
        return

    leads = r.json().get("results", [])
    if not leads:
        st.warning("No companies passed strict verification for this brief. "
                  "Try broadening your location or industry.")
        return

    st.markdown(f"### {len(leads)} Verified Companies")

    for lead in leads:
        company  = lead.get("company", "Unknown")
        email    = lead.get("email", "")
        phone    = lead.get("phone", "")
        website  = lead.get("active_website", lead.get("website", ""))
        ev       = lead.get("email_verification", {}) or {}
        pv       = lead.get("phone_verification", {}) or {}
        gaps     = lead.get("compliance_gaps", [])

        gap_text = ("⚠️ " + ", ".join(gaps)) if gaps else "✓ No compliance issues found"

        st.markdown(f"""
        <div style="background:white;border:1px solid #e2e8f0;border-radius:12px;
                    padding:16px 20px;margin-bottom:10px;">
          <div style="font-size:1rem;font-weight:700;color:#1e293b">{company}</div>
          <div style="font-size:0.82rem;color:#374151;margin-top:6px">
            📧 <strong>{email}</strong>
            <span style="background:#dcfce7;color:#166534;padding:1px 8px;border-radius:10px;
                        font-size:0.7rem;margin-left:6px">✓ Deliverable (score {ev.get('score','?')})</span>
          </div>
          <div style="font-size:0.82rem;color:#374151;margin-top:4px">
            📞 <strong>{phone}</strong>
            <span style="background:#dcfce7;color:#166534;padding:1px 8px;border-radius:10px;
                        font-size:0.7rem;margin-left:6px">✓ Valid ({pv.get('country','—')})</span>
          </div>
          {"<div style='font-size:0.78rem;color:#64748b;margin-top:6px'>🌐 <a href='"+website+"' target='_blank'>"+website+"</a></div>" if website else ""}
          <div style="font-size:0.76rem;color:#92400e;margin-top:8px">{gap_text}</div>
        </div>
        """, unsafe_allow_html=True)

    df = pd.DataFrame(leads)
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Download verified leads as CSV", data=csv,
                       file_name="verified_leads.csv", mime="text/csv")


def render_assistant_page():
    """Entry point — call this from your multipage router."""
    if not st.session_state.get("auth_token"):
        st.warning("Please sign in first.")
        return

    if st.session_state.asst_job_id:
        _render_research_progress()
    else:
        _render_question_stage()
