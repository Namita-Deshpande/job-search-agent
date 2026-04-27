# Job Search Command Centre

A multi-agent AI system that automates every stage of the job search process.

---

## What it does

- **Tailor Agent** — rewrites your CV and generates a cover letter matched to any job description, then scores the fit
- **Tracker Agent** — manages your entire application pipeline across 9 stages with AI-powered health analysis
- **Sourcer Agent** — searches Adzuna and Arbeitnow for relevant roles, scores them against your profile, and filters duplicates
- **Coach Agent** — generates role-specific interview prep and gives scored feedback on your practice answers

---

## System architecture

The four agents are wired together as a continuous workflow. After the **Tailor Agent** generates a tailored CV, a one-click action sends the company, role, and job description straight into the **Tracker Agent** — no copy-pasting. From the Tracker, any saved application can launch the **Coach Agent** with the job description pre-loaded, so interview prep starts from the exact role you applied for. The **Sourcer Agent** runs independently, surfacing new roles and deduplicating against everything already seen. A weekly **Email Digest** ties it all together, sending a pipeline health score and follow-up list directly to your inbox.

---

## Agents

### 🎯 Tailor Agent
**Problem:** Generic CVs get filtered out before a human ever reads them.

Paste in a job description and upload your CV — the agent extracts the top keywords, rewrites your bullet points to mirror the role's language without fabricating experience, and writes a cover letter that sounds human. Everything exports as a single `.docx` file, and a match score (0–100) tells you how well the tailored CV aligns with the job.

---

### 📋 Tracker Agent
**Problem:** Spreadsheets don't tell you what to do next.

Track applications through 9 stages from Wishlist to Accepted, with fields for URL, salary range, dates, and notes. A live dashboard shows pipeline counts at a glance. The AI Insights button sends your full pipeline to Claude, which returns honest analysis of your conversion rates and exactly 3 concrete next steps.

---

### 🔍 Sourcer Agent
**Problem:** Manually checking job boards every day is slow and repetitive.

Pulls listings from Adzuna (Germany) and Arbeitnow, deduplicates against every URL seen in previous runs, and uses Claude to score each listing 0–100 against your target titles and keywords. Only roles above the relevance threshold are shown, sorted by score. Results can be sent directly to the Tracker with one click.

---

### 🎤 Coach Agent
**Problem:** Interview prep is generic when it isn't tailored to the actual role.

Given a company and job description, Claude generates a structured prep guide: company summary, expected interview rounds, 5 technical questions referencing the specific tech in the JD, 5 STAR-format behavioural questions, smart questions to ask the interviewer, and red flags to watch for. Practice mode lets you type an answer and get a score, strengths, improvements, and a rewritten model answer.

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.13 |
| AI | Claude Haiku (Anthropic SDK) |
| UI | Streamlit |
| Document generation | python-docx |
| Document parsing | pypdf |
| Job board APIs | Adzuna API, Arbeitnow API |
| Email | Gmail SMTP (smtplib — stdlib) |
| Persistence | JSON files |

---

## How to run locally

**1. Clone the repo**

```bash
git clone https://github.com/Namita-Deshpande/job-search-agent.git
cd job-search-agent
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment variables**

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-key-here

# Optional — Adzuna job search (Germany)
ADZUNA_APP_ID=your-app-id
ADZUNA_API_KEY=your-api-key

# Optional — weekly email digest
EMAIL_SENDER=your-gmail@gmail.com
EMAIL_PASSWORD=your-gmail-app-password
EMAIL_RECEIVER=recipient@example.com

# Password gate
APP_PASSWORD=your-password
```

- Anthropic API key: [console.anthropic.com](https://console.anthropic.com)
- Adzuna API keys: [developer.adzuna.com](https://developer.adzuna.com)
- Gmail app password: Google Account → Security → 2-Step Verification → App passwords

**4. Run the app**

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Project structure

```
job-search-agent/
├── agents/
│   ├── tailor_agent.py       # CV tailoring and cover letter generation
│   ├── tracker_agent.py      # application tracking and pipeline analysis
│   ├── sourcer_agent.py      # job board search, scoring, deduplication
│   ├── coach_agent.py        # interview prep generation and answer feedback
│   └── email_agent.py        # weekly digest formatting and Gmail delivery
├── data/
│   ├── applications.json     # tracker persistence
│   ├── seen_jobs.json        # sourcer deduplication cache
│   ├── prep_sessions.json    # coach session history
│   └── email_log.json        # digest send log
├── outputs/                  # generated .docx files (gitignored)
├── app.py                    # Streamlit UI
├── requirements.txt
└── .env                      # not committed
```

---

## Live demo

[Job Search Command Centre](https://namd-job-search-agents.streamlit.app/)

---

## Built by

**Namita Deshpande** — AI & Automation Engineer
