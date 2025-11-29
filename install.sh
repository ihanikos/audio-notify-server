#!/bin/bash
#
# Installation script for audio-notify-server
# Installs the package and sets up a systemd user service for ZeroTier
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_NAME="audio-notify-server"
INTERFACE_PREFIX="${1:-zt}"  # Default to ZeroTier, can override with argument

echo "=== audio-notify-server installer ==="
echo ""

# Check if running as root (we don't want that for user service)
if [[ $EUID -eq 0 ]]; then
    echo "Error: Do not run this script as root."
    echo "The service will be installed as a user service."
    exit 1
fi

# Check for Python
if ! command -v python3 &> /dev/null; then
    echo "Error: Python 3 is required but not found."
    exit 1
fi

# Install the package
echo "Installing audio-notify-server..."
pip install --user -e "$SCRIPT_DIR"

# Find where pip installed the script
INSTALL_PATH=$(python3 -c "import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))")
EXECUTABLE="$INSTALL_PATH/audio-notify-server"

if [[ ! -f "$EXECUTABLE" ]]; then
    # Try alternative location
    EXECUTABLE="$HOME/.local/bin/audio-notify-server"
fi

if [[ ! -f "$EXECUTABLE" ]]; then
    echo "Warning: Could not find installed executable, using module invocation"
    EXECUTABLE="python3 -m audio_notify_server.cli"
fi

echo "Executable: $EXECUTABLE"
echo ""

# Create systemd user directory
mkdir -p ~/.config/systemd/user

# Create the systemd service file
cat > ~/.config/systemd/user/${SERVICE_NAME}.service << EOF
[Unit]
Description=Audio Notification Server (ZeroTier)
Documentation=https://github.com/yourusername/audio-notify-server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
# Wait for ZeroTier interface to appear (up to 60 seconds)
ExecStartPre=/bin/bash -c 'for i in {1..30}; do ip link show | grep -q "^[0-9]*: ${INTERFACE_PREFIX}" && exit 0; sleep 2; done; echo "Warning: No ${INTERFACE_PREFIX}* interface found, starting anyway"'
ExecStart=${EXECUTABLE} --interface-prefix ${INTERFACE_PREFIX}
Restart=on-failure
RestartSec=5

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=default.target
EOF

echo "Created systemd service: ~/.config/systemd/user/${SERVICE_NAME}.service"
echo ""

# Reload systemd
systemctl --user daemon-reload

echo "=== Installation complete ==="
echo ""
echo "Commands:"
echo "  Start now:           systemctl --user start ${SERVICE_NAME}"
echo "  Enable on boot:      systemctl --user enable ${SERVICE_NAME}"
echo "  Start + enable:      systemctl --user enable --now ${SERVICE_NAME}"
echo "  Check status:        systemctl --user status ${SERVICE_NAME}"
echo "  View logs:           journalctl --user -u ${SERVICE_NAME} -f"
echo "  Stop:                systemctl --user stop ${SERVICE_NAME}"
echo "  Disable:             systemctl --user disable ${SERVICE_NAME}"
echo ""
echo "For the service to start on boot (before login), enable lingering:"
echo "  sudo loginctl enable-linger $USER"
echo ""
echo "Interface prefix: ${INTERFACE_PREFIX}* (change with: $0 <prefix>)"
echo ""

# Ask if user wants to enable now
read -p "Enable and start the service now? [y/N] " -n 1 -r
echo ""
if [[ $REPLY =~ ^[Yy]$ ]]; then
    systemctl --user enable --now ${SERVICE_NAME}
    echo ""
    echo "Service started. Checking status..."
    sleep 2
    systemctl --user status ${SERVICE_NAME} --no-pager || true
fi
