"""Entrypoint: arg parsing, logging, Wnck/Gtk init, and the run loop.

  python3 -m window_tamer                 # daemon: place windows as they match
  python3 -m window_tamer --dry-run       # log plans, move nothing
  python3 -m window_tamer --once          # place current windows, then exit
  python3 -m window_tamer --dry-run --once  # smoke: log plans for current windows
"""
import argparse
import logging
import sys
from pathlib import Path

from .engine import Engine, connect_signals, consider
from .executor import apply_actions
from .monitors import load_monitors
from .rules import load_rules

log = logging.getLogger("window_tamer")

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "config" / "rules.yaml"
# Grace period for async move/maximize sequences to settle in --once (non-dry).
ONCE_GRACE_MS = 5000


def _parse_args(argv):
    p = argparse.ArgumentParser(prog="window_tamer", description=__doc__)
    p.add_argument("--dry-run", action="store_true",
                   help="log the plan for each match, but move nothing")
    p.add_argument("--once", action="store_true",
                   help="place current windows once, then exit (no event loop)")
    p.add_argument("--rules", default=str(DEFAULT_RULES),
                   help=f"path to rules.yaml (default: {DEFAULT_RULES})")
    p.add_argument("--log-level", default="INFO",
                   help="logging level (DEBUG/INFO/WARNING/...)")
    return p.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    import gi
    gi.require_version("Wnck", "3.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("GLib", "2.0")
    from gi.repository import GLib, Gtk, Wnck

    Gtk.init([])
    screen = Wnck.Screen.get_default()
    screen.force_update()  # populate the window list before we enumerate

    monitors = load_monitors()
    rules = load_rules(args.rules)
    log.info("monitors: %s", {n: (m.x, m.width) for n, m in monitors.items()})
    log.info("rules: %s", [r.name for r in rules])

    def execute(window, actions):
        apply_actions(window, actions, engine.monitors, screen)

    engine = Engine(rules, monitors, execute, dry_run=args.dry_run,
                    refresh_monitors=load_monitors)

    if args.once:
        for window in screen.get_windows():
            consider(engine, window)
        if args.dry_run:
            return 0
        # Let any async move/maximize sequences finish, then quit.
        GLib.timeout_add(ONCE_GRACE_MS, Gtk.main_quit)
        Gtk.main()
        return 0

    connect_signals(screen, engine)
    log.info("xwindow-tamer running (dry_run=%s); ctrl-c to stop", args.dry_run)
    try:
        Gtk.main()
    except KeyboardInterrupt:
        log.info("stopping")
    return 0


if __name__ == "__main__":
    sys.exit(main())
