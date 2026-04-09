"""
Local test script for the Closed Won handoff logic.

Runs the full flow against the real ClickUp API using a test task.
Requires CLICKUP_API_TOKEN env var (or .env file).

Usage:
    python test_local.py <sales_crm_task_id> <new_folder_id>

Example:
    python test_local.py 86e0q3tnk 90177846631
"""

import sys
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("test_local")

from lib.clickup import get_task, get_folder_lists, get_list_tasks, update_task_field
from lib.field_mapping import FIELD_MAP, extract_field_values, format_value_for_update

DISCOVERY_INTAKE_LIST_NAME = "Discovery + Intake"
CLIENT_SNAPSHOT_TASK_NAME = "Client Snapshot"


def main():
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        print("ERROR: Set CLICKUP_API_TOKEN in .env or environment")
        sys.exit(1)

    if len(sys.argv) < 3:
        print("Usage: python test_local.py <sales_crm_task_id> <new_folder_id>")
        print("\nTo just test fetching the sales task fields (no folder needed):")
        print("  python test_local.py <sales_crm_task_id> --dry-run")
        sys.exit(1)

    sales_task_id = sys.argv[1]
    new_folder_id = sys.argv[2]
    dry_run = new_folder_id == "--dry-run"

    # Step 1: Fetch sales task
    print(f"\n{'='*60}")
    print(f"Step 1: Fetching Sales CRM task {sales_task_id}")
    print(f"{'='*60}")
    sales_task = get_task(token, sales_task_id)
    print(f"Task name: {sales_task.get('name')}")
    print(f"Status: {sales_task.get('status', {}).get('status')}")

    # Step 2: Extract field values
    print(f"\n{'='*60}")
    print("Step 2: Extracting custom field values")
    print(f"{'='*60}")
    custom_fields = sales_task.get("custom_fields", [])
    field_values = extract_field_values(custom_fields)

    for field_id, value in field_values.items():
        name = FIELD_MAP[field_id]["name"]
        ftype = FIELD_MAP[field_id]["type"]
        print(f"  {name} ({ftype}): {value}")

    skipped = [FIELD_MAP[fid]["name"] for fid in FIELD_MAP if fid not in field_values]
    if skipped:
        print(f"  Skipped (empty): {skipped}")

    if dry_run:
        print(f"\n{'='*60}")
        print("DRY RUN — stopping here (no folder ID provided)")
        print(f"{'='*60}")
        return

    # Step 3: Find Discovery + Intake list
    print(f"\n{'='*60}")
    print(f"Step 3: Fetching lists in folder {new_folder_id}")
    print(f"{'='*60}")
    lists = get_folder_lists(token, new_folder_id)
    for lst in lists:
        print(f"  List: {lst.get('name')} (id: {lst.get('id')})")

    discovery_list = None
    for lst in lists:
        if lst.get("name") == DISCOVERY_INTAKE_LIST_NAME:
            discovery_list = lst
            break

    if not discovery_list:
        print(f"ERROR: '{DISCOVERY_INTAKE_LIST_NAME}' not found!")
        sys.exit(1)

    discovery_list_id = discovery_list["id"]
    print(f"  → Found: {discovery_list_id}")

    # Step 4: Find Client Snapshot task
    print(f"\n{'='*60}")
    print(f"Step 4: Fetching tasks in Discovery + Intake")
    print(f"{'='*60}")
    tasks = get_list_tasks(token, discovery_list_id)
    for task in tasks:
        print(f"  Task: {task.get('name')} (id: {task.get('id')})")

    snapshot_task = None
    for task in tasks:
        if task.get("name") == CLIENT_SNAPSHOT_TASK_NAME:
            snapshot_task = task
            break

    if not snapshot_task:
        print(f"ERROR: '{CLIENT_SNAPSHOT_TASK_NAME}' not found!")
        sys.exit(1)

    snapshot_task_id = snapshot_task["id"]
    print(f"  → Found: {snapshot_task_id}")

    # Step 5: Update fields
    print(f"\n{'='*60}")
    print("Step 5: Updating custom fields on Client Snapshot")
    print(f"{'='*60}")
    for field_id, raw_value in field_values.items():
        name = FIELD_MAP[field_id]["name"]
        formatted = format_value_for_update(field_id, raw_value)
        print(f"  Updating {name} → {formatted}")
        success = update_task_field(token, snapshot_task_id, field_id, formatted)
        print(f"    {'✓ Success' if success else '✗ Failed'}")

    print(f"\n{'='*60}")
    print("Done!")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
