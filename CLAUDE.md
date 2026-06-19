# CLAUDE.md

Guidance for Claude Code when working in this repository.

**Build roadmap & current status: see [PLAN.md](PLAN.md)** — self-contained, the
place to resume a cold session.

## Project Overview

`xwindow-tamer` is an event-driven daemon that places X11 windows onto the right
monitor / workspace according to declarative rules, the instant a window matches
— **including the moment an extension rewrites a window title *after* creation**
(e.g. Simple Tab Groups prepending `Calendar - `). That title-change event is
exactly what `devilspie2` v0.42 cannot react to, which is why this project
exists. It replaces our devilspie2 setup (the Firefox placement script, the
PasswordSafe script, and the cinnamon-restart re-placement watcher).

It uses **libwnck via GObject introspection** (`gi`) for both events
(`window-opened`, `name-changed`, `window-closed`) and window control
(`set_geometry`, `maximize`, `minimize`, `move_to_workspace`). It is therefore
**X11-only and permanently so** — libwnck does not exist on Wayland, and
Wayland's security model forbids this whole external-control pattern.

## Runtime constraint (important)

The daemon MUST run on the system `/usr/bin/python3`. The `gi`/Wnck bindings come
from apt (`python3-gi`, `gir1.2-wnck-3.0`), not pip — a venv without
`--system-site-packages` cannot import Wnck. `scripts/test.sh` hardcodes
`/usr/bin/python3` for the same reason.

## Project Structure

```
window_tamer/
  monitors.py   # parse `xrandr --listmonitors` -> Monitor objects        (pure)
  rules.py      # load rules.yaml + match (class/title) -> Rule            (pure)
  planner.py    # plan(rule, monitors) -> ordered [Action]                 (pure)
  executor.py   # apply [Action] to a Wnck window via non-blocking sequencer (X)
  engine.py     # Wnck event wiring + place-once dedup                     (X)
  __main__.py   # entrypoint: args (--dry-run/--once), logging, run loop
config/rules.yaml
systemd/xwindow-tamer.service
scripts/test.sh
tests/
```

**Design seam:** *decisions* are pure and unit-tested (`monitors`, `rules`,
`planner`, and the sequencer's control flow); *X11 effects* are thin and verified
by smoke/UAT. Keep new logic on the pure side of that seam wherever possible.

## Development Methodology: TDD Red/Green

**All new functionality MUST follow Test-Driven Development using red/green.**
Work in small increments — never write large amounts of implementation code
without corresponding tests.

1. **RED**: Write a small failing test for the next behavior. Run it to **prove
   it fails**. If it passes immediately, the test is wrong or the behavior
   already exists.
2. **GREEN**: Write the minimal code to pass. Run it to **prove it passes**. Add
   nothing beyond what the test requires.
3. **REFACTOR**: Clean up while keeping tests green.
4. **REPEAT**: Add the next small test.

### Key principles
- **Never skip RED** — running before implementing proves the test can fail.
- **Small increments** — one behavior per test.
- **Tests are documentation** — they show exactly what the code should do.
- **Diagnostic logging is temporary** — remove debug prints after the bug is fixed.

### Debugging failures
Add diagnostic logging, write a minimal *proving* test that reproduces the bug
(run it to confirm it fails), find the root cause, fix, then run the proving test
plus the full suite to confirm no regressions. The proving test stays as
regression coverage.

## Running Tests

```bash
./scripts/test.sh            # unit tests (pytest, no X needed) [default]
./scripts/test.sh status     # check runtime + test prerequisites
./scripts/test.sh smoke      # dry-run against live windows (needs X; moves nothing)
./scripts/test.sh all        # status + unit
# pass-through args: ./scripts/test.sh unit -k monitors -x
```

## Verification & Testing Plan

- **Layer 1 — Unit (pure, no X):** monitors parsing, rule load+match, planner
  action lists + coordinates, sequencer control flow, engine place-once dedup.
- **Layer 2 — Smoke (live X):** `--dry-run` logs the plan it *would* run for each
  current window without moving anything.
- **Layer 3 — UAT (human):** run live alongside devilspie2 (with its Firefox
  `.lua` disabled), cold-restart Firefox, and walk the acceptance checklist
  (correct monitors/workspace, Th raisable from taskbar, non-group windows never
  block, placed-once / no jumping, mid-session opens, survives reboot once the
  systemd unit is enabled).

## Git Workflow
- Develop on `main`. This is a personal tool; keep history clean and commits
  small (ideally one per green TDD step or logical group).
