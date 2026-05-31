# Performance and server-robustness notes

This document catalogues every concrete change we could make to speed up the
TFT-Rolldown simulator and make its client/server communication more robust.
**No code changes** are made here – every item below is a recommendation with
enough detail that an implementer can pick it up and act on it without
spelunking through the existing files.

Each item is structured as **Problem → Proposed fix → How to implement →
Expected impact** so you can pick whichever is the best trade-off for your
constraints.

---

## 1. Performance improvements (functionality preserved)

### 1.1 The champion pool is rebuilt from scratch on every roll

* **Problem.** `Game.build_champion_pool` (`shared/game.py`) calls
  `send_message(self.client_socket, 'pool')`, decodes the JSON, then loops
  over every entry to materialise a fresh `{rarity: [Unit, …]}` dictionary.
  Reading the entire pool over TCP and deserialising it is on the critical
  path of every roll/reroll.
* **Proposed fix.** Cache the pool in the client and only invalidate the
  cache when the player actually changes it (buy, sell, reroll, loaded
  dice).  Most of the time the cache is still valid, so no message is
  needed.
* **How to implement.** Add `self._pool_cache` and `self._pool_dirty` flags
  to `Game`.  Wrap every `_send_buy_message` / `_send_sell_message` call so
  it also updates the local cache directly (the server already knows the
  effect, no need to ask it).  Provide a `_resync_pool()` method that pulls
  the authoritative state from the server only when needed (e.g. on
  reconnect or on user request).
* **Expected impact.** O(1) hot path instead of O(N) over the entire pool
  (~250 entries currently).  Removes the largest source of GUI stutter on
  rapid rolldowns.

### 1.2 `LEVEL_ODDS` is copied with `deepcopy` per loaded-dice slot

* **Problem.** `Game.loaded_dice` uses `deepcopy(LEVEL_ODDS[level])` inside
  a loop, even though each call only mutates a small list of five floats.
* **Proposed fix.** Use `list(LEVEL_ODDS[level])` (a one-level shallow copy)
  instead of `deepcopy`.  Five integers do not need recursive copying.
* **How to implement.** Replace `deepcopy(LEVEL_ODDS[level])` with
  `list(LEVEL_ODDS[level])`.
* **Expected impact.** Microsecond-scale wins, but `deepcopy` is one of the
  most expensive standard-library operations; removing it from a hot loop
  is worth doing.

### 1.3 Linear scans in `Team` (now mitigated, can be improved further)

* **Problem.** `Team._count_on_board`, `Team._count_on_bench`,
  `Team._remove_copies`, and `Team.__contains__` are all O(N) over the
  team.  Even if N is small (≤ 18), every shop refresh calls them.
* **Proposed fix.** Maintain a `{ (unit_name, level): set[location] }` index
  alongside `self.board` / `self.bench` so all five operations become O(1)
  to O(k) where k is the number of matching copies.
* **How to implement.** Update the index in `add_unit_to_bench`,
  `_buy_triggers_upgrade`, `remove_unit_from_board`, `remove_unit_from_bench`,
  `move_to_bench`, `move_within_bench`, `move_within_board`.  Add invariants
  asserted in tests so the index can't drift from the storage.
* **Expected impact.** Negligible for small boards, but it makes the cost
  predictable and unlocks more aggressive caching elsewhere.

### 1.4 Trait icons are repeatedly loaded from disk

* **Problem.** `MainWindow._pixmap_for_trait` (in `gui/user_interface.py`)
  hits the filesystem on every trait refresh – this happens after every
  buy, sell, or move.
* **Proposed fix.** Cache `QPixmap` objects keyed by trait name and load
  them lazily.  `QPixmap` is cheap to copy because it is internally
  reference-counted.
* **How to implement.** Build a dictionary `self._trait_pix_cache` populated
  on first use; clear it only when the set directory changes.
* **Expected impact.** Eliminates disk I/O from the hot UI path.  Worth
  doing for champion splashes too (`_pixmap_for_unit`).

### 1.5 `add_unit_to_bench` walks the bench three times

* **Problem.** Finding the leftmost open slot, counting bench copies, and
  potentially placing the unit are three separate full passes.
* **Proposed fix.** Compute counts in a single loop, or rely on the index
  proposed in §1.3.
* **How to implement.** Inline `_count_on_bench` and `first_open_bench_slot`
  inside `add_unit_to_bench`.
* **Expected impact.** ~3x reduction in loops when buying, but trivial at
  bench size 9.

### 1.6 `random.choices` is called inside `Game.roll` per slot

* **Problem.** `random.choices(...)` is called five times for the five
  shop slots, each time re-computing cumulative weights.
* **Proposed fix.** Compute the cumulative weights once per `roll` and
  reuse them across all five draws.
* **How to implement.** Use `random.choices(..., k=5)` (we already do for
  the cost roll; do the same for the unit draws).
* **Expected impact.** Micro-optimisation but the loop runs many times in
  long simulations.

### 1.7 `display_new_shop` clears every label even when the slot is unchanged

* **Problem.** On every reroll we call `slot.display(unit, pixmap)` for all
  five slots, even though Qt does its own dirty checks.
* **Proposed fix.** Track the displayed unit per slot and skip the call
  when it would set the same value.
* **How to implement.** Compare `slot.unit` with the new unit before
  calling `slot.display(…)`.
* **Expected impact.** Reduces redraw load during rapid rolldowns.

### 1.8 `Team.active_traits` builds a list, sorts it, and never caches it

* **Problem.** Called twice per UI refresh (`refresh_traits` plus any
  diagnostic call).  Each call iterates over every trait on the team.
* **Proposed fix.** Cache the result and invalidate when `self.traits`
  mutates (i.e. inside `_add_traits_for` / `_remove_traits_for`).
* **How to implement.** Add `self._active_traits_cache = None` and clear it
  in the two mutation helpers.
* **Expected impact.** Modest – useful when the same data is read several
  times per frame, especially after we add tooltips/hovers.

### 1.9 Pre-compute champion splash paths once at game start

* **Problem.** `_pixmap_for_unit` calls `.is_file()` on every paint to
  decide between `name` and `id_name`.
* **Proposed fix.** Build a dictionary of `{ unit_name: Path }` during
  `read_database` (or first GUI use) so the path resolution is a single
  dictionary lookup.
* **How to implement.** Walk `champions/` once, recording the most-specific
  path for every champion.  Surface as `Game.splash_path(unit)`.
* **Expected impact.** Removes stat calls from the GUI hot path.

### 1.10 Use `QStandardPaths.AppLocalDataLocation` for the server log

* **Problem.** The `server_log` file is written to the CWD, which sometimes
  collides between concurrent runs.
* **Proposed fix.** Use a per-user data directory.
* **How to implement.** Replace `SERVER_LOG_FILE = Path('server_log')` with
  a function that returns
  `Path(QStandardPaths.writableLocation(QStandardPaths.AppLocalDataLocation)) / 'rolldown.log'`.
* **Expected impact.** Removes flakiness from tests run in parallel.

### 1.11 Tracking and clearing `THREE_STARRED` should not be global

* **Problem.** `THREE_STARRED` is a module-level `set()` shared across
  every test and game session.  Tests must clear it between runs (we do –
  see `conftest.py`).
* **Proposed fix.** Move the set onto the `Game` instance.
* **How to implement.** Replace global with `self._three_starred`.
* **Expected impact.** Cleaner state, no test interactions, opens the door
  to multi-player support later.

---

## 2. Server robustness suggestions

### 2.1 The server bootstrap race

* **Problem.** `Game.__init__` spawns the server as a subprocess and then
  sleeps for 0.5 s before connecting.  On a slow machine the sleep is
  short, on a fast machine it is wasted time.  If the server never starts,
  the connect call eventually fails with a confusing error.
* **Proposed fix.** Replace the sleep with a polling loop that retries
  `init_rolldown_client(0)` up to N times with exponential backoff and
  raises a clean `ServerStartupError` if the deadline is exceeded.
* **How to implement.** Wrap the connect call in
  ```python
  for delay in (0.05, 0.1, 0.25, 0.5, 1.0):
      try:
          return init_rolldown_client(0)
      except ConnectionRefusedError:
          time.sleep(delay)
  raise ServerStartupError(...)
  ```
* **Expected impact.** Eliminates the 0.5 s startup hitch and the silent
  failures observed in `start.py`.

### 2.2 `client_socket.recv(1024)` assumes a single chunk

* **Problem.** The client receives at most 1024 bytes per call but the
  pool message can easily exceed this for richer sets.  Worse, the message
  framing relies on a trailing `\0`, but if a single `recv` lands a chunk
  larger than 1024 bytes the next message can leak into the response.
* **Proposed fix.** Use length-prefixed framing or a proper line-protocol
  with `socket.makefile('rb')`.  Each message is preceded by a 4-byte
  network-order length so the reader knows exactly how much to consume.
* **How to implement.** Add a `framing.py` module with `read_message`/
  `write_message` helpers; route every send/recv through them.
* **Expected impact.** Eliminates one class of subtle data-corruption bug
  and makes `recv` re-entrant.

### 2.3 The server uses one thread per client and never joins them

* **Problem.** `init_rolldown_server` spawns a thread per client and
  appends it to a list, but the list grows without bound and threads are
  only joined on `shutdown`.  A long-running session leaks threads.
* **Proposed fix.** Use a thread pool (`concurrent.futures.ThreadPoolExecutor`)
  or, even better, `asyncio` with non-blocking sockets.  Threads should
  remove themselves from the registry on exit.
* **How to implement.** Replace the manual loop with an `asyncio` server
  using `asyncio.start_server`.  Each client lives inside an `async def`
  coroutine; cancellation is automatic when the connection closes.
* **Expected impact.** Constant memory regardless of client count; trivial
  shutdown.

### 2.4 `POOL_LOCK` is a global module-level lock

* **Problem.** Holding a process-wide lock around every pool operation
  serialises all clients.  Even simple reads (`pool`, `full_pool`) wait for
  unrelated writes (`buy`, `sell`).
* **Proposed fix.** Use a reader/writer lock so multiple `pool` queries can
  proceed in parallel while `buy`/`sell` retain exclusive access.
* **How to implement.** Use `threading.RWLock` from `readerwriterlock`
  (third-party) or implement one using two semaphores.  Update the
  `with POOL_LOCK:` blocks accordingly.
* **Expected impact.** Higher throughput when many GUIs are connected.

### 2.5 Server crashes propagate via `UnknownChampionError` and stop the thread

* **Problem.** When a buyer sends an unknown champion, the server raises
  `UnknownChampionError` which kills the worker thread.  The client never
  gets a definitive error and is left hanging.
* **Proposed fix.** Send a structured error response and continue the
  loop.  The exception should be logged, not propagated.
* **How to implement.** Wrap the `recv → dispatch` body in
  `try: … except (UnknownChampionError, UnknownMessageError) as err:` and
  always send a `{"error": "..."}` payload back.
* **Expected impact.** No more zombie threads; clients see clear errors.

### 2.6 No authentication / authorisation

* **Problem.** Anyone on the host can connect to port 8000 and mutate the
  pool.  Fine for a local sim, but worth flagging.
* **Proposed fix.** Either bind the server to `127.0.0.1` exclusively, or
  require a per-session token negotiated at connect time.
* **How to implement.** Replace `socket.gethostname()` with `'127.0.0.1'`
  in `init_rolldown_server`; document that the simulator is single-host.
* **Expected impact.** Reduces blast radius to the local machine.

### 2.7 The client message format is positional and brittle

* **Problem.** Messages such as `sell: Aatrox: 2` rely on string splitting
  with `:`.  A unit name containing a colon would break the parser
  (Set 17's `N.O.V.A.` would not, but future sets might).
* **Proposed fix.** Switch to JSON or msgpack messages with explicit
  keys (`{"op": "sell", "unit": "Aatrox", "level": 2}`).
* **How to implement.** Add `Protocol` constants on both sides, plus a
  `parse_message` helper that returns `(op, args)`.
* **Expected impact.** Robustness against future content; easier to extend
  with new operations (e.g. trait queries).

### 2.8 No heartbeat / no idle timeout

* **Problem.** A client that has lost its network never gets evicted and
  the server keeps its thread alive.
* **Proposed fix.** Send a `ping` from the server every N seconds; close
  the connection if `pong` doesn't arrive within `timeout` seconds.
* **How to implement.** Background `asyncio.Task` per connection scheduling
  `await connection.write(PING)` then `await asyncio.wait_for(...)`.
* **Expected impact.** Self-healing server in face of network blips.

### 2.9 Buy/sell messages are not transactional

* **Problem.** A failed `buy` (unknown champion, server crash mid-write)
  can leave the client with the unit on its bench but the server still
  thinking it's in the pool.
* **Proposed fix.** Adopt a request/response model where the server
  acknowledges the new state.  Clients only mutate locally after the
  acknowledgement.
* **How to implement.** Treat every message as a request that must be
  answered with a structured `{"ok": true, "state": ...}` or
  `{"ok": false, "error": ...}` response.
* **Expected impact.** Eliminates the desync class of bugs.

### 2.10 Spawned server inherits the GUI's environment

* **Problem.** `subprocess.Popen([...])` inherits `QT_QPA_PLATFORM` and
  other Qt-related vars from the GUI process, which can affect the server
  if it ever imports Qt (it shouldn't, but it's coupled).
* **Proposed fix.** Pass an explicit `env=` to `Popen` that includes only
  the variables the server actually needs.
* **How to implement.** Build `env = {'PATH': os.environ['PATH'], ...}`
  before launching.
* **Expected impact.** Decouples server start from GUI environment.

### 2.11 Replace the bare TCP server with a unix-domain socket on Linux

* **Problem.** TCP is overkill for a same-host server and exposes port
  8000.  Conflicts arise when something else is using the port.
* **Proposed fix.** Use a unix-domain socket (`AF_UNIX`) on POSIX hosts and
  fall back to TCP on Windows.
* **How to implement.** `socket.socket(socket.AF_UNIX, …)` plus path under
  `tempfile.gettempdir()`.
* **Expected impact.** Faster IPC on Linux, no port collisions.

### 2.12 The server has no persistent log of state transitions

* **Problem.** When something goes wrong the only artefact is whatever
  hit `stdout` / `stderr`.  Restarting the server loses pool state.
* **Proposed fix.** Append every mutation to a JSON-lines append-only log
  (`logs/rolldown.log.jsonl`).  Replay on startup to restore state.
* **How to implement.** Open the file in append mode and write
  `json.dumps({"op": op, "ts": now, …})` plus `'\n'`.  Replay reads each
  line and reapplies via `dispatch`.
* **Expected impact.** Crash resilience and auditability.

### 2.13 No graceful shutdown signal

* **Problem.** The server exits only on Ctrl-C; a kill -TERM leaves
  half-handled connections.
* **Proposed fix.** Install a `signal.signal(signal.SIGTERM, handler)` that
  flushes pending operations and joins client threads.
* **How to implement.** Move `shutdown(main_socket, client_threads)` into
  a signal handler.
* **Expected impact.** Clean shutdown when killed by systemd / docker.

### 2.14 Tests cannot drive the server end-to-end without a real port

* **Problem.** Running tests against the real server is racy.
* **Proposed fix.** Provide a `Server.run_in_process(timeout=…)` helper
  plus a `Game.with_local_server(...)` context manager that picks an
  ephemeral port (`bind((..., 0))`).
* **How to implement.** Expose the server's bind port after `bind()` and
  pipe it to clients via the helper.
* **Expected impact.** Reliable integration tests.

---

## 3. Summary

The two highest-leverage changes are:

1. **Cache the champion pool client-side** (§1.1) – removes the dominant
   per-roll cost and avoids most server round trips.
2. **Switch to length-prefixed JSON framing** (§2.2 + §2.7) – fixes a real
   class of bugs and makes the protocol extensible.

Everything else falls under "polish" and can be picked up incrementally.
