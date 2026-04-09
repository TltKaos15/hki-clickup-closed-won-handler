#!/bin/bash
# Deployment script for HKI ClickUp Closed Won Webhook
# Run as root on the Hostinger VPS

set -e

APP_DIR="/opt/closed-won-handler"
APP_USER="webhookapp"
DOMAIN="webhooks.kmaclabs.cloud"

echo "=== Step 1: Create app user ==="
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false "$APP_USER"
    echo "Created user $APP_USER"
else
    echo "User $APP_USER already exists"
fi

echo ""
echo "=== Step 2: Set up app directory ==="
mkdir -p "$APP_DIR"
cd "$APP_DIR"

echo ""
echo "=== Step 3: Install pip and venv ==="
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv > /dev/null

echo ""
echo "=== Step 4: Copy app files ==="
cat > app.py << 'PYEOF'
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
PYEOF

mkdir -p lib
cat > lib/__init__.py << 'PYEOF'
PYEOF

cat > lib/clickup.py << 'PYEOF'
import requests
import logging

logger = logging.getLogger(__name__)

BASE_URL = "https://api.clickup.com/api/v2"


def _headers(token):
    return {
        "Authorization": token,
        "Content-Type": "application/json",
    }


def get_task(token, task_id):
    url = f"{BASE_URL}/task/{task_id}"
    logger.info(f"Fetching task {task_id}")
    resp = requests.get(url, headers=_headers(token))

    if resp.status_code == 404:
        raise TaskNotFoundError(f"Task {task_id} not found")
    resp.raise_for_status()

    data = resp.json()
    logger.info(f"Fetched task: {data.get('name')} (id: {task_id})")
    return data


def get_folder_lists(token, folder_id):
    url = f"{BASE_URL}/folder/{folder_id}"
    logger.info(f"Fetching folder {folder_id}")
    resp = requests.get(url, headers=_headers(token))

    if resp.status_code == 404:
        raise FolderNotFoundError(f"Folder {folder_id} not found")
    resp.raise_for_status()

    data = resp.json()
    lists = data.get("lists", [])

    if lists:
        logger.info(f"Found {len(lists)} lists in folder via primary endpoint")
        return lists

    logger.info("Primary endpoint returned empty lists, trying fallback")
    url = f"{BASE_URL}/folder/{folder_id}/list"
    resp = requests.get(url, headers=_headers(token))
    resp.raise_for_status()

    lists = resp.json().get("lists", [])
    logger.info(f"Found {len(lists)} lists in folder via fallback endpoint")
    return lists


def get_list_tasks(token, list_id):
    url = f"{BASE_URL}/list/{list_id}/task"
    logger.info(f"Fetching tasks in list {list_id}")
    resp = requests.get(url, headers=_headers(token))
    resp.raise_for_status()

    tasks = resp.json().get("tasks", [])
    logger.info(f"Found {len(tasks)} tasks in list")
    return tasks


def update_task_field(token, task_id, field_id, value):
    url = f"{BASE_URL}/task/{task_id}/field/{field_id}"
    payload = {"value": value}
    logger.info(f"Updating field {field_id} on task {task_id} with value: {value}")

    try:
        resp = requests.post(url, headers=_headers(token), json=payload)

        if resp.status_code == 429:
            logger.warning(f"Rate limited updating field {field_id}")
            return False

        if not resp.ok:
            logger.error(
                f"Failed to update field {field_id}: "
                f"{resp.status_code} {resp.text}"
            )
            return False

        logger.info(f"Successfully updated field {field_id}")
        return True

    except requests.RequestException as e:
        logger.error(f"Request error updating field {field_id}: {e}")
        return False


class TaskNotFoundError(Exception):
    pass


class FolderNotFoundError(Exception):
    pass
PYEOF

cat > lib/field_mapping.py << 'PYEOF'
FIELD_MAP = {
    "7c409897-f0c8-451f-bd6c-79fa0dbf2cd6": {"name": "Company", "type": "short_text"},
    "3f019ca2-cde2-4de8-9830-08ceea00234b": {"name": "Primary Contact", "type": "short_text"},
    "b27b1a2f-e31c-4266-9339-42692223b899": {"name": "Contact Email", "type": "email"},
    "1787374a-cf49-4b29-a218-37a7e4f9a441": {"name": "Contact Phone", "type": "phone"},
    "e70535bc-bccc-4834-9ccf-0961ddac4ab4": {"name": "Opportunity Type", "type": "drop_down"},
    "2cf4a2e5-3c0b-4960-b296-80f9dbb3ed1a": {"name": "Estimated Value", "type": "currency"},
    "00819039-5cb0-4905-b20e-16ff7176cc72": {"name": "Last Contact", "type": "date"},
}

OPPORTUNITY_TYPE_OPTIONS = {
    "002e215f-3327-45eb-8172-75d818dc58c1": "Training",
    "3c30d4f2-3a8b-44b3-91eb-9ccefcd1ffd1": "Presentation",
    "2684f90a-37ac-400c-ba56-61d1ae582d29": "Workflow",
    "b7ad395c-fbb3-4b49-8746-49b01a3749f1": "Custom App",
}


def extract_field_values(custom_fields):
    values = {}
    for field in custom_fields:
        field_id = field.get("id")
        if field_id not in FIELD_MAP:
            continue

        field_type = FIELD_MAP[field_id]["type"]
        value = field.get("value")

        if field_type == "drop_down":
            if value is not None:
                type_config = field.get("type_config", {})
                options = type_config.get("options", [])
                if isinstance(value, int) and options:
                    for opt in options:
                        if opt.get("orderindex") == value:
                            values[field_id] = opt.get("id")
                            break
                    else:
                        values[field_id] = value
                elif isinstance(value, str):
                    values[field_id] = value
                else:
                    values[field_id] = value
            continue

        if value is None or value == "":
            continue

        values[field_id] = value

    return values


def format_value_for_update(field_id, raw_value):
    field_type = FIELD_MAP[field_id]["type"]

    if field_type in ("short_text", "email", "phone"):
        return str(raw_value)

    if field_type == "currency":
        return float(raw_value)

    if field_type == "date":
        return int(raw_value)

    if field_type == "drop_down":
        return str(raw_value)

    return raw_value
PYEOF

echo ""
echo "=== Step 5: Create virtual environment and install dependencies ==="
python3 -m venv venv
source venv/bin/activate
pip install -q flask requests python-dotenv gunicorn

echo ""
echo "=== Step 6: Create .env file ==="
if [ ! -f .env ]; then
    echo "CLICKUP_API_TOKEN=pk_198194918_JIW1QHCH5FSGRMPXMIUYI6UJP88VKFEE" > .env
    echo "Created .env file"
else
    echo ".env already exists, skipping"
fi

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

echo ""
echo "=== Step 7: Create systemd service ==="
cat > /etc/systemd/system/closed-won-handler.service << EOF
[Unit]
Description=HKI ClickUp Closed Won Webhook Handler
After=network.target

[Service]
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/gunicorn --bind 127.0.0.1:8000 --workers 2 --timeout 30 app:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable closed-won-handler
systemctl restart closed-won-handler

echo ""
echo "=== Step 8: Configure nginx ==="
cat > /etc/nginx/sites-available/webhooks.kmaclabs.cloud << EOF
server {
    listen 80;
    server_name webhooks.kmaclabs.cloud;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/webhooks.kmaclabs.cloud /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo ""
echo "=== Step 9: Set up SSL with certbot ==="
certbot --nginx -d webhooks.kmaclabs.cloud --non-interactive --agree-tos --email mickey@kmaclabs.cloud --redirect || echo "Certbot failed — you may need to run this manually after DNS is pointed to 187.77.14.235"

echo ""
echo "=== Step 10: Open firewall ports ==="
ufw allow 80/tcp 2>/dev/null || true
ufw allow 443/tcp 2>/dev/null || true

echo ""
echo "=== Deployment complete! ==="
echo "Service status:"
systemctl status closed-won-handler --no-pager
echo ""
echo "Test with:"
echo "  curl https://webhooks.kmaclabs.cloud/health"
echo "  curl -X POST https://webhooks.kmaclabs.cloud/webhook -H 'Content-Type: application/json' -d '{\"sales_crm_task_id\":\"86e0q3tnk\",\"new_folder_id\":\"90178067224\"}'"
