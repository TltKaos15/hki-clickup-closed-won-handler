"""
HKI ClickUp Closed Won Handoff Webhook

Flask app that receives a webhook from Zapier when a deal closes won,
then copies custom field values from the Sales CRM task to the
Client Snapshot task in the new client folder.
"""

import os
import logging
from flask import Flask, request, jsonify
from dotenv import load_dotenv

from lib.clickup import (
    get_task,
    get_folder_lists,
    get_list_tasks,
    update_task_field,
    TaskNotFoundError,
    FolderNotFoundError,
)
from lib.field_mapping import (
    FIELD_MAP,
    extract_field_values,
    format_value_for_update,
)

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

DISCOVERY_INTAKE_LIST_NAME = "Discovery + Intake"
CLIENT_SNAPSHOT_TASK_NAME = "Client Snapshot"


@app.route("/webhook", methods=["POST"])
def webhook():
    token = os.environ.get("CLICKUP_API_TOKEN")
    if not token:
        logger.error("CLICKUP_API_TOKEN not set")
        return jsonify({"status": "error", "message": "Server misconfigured"}), 500

    body = request.get_json(silent=True)
    if not body:
        return jsonify({"status": "error", "message": "Invalid JSON body"}), 400

    sales_crm_task_id = body.get("sales_crm_task_id")
    new_folder_id = body.get("new_folder_id")

    if not sales_crm_task_id or not new_folder_id:
        return jsonify({
            "status": "error",
            "message": "Missing required fields: sales_crm_task_id and new_folder_id",
        }), 400

    logger.info(
        f"Received webhook: sales_crm_task_id={sales_crm_task_id}, "
        f"new_folder_id={new_folder_id}"
    )

    # Step 1: Fetch Sales CRM task
    try:
        sales_task = get_task(token, sales_crm_task_id)
    except TaskNotFoundError:
        return jsonify({
            "status": "error",
            "message": f"Sales CRM task {sales_crm_task_id} not found",
        }), 404
    except Exception as e:
        logger.error(f"Error fetching sales task: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error fetching sales task: {e}",
        }), 500

    # Step 2: Extract custom field values
    custom_fields = sales_task.get("custom_fields", [])
    field_values = extract_field_values(custom_fields)
    logger.info(f"Extracted {len(field_values)} field values from sales task")

    if not field_values:
        return jsonify({
            "status": "success",
            "message": "No custom field values to copy",
            "sales_task_id": sales_crm_task_id,
            "fields_updated": [],
            "fields_skipped": [FIELD_MAP[fid]["name"] for fid in FIELD_MAP],
            "fields_failed": [],
        }), 200

    # Step 3: Find Discovery + Intake list in new folder
    try:
        lists = get_folder_lists(token, new_folder_id)
    except FolderNotFoundError:
        return jsonify({
            "status": "error",
            "message": f"Folder {new_folder_id} not found",
        }), 404
    except Exception as e:
        logger.error(f"Error fetching folder lists: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error fetching folder lists: {e}",
        }), 500

    discovery_list = None
    for lst in lists:
        if lst.get("name") == DISCOVERY_INTAKE_LIST_NAME:
            discovery_list = lst
            break

    if not discovery_list:
        list_names = [lst.get("name") for lst in lists]
        return jsonify({
            "status": "error",
            "message": (
                f"'{DISCOVERY_INTAKE_LIST_NAME}' list not found in folder. "
                f"Available lists: {list_names}"
            ),
        }), 404

    discovery_list_id = discovery_list["id"]
    logger.info(f"Found Discovery + Intake list: {discovery_list_id}")

    # Step 4: Find Client Snapshot task
    try:
        tasks = get_list_tasks(token, discovery_list_id)
    except Exception as e:
        logger.error(f"Error fetching list tasks: {e}")
        return jsonify({
            "status": "error",
            "message": f"Error fetching tasks in Discovery + Intake: {e}",
        }), 500

    snapshot_task = None
    for task in tasks:
        if task.get("name") == CLIENT_SNAPSHOT_TASK_NAME:
            snapshot_task = task
            break

    if not snapshot_task:
        task_names = [t.get("name") for t in tasks]
        return jsonify({
            "status": "error",
            "message": (
                f"'{CLIENT_SNAPSHOT_TASK_NAME}' task not found in Discovery + Intake. "
                f"Available tasks: {task_names}"
            ),
        }), 404

    snapshot_task_id = snapshot_task["id"]
    logger.info(f"Found Client Snapshot task: {snapshot_task_id}")

    # Step 5: Update custom fields on Client Snapshot
    fields_updated = []
    fields_failed = []
    fields_skipped = []

    for field_id, meta in FIELD_MAP.items():
        if field_id not in field_values:
            fields_skipped.append(meta["name"])
            continue

        raw_value = field_values[field_id]
        formatted_value = format_value_for_update(field_id, raw_value)

        success = update_task_field(token, snapshot_task_id, field_id, formatted_value)
        if success:
            fields_updated.append(meta["name"])
        else:
            fields_failed.append(meta["name"])

    total = len(fields_updated) + len(fields_failed)
    if fields_failed and fields_updated:
        status = "partial"
    elif fields_failed and not fields_updated:
        status = "error"
    else:
        status = "success"

    message = f"Updated {len(fields_updated)} of {total} fields on Client Snapshot"
    logger.info(f"Result: {message}")

    return jsonify({
        "status": status,
        "message": message,
        "sales_task_id": sales_crm_task_id,
        "snapshot_task_id": snapshot_task_id,
        "fields_updated": fields_updated,
        "fields_skipped": fields_skipped,
        "fields_failed": fields_failed,
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)
