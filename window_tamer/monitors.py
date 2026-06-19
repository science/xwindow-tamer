"""Monitor geometry from `xrandr --listmonitors`.

We parse xrandr rather than Gdk because this binding's Gdk.Monitor lacks
get_connector(), and rules reference monitors by connector name (DP-1/DP-4/DP-3).
"""
import re
import subprocess
from dataclasses import dataclass

# Matches e.g. " 0: +*DP-4 1920/527x1080/296+1920+0  DP-4"
#   group star = "*" if primary; name = connector; w/h = pixels; x/y = origin.
_LINE = re.compile(
    r"^\s*\d+:\s+\+(?P<star>\*?)(?P<name>\S+)\s+"
    r"(?P<w>\d+)/\d+x(?P<h>\d+)/\d+\+(?P<x>-?\d+)\+(?P<y>-?\d+)"
)


@dataclass
class Monitor:
    name: str
    x: int
    y: int
    width: int
    height: int
    primary: bool = False

    def contains_x(self, wx: int) -> bool:
        """True if absolute x-coordinate `wx` falls on this monitor (half-open)."""
        return self.x <= wx < self.x + self.width


def parse_listmonitors(text: str) -> dict[str, Monitor]:
    """Parse `xrandr --listmonitors` output into {connector_name: Monitor}."""
    monitors: dict[str, Monitor] = {}
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        monitors[m["name"]] = Monitor(
            name=m["name"],
            x=int(m["x"]),
            y=int(m["y"]),
            width=int(m["w"]),
            height=int(m["h"]),
            primary=bool(m["star"]),
        )
    return monitors


def load_monitors() -> dict[str, Monitor]:
    """Run xrandr and parse the current monitor layout."""
    out = subprocess.run(
        ["xrandr", "--listmonitors"], capture_output=True, text=True, check=True
    ).stdout
    return parse_listmonitors(out)
