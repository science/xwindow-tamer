"""Rule loading + matching (pure -- no X server needed).

A rule matches a window by its Wnck class (regex, IGNORECASE) and/or title
(regex). A missing match key is a wildcard. Rules are tried top-to-bottom and
the first match wins. `workspace` is 1-based in config and stored 0-based here.
"""
import re
from dataclasses import dataclass
from typing import Optional, Pattern

import yaml


@dataclass
class Geometry:
    width: int
    height: int
    center: bool = False


@dataclass
class Place:
    monitor: Optional[str] = None
    maximize: bool = False
    minimize: bool = False
    workspace: Optional[int] = None  # 0-based
    geometry: Optional[Geometry] = None


@dataclass
class Rule:
    name: str
    class_re: Optional[Pattern]
    title_re: Optional[Pattern]
    place: Place


def _compile(pattern: Optional[str], flags: int = 0) -> Optional[Pattern]:
    return re.compile(pattern, flags) if pattern is not None else None


def _parse_place(raw: dict) -> Place:
    geo_raw = raw.get("geometry")
    geometry = (
        Geometry(
            width=geo_raw["width"],
            height=geo_raw["height"],
            center=bool(geo_raw.get("center", False)),
        )
        if geo_raw is not None
        else None
    )
    ws = raw.get("workspace")
    return Place(
        monitor=raw.get("monitor"),
        maximize=bool(raw.get("maximize", False)),
        minimize=bool(raw.get("minimize", False)),
        workspace=(ws - 1) if ws is not None else None,
        geometry=geometry,
    )


def load_rules(path: str) -> list[Rule]:
    """Load and compile rules from a YAML file into a list of Rule objects."""
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    rules: list[Rule] = []
    for raw in data.get("rules", []):
        match = raw.get("match", {})
        rules.append(
            Rule(
                name=raw["name"],
                class_re=_compile(match.get("class"), re.IGNORECASE),
                title_re=_compile(match.get("title")),
                place=_parse_place(raw.get("place", {})),
            )
        )
    return rules


def match_rule(rules: list[Rule], cls: str, title: str) -> Optional[Rule]:
    """Return the first rule whose class/title patterns match, or None."""
    for rule in rules:
        if rule.class_re is not None and not rule.class_re.search(cls):
            continue
        if rule.title_re is not None and not rule.title_re.search(title):
            continue
        return rule
    return None
