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
