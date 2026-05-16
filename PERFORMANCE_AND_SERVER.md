# Performance & Server Robustness Analysis

This document lists ways the rolldown simulator can be made faster and the
server/socket layer made more robust.

> **Implementation status:** items **1.2, 1.3, 1.5, 1.6, 2.1, 2.2, 2.3, 2.4**
> have since been implemented (see `shared/networking_server.py`,
> `shared/networking_client.py`, `shared/game.py`, `gui/user_interface.py` and
> the tests in `tests/test_server.py`). They are marked **[DONE]** below. The
> remaining items (1.1, 1.4) are still recommendations only.

---

## 1. Performance improvements (functionality unchanged)

### 1.1 The champion pool is rebuilt over the socket on every roll
`Game.build_champion_pool()` sends a `pool` message, the server JSON-serialises
the **entire** pool (`get_champion_pool` iterates every remaining copy of every
champion), the client `json.loads` it, and then rebuilds five Python lists by
expanding `[unit] * amount`. This happens on *every* `roll()` and *every*
`loaded_dice()`.

*Implementation:*
- Keep an authoritative pool **count dict** (`{name: remaining}`) on the client
  and mutate it locally on buy/sell instead of re-fetching. Only reconcile with
  the server on reset.
- If a server must remain, have it push *deltas* (`{name: +/-n}`) rather than
  the full pool, and cache the last known pool client-side.
- Avoid materialising `[unit] * amount` lists for rolling. Roll a cost, then do
  a **weighted random choice over names** using the count dict
  (`random.choices(names, weights=counts)`), which is O(distinct names) instead
  of O(total copies, ~1500+).

### 1.2 Message storms on every reroll — **[DONE]**
Each reroll sends one `sell:` message per old shop slot and one `buy:` message
per new slot (≈10 round-trips per reroll), each a blocking request/response.

*Implementation:* batch into a single framed message
(`bulk: [{"sell": "Ahri", "level": 1}, {"buy": "Zed"}]`) handled atomically
under one lock acquisition. (This is TODO items #2 and #4 in `TODO`.)

### 1.3 Blocking, one-byte-at-a-time receive loop — **[DONE]**
`send_message()` loops `recv(1024)` and concatenates until it sees a trailing
`\0`. With many small messages this is many syscalls and a hard
synchronization point.

*Implementation:* use **length-prefixed framing** (send a 4-byte big-endian
length, then the payload) and a buffered reader, so a message is read in one
deterministic step with no sentinel scanning.

### 1.4 `roll()` "out of cost" fallback ignores odds
When a cost bucket is empty, `roll()` picks a uniformly random unit from the
entire remaining pool, which is both incorrect (ignores TFT odds) and builds a
full flattened list each time.

*Implementation:* re-roll the cost using the level odds with the empty cost
zeroed out (the loaded-dice code already does this — share that helper).

### 1.5 Repeated work / object churn — **[DONE]**
- `read_database()` is parsed once but `populate_champ_pool()` re-reads and
  re-parses the same JSON on the server; share a single parsed structure.
- `deepcopy(LEVEL_ODDS[level])` in `loaded_dice` can be a plain list copy.
- Reuse `Unit` instances (they are immutable for pool purposes) instead of
  re-instantiating; cache `champions_dict` lookups.

### 1.6 GUI redraw — **[DONE]**
- Cache `QPixmap`s per champion/trait instead of constructing a new `QPixmap`
  from disk on every `refresh_team()` / shop redraw.
- Invert trait icons once (already cached via the `.inverted_icons.json`
  marker) rather than per startup work beyond the marker check.

---

## 2. More robust server implementation

### 2.1 Replace the start-up race — **[DONE]**
`Game.__init__` does `subprocess.Popen(...)` then `time.sleep(0.5)` and hopes
the server is up. This is racy and fixed-cost.

*Implementation:* poll-connect with backoff until connected or a timeout
elapses, or have the spawned server write a readiness file / print a ready
sentinel the client waits on. Better: a **readiness handshake** — the client
retries `connect()` in a loop (e.g. 20 × 100 ms) instead of one blind sleep.

### 2.2 Don't bind clients, and bind the server to loopback — **[DONE]**
The client calls `client_socket.bind((host, port))` with `host =
socket.gethostname()` — clients should not bind, and `gethostname()` resolution
is environment-fragile (fails/varies on WSL, containers, CI).

*Implementation:* server binds `127.0.0.1` (or `0.0.0.0` if remote access is
truly needed); clients simply `connect(("127.0.0.1", PORT))` with no `bind`.

### 2.3 Graceful shutdown — **[DONE]**
`shutdown` is only reachable via `KeyboardInterrupt`; the `shutdown` message
just closes one connection and the accept loop never exits, leaking threads and
the bound port. There is also no clean way to stop the subprocess server.

*Implementation:* a real `shutdown` command sets a `stop` `threading.Event`,
closes the listening socket to break `accept()`, joins client threads, and
exits. Track the server PID so the launching process can terminate it on quit.

### 2.4 Concurrency model — **[DONE]**
A single global `POOL_LOCK` serialises all pool access and there is one thread
per client with unbounded thread creation.

*Implementation options:*
- **Simplest & most robust for a single-player simulator:** drop the socket
  server entirely and make the pool an in-process object (the `client_socket`
  injection added for tests already proves this is feasible — a
  `LocalPool` implementing `send`/`recv`, or better a direct method API).
- If multi-process is required: an `asyncio` server (single thread, no
  per-client threads, no GIL contention) with an async lock, or a
  `socketserver.ThreadingTCPServer` with a bounded pool and explicit
  per-key locking.

### 2.5 Protocol hardening
- Length-prefixed framing (see 1.3) removes the `\0` sentinel ambiguity and
  partial-read bugs.
- Use JSON for *all* messages (including requests) with a `type` field instead
  of substring checks like `'buy' in message` (which also matches `'full_pool'`
  by accident historically).
- Validate inputs and return structured errors instead of raising
  `UnknownMessageError` inside the client thread (which silently kills it).

### 2.6 Idempotent / safe reset
`reset` re-reads `sys.argv[1]` on the server; if the server was started in a
different cwd this breaks. Pass the data directory in the protocol or store it
in server state at startup.

---

## Priority summary

| Priority | Change | Benefit |
|---|---|---|
| High | Client-side pool with local mutation (1.1) | Removes per-roll full serialise/parse |
| High | Length-prefixed framing (1.3 / 2.5) | Removes blocking sentinel loop & partial reads |
| High | Readiness handshake instead of `sleep(0.5)` (2.1) | Removes start-up race |
| Medium | Batch reroll messages (1.2) | ~10× fewer round-trips per reroll |
| Medium | Correct out-of-cost reroll (1.4) | Correctness + less allocation |
| Medium | In-process pool / asyncio server (2.4) | Robustness, no thread leaks |
| Low | Pixmap caching (1.6) | Smoother GUI |
| Low | Graceful shutdown (2.3) | No leaked port/threads |
