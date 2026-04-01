# Job Hunter Bot

Fully automated job hunting pipeline that scrapes 8 job boards, scores every listing against your profile using a local AI model, checks if you have LinkedIn connections at the company, and logs everything to a Notion dashboard — hands-free, twice a day.

You leave your PC on. The bot does the rest.

## What It Does

```
Every morning and evening:

1. SCRAPE       8 job boards (Indeed, LinkedIn, ZipRecruiter, Google,
                Built In, Y Combinator, Jobright)
2. PRE-FILTER   Keyword filter removes obviously irrelevant roles (zero AI cost)
3. SCORE        Local AI model (Ollama) rates each job 1-10 for YOUR fit
4. CONNECTIONS  Checks your LinkedIn CSV for people at each company
5. NOTION       Logs scored jobs with full JD, fit reason, connection info
6. GMAIL        Scans inbox for interview invites / rejections, updates Notion

Your daily involvement: ~5 minutes reviewing Notion.
```

## Architecture

```
                    JobSpy (Indeed, LinkedIn, ZipRecruiter, Google)
                                    |
                    Secondary Scraper (Built In, YC, Jobright)
                                    |
                              Deduplicate
                                    |
                     Pre-filter (keyword, no AI)
                                    |
                   Score (Ollama local / Gemini fallback)
                                    |
                      Check LinkedIn connections
                                    |
                          Log to Notion
                                    |
                    Gmail monitor (hourly, async)
                                    |
                      Update Notion status
                   (Interview / Rejected / Offer)
```

## Notion Dashboard

Each job entry includes:

| Field | Description |
|-------|-------------|
| Job Title | Role name |
| Company | Employer |
| Score | 1-10 AI fit rating |
| Fit Reason | Why it scored high/low |
| Status | Apply / Ask Referral / Review / Interview / Rejected |
| URL | Direct link to apply |
| Referral Info | LinkedIn connections at the company (if any) |
| Full JD | Embedded in the page body — copy-paste into your resume tool |

### Status Workflow

- **Apply** (score 7+) — High match, apply now
- **Ask Referral** — You have a LinkedIn connection, reach out first
- **Review** (score 6) — Borderline, your call
- **Interview** — Bot detected interview email
- **Rejected** — Bot detected rejection email
- **Offer** — Bot detected offer email

## Requirements

- **Python 3.10+**
- **Ollama** (free, local AI) — or Gemini API key as fallback
- **Notion** account + integration (free)
- **Gmail** with App Password (free, optional for email monitoring)
- **8-24 GB RAM** (for running the local AI model)

## Setup (20 minutes)

### 1. Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/job-hunter.git
cd job-hunter
pip install -r requirements.txt
```

### 2. Install Ollama (Local AI — Recommended)

Download from https://ollama.com/download, then:

```bash
ollama pull qwen2.5:7b
```

This gives you unlimited scoring with zero API costs. If your PC has less than 16GB RAM, use the smaller model:

```bash
ollama pull llama3.2:3b
```

Then change `OLLAMA_MODEL` in `scorer.py` to `"llama3.2:3b"`.

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

Edit `.env` with your keys. Then edit `config.py`:

- **`JOB_TITLES`** — What roles to search for
- **`SEARCH_LOCATIONS`** — Where (city, state, or "Remote")
- **`APPLICANT_PROFILE`** — Your personal details
- **`AUTO_APPLY_MIN`** — Score threshold for "Apply" status (default: 7)
- **`FLAG_MIN`** — Score threshold for "Review" status (default: 6)

Finally, edit `scorer.py`:

- **`CANDIDATE_PROFILE`** — Your background summary (used by AI to score fit)
- **`REJECT_KEYWORDS`** — Job titles to always skip
- **`REQUIRE_KEYWORDS`** — Job titles to always consider

### 5. Set Up Notion Database

**Option A: Automatic**
```bash
python setup_notion.py
```

**Option B: Manual**
Create a database in Notion with these columns: Job Title (title), Company (text), Location (text), Score (number), Fit Reason (text), Seniority (select), Key Skills (text), URL (url), Source (select), Status (select), Salary (text), Date Posted (date), Referral Info (text), Notes (text).

Either way, share the database page with your Notion integration (... -> Connections -> add it).

Paste the database ID into `.env` as `NOTION_DATABASE_ID`.

### 6. LinkedIn Connections (Optional)

For referral checking:
1. Go to https://www.linkedin.com/mypreferences/d/download-my-data
2. Export **Connections** only
3. Place `Connections.csv` in the project folder as `connections.csv`

### 7. Gmail Monitoring (Optional)

Requires 2-Step Verification enabled, then:
1. Go to https://myaccount.google.com/apppasswords
2. Generate an App Password
3. Make sure IMAP is enabled: Gmail Settings -> Forwarding and POP/IMAP -> Enable IMAP
4. Add to `.env`

### 8. Run

```bash
# Single run (test everything works)
python main.py

# Scheduled mode (2x daily + hourly Gmail check)
python main.py --schedule

# Just test Gmail
python main.py --gmail-only
```

## Scheduling (True Automation)

### Keep Terminal Open
```bash
python main.py --schedule
```
Runs at 8:00 AM and 9:00 PM, checks Gmail every hour.

### Windows Task Scheduler (Set and Forget)

1. `Win + R` -> `taskschd.msc`
2. Create Basic Task -> "Job Hunter Bot"
3. Trigger: **When the computer starts**
4. Action: Start a program
   - Program: `C:\path\to\python.exe`
   - Arguments: `main.py --schedule`
   - Start in: `C:\path\to\job-hunter`
5. Properties -> "Run whether user is logged on or not"

### Linux/Mac (cron)
```bash
crontab -e
# Add:
0 8,21 * * * cd /path/to/job-hunter && python main.py >> job_hunter.log 2>&1
```

## How Deduplication Works

The bot never re-scores or re-logs the same job:

1. **`scored_urls.txt`** — Tracks every URL ever scored. Next run skips them.
2. **Notion URL check** — Before logging, checks if the URL already exists in your database.
3. **Gmail** — Scans a rolling time window. Re-detecting the same email just re-sets the same status.

Delete `scored_urls.txt` periodically if you want the bot to re-evaluate old jobs.

## File Structure

```
job-hunter/
├── main.py               # Orchestrator — run this
├── config.py             # Your settings + profile
├── scorer.py             # AI scoring (Ollama / Gemini) + pre-filter
├── scraper.py            # Primary scraper (JobSpy: 4 sites)
├── secondary_scraper.py  # Built In, Y Combinator, Jobright
├── connections.py        # LinkedIn CSV connection checker
├── notion_logger.py      # Notion API (auto-detects your columns)
├── gmail_monitor.py      # IMAP inbox scanner
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
| Job titles | `JOB_TITLES` in `config.py` |
| Locations | `SEARCH_LOCATIONS` in `.env` |
| Score thresholds | `AUTO_APPLY_MIN` / `FLAG_MIN` in `.env` |
| Your background (for scoring) | `CANDIDATE_PROFILE` in `scorer.py` |
| Reject/require keywords | `REJECT_KEYWORDS` / `REQUIRE_KEYWORDS` in `scorer.py` |
| Local AI model | `OLLAMA_MODEL` in `scorer.py` |
| Schedule times | Edit `schedule.every().day.at()` in `main.py` |
| Gmail check frequency | `GMAIL_CHECK_INTERVAL` in `.env` |

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Windows encoding errors | Ensure you're using the latest `main.py` (forces UTF-8) |
| Gemini rate limits | Install Ollama for unlimited local scoring |
| Glassdoor errors | Removed by default (their API blocks scraping) |
| Notion 400 errors | The logger auto-detects columns; make sure your database is shared with the integration |
| Gmail auth failed | Enable IMAP + use an App Password (not your regular password) |
| Ollama slow on CPU | Switch to `llama3.2:3b` (smaller, faster, slightly less accurate) |
| Secondary scraper returns 0 jobs | These sites change their HTML frequently; open an issue |

## Contributing

PRs welcome. The secondary scraper (`secondary_scraper.py`) is the most likely to need updates as websites change their structure. If you add support for a new job board, please follow the same return format as `scraper.py`.

## License

MIT
