"""Non-blocking action sequencer.

The control flow here is PURE and unit-tested with an injected scheduler. The
Wnck step builders (which produce the actual `step()` callables that touch X)
live alongside it but are exercised only by smoke/UAT.

NEVER block the GLib main loop -- that is the exact devilspie2 failure mode. We
drive one step at a time on a timer: each step returns True to advance, False to
retry. Retries are capped; on exhaustion we advance anyway so one stuck step
cannot wedge the whole sequence. `on_done` fires exactly once at the end.

The scheduler contract matches GLib.timeout_add(interval_ms, fn): fn is called
repeatedly every interval and returns True to keep being called, False to stop.
"""
from typing import Callable, Optional, Sequence

from .monitors import Monitor
from .planner import Maximize, Minimize, Move, Unmaximize, Workspace

# A step touches X and reports whether it succeeded (advance) or should retry.
Step = Callable[[], bool]
# schedule(interval_ms, tick): register tick to be called per GLib semantics.
Scheduler = Callable[[int, Callable[[], bool]], None]

DEFAULT_INTERVAL_MS = 100
DEFAULT_MAX_RETRIES = 10


def run_sequence(
    steps: Sequence[Step],
    schedule: Scheduler,
    on_done: Optional[Callable[[], None]] = None,
    interval_ms: int = DEFAULT_INTERVAL_MS,
    max_retries: int = DEFAULT_MAX_RETRIES,
) -> None:
    """Drive `steps` to completion via `schedule`, firing `on_done` once."""
    state = {"i": 0, "retries": 0, "done": False}

    def finish() -> bool:
        if not state["done"]:
            state["done"] = True
            if on_done is not None:
                on_done()
        return False  # stop the timer

    def tick() -> bool:
        if state["i"] >= len(steps):
            return finish()

        if steps[state["i"]]():
            state["i"] += 1
            state["retries"] = 0
        else:
            state["retries"] += 1
            if state["retries"] > max_retries:
                state["i"] += 1
                state["retries"] = 0

        if state["i"] >= len(steps):
            return finish()
        return True  # keep ticking

    schedule(interval_ms, tick)


# --------------------------------------------------------------------------
# Wnck step builders (X effects -- verified by smoke/UAT, not unit tests).
# gi is imported lazily so the pure run_sequence above stays importable on a
# box with no X / no Wnck. Each builder returns a step() honoring the gotchas:
#   - set_geometry is a no-op while maximized; unmaximize first and wait.
#   - maximize lands on whichever monitor the window currently occupies, so
#     confirm we're on the target monitor first and re-heal if it lands wrong.
# --------------------------------------------------------------------------


def _monitor_for_x(monitors: dict[str, Monitor], x: int) -> Optional[Monitor]:
    for mon in monitors.values():
        if mon.contains_x(x):
            return mon
    return None


def _unmaximize_step(window) -> Step:
    def step() -> bool:
        if not window.is_maximized():
            return True
        window.unmaximize()  # async; verify cleared on a later tick
        return False
    return step


def _move_step(window, move: Move, gravity, mask, monitors) -> Step:
    target = _monitor_for_x(monitors, move.x)

    def step() -> bool:
        window.set_geometry(gravity, mask, move.x, move.y, move.width, move.height)
        x = window.get_geometry()[0]
        return target.contains_x(x) if target is not None else True
    return step


def _maximize_step(window, mon: Monitor, gravity, mask) -> Step:
    full = (mon.x, mon.y, mon.width, mon.height)

    def step() -> bool:
        x = window.get_geometry()[0]
        on_target = mon.contains_x(x)
        if window.is_maximized():
            if on_target:
                return True
            window.unmaximize()  # maximized on the wrong monitor -> clear & re-place
            return False
        if not on_target:
            window.set_geometry(gravity, mask, *full)
            return False
        window.maximize()  # async; verify on a later tick
        return False
    return step


def _minimize_step(window) -> Step:
    def step() -> bool:
        window.minimize()
        return True
    return step


def _workspace_step(window, ws: Workspace, screen) -> Step:
    def step() -> bool:
        space = screen.get_workspace(ws.index)
        if space is not None:
            window.move_to_workspace(space)
        return True
    return step


def build_steps(window, actions, monitors: dict[str, Monitor], screen) -> list:
    """Translate an action list into Wnck step callables for run_sequence."""
    import gi

    gi.require_version("Wnck", "3.0")
    from gi.repository import Wnck

    gravity = Wnck.WindowGravity.CURRENT
    m = Wnck.WindowMoveResizeMask
    mask = m.X | m.Y | m.WIDTH | m.HEIGHT

    steps: list = []
    for a in actions:
        if isinstance(a, Unmaximize):
            steps.append(_unmaximize_step(window))
        elif isinstance(a, Move):
            steps.append(_move_step(window, a, gravity, mask, monitors))
        elif isinstance(a, Maximize):
            steps.append(_maximize_step(window, monitors[a.monitor_name], gravity, mask))
        elif isinstance(a, Minimize):
            steps.append(_minimize_step(window))
        elif isinstance(a, Workspace):
            steps.append(_workspace_step(window, a, screen))
    return steps


def apply_actions(window, actions, monitors: dict[str, Monitor], screen, on_done=None) -> None:
    """Production execute(): build Wnck steps and run them on the GLib loop."""
    import gi

    gi.require_version("GLib", "2.0")
    from gi.repository import GLib

    steps = build_steps(window, actions, monitors, screen)
    run_sequence(steps, schedule=GLib.timeout_add, on_done=on_done)
