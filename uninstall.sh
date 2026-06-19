#!/usr/bin/env bash
# uninstall.sh — remove the xwindow-tamer systemd user service and CLI symlink.
# Leaves the repo itself untouched.
set -euo pipefail

SERVICE_DIR="${HOME}/.config/systemd/user"
BIN_DIR="${HOME}/.local/bin"
SERVICE="xwindow-tamer.service"

systemctl --user disable --now "${SERVICE}" 2>/dev/null || true
rm -f "${SERVICE_DIR}/${SERVICE}"
rm -f "${BIN_DIR}/xwindow-tamer"
systemctl --user daemon-reload

echo "xwindow-tamer uninstalled (repo left in place)."
