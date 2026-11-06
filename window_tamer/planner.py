"""Turn a matched Rule + monitor layout into an ordered list of Actions (pure).

Actions are the plan vocabulary the executor knows how to run:
  Unmaximize()              -- clear maximized state (move is a no-op while maxed)
  Move(x, y, width, height) -- absolute geometry
  Maximize(monitor_name)    -- maximize on the monitor the window now occupies
  Minimize()                -- stash (stays raisable from the taskbar)
  Workspace(index)          -- move to 0-based workspace index
"""
import logging
from dataclasses import dataclass
from typing import Optional

from .monitors import Monitor
from .rules import Rule

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Unmaximize:
    pass


@dataclass(frozen=True)
class Move:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class Maximize:
    monitor_name: str


@dataclass(frozen=True)
class Minimize:
    pass


@dataclass(frozen=True)
class Workspace:
    index: int


def _centered(mon: Monitor, width: int, height: int) -> Move:
    """A Move that centers a width x height box within `mon`."""
    return Move(
        mon.x + (mon.width - width) // 2,
        mon.y + (mon.height - height) // 2,
        width,
        height,
    )


def _resolve_monitor(name: str, monitors: dict[str, Monitor]) -> Optional[Monitor]:
    """The named monitor, or a fallback when it is absent (switched off, unplugged,
    not enumerated): the primary, else the leftmost. None if there are no monitors."""
    if name in monitors:
        return monitors[name]
    if not monitors:
        log.warning("monitor %s not present and no monitors known; skipping move", name)
        return None
    primary = [m for m in monitors.values() if m.primary]
    fallback = primary[0] if primary else min(monitors.values(), key=lambda m: m.x)
    log.warning("monitor %s not present; falling back to %s", name, fallback.name)
    return fallback


def plan(rule: Rule, monitors: dict[str, Monitor]) -> list:
    """Build the ordered action list for placing a window per `rule`."""
    place = rule.place
    actions: list = []

    if place.workspace is not None:
        actions.append(Workspace(place.workspace))

    mon = _resolve_monitor(place.monitor, monitors) if place.monitor is not None else None
    if mon is not None:
        actions.append(Unmaximize())
        if place.geometry is not None:
            g = place.geometry
            if g.center:
                actions.append(_centered(mon, g.width, g.height))
            else:
                actions.append(Move(mon.x, mon.y, g.width, g.height))
        else:
            # A centered half-monitor "landing box" -- NOT a full-monitor box.
            # muffin won't reposition a full-monitor-WIDTH window onto the center
            # monitor (it snaps to an edge), so we land a smaller box squarely
            # inside the target monitor; maximize() then resizes to the work area.
            actions.append(_centered(mon, mon.width // 2, mon.height // 2))
            if place.maximize:
                actions.append(Maximize(mon.name))

    if place.minimize:
        actions.append(Minimize())

    return actions
