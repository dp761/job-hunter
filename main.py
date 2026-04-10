"""
Job Hunter Bot -- Lean Pipeline
=================================
Scrape -> Score -> Check Connections -> Log to Notion -> Monitor Gmail

Resume generation and auto-apply are handled externally via
Comet + Gemini Gems. The bot focuses on finding and scoring jobs,
then giving you everything you need in Notion to act fast.

Usage:
    python main.py              # Run pipeline once
    python main.py --schedule   # Run daily + monitor Gmail hourly
    python main.py --gmail-only # Just scan Gmail and update Notion
"""

import argparse
import logging
import sys
import io
from datetime import datetime

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(message)s",
    datefmt="%H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("job_hunter.log", mode="a", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


def validate_config():
    """Check required credentials exist."""
    import config

    missing = []
    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY.startswith("your_"):
        missing.append("GEMINI_API_KEY")
    if not config.NOTION_API_KEY or config.NOTION_API_KEY.startswith("your_"):
        missing.append("NOTION_API_KEY")
    if not config.NOTION_DATABASE_ID or config.NOTION_DATABASE_ID.startswith("your_"):
        missing.append("NOTION_DATABASE_ID")

    if missing:
        logger.error(f"Missing: {', '.join(missing)} -- edit your .env file")
        return False

    if not config.GMAIL_ADDRESS or config.GMAIL_ADDRESS.startswith("your_"):
        logger.warning("GMAIL not configured -- email monitoring disabled")

    return True


# -------------------------------------------------------------------
# LOCATION FILTER
# -------------------------------------------------------------------

US_STATES = [
    "alabama", "alaska", "arizona", "arkansas", "california", "colorado",
    "connecticut", "delaware", "florida", "georgia", "hawaii", "idaho",
    "illinois", "indiana", "iowa", "kansas", "kentucky", "louisiana",
    "maine", "maryland", "massachusetts", "michigan", "minnesota",
    "mississippi", "missouri", "montana", "nebraska", "nevada",
    "new hampshire", "new jersey", "new mexico", "new york",
    "north carolina", "north dakota", "ohio", "oklahoma", "oregon",
    "pennsylvania", "rhode island", "south carolina", "south dakota",
    "tennessee", "texas", "utah", "vermont", "virginia", "washington",
    "west virginia", "wisconsin", "wyoming", "district of columbia",
]

US_STATE_ABBREVS = [
    "al", "ak", "az", "ar", "ca", "co", "ct", "de", "fl", "ga", "hi",
    "id", "il", "in", "ia", "ks", "ky", "la", "me", "md", "ma", "mi",
    "mn", "ms", "mo", "mt", "ne", "nv", "nh", "nj", "nm", "ny", "nc",
    "nd", "oh", "ok", "or", "pa", "ri", "sc", "sd", "tn", "tx", "ut",
    "vt", "va", "wa", "wv", "wi", "wy", "dc",
]

# Georgia-area cities/regions for onsite matching
GEORGIA_LOCATIONS = [
    "atlanta", "marietta", "sandy springs", "alpharetta", "roswell",
    "decatur", "kennesaw", "duluth", "lawrenceville", "savannah",
    "augusta", "columbus", "macon", "athens", ", ga", "georgia",
]

NON_US_INDICATORS = [
    "london", "uk", "united kingdom", "canada", "toronto", "vancouver",
    "berlin", "germany", "france", "paris", "amsterdam", "netherlands",
    "singapore", "india", "bangalore", "mumbai", "hyderabad", "delhi",
    "australia", "sydney", "melbourne", "japan", "tokyo", "brazil",
    "mexico", "dubai", "uae", "israel", "tel aviv", "ireland", "dublin",
    "spain", "madrid", "barcelona", "italy", "milan", "rome",
    "sweden", "stockholm", "norway", "oslo", "denmark", "copenhagen",
    "switzerland", "zurich", "poland", "warsaw", "portugal", "lisbon",
    "china", "shanghai", "beijing", "south korea", "seoul",
]


def _filter_by_location(jobs: list[dict]) -> list[dict]:
    """
    Keep only jobs that are:
    - Remote (US-based or unspecified)
    - Located in Georgia
    - Hybrid in Georgia
    - USA-based without onsite requirement outside Georgia
    Remove:
    - Non-US locations
    - Onsite roles outside Georgia
    """
    kept = []

    for job in jobs:
        location = job.get("location", "").lower().strip()

        # No location specified -- keep it (might be remote)
        if not location:
            kept.append(job)
            continue

        # Explicitly non-US -- reject
        if any(loc in location for loc in NON_US_INDICATORS):
            continue

        # Remote -- always keep
        if "remote" in location:
            kept.append(job)
            continue

        # Georgia-based -- always keep
        if any(ga in location for ga in GEORGIA_LOCATIONS):
            kept.append(job)
            continue

        # Check if it's a US location
        is_us = False
        # Check state abbreviation pattern like "City, GA" or "City, CA"
        for abbrev in US_STATE_ABBREVS:
            if f", {abbrev}" in location or f" {abbrev}" == location[-3:]:
                is_us = True
                break

        if not is_us:
            for state in US_STATES:
                if state in location:
                    is_us = True
                    break

        if not is_us:
            if "united states" in location or "usa" in location or "us" == location:
                is_us = True

        # US but not Georgia -- check if it says onsite/in-office
        if is_us:
            title_lower = job.get("title", "").lower()
            desc_lower = job.get("description", "").lower()[:500]
            combined = location + " " + title_lower + " " + desc_lower

            # If explicitly onsite and not in Georgia, skip
            if any(kw in combined for kw in ["onsite", "on-site", "in-office", "in office"]):
                if not any(ga in location for ga in GEORGIA_LOCATIONS):
                    continue

            # Hybrid outside Georgia -- skip
            if "hybrid" in combined:
                if not any(ga in location for ga in GEORGIA_LOCATIONS):
                    continue

            # US-based, no onsite requirement -- keep (could be remote-friendly)
            kept.append(job)
            continue

        # Unknown location -- keep it, scorer will handle
        kept.append(job)

    return kept


def run_pipeline():
    """Execute the lean pipeline: Scrape -> Score -> Connections -> Notion."""
    start = datetime.now()
    logger.info("=" * 60)
    logger.info("JOB HUNTER BOT -- Pipeline Start")
    logger.info("=" * 60)

    if not validate_config():
        return

    # -- 1. SCRAPE --
    from scraper import scrape_all_jobs
    from secondary_scraper import scrape_secondary_sites

    logger.info("")
    logger.info("STEP 1/4 -- Scraping jobs...")

    logger.info("  Primary (JobSpy: Indeed, LinkedIn, ZipRecruiter, Google)...")
    jobs = scrape_all_jobs()

    logger.info("  Secondary (Built In, Y Combinator, Jobright)...")
    try:
        secondary = scrape_secondary_sites()
        # Deduplicate by URL against primary results
        existing_urls = {j["url"] for j in jobs}
        new_secondary = [j for j in secondary if j["url"] not in existing_urls]
        jobs.extend(new_secondary)
        logger.info(f"  -> Secondary added {len(new_secondary)} unique jobs")
    except Exception as e:
        logger.warning(f"  -> Secondary scraper failed: {e}")

    if not jobs:
        logger.info("No new jobs found. Done.")
        return

    # ATS portal scanning (Greenhouse, Lever, Ashby, Workday)
    logger.info("  ATS portals (Greenhouse, Lever, Ashby, Workday)...")
    try:
        from ats_scanner import scan_ats_portals
        ats_jobs = scan_ats_portals()
        existing_urls = {j["url"] for j in jobs}
        new_ats = [j for j in ats_jobs if j["url"] not in existing_urls]
        jobs.extend(new_ats)
        logger.info(f"  -> ATS portals added {len(new_ats)} unique jobs")
    except Exception as e:
        logger.warning(f"  -> ATS scanner failed: {e}")

    # -- LOCATION FILTER -- Remove non-US, non-Remote, onsite-outside-Georgia --
    before_filter = len(jobs)
    jobs = _filter_by_location(jobs)
    logger.info(f"  Location filter: {before_filter} -> {len(jobs)} jobs (removed {before_filter - len(jobs)} non-US/non-GA)")

    # -- 2. SCORE & FILTER --
    from scorer import score_and_filter

    logger.info("")
    logger.info("STEP 2/4 -- Scoring with Gemini...")
    jobs = score_and_filter(jobs)
    if not jobs:
        logger.info("No jobs passed the filter. Done.")
        return

    # -- 3. CHECK CONNECTIONS --
    from connections import check_connections

    logger.info("")
    logger.info("STEP 3/4 -- Checking LinkedIn connections...")
    jobs = check_connections(jobs)

    # -- 4. LOG TO NOTION --
    from notion_logger import log_all_jobs

    logger.info("")
    logger.info("STEP 4/4 -- Logging to Notion...")
    logged = log_all_jobs(jobs)

    # -- SUMMARY --
    elapsed = (datetime.now() - start).total_seconds()
    auto_apply = len([j for j in jobs if j.get("action") == "auto_apply"])
    referrals = len([j for j in jobs if j.get("action") == "ask_referral"])
    flagged = len([j for j in jobs if j.get("action") == "flag_for_review"])

    logger.info("")
    logger.info("=" * 60)
    logger.info("PIPELINE COMPLETE")
    logger.info(f"  Total scored:     {len(jobs)} jobs")
    logger.info(f"  Score 7+:         {auto_apply + referrals} (apply via Comet)")
    logger.info(f"  Has connection:   {referrals} (ask referral first)")
    logger.info(f"  Score 6 (review): {flagged}")
    logger.info(f"  Logged to Notion: {logged} new entries")
    logger.info(f"  Time:             {elapsed:.0f}s")
    logger.info("=" * 60)


def run_gmail_check():
    """Scan Gmail and update Notion statuses."""
    logger.info("Scanning Gmail for job updates...")
    import config
    if not config.GMAIL_ADDRESS or config.GMAIL_ADDRESS.startswith("your_"):
        logger.info("Gmail not configured, skipping")
        return

    from gmail_monitor import scan_gmail, apply_updates_to_notion
    import notion_logger

    updates = scan_gmail(hours_back=max(config.GMAIL_CHECK_INTERVAL // 60 + 1, 2) * 60)
    if updates:
        count = apply_updates_to_notion(updates, notion_logger)
        logger.info(f"  -> Updated {count} Notion entries from email")
    else:
        logger.info("  -> No job-related emails found")


def main():
    parser = argparse.ArgumentParser(description="Job Hunter Bot -- Lean Pipeline")
    parser.add_argument("--schedule", action="store_true", help="Run daily + Gmail monitoring")
    parser.add_argument("--time", default="08:00", help="Daily run time (default: 08:00)")
    parser.add_argument("--gmail-only", action="store_true", help="Only scan Gmail, don't scrape")
    args = parser.parse_args()

    if args.gmail_only:
        run_gmail_check()
        return

    if args.schedule:
        import schedule
        import time
        import config

        logger.info("SCHEDULER MODE")
        logger.info(f"  Job pipeline: 2x daily (8:00 AM, 9:00 PM)")
        logger.info(f"  Gmail check:  every {config.GMAIL_CHECK_INTERVAL} minutes")
        logger.info(f"  Press Ctrl+C to stop")
        logger.info("")

        run_pipeline()
        run_gmail_check()

        # 2 runs per day: morning catch + evening sweep
        schedule.every().day.at("08:00").do(run_pipeline)
        schedule.every().day.at("21:00").do(run_pipeline)
        schedule.every(config.GMAIL_CHECK_INTERVAL).minutes.do(run_gmail_check)

        while True:
            schedule.run_pending()
            time.sleep(30)
    else:
        run_pipeline()


if __name__ == "__main__":
    main()
