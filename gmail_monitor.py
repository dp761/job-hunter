"""
Gmail Monitor
==============
Scans your Gmail inbox for job application responses (interviews,
rejections, follow-ups) and auto-updates Notion status.

Uses IMAP (free, no API setup needed) -- requires a Gmail App Password.
"""

import imaplib
import email
import logging
import re
import time
from datetime import datetime, timedelta
from email.header import decode_header
import config

logger = logging.getLogger(__name__)

# Keywords that indicate different outcomes
INTERVIEW_KEYWORDS = [
    "interview", "schedule a call", "phone screen", "next steps",
    "meet the team", "technical assessment", "take-home", "coding challenge",
    "we'd like to invite", "availability", "calendar invite",
    "hiring manager", "panel interview", "on-site",
]

REJECTION_KEYWORDS = [
    "unfortunately", "not moving forward", "other candidates",
    "not a fit", "decided not to", "position has been filled",
    "not selected", "regret to inform", "pursuing other",
    "will not be moving", "after careful consideration",
]

OFFER_KEYWORDS = [
    "offer letter", "pleased to offer", "extend an offer",
    "compensation package", "start date", "offer of employment",
]

# Common automated sender patterns to ignore
IGNORE_SENDERS = [
    "noreply", "no-reply", "donotreply", "notifications",
    "marketing", "newsletter", "promo",
]


def _decode_subject(msg) -> str:
    """Decode email subject safely."""
    subject = msg.get("Subject", "")
    if subject:
        decoded = decode_header(subject)
        parts = []
        for part, charset in decoded:
            if isinstance(part, bytes):
                parts.append(part.decode(charset or "utf-8", errors="replace"))
            else:
                parts.append(str(part))
        return " ".join(parts)
    return ""


def _get_body(msg) -> str:
    """Extract plain text body from email."""
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    charset = part.get_content_charset() or "utf-8"
                    body += payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset() or "utf-8"
            body = payload.decode(charset, errors="replace")
    return body[:3000]  # Limit for processing


def _classify_email(subject: str, body: str) -> str | None:
    """
    Classify an email as interview, rejection, offer, or None.
    Returns the status string or None if not job-related.
    """
    combined = (subject + " " + body).lower()

    # Check offer first (most specific)
    if any(kw in combined for kw in OFFER_KEYWORDS):
        return "Offer"

    # Check interview
    if any(kw in combined for kw in INTERVIEW_KEYWORDS):
        return "Interview"

    # Check rejection
    if any(kw in combined for kw in REJECTION_KEYWORDS):
        return "Rejected"

    return None


def _extract_company(subject: str, body: str, sender: str) -> str | None:
    """Try to extract the company name from the email."""
    # Common patterns: "Your application to [Company]", "from [Company]"
    patterns = [
        r"application (?:to|at|with) (\w[\w\s&.]+?)(?:\s*[----]|\s*for|\s*\n|$)",
        r"from (\w[\w\s&.]+?) (?:team|hiring|recruitment|hr)",
        r"at (\w[\w\s&.]+?)(?:\s*[----,.]|\s*for|\s*\n|$)",
        r"(\w[\w\s&.]+?) (?:is pleased|would like|has reviewed)",
    ]

    combined = subject + " " + body[:500]
    for pattern in patterns:
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            company = match.group(1).strip()
            if len(company) > 2 and len(company) < 50:
                return company

    # Try extracting from sender domain
    domain_match = re.search(r"@([\w.-]+)\.", sender)
    if domain_match:
        domain = domain_match.group(1)
        if domain not in ["gmail", "yahoo", "outlook", "hotmail"]:
            return domain.capitalize()

    return None


def scan_gmail(hours_back: int = 24) -> list[dict]:
    """
    Scan Gmail for recent job-related emails.
    Returns list of {company, status, subject, date} dicts.
    """
    if not config.GMAIL_ADDRESS or not config.GMAIL_APP_PASSWORD:
        logger.warning("Gmail credentials not set -- skipping email scan")
        return []

    updates = []

    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com")
        mail.login(config.GMAIL_ADDRESS, config.GMAIL_APP_PASSWORD)
        mail.select("INBOX")

        # Search for recent emails
        since_date = (datetime.now() - timedelta(hours=hours_back)).strftime("%d-%b-%Y")
        _, msg_nums = mail.search(None, f'(SINCE "{since_date}")')

        if not msg_nums[0]:
            logger.info("No new emails found")
            mail.logout()
            return []

        msg_ids = msg_nums[0].split()
        logger.info(f"Scanning {len(msg_ids)} emails from the last {hours_back}h...")

        for mid in msg_ids:
            _, msg_data = mail.fetch(mid, "(RFC822)")
            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)

            sender = msg.get("From", "").lower()

            # Skip obvious non-job emails
            if any(s in sender for s in IGNORE_SENDERS):
                continue

            subject = _decode_subject(msg)
            body = _get_body(msg)
            status = _classify_email(subject, body)

            if status:
                company = _extract_company(subject, body, sender)
                updates.append({
                    "company": company,
                    "status": status,
                    "subject": subject[:100],
                    "sender": sender,
                    "date": msg.get("Date", ""),
                })
                logger.info(f"  -> {status}: {company or 'Unknown'} -- {subject[:60]}")

        mail.logout()
        logger.info(f"Found {len(updates)} job-related email updates")

    except Exception as e:
        logger.error(f"Gmail scan failed: {e}")

    return updates


def apply_updates_to_notion(updates: list[dict], notion_module) -> int:
    """
    Match email updates to Notion entries and update their status.
    Returns count of successful updates.
    """
    if not updates:
        return 0

    count = 0
    for update in updates:
        if not update.get("company"):
            logger.info(f"  -> Skipping update (no company extracted): {update['subject']}")
            continue

        success = notion_module.update_status_by_company(
            company=update["company"],
            new_status=update["status"],
            note=f"Email: {update['subject']}",
        )

        if success:
            count += 1
            logger.info(f"  -> Updated Notion: {update['company']} -> {update['status']}")
        else:
            logger.info(f"  -> No Notion match for company: {update['company']}")

    return count
