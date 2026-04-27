# ── Config ────────────────────────────────────────────────────────────────────
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 1024
SEEN_JOBS_FILE = "data/seen_jobs.json"
ADZUNA_BASE_URL = "https://api.adzuna.com/v1/api"
ADZUNA_COUNTRY = "de"
ADZUNA_RESULTS_PER_PAGE = 20
ADZUNA_PAGES = 2
ARBEITNOW_BASE_URL = "https://www.arbeitnow.com/api/job-board-api"
ARBEITNOW_PAGES = 3
MIN_SCORE = 30
REQUEST_TIMEOUT = 10
# ─────────────────────────────────────────────────────────────────────────────

import json
import os
import re
from datetime import datetime
from pathlib import Path

import anthropic
import requests
from dotenv import load_dotenv

load_dotenv()

_client: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _client


def _parse_json(text: str) -> list | dict:
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if fence:
        text = fence.group(1).strip()
    return json.loads(text)


def _load_seen_jobs() -> set[str]:
    path = Path(SEEN_JOBS_FILE)
    if not path.exists():
        return set()
    with open(path) as f:
        return set(json.load(f))


def _save_seen_jobs(seen: set[str]) -> None:
    path = Path(SEEN_JOBS_FILE)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(sorted(seen), f, indent=2)


def _format_date(iso_str: str) -> str:
    try:
        return datetime.fromisoformat(iso_str.replace("Z", "+00:00")).strftime("%Y-%m-%d")
    except Exception:
        return iso_str[:10] if iso_str else ""


def _normalize_adzuna(job: dict) -> dict:
    salary_parts = []
    if job.get("salary_min"):
        salary_parts.append(f"€{int(job['salary_min']):,}")
    if job.get("salary_max"):
        salary_parts.append(f"€{int(job['salary_max']):,}")
    return {
        "title": job.get("title", ""),
        "company": job.get("company", {}).get("display_name", ""),
        "location": job.get("location", {}).get("display_name", ""),
        "salary": " – ".join(salary_parts),
        "url": job.get("redirect_url", ""),
        "source": "Adzuna",
        "date_posted": _format_date(job.get("created", "")),
        "description": job.get("description", ""),
        "score": 0,
    }


def _normalize_arbeitnow(job: dict) -> dict:
    ts = job.get("created_at")
    if isinstance(ts, (int, float)):
        date_posted = datetime.fromtimestamp(ts).strftime("%Y-%m-%d")
    else:
        date_posted = str(ts)[:10] if ts else ""
    return {
        "title": job.get("title", ""),
        "company": job.get("company_name", ""),
        "location": "Remote" if job.get("remote") else job.get("location", ""),
        "salary": "",
        "url": job.get("url", ""),
        "source": "Arbeitnow",
        "date_posted": date_posted,
        "description": job.get("description", ""),
        "score": 0,
    }


def _fetch_adzuna(
    job_titles: list[str], keywords: list[str], location: str
) -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID", "")
    app_key = os.getenv("ADZUNA_API_KEY", "")
    if not app_id or not app_key:
        return []

    base_what = " ".join(job_titles + keywords[:3])

    # Build list of (what, where) search variants based on location
    searches: list[dict] = []
    if location in ("Berlin", "Both"):
        searches.append({"what": base_what, "where": "Berlin"})
    if location in ("Remote", "Both"):
        searches.append({"what": base_what + " remote"})

    raw: list[dict] = []
    for extra_params in searches:
        for page in range(1, ADZUNA_PAGES + 1):
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "results_per_page": ADZUNA_RESULTS_PER_PAGE,
                "content-type": "application/json",
                **extra_params,
            }
            endpoint = f"{ADZUNA_BASE_URL}/jobs/{ADZUNA_COUNTRY}/search/{page}"
            try:
                resp = requests.get(endpoint, params=params, timeout=REQUEST_TIMEOUT)
                resp.raise_for_status()
                raw.extend(resp.json().get("results", []))
            except Exception:
                break

    # Deduplicate within this batch by URL
    seen_urls: set[str] = set()
    deduped = []
    for job in raw:
        url = job.get("redirect_url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(job)

    return [_normalize_adzuna(j) for j in deduped]


def _fetch_arbeitnow(
    job_titles: list[str], keywords: list[str], location: str
) -> list[dict]:
    raw: list[dict] = []

    if location in ("Remote", "Both"):
        for page in range(1, ARBEITNOW_PAGES + 1):
            try:
                resp = requests.get(
                    ARBEITNOW_BASE_URL,
                    params={"remote": "true", "page": page},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                batch = resp.json().get("data", [])
                if not batch:
                    break
                raw.extend(batch)
            except Exception:
                break

    if location in ("Berlin", "Both"):
        for page in range(1, ARBEITNOW_PAGES + 1):
            try:
                resp = requests.get(
                    ARBEITNOW_BASE_URL,
                    params={"page": page},
                    timeout=REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                batch = resp.json().get("data", [])
                if not batch:
                    break
                raw.extend(j for j in batch if "berlin" in j.get("location", "").lower())
            except Exception:
                break

    # Client-side title/keyword relevance filter — keep jobs where a meaningful
    # keyword from the search appears in the title or tags
    search_terms = [
        w.lower()
        for t in job_titles
        for w in t.split()
    ] + [k.lower() for k in keywords]
    meaningful = [t for t in search_terms if len(t) > 3]

    relevant = []
    for job in raw:
        title_lower = job.get("title", "").lower()
        tags_lower = " ".join(job.get("tags", [])).lower()
        if any(term in title_lower or term in tags_lower for term in meaningful):
            relevant.append(job)

    # Deduplicate within this batch by URL
    seen_urls: set[str] = set()
    deduped = []
    for job in relevant:
        url = job.get("url", "")
        if url and url not in seen_urls:
            seen_urls.add(url)
            deduped.append(job)

    return [_normalize_arbeitnow(j) for j in deduped]


_SCORING_SYSTEM = """\
Score each job listing for a candidate on a 0-100 scale.
Criteria:
- Title match (40 pts): how closely does the job title match the candidate's target roles?
- Keyword overlap (40 pts): how many search keywords appear in the title or description snippet?
- Seniority fit (20 pts): is this a mid/senior individual-contributor role? Deduct for internships, graduate schemes, or C-suite titles.
Respond ONLY with a JSON array — no preamble: [{"index": 0, "score": 75}, {"index": 1, "score": 42}, ...]"""


def _score_jobs(
    jobs: list[dict], job_titles: list[str], keywords: list[str]
) -> list[dict]:
    if not jobs:
        return jobs

    target_titles = ", ".join(job_titles)
    target_keywords = ", ".join(keywords) if keywords else "none specified"

    listings = []
    for i, job in enumerate(jobs):
        desc = re.sub(r"<[^>]+>", " ", job.get("description", ""))[:150].strip()
        listings.append(f"{i}. Title: {job['title']} | {desc}")

    user_content = (
        f"Target roles: {target_titles}\n"
        f"Keywords: {target_keywords}\n\n"
        "Jobs:\n" + "\n".join(listings)
    )

    client = _get_client()
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=[
                {
                    "type": "text",
                    "text": _SCORING_SYSTEM,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_content}],
        )
        scores = _parse_json(response.content[0].text)
        score_map = {item["index"]: item["score"] for item in scores}
    except Exception:
        score_map = {}

    for i, job in enumerate(jobs):
        job["score"] = score_map.get(i, 60)

    return jobs


def search_jobs(
    job_titles: list[str],
    keywords: list[str],
    location: str,
) -> tuple[list[dict], dict]:
    """Fetch, deduplicate, score, and return job listings.

    Returns:
        (jobs, stats)
        jobs: scored jobs with score >= MIN_SCORE, sorted descending by score
        stats: dict with keys adzuna_raw, arbeitnow_raw, new_count,
               skipped_duplicates, below_threshold
    """
    seen = _load_seen_jobs()

    adzuna_jobs = _fetch_adzuna(job_titles, keywords, location)
    arbeitnow_jobs = _fetch_arbeitnow(job_titles, keywords, location)

    all_jobs = adzuna_jobs + arbeitnow_jobs

    # Filter out URLs seen in previous runs
    new_jobs: list[dict] = []
    new_urls: set[str] = set()
    skipped = 0
    for job in all_jobs:
        url = job.get("url", "")
        if not url or url in seen or url in new_urls:
            skipped += 1
        else:
            new_jobs.append(job)
            new_urls.add(url)

    scored = _score_jobs(new_jobs, job_titles, keywords)

    # Persist all newly seen URLs (including below-threshold ones)
    seen.update(new_urls)
    _save_seen_jobs(seen)

    passing = [j for j in scored if j["score"] >= MIN_SCORE]
    passing.sort(key=lambda j: j["score"], reverse=True)

    stats = {
        "adzuna_raw": len(adzuna_jobs),
        "arbeitnow_raw": len(arbeitnow_jobs),
        "new_count": len(new_jobs),
        "skipped_duplicates": skipped,
        "below_threshold": len(new_jobs) - len(passing),
    }
    return passing, stats
