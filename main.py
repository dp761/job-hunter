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
