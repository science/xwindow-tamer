#!/usr/bin/env bash
# install.sh — install xwindow-tamer as a systemd user service (X11/Cinnamon).
#
# Model (same as ~/dev/anomalous-mon, brightness-ctl): the service ExecStart and
# the CLI symlink both point back at this repo, so editing the repo IS the
# deploy — no copy step to drift out of sync. A fresh machine gets this for free
# because `yadm bootstrap` clones the repo and runs this installer.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SERVICE_DIR="${HOME}/.config/systemd/user"
BIN_DIR="${HOME}/.local/bin"
SERVICE="xwindow-tamer.service"

# The daemon needs gi/Wnck/yaml on the system python3. Fail loud, with the fix.
if ! /usr/bin/python3 - <<'PY' 2>/dev/null
import gi, yaml  # noqa
gi.require_version("Wnck", "3.0"); gi.require_version("Gtk", "3.0")
from gi.repository import Wnck, Gtk  # noqa
PY
then
    echo "ERROR: /usr/bin/python3 is missing gi/Wnck/yaml. Install them with:" >&2
    echo "  sudo apt install python3-gi gir1.2-wnck-3.0 gir1.2-gtk-3.0 python3-yaml" >&2
    exit 1
fi

chmod +x "${SCRIPT_DIR}/bin/xwindow-tamer"
mkdir -p "${SERVICE_DIR}" "${BIN_DIR}"

# CLI symlink for manual use (xwindow-tamer --dry-run, --once, etc.).
ln -sfn "${SCRIPT_DIR}/bin/xwindow-tamer" "${BIN_DIR}/xwindow-tamer"

# Systemd user service. WantedBy=default.target — NOT graphical-session.target,
# which Cinnamon does not activate. StartLimitIntervalSec=0 + Restart=on-failure
# means that if we start before X is reachable at login, we keep retrying until
# DISPLAY answers instead of giving up after a few quick failures.
cat > "${SERVICE_DIR}/${SERVICE}" <<EOF
[Unit]
Description=xwindow-tamer: rule-based, event-driven X11 window placement
After=default.target
StartLimitIntervalSec=0

[Service]
Type=simple
ExecStart=${SCRIPT_DIR}/bin/xwindow-tamer
Environment=DISPLAY=:0
Restart=on-failure
RestartSec=2

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now "${SERVICE}"

echo "xwindow-tamer installed and started."
echo "  Status:  systemctl --user status ${SERVICE}"
echo "  Logs:    journalctl --user -u ${SERVICE} -f"
echo "  Manual:  xwindow-tamer --dry-run --once   (symlinked to ${BIN_DIR}/xwindow-tamer)"
echo "  Rules:   ${SCRIPT_DIR}/config/rules.yaml"
case ":$PATH:" in
    *":${BIN_DIR}:"*) ;;
    *) echo "NOTE: ${BIN_DIR} is not on your \$PATH — add it to run 'xwindow-tamer' directly." ;;
esac
