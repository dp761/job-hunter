"""
Secondary Scraper
==================
Scrapes job boards that JobSpy doesn't support:
  - Built In (builtin.com)
  - Y Combinator Work at a Startup (workatastartup.com)
  - Jobright (jobright.ai)

Uses requests + BeautifulSoup. No Playwright needed.
Returns jobs in the same dict format as scraper.py for seamless integration.
"""

import logging
import re
import time
from datetime import datetime, timedelta
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

import config

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# -------------------------------------------------------------------
# BUILT IN (builtin.com)
# -------------------------------------------------------------------

BUILTIN_ROLE_SLUGS = {
    "Product Manager": "product-management",
    "Associate Product Manager": "product-management",
    "Product Analyst": "product-management",
    "Business Analyst": "business-analyst",
    "Solution Architect": "solutions-architect",
}

BUILTIN_LOCATION_MAP = {
    "Georgia": "atlanta",
    "Remote": "remote",
}


def _scrape_builtin() -> list[dict]:
    """Scrape jobs from Built In."""
    jobs = []
    seen_urls = set()

    for title, slug in BUILTIN_ROLE_SLUGS.items():
        for location, loc_slug in BUILTIN_LOCATION_MAP.items():
            url = f"https://builtin.com/jobs/{loc_slug}/{slug}"
            logger.info(f"  Built In: {url}")

            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"  -> Built In returned {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Built In uses data-id job cards
                cards = soup.select('[data-id="job-card"], .job-card, article.job-bounded-card')
                if not cards:
                    # Try alternative selectors
                    cards = soup.select("div[class*='job-card'], div[class*='JobCard']")

                for card in cards:
                    try:
                        # Title
                        title_el = card.select_one("h2 a, h3 a, a[class*='job-title'], a[data-id='job-card-alias']")
                        if not title_el:
                            continue
                        job_title = title_el.get_text(strip=True)
                        job_url = title_el.get("href", "")
                        if job_url and not job_url.startswith("http"):
                            job_url = "https://builtin.com" + job_url

                        if job_url in seen_urls:
                            continue
                        seen_urls.add(job_url)

                        # Company
                        company_el = card.select_one("div[class*='company-name'], span[class*='company'], a[class*='company']")
                        company = company_el.get_text(strip=True) if company_el else ""

                        # Location
                        loc_el = card.select_one("div[class*='location'], span[class*='location']")
                        job_location = loc_el.get_text(strip=True) if loc_el else location

                        jobs.append({
                            "title": job_title,
                            "company": company,
                            "location": job_location,
                            "url": job_url,
                            "description": "",  # Would need a second fetch per job
                            "site": "builtin",
                            "date_posted": None,
                            "salary": "",
                        })
                    except Exception:
                        continue

                logger.info(f"  -> Found {len(cards)} cards, {len(jobs)} total")
                time.sleep(2)

            except Exception as e:
                logger.warning(f"  -> Built In error: {e}")

    return jobs


# -------------------------------------------------------------------
# Y COMBINATOR - WORK AT A STARTUP (workatastartup.com)
# -------------------------------------------------------------------

YC_ROLE_QUERIES = [
    "Product Manager",
    "Business Analyst",
    "Product Analyst",
    "Solution Architect",
]


def _scrape_yc() -> list[dict]:
    """Scrape jobs from Y Combinator's Work at a Startup via HTML."""
    jobs = []
    seen_urls = set()

    for query in YC_ROLE_QUERIES:
        logger.info(f"  YC Work at a Startup: searching '{query}'")

        url = f"https://www.workatastartup.com/jobs?query={quote_plus(query)}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.warning(f"  -> YC returned {resp.status_code}")
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            # Try to extract job data from Next.js JSON payload
            script = soup.select_one("script#__NEXT_DATA__")
            if script and script.string:
                try:
                    import json
                    data = json.loads(script.string)
                    props = data.get("props", {}).get("pageProps", {})

                    # Navigate various possible structures
                    job_list = (
                        props.get("jobs", []) or
                        props.get("jobListings", []) or
                        props.get("results", []) or
                        []
                    )

                    for item in job_list:
                        try:
                            job_id = item.get("id", item.get("_id", ""))
                            job_url = f"https://www.workatastartup.com/jobs/{job_id}" if job_id else ""

                            if not job_url or job_url in seen_urls:
                                continue
                            seen_urls.add(job_url)

                            job_title = item.get("title", "")
                            company_data = item.get("company", {})
                            company = company_data.get("name", "") if isinstance(company_data, dict) else str(company_data)
                            job_location = item.get("pretty_location", item.get("location", ""))
                            description = item.get("description", "")

                            jobs.append({
                                "title": job_title,
                                "company": company,
                                "location": job_location,
                                "url": job_url,
                                "description": description[:3000],
                                "site": "y-combinator",
                                "date_posted": None,
                                "salary": "",
                            })
                        except Exception:
                            continue

                    if job_list:
                        logger.info(f"  -> Found {len(job_list)} jobs from JSON, {len(jobs)} total")
                        time.sleep(1)
                        continue
                except (json.JSONDecodeError, KeyError):
                    pass

            # Fallback: parse visible HTML links
            links = soup.select("a[href*='/jobs/']")
            found = 0
            for link in links:
                href = link.get("href", "")
                if not href or not re.match(r"/jobs/\d+", href):
                    continue

                full_url = "https://www.workatastartup.com" + href
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title_text = link.get_text(strip=True)
                if title_text:
                    jobs.append({
                        "title": title_text,
                        "company": "",
                        "location": "",
                        "url": full_url,
                        "description": "",
                        "site": "y-combinator",
                        "date_posted": None,
                        "salary": "",
                    })
                    found += 1

            logger.info(f"  -> Found {found} jobs from HTML, {len(jobs)} total")
            time.sleep(1)

        except Exception as e:
            logger.warning(f"  -> YC error: {e}")

    return jobs


# -------------------------------------------------------------------
# JOBRIGHT (jobright.ai)
# -------------------------------------------------------------------

JOBRIGHT_SEARCH_URL = "https://jobright.ai/jobs"


def _scrape_jobright() -> list[dict]:
    """Scrape jobs from Jobright.ai."""
    jobs = []
    seen_urls = set()

    for title in config.JOB_TITLES:
        for location in config.SEARCH_LOCATIONS:
            query = quote_plus(title)
            loc = quote_plus(location)
            url = f"{JOBRIGHT_SEARCH_URL}?query={query}&location={loc}"
            logger.info(f"  Jobright: '{title}' in '{location}'")

            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code != 200:
                    logger.warning(f"  -> Jobright returned {resp.status_code}")
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")

                # Try to find job cards - Jobright uses React so HTML might be minimal
                # Look for JSON data in script tags (common pattern for React SSR)
                scripts = soup.select("script[type='application/json'], script#__NEXT_DATA__")
                for script in scripts:
                    try:
                        import json
                        data = json.loads(script.string or "{}")

                        # Navigate Next.js data structure
                        props = data.get("props", {}).get("pageProps", {})
                        job_list = props.get("jobs", props.get("initialJobs", []))

                        if not isinstance(job_list, list):
                            continue

                        for item in job_list:
                            job_title = item.get("title", "")
                            company = item.get("company", item.get("companyName", ""))
                            job_location = item.get("location", "")
                            job_url = item.get("url", item.get("link", ""))
                            description = item.get("description", "")

                            if not job_url:
                                job_id = item.get("id", item.get("_id", ""))
                                if job_id:
                                    job_url = f"https://jobright.ai/jobs/{job_id}"

                            if not job_url or job_url in seen_urls:
                                continue
                            seen_urls.add(job_url)

                            jobs.append({
                                "title": job_title,
                                "company": company if isinstance(company, str) else company.get("name", ""),
                                "location": job_location,
                                "url": job_url,
                                "description": description[:3000],
                                "site": "jobright",
                                "date_posted": None,
                                "salary": "",
                            })
                    except (json.JSONDecodeError, AttributeError):
                        continue

                # Fallback: try parsing visible HTML job cards
                if not jobs:
                    cards = soup.select("div[class*='job'], a[class*='job'], div[class*='Job']")
                    for card in cards:
                        try:
                            link = card if card.name == "a" else card.select_one("a")
                            if not link:
                                continue
                            href = link.get("href", "")
                            if not href or href in seen_urls:
                                continue
                            if not href.startswith("http"):
                                href = "https://jobright.ai" + href
                            seen_urls.add(href)

                            job_title = link.get_text(strip=True)[:200]
                            jobs.append({
                                "title": job_title,
                                "company": "",
                                "location": location,
                                "url": href,
                                "description": "",
                                "site": "jobright",
                                "date_posted": None,
                                "salary": "",
                            })
                        except Exception:
                            continue

                logger.info(f"  -> {len(jobs)} jobs so far from Jobright")
                time.sleep(2)

            except Exception as e:
                logger.warning(f"  -> Jobright error: {e}")

    return jobs


# -------------------------------------------------------------------
# FETCH JOB DESCRIPTIONS (for jobs missing descriptions)
# -------------------------------------------------------------------

def _fetch_description(job: dict) -> str:
    """Fetch the full job description from the job URL."""
    if job.get("description"):
        return job["description"]

    try:
        resp = requests.get(job["url"], headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return ""

        soup = BeautifulSoup(resp.text, "html.parser")

        # Try common description containers
        for selector in [
            "div[class*='description']",
            "div[class*='job-description']",
            "div[class*='jobDescription']",
            "section[class*='description']",
            "article",
            "main",
        ]:
            el = soup.select_one(selector)
            if el and len(el.get_text(strip=True)) > 100:
                return el.get_text(separator="\n", strip=True)[:3000]

        return ""
    except Exception:
        return ""


# -------------------------------------------------------------------
# PUBLIC API: Called by main.py
# -------------------------------------------------------------------

def scrape_secondary_sites() -> list[dict]:
    """
    Scrape all secondary job sites.
    Returns deduplicated list in the same format as scraper.py.
    """
    all_jobs = []

    # Built In
    logger.info("Scraping Built In...")
    try:
        builtin_jobs = _scrape_builtin()
        all_jobs.extend(builtin_jobs)
        logger.info(f"  -> Built In: {len(builtin_jobs)} jobs")
    except Exception as e:
        logger.warning(f"  -> Built In failed: {e}")

    # Y Combinator
    logger.info("Scraping Y Combinator Work at a Startup...")
    try:
        yc_jobs = _scrape_yc()
        all_jobs.extend(yc_jobs)
        logger.info(f"  -> YC: {len(yc_jobs)} jobs")
    except Exception as e:
        logger.warning(f"  -> YC failed: {e}")

    # Jobright
    logger.info("Scraping Jobright...")
    try:
        jobright_jobs = _scrape_jobright()
        all_jobs.extend(jobright_jobs)
        logger.info(f"  -> Jobright: {len(jobright_jobs)} jobs")
    except Exception as e:
        logger.warning(f"  -> Jobright failed: {e}")

    # Fetch descriptions for jobs that are missing them
    missing_desc = [j for j in all_jobs if not j.get("description")]
    if missing_desc:
        logger.info(f"Fetching descriptions for {len(missing_desc)} jobs (max 20)...")
        for job in missing_desc[:20]:  # Cap at 20 to avoid being too aggressive
            desc = _fetch_description(job)
            if desc:
                job["description"] = desc
            time.sleep(1.5)

    logger.info(f"Secondary scraper total: {len(all_jobs)} jobs")
    return all_jobs
