"""
Configuration
==============
Reads .env for secrets. Edit APPLICANT_PROFILE and JOB_TITLES below
to match your own background.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# -- API Keys --
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
NOTION_API_KEY = os.getenv("NOTION_API_KEY", "")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID", "")

# -- Gmail (for monitoring interview/rejection emails) --
GMAIL_ADDRESS = os.getenv("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")

# -- File paths --
CONNECTIONS_CSV_PATH = os.getenv("CONNECTIONS_CSV_PATH", "connections.csv")

# -- Search settings --
SEARCH_LOCATIONS = [
    loc.strip()
    for loc in os.getenv("SEARCH_LOCATIONS", "United States").split(",")
]
DAYS_BACK = int(os.getenv("DAYS_BACK", "2"))

# -- Scoring thresholds --
AUTO_APPLY_MIN = int(os.getenv("AUTO_APPLY_MIN", "7"))
FLAG_MIN = int(os.getenv("FLAG_MIN", "6"))

# -- Schedule --
PIPELINE_TIME = os.getenv("PIPELINE_TIME", "08:00")
GMAIL_CHECK_INTERVAL = int(os.getenv("GMAIL_CHECK_INTERVAL", "60"))

# ================================================================
# CUSTOMIZE BELOW -- Update these to match YOUR job search
# ================================================================

# Job titles to search for
JOB_TITLES = [
    "Product Manager",
    "Associate Product Manager",
    "Product Analyst",
    "Business Analyst",
    "Solution Architect",
]

# Sites to scrape via JobSpy (primary scraper)
# Supported: indeed, linkedin, zip_recruiter, google
# Glassdoor is currently broken/blocked
SCRAPE_SITES = ["indeed", "linkedin", "zip_recruiter", "google"]

# Your profile -- used to auto-fill application forms
# and to score job fit against your background
APPLICANT_PROFILE = {
    "first_name": "YOUR_FIRST_NAME",
    "last_name": "YOUR_LAST_NAME",
    "email": "YOUR_EMAIL",
    "phone": "YOUR_PHONE",
    "linkedin_url": "YOUR_LINKEDIN_URL",
    "city": "YOUR_CITY",
    "state": "YOUR_STATE",
    "years_experience": "YOUR_YEARS",
    "work_authorization": "YOUR_WORK_AUTH",
    "salary_expectations": "Open / Negotiable",
    "willing_to_relocate": "YOUR_PREFERENCE",
    "start_date": "YOUR_AVAILABILITY",
    "highest_education": "YOUR_DEGREE",
}
