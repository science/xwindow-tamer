"""Unit tests for engine place-once dedup (pure -- no X server needed).

The Engine's decision core is exercised with an injected `execute` callback so
no Wnck window is required. We assert: a matched window is placed exactly once,
a non-matching window costs nothing and stays eligible (so a later title change
places it), and window-closed forgets the xid so a reopen re-places.
"""
from window_tamer.engine import Engine
from window_tamer.monitors import parse_listmonitors
from window_tamer.rules import Place, Rule

MONS = parse_listmonitors(
    """Monitors: 3
 0: +*DP-4 1920/527x1080/296+1920+0  DP-4
 1: +DP-1 1920/527x1080/296+0+0  DP-1
 2: +DP-3 1920/527x1080/296+3840+0  DP-3
"""
)


def _rules():
    import re

    return [
        Rule(
            name="mail",
            class_re=re.compile("Firefox", re.IGNORECASE),
            title_re=re.compile("^Mail -"),
            place=Place(monitor="DP-4", maximize=True),
        )
    ]


def _engine():
    calls = []
    eng = Engine(_rules(), MONS, execute=lambda target, actions: calls.append((target, actions)))
    return eng, calls


def test_matching_window_is_placed_once():
    eng, calls = _engine()
    eng.place(xid=1, cls="Firefox", title="Mail - Inbox", target="win1")
    assert len(calls) == 1
    assert calls[0][0] == "win1"


def test_second_event_for_placed_xid_is_noop():
    eng, calls = _engine()
    eng.place(xid=1, cls="Firefox", title="Mail - Inbox", target="win1")
    eng.place(xid=1, cls="Firefox", title="Mail - Inbox (2 unread)", target="win1")
    assert len(calls) == 1


def test_non_matching_window_is_not_placed_and_stays_eligible():
    eng, calls = _engine()
    # Window opens with no STG prefix yet -> no match, no placement.
    eng.place(xid=2, cls="Firefox", title="Mozilla Firefox", target="win2")
    assert calls == []
    # Title later gains the prefix -> now it matches and places.
    eng.place(xid=2, cls="Firefox", title="Mail - Inbox", target="win2")
    assert len(calls) == 1


def test_window_closed_forgets_xid_so_reopen_replaces():
    eng, calls = _engine()
    eng.place(xid=3, cls="Firefox", title="Mail - Inbox", target="win3")
    assert len(calls) == 1
    eng.forget(xid=3)
    eng.place(xid=3, cls="Firefox", title="Mail - Inbox", target="win3")
    assert len(calls) == 2


def test_dry_run_computes_but_does_not_execute():
    calls = []
    eng = Engine(
        _rules(),
        MONS,
        execute=lambda target, actions: calls.append(1),
        dry_run=True,
    )
    rule = eng.place(xid=4, cls="Firefox", title="Mail - Inbox", target="win4")
    assert calls == []          # nothing executed
    assert rule is not None      # but a decision was made (for logging)
    # still deduped: a second event is a no-op
    assert eng.place(xid=4, cls="Firefox", title="Mail - Inbox", target="win4") is None


# --- monitor refresh ----------------------------------------------------------
# The layout is re-read on every matched placement so a monitor that disappears
# after startup is not targeted from a stale snapshot.


def test_matched_placement_uses_refreshed_monitors():
    only_dp1 = parse_listmonitors(
        """Monitors: 1
 0: +*DP-1 1920/527x1080/296+0+0  DP-1
"""
    )
    calls = []
    eng = Engine(
        _rules(), MONS,
        execute=lambda target, actions: calls.append(actions),
        refresh_monitors=lambda: only_dp1,
    )
    eng.place(xid=1, cls="Firefox", title="Mail - Inbox", target="w")
    # DP-4 is gone -> falls back to DP-1 (the refreshed primary).
    assert calls[0][-1].monitor_name == "DP-1"
    assert eng.monitors is only_dp1


def test_refresh_failure_keeps_previous_monitors():
    def boom():
        raise RuntimeError("xrandr failed")

    calls = []
    eng = Engine(
        _rules(), MONS,
        execute=lambda target, actions: calls.append(actions),
        refresh_monitors=boom,
    )
    eng.place(xid=1, cls="Firefox", title="Mail - Inbox", target="w")
    assert calls[0][-1].monitor_name == "DP-4"
    assert eng.monitors is MONS


def test_non_matching_window_does_not_refresh():
    n = []
    eng = Engine(
        _rules(), MONS, execute=lambda t, a: None,
        refresh_monitors=lambda: n.append(1) or MONS,
    )
    eng.place(xid=1, cls="Firefox", title="Some page", target="w")
    assert n == []
