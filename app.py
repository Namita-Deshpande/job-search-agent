import io
import os
import re
from datetime import datetime
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agents.tailor_agent import tailor_cv
from agents.tracker_agent import (
    STATUSES,
    add_application,
    analyze_pipeline,
    delete_application,
    get_pipeline_summary,
    load_applications,
    update_application,
)
from agents.sourcer_agent import search_jobs
from agents.coach_agent import create_session, generate_prep, get_feedback, save_session

st.set_page_config(
    page_title="Job Search Command Centre",
    page_icon="💼",
    layout="wide",
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_text(uploaded_file) -> str:
    name = uploaded_file.name.lower()
    raw = uploaded_file.read()
    if name.endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(raw))
        return "\n".join(p.text for p in doc.paragraphs if p.text.strip())
    if name.endswith(".pdf"):
        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(raw))
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    return ""


def _badge_html(keywords: list[str]) -> str:
    badges = " ".join(
        f'<span style="background:#1E3A5F;color:#fff;padding:5px 13px;'
        f'border-radius:20px;font-size:0.82em;margin:3px;display:inline-block;">'
        f"{kw}</span>"
        for kw in keywords
    )
    return f'<div style="line-height:2.2;">{badges}</div>'


def _score_color(score: int) -> str:
    if score >= 70:
        return "#2ecc71"
    if score >= 40:
        return "#f39c12"
    return "#e74c3c"


def _status_color(status: str) -> str:
    return {
        "Wishlist":     "#6c757d",
        "Applied":      "#1E3A5F",
        "Phone Screen": "#0077b6",
        "Interview":    "#f39c12",
        "Final Round":  "#e67e22",
        "Offer":        "#2ecc71",
        "Accepted":     "#27ae60",
        "Rejected":     "#e74c3c",
        "Withdrawn":    "#95a5a6",
    }.get(status, "#1E3A5F")


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("💼 Job Search Command Centre")

tab1, tab2, tab3, tab4 = st.tabs(["✨ Tailor CV", "📋 Track Applications", "🔍 Source Jobs", "🎯 Interview Coach"])


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 1 — Tailor CV
# ═══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.caption("Tailor Agent — powered by Claude")

    col_left, col_right = st.columns(2)

    with col_left:
        st.subheader("Your CV")
        uploaded = st.file_uploader("Upload your CV", type=["docx", "pdf"])

    with col_right:
        st.subheader("Job Description")
        job_desc = st.text_area(
            "Paste the job description",
            height=260,
            placeholder="Paste the full job posting here…",
        )

    cv_text = ""
    if uploaded:
        file_key = uploaded.name + str(uploaded.size)
        if st.session_state.get("_file_key") != file_key:
            cv_text = _extract_text(uploaded)
            st.session_state["_file_key"] = file_key
            st.session_state["_cv_text"] = cv_text
        else:
            cv_text = st.session_state.get("_cv_text", "")

        with st.expander("Preview extracted CV text"):
            preview = cv_text[:2000] + ("…" if len(cv_text) > 2000 else "")
            st.text(preview)

    st.divider()

    ready = bool(cv_text.strip() and job_desc.strip())
    if not ready and (uploaded or job_desc):
        st.info("Upload a CV **and** paste a job description to enable generation.")

    if st.button("✨ Generate Tailored CV", disabled=not ready, type="primary"):
        with st.spinner("Claude is tailoring your CV — this takes ~15 seconds…"):
            try:
                result = tailor_cv(cv_text, job_desc)
            except Exception as exc:
                st.error(f"Something went wrong: {exc}")
                st.stop()

        st.success("Tailoring complete!")

        score = int(result["match_score"])
        color = _score_color(score)

        score_col, bar_col = st.columns([1, 5])
        with score_col:
            st.markdown(
                f'<div style="font-size:2.4rem;font-weight:700;color:{color};">'
                f'{score}<span style="font-size:1rem;color:#888;"> / 100</span></div>'
                f'<div style="font-size:0.85rem;color:#888;">Match Score</div>',
                unsafe_allow_html=True,
            )
        with bar_col:
            st.write("")
            st.progress(score / 100)

        st.divider()

        st.subheader("Top Keywords Identified")
        st.markdown(_badge_html(result["keywords"]), unsafe_allow_html=True)

        st.divider()

        with st.expander("📄 Tailored CV", expanded=True):
            st.text_area(
                label="tailored_cv",
                value=result["tailored_cv"],
                height=420,
                label_visibility="collapsed",
            )

        with st.expander("✉️ Cover Letter", expanded=True):
            st.text_area(
                label="cover_letter",
                value=result["cover_letter"],
                height=280,
                label_visibility="collapsed",
            )

        docx_path = Path(result["output_path"])
        if docx_path.exists():
            with open(docx_path, "rb") as f:
                st.download_button(
                    label="⬇️  Download Tailored CV + Cover Letter (.docx)",
                    data=f.read(),
                    file_name=docx_path.name,
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary",
                )
        else:
            st.warning("Could not locate the generated .docx file.")


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 2 — Track Applications
# ═══════════════════════════════════════════════════════════════════════════════
with tab2:
    st.caption("Tracker Agent — your job search pipeline")

    apps = load_applications()
    summary = get_pipeline_summary(apps)
    active = sum(summary[s] for s in ["Applied", "Phone Screen", "Interview", "Final Round"])

    # ── Metrics ───────────────────────────────────────────────────────────────
    m1, m2, m3, m4, m5 = st.columns(5)
    m1.metric("Total", len(apps))
    m2.metric("Wishlist", summary["Wishlist"])
    m3.metric("Active", active)
    m4.metric("Offers", summary["Offer"] + summary["Accepted"])
    m5.metric("Rejected", summary["Rejected"])

    st.divider()

    # ── Controls: filter + AI insights ───────────────────────────────────────
    ctrl_left, ctrl_right = st.columns([3, 1])
    with ctrl_left:
        status_filter = st.selectbox(
            "Filter",
            ["All"] + STATUSES,
            label_visibility="collapsed",
        )
    with ctrl_right:
        if st.button("🤖 AI Insights", use_container_width=True):
            with st.spinner("Analyzing your pipeline…"):
                st.session_state["_insights"] = analyze_pipeline(apps)

    if "_insights" in st.session_state:
        st.info(st.session_state["_insights"])

    st.divider()

    # ── Add Application ───────────────────────────────────────────────────────
    with st.expander("➕ Add Application"):
        with st.form("add_form", clear_on_submit=True):
            fc1, fc2 = st.columns(2)
            with fc1:
                new_company = st.text_input("Company *")
                new_status = st.selectbox("Status", STATUSES, index=1)
                new_salary = st.text_input("Salary Range", placeholder="e.g. £50k–£65k")
            with fc2:
                new_role = st.text_input("Role *")
                new_date = st.date_input("Date Applied")
                new_url = st.text_input("Job URL")
            new_notes = st.text_area("Notes", height=80)

            if st.form_submit_button("Add Application", type="primary"):
                if not new_company.strip() or not new_role.strip():
                    st.error("Company and Role are required.")
                else:
                    add_application(
                        company=new_company.strip(),
                        role=new_role.strip(),
                        url=new_url.strip(),
                        status=new_status,
                        date_applied=str(new_date),
                        salary_range=new_salary.strip(),
                        notes=new_notes.strip(),
                    )
                    st.rerun()

    # ── Application cards ─────────────────────────────────────────────────────
    filtered = [
        a for a in apps
        if status_filter == "All" or a.get("status") == status_filter
    ]
    filtered.sort(key=lambda a: a.get("date_applied", ""), reverse=True)

    if not filtered:
        st.write("No applications yet." if not apps else "No applications match this filter.")

    for app in filtered:
        status = app.get("status", "Applied")
        color = _status_color(status)
        expander_label = f"{app['company']}  —  {app['role']}  [{status}]"

        with st.expander(expander_label):
            info_col, edit_col = st.columns([1, 1])

            with info_col:
                st.markdown(
                    f'<span style="background:{color};color:#fff;padding:3px 12px;'
                    f'border-radius:12px;font-size:0.82em;">{status}</span>',
                    unsafe_allow_html=True,
                )
                st.write(f"**Applied:** {app.get('date_applied', '—')}")
                if app.get("salary_range"):
                    st.write(f"**Salary:** {app['salary_range']}")
                if app.get("url"):
                    st.markdown(f"[View Job Posting]({app['url']})")

            with edit_col:
                with st.form(key=f"edit_{app['id']}"):
                    new_s = st.selectbox(
                        "Status",
                        STATUSES,
                        index=STATUSES.index(status) if status in STATUSES else 1,
                    )
                    new_n = st.text_area("Notes", value=app.get("notes", ""), height=80)
                    save_col, del_col = st.columns(2)
                    with save_col:
                        save_clicked = st.form_submit_button(
                            "Save", type="primary", use_container_width=True
                        )
                    with del_col:
                        del_clicked = st.form_submit_button(
                            "Delete", type="secondary", use_container_width=True
                        )

                    if save_clicked:
                        update_application(app["id"], status=new_s, notes=new_n)
                        st.rerun()
                    if del_clicked:
                        delete_application(app["id"])
                        st.rerun()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 3 — Source Jobs
# ═══════════════════════════════════════════════════════════════════════════════
_DEFAULT_TITLES = ["AI Engineer", "Automation Engineer", "ML Engineer", "Python Developer"]

with tab3:
    st.caption("Sourcer Agent — find new roles from Adzuna and Arbeitnow")

    adzuna_ready = bool(os.getenv("ADZUNA_APP_ID") and os.getenv("ADZUNA_API_KEY"))
    if not adzuna_ready:
        st.warning(
            "Adzuna API keys not found. Add **ADZUNA_APP_ID** and **ADZUNA_API_KEY** "
            "to your `.env` file to include Adzuna results. Arbeitnow will still run."
        )

    # ── Search config form ────────────────────────────────────────────────────
    with st.form("sourcer_form"):
        selected_titles = st.multiselect(
            "Job Titles",
            options=_DEFAULT_TITLES,
            default=_DEFAULT_TITLES,
        )
        keywords_raw = st.text_input(
            "Keywords (comma-separated)",
            placeholder="e.g. LLM, FastAPI, Docker, NLP",
        )
        location = st.radio(
            "Location",
            ["Berlin", "Remote", "Both"],
            index=2,
            horizontal=True,
        )
        run_search = st.form_submit_button("🔍 Run Search", type="primary")

    if run_search:
        if not selected_titles:
            st.error("Select at least one job title.")
        else:
            keywords = [k.strip() for k in keywords_raw.split(",") if k.strip()]
            with st.spinner("Searching Adzuna and Arbeitnow — this may take ~20 seconds…"):
                try:
                    jobs, stats = search_jobs(selected_titles, keywords, location)
                    st.session_state["_sourcer_results"] = jobs
                    st.session_state["_sourcer_stats"] = stats
                    st.session_state["_added_jobs"] = set()
                except Exception as exc:
                    st.error(f"Search failed: {exc}")

    # ── Results ───────────────────────────────────────────────────────────────
    if "_sourcer_results" in st.session_state:
        jobs = st.session_state["_sourcer_results"]
        stats = st.session_state["_sourcer_stats"]
        added_jobs: set = st.session_state.get("_added_jobs", set())

        st.divider()
        st.markdown(
            f"**{len(jobs)} new jobs found** &nbsp;·&nbsp; {stats['skipped_duplicates']} duplicates skipped",
            unsafe_allow_html=True,
        )

        # ── Debug panel ───────────────────────────────────────────────────────
        with st.expander("🐛 Debug info"):
            app_id = os.getenv("ADZUNA_APP_ID", "")
            api_key = os.getenv("ADZUNA_API_KEY", "")
            st.markdown("**API keys**")
            st.write(
                f"ADZUNA_APP_ID: `{app_id[:4]}…`" if app_id else "ADZUNA_APP_ID: ❌ not set"
            )
            st.write(
                f"ADZUNA_API_KEY: `{api_key[:4]}…`" if api_key else "ADZUNA_API_KEY: ❌ not set"
            )
            st.markdown("**Fetch counts**")
            st.write(f"Adzuna raw jobs fetched: **{stats['adzuna_raw']}**")
            st.write(f"Arbeitnow raw jobs fetched: **{stats['arbeitnow_raw']}**")
            st.write(f"New (not seen before): **{stats['new_count']}**")
            st.write(f"Skipped as duplicates: **{stats['skipped_duplicates']}**")
            st.write(f"Scored below threshold: **{stats['below_threshold']}**")
            st.markdown("**Score threshold**")
            from agents.sourcer_agent import MIN_SCORE
            st.write(f"Current MIN_SCORE = **{MIN_SCORE}**")
            st.markdown("**Reset seen-jobs cache**")
            st.caption("Clears data/seen_jobs.json so all jobs appear fresh on next search.")
            if st.button("🗑️ Clear seen-jobs cache"):
                from pathlib import Path as _P
                _P("data/seen_jobs.json").unlink(missing_ok=True)
                st.session_state.pop("_sourcer_results", None)
                st.session_state.pop("_sourcer_stats", None)
                st.rerun()

        if not jobs:
            st.info("No jobs above the score threshold this run. Try broadening your keywords or location.")
        else:
            st.write("")
            for i, job in enumerate(jobs):
                score = job["score"]
                badge_color = "#2ecc71" if score >= 80 else ("#f39c12" if score >= 60 else "#e74c3c")

                score_col, info_col = st.columns([1, 7])

                with score_col:
                    st.markdown(
                        f'<div style="background:{badge_color};color:#fff;text-align:center;'
                        f'padding:14px 0;border-radius:8px;font-size:1.5rem;font-weight:700;">'
                        f'{score}</div>',
                        unsafe_allow_html=True,
                    )

                with info_col:
                    title_line = (
                        f"**[{job['title']}]({job['url']})** &nbsp; — &nbsp; {job['company']}"
                        if job.get("url") else f"**{job['title']}** — {job['company']}"
                    )
                    st.markdown(title_line, unsafe_allow_html=True)

                    meta_parts = [job.get("location", ""), job.get("salary", ""), job.get("date_posted", "")]
                    meta = "  ·  ".join(p for p in meta_parts if p)
                    source_badge = (
                        f'<span style="background:#1E3A5F;color:#fff;padding:1px 8px;'
                        f'border-radius:10px;font-size:0.75em;">{job["source"]}</span>'
                    )
                    st.markdown(
                        f'<span style="color:#888;font-size:0.85em;">{meta}</span> &nbsp; {source_badge}',
                        unsafe_allow_html=True,
                    )

                    url = job.get("url", "")
                    if url in added_jobs:
                        st.markdown("**✓ Added to Tracker**")
                    else:
                        if st.button("➕ Add to Tracker", key=f"add_{i}"):
                            add_application(
                                company=job["company"],
                                role=job["title"],
                                url=url,
                                status="Wishlist",
                            )
                            added_jobs.add(url)
                            st.session_state["_added_jobs"] = added_jobs
                            st.rerun()

                st.divider()


# ═══════════════════════════════════════════════════════════════════════════════
# TAB 4 — Interview Coach
# ═══════════════════════════════════════════════════════════════════════════════
with tab4:
    st.caption("Coach Agent — prep and practice for any role")

    # ── SECTION 1: Prep generation ────────────────────────────────────────────
    st.subheader("Generate Interview Prep")

    with st.form("coach_prep_form"):
        coach_company = st.text_input("Company name", placeholder="e.g. Zalando")
        coach_jd = st.text_area(
            "Job description",
            height=220,
            placeholder="Paste the full job posting here…",
        )
        prep_submitted = st.form_submit_button("Generate Prep", type="primary")

    if prep_submitted:
        if not coach_company.strip() or not coach_jd.strip():
            st.error("Enter both a company name and a job description.")
        else:
            with st.spinner("Claude is analysing the role — this takes ~15 seconds…"):
                try:
                    prep = generate_prep(coach_company.strip(), coach_jd.strip())
                    session = create_session(coach_company.strip(), prep["role"], prep)
                    save_session(session)
                    st.session_state["_coach_prep"] = prep
                    st.session_state["_coach_session"] = session
                    st.session_state.pop("_coach_feedback", None)
                except Exception as exc:
                    st.error(f"Prep generation failed: {exc}")

    if "_coach_prep" in st.session_state:
        prep = st.session_state["_coach_prep"]
        session = st.session_state["_coach_session"]

        st.success(f"Prep ready — **{prep['role']}** at **{session['company']}**")

        with st.expander("🏢 About the company"):
            st.write(prep["company_summary"])

        with st.expander("📋 Likely interview rounds"):
            for i, rnd in enumerate(prep["interview_rounds"], 1):
                st.write(f"**Round {i}:** {rnd}")

        with st.expander("⚙️ Technical questions"):
            for i, q in enumerate(prep["technical_questions"], 1):
                st.markdown(f"**{i}.** {q}")

        with st.expander("🧠 Behavioural questions (STAR)"):
            for i, q in enumerate(prep["behavioural_questions"], 1):
                st.markdown(f"**{i}.** {q}")

        with st.expander("❓ Questions to ask the interviewer"):
            for i, q in enumerate(prep["questions_to_ask"], 1):
                st.markdown(f"**{i}.** {q}")

        with st.expander("🚩 Red flags to watch for"):
            for i, rf in enumerate(prep["red_flags"], 1):
                st.markdown(f"**{i}.** {rf}")

        st.divider()

        # ── SECTION 2: Mock interview ─────────────────────────────────────────
        st.subheader("Mock Interview")

        q_options = (
            [f"[Technical] {q}" for q in prep["technical_questions"]]
            + [f"[Behavioural] {q}" for q in prep["behavioural_questions"]]
        )

        with st.form("mock_form"):
            selected_q = st.selectbox("Select a question", q_options)
            answer_input = st.text_area(
                "Your answer",
                height=200,
                placeholder="Type your answer here…",
            )
            feedback_submitted = st.form_submit_button("Get Feedback", type="primary")

        if feedback_submitted:
            if not answer_input.strip():
                st.error("Type an answer before submitting.")
            else:
                # Strip the "[Technical] " / "[Behavioural] " prefix to get the raw question
                raw_question = re.sub(r"^\[(?:Technical|Behavioural)\] ", "", selected_q)
                with st.spinner("Evaluating your answer…"):
                    try:
                        feedback = get_feedback(
                            raw_question,
                            answer_input.strip(),
                            session["company"],
                            session["role"],
                        )
                        st.session_state["_coach_feedback"] = {
                            "question": selected_q,
                            "feedback": feedback,
                        }
                        # Append to session history and persist
                        session["history"].append({
                            "question": selected_q,
                            "score": feedback["score"],
                            "timestamp": datetime.now().isoformat(),
                        })
                        save_session(session)
                    except Exception as exc:
                        st.error(f"Feedback failed: {exc}")

        if "_coach_feedback" in st.session_state:
            fb_data = st.session_state["_coach_feedback"]
            feedback = fb_data["feedback"]
            score = feedback["score"]
            score_color = "#2ecc71" if score >= 80 else ("#f39c12" if score >= 60 else "#e74c3c")

            st.markdown("#### Feedback")

            score_col, bar_col = st.columns([1, 5])
            with score_col:
                st.markdown(
                    f'<div style="font-size:2.4rem;font-weight:700;color:{score_color};">'
                    f'{score}<span style="font-size:1rem;color:#888;"> / 100</span></div>',
                    unsafe_allow_html=True,
                )
            with bar_col:
                st.write("")
                st.progress(score / 100)

            st.markdown("**Strengths**")
            for s in feedback["strengths"]:
                st.markdown(f"✓ {s}")

            st.markdown("**Improvements**")
            for imp in feedback["improvements"]:
                st.markdown(f"→ {imp}")

            with st.expander("💡 Suggested better answer", expanded=True):
                st.text_area(
                    label="better_answer",
                    value=feedback["better_answer"],
                    height=200,
                    label_visibility="collapsed",
                )

        # ── Session history ───────────────────────────────────────────────────
        history = st.session_state.get("_coach_session", {}).get("history", [])
        if history:
            st.divider()
            st.markdown("**Session history**")
            for i, h in enumerate(history, 1):
                score = h["score"]
                color = "#2ecc71" if score >= 80 else ("#f39c12" if score >= 60 else "#e74c3c")
                q_short = h["question"][:80] + ("…" if len(h["question"]) > 80 else "")
                st.markdown(
                    f'Q{i}: {q_short} &nbsp; '
                    f'<span style="color:{color};font-weight:700;">{score}/100</span>',
                    unsafe_allow_html=True,
                )
