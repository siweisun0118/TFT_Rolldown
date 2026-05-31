# Proposed (but not yet implemented) improvements

This document holds detailed implementation proposals for the four items
in `PERFORMANCE_NOTES.md` that we have **not** yet rolled in.  Each entry
includes the precise files that would change, the data structures
involved, the rollout plan, and the testing strategy.

The proposals are written so an implementer can pick any one and ship
it independently of the others.

> The companion file `PERFORMANCE_NOTES.md` lists every recommendation
> and explains *why* each one is worthwhile.  This file is **how** for
> the four still-pending items.

---

## §1.8  Cache `Team.active_traits()`

**Problem recap.** `Team.active_traits()` walks every trait on the team,
classifies each by tier, then sorts the result.  `MainWindow.refresh_traits()`
calls it after every buy / sell / move; cumulatively that's the largest
trait computation per frame.  The trait dictionary itself changes only
when the board changes – sells from the bench do not invalidate it.

### Data structure

Add three private attributes to :class:`Team`:

```python
self._traits_cache_dict = None   # dict[str, int]  – output of _compute_traits()
self._active_traits_cache = None # list[tuple]     – output of active_traits()
self._traits_dirty = True
```

### Invalidation points

The cache is only invalidated when the *board contents* change.  Those
are the methods that mutate `self.board_positions`:

* `place_on_board`
* `move_to_bench`
* `move_within_board`
* `remove_unit_from_board`
* `_remove_copies` (only when `board_removed` is non-empty)
* `_place_upgraded` (only when target lands on the board)
* `_maybe_upgrade` (it calls the two above, so cache invalidation lives
  inside them rather than here)

A small helper:

```python
def _mark_traits_dirty(self):
    self._traits_dirty = True
```

is called at the start of every mutator listed above.  Bench-only
mutations (`move_within_bench`, `remove_unit_from_bench`) deliberately
skip the invalidation since the bench does not contribute traits.

### `active_traits()` body

```python
def active_traits(self):
    if not self._traits_dirty and self._active_traits_cache is not None:
        return list(self._active_traits_cache)
    traits = self._compute_traits()           # existing helper
    self._traits_cache_dict = traits
    result = []
    for trait_name, amount in traits.items():
        # ... unchanged classification logic ...
        result.append((trait_name, amount, next_break, tier))
    tier_order = {'prismatic': 0, 'gold': 1, 'silver': 2, 'bronze': 3, 'inactive': 4}
    result.sort(key=lambda r: (tier_order.get(r[3], 99), r[0]))
    self._active_traits_cache = result
    self._traits_dirty = False
    return list(result)            # return a copy so callers can't poison
```

`get_traits()` is unaffected – it already delegates to `active_traits()`.

### Tests to add

* Mutating a bench slot does **not** invalidate the cache (assert the
  cache instance survives the operation).
* Mutating a board slot **does** invalidate the cache.
* A test that toggles the same unit between board and bench many times
  and asserts `active_traits()` is monotonically equal to the
  freshly-computed version.

### Risk / rollout

* Pure additive change behind a `_traits_dirty` flag; if a mutator is
  missed the worst case is a stale-but-still-correct trait list after a
  bench-only mutation.  Add a debug assertion in the test suite to
  guarantee no mutator forgets the invalidation call.
* No new dependencies, no API change.

---

## §2.7  JSON message format

**Problem recap.** Current messages are positional strings such as
`sell: Aatrox: 2`.  This couples the parser to the unit's name format,
disallows colons in champion names, and makes it hard to add new
operations without breaking the parser.

### Wire format

We already have length-prefixed framing (§2.2), so the JSON payload sits
inside that envelope.  Each message is a JSON object with two top-level
keys:

```json
{"op": "buy", "args": {"unit": "Aatrox"}}
{"op": "sell", "args": {"unit": "Aatrox", "level": 2}}
{"op": "pool"}
{"op": "shutdown"}
```

The response is also JSON:

```json
{"ok": true,  "result": {"pool": {"Aatrox": 27, ...}}}
{"ok": false, "error": "unknown_unit", "details": "Foo"}
```

### Files affected

* `shared/networking_protocol.py` (new): hosts `encode_request`,
  `decode_request`, `encode_response`, `decode_response`, plus a
  `Protocol` constant with the op names.  Defines exceptions
  `ProtocolError` and `ServerError` derived from `RuntimeError`.
* `shared/networking_client.py`: replace the string `send_message` with
  `request(op, **args) -> dict`.  Internally it calls the framing
  helpers (already present) and `json.dumps` / `json.loads`.
* `shared/networking_server.py`: dispatch switches on `payload['op']`
  rather than `message.startswith(...)`.  Each helper returns a Python
  dict that gets serialised; errors raise a `ServerError(code, detail)`
  caught by the worker loop.
* `shared/game.py`: replaces every `send_message(self.client_socket, ...)`
  call with `self.client.request('buy', unit=name)` etc.  Returns either
  the unpacked `result` dict or raises `ServerError`.

### Migration plan

1. Land `networking_protocol.py` and the new client/server methods.
2. Add a `_protocol_version` field to the handshake (first message);
   `1` = legacy string protocol, `2` = JSON.  The server keeps a tiny
   legacy parser for the duration of one release.
3. Bump everything to v2 and delete the legacy parser.

### Tests to add

* Round trip every op through `encode_request` / `decode_request`.
* Server returns `ok=false` for unknown ops, unknown champions, and
  malformed payloads.
* Backwards-compat tests pinning the v2 wire bytes for the most common
  operations (buy / sell / pool) so future refactors don't change the
  format silently.

### Risk / rollout

* JSON is verbose but the framing helper guarantees the payload survives
  the wire, so the only meaningful cost is a slightly higher CPU spend
  per message.  Profiling the server (§2.3) shows the JSON encode/decode
  of a full pool takes <2 ms on a 2020-era laptop – well below the
  per-frame budget.

---

## §2.8  Heartbeats + idle timeout

**Problem recap.** A client that has lost its network connection never
gets evicted because we never look for missing traffic.  Each orphaned
worker thread holds an FD and a Python stack until the process restarts.

### Design

The server now has two background coroutines per client (or two timers
in the threading implementation):

* **Send a `ping` every `HEARTBEAT_INTERVAL` seconds** (default 5 s).
  The client must respond with `pong` within `HEARTBEAT_TIMEOUT`
  seconds (default 15 s).  We allow up to two missed pings before
  evicting the connection (handles short network blips on Wi-Fi).
* **Idle timeout.** If no message arrives within `IDLE_TIMEOUT`
  seconds (default 60 s), the connection is closed.

### Implementation – threading version

We currently use one thread per client.  Heartbeats are easiest to
implement on top of a non-blocking socket using `select`.

```python
def client_thread(connection, addr, champions):
    connection.setblocking(False)
    last_recv = time.monotonic()
    last_ping = time.monotonic()
    awaiting_pong = False

    while True:
        ready, _, _ = select.select([connection], [], [], 1.0)
        now = time.monotonic()

        if ready:
            try:
                message = recv_framed(connection)
            except (ConnectionError, BlockingIOError):
                break
            last_recv = now
            if message == 'pong':
                awaiting_pong = False
                continue
            response = dispatch(message, champions)
            send_framed(connection, response)

        # Idle eviction.
        if now - last_recv > IDLE_TIMEOUT:
            break
        # Heartbeat scheduling.
        if not awaiting_pong and now - last_ping > HEARTBEAT_INTERVAL:
            send_framed(connection, 'ping')
            last_ping = now
            awaiting_pong = True
        # Pong timeout.
        if awaiting_pong and now - last_ping > HEARTBEAT_TIMEOUT:
            break
    connection.close()
```

The client must respond to `ping` with `pong`.  The client's
`recv_framed` loop already handles arbitrary string payloads, so we
just need a small dispatch table on the client side too.

### Implementation – asyncio version (preferred long term)

If we migrate to `asyncio.start_server` (§2.3), heartbeats become a
`asyncio.create_task(_heartbeat(writer))` per connection that runs:

```python
async def _heartbeat(writer):
    while not writer.is_closing():
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        send_framed(writer, 'ping')
```

and the reader coroutine matches `pong` against an `asyncio.Event`.

### Files affected

* `shared/networking_server.py`: add the loop above.
* `shared/networking_client.py`: handle inbound `ping` by replying
  `pong` from the receive loop.
* `tests/test_perf_and_server.py`: add a regression test that the
  server kills connections that don't reply to two consecutive pings.

### Tests to add

* Spawn a fake client (`socketpair`) that does **not** respond to
  pings; assert the server-side worker exits within
  `HEARTBEAT_TIMEOUT * 2` seconds.
* Spawn a client that replies promptly; assert the connection stays
  open for `HEARTBEAT_INTERVAL * 4` seconds without eviction.

### Risk / rollout

* The protocol gains the `ping`/`pong` strings.  Once the JSON protocol
  (§2.7) lands these become `{"op": "ping"}` / `{"op": "pong"}` so the
  message space stays clean.
* The threading version is somewhat ugly because we mix blocking
  framing helpers with non-blocking `select`; revisiting once §2.3 is
  done is recommended.

---

## §2.13  Graceful shutdown signal

**Problem recap.** Today the server only exits on `Ctrl-C`; a
`kill -TERM` leaves clients with half-handled connections.

### Design

* Install signal handlers for `SIGTERM` (POSIX) and `signal.SIGBREAK`
  (Windows).  The handlers set a `_stop` `threading.Event`.
* The main accept loop checks `_stop.is_set()` between accepts.
* Each worker also polls `_stop.is_set()` between messages (the
  heartbeat loop already polls once per second; we can reuse that
  tick).

### Implementation

```python
import signal
_stop = threading.Event()

def _request_shutdown(signum, frame):
    print(f'Received signal {signum}; shutting down...')
    _stop.set()

def init_rolldown_server(argv):
    ...
    signal.signal(signal.SIGTERM, _request_shutdown)
    if hasattr(signal, 'SIGBREAK'):
        signal.signal(signal.SIGBREAK, _request_shutdown)
    main_socket.settimeout(0.5)  # so accept() periodically returns control

    try:
        while not _stop.is_set():
            try:
                connection, addr = main_socket.accept()
            except socket.timeout:
                continue
            ...  # spawn worker as today
    finally:
        shutdown(main_socket, client_threads)
```

Worker shutdown:

```python
def client_thread(connection, addr, champions):
    while not _stop.is_set():
        ...
    try:
        send_framed(connection, '{"op": "bye"}')
    except OSError:
        pass
    connection.close()
```

### Files affected

* `shared/networking_server.py`: signal handler, modified accept loop,
  worker shutdown.
* `shared/networking_client.py`: optional – treat the `bye` message as
  a normal close.

### Persistence interaction

The transition log (§2.12) is already append-only and flushed after
every record.  No extra work is needed for shutdown – the log file is
always in a consistent state.

### Tests to add

* Send a `SIGTERM` to the server process; assert it exits within 2
  seconds and the transition log ends cleanly (no half-written line).
* Assert clients that are mid-operation receive an `error: shutting_down`
  response rather than a stalled socket.

### Risk / rollout

* `signal.signal` only runs on the main thread, but our threading
  layout already has that property.  When we move to asyncio (§2.3),
  `loop.add_signal_handler(...)` replaces this with the same semantics.
* Worth landing alongside §2.8 since they share the "poll for a flag
  every second" infrastructure.

---

## Cross-cutting next step

If only one of these is to be picked up next, **§1.8** is the easiest
win and isolated from networking changes.  After that, **§2.7** unlocks
§2.8 and §2.13 by giving us a richer wire format to add `ping`/`pong`
and `bye` ops without inventing new sentinel strings.
