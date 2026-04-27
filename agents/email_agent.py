# ── Config ────────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 256
EMAIL_LOG_FILE = "data/email_log.json"
# ─────────────────────────────────────────────────────────────────────────────

import json
import os
import smtplib
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
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


def load_email_log() -> dict:
    path = Path(EMAIL_LOG_FILE)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _save_email_log(entry: dict) -> None:
    path = Path(EMAIL_LOG_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    log = load_email_log()
    log["last_sent"] = entry
    with open(path, "w") as f:
        json.dump(log, f, indent=2)


def build_digest_data(apps: list[dict]) -> dict:
    today = date.today()
    week_ago = today - timedelta(days=7)
    two_weeks_ago = today - timedelta(days=14)

    this_week, last_week = 0, 0
    for app in apps:
        d_str = app.get("date_applied", "")
        try:
            d = date.fromisoformat(d_str)
        except Exception:
            continue
        if d >= week_ago:
            this_week += 1
        elif d >= two_weeks_ago:
            last_week += 1

    status_counts: dict[str, int] = {}
    for app in apps:
        s = app.get("status", "Applied")
        status_counts[s] = status_counts.get(s, 0) + 1

    stale: list[dict] = []
    for app in apps:
        if app.get("status") in ("Wishlist", "Applied"):
            updated = app.get("updated_at", app.get("date_applied", ""))
            try:
                dt = datetime.fromisoformat(updated)
                if (datetime.now() - dt).days >= 7:
                    stale.append(app)
            except Exception:
                pass

    upcoming: list[dict] = []
    for app in apps:
        if app.get("status") in ("Phone Screen", "Interview", "Final Round"):
            upcoming.append(app)

    return {
        "total": len(apps),
        "this_week": this_week,
        "last_week": last_week,
        "status_counts": status_counts,
        "stale": stale,
        "upcoming": upcoming,
    }


_HEALTH_SYSTEM = """\
You are a career coach. Given a job application pipeline summary, return a JSON object with two keys:
{"score": <integer 0-100>, "advice": "<one concrete sentence of actionable advice>"}
No markdown, no preamble."""


def score_pipeline_health(data: dict) -> dict:
    summary = (
        f"Total applications: {data['total']}\n"
        f"Applied this week: {data['this_week']}, last week: {data['last_week']}\n"
        f"Status breakdown: {json.dumps(data['status_counts'])}\n"
        f"Stale (no update 7+ days): {len(data['stale'])}\n"
        f"Active interviews/screens: {len(data['upcoming'])}"
    )
    client = _get_client()
    try:
        resp = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[{"type": "text", "text": _HEALTH_SYSTEM, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": summary}],
        )
        text = resp.content[0].text.strip()
        import re
        fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if fence:
            text = fence.group(1).strip()
        result = json.loads(text)
        return {"score": int(result["score"]), "advice": result["advice"]}
    except Exception:
        return {"score": 50, "advice": "Keep applying consistently and follow up on stale applications."}


def _score_bar(score: int) -> str:
    filled = round(score / 10)
    bar = "█" * filled + "░" * (10 - filled)
    color = "#22c55e" if score >= 70 else "#f59e0b" if score >= 40 else "#ef4444"
    return f'<span style="color:{color};font-family:monospace">{bar}</span> <strong style="color:{color}">{score}/100</strong>'


def build_html_email(data: dict, health: dict) -> str:
    today_str = date.today().strftime("%B %d, %Y")

    status_rows = "".join(
        f"<tr><td style='padding:4px 12px 4px 0'>{s}</td>"
        f"<td style='padding:4px 0'><strong>{c}</strong></td></tr>"
        for s, c in sorted(data["status_counts"].items(), key=lambda x: -x[1])
    )

    stale_rows = "".join(
        f"<li>{a['company']} — {a['role']} ({a['status']})</li>"
        for a in data["stale"][:8]
    ) or "<li>None — great job staying on top of things!</li>"

    upcoming_rows = "".join(
        f"<li>{a['company']} — {a['role']} ({a['status']})</li>"
        for a in data["upcoming"]
    ) or "<li>No active screens or interviews right now.</li>"

    week_delta = data["this_week"] - data["last_week"]
    delta_str = (f"+{week_delta}" if week_delta > 0 else str(week_delta)) if week_delta != 0 else "same as last week"

    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:24px;color:#1f2937">
  <h2 style="margin-bottom:4px">📋 Job Search Weekly Digest</h2>
  <p style="color:#6b7280;margin-top:0">{today_str}</p>
  <hr style="border:none;border-top:1px solid #e5e7eb;margin:16px 0">

  <h3>Pipeline Overview</h3>
  <p>You have <strong>{data['total']} total applications</strong>.
     This week: <strong>{data['this_week']}</strong> new
     ({delta_str} vs last week).</p>

  <table style="border-collapse:collapse;margin-bottom:16px">
    {status_rows}
  </table>

  <h3>Pipeline Health</h3>
  <p>{_score_bar(health['score'])}</p>
  <p style="font-style:italic;color:#374151">💡 {health['advice']}</p>

  <h3>Follow-Up Needed (7+ days stale)</h3>
  <ul>{stale_rows}</ul>

  <h3>Active Screens & Interviews</h3>
  <ul>{upcoming_rows}</ul>

  <hr style="border:none;border-top:1px solid #e5e7eb;margin:24px 0">
  <p style="color:#9ca3af;font-size:12px">Sent by your Job Search Command Centre · Manual trigger</p>
</body>
</html>"""
    return html


def send_digest(apps: list[dict]) -> dict:
    sender = os.getenv("EMAIL_SENDER", "")
    password = os.getenv("EMAIL_PASSWORD", "")
    receiver = os.getenv("EMAIL_RECEIVER", "")

    if not all([sender, password, receiver]):
        raise ValueError("EMAIL_SENDER, EMAIL_PASSWORD, and EMAIL_RECEIVER must be set in .env")

    data = build_digest_data(apps)
    health = score_pipeline_health(data)
    html_body = build_html_email(data, health)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Job Search Digest — {date.today().strftime('%b %d, %Y')}"
    msg["From"] = sender
    msg["To"] = receiver
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(sender, password)
        server.sendmail(sender, receiver, msg.as_string())

    sent_at = datetime.now().isoformat()
    _save_email_log({"sent_at": sent_at, "to": receiver, "total_apps": data["total"]})
    return {"data": data, "health": health, "sent_at": sent_at}
