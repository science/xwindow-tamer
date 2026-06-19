"""Unit tests for monitors.parse_listmonitors (pure -- no X server needed)."""
from window_tamer.monitors import parse_listmonitors

# Real output from `xrandr --listmonitors` on linux-bambam:
#   DP-1 left (x=0), DP-4 center/primary (x=1920), DP-3 right (x=3840); all 1920 wide.
SAMPLE = """Monitors: 3
 0: +*DP-4 1920/527x1080/296+1920+0  DP-4
 1: +DP-1 1920/527x1080/296+0+0  DP-1
 2: +DP-3 1920/527x1080/296+3840+0  DP-3
"""


def test_parses_all_three_monitors_by_connector_name():
    mons = parse_listmonitors(SAMPLE)
    assert set(mons) == {"DP-1", "DP-4", "DP-3"}


def test_monitor_origin_and_width():
    mons = parse_listmonitors(SAMPLE)
    assert (mons["DP-1"].x, mons["DP-1"].width) == (0, 1920)
    assert (mons["DP-4"].x, mons["DP-4"].width) == (1920, 1920)
    assert (mons["DP-3"].x, mons["DP-3"].width) == (3840, 1920)


def test_height_and_y_origin():
    m = parse_listmonitors(SAMPLE)["DP-4"]
    assert (m.y, m.height) == (0, 1080)


def test_primary_flag_from_asterisk():
    mons = parse_listmonitors(SAMPLE)
    assert mons["DP-4"].primary is True
    assert mons["DP-1"].primary is False
    assert mons["DP-3"].primary is False


def test_contains_x_is_half_open_interval():
    mons = parse_listmonitors(SAMPLE)
    assert mons["DP-1"].contains_x(0)
    assert mons["DP-1"].contains_x(1919)
    assert not mons["DP-1"].contains_x(1920)   # belongs to DP-4
    assert mons["DP-4"].contains_x(1920)
    assert mons["DP-3"].contains_x(3840)


def test_ignores_header_and_blank_lines():
    assert parse_listmonitors("Monitors: 0\n\n") == {}
