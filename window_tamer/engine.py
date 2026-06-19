"""Place-once decision core + (Layer 2) Wnck signal wiring.

The decision core (`Engine`) is PURE and unit-tested with an injected `execute`
callback -- no Wnck window required. The whole point of this daemon is that a
window which does NOT yet match (its Simple Tab Groups title prefix hasn't been
applied yet) costs nothing and stays eligible, so the later `name-changed` event
that adds the prefix is what triggers placement. Only a window we actually place
is remembered, and `window-closed` forgets it so a reopen re-places.
"""
import logging
from typing import Callable, Optional

from .monitors import Monitor
from .planner import plan
from .rules import Rule, match_rule

log = logging.getLogger(__name__)

# execute(target, actions): apply the plan to a window. target is opaque to the
# core (a Wnck.Window in prod); the executor knows how to run the actions on it.
Execute = Callable[[object, list], None]


class Engine:
    def __init__(
        self,
        rules: list[Rule],
        monitors: dict[str, Monitor],
        execute: Execute,
        dry_run: bool = False,
    ):
        self.rules = rules
        self.monitors = monitors
        self.execute = execute
        self.dry_run = dry_run
        self.placed: set[int] = set()

    def place(self, xid: int, cls: str, title: str, target: object) -> Optional[Rule]:
        """Place `target` if it matches and hasn't been placed. Returns the
        matched Rule (whether or not it was executed, for logging), else None."""
        if xid in self.placed:
            return None
        rule = match_rule(self.rules, cls, title)
        if rule is None:
            return None
        actions = plan(rule, self.monitors)
        if self.dry_run:
            log.info("[dry-run] %s -> %s: %s", title, rule.name, actions)
        else:
            log.info("place %s -> %s: %s", title, rule.name, actions)
            self.execute(target, actions)
        self.placed.add(xid)
        return rule

    def forget(self, xid: int) -> None:
        """Forget a window (on close) so a future reopen is placed again."""
        self.placed.discard(xid)


# --------------------------------------------------------------------------
# Wnck signal wiring (Layer 2). Pure Python -- operates on objects passed in,
# so this stays importable without gi/X (only run() actually touches X).
# --------------------------------------------------------------------------


def window_props(window) -> tuple:
    """Extract (class, title) for rule matching. Class group name is the WM_CLASS
    we match against (e.g. 'Firefox', 'PasswordSafe (wxWidgets)')."""
    cls = window.get_class_group_name() or window.get_class_instance_name() or ""
    title = window.get_name() or ""
    return cls, title


def consider(engine: "Engine", window) -> None:
    """Run a single window through the place-once core."""
    cls, title = window_props(window)
    engine.place(window.get_xid(), cls, title, window)


def connect_signals(screen, engine: "Engine") -> None:
    """Wire window-opened / name-changed / window-closed onto the engine.

    name-changed is the whole point: it fires when an extension rewrites a
    title after creation (Simple Tab Groups prepending a group prefix), which
    is the event devilspie2 cannot react to.
    """
    def on_name_changed(window):
        consider(engine, window)

    def on_window_opened(_screen, window):
        log.debug("window-opened: %s", window_props(window))
        consider(engine, window)
        window.connect("name-changed", on_name_changed)

    def on_window_closed(_screen, window):
        engine.forget(window.get_xid())

    screen.connect("window-opened", on_window_opened)
    screen.connect("window-closed", on_window_closed)

    # Already-open windows: place once now and watch for later title changes.
    for window in screen.get_windows():
        consider(engine, window)
        window.connect("name-changed", on_name_changed)
