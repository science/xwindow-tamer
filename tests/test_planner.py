"""Unit tests for planner.plan (pure -- no X server needed)."""
from window_tamer.monitors import parse_listmonitors
from window_tamer.planner import (
    Maximize,
    Minimize,
    Move,
    Unmaximize,
    Workspace,
    plan,
)
from window_tamer.rules import Geometry, Place, Rule

# Same layout as tests/test_monitors.py: DP-1 @0, DP-4 @1920 (primary), DP-3 @3840.
MONS = parse_listmonitors(
    """Monitors: 3
 0: +*DP-4 1920/527x1080/296+1920+0  DP-4
 1: +DP-1 1920/527x1080/296+0+0  DP-1
 2: +DP-3 1920/527x1080/296+3840+0  DP-3
"""
)


def _rule(place):
    return Rule(name="t", class_re=None, title_re=None, place=place)


# The maximize-path Move is a sub-monitor "landing box" (centered half-monitor),
# NOT a full-monitor box: muffin refuses to reposition a full-monitor-WIDTH
# window onto the center monitor (it snaps to x=0 or the far edge). Maximize then
# resizes to the work area, so the landing box size is irrelevant -- it only has
# to put the window unambiguously inside the target monitor. (UAT-discovered.)
# DP-1: 960x540 centered -> (480, 270); DP-4: -> (2400, 270).


def test_calendar_maximize_on_left():
    r = _rule(Place(monitor="DP-1", maximize=True))
    assert plan(r, MONS) == [Unmaximize(), Move(480, 270, 960, 540), Maximize("DP-1")]


def test_mail_maximize_on_center():
    r = _rule(Place(monitor="DP-4", maximize=True))
    assert plan(r, MONS) == [Unmaximize(), Move(2400, 270, 960, 540), Maximize("DP-4")]


def test_th_maximize_then_minimize():
    r = _rule(Place(monitor="DP-4", maximize=True, minimize=True))
    assert plan(r, MONS) == [
        Unmaximize(),
        Move(2400, 270, 960, 540),
        Maximize("DP-4"),
        Minimize(),
    ]


def test_rpg_workspace_only():
    r = _rule(Place(workspace=1))
    assert plan(r, MONS) == [Workspace(1)]


def test_passwordsafe_centered_geometry_no_maximize():
    r = _rule(
        Place(monitor="DP-4", geometry=Geometry(width=1025, height=750, center=True))
    )
    # centered on DP-4: x = 1920 + (1920-1025)//2 = 2367; y = (1080-750)//2 = 165
    assert plan(r, MONS) == [Unmaximize(), Move(2367, 165, 1025, 750)]


def test_workspace_comes_before_monitor():
    r = _rule(Place(workspace=1, monitor="DP-1", maximize=True))
    assert plan(r, MONS) == [
        Workspace(1),
        Unmaximize(),
        Move(480, 270, 960, 540),
        Maximize("DP-1"),
    ]


def test_monitor_move_without_maximize():
    # No geometry, no maximize: still lands the window inside DP-3 via the
    # centered landing box. DP-3 @3840 -> (4320, 270, 960, 540).
    r = _rule(Place(monitor="DP-3"))
    assert plan(r, MONS) == [Unmaximize(), Move(4320, 270, 960, 540)]


# --- missing-monitor fallback -------------------------------------------------
# A rule's monitor can be absent (switched off, unplugged, or not enumerated at
# startup). Placement must degrade to a monitor that exists -- the primary, else
# the leftmost -- instead of raising KeyError and leaving the window unplaced.


def test_missing_monitor_falls_back_to_primary():
    # HDMI-0 is not in MONS; primary is DP-4 -> same box as the DP-4 case above.
    r = _rule(
        Place(monitor="HDMI-0", geometry=Geometry(width=1025, height=750, center=True))
    )
    assert plan(r, MONS) == [Unmaximize(), Move(2367, 165, 1025, 750)]


def test_missing_monitor_maximize_targets_fallback_name():
    r = _rule(Place(monitor="HDMI-0", maximize=True))
    assert plan(r, MONS) == [Unmaximize(), Move(2400, 270, 960, 540), Maximize("DP-4")]


def test_missing_monitor_without_primary_falls_back_to_leftmost():
    no_primary = parse_listmonitors(
        """Monitors: 2
 0: +DP-3 1920/527x1080/296+1920+0  DP-3
 1: +DP-1 1920/527x1080/296+0+0  DP-1
"""
    )
    r = _rule(Place(monitor="HDMI-0", maximize=True))
    assert plan(r, no_primary) == [Unmaximize(), Move(480, 270, 960, 540), Maximize("DP-1")]


def test_no_monitors_at_all_skips_monitor_actions():
    r = _rule(Place(workspace=1, monitor="HDMI-0", maximize=True))
    assert plan(r, {}) == [Workspace(1)]
