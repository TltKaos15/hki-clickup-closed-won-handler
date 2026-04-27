"""
Weekly Meeting Agenda Creator

Creates meeting agenda pages in the Meeting Notes doc.
Run with a meeting type argument:

    python meeting_agenda.py team     # Friday cron — creates Thu team meeting page
    python meeting_agenda.py jm       # Tuesday cron — creates Mon J&M meeting page
    python meeting_agenda.py all      # Creates both (for testing)
"""

import os
import sys
import logging
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

WORKSPACE_ID = "90171002551"
DOC_ID = "2kz9rknq-1537"

MEETINGS = {
    "team": {
        "parent_page_id": "2kz9rknq-517",  # "Weekly Team Meetings"
        "target_weekday": 3,  # Thursday
        "name_format": "%-m/%-d - Weekly Team Meeting",
        "content": """\
**Attendees**
*   [@hki-all](#user_group_mention#caa8fb2c-651c-48b0-8f04-1369376f2703)

**Agenda**
1. Announcements
2. Operations
3. Prospect Updates
4. Client Updates
5. Discussion topics
6. Next steps

**Action Items (Add otter action items here with tag)**
- [ ] @mention Task 1: _Brief description_
- [ ] @mention Task 2: _Brief description_
- [ ] @mention Task 3: _Brief description_

**Detailed Notes (Add otter summary notes here)**""",
    },
    "jm": {
        "parent_page_id": "2kz9rknq-617",  # "Weekly J&M Meetings"
        "target_weekday": 0,  # Monday
        "name_format": "%-m/%-d - Weekly Jenni and Mickey Meeting",
        "content": """\
**Attendees**
*   [@Jenni Arnold](#user_mention#101113187) [@Mickey Clinard](#user_mention#198194918)

**Agenda**
1. Announcements
2. Operations review
    1. Partnership agreement
    2. Accounting
    3. Banking
    4. Subscriptions
    5. Jenni rebrand
    6. Website
3. Prospects updates
4. Client updates
5. Discussion topics
6. Next steps

**Action Items (Add otter action items here)**
- [ ] @mention Task 1: _Brief description_
- [ ] @mention Task 2: _Brief description_
- [ ] @mention Task 3: _Brief description_

**Detailed Notes**
Place otter summary notes here.""",
    },
}


def get_next_weekday(target_weekday):
    """Calculate the date of the next occurrence of target_weekday (0=Mon, 3=Thu)."""
    today = datetime.now()
    days_ahead = target_weekday - today.weekday()
    if days_ahead <= 0:
        days_ahead += 7
    return today + timedelta(days=days_ahead)


def create_meeting_page(token, meeting_key):
    """Create a new meeting agenda page."""
    config = MEETINGS[meeting_key]
    meeting_date = get_next_weekday(config["target_weekday"])
    page_name = meeting_date.strftime(config["name_format"])

    logger.info(f"Creating agenda: {page_name}")

    url = f"https://api.clickup.com/api/v3/workspaces/{WORKSPACE_ID}/docs/{DOC_ID}/pages"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }
    payload = {
        "name": page_name,
        "parent_page_id": config["parent_page_id"],
        "sub_title": meeting_date.strftime("%A, %B %-d, %Y"),
        "content": config["content"],
        "content_format": "text/md",
    }

    resp = requests.post(url, headers=headers, json=payload)

    if resp.status_code in (200, 201):
        page = resp.json()
        page_id = page.get("id", "unknown")
        logger.info(f"Created page: {page_name} (id: {page_id})")
        return True
    else:
        logger.error(f"Failed to create page: {resp.status_code} — {resp.text}")
        return False


def main():
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        logger.error("CLICKUP_API_TOKEN not set")
        sys.exit(1)

    if len(sys.argv) < 2 or sys.argv[1] not in ("team", "jm", "all"):
        print("Usage: python meeting_agenda.py [team|jm|all]")
        sys.exit(1)

    meeting_type = sys.argv[1]
    keys = list(MEETINGS.keys()) if meeting_type == "all" else [meeting_type]

    all_ok = True
    for key in keys:
        if not create_meeting_page(token, key):
            all_ok = False

    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
