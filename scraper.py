"""Scrape jobs from multiple sites using python-jobspy."""

import logging
from datetime import datetime, timedelta
from jobspy import scrape_jobs
import config

logger = logging.getLogger(__name__)


def scrape_all_jobs() -> list[dict]:
    """
    Scrape jobs for all configured titles and locations.
    Returns a deduplicated list of job dicts.
    """
    all_jobs = []
    seen_urls = set()
    cutoff = datetime.now() - timedelta(days=config.DAYS_BACK)

    for title in config.JOB_TITLES:
        for location in config.SEARCH_LOCATIONS:
            logger.info(f"Scraping: '{title}' in '{location}'")
            try:
                df = scrape_jobs(
                    site_name=config.SCRAPE_SITES,
                    search_term=title,
                    location=location,
                    results_wanted=30,
                    hours_old=config.DAYS_BACK * 24,
                    country_indeed="USA",
                )

                if df is None or df.empty:
                    logger.info("  -> 0 results")
                    continue

                for _, row in df.iterrows():
                    job = _row_to_dict(row)
                    if job["url"] in seen_urls:
                        continue
                    seen_urls.add(job["url"])
                    if job.get("date_posted") and job["date_posted"] < cutoff:
                        continue
                    all_jobs.append(job)

                logger.info(f"  -> {len(df)} raw, {len(all_jobs)} total unique")

            except Exception as e:
                logger.warning(f"  -> Scrape failed for '{title}' in '{location}': {e}")

    logger.info(f"Total unique jobs scraped: {len(all_jobs)}")
    return all_jobs


def _row_to_dict(row) -> dict:
    """Convert a DataFrame row to a clean dict."""

    def safe(col, default=""):
        val = row.get(col, default)
        if val is None or (isinstance(val, float) and str(val) == "nan"):
            return default
        return str(val).strip()

    date_posted = None
    raw_date = row.get("date_posted")
    if raw_date is not None and str(raw_date) != "nan":
        try:
            if hasattr(raw_date, "to_pydatetime"):
                date_posted = raw_date.to_pydatetime()
            else:
                date_posted = datetime.fromisoformat(str(raw_date))
        except Exception:
            date_posted = None

    return {
        "title": safe("title"),
        "company": safe("company"),
        "location": safe("location"),
        "url": safe("job_url"),
        "description": safe("description")[:3000],
        "site": safe("site"),
        "date_posted": date_posted,
        "salary": safe("min_amount") + " - " + safe("max_amount")
        if safe("min_amount")
        else "",
    }
