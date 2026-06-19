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
