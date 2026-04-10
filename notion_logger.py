"""
Notion Logger (Resilient)
==========================
Auto-detects which columns exist in your database and only writes
to those. No more 400 errors from missing properties.
"""

import logging
import requests
from datetime import datetime
import config

logger = logging.getLogger(__name__)

NOTION_API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {config.NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

# Cache for database schema
_db_properties = None


def _get_db_properties() -> dict:
    """Fetch the database schema to know which columns exist."""
    global _db_properties
    if _db_properties is not None:
        return _db_properties

    url = f"{NOTION_API}/databases/{config.NOTION_DATABASE_ID}"
    try:
        resp = requests.get(url, headers=HEADERS)
        resp.raise_for_status()
        data = resp.json()
        _db_properties = data.get("properties", {})
        logger.info(f"Notion columns detected: {', '.join(_db_properties.keys())}")
        return _db_properties
    except Exception as e:
        logger.warning(f"Could not fetch database schema: {e}")
        return {}


def _find_prop_name(name: str) -> str | None:
    """Find actual Notion property name, tolerant of whitespace differences."""
    props = _get_db_properties()
    # Exact match first
    if name in props:
        return name
    # Try stripped matching (handles "Company " vs "Company")
    name_stripped = name.strip().lower()
    for key in props:
        if key.strip().lower() == name_stripped:
            return key
    return None


def _prop_exists(name: str) -> bool:
    """Check if a property exists in the database."""
    return _find_prop_name(name) is not None


def _prop_type(name: str) -> str:
    """Get the type of a property."""
    actual_name = _find_prop_name(name)
    if not actual_name:
        return ""
    props = _get_db_properties()
    return props.get(actual_name, {}).get("type", "")


def get_existing_urls() -> set:
    """Fetch all job URLs already in the Notion database."""
    existing = set()
    url = f"{NOTION_API}/databases/{config.NOTION_DATABASE_ID}/query"
    has_more = True
    start_cursor = None

    # Find which property holds URLs
    url_prop_name = None
    props = _get_db_properties()
    for name, prop in props.items():
        if prop.get("type") == "url":
            url_prop_name = name
            break

    if not url_prop_name:
        logger.warning("No URL column found in Notion database")
        return existing

    while has_more:
        payload = {"page_size": 100}
        if start_cursor:
            payload["start_cursor"] = start_cursor

        try:
            resp = requests.post(url, headers=HEADERS, json=payload)
            resp.raise_for_status()
            data = resp.json()

            for page in data.get("results", []):
                page_props = page.get("properties", {})
                url_prop = page_props.get(url_prop_name, {})
                if url_prop.get("url"):
                    existing.add(url_prop["url"])

            has_more = data.get("has_more", False)
            start_cursor = data.get("next_cursor")
        except Exception as e:
            logger.warning(f"Failed to fetch existing entries: {e}")
            break

    return existing


def _add_property(properties: dict, name: str, value):
    """Add a property to the payload only if it exists in the database."""
    actual_name = _find_prop_name(name)
    if not actual_name:
        return

    prop_type = _prop_type(name)

    try:
        if prop_type == "title":
            properties[actual_name] = {"title": [{"text": {"content": str(value)[:100]}}]}

        elif prop_type == "rich_text":
            properties[actual_name] = {"rich_text": [{"text": {"content": str(value)[:2000]}}]}

        elif prop_type == "number":
            properties[actual_name] = {"number": value if isinstance(value, (int, float)) else 0}

        elif prop_type == "url":
            properties[actual_name] = {"url": str(value) if value else None}

        elif prop_type == "select":
            properties[actual_name] = {"select": {"name": str(value)[:100]}}

        elif prop_type == "multi_select":
            if isinstance(value, list):
                properties[actual_name] = {"multi_select": [{"name": str(v)[:100]} for v in value[:10]]}
            else:
                properties[actual_name] = {"multi_select": [{"name": str(value)[:100]}]}

        elif prop_type == "date":
            if value:
                properties[actual_name] = {"date": {"start": str(value)}}

        elif prop_type == "checkbox":
            properties[actual_name] = {"checkbox": bool(value)}

    except Exception as e:
        logger.warning(f"  -> Could not set property '{name}': {e}")


def log_job(job: dict) -> bool:
    """Create a new page in the Notion database for a job."""
    url = f"{NOTION_API}/pages"

    # Determine status
    status_map = {
        "auto_apply": "Apply",
        "ask_referral": "Ask Referral",
        "flag_for_review": "Review",
    }
    status = status_map.get(job.get("action", ""), "New")

    # Build properties dynamically based on what columns exist
    properties = {}

    # Title property (required -- find whichever column is the title)
    props = _get_db_properties()
    title_col = None
    for name, prop in props.items():
        if prop.get("type") == "title":
            title_col = name
            break

    if title_col:
        _add_property(properties, title_col, job["title"])
    else:
        logger.error("No title column found in database!")
        return False

    # Standard properties -- bot writes to whichever ones exist
    _add_property(properties, "Company", job.get("company", ""))
    _add_property(properties, "Location", job.get("location", ""))
    _add_property(properties, "Score", job.get("score", 0))
    _add_property(properties, "Grade", job.get("overall_grade", ""))
    _add_property(properties, "Fit Reason", job.get("fit_reason", ""))
    _add_property(properties, "Dimensions", job.get("dimension_summary", ""))
    _add_property(properties, "Seniority", job.get("seniority", "unclear"))
    _add_property(properties, "Key Skills", ", ".join(job.get("key_skills", [])))
    _add_property(properties, "URL", job.get("url", ""))
    _add_property(properties, "Source", job.get("site", "unknown"))
    _add_property(properties, "Status", status)
    _add_property(properties, "Salary", job.get("salary", ""))

    # Date posted
    if job.get("date_posted"):
        try:
            date_str = job["date_posted"].strftime("%Y-%m-%d")
            _add_property(properties, "Date Posted", date_str)
        except Exception:
            pass

    # Connection / referral info
    if job.get("connections"):
        conn_lines = []
        for c in job["connections"][:3]:
            name = c.get("name", "")
            pos = c.get("position", "")
            profile = c.get("profile_url", "")
            conn_lines.append(f"{name} ({pos}) - {profile}")
        conn_text = "\n".join(conn_lines)
        _add_property(properties, "Referral Info", conn_text)

    payload = {
        "parent": {"database_id": config.NOTION_DATABASE_ID},
        "properties": properties,
    }

    # Add JD as page body so you can copy-paste into your Gem
    jd_text = job.get("description", "")
    if jd_text:
        blocks = []
        blocks.append({
            "object": "block",
            "type": "heading_2",
            "heading_2": {
                "rich_text": [{"type": "text", "text": {"content": "Job Description"}}]
            }
        })
        for i in range(0, min(len(jd_text), 6000), 2000):
            chunk = jd_text[i:i + 2000]
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": chunk}}]
                }
            })
        payload["children"] = blocks

    try:
        resp = requests.post(url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        logger.info(f"  -> Logged: {job['title']} @ {job['company']} [{status}]")
        return True
    except requests.exceptions.HTTPError as e:
        # Log the actual Notion error for debugging
        try:
            error_body = e.response.json()
            error_msg = error_body.get("message", str(e))
            logger.warning(f"  -> Notion error for '{job['title']}': {error_msg}")
        except Exception:
            logger.warning(f"  -> Failed to log '{job['title']}': {e}")
        return False
    except Exception as e:
        logger.warning(f"  -> Failed to log '{job['title']}': {e}")
        return False


def log_all_jobs(jobs: list[dict]) -> int:
    """Log all jobs to Notion, skipping duplicates."""
    existing_urls = get_existing_urls()
    logged = 0

    for job in jobs:
        if job["url"] in existing_urls:
            logger.info(f"  -> Skipped (duplicate): {job['title']}")
            continue
        if log_job(job):
            logged += 1

    logger.info(f"Logged {logged} new jobs to Notion")
    return logged


def update_status_by_company(company: str, new_status: str, note: str = "") -> bool:
    """
    Find a Notion entry by company name and update its status.
    Used by Gmail monitor for interview/rejection updates.
    """
    query_url = f"{NOTION_API}/databases/{config.NOTION_DATABASE_ID}/query"

    payload = {
        "filter": {
            "property": "Company",
            "rich_text": {"contains": company},
        },
        "sorts": [{"property": "Score", "direction": "descending"}],
        "page_size": 5,
    }

    try:
        resp = requests.post(query_url, headers=HEADERS, json=payload)
        resp.raise_for_status()
        results = resp.json().get("results", [])

        if not results:
            return False

        page_id = results[0]["id"]
        update_url = f"{NOTION_API}/pages/{page_id}"

        update_payload = {"properties": {}}

        if _prop_exists("Status"):
            update_payload["properties"]["Status"] = {"select": {"name": new_status}}
        if note and _prop_exists("Notes"):
            update_payload["properties"]["Notes"] = {
                "rich_text": [{"text": {"content": note[:200]}}]
            }

        resp = requests.patch(update_url, headers=HEADERS, json=update_payload)
        resp.raise_for_status()
        return True

    except Exception as e:
        logger.warning(f"Failed to update Notion for '{company}': {e}")
        return False
