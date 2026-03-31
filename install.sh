#!/bin/bash
# Run from the project directory as root: sudo bash install.sh
set -e

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_USER="${SUDO_USER:-$(logname)}"

echo "Installing from: $INSTALL_DIR"
echo "Running as user: $SERVICE_USER"

# Install dependencies including gunicorn
"$INSTALL_DIR/venv/bin/pip" install -r "$INSTALL_DIR/requirements.txt" -q

# Write systemd service file with real paths
sed -e "s|__INSTALL_DIR__|$INSTALL_DIR|g" \
    -e "s|__USER__|$SERVICE_USER|g" \
    "$INSTALL_DIR/online-questions.service" \
    > /etc/systemd/system/online-questions.service

systemctl daemon-reload
systemctl enable online-questions
systemctl restart online-questions
echo "Service started. Check with: systemctl status online-questions"
echo "Logs: journalctl -u online-questions -f"
echo ""

# Install nginx config
cp "$INSTALL_DIR/online-questions.nginx" /etc/nginx/sites-available/online-questions
ln -sf /etc/nginx/sites-available/online-questions /etc/nginx/sites-enabled/online-questions
nginx -t && systemctl reload nginx
echo "nginx configured for test.mattvenn.net"
