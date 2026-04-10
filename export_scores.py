"""Run this from your job-hunter folder: python export_scores.py"""

import requests
import os
from dotenv import load_dotenv

load_dotenv()

headers = {
    "Authorization": "Bearer " + os.getenv("NOTION_API_KEY", ""),
    "Content-Type": "application/json",
    "Notion-Version": "2022-06-28",
}

resp = requests.post(
    f"https://api.notion.com/v1/databases/{os.getenv('NOTION_DATABASE_ID')}/query",
    headers=headers,
    json={"sorts": [{"property": "Score", "direction": "descending"}], "page_size": 30},
)

print("\nScore | Job Title | Company | Status | Fit Reason")
print("-" * 100)

for page in resp.json().get("results", []):
    p = page["properties"]

    title = "N/A"
    if p.get("Job Title", {}).get("title"):
        title = p["Job Title"]["title"][0].get("text", {}).get("content", "N/A")

    company = "N/A"
    if p.get("Company", {}).get("rich_text"):
        company = p["Company"]["rich_text"][0].get("text", {}).get("content", "N/A")

    score = p.get("Score", {}).get("number", "N/A")

    reason = "N/A"
    if p.get("Fit Reason", {}).get("rich_text"):
        reason = p["Fit Reason"]["rich_text"][0].get("text", {}).get("content", "N/A")

    status = "N/A"
    if p.get("Status", {}).get("select"):
        status = p["Status"]["select"].get("name", "N/A")

    print(f"{score} | {title[:40]} | {company[:20]} | {status} | {reason[:50]}")
