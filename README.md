# Job Search Command Centre

A multi-agent AI system that automates the repetitive parts of job searching — tailoring CVs, tracking applications, sourcing roles, and preparing for interviews.

---

## Tailor Agent (Agent 1 of 4)

The first agent in the system. Upload your CV and paste a job description — it handles the rest.

**Features:**

- Extracts the top 10 keywords from the job description
- Rewrites your CV bullet points to match the role naturally, without fabricating experience
- Writes a 3-paragraph cover letter that sounds human, not templated
- Scores how well your tailored CV matches the job (0–100)
- Exports everything as a single downloadable `.docx` file

---

## Coming Soon

- **Application Tracker** — log every application, status, and follow-up in one place
- **Job Sourcer** — find relevant job postings based on your target role and preferences
- **Interview Coach** — practice answers to likely interview questions for a specific role

---

## Tech Stack

- Python
- Claude API (Anthropic)
- Streamlit
- python-docx
- pypdf

---

## How to Run

**1. Clone the repo**

```bash
git clone https://github.com/Namita-Deshpande/job-search-agent.git
cd job-search-agent
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Add your API key**

Create a `.env` file in the project root:

```
ANTHROPIC_API_KEY=your-key-here
```

Get a key at [console.anthropic.com](https://console.anthropic.com).

**4. Run the app**

```bash
streamlit run app.py
```

Open [http://localhost:8501](http://localhost:8501) in your browser.

---

## Project Structure

```
job-search-agent/
├── agents/
│   └── tailor_agent.py   # CV tailoring logic
├── data/
│   └── master_cv.txt     # optional base CV for testing
├── outputs/              # generated .docx files (gitignored)
├── app.py                # Streamlit UI
├── requirements.txt
└── .env                  # not committed
```

---

This is Agent 1 of a multi-agent job search system being built incrementally. Each agent will be added as a standalone module and wired into a shared UI.
