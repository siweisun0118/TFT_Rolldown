# Implementation Checklist

Working plan for the seven requested features:

1. Lobby system (see other players' status)
2. Challenge → watch a simulated fight, with a speed slider, replay, and return-to-lobby
3. Health bars in the GUI that update as units take damage
4. Combat event hooks
5. Keywords — Burn, Sunder, Shred, Wound, Precision
6. Items that grant stats and fire effects off hooks
7. A unit stat tab during a fight, without pausing it

Two reference sections follow the phase plan: **Known defects still open**, and a
**Recommendation backlog** giving the verified status of every item in
`PERFORMANCE_NOTES.md` and `PROPOSED_IMPROVEMENTS.md` with its sequencing against
the feature work.

---

## Decisions locked in

| # | Question | Decision |
|---|---|---|
| 1 | Item economy (how players acquire items) | **Settled** — six random items generated at the start of the rolldown; drag onto a board unit to equip, right-click the unit to unequip; item bar sits left of the map |
| 2 | Extend the sim stat model? | **Settled** — AP/AD damage scaling, omnivamp, durability, shields and crit are all in scope; mana and abilities are not |
| 3 | Cross-machine play | **Same machine only** for now. Multiple GUI processes, one shared server |
| 4 | Is `simulate.py`'s batch CLI output frozen? | **Changeable if needed**, but leave it byte-identical for now; any change is a separate, explicit decision |
| 5 | `Nunu`/`RekSai` name mismatch | Alias in the bridge, don't edit the JSONs |
| 6 | Health bars on the rolldown board? | No — the widget exists on every chip but is hidden outside combat |
| 7 | "Loses 60% HP" semantics | Remaining HP drops below the threshold; latched, fires once per threshold per combat |
| 8 | Slider slow end | Literal: 1 s/tick .. 0.01 s/tick. No tick skipping |
| 9 | Challenge etiquette | Decline allowed; one pending challenge at a time; boards snapshotted at accept time; results transient |
| 10 | RNG in item effects | Allowed, but only via a seeded PRNG whose seed is exchanged in the handshake |
| 11 | Crit magnitude | `crit_damage / 100` times damage — 150 means 1.5x. `crit_chance`% per attack |
| 12 | Durability stacking | Multiplicative, not additive |
| 13 | Shield consumption | FIFO by application order; a shield vanishes when its effect ends, whatever is left |
| 14 | Damage scaling order | Star-level scaling first, then `damage * (AD or AP) / 100` |
| 15 | Where hooks live | `simulate/hooks.py`, so the combat engine stays free of `shared/` |
| 16 | Selling a unit | No longer right-click. Drag to the bottom of the screen, or press `E` while hovering |
| 17 | Items with no effect this pass | Blue Buff, Spear of Shojin, Edge of Night, Quicksilver, Nashor's Tooth. Items only *partly* mana/ability dependent keep their remaining effect |

### Two facts that shape everything below

- **A whole fight costs ~46 ms.** Measured: `teams/jhin.txt` vs `teams/melees.txt` = 46 ms; all 153 pairings in `teams/` = 57 ms average. So we compute the entire fight up front and *replay* it, rather than stepping the sim live during playback.
- **The sim is not side-symmetric.** `target_key`, `cell_key`, and `contest_winner` in `simulate/simulate.py` all break ties on `side == 'ally'`. If each client made itself the ally, the two clients would compute *different fights*. The protocol must fix one canonical assignment (challenger = ally) and flip only the rendering.

---

## Phase 0 — Foundations

Nothing here changes behavior. It exists so Phases 1–6 have something to build on, and so we can prove we didn't break the existing simulator.

### 0.1 Lock down current simulator output

- [ ] Add `tests/test_simulate_golden.py`: run `load_units('TFT_Set_17/champion_stats.json')` over every team in `teams/`, compare the full result dict against a committed golden fixture.
- [ ] Commit the golden fixture as `tests/fixtures/simulate_golden.json` (generate it from the *current, unmodified* `simulate.py`).
- [ ] Assert exact equality including key order and the `damage_taken` field — this is the regression net for the Phase 0.3 refactor.

**Files:** `tests/test_simulate_golden.py` (new), `tests/fixtures/simulate_golden.json` (new)

### 0.2 Make `simulate/` importable

- [ ] Add `simulate/__init__.py` (currently missing — the package can't be imported).

**Files:** `simulate/__init__.py` (new)

### 0.3 Refactor `simulate.py` into a steppable engine

Extract the body of the `for now in range(...)` loop into a class. Move nothing else; keep every helper (`round_half_down`, `scale_stat`, `damage_hit`, `ceil_dist`, `sq_dist`, `target_key`, `cell_key`, `contest_winner`, `acquire`, `start_movement`) exactly as-is.

```python
class Combat:
    def __init__(self, ally, enemy, hooks=None, seed=0): ...
    tick: int
    outcome: str | None          # None while running
    def step(self) -> list[Event]  # advance exactly one tick
    def run(self) -> str           # loop step() until outcome is set
```

- [ ] Add `Combat` with the seven numbered phases from the existing loop kept in the same order.
- [ ] Rewrite `simulate(ally, enemy)` as `return Combat(ally, enemy).run()`.
- [ ] Leave `run_fight()` and `main()` untouched in signature and output.
- [ ] Rename the module-level `Unit` to `CombatUnit`, keeping `Unit = CombatUnit` as an alias so existing code and tests don't break. This disambiguates it from `shared.rolldown_classes.Unit`.
- [ ] Run 0.1's golden test — must pass unchanged.

**Files:** `simulate/simulate.py`

### 0.4 GUI ↔ sim bridge

- [ ] New `simulate/bridge.py`:
  - `NAME_ALIASES = {'Nunu': 'Nunu & Willump', 'RekSai': "Rek'Sai"}` — verified: these are the *only* two mismatches between `champions.json` (63 playable) and `champion_stats.json` (63 entries).
  - `stats_name(roster_name) -> str` — applies the alias map.
  - `team_to_entries(team) -> [(stats_name, level, 'A3'), ...]` — reads `Team.board_positions` (keys are already `(row_label, col)` with rows A–D, cols 1–7, exactly what `simulate.ally_cell` consumes). Bench units are skipped.
  - `entries_to_payload(entries) -> dict` / `payload_to_entries(dict) -> entries` for the wire.
  - `load_stats_db(input_dir)` — wraps `simulate.load_units(input_dir / 'champion_stats.json')` with a module-level cache.
- [ ] New `tests/test_bridge.py`: assert every playable champion in `champions.json` resolves to a `champion_stats.json` entry via `stats_name`; assert a round trip of a constructed `Team` through `team_to_entries` → `run_fight` doesn't raise.

**Files:** `simulate/bridge.py` (new), `tests/test_bridge.py` (new)

---

## Phase 1 — Hooks (feature 4)

Built before items and before the fight view, because both consume the same event stream.

### 1.1 Event bus

- [ ] New `simulate/hooks.py`:
  - `Event` — a `NamedTuple` of `(tick, kind, source_idx, target_idx, payload)`. Units are referenced by their **index into `Combat.units`**, not by object, so events serialize cleanly for the replay log.
  - `EventKind` — an `IntEnum` so ordinal comparison is stable. The eleven the spec requires: `COMBAT_START`, `ON_ATTACK`, `ON_CRIT`, `ON_ATTACKED`, `ON_DAMAGE_DEALT`, `ON_DAMAGE_TAKEN`, `ON_HP_THRESHOLD`, `ON_INTERVAL`, `ON_EFFECT_EXPIRED`, `ON_TARGETING_CHANGED`, `ON_UNIT_DEATH`. The list is explicitly non-exhaustive — add more where an item needs one. `COMBAT_END`, `MOVE_START` and `MOVE_END` are required by the replay log regardless.
  - `HookBus` — `subscribe(kind, priority, callback)`, `emit(event)` (queues), `dispatch()` (drains).

### 1.2 Determinism rules (these are the whole point — get them right)

- [ ] Events are **queued** during a phase and **dispatched at one point only**: end of phase 4 (after damage is applied and the dead are marked). Never dispatch mid-iteration over `units`.
- [ ] Dispatch order is `(event.kind, event.source_idx, subscriber_priority, subscription_order)`. Never iterate a `set`.
- [ ] Hook callbacks may queue new events; those are drained in the same `dispatch()` pass with a **recursion depth cap of 8**. Exceeding the cap drops the event and (in debug builds) asserts.
- [ ] All hook arithmetic is integer. Percentages are `value * pct // 100`, never floats.
- [ ] Any randomness goes through `Combat.rng` = `random.Random(seed)`, seeded from the challenge handshake. No bare `random.*` calls.

### 1.3 Threshold events

- [ ] Add `hp_flags: int` to `CombatUnit.__slots__` — a bitmask of thresholds already crossed.
- [ ] Thresholds checked in phase 4 after damage: for each configured percentage `p`, fire `HP_THRESHOLD` once when `hp * 100 < max_hp * p` and the bit is unset, then set the bit. Bits are never cleared, so healing back above does not re-arm (per decision 7).
- [ ] Default thresholds: 60%, 40%, 20%. Configurable via a module constant.

### 1.4 Wire the bus into `Combat`

- [ ] `Combat.__init__` takes an optional `HookBus`; when `None`, a null bus is used so the batch CLI path stays at zero overhead.
- [ ] Emit points, by phase:
  - phase 1 → `MOVE_END`
  - phase 3 → `PRE_ATTACK` / `POST_ATTACK` per firing attacker
  - phase 4 → `DAMAGE_DEALT`, `DAMAGE_TAKEN`, `HP_THRESHOLD`, `UNIT_DEATH`
  - phase 5 → `COMBAT_END`
  - phase 7 → `MOVE_START`
- [ ] `Combat.step()` returns the dispatched event list for the tick.
- [ ] Re-run the golden test: with a null bus, output must still be byte-identical.

### 1.5 Tests

- [ ] `tests/test_hooks.py`: same inputs → identical event log across 100 runs; a hook that deals damage produces the same result regardless of subscription order at equal priority; the depth cap terminates a deliberately self-feeding hook.

**Files:** `simulate/hooks.py` (new), `simulate/simulate.py`, `tests/test_hooks.py` (new)

---

## Phase 1b — Combat model extensions (simulate.py)

The engine currently models hp / damage / mr / armor / attack speed / range and
nothing else. Every item effect depends on this landing first, so it goes in
alongside the hook bus and before items.

### 1b.1 Damage scaling

- [ ] `damage` scales by the unit's offensive stat: AP for a `Magic` role, AD for
      `Attack`, whichever is larger for `Hybrid`. Formula is
      `damage * (AD or AP) / 100`, rounded the way everything else in
      `simulate.py` rounds (half-down, integer-exact).
- [ ] Applied **after** `scale_stat`'s star-level scaling, not before.
- [ ] With every unit at `AP: 100, AD: 100` the baseline is unchanged, so the
      golden test from Phase 0.1 must still pass before items are equipped.

### 1b.2 New stats on `CombatUnit`

- [ ] `crit_chance` (default 25), `crit_damage` (default 150), `omnivamp`
      (default 0), all already present in `champion_stats.json`.
- [ ] Crit: `crit_chance`% per attack, dealing `crit_damage / 100` times damage.
      **This is the engine's first source of randomness** — it must draw from
      `Combat.rng`, seeded from the challenge handshake, or two clients watching
      the same fight will diverge (decision 10).
- [ ] Omnivamp: the attacker heals for that percentage of all damage it deals.
- [ ] Durability: incoming damage reduced by X%, multiple sources stacking
      **multiplicatively** — `dmg * (1-a) * (1-b)`, not `dmg * (1-a-b)`.

### 1b.3 Shields

- [ ] A shield absorbs damage in place of hp, consumed **in application order**:
      a 200 shield applied before a 100 shield absorbs until it is exhausted or
      expires, then the 100 takes over.
- [ ] A shield disappears when its effect ends regardless of how much is left,
      and nothing happens if it was already exhausted.
- [ ] Expiry emits `ON_EFFECT_EXPIRED` — Crownguard converts an expiring shield
      into ability power, so the event has to be observable.

### 1b.4 Keywords

Timed debuffs, all expiring through the same effect machinery:

- [ ] **Burn** — target loses X% max hp per second for Y seconds (true damage).
- [ ] **Sunder** — target loses 30% armor.
- [ ] **Shred** — target loses 30% magic resist.
- [ ] **Wound** — target's healing reduced by that percentage.
- [ ] **Precision** — ability damage may crit. Abilities are out of scope, so
      this is recorded but inert; Infinity Edge and Jeweled Gauntlet reduce to
      their crit stats this pass.
- [ ] Ignored for now: untargetable, shedding negative effects, crowd-control
      immunity.

### 1b.5 Tests

- [ ] Durability stacks multiplicatively; two 50% sources leave 25% of the damage.
- [ ] Shield FIFO order, and expiry discarding the remainder.
- [ ] Crit is reproducible for a fixed seed and identical across two `Combat`
      instances built from the same payload.
- [ ] Burn/Sunder/Shred/Wound each expire on schedule and stack per the item text.

**Files:** `simulate/simulate.py`, `simulate/hooks.py`, `tests/test_combat_model.py` (new)

---

## Phase 2 — Health bars (feature 3)

### 2.1 Widget

- [ ] New `HealthBar(QtWidgets.QWidget)` in `gui/widgets.py`:
  - `set_hp(current, maximum)`, `set_side(side)`.
  - `paintEvent` draws a rounded background track plus a fill whose width is `current / maximum`. Color ramps green → amber → red. Ally and enemy get different border tints.
  - Fixed height ~8 px, expanding width.

### 2.2 Attach to `UnitChip`

- [ ] `UnitChip.__init__` creates `self.health_bar = HealthBar(self)` and calls `self.health_bar.setVisible(False)`.
- [ ] `UnitChip.resizeEvent` (new override) positions the bar across the bottom of the chip with a 2 px inset.
- [ ] `UnitChip.set_hp(cur, max)` forwards to the bar and shows it; `UnitChip.hide_health()` hides it.
- [ ] `UnitChip.set_dead(True)` applies a desaturating `QGraphicsColorizeEffect` (or a 40%-opacity overlay) and hides the bar.
- [ ] Rolldown code paths never call `set_hp`, so the board and bench look exactly as they do today.

### 2.3 Tests

- [ ] `tests/test_gui_healthbar.py` (offscreen, following the existing `QT_QPA_PLATFORM=offscreen` pattern): bar hidden by default; `set_hp(50, 100)` makes it visible with a half-width fill; `set_hp(0, 100)` clamps rather than going negative.

**Files:** `gui/widgets.py`, `tests/test_gui_healthbar.py` (new)

---

## Phase 3 — Fight recording and playback (feature 2, offline half)

Everything in this phase is testable with two hardcoded teams from `teams/` — no server work required.

### 3.1 Recording format

- [ ] New `simulate/recording.py`:
  ```python
  @dataclass
  class FightRecording:
      ally_name: str
      enemy_name: str
      units: list[UnitSnapshot]   # name, side, level, start (x, y), max_hp, items
      events: list[Event]         # the full ordered log from Phase 1
      outcome: str                # 'ally' | 'enemy' | 'tie'
      final_tick: int
      seed: int
  ```
  - `record_fight(db, ally_entries, enemy_entries, seed) -> FightRecording` — builds the combat units, runs `Combat` to completion with a recording `HookBus`, and returns the log. ~46 ms.
  - `to_json` / `from_json` so a recording can be persisted or shipped over the wire if we ever want that.

### 3.2 Replay state machine

- [ ] `ReplayState` in the same module: holds a mutable `{unit_idx: (x, y, hp, alive)}` map, `apply_up_to(tick)` walks events forward, `reset()` returns to tick 0.
- [ ] Because the log is a complete forward description, "replay from the beginning" is just `reset()` + play. No re-simulation.
- [ ] Store keyframes every 500 ticks so seeking backwards doesn't have to replay from 0 (only matters if we add scrubbing later; cheap to build now).

### 3.3 Fight board widget

The combat board is **not** the 4×7 rolldown board. `simulate` uses `x ∈ 0..15`, `y ∈ 1..10` with `x % 2 == y % 2` — i.e. **8 columns × 10 rows**, ally on `y = 1..4`, enemy on `y = 7..10`, rows 5–6 empty.

- [ ] Generalise `HexBoard` in `gui/widgets.py`:
  - Add `show_labels=True` and `interactive=True` constructor flags.
  - `HexTile` skips creating its coordinate `QLabel` when `show_labels=False`, and skips `setAcceptDrops(True)` when `interactive=False`.
  - No geometry changes — the existing `resizeEvent` already offsets odd row indices by half a hex, which is exactly the parity rule the sim uses.
- [ ] Coordinate mapping helper (put it in `simulate/bridge.py`):
  - `sim_to_screen(x, y) -> (row_idx, col_idx)` = `(10 - y, x // 2)`. Enemy ends up at the top, ally at the bottom, and `y` odd → `row_idx` odd → the half-hex offset lines up automatically.
  - Verified: `A4` → `ally_cell` → `(8, 4)` → screen `(6, 4)`, i.e. row A is the front row nearest the enemy. Correct.

### 3.4 Fight view

- [ ] New `gui/fight_view.py` — `FightView(QtWidgets.QWidget)`:
  - An 8×10 `HexBoard(show_labels=False, interactive=False)`.
  - A header showing both player names and the tick clock (`tick / 100` seconds).
  - A `QSlider` mapping linearly to `ms_per_tick ∈ [10, 1000]`, labeled with the resulting speed multiplier.
  - `Replay` button → `ReplayState.reset()` and restart playback.
  - `Return to Lobby` button → emits `returnToLobby` signal.
  - Play/pause toggle (cheap to add, and necessary in practice at the slow end of the slider).
  - A result banner on `COMBAT_END`.

### 3.5 Playback timing (do not drive a QTimer at the tick rate)

- [ ] A single `QTimer` at a fixed ~16 ms (60 fps). On each fire:
  - `elapsed = now - last_frame_time`
  - `ticks_to_advance = (accumulator + elapsed) // ms_per_tick`; carry the remainder in the accumulator.
  - Apply every event in `(current_tick, current_tick + ticks_to_advance]` to `ReplayState`, then repaint.
- [ ] This decouples playback from timer granularity — Qt cannot reliably fire at 10 ms, but it can happily apply 2 ticks per 16 ms frame.
- [ ] Changing the slider mid-playback updates `ms_per_tick` without resetting the accumulator.
- [ ] Note for later: at the slow end, a tie-capped fight is 5500 ticks × 1 s = ~92 minutes. Per decision 8 we implement the literal mapping; the pause button and Return-to-Lobby are the escape hatches.

### 3.6 Rendering

- [ ] `FightView.render_state()` maps each live unit to its tile, calls `chip.set_unit(...)` with the splash from `Game.splash_path`, and `chip.set_hp(hp, max_hp)`.
- [ ] Dead units → `chip.set_dead(True)`.
- [ ] Only repaint tiles whose contents changed since the last frame (track a dirty set) — at 60 fps over 80 tiles this matters.

### 3.7 Tests

- [ ] `tests/test_fight_view.py` (offscreen): slider position → `ms_per_tick` mapping at both extremes; `Replay` resets the tick to 0 and restores full HP; advancing to `final_tick` reproduces the recording's outcome; `sim_to_screen` round trips for all 80 valid cells.

**Files:** `simulate/recording.py` (new), `gui/fight_view.py` (new), `gui/widgets.py`, `simulate/bridge.py`, `tests/test_fight_view.py` (new)

---

## Phase 4 — Lobby (feature 1)

Same-machine only (decision 3): several GUI processes, one shared `networking_server.py`.

### 4.1 Server-side lobby registry

- [ ] `shared/rolldown_enums.py`: add `LOBBY_LOCK = threading.Lock()` and `LOBBY = {}` alongside the existing `POOL_LOCK` / `CHAMPION_POOL`.
- [ ] `shared/networking_server.py`:
  - Give `client_thread` per-connection state: `player_id` (a `uuid4` hex), `player_name`, `state`, `inbox` (a list of pending notifications).
  - Register on `hello`, deregister in the existing `finally` block so a crashed GUI leaves the lobby cleanly.
  - New verbs, all fitting the existing single request → single response framing:

    | message | response |
    |---|---|
    | `hello: <name>` | `OK: <player_id>` |
    | `status: <rolling\|ready\|in_fight>` | `OK` |
    | `lobby` | JSON list of `{id, name, state, board_size}` |
    | `challenge: <target_id>` | `OK: <challenge_id>` or `ERROR: ...` |
    | `inbox` | JSON list of pending notifications, then clears |
    | `accept: <challenge_id>` | JSON `{seed, ally: <payload>, enemy: <payload>}` |
    | `decline: <challenge_id>` | `OK` |
    | `board: <json>` | `OK` — stashes this player's team payload for challenges |
    | `bye` | `OK` |

  - **Challenger is always `ally`** (see the side-symmetry note at the top). The server records which side each player is on and hands both clients the identical `{seed, ally, enemy}` blob, so both compute the same fight.
  - One outstanding challenge per player, per decision 9. A second `challenge` while one is pending returns `ERROR: challenge pending`.
  - `accept` snapshots both `board:` payloads *at accept time*.

### 4.2 Client-side lobby

- [ ] New `shared/lobby_client.py` — thin wrapper over `send_message` exposing `hello`, `set_status`, `list_players`, `challenge`, `poll_inbox`, `accept`, `decline`, `publish_board`, `bye`.
  - Reuses `Game.client_socket`. Keeping it on the Qt main thread means it serializes naturally with buy/sell and needs no socket lock.
  - Set a socket timeout (2 s) around every call so a dead server can't freeze the UI. On timeout, surface a toast and stop polling.
- [ ] New `gui/lobby_view.py` — `LobbyView(QtWidgets.QWidget)`:
  - `QTableWidget` of players: name, status, board size, and a Challenge button per row.
  - Incoming-challenge prompt (a `QMessageBox` or an inline banner) with Accept / Decline.
  - A `QTimer` at 1 s calling `lobby` + `inbox`.
  - Emits `fightReady(recording)` when a challenge is accepted on either side.

### 4.3 Window flow

- [ ] `gui/user_interface.py`: wrap the existing central widget in a `QStackedWidget` with three pages — rolldown (index 0), lobby (1), fight (2).
  - `gui/user_interface_v3.py`'s `setupUi` keeps building the rolldown page exactly as it does now; the stack wraps it in `MainWindow`.
  - Add a **"Done Rolling"** button to the rolldown top bar (there is no notion of "finished" today). Clicking it publishes the board via `board:`, sets status `ready`, and switches to the lobby page.
  - `FightView.returnToLobby` → status back to `ready`, switch to page 1.
  - `MainWindow.closeEvent` → send `bye` so the player disappears from other people's lobbies.
- [ ] Prompt for a player name at startup, next to the existing gold/level `QInputDialog` calls in `take_inputs`. Default to `getpass.getuser()`.

### 4.4 Both sides run the sim

- [ ] On accept, both clients call `record_fight(db, ally_entries, enemy_entries, seed)` with the identical blob from the server, then hand the recording to `FightView`. No fight state crosses the network — just the two team payloads and the seed.
- [ ] Add a cheap integrity check: each client sends `result: <challenge_id>: <outcome>` and the server logs a warning if the two disagree. That catches version skew between clients early.

### 4.5 Tests

- [ ] `tests/test_lobby.py`: drive the server verbs directly (the existing `tests/test_perf_and_server.py` already calls server functions in-process without a real socket — follow that pattern). Cover: register/deregister; `lobby` reflects status changes; a second challenge is rejected; decline clears the pending challenge; disconnect removes the player.
- [ ] A determinism test: run `record_fight` twice with the same seed and payload, assert identical event logs — this is the cross-client agreement guarantee.

**Files:** `shared/networking_server.py`, `shared/rolldown_enums.py`, `shared/lobby_client.py` (new), `gui/lobby_view.py` (new), `gui/user_interface.py`, `gui/user_interface_v3.py`, `tests/test_lobby.py` (new)

---

## Phase 5 — Wire lobby to fight

- [ ] `LobbyView.fightReady` → `MainWindow` builds the `FightView`, switches to page 2, starts playback.
- [ ] Set status `in_fight` for the duration; back to `ready` on return.
- [ ] Handle the opponent disconnecting mid-fight: the recording is already local and complete, so playback just continues; only the return-to-lobby path needs to notice the player is gone.
- [ ] Toast on `ERROR:` responses using the existing `Toast` widget rather than modal dialogs.

---

## Phase 6 — Items (feature 6)

No longer blocked: the item data exists and the stat model lands in Phase 1b.

### 6.1 Generate `TFT_Set_17/items.json`

- [ ] Read `items_semantic.json` and emit `items.json` with the same stat block,
      replacing the prose `effect` string with a JSON array of hooks to trigger.
- [ ] Hook entries name an `EventKind` from `simulate/hooks.py` plus its
      parameters, so an effect is data rather than code where possible.
- [ ] The five items in decision 17 get an empty effect array — stats only.
- [ ] Items that are only *partly* mana- or ability-dependent keep the rest:
      Ionic Spark keeps its Shred aura, Protector's Vow its shield, Adaptive Helm
      its role-based stats, Hand of Justice its conditional doubling.

### 6.2 Item model

- [ ] `Unit.items` on `shared/rolldown_classes.Unit`, carried through `copy()` and
      `upgrade()`, and serialized into the challenge payload — items must cross
      the wire or the two clients simulate different fights.
- [ ] Decide and document whether item stats apply before or after `scale_stat`,
      and test it. Decision 14 fixes the AD/AP scaling order; this is the
      remaining ordering question.
- [ ] `simulate/items.py` — effect implementations registered as `HookBus`
      subscribers at `COMBAT_START`.

### 6.3 Item bar and equipping

- [ ] Six random items generated at the start of the rolldown, shown in a bar to
      the **left of the map** (the traits column currently occupies that side —
      decide whether items sit beside or below it).
- [ ] Drag an item onto a board unit to equip; up to three per unit.
- [ ] Right-click a board unit to unequip. This is now unambiguous: Phase 7
      removes right-click-to-sell.
- [ ] Render equipped items as pips on the `UnitChip`.

### 6.4 Thief's Gloves

- [ ] Counts as one item in the bar, three once equipped.
- [ ] Cannot go on a unit that already holds an item, and blocks any further
      items on that unit.
- [ ] Its two random items are drawn **once at the start of the rolldown** and do
      not change; multiple copies roll independently.

### 6.5 Tests

- [ ] Every item in `items.json` resolves to known hooks with valid parameters.
- [ ] The three-item cap, and the Thief's Gloves exclusivity rules in both
      directions.
- [ ] An equipped item changes the fight outcome deterministically for a fixed seed.

**Files:** `TFT_Set_17/items.json` (new), `simulate/items.py` (new), `simulate/bridge.py`, `shared/rolldown_classes.py`, `gui/widgets.py`, `gui/user_interface.py`, `tests/test_items.py` (new)

---

## Phase 7 — GUI changes

Independent of the fight work; can land any time after Phase 0.

### 7.1 Replace right-click-to-sell

Right-click is reassigned to unequip (Phase 6) and to the fight stat tab (7.3), so
the existing binding at `gui/user_interface.py:_chip_clicked` must go.

- [ ] Remove the right-click sell path.
- [ ] **Drag to the bottom of the screen to sell.** No drop target exists there
      today — `setAcceptDrops(True)` appears only on `HexTile` and `BenchSlot`,
      and `ShopSlot` has none. Either make the shop row a drop target or add a
      dedicated sell strip.
- [ ] **`E` while hovering to sell.** No hover tracking exists anywhere in the GUI
      (no `setMouseTracking`, `enterEvent`, `leaveEvent` or `underMouse`), so
      `UnitChip` needs it. `E` is free; `M`, `D`, `F` and `P` are already bound.

### 7.2 Board icons fill the hex

- [ ] `HexTile.resizeEvent` currently insets the chip to `side * 0.62`, which is
      what makes the icons look tiny. Enlarge toward the hex's inscribed area,
      keeping the coordinate label legible and the drop target intact.

### 7.3 Unit stat tab during a fight

- [ ] Right-clicking a unit in the fight view opens a panel showing its stats and
      current hp.
- [ ] It must **not** pause playback — the panel reads from `ReplayState` and
      refreshes on the existing 60 fps timer.

**Files:** `gui/widgets.py`, `gui/user_interface.py`, `gui/fight_view.py`, `tests/test_gui_interaction.py` (new)

---

## Testing summary

| Test file | Covers |
|---|---|
| `tests/test_simulate_golden.py` | Batch CLI output unchanged by the `Combat` refactor |
| `tests/test_bridge.py` | Name aliasing, team → entries, all 63 champions resolve |
| `tests/test_hooks.py` | Event ordering determinism, recursion cap |
| `tests/test_gui_healthbar.py` | Health bar visibility, fill width, clamping |
| `tests/test_fight_view.py` | Slider mapping, replay reset, coordinate mapping |
| `tests/test_lobby.py` | Lobby verbs, challenge lifecycle, cross-client determinism |
| `tests/test_combat_model.py` | Durability stacking, shield FIFO and expiry, seeded crit, keyword timing |
| `tests/test_items.py` | Hook resolution, the three-item cap, Thief's Gloves rules |
| `tests/test_gui_interaction.py` | Sell by drag and by `E`, hex-filling icons, the fight stat tab |

All GUI tests run under `QT_QPA_PLATFORM=offscreen`, matching the existing `tests/conftest.py` fixtures.

---

## Suggested order

1. Phase 0 (foundations) — no behavior change, retires the refactor risk
2. Phase 1 (hooks), then 1b (combat model and keywords) — 1b is what items need
3. Phase 2 (health bars)
4. Phase 3 (fight view, driven by a hardcoded matchup)
5. Phase 6 (items) — now unblocked, and testable offline against the fight view
6. Phase 4 + 5 (lobby, then wire it up)
7. Phase 7 (GUI changes) — independent, land whenever convenient

Phases 0–3, 6 and 7 need zero server changes and are independently testable, which puts most of the risk behind us before any networking work starts. Items move ahead of the lobby because they only need the combat model and the fight view, not the protocol.

---

## Known defects still open

Verified against the code, and not covered by any recommendation in
`PERFORMANCE_NOTES.md` or `PROPOSED_IMPROVEMENTS.md`. Several bear directly on the
lobby and fight work, since they only bite once more than one client shares a
server.

| Defect | Evidence | Bears on |
|---|---|---|
| `print(cur_pool)` dumps the whole pool on every loaded-dice roll | `shared/game.py` | — |
| Framing helpers duplicated verbatim between client and server | `networking_client.py` vs `networking_server.py` | any protocol change |
| Length prefix is unbounded — a peer can force a huge `recv` | `networking_client.py` | lobby |
| `loaded_dice` falls back to the module-global `CHAMPION_POOL`, which is only populated in the server process, so it is always empty in a client | `shared/game.py` | — |
| Server spawned as literal `'python'` with no `cwd=`; dies outside the repo root or where only `python3` exists | `shared/game.py` | — |
| Two GUIs starting together both spawn a server; the loser cannot bind | `shared/game.py` | lobby |
| `assert POOL_LOCK.locked()` checks that *someone* holds the lock, not the caller | `networking_server.py` | lobby |
| Three-star exclusion is client-local, so another player can still roll a champion someone has 3-starred | `shared/game.py` | lobby |
| `_probe_protocol` accepts any framed `pool` reply, so a client opened for one set can attach to a server loaded with another | `shared/game.py` | lobby |
| `shared/loaded_dice.py` is a dead duplicate that cannot be imported | `shared/loaded_dice.py` | — |
| `datetime.utcnow()` is deprecated from Python 3.12 | `networking_server.py` | — |
| The `shutdown` operation is byte-identical to `quit` and stops nothing | `networking_server.py` | lobby |

Seven related recommendations have already been implemented: the sell path now runs
through `Game` and updates the pool cache, loaded dice reserves its picks, replay is
idempotent, operation dispatch matches exactly, the client and server bind loopback,
a refused sell no longer mutates local state, and three-star tracking is per-instance.

---

## Recommendation backlog

Status of every recommendation in `PERFORMANCE_NOTES.md` and
`PROPOSED_IMPROVEMENTS.md`, verified against the code as it stands. Nine are done,
seven partial, nine untouched.

| ID | Recommendation | Status | What remains |
|---|---|---|---|
| 1.1 | Cache the champion pool client-side | partial | `invalidate_pool_cache()` has no production caller, so a client never learns of another client's mutations; `build_champion_pool` still materializes the whole pool per call |
| 1.2 | Shallow-copy the loaded-dice odds | done | — |
| 1.3 | O(1) `(name, level)` index in `Team` | not done | the index is maintained by every mutator and read by nobody — either wire `count_on_board`/`count_on_bench`/`__contains__`/`remove_copies` to it or delete it |
| 1.4 | Cache trait icons, and champion splashes | partial | trait pixmaps are cached; `_pixmap_for_unit` still decodes from disk on every call |
| 1.5 | Single-pass `add_unit_to_bench` | partial | the open-slot scan is inlined; the two count helpers are still separate passes |
| 1.6 | Batch `random.choices` per roll | done | — |
| 1.7 | Skip unchanged shop slots | not done | `same_unit` is computed and never used; every reroll rebuilds all five slots |
| 1.8 | Cache `Team.active_traits()` | not done | no cache or dirty flag exists |
| 1.9 | Precompute champion splash paths | done | one `is_file()` remains in `UnitChip.set_unit`, shared with 1.4's residue |
| 1.10 | Keep the server log out of the CWD | done | via `shared/paths.py` and `ROLLDOWN_DATA_DIR` rather than `QStandardPaths` |
| 1.11 | Move `THREE_STARRED` off the module level | done | — |
| 2.1 | Replace the bootstrap sleep with backoff | done | raises a plain `RuntimeError` rather than a named `ServerStartupError` |
| 2.2 | Length-prefixed framing | done | the helpers are duplicated verbatim in client and server |
| 2.3 | Bounded worker lifecycle | not done | one thread per accept, appended to a list that is never pruned |
| 2.4 | Reader/writer pool lock | not done | still a single exclusive lock; reads serialize behind writes |
| 2.5 | Structured errors, worker survives | partial | the worker survives, but the reply is an `ERROR:` string rather than a structured payload |
| 2.6 | Bind to loopback | done | — |
| 2.7 | JSON request/response protocol | not done | still positional strings with `startswith` dispatch and colon splitting |
| 2.8 | Heartbeat and idle timeout | not done | no ping/pong and no socket timeout |
| 2.9 | Transactional buy/sell | partial | sells now require the acknowledgement first; `roll()` still issues five independent buys with no rollback |
| 2.10 | Scope the spawned server's environment | done | — |
| 2.11 | Unix-domain socket on POSIX | not done | `AF_INET` only |
| 2.12 | Transition log with replay | partial | replay is idempotent; the log is still never truncated or rotated |
| 2.13 | Graceful shutdown on a signal | not done | no signal handler, and the `shutdown` operation still only closes the caller's connection |
| 2.14 | Server on an ephemeral port for tests | partial | the `live_server` fixture covers tests; there is no production helper or configurable port |

### Sequencing against the feature work

**Before the lobby (Phase 4).**

- [ ] **2.7 JSON protocol.** The lobby adds roughly nine verbs carrying nested
      payloads — player lists, board snapshots, challenge blobs, seeds. Every one
      of them is a new sentinel string under the current parser.
- [ ] **2.3, cheap half.** Have workers deregister in their `finally` block. A stale
      thread is a ghost player in everyone's lobby; the asyncio rewrite the
      recommendation packages it with is not warranted.
- [ ] **1.1 completion.** A per-client cache with no resync is a correctness bug the
      moment two GUIs share a server, which the lobby makes the normal case.

**Before the fight view (Phase 3).**

- [ ] **1.4 / 1.9 residue.** Cache decoded splash pixmaps and drop the per-chip
      `stat`. A fight repainting ~20 units puts PNG decoding in the animation loop.
- [ ] **1.8 trait cache.** Cheapest isolated win, and combat hooks will refresh
      traits per event rather than per click.

**Whenever convenient.** 1.3 (wire the index or delete it), 1.5, 1.7, 2.1's typed
exception, 2.2's shared framing module, 2.5 and 2.9 folded into 2.7, 2.12's log
lifecycle, 2.13 alongside 2.14's stop plumbing.

**Skip for this project.** 2.4 (a reader/writer lock buys nothing at a handful of
local clients), 2.8 (same-host clients die with their sockets; lobby presence
belongs at the application level), 2.11 (loopback TCP is fast enough and
`AF_UNIX` breaks the Windows path).

