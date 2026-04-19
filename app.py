import io
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

load_dotenv()

from agents.tailor_agent import tailor_cv

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


# ── Page ──────────────────────────────────────────────────────────────────────

st.title("💼 Job Search Command Centre")
st.caption("Tailor Agent — powered by Claude")

col_left, col_right = st.columns(2)

with col_left:
    st.subheader("Your CV")
    uploaded = st.file_uploader("Upload your CV", type=["docx", "pdf"])

with col_right:
    st.subheader("Job Description")
    job_desc = st.text_area("Paste the job description", height=260, placeholder="Paste the full job posting here…")

# Cache extracted CV text in session state so reruns don't re-read the file
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

    # ── Match score ──────────────────────────────────────────────────────────
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
        st.write("")  # vertical spacing
        st.progress(score / 100)

    st.divider()

    # ── Keywords ─────────────────────────────────────────────────────────────
    st.subheader("Top Keywords Identified")
    st.markdown(_badge_html(result["keywords"]), unsafe_allow_html=True)

    st.divider()

    # ── Tailored CV preview ───────────────────────────────────────────────────
    with st.expander("📄 Tailored CV", expanded=True):
        st.text_area(
            label="tailored_cv",
            value=result["tailored_cv"],
            height=420,
            label_visibility="collapsed",
        )

    # ── Cover letter preview ──────────────────────────────────────────────────
    with st.expander("✉️ Cover Letter", expanded=True):
        st.text_area(
            label="cover_letter",
            value=result["cover_letter"],
            height=280,
            label_visibility="collapsed",
        )

    # ── Download ──────────────────────────────────────────────────────────────
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
