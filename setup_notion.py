"""
Notion Database Setup
======================
Run ONCE to create the Job Tracker database with all columns.

Usage:  python setup_notion.py
"""

import requests
import sys
from dotenv import load_dotenv
import os

load_dotenv()

NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_API = "https://api.notion.com/v1"
HEADERS = {
    "Authorization": f"Bearer {NOTION_API_KEY}",
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}


def create_database(parent_page_id: str) -> str:
    """Create the Job Tracker database with all columns."""

    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "title": [{"type": "text", "text": {"content": "Job Tracker"}}],
        "properties": {
            "Job Title": {"title": {}},
            "Company": {"rich_text": {}},
            "Location": {"rich_text": {}},
            "Score": {"number": {"format": "number"}},
            "Fit Reason": {"rich_text": {}},
            "Seniority": {
                "select": {
                    "options": [
                        {"name": "junior", "color": "green"},
                        {"name": "mid", "color": "blue"},
                        {"name": "senior", "color": "purple"},
                        {"name": "unclear", "color": "gray"},
                    ]
                }
            },
            "Key Skills": {"rich_text": {}},
            "URL": {"url": {}},
            "Source": {
                "select": {
                    "options": [
                        {"name": "indeed", "color": "blue"},
                        {"name": "linkedin", "color": "default"},
                        {"name": "glassdoor", "color": "green"},
                        {"name": "unknown", "color": "gray"},
                    ]
                }
            },
            "Status": {
                "select": {
                    "options": [
                        {"name": "New", "color": "default"},
                        {"name": "Ask Referral", "color": "yellow"},
                        {"name": "Ready to Apply", "color": "orange"},
                        {"name": "Review", "color": "blue"},
                        {"name": "Auto-Applied", "color": "green"},
                        {"name": "Applied", "color": "green"},
                        {"name": "Interview", "color": "purple"},
                        {"name": "Offer", "color": "pink"},
                        {"name": "Rejected", "color": "red"},
                        {"name": "Skipped", "color": "gray"},
                    ]
                }
            },
            "Salary": {"rich_text": {}},
            "Date Posted": {"date": {}},
            "Referral Info": {"rich_text": {}},
            "Resume Path": {"rich_text": {}},
            "Cover Letter Path": {"rich_text": {}},
            "Notes": {"rich_text": {}},
        },
    }

    resp = requests.post(f"{NOTION_API}/databases", headers=HEADERS, json=payload)

    if resp.status_code == 200:
        db_id = resp.json()["id"]
        print(f"\n[OK] Database created!")
        print(f"\n   Database ID: {db_id}")
        print(f"\n   -> Paste this into your .env as NOTION_DATABASE_ID")
        return db_id
    else:
        print(f"\n[ERROR] Failed: {resp.status_code}")
        print(resp.json())
        sys.exit(1)


def main():
    if not NOTION_API_KEY or NOTION_API_KEY.startswith("your_"):
        print("[ERROR] Set NOTION_API_KEY in .env first.")
        sys.exit(1)

    print("=" * 50)
    print("NOTION DATABASE SETUP")
    print("=" * 50)
    print()
    print("Find your page ID:")
    print("  1. Open the page in Notion")
    print("  2. Share -> Copy link")
    print("  3. The 32-char hex string at the end of the URL is the ID")
    print()

    page_id = input("Paste the parent page ID: ").strip()
    if "notion.so" in page_id:
        page_id = page_id.split("-")[-1].split("?")[0]
    if len(page_id) < 20:
        print("[ERROR] Invalid page ID")
        sys.exit(1)

    create_database(page_id)


if __name__ == "__main__":
    main()
