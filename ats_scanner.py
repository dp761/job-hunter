"""
ATS Portal Scanner
===================
Scrapes jobs directly from company career pages powered by
Greenhouse, Lever, Ashby, and Workday.

These are where PM jobs actually live -- many never get posted
to Indeed or LinkedIn.

Usage:
    Automatically called by main.py, or run standalone:
    python ats_scanner.py

Configure target companies in ats_companies.yml or the default list below.
"""

import json
import logging
import os
import re
import time
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# -------------------------------------------------------------------
# TARGET COMPANIES (edit this list or load from file)
# -------------------------------------------------------------------
# Format: (company_name, ats_type, careers_url)
# ats_type: "greenhouse", "lever", "ashby", "workday", "custom"

DEFAULT_COMPANIES = [
    # Tech / AI
    ("Stripe", "greenhouse", "https://boards.greenhouse.io/stripe"),
    ("Notion", "greenhouse", "https://boards.greenhouse.io/notion"),
    ("Figma", "greenhouse", "https://boards.greenhouse.io/figma"),
    ("Databricks", "greenhouse", "https://boards.greenhouse.io/databricks"),
    ("Datadog", "greenhouse", "https://boards.greenhouse.io/datadog"),
    ("Cloudflare", "greenhouse", "https://boards.greenhouse.io/cloudflare"),
    ("Plaid", "greenhouse", "https://boards.greenhouse.io/plaid"),
    ("Brex", "greenhouse", "https://boards.greenhouse.io/brex"),
    ("Ramp", "greenhouse", "https://boards.greenhouse.io/ramp"),
    ("Scale AI", "greenhouse", "https://boards.greenhouse.io/scaleai"),
    ("Anthropic", "greenhouse", "https://boards.greenhouse.io/anthropic"),
    ("Anduril", "greenhouse", "https://boards.greenhouse.io/andurilindustries"),
    ("Rippling", "greenhouse", "https://boards.greenhouse.io/rippling"),

    # Lever
    ("Netflix", "lever", "https://jobs.lever.co/netflix"),
    ("Twitch", "lever", "https://jobs.lever.co/twitch"),

    # Ashby
    ("Linear", "ashby", "https://jobs.ashbyhq.com/linear"),
    ("Vercel", "ashby", "https://jobs.ashbyhq.com/vercel"),
    ("Ramp", "ashby", "https://jobs.ashbyhq.com/ramp"),

    # Supply Chain / AgTech / IoT (your domains)
    ("John Deere", "workday", "https://johndeere.wd1.myworkdayjobs.com/CareersJD"),
    ("Samsara", "greenhouse", "https://boards.greenhouse.io/samsara"),
    ("Motive", "greenhouse", "https://boards.greenhouse.io/gomotive"),
    ("FarmLogs", "greenhouse", "https://boards.greenhouse.io/farmlogs"),
    ("Indigo Ag", "greenhouse", "https://boards.greenhouse.io/indigoag"),
    ("project44", "greenhouse", "https://boards.greenhouse.io/project44"),
    ("FourKites", "greenhouse", "https://boards.greenhouse.io/fourkites"),
]

# Job title keywords to match
TITLE_KEYWORDS = [kw.lower() for kw in config.JOB_TITLES] + [
    "product owner", "product lead", "data product", "ai product",
]


def _load_companies() -> list[tuple]:
    """Load company list from YAML file if exists, otherwise use defaults."""
    yml_path = "ats_companies.yml"
    if os.path.exists(yml_path):
        try:
            import yaml
            with open(yml_path, "r") as f:
                data = yaml.safe_load(f)
            companies = []
            for entry in data.get("companies", []):
                companies.append((
                    entry.get("name", ""),
                    entry.get("ats", "greenhouse"),
                    entry.get("url", ""),
                ))
            if companies:
                logger.info(f"Loaded {len(companies)} companies from {yml_path}")
                return companies
        except Exception as e:
            logger.warning(f"Could not load {yml_path}: {e}")

    return DEFAULT_COMPANIES


def _title_matches(title: str) -> bool:
    """Check if a job title matches our target keywords."""
    title_lower = title.lower()
    return any(kw in title_lower for kw in TITLE_KEYWORDS)


# -------------------------------------------------------------------
# GREENHOUSE SCRAPER
# -------------------------------------------------------------------

def _scrape_greenhouse(company_name: str, url: str) -> list[dict]:
    """Scrape jobs from Greenhouse boards."""
    jobs = []

    # Greenhouse has a JSON API at /boards/{company}/jobs
    # Try API first
    api_url = None
    if "boards.greenhouse.io" in url:
        slug = url.rstrip("/").split("/")[-1]
        api_url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
    elif "jobs." in url:
        # Custom domain -- try HTML scraping
        pass

    if api_url:
        try:
            resp = requests.get(api_url, headers=HEADERS, timeout=30)
            if resp.status_code == 200:
                data = resp.json()
                for item in data.get("jobs", []):
                    title = item.get("title", "")
                    if not _title_matches(title):
                        continue

                    location = item.get("location", {}).get("name", "")
                    job_url = item.get("absolute_url", "")
                    content = item.get("content", "")

                    # Strip HTML from content
                    if content:
                        soup = BeautifulSoup(content, "html.parser")
                        content = soup.get_text(separator="\n", strip=True)

                    jobs.append({
                        "title": title,
                        "company": company_name,
                        "location": location,
                        "url": job_url,
                        "description": content[:3000],
                        "site": "greenhouse",
                        "date_posted": None,
                        "salary": "",
                    })

                return jobs
        except Exception as e:
            logger.warning(f"  -> Greenhouse API failed for {company_name}: {e}")

    # Fallback: HTML scraping
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")
        links = soup.select("a[href*='/jobs/'], a[href*='/job/']")

        for link in links:
            title = link.get_text(strip=True)
            if not title or not _title_matches(title):
                continue

            href = link.get("href", "")
            if not href.startswith("http"):
                href = url.rstrip("/") + "/" + href.lstrip("/")

            jobs.append({
                "title": title,
                "company": company_name,
                "location": "",
                "url": href,
                "description": "",
                "site": "greenhouse",
                "date_posted": None,
                "salary": "",
            })
    except Exception as e:
        logger.warning(f"  -> Greenhouse HTML failed for {company_name}: {e}")

    return jobs


# -------------------------------------------------------------------
# LEVER SCRAPER
# -------------------------------------------------------------------

def _scrape_lever(company_name: str, url: str) -> list[dict]:
    """Scrape jobs from Lever."""
    jobs = []

    try:
        # Lever has a public JSON API
        slug = url.rstrip("/").split("/")[-1]
        api_url = f"https://api.lever.co/v0/postings/{slug}"

        resp = requests.get(api_url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            # Try HTML fallback
            resp = requests.get(url, headers=HEADERS, timeout=30)
            if resp.status_code != 200:
                return jobs

            soup = BeautifulSoup(resp.text, "html.parser")
            for posting in soup.select(".posting"):
                title_el = posting.select_one(".posting-title h5, a")
                if not title_el:
                    continue
                title = title_el.get_text(strip=True)
                if not _title_matches(title):
                    continue

                link = posting.select_one("a.posting-btn-submit, a[href]")
                href = link.get("href", "") if link else ""

                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": "",
                    "url": href,
                    "description": "",
                    "site": "lever",
                    "date_posted": None,
                    "salary": "",
                })
            return jobs

        # Parse JSON API response
        data = resp.json()
        for item in data:
            title = item.get("text", "")
            if not _title_matches(title):
                continue

            location = ""
            categories = item.get("categories", {})
            if categories:
                location = categories.get("location", "")

            desc_plain = item.get("descriptionPlain", "")

            jobs.append({
                "title": title,
                "company": company_name,
                "location": location,
                "url": item.get("hostedUrl", ""),
                "description": desc_plain[:3000],
                "site": "lever",
                "date_posted": None,
                "salary": "",
            })

    except Exception as e:
        logger.warning(f"  -> Lever failed for {company_name}: {e}")

    return jobs


# -------------------------------------------------------------------
# ASHBY SCRAPER
# -------------------------------------------------------------------

def _scrape_ashby(company_name: str, url: str) -> list[dict]:
    """Scrape jobs from Ashby."""
    jobs = []

    try:
        # Ashby uses a GraphQL API
        slug = url.rstrip("/").split("/")[-1]
        api_url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"

        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": slug},
            "query": """query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
                jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
                    jobPostings {
                        id title teamName locationName employmentType
                        descriptionPlain compensationTierSummary
                    }
                }
            }"""
        }

        resp = requests.post(api_url, json=payload, headers={
            **HEADERS, "Content-Type": "application/json"
        }, timeout=30)

        if resp.status_code == 200:
            data = resp.json()
            postings = (data.get("data", {}).get("jobBoard", {})
                       .get("jobPostings", []))

            for item in postings:
                title = item.get("title", "")
                if not _title_matches(title):
                    continue

                job_id = item.get("id", "")
                job_url = f"https://jobs.ashbyhq.com/{slug}/{job_id}"
                desc = item.get("descriptionPlain", "")
                comp = item.get("compensationTierSummary", "")

                jobs.append({
                    "title": title,
                    "company": company_name,
                    "location": item.get("locationName", ""),
                    "url": job_url,
                    "description": desc[:3000],
                    "site": "ashby",
                    "date_posted": None,
                    "salary": comp,
                })

    except Exception as e:
        logger.warning(f"  -> Ashby failed for {company_name}: {e}")

    return jobs


# -------------------------------------------------------------------
# WORKDAY SCRAPER (limited -- complex JS-rendered pages)
# -------------------------------------------------------------------

def _scrape_workday(company_name: str, url: str) -> list[dict]:
    """Attempt to scrape Workday career pages. Limited without JS rendering."""
    jobs = []

    try:
        # Workday has a search API at some endpoints
        resp = requests.get(url, headers=HEADERS, timeout=30)
        if resp.status_code != 200:
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try to find job links
        for link in soup.select("a[href*='job'], a[data-automation-id]"):
            title = link.get_text(strip=True)
            if not title or not _title_matches(title):
                continue

            href = link.get("href", "")
            if not href.startswith("http"):
                base = "/".join(url.split("/")[:3])
                href = base + href

            jobs.append({
                "title": title,
                "company": company_name,
                "location": "",
                "url": href,
                "description": "",
                "site": "workday",
                "date_posted": None,
                "salary": "",
            })

    except Exception as e:
        logger.warning(f"  -> Workday failed for {company_name}: {e}")

    return jobs


# -------------------------------------------------------------------
# PUBLIC API
# -------------------------------------------------------------------

ATS_SCRAPERS = {
    "greenhouse": _scrape_greenhouse,
    "lever": _scrape_lever,
    "ashby": _scrape_ashby,
    "workday": _scrape_workday,
}


def scan_ats_portals() -> list[dict]:
    """
    Scan all configured company ATS portals for matching jobs.
    Returns deduplicated list in standard job dict format.
    """
    companies = _load_companies()
    all_jobs = []
    seen_urls = set()

    logger.info(f"Scanning {len(companies)} company career portals...")

    for company_name, ats_type, careers_url in companies:
        if not careers_url:
            continue

        scraper = ATS_SCRAPERS.get(ats_type)
        if not scraper:
            logger.warning(f"  -> Unknown ATS type '{ats_type}' for {company_name}")
            continue

        try:
            jobs = scraper(company_name, careers_url)

            # Deduplicate
            new_jobs = []
            for job in jobs:
                if job["url"] not in seen_urls:
                    seen_urls.add(job["url"])
                    new_jobs.append(job)

            if new_jobs:
                all_jobs.extend(new_jobs)
                logger.info(f"  {company_name} ({ats_type}): {len(new_jobs)} matching jobs")

        except Exception as e:
            logger.warning(f"  -> {company_name} error: {e}")

        time.sleep(0.5)  # Be polite

    logger.info(f"ATS portal scan total: {len(all_jobs)} matching jobs from {len(companies)} companies")
    return all_jobs


# -------------------------------------------------------------------
# STANDALONE ENTRY POINT
# -------------------------------------------------------------------

if __name__ == "__main__":
    import sys
    import io

    if sys.platform == "win32":
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
    )

    jobs = scan_ats_portals()
    print(f"\n{'='*80}")
    print(f"Found {len(jobs)} matching PM/BA/SA jobs across all portals:\n")
    for j in jobs:
        print(f"  {j['title'][:50]:<50} | {j['company']:<20} | {j['site']}")
