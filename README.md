# HKI ClickUp Closed Won Handler

Webhook that automatically copies custom field values from a Sales CRM deal task to a Client Snapshot task when a deal closes won.

## How It Works

1. **Zapier Step 1** — ClickUp trigger detects a task status change to "Closed Won" in the Sales Pipeline list
2. **Zapier Step 2** — Clones the `[TEMPLATE] Client Name` folder into the Client Engagements space, named after the deal
3. **Zapier Step 3** — POSTs to this webhook with the deal task ID and new folder ID
4. **This script** — Fetches the deal's custom fields, finds the Client Snapshot task in the new folder's Discovery + Intake list, and copies 7 field values over

## Custom Fields Copied

| Field | Type |
|---|---|
| Company | Text |
| Primary Contact | Text |
| Contact Email | Email |
| Contact Phone | Phone |
| Opportunity Type | Dropdown |
| Estimated Value | Currency |
| Last Contact | Date |

Fields with empty/null values are skipped. If individual field updates fail, the script continues with remaining fields and returns a partial success response.

## Architecture

- **Flask** app served by **gunicorn** (2 workers)
- Reverse proxied through **nginx** with SSL via **certbot**
- Runs as a **systemd** service on Hostinger VPS (`187.77.14.235`)
- Live at `https://webhooks.kmaclabs.cloud/webhook`

## Endpoints

| Method | Path | Description |
|---|---|---|
| POST | `/webhook` | Main webhook — accepts `{"sales_crm_task_id": "...", "new_folder_id": "..."}` |
| GET | `/health` | Health check — returns `{"status": "ok"}` |

## Retry Logic

ClickUp's template cloning is asynchronous — lists and tasks may not be available immediately after folder creation. The script retries up to 4 times with 10-second delays (40 seconds total) before giving up.

## Environment Variables

| Variable | Description |
|---|---|
| `CLICKUP_API_TOKEN` | ClickUp API token (stored in `/opt/closed-won-handler/.env` on VPS) |

## Deploying Updates

When you make changes to the code:

1. **Push to GitHub** from your Mac
2. **SSH into the VPS** and run:

```bash
cd /opt/closed-won-handler && git pull origin main && systemctl restart closed-won-handler
```

That's it — the service restarts with the new code.

## Useful VPS Commands

```bash
# Check if the service is running
systemctl status closed-won-handler

# View live logs
journalctl -u closed-won-handler -f

# Restart the service
systemctl restart closed-won-handler

# Test the health endpoint
curl https://webhooks.kmaclabs.cloud/health

# Test the webhook manually
curl -X POST https://webhooks.kmaclabs.cloud/webhook \
  -H 'Content-Type: application/json' \
  -d '{"sales_crm_task_id":"TASK_ID_HERE","new_folder_id":"FOLDER_ID_HERE"}'
```

## Key IDs

| Item | ID |
|---|---|
| Workspace | `90171002551` |
| SalesCRM Space | `90174708397` |
| Sales Pipeline List | `901711942257` |
| Client Engagements Space | `90174986644` |
| Template Folder | `90177846631` |
| ClickUp Folder Template | `90178067159` |

## Local Development

```bash
# Clone the repo
git clone https://github.com/TltKaos15/hki-clickup-closed-won-handler.git
cd hki-clickup-closed-won-handler

# Set up venv
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Create .env
echo "CLICKUP_API_TOKEN=pk_..." > .env

# Run locally
python app.py

# Test
curl -X POST http://localhost:5000/webhook \
  -H 'Content-Type: application/json' \
  -d '{"sales_crm_task_id":"86e0q3tnk","new_folder_id":"FOLDER_ID"}'
```

## File Structure

```
├── app.py               # Flask webhook endpoint + orchestration
├── lib/
│   ├── __init__.py
│   ├── clickup.py       # ClickUp API client
│   └── field_mapping.py # Field IDs, types, value formatting
├── test_local.py        # Standalone test script
├── deploy.sh            # VPS deployment script
├── requirements.txt     # Python dependencies
├── .env.example         # Environment variable template
└── .gitignore
```
