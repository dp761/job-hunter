"""
LinkedIn Connections Checker
==============================
Loads your exported LinkedIn connections CSV and checks if you
have a 1st-degree connection at any company in the job list.

How to export your connections:
  1. Go to linkedin.com -> Settings -> Data Privacy
  2. Click "Get a copy of your data"
  3. Select "Connections" -> Request archive
  4. Download and extract -> find "Connections.csv"
  5. Place it in the job-hunter folder as connections.csv
"""

import csv
import logging
import os
from collections import defaultdict
import config

logger = logging.getLogger(__name__)

# Cache so we only load the CSV once per run
_connections_cache: dict[str, list[dict]] | None = None


def _normalize(name: str) -> str:
    """Normalize company name for fuzzy matching."""
    name = name.lower().strip()
    # Remove common suffixes
    for suffix in [", inc.", ", inc", " inc.", " inc", ", llc", " llc",
                   ", ltd", " ltd", " corp", " corporation", " co.",
                   " company", " technologies", " technology", " group"]:
        name = name.replace(suffix, "")
    return name.strip()


def load_connections() -> dict[str, list[dict]]:
    """
    Load LinkedIn connections CSV.
    Returns dict: normalized_company_name -> list of {name, profile_url, position}
    """
    global _connections_cache
    if _connections_cache is not None:
        return _connections_cache

    csv_path = config.CONNECTIONS_CSV_PATH
    if not os.path.exists(csv_path):
        logger.warning(f"Connections CSV not found at '{csv_path}'. Skipping connection check.")
        _connections_cache = {}
        return _connections_cache

    by_company = defaultdict(list)

    try:
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                first = row.get("First Name", "").strip()
                last = row.get("Last Name", "").strip()
                company = row.get("Company", "").strip()
                position = row.get("Position", "").strip()
                url = row.get("URL", "").strip()

                if not company:
                    continue

                by_company[_normalize(company)].append({
                    "name": f"{first} {last}".strip(),
                    "position": position,
                    "profile_url": url,
                    "company_raw": company,
                })

        logger.info(f"Loaded {sum(len(v) for v in by_company.values())} connections at {len(by_company)} companies")
        _connections_cache = dict(by_company)
        return _connections_cache

    except Exception as e:
        logger.warning(f"Failed to load connections CSV: {e}")
        _connections_cache = {}
        return _connections_cache


def check_connections(jobs: list[dict]) -> list[dict]:
    """
    For each job, check if we have connections at that company.
    Adds 'connections' field (list of matching people) and
    updates action to 'ask_referral' if connections found and score >= AUTO_APPLY_MIN.
    """
    conn_map = load_connections()
    if not conn_map:
        logger.info("No connections data -- skipping referral check")
        return jobs

    referral_count = 0

    for job in jobs:
        company_norm = _normalize(job.get("company", ""))
        matches = conn_map.get(company_norm, [])

        # Also try partial matching (e.g., "Google" matches "Google LLC")
        if not matches:
            for key, people in conn_map.items():
                if company_norm in key or key in company_norm:
                    matches = people
                    break

        job["connections"] = matches

        if matches and job.get("action") == "auto_apply":
            job["action"] = "ask_referral"
            referral_count += 1
            names = ", ".join(p["name"] for p in matches[:3])
            logger.info(f"  -> Connection found at {job['company']}: {names} -> ask referral first")

    logger.info(f"Found connections at {referral_count} companies (will ask referral before applying)")
    return jobs
