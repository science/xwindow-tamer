"""Unit tests for rules.load_rules + match_rule (pure -- no X server needed)."""
import textwrap

import pytest

from window_tamer.rules import load_rules, match_rule

# Canonical rule set (mirrors config/rules.yaml). workspace is 1-based in config.
RULES_YAML = textwrap.dedent(
    """
    rules:
      - name: firefox-calendar
        match: { class: Firefox, title: '^Calendar -' }
        place: { monitor: DP-1, maximize: true }

      - name: firefox-mail
        match: { class: Firefox, title: '^Mail -' }
        place: { monitor: DP-4, maximize: true }

      - name: firefox-th
        match: { class: Firefox, title: '^Th -' }
        place: { monitor: DP-4, maximize: true, minimize: true }

      - name: firefox-rpg
        match: { class: Firefox, title: '^RPG' }
        place: { workspace: 2 }

      - name: passwordsafe
        match: { class: PasswordSafe }
        place: { monitor: DP-4, geometry: { width: 1025, height: 750, center: true } }
    """
)


@pytest.fixture
def rules(tmp_path):
    p = tmp_path / "rules.yaml"
    p.write_text(RULES_YAML)
    return load_rules(str(p))


def test_load_rules_returns_all_in_order(rules):
    assert [r.name for r in rules] == [
        "firefox-calendar",
        "firefox-mail",
        "firefox-th",
        "firefox-rpg",
        "passwordsafe",
    ]


def test_workspace_converted_to_zero_based(rules):
    rpg = next(r for r in rules if r.name == "firefox-rpg")
    assert rpg.place.workspace == 1  # config said 2 (1-based)


def test_place_flags_parsed(rules):
    th = next(r for r in rules if r.name == "firefox-th")
    assert th.place.monitor == "DP-4"
    assert th.place.maximize is True
    assert th.place.minimize is True
    assert th.place.workspace is None


def test_geometry_parsed(rules):
    pw = next(r for r in rules if r.name == "passwordsafe")
    assert pw.place.geometry is not None
    assert (pw.place.geometry.width, pw.place.geometry.height) == (1025, 750)
    assert pw.place.geometry.center is True


def test_missing_place_flags_default_false(rules):
    cal = next(r for r in rules if r.name == "firefox-calendar")
    assert cal.place.maximize is True
    assert cal.place.minimize is False
    assert cal.place.geometry is None


def test_match_each_firefox_title(rules):
    assert match_rule(rules, "Firefox", "Calendar - Steve").name == "firefox-calendar"
    assert match_rule(rules, "Firefox", "Mail - Inbox").name == "firefox-mail"
    assert match_rule(rules, "Firefox", "Th - notes").name == "firefox-th"
    assert match_rule(rules, "Firefox", "RPG campaign").name == "firefox-rpg"


def test_match_passwordsafe_by_class(rules):
    r = match_rule(rules, "PasswordSafe (wxWidgets)", "anything")
    assert r.name == "passwordsafe"


def test_class_match_is_case_insensitive(rules):
    assert match_rule(rules, "firefox", "Calendar - x").name == "firefox-calendar"


def test_no_match_returns_none(rules):
    assert match_rule(rules, "Firefox", "Mozilla Firefox") is None
    assert match_rule(rules, "Gimp", "image.png") is None


def test_first_match_wins(rules):
    # Calendar title also is Firefox; mail rule comes later and must not steal it.
    assert match_rule(rules, "Firefox", "Calendar - Mail - tricky").name == "firefox-calendar"
