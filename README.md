# xwindow-tamer

An event-driven daemon that places X11 windows onto the right monitor and
workspace the instant they match a declarative rule — **including the moment a
browser extension rewrites a window title *after* the window was created.**

It uses [libwnck](https://gitlab.gnome.org/GNOME/libwnck) via GObject
introspection (`gi`) for both window events (`window-opened`, `name-changed`,
`window-closed`) and window control (`set_geometry`, `maximize`, `minimize`,
`move_to_workspace`). It is therefore **X11-only, permanently** — libwnck does
not exist on Wayland, and Wayland's security model forbids this whole
external-control pattern. Hence the `x` in the name.

## What it does

You write rules in `config/rules.yaml`:

```yaml
rules:
  - name: firefox-calendar
    match: { class: Firefox, title: '^Calendar -' }
    place: { monitor: DP-1, maximize: true }

  - name: firefox-mail
    match: { class: Firefox, title: '^Mail -' }
    place: { monitor: DP-4, maximize: true }

  - name: firefox-th            # stash under Mail; minimize keeps it raisable
    match: { class: Firefox, title: '^Th -' }
    place: { monitor: DP-4, maximize: true, minimize: true }

  - name: firefox-rpg
    match: { class: Firefox, title: '^RPG' }
    place: { workspace: 2 }

  - name: passwordsafe
    match: { class: PasswordSafe }
    place: { monitor: DP-4, geometry: { width: 1025, height: 750, center: true } }
```

Rules are matched top-to-bottom, first match wins. `class` is a case-insensitive
regex over the window's WM class; `title` is a regex over the window name; a
missing match key is a wildcard. A matched window is placed **exactly once** — if
you move it by hand afterwards, the daemon leaves it alone — and a closed window
is forgotten so a reopen is placed again.

```bash
python3 -m window_tamer                 # daemon: place windows as they match
python3 -m window_tamer --dry-run       # log the plan for each match, move nothing
python3 -m window_tamer --once          # place current windows once, then exit
python3 -m window_tamer --dry-run --once  # "smoke": log plans for current windows
```

## Why not just use devilspie2?

This project exists because of one specific thing `devilspie2` v0.42 cannot do.

Some browser extensions (e.g. [Simple Tab
Groups](https://github.com/Drive4ik/simple-tab-groups)) prepend a group name to
the window title **after** the window is created — `Inbox …` becomes
`Mail - Inbox …` a few seconds later, sometimes up to ~60s on a cold browser
start. We want the window placed based on that final, prefixed title.

- **devilspie2 fires rules only on window-*create*, never on title-*change*.**
  At create time the prefix isn't there yet, so the rule doesn't match, and dp2
  never looks again.
- **Working around it by polling the title inside a dp2 script is fatal**, because
  **dp2 is single-threaded.** Each *non-group* window (a blank `Mozilla Firefox`
  window, a Drive doc) that never gains a prefix freezes the entire daemon for the
  whole poll budget. In practice two such windows each block for ~60s, placement
  serializes over 2+ minutes, windows "jump" in one at a time, and a window that
  needs a different monitor gets starved entirely. No poll budget wins: short
  abandons slow-prefixed windows, long freezes dp2 on non-group ones.

The fix is to be **event-driven**: react to libwnck's `name-changed` signal — the
event dp2 lacks — with in-process state so each window is placed exactly once and
non-matching windows cost nothing. libwnck's control API is reachable from Python
via `gi`, so this is a small daemon rather than a fork of dp2's C.

## Hard-won gotchas (baked into the code)

These cost real debugging time and are encoded as behavior + tests:

1. **`set_geometry` is a no-op on a maximized window, and `unmaximize()` is
   async.** Unmaximize first, then wait until `is_maximized()` is false before
   moving.
2. **A full-monitor-width window can't be repositioned onto a non-edge monitor** —
   the window manager (muffin/Cinnamon) snaps it to a screen edge, so
   `set_geometry(x=center_monitor)` is silently ignored. We move a smaller
   *centered landing box* onto the target monitor, then `maximize()` (which
   resizes to the panel-adjusted work area for us).
3. **`maximize()` maximizes onto whichever monitor the window currently
   occupies.** Confirm the window is on the target monitor before maximizing, and
   re-heal if it lands wrong.
4. **Never stack a window with `_NET_WM_STATE_BELOW`** — it becomes un-raisable
   from the taskbar. To stash a window under another, `minimize()` it (a taskbar
   click then restores it maximized and on top).
5. **Never block the GLib main loop.** The executor sequences async steps via
   `GLib.timeout_add`, never `sleep` — blocking the loop is the exact dp2 failure.

## Architecture

The design separates pure *decisions* (unit-tested, no X needed) from thin X11
*effects* (verified by smoke/UAT):

```
window_tamer/
  monitors.py   parse `xrandr --listmonitors` -> Monitor objects        (pure)
  rules.py      load rules.yaml + match (class/title) -> Rule            (pure)
  planner.py    plan(rule, monitors) -> ordered [Action]                 (pure)
  executor.py   run_sequence (pure control flow) + Wnck step builders     (X)
  engine.py     place-once dedup (pure) + Wnck signal wiring              (X)
  __main__.py   args, logging, Gtk/Wnck init, run loop
config/rules.yaml
systemd/xwindow-tamer.service
```

## Running it

The daemon **must** run on the system `/usr/bin/python3`: the `gi`/Wnck bindings
come from your distro packages (`python3-gi`, `gir1.2-wnck-3.0`, `python3-yaml`),
not pip — a virtualenv without `--system-site-packages` cannot import Wnck.

```bash
./scripts/test.sh status   # verify prerequisites (gi/Wnck, yaml, pytest, xrandr)
./scripts/test.sh          # run the unit suite (pure, no X needed)
./scripts/test.sh smoke    # dry-run against live windows (needs X; moves nothing)
```

To run it at login, use the installer:

```bash
./install.sh      # generate + enable the systemd user service, symlink the CLI
./uninstall.sh    # remove the service and symlink (repo left in place)
```

`install.sh` writes `~/.config/systemd/user/xwindow-tamer.service` whose
`ExecStart` points back at `bin/xwindow-tamer` **in this repo**, and symlinks
`~/.local/bin/xwindow-tamer` to the same launcher — so editing the repo *is* the
deploy, with no copy step to drift out of sync. The launcher always runs on
`/usr/bin/python3` (the interpreter with the apt gi/Wnck bindings).

> The unit uses `WantedBy=default.target`, not `graphical-session.target` —
> Cinnamon does not activate the latter. `Restart=on-failure` with
> `StartLimitIntervalSec=0` keeps retrying if the service starts before X is
> reachable at login.

On this author's machine the install is driven automatically by `yadm
bootstrap`, which clones this repo into `~/dev/xwindow-tamer` and runs
`install.sh`.

## License

Apache License 2.0. Copyright 2026 Stephen Midgley. See [LICENSE](LICENSE).
