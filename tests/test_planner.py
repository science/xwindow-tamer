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
