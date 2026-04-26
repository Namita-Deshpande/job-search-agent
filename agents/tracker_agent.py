# ── Config ────────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
DATA_FILE = "data/applications.json"
# ─────────────────────────────────────────────────────────────────────────────

import json
import os
import uuid
from datetime import date, datetime
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

STATUSES = [
    "Wishlist",
    "Applied",
    "Phone Screen",
    "Interview",
    "Final Round",
    "Offer",
    "Accepted",
    "Rejected",
    "Withdrawn",
]

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def load_applications() -> list[dict]:
    path = Path(DATA_FILE)
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


def save_applications(apps: list[dict]) -> None:
    path = Path(DATA_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(apps, f, indent=2)


def add_application(
    company: str,
    role: str,
    url: str = "",
    status: str = "Applied",
    date_applied: str = "",
    salary_range: str = "",
    notes: str = "",
) -> dict:
    apps = load_applications()
    now = datetime.now().isoformat()
    app = {
        "id": str(uuid.uuid4()),
        "company": company,
        "role": role,
        "url": url,
        "status": status,
        "date_applied": date_applied or str(date.today()),
        "salary_range": salary_range,
        "notes": notes,
        "created_at": now,
        "updated_at": now,
    }
    apps.append(app)
    save_applications(apps)
    return app


def update_application(app_id: str, **kwargs) -> dict:
    apps = load_applications()
    for app in apps:
        if app["id"] == app_id:
            kwargs["updated_at"] = datetime.now().isoformat()
            app.update(kwargs)
            save_applications(apps)
            return app
    raise ValueError(f"Application {app_id} not found")


def delete_application(app_id: str) -> None:
    apps = load_applications()
    save_applications([a for a in apps if a["id"] != app_id])


def get_pipeline_summary(apps: list[dict]) -> dict:
    summary = {s: 0 for s in STATUSES}
    for app in apps:
        s = app.get("status", "Applied")
        if s in summary:
            summary[s] += 1
    return summary


_ANALYSIS_SYSTEM = """\
You are a career coach reviewing a job seeker's application pipeline.
Give honest, specific, actionable insights — no generic advice.
Cover: pipeline health, conversion rates between stages, any patterns you notice, and exactly 3 concrete next steps.
Under 250 words. Plain text only — no markdown headers or bullet symbols."""


def analyze_pipeline(apps: list[dict]) -> str:
    if not apps:
        return "No applications yet. Add your first job application to get started!"

    summary = get_pipeline_summary(apps)
    active_statuses = {"Applied", "Phone Screen", "Interview", "Final Round"}
    active = sum(summary[s] for s in active_statuses)

    lines = [
        f"Total applications: {len(apps)}",
        f"Active in pipeline: {active}",
        "Status breakdown: " + ", ".join(f"{v} {k}" for k, v in summary.items() if v > 0),
        "",
        "Applications:",
    ]
    for a in apps:
        note = f" | Notes: {a['notes']}" if a.get("notes") else ""
        lines.append(
            f"- {a['company']} | {a['role']} | {a['status']} | Applied: {a.get('date_applied', 'N/A')}{note}"
        )

    client = _get_client()
    response = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=[
            {
                "type": "text",
                "text": _ANALYSIS_SYSTEM,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "\n".join(lines)}],
    )
    return response.content[0].text
