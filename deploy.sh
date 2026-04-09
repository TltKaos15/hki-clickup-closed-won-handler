#!/bin/bash
# Deployment script for HKI ClickUp Closed Won Webhook
# Run as root on the Hostinger VPS
# Clones from GitHub and sets up the full stack

set -e

REPO_URL="https://github.com/TltKaos15/hki-clickup-closed-won-handler.git"
APP_DIR="/opt/closed-won-handler"
APP_USER="webhookapp"
DOMAIN="webhooks.kmaclabs.cloud"

echo "=== Step 1: Install dependencies ==="
apt-get update -qq
apt-get install -y -qq python3-pip python3-venv git > /dev/null

echo ""
echo "=== Step 2: Create app user ==="
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -s /bin/false "$APP_USER"
    echo "Created user $APP_USER"
else
    echo "User $APP_USER already exists"
fi

echo ""
echo "=== Step 3: Clone repo from GitHub ==="
if [ -d "$APP_DIR/.git" ]; then
    echo "Repo already exists, pulling latest..."
    cd "$APP_DIR"
    git pull origin main
else
    rm -rf "$APP_DIR"
    git clone "$REPO_URL" "$APP_DIR"
    cd "$APP_DIR"
fi

echo ""
echo "=== Step 4: Create virtual environment and install dependencies ==="
python3 -m venv venv
source venv/bin/activate
pip install -q -r requirements.txt

echo ""
echo "=== Step 5: Create .env file ==="
if [ ! -f .env ]; then
    read -p "Enter your ClickUp API token: " CLICKUP_TOKEN
    echo "CLICKUP_API_TOKEN=$CLICKUP_TOKEN" > .env
    echo "Created .env file"
else
    echo ".env already exists, skipping"
fi

chown -R "$APP_USER":"$APP_USER" "$APP_DIR"

echo ""
echo "=== Step 6: Create systemd service ==="
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
echo "=== Step 7: Configure nginx ==="
cat > /etc/nginx/sites-available/$DOMAIN << EOF
server {
    listen 80;
    server_name $DOMAIN;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/
nginx -t && systemctl reload nginx

echo ""
echo "=== Step 8: Set up SSL with certbot ==="
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email mickey@kmaclabs.cloud --redirect || echo "Certbot failed — you may need to run this manually after DNS propagates"

echo ""
echo "=== Step 9: Open firewall ports ==="
ufw allow 80/tcp 2>/dev/null || true
ufw allow 443/tcp 2>/dev/null || true

echo ""
echo "=== Deployment complete! ==="
echo "Service status:"
systemctl status closed-won-handler --no-pager
echo ""
echo "To update in the future, just run:"
echo "  cd $APP_DIR && git pull origin main && sudo systemctl restart closed-won-handler"
echo ""
echo "Test with:"
echo "  curl https://$DOMAIN/health"
