"""xwindow-tamer: rule-based X11 window placement.

An event-driven daemon (libwnck via GObject introspection) that places windows
onto the right monitor/workspace as soon as they match a rule -- including the
moment an extension (e.g. Simple Tab Groups) rewrites a window title *after*
creation, which is exactly the event devilspie2 v0.42 cannot react to.
"""

__version__ = "0.1.0"
