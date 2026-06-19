# xwindow-tamer — Build Plan & Handoff

Self-contained roadmap for building this project. Written so a fresh Claude
session (no prior conversation memory) can resume. Read `CLAUDE.md` first
(methodology + runtime constraints), then this.

## Resume in 30 seconds

```bash
cd ~/dev/xwindow-tamer
./scripts/test.sh status     # verify prerequisites (python3-gi/Wnck, yaml, pytest, xrandr)
./scripts/test.sh unit       # current suite should be GREEN
```

Then continue at the next unchecked TDD cycle under **Build Status** below,
following RED → GREEN → REFACTOR for each.

---

## 1. Why this exists (problem statement)

We need windows placed on specific monitors/workspaces by matching rules,
**including when an extension rewrites a window title *after* the window is
created** (Simple Tab Groups prepends a group name, e.g. `Inbox …` becomes
`Mail - Inbox …` a few seconds later — sometimes up to ~60s on a cold Firefox
boot).

`devilspie2` v0.42 cannot do this. The diagnosis (hard-won — do not relitigate):

- **dp2 fires rules only on window-*create*, never on title-*change*.** At create
  time the STG prefix isn't there yet, so the rule doesn't match.
- Working around it with an in-script **block-poll** for the title is fatal:
  **dp2 is single-threaded**, so each *non-group* Firefox window (e.g. a blank
  `Mozilla Firefox` window, or a Drive doc) freezes the whole daemon for the
  entire poll budget. Observed: two non-group windows each blocked 60s →
  placement serialized over 2+ minutes, windows "jumping" in one by one, and the
  cross-monitor window (Calendar) starved entirely. **No poll budget works**:
  short abandons slow-prefixed group windows; long freezes dp2 on non-group ones.

The fix is event-driven: react to libwnck's `name-changed` signal (the event dp2
lacks), with in-process state so each window is placed exactly once and
non-matching windows cost nothing. libwnck is reachable from Python via `gi`,
including the control API — so we build a small daemon rather than forking dp2's C.

**X11-only, permanently.** libwnck doesn't exist on Wayland and Wayland forbids
this external-control pattern. Hence the `x` in the name.

## 2. Hard-won gotchas (bake these into code + tests)

1. **`set_geometry`/move is a NO-OP on a maximized window, and `unmaximize()` is
   async.** Must `unmaximize()` then **wait until `is_maximized()` is False**
   before moving. (Symptom we hit: Mail stuck on the right monitor at x=3840
   through every retry.)
2. **`maximize()` maximizes onto whichever monitor the window currently
   occupies.** If the move hasn't landed yet, it maximizes on the *creation*
   monitor. So: confirm the window is on the target monitor (by x-range) *before*
   maximizing, and re-heal (re-move + re-maximize) if it lands wrong.
3. **Never use `set_window_below()` / EWMH `_NET_WM_STATE_BELOW` to stack a
   window.** It makes the window **un-raisable** — clicking its taskbar entry
   won't bring it forward (the focused window just loses focus). To stash Th
   under Mail, **`minimize()`** it (restores maximized + raisable on click).
4. **Wnck `get_geometry()` returns reliable absolute coords** (it agreed with
   on-screen reality at x=3840). **Do NOT trust `wmctrl -lG`** — it reported a
   bogus +1920 offset for centered windows. Use Wnck (or `xwininfo`) for coords.
5. **Firefox session-restore** places restored windows on arbitrary monitors and
   may briefly re-assert positions during a cold boot — so placement must be
   robust to a window starting on the "wrong" monitor and to brief contention.
6. **Cinnamon does NOT activate `graphical-session.target`.** User services must
   use `WantedBy=default.target` (the existing dp2 watcher does this). There's a
   `~/.xprofile` fallback pattern on this machine for session-start hooks.
7. Don't block the GLib loop. The executor sequences async steps via
   `GLib.timeout_add`, never `sleep`. (Blocking is the exact dp2 failure.)

## 3. Environment facts (linux-bambam, X11/Cinnamon)

Monitor layout (`xrandr --listmonitors`), all 1920 wide:

| Connector | Role   | x origin | Panel        | Maximizes to |
|-----------|--------|----------|--------------|--------------|
| DP-1      | left   | 0        | none         | 1920×1080    |
| DP-4      | center | 1920     | bottom panel | 1920×1020 (primary) |
| DP-3      | right  | 3840     | none         | 1920×1080    |

- Runtime interpreter: **`/usr/bin/python3`** (has apt `gi`/Wnck + pytest).
- `DISPLAY=:0`. Service runs on the **host** (where X is); code lives in
  bind-mounted `~/dev` but that's just the source.

## 4. Architecture (pure/effect seam)

```
window_tamer/
  monitors.py   parse_listmonitors(text) -> {name: Monitor}              PURE  [done]
  rules.py      load_rules(path) -> [Rule]; match_rule(rules, cls, title) PURE
  planner.py    plan(rule, monitors) -> [Action]                         PURE
  executor.py   run_sequence(steps, schedule, ...) + Wnck step builders   X (control-flow PURE)
  engine.py     Wnck window-opened/name-changed/closed + place-once       X (dedup PURE)
  __main__.py   args (--dry-run/--once), logging, Gtk.init + Gtk.main
```

**Action dataclasses** (the plan vocabulary):
`Unmaximize()`, `Move(x, y, width, height)`, `Maximize(monitor_name)`,
`Minimize()`, `Workspace(index)`  (index is 0-based).

**`plan(rule, monitors)` semantics** (ordered):
1. If `place.workspace` set → `Workspace(workspace_index)`.
2. If `place.monitor` set: `Unmaximize()`, then
   - if `place.geometry` → `Move(centered box within monitor)` (no maximize), else
   - `Move(mon.x, mon.y, mon.width, mon.height)`, then if `place.maximize` →
     `Maximize(mon.name)`.
3. If `place.minimize` → `Minimize()` (last).

(For the maximize path the Move just lands the window on the right monitor;
`maximize()` then clamps to the panel-adjusted work area, so we don't compute
1020 vs 1080 ourselves.)

**Executor sequencer** must be testable without X: `run_sequence` takes an
injected `schedule(interval_ms, fn)` (prod = `GLib.timeout_add`; test = a
synchronous driver). Each step returns `True` to advance, `False` to retry;
retries capped, then advance anyway; `on_done` fires once. This encodes
"unmaximize until cleared", "move until on target monitor", "maximize then verify
+ heal" without blocking.

**Engine place-once:** keep `placed: set[xid]`. On a matching `name-changed`/open,
if xid already placed → skip; else plan+execute and add. On `window-closed`,
discard xid (so a reopened window re-places). `--dry-run` logs the plan instead
of executing; `--once` enumerates current windows then exits.

## 5. Rules (config/rules.yaml)

Engine matches top-to-bottom, first match wins. `class` = regex (IGNORECASE) over
the Wnck class group/instance; `title` = regex over the window name; a missing
match key is a wildcard. `workspace` in config is 1-based (engine converts to
0-based).

```yaml
rules:
  - name: firefox-calendar
    match: { class: Firefox, title: '^Calendar -' }
    place: { monitor: DP-1, maximize: true }

  - name: firefox-mail
    match: { class: Firefox, title: '^Mail -' }
    place: { monitor: DP-4, maximize: true }

  - name: firefox-th            # stash under Mail on center; minimize keeps it raisable
    match: { class: Firefox, title: '^Th -' }
    place: { monitor: DP-4, maximize: true, minimize: true }

  - name: firefox-rpg
    match: { class: Firefox, title: '^RPG' }
    place: { workspace: 2 }

  - name: passwordsafe          # WM_CLASS "PasswordSafe (wxWidgets)"
    match: { class: PasswordSafe }
    place: { monitor: DP-4, geometry: { width: 1025, height: 750, center: true } }
```

## 6. TDD cycles (Layer 1 — pure, no X)

Each: write failing test → `./scripts/test.sh unit` (prove RED) → minimal impl →
prove GREEN → refactor. One behavior per test.

- [x] **C1 monitors** — `parse_listmonitors`: connectors, origin/width, height,
      primary flag, half-open `contains_x`, ignores header/blank lines. (6 tests GREEN)
- [x] **C2 rules** — `load_rules` (yaml → Rule; workspace 1→0; geometry parsed;
      patterns compiled) and `match_rule` (each FF title + pwsafe class → right
      rule; first-match-wins; no-match → None; wildcard on missing key;
      case-insensitive class).
- [x] **C3 planner** — `plan(rule, monitors)` exact action lists + coords for all
      five rules using the SAMPLE monitors (Calendar→`[Unmax, Move(0,0,1920,1080),
      Maximize(DP-1)]`; Th→`[Unmax, Move(1920,…), Maximize(DP-4), Minimize]`;
      RPG→`[Workspace(1)]`; pwsafe→`[Unmax, Move(centered 1025×750 on DP-4)]`).
- [x] **C4 executor sequencer** — control flow with a stub scheduler: advances on
      success, retries to cap then advances, preserves order, `on_done` once.
- [x] **C5 engine dedup** — place-once: second `name-changed` for a placed xid is
      a no-op; `window-closed` forgets the xid.

## 7. Layer 2 — wire X + dry-run (smoke)

- Implement `executor` Wnck step builders (using the sequencer) and `engine` Wnck
  signal wiring + `__main__` (`Gtk.init`; `Wnck.Screen.get_default()`; connect
  `window-opened`→hook `name-changed`; `window-closed`; handle already-open
  windows at startup).
- Add `--dry-run` (log planned actions, move nothing) and `--once` (enumerate
  current windows, then exit).
- `./scripts/test.sh smoke` runs `--dry-run --once` against live windows and
  should log the monitor map, the rules, and the plan for each current match —
  **moving nothing**. Eyeball that Calendar/Mail/Th/RPG/pwsafe map correctly.

## 8. Layer 3 — UAT (human acceptance)

1. Disable dp2's Firefox script so the two don't fight:
   `mv ~/.config/devilspie2/firefox-placement.lua{,.disabled}` (dp2 only loads
   `*.lua`; it reloads per window event, so no restart needed).
2. Run live in a terminal, watch logs: `/usr/bin/python3 -m window_tamer`
3. Cold-restart Firefox; verify the acceptance checklist:
   - [ ] Calendar → DP-1 (left), maximized
   - [ ] Mail → DP-4 (center), maximized
   - [ ] Th → DP-4, maximized then minimized; taskbar click restores it
         maximized **on top (no wedge)**
   - [ ] RPG → workspace 2
   - [ ] PasswordSafe (open it) → centered on DP-4
   - [ ] Non-group windows (`Mozilla Firefox`, `Key information …`) never block or
         delay placement; matched windows place within ~1–2s of their title
         gaining the prefix
   - [ ] Placed once — manually moving a window afterward is NOT undone (no jumping)
   - [ ] A Calendar/Mail window opened mid-session is also placed
4. Install + enable the systemd user unit; confirm it survives a real login/reboot.

## 9. Migration / retire devilspie2 (Phase 2, after UAT passes)

Port the remaining dp2 duties, then retire dp2:
- `pwsafe.lua` → already covered by the `passwordsafe` rule; then delete the lua.
- `devilspie2-cinnamon-watcher.service` (`~/bin/devilspie2-cinnamon-watcher`)
  restarts dp2 on Cinnamon restart to re-place windows. xwindow-tamer should
  re-apply rules to all current windows on Cinnamon restart instead (watch the
  same `org.Cinnamon` D-Bus `NameOwnerChanged`, or re-enumerate on a signal),
  folding this job in. Then disable that service.
- Disable dp2 autostart (`~/.config/autostart/devilspie2.desktop`) once nothing
  else needs dp2. Keep dp2 installed-but-dormant as a fallback until confident,
  then remove.

Relevant existing files (on the host):
- `~/.config/devilspie2/firefox-placement.lua` (+ `pwsafe.lua`)
- `~/.config/systemd/user/devilspie2-cinnamon-watcher.service`, `~/bin/devilspie2-cinnamon-watcher`
- `~/.config/autostart/devilspie2.desktop`
- Debug log we used during diagnosis: `~/.cache/devilspie2-placement.log`

## 10. systemd unit (Phase 2 sketch)

`systemd/xwindow-tamer.service` (install to `~/.config/systemd/user/`):
- `ExecStart=/usr/bin/python3 -m window_tamer`, `WorkingDirectory=%h/dev/xwindow-tamer`,
  `Environment=PYTHONPATH=%h/dev/xwindow-tamer DISPLAY=:0`
  (+ `XAUTHORITY=%h/.Xauthority` if needed), `Restart=on-failure`.
- `After=default.target`, `WantedBy=default.target` (NOT graphical-session.target —
  Cinnamon doesn't activate it; see gotcha 6). Validate auto-start at login; if it
  starts before X, `Restart=on-failure` retries until `DISPLAY` is reachable.

## 11. Build Status (update as you go)

- [x] Repo scaffolded, `git init`, dir structure
- [x] Harness: `pyproject.toml` (pytest `pythonpath=["."]`), `scripts/test.sh`
      (`unit`/`smoke`/`status`/`all`), `CLAUDE.md`, this `PLAN.md`
- [x] `window_tamer/__init__.py`
- [x] **C1 monitors — GREEN (6 tests)**
- [x] **C2 rules — GREEN (10 tests)**
- [x] **C3 planner — GREEN (7 tests)**
- [x] **C4 executor sequencer — GREEN (6 tests)**
- [x] **C5 engine dedup — GREEN (5 tests)**
- [x] **Layer 2: X wiring + `--dry-run`/`--once` + smoke** — dry-run smoke maps
      Calendar/Mail/Th/RPG correctly; live (non-dry) execution still needs UAT.
- [ ] Layer 3: UAT (human — needs a watched cold Firefox restart)
- [ ] Phase 2: port pwsafe/watcher, retire dp2, systemd unit
      (`systemd/xwindow-tamer.service` drafted)

## 12. Open decisions (ask the user)

- **Commit cadence:** one commit per green TDD step (granular history) vs. batch
  per layer. (Nothing committed yet beyond `git init`.)
- Confirm rule details before relying on them (esp. Firefox Wnck class string —
  verify it's `Firefox`/`firefox` via `--dry-run` logging; pwsafe class match).

## 13. Conventions (from CLAUDE.md / borrowed from hot-tub-controller & book-translate)

- **TDD red/green**: never skip RED; small increments; one behavior per test;
  diagnostic logging is temporary.
- **Run tests via `./scripts/test.sh`**, not ad-hoc commands.
- Develop on `main`; small commits.
