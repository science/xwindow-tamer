"""Turn a matched Rule + monitor layout into an ordered list of Actions (pure).

Actions are the plan vocabulary the executor knows how to run:
  Unmaximize()              -- clear maximized state (move is a no-op while maxed)
  Move(x, y, width, height) -- absolute geometry
  Maximize(monitor_name)    -- maximize on the monitor the window now occupies
  Minimize()                -- stash (stays raisable from the taskbar)
  Workspace(index)          -- move to 0-based workspace index
"""
from dataclasses import dataclass

from .monitors import Monitor
from .rules import Rule


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


def plan(rule: Rule, monitors: dict[str, Monitor]) -> list:
    """Build the ordered action list for placing a window per `rule`."""
    place = rule.place
    actions: list = []

    if place.workspace is not None:
        actions.append(Workspace(place.workspace))

    if place.monitor is not None:
        mon = monitors[place.monitor]
        actions.append(Unmaximize())
        if place.geometry is not None:
            g = place.geometry
            if g.center:
                x = mon.x + (mon.width - g.width) // 2
                y = mon.y + (mon.height - g.height) // 2
            else:
                x, y = mon.x, mon.y
            actions.append(Move(x, y, g.width, g.height))
        else:
            actions.append(Move(mon.x, mon.y, mon.width, mon.height))
            if place.maximize:
                actions.append(Maximize(mon.name))

    if place.minimize:
        actions.append(Minimize())

    return actions
