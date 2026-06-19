#!/bin/bash
#
# Test management script for xwindow-tamer.
#
# Usage:
#   ./scripts/test.sh [command]
#
# Commands:
#   unit      - Run pure unit tests (pytest, no X server needed)  [default]
#   smoke     - Run the daemon in --dry-run against live windows (needs X)
#   status    - Check that the runtime + test prerequisites are present
#   all       - status + unit
#   help      - Show this help
#
# Always uses /usr/bin/python3: it is the interpreter that has the apt-provided
# gi/Wnck bindings AND pytest. A venv would lose Wnck, so do not use one.

set -euo pipefail

PY=/usr/bin/python3
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

cmd_status() {
    echo "== xwindow-tamer prerequisites =="
    "$PY" - <<'PY'
import importlib, shutil, sys
ok = True
print("python:", sys.version.split()[0], "(", sys.executable, ")")
def check_mod(mod, label):
    global ok
    try:
        importlib.import_module(mod); print(f"  [ok] {label}")
    except Exception as e:
        ok = False; print(f"  [MISSING] {label}: {e.__class__.__name__}")
check_mod("yaml", "PyYAML (rules config)")
check_mod("pytest", "pytest (tests)")
import gi
for ns, ver in (("Wnck", "3.0"), ("Gtk", "3.0"), ("GLib", "2.0")):
    try:
        gi.require_version(ns, ver); importlib.import_module(f"gi.repository.{ns}")
        print(f"  [ok] gi {ns} {ver}")
    except Exception as e:
        ok = False; print(f"  [MISSING] gi {ns} {ver}: {e}")
print("  [ok] xrandr" if shutil.which("xrandr") else "  [MISSING] xrandr")
sys.exit(0 if ok and shutil.which("xrandr") else 1)
PY
}

cmd_unit() {
    echo "== unit tests =="
    "$PY" -m pytest "$@"
}

cmd_smoke() {
    echo "== smoke: dry-run against live windows (no windows will be moved) =="
    if [[ -z "${DISPLAY:-}" ]]; then
        echo "DISPLAY is unset -- smoke needs a running X session." >&2; exit 1
    fi
    "$PY" -m window_tamer --dry-run --once
}

case "${1:-unit}" in
    unit)   shift || true; cmd_unit "$@" ;;
    smoke)  cmd_smoke ;;
    status) cmd_status ;;
    all)    cmd_status && cmd_unit ;;
    help|-h|--help) sed -n '2,18p' "$0" | sed 's/^# \{0,1\}//' ;;
    *) echo "unknown command: $1 (try: help)" >&2; exit 2 ;;
esac
