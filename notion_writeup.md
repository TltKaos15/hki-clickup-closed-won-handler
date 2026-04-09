# Closed Won Handoff Automation

## Overview

When a deal in ClickUp's Sales Pipeline closes won, this automation:

1. **Zapier** detects the status change and clones the client folder template into Client Engagements
2. **Zapier** calls our webhook at `https://webhooks.kmaclabs.cloud/webhook`
3. **The webhook** copies 7 custom fields from the deal task to the Client Snapshot task in the new folder

## Fields Copied

- Company (text)
- Primary Contact (text)
- Contact Email (email)
- Contact Phone (phone)
- Opportunity Type (dropdown)
- Estimated Value (currency)
- Last Contact (date)

Empty fields are skipped. Failed field updates don't block the others.

## Infrastructure

- **Hosted on:** Hostinger VPS (`187.77.14.235`)
- **URL:** `https://webhooks.kmaclabs.cloud/webhook`
- **Stack:** Python / Flask / gunicorn / nginx / SSL via certbot
- **Service:** runs as `closed-won-handler` systemd service (auto-restarts on crash or reboot)
- **Repo:** [github.com/TltKaos15/hki-clickup-closed-won-handler](https://github.com/TltKaos15/hki-clickup-closed-won-handler)

## How to Deploy Updates

After pushing code changes to GitHub, SSH into the VPS and run:

```
cd /opt/closed-won-handler && git pull origin main && systemctl restart closed-won-handler
```

## Useful Commands (run on VPS via SSH)

| Command | What it does |
|---|---|
| `systemctl status closed-won-handler` | Check if service is running |
| `journalctl -u closed-won-handler -f` | Watch live logs |
| `systemctl restart closed-won-handler` | Restart the service |
| `curl https://webhooks.kmaclabs.cloud/health` | Test health check |

## Retry Behavior

ClickUp's template cloning is async — tasks may not exist immediately after the folder is created. The webhook retries up to 4 times (10s apart) before failing. This handles the race condition automatically.

## Zapier Configuration

- **Zap name:** Closed_Won_Handoff
- **Step 1:** ClickUp trigger → Task Changes in Sales Pipeline → status = Closed Won
- **Step 2:** Webhooks by Zapier → POST to ClickUp API to clone folder template (`90178067159`)
- **Step 3:** Webhooks by Zapier → POST to `https://webhooks.kmaclabs.cloud/webhook` with JSON body:
  - `sales_crm_task_id` → from Step 1
  - `new_folder_id` → from Step 2

## Key Reference IDs

| Item | ID |
|---|---|
| Workspace | `90171002551` |
| SalesCRM Space | `90174708397` |
| Sales Pipeline List | `901711942257` |
| Client Engagements Space | `90174986644` |
| Template Folder | `90177846631` |
| Folder Template ID (for Zapier) | `90178067159` |
