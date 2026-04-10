# Job Hunter Bot

Fully automated job hunting pipeline that scrapes 8+ job boards, scores every listing with 10-dimension AI analysis using a local model, checks LinkedIn connections for referrals, filters by location, and logs everything to Notion -- hands-free, twice a day.

You leave your PC on. The bot does the rest.

## What It Does

```
Every morning and evening:

1. SCRAPE         8 sources (Indeed, LinkedIn, ZipRecruiter, Google,
                  Built In, Y Combinator, Jobright)
2. ATS SCAN       27 company career portals (Greenhouse, Lever, Ashby, Workday)
3. LOCATION       Filters out non-US, non-remote, onsite-outside-your-state
4. PRE-FILTER     Keyword filter removes irrelevant roles (zero AI cost)
5. SCORE          Local AI (Ollama) rates each job across 10 dimensions A-F
6. GUARDRAILS     8 traps caught: physical product, support roles, hidden seniority...
7. CONNECTIONS    Checks LinkedIn CSV for referral opportunities
8. NOTION         Logs scored jobs with full JD, dimensions, connection info
9. GMAIL          Scans inbox for interview/rejection emails, updates Notion

Your daily involvement: ~5 minutes reviewing Notion.
```

## 10-Dimension A-F Scoring

Every job is scored across 10 weighted dimensions instead of a single number:

| Dimension | Weight | What It Measures |
|-----------|--------|-----------------|
| Role Match | 2.0x | Is this actually a software/digital PM role? |
| Seniority Fit | 1.5x | Right level for you? |
| Domain Match | 1.5x | Industry overlap with your background? |
| Technical Fit | 1.3x | Do they want skills you have? |
| Requirements Gap | 1.3x | Hard requirements you lack? |
| Location Fit | 1.0x | Location works for you? |
| Leadership Fit | 0.8x | Team scope matches your experience? |
| Growth Potential | 0.7x | Career stepping stone? |
| Company Quality | 0.5x | Brand, funding, stability? |
| Compensation Signal | 0.4x | Pay reasonable? |

The final score is a weighted average. Role Match and Domain Match weigh 4x more than Company Quality -- because a PM role at a no-name company in your domain beats a Program Manager job at Google.

## 8 Scoring Guardrails

The AI catches common traps that fool simpler scoring systems:

| # | Trap | Example | Action |
|---|------|---------|--------|
| G1 | Physical product | "Product Manager" at Coca-Cola = beverage R&D | Cap at 4 |
| G2 | Product Support | "Product Support Manager" | Cap at 4 |
| G3 | Product Marketing | "Product Marketing Manager" | Cap at 6 |
| G4 | Production | "Production Manager" = factory ops | Cap at 3 |
| G5 | Brand inflation | Weak role at great company = still weak | Score role, not logo |
| G6 | Remote non-US | "Remote - EMEA" | Cap at 3 |
| G7 | Hybrid outside state | "Hybrid - San Francisco" | Cap at 5 |
| G8 | Hidden seniority | Title says "PM", JD says "15+ years, P&L" | Cap at 5 |

## Architecture

```
JobSpy (Indeed, LinkedIn, ZipRecruiter, Google)
                    |
Secondary Scraper (Built In, YC, Jobright)
                    |
ATS Scanner (Greenhouse, Lever, Ashby, Workday -- 27 companies)
                    |
              Deduplicate
                    |
         Location Filter (US + your state + remote only)
                    |
        Pre-filter (keyword, zero AI cost)
                    |
    Score (Ollama local / Gemini fallback) -- 10 dimensions + guardrails
                    |
       Check LinkedIn connections (CSV)
                    |
           Log to Notion (with full JD in page body)
                    |
         Gmail monitor (hourly, async)
                    |
       Update Notion status (Interview / Rejected / Offer)
```

## ATS Portal Scanner

Directly scrapes career pages from 27 companies using their native APIs:

- **Greenhouse** (JSON API): Stripe, Notion, Figma, Databricks, Cloudflare, Scale AI, Anthropic, Rippling, Samsara, Motive, and more
- **Lever** (JSON API): Netflix, Twitch
- **Ashby** (GraphQL): Linear, Vercel, Ramp
- **Workday** (HTML): John Deere

These catch PM jobs that never get posted to Indeed or LinkedIn. Add your target companies to the list in `ats_scanner.py`.

## Notion Dashboard

Each job entry includes:

| Field | Description |
|-------|-------------|
| Job Title | Role name |
| Company | Employer |
| Score | Weighted 1-10 from dimensions |
| Grade | Overall A-F grade |
| Dimensions | Breakdown: Role:A Domain:B Seniority:C ... |
| Fit Reason | Specific reason mentioning company + match/gap |
| Status | Apply / Ask Referral / Review / Interview / Rejected |
| URL | Direct link to apply |
| Referral Info | LinkedIn connections at the company |
| Full JD | Embedded in page body for resume tailoring |

### Status Workflow

- **Apply** (score 7+) -- High match, apply now
- **Ask Referral** -- LinkedIn connection found, reach out first
- **Review** (score 6) -- Borderline, your call
- **Interview** -- Bot detected interview email
- **Rejected** -- Bot detected rejection email
- **Offer** -- Bot detected offer email

## Requirements

- **Python 3.10+**
- **Ollama** (free, local AI) -- or Gemini API key as fallback
- **Notion** account + integration (free)
- **Gmail** with App Password (free, optional)
- **16-24 GB RAM** recommended for local AI model

## Setup (20 minutes)

### 1. Clone & Install

```bash
git clone https://github.com/dp761/job-hunter.git
cd job-hunter
pip install -r requirements.txt
```

### 2. Install Ollama (Recommended -- Free, No Rate Limits)

Download from https://ollama.com/download, then:

```bash
ollama pull qwen2.5:7b
ollama create job-scorer -f Modelfile
```

For lower RAM (< 16GB):
```bash
ollama pull qwen2.5:3b
```
Then edit `Modelfile` first line to `FROM qwen2.5:3b` before creating.

### 3. Get API Keys

| Service | URL | Cost |
|---------|-----|------|
| Notion Integration | https://www.notion.so/my-integrations | Free |
| Gemini API (optional fallback) | https://aistudio.google.com/apikey | Free tier |
| Gmail App Password (optional) | https://myaccount.google.com/apppasswords | Free |

### 4. Configure

```bash
cp .env.template .env
```

Edit `.env` with your keys. Then customize:

- **`config.py`**: Job titles, locations, search sites, your profile details
- **`scorer.py`**: `CANDIDATE_PROFILE` (your background), `REJECT_KEYWORDS`, `REQUIRE_KEYWORDS`
- **`Modelfile`**: Scoring rules, guardrails, calibration examples
- **`ats_scanner.py`**: Target companies for portal scanning

### 5. Set Up Notion Database

Create a database with columns: Job Title (title), Company (text), Location (text), Score (number), Grade (text), Dimensions (text), Fit Reason (text), Seniority (select), Key Skills (text), URL (url), Source (select), Status (select), Salary (text), Date Posted (date), Referral Info (text), Description (text), Notes (text).

Share the database with your Notion integration. Paste the database ID into `.env`.

The logger auto-detects your columns -- it writes to whatever exists and skips what doesn't.

### 6. LinkedIn Connections (Optional)

1. Go to https://www.linkedin.com/mypreferences/d/download-my-data
2. Export **Connections** only
3. Remove the metadata rows at the top (keep only headers + data)
4. Place as `connections.csv` in the project folder

### 7. Gmail Monitoring (Optional)

1. Enable 2-Step Verification on your Google account
2. Enable IMAP in Gmail settings
3. Generate an App Password at https://myaccount.google.com/apppasswords
4. Add credentials to `.env`

### 8. Run

```bash
# Single run (test everything)
python main.py

# Scheduled mode (2x daily + hourly Gmail)
python main.py --schedule

# Just test Gmail
python main.py --gmail-only

# Test ATS scanner standalone
python ats_scanner.py

# Export current scores
python export_scores.py
```

## Scheduling

### Terminal (Simple)
```bash
python main.py --schedule
```
Runs at 8:00 AM and 9:00 PM, checks Gmail every hour.

### Windows Task Scheduler (Set and Forget)

1. `Win + R` -> `taskschd.msc`
2. Create Basic Task -> "Job Hunter Bot"
3. Trigger: When the computer starts
4. Action: Start a program
   - Program: `C:\path\to\python.exe`
   - Arguments: `main.py --schedule`
   - Start in: `C:\path\to\job-hunter`
5. Properties -> "Run whether user is logged on or not"

### Linux/Mac (cron)
```bash
crontab -e
0 8,21 * * * cd /path/to/job-hunter && python main.py >> job_hunter.log 2>&1
```

## Deduplication

Three layers prevent duplicate work:

1. **`scored_urls.txt`** -- Tracks every URL ever scored. Skips on re-run.
2. **Notion URL check** -- Won't create duplicate entries.
3. **Gmail** -- Rolling time window, re-detecting same email is harmless.

Delete `scored_urls.txt` to force re-evaluation.

## File Structure

```
job-hunter/
├── main.py               # Orchestrator
├── config.py             # Settings + profile
├── scorer.py             # 10-dimension AI scoring + guardrails
├── Modelfile             # Custom Ollama model definition
├── scraper.py            # Primary scraper (JobSpy: 4 sites)
├── secondary_scraper.py  # Built In, Y Combinator, Jobright
├── ats_scanner.py        # Greenhouse, Lever, Ashby, Workday (27 companies)
├── connections.py        # LinkedIn CSV connection checker
├── notion_logger.py      # Notion API (auto-detects columns)
├── gmail_monitor.py      # IMAP inbox scanner
├── export_scores.py      # Export scored jobs from Notion
├── setup_notion.py       # One-time database creator
├── .env.template         # Secrets template
├── .gitignore
├── requirements.txt
├── LICENSE
└── README.md
```

## Customization

| What | Where |
|------|-------|
| Job titles to search | `JOB_TITLES` in `config.py` |
| Search locations | `SEARCH_LOCATIONS` in `.env` |
| Score thresholds | `AUTO_APPLY_MIN` / `FLAG_MIN` in `.env` |
| Your background for scoring | `CANDIDATE_PROFILE` in `scorer.py` |
| Scoring rules + guardrails | `Modelfile` |
| Reject/require keywords | `REJECT_KEYWORDS` / `REQUIRE_KEYWORDS` in `scorer.py` |
| Target ATS companies | `DEFAULT_COMPANIES` in `ats_scanner.py` |
| Local AI model | First line of `Modelfile` + `OLLAMA_MODEL` in `scorer.py` |
| Schedule times | `schedule.every().day.at()` in `main.py` |
| Location filter | `GEORGIA_LOCATIONS` / `NON_US_INDICATORS` in `main.py` |
| Gmail check frequency | `GMAIL_CHECK_INTERVAL` in `.env` |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Windows encoding errors | Latest `main.py` forces UTF-8 |
| Gemini rate limits | Install Ollama for unlimited local scoring |
| Ollama timeout | Increase timeout in `scorer.py` or use smaller model |
| Glassdoor errors | Removed (their API blocks scraping) |
| Notion 400 errors | Logger auto-detects columns; check column names for trailing spaces |
| Gmail auth failed | Enable IMAP + use App Password (not regular password) |
| Company names missing | Check Notion column name matches exactly |
| Non-US jobs appearing | Location filter runs before scoring; check `NON_US_INDICATORS` in `main.py` |
| ATS scanner timeout | Timeouts set to 30s; some company pages may be geo-blocked |
| YC returns 0 jobs | Their site is React-rendered; HTML scraping has limited results |

## Contributing

PRs welcome. Most likely files to need updates:
- `secondary_scraper.py` -- websites change HTML structure
- `ats_scanner.py` -- company URLs change
- `Modelfile` -- add more guardrails or calibration examples

## License

MIT
