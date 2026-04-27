# ── Config ────────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS_PREP = 2048
MAX_TOKENS_FEEDBACK = 1024
SESSIONS_FILE = "data/prep_sessions.json"
# ─────────────────────────────────────────────────────────────────────────────

import json
import os
import re
import uuid
from datetime import date, datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _parse_json(text: str) -> dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


# ── Session persistence ───────────────────────────────────────────────────────

def load_sessions() -> list[dict]:
    path = Path(SESSIONS_FILE)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_session(session: dict) -> None:
    sessions = load_sessions()
    for i, s in enumerate(sessions):
        if s["id"] == session["id"]:
            sessions[i] = session
            break
    else:
        sessions.append(session)
    path = Path(SESSIONS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sessions, f, indent=2)


def create_session(company: str, role: str, prep: dict) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "company": company,
        "role": role,
        "date": str(date.today()),
        "questions": {
            "technical": prep["technical_questions"],
            "behavioural": prep["behavioural_questions"],
        },
        "history": [],
    }


# ── Call 1: prep generation ───────────────────────────────────────────────────

_PREP_SYSTEM = """\
You are an expert career coach preparing a candidate for a specific job interview.

Given a company name and job description, produce a structured prep guide.

Respond ONLY with valid JSON — no markdown fences, no preamble — in this exact shape:
{
  "role": "<job title extracted from the description>",
  "company_summary": "<what this company does — exactly 3 sentences>",
  "interview_rounds": [
    "<Round 1: round name and what to expect in 1-2 sentences>",
    "<Round 2: round name and what to expect in 1-2 sentences>",
    "<Round 3: round name and what to expect in 1-2 sentences>"
  ],
  "technical_questions": [
    "<technical question 1>",
    "<technical question 2>",
    "<technical question 3>",
    "<technical question 4>",
    "<technical question 5>"
  ],
  "behavioural_questions": [
    "<STAR-format behavioural question 1>",
    "<STAR-format behavioural question 2>",
    "<STAR-format behavioural question 3>",
    "<STAR-format behavioural question 4>",
    "<STAR-format behavioural question 5>"
  ],
  "questions_to_ask": [
    "<thoughtful question for the interviewer 1>",
    "<thoughtful question for the interviewer 2>",
    "<thoughtful question for the interviewer 3>"
  ],
  "red_flags": [
    "<specific red flag or watch-out for this role/company type>",
    "<specific red flag or watch-out for this role/company type>"
  ]
}

Rules:
- technical_questions must reference specific technologies, tools, or responsibilities from the job description
- behavioural_questions must open with a STAR cue ("Tell me about a time when…", "Describe a situation where…")
- questions_to_ask must be specific and insightful, not generic (not "What does a typical day look like?")
- red_flags must be concrete and relevant to this specific role and company type, not boilerplate interview advice
"""


def generate_prep(company: str, job_description: str) -> dict:
    """Call 1 — analyse the role and generate interview prep content.

    Returns dict with keys: role, company_summary, interview_rounds,
    technical_questions, behavioural_questions, questions_to_ask, red_flags.
    """
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_PREP,
        system=[
            {
                "type": "text",
                "text": _PREP_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": f"Company: {company}\n\nJob Description:\n{job_description}",
            }
        ],
    )
    result = _parse_json(response.content[0].text)
    required = {
        "role", "company_summary", "interview_rounds",
        "technical_questions", "behavioural_questions",
        "questions_to_ask", "red_flags",
    }
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Prep response missing fields: {missing}")
    return result


# ── Call 2: answer feedback ───────────────────────────────────────────────────

_FEEDBACK_SYSTEM = """\
You are an expert interview coach evaluating a candidate's answer.

Respond ONLY with valid JSON — no markdown fences, no preamble — in this exact shape:
{
  "score": <integer 0-100>,
  "strengths": [
    "<specific strength of this answer>",
    "<specific strength of this answer>"
  ],
  "improvements": [
    "<specific, actionable improvement with a concrete suggestion>",
    "<specific, actionable improvement with a concrete suggestion>"
  ],
  "better_answer": "<a rewritten version that addresses the improvements — preserve the candidate's voice and facts, just make it stronger and more structured>"
}

Scoring guide:
- 80-100: strong, specific, well-structured, concrete examples, quantified where possible
- 60-79: solid but missing specifics, depth, or a clear structure
- 40-59: relevant but vague, too short, or lacks real examples
- 0-39: off-topic, purely generic, or very weak

For improvements: be direct and concrete ("Add the outcome — how many users were affected?" not "Be more specific").
For better_answer: write in first person, keep the candidate's actual experience, just make the structure tighter.
"""


def get_feedback(question: str, answer: str, company: str, role: str) -> dict:
    """Call 2 — score a candidate's answer and return structured feedback.

    Returns dict with keys: score, strengths, improvements, better_answer.
    """
    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS_FEEDBACK,
        system=[
            {
                "type": "text",
                "text": _FEEDBACK_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": (
                    f"Role: {role} at {company}\n\n"
                    f"Interview question: {question}\n\n"
                    f"Candidate's answer: {answer}"
                ),
            }
        ],
    )
    result = _parse_json(response.content[0].text)
    required = {"score", "strengths", "improvements", "better_answer"}
    missing = required - result.keys()
    if missing:
        raise ValueError(f"Feedback response missing fields: {missing}")
    return result
