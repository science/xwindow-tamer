"""Unit tests for executor.run_sequence control flow (pure -- no X server).

The sequencer drives steps via an injected scheduler. In production the
scheduler is GLib.timeout_add (calls the tick fn every interval, stopping when
it returns False). The test scheduler drains synchronously with the same
contract: keep calling tick while it returns True.
"""
from window_tamer.executor import run_sequence


def drain(interval_ms, tick):
    """Test scheduler mirroring GLib.timeout_add: tick until it returns False."""
    while tick():
        pass


def test_all_steps_succeed_run_in_order_once():
    calls = []
    steps = [lambda: (calls.append("a"), True)[1],
             lambda: (calls.append("b"), True)[1],
             lambda: (calls.append("c"), True)[1]]
    done = []
    run_sequence(steps, schedule=drain, on_done=lambda: done.append(1))
    assert calls == ["a", "b", "c"]
    assert done == [1]


def test_on_done_fires_exactly_once():
    done = []
    run_sequence([lambda: True], schedule=drain, on_done=lambda: done.append(1))
    assert done == [1]


def test_empty_sequence_still_fires_on_done():
    done = []
    run_sequence([], schedule=drain, on_done=lambda: done.append(1))
    assert done == [1]


def test_failing_step_retries_to_cap_then_advances():
    count = {"n": 0}

    def always_fail():
        count["n"] += 1
        return False

    advanced = []
    done = []
    run_sequence(
        [always_fail, lambda: (advanced.append(1), True)[1]],
        schedule=drain,
        on_done=lambda: done.append(1),
        max_retries=3,
    )
    # initial attempt + 3 retries = 4 calls, then give up and advance.
    assert count["n"] == 4
    assert advanced == [1]
    assert done == [1]


def test_step_that_eventually_succeeds_does_not_exhaust_retries():
    count = {"n": 0}

    def succeed_on_third():
        count["n"] += 1
        return count["n"] >= 3

    after = []
    run_sequence(
        [succeed_on_third, lambda: (after.append(1), True)[1]],
        schedule=drain,
        on_done=None,
        max_retries=10,
    )
    assert count["n"] == 3
    assert after == [1]


def test_retry_counter_resets_between_steps():
    # First step fails twice then succeeds; second step must get a fresh budget.
    c1 = {"n": 0}
    c2 = {"n": 0}

    def step1():
        c1["n"] += 1
        return c1["n"] >= 3

    def step2():
        c2["n"] += 1
        return c2["n"] >= 3

    run_sequence([step1, step2], schedule=drain, max_retries=5)
    assert c1["n"] == 3
    assert c2["n"] == 3
