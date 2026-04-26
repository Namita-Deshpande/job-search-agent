import io
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

tab1, tab2 = st.tabs(["✨ Tailor CV", "📋 Track Applications"])


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
