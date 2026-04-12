# Domain Pitfalls: Admin UI Integration (FastAPI + APScheduler Mixed Model)

**Domain:** Adding FastAPI admin dashboard to existing APScheduler background-thread trading bot
**Researched:** 2026-04-12
**Scope:** Integration pitfalls specific to v1.1 Admin UI milestone — NOT general trading bot pitfalls
**Confidence:** HIGH (findings grounded in existing MuTrade codebase + well-understood Python threading/asyncio behavior)

---

## Context: Current MuTrade Architecture

Before reading pitfalls, understand what already exists:

- `BackgroundScheduler` runs `run_session()` in its own thread (APScheduler thread pool)
- `uvicorn` owns the main thread and runs an `asyncio` event loop
- `BotStateHub` already bridges them via `threading.RLock` + `asyncio.Queue(maxsize=1)` + `threading.Event`
- `hub.push_snapshot()` uses `loop.call_soon_threadsafe()` — already correct
- `hub.request_stop()` uses `threading.Event` — already correct
- `TrailingStopEngine.states` returns a shallow `dict` copy (not a live reference)

This means several thread-safety primitives are already in place. The pitfalls below focus on what is NOT yet built and what can go wrong when adding routes, WebSocket, config editing, and log parsing.

---

## Critical Pitfalls

Mistakes that cause incorrect bot behavior, data corruption, or silent race conditions.

---

### Pitfall 1: Reading `engine.states` Directly from FastAPI Without a Lock

**Confidence:** HIGH

**What goes wrong:**
`TrailingStopEngine._states` is a plain Python `dict` mutated by the APScheduler thread (inside `engine.tick()`). If a FastAPI route accesses `engine.states` (the property) concurrently while `tick()` is running, the dict iteration inside `tick()` and the dict copy inside the property happen without synchronization.

In CPython, the GIL makes most individual dict operations safe, but a for-loop over a dict while another thread modifies it raises `RuntimeError: dictionary changed size during iteration`. This can happen if a new symbol is added mid-tick.

**Why it happens:**
Developer passes `engine` into `create_app()` (already done in `main.py`), then accesses `engine.states` from a FastAPI route directly, reasoning that `TrailingStopEngine.states` returns a copy so it's "safe." The copy is safe; the iteration to build the copy is not if `tick()` adds a new key simultaneously.

**Warning signs:**
- Intermittent `RuntimeError: dictionary changed size during iteration` in APScheduler thread
- Dashboard shows stale or partial symbol data
- Error is non-deterministic — hard to reproduce in testing

**Prevention:**
Route handlers must NOT call `engine.states` directly. They must call `hub.get_snapshot()` instead. `BotStateHub` already has `_lock` protecting `_snapshot`, and `push_snapshot()` serializes engine state into `_snapshot` from the APScheduler thread. The FastAPI route reads `_snapshot` (already-serialized, already-copied dict) safely.

Rule: FastAPI → hub → snapshot. Never FastAPI → engine directly.

**Phase:** Phase 6 (Dashboard routes). Enforce in code review gate.

---

### Pitfall 2: Double-Start Race Condition in Bot Start Endpoint

**Confidence:** HIGH

**What goes wrong:**
A `/bot/start` endpoint that calls `scheduler.add_job()` or `scheduler.resume()` is unsafe if called twice in rapid succession (user double-clicks, network retry, or automated client retry). Two concurrent requests can:
1. Add the same job twice → two `run_session()` closures run simultaneously → two threads both calling `engine.tick()` → concurrent dict mutation → data corruption and duplicate sell orders
2. Each closure independently sets `hub.set_running(True)` and calls `hub.clear_stop()` — the second call clears the stop flag the first may have just set

Additionally: `hub.is_running()` is not an atomic check-and-set. Between `is_running()` returning `False` and `set_running(True)` being called, another request can also see `False` and proceed.

**Why it happens:**
Route checks `hub.is_running()`, sees False, proceeds to start bot. Two simultaneous requests both check before either one updates the flag.

**Warning signs:**
- Duplicate `[LIVE] SELL SIGNAL` log entries for the same symbol within the same second
- `sell_pending` set inconsistency (two threads both check/set it)
- `hub._is_running` alternates unexpectedly

**Prevention:**
Use a `threading.Lock` (not `RLock`) as a mutex specifically for start/stop operations. The lock must be held for the full check-then-act sequence:

```python
# In BotStateHub or a dedicated BotController
_start_stop_lock = threading.Lock()

def start_bot(self) -> bool:
    """Returns True if bot was started, False if already running."""
    with self._start_stop_lock:
        if self._is_running:
            return False
        # start scheduler job here
        self._is_running = True
        return True
```

Route returns HTTP 409 Conflict if `start_bot()` returns False.

Additionally: APScheduler job IDs must be used — `scheduler.get_job("market_poll")` returns `None` if not running. Check job existence before adding.

**Phase:** Phase 7 (Bot control endpoints). The lock must be in BotStateHub or a new BotController class.

---

### Pitfall 3: Stop-During-Sell Race Condition

**Confidence:** HIGH

**What goes wrong:**
`hub.request_stop()` sets `_stop_event`. The APScheduler thread checks `is_stop_requested()` at the TOP of the while loop, before calling `poll_prices()`. But if the stop is requested between `engine.tick()` returning a signal and `executor.execute(sig)` completing:

```
APScheduler thread:           FastAPI thread:
tick() → sell signal
                              request_stop() sets event
executor.execute(sig) starts
  → KIS order submitted
  → wait for fill ...
is_stop_requested() → True
break → hub.set_running(False)
  executor still waiting for fill!
```

The session function returns but `executor.execute()` may still be waiting for fill confirmation (polling loop inside `OrderExecutor`). Now `hub.is_running()` returns `False` but the bot is still submitting orders. A second start request sees `is_running() == False` and launches a new session — two sessions now active.

**Why it happens:**
`hub.is_running()` reflects scheduler loop state, not executor state. The stop check is only at the top of the while loop, not inside executor.

**Warning signs:**
- `is_running()` returns False but KIS order status queries still appearing in logs
- Duplicate orders for same symbol in same session
- `hub.set_running(False)` logged before order fill confirmation logged

**Prevention:**
Two strategies:

1. **Executor-aware stop flag:** `OrderExecutor.execute()` should check `hub.is_stop_requested()` between fill-check polls and abort gracefully (mark order as submitted but stop fill-waiting).

2. **Graceful stop with timeout:** Add `hub.set_executing(True/False)` calls around `executor.execute()`. The stop endpoint waits up to N seconds for `is_executing()` to go False before acknowledging the stop. Return HTTP 202 Accepted from the stop endpoint (not 200), with a status field indicating "stopping."

For v1.1 scope: at minimum, document in UI that "Stop" waits for current sell to complete. Return bot status as `"stopping"` vs `"running"` vs `"stopped"`.

**Phase:** Phase 7 (Bot control endpoints). Requires BotStateHub extension.

---

### Pitfall 4: `asyncio.Queue(maxsize=1)` Overflow Silently Dropping Updates

**Confidence:** HIGH

**What goes wrong:**
`BotStateHub._change_queue` is `asyncio.Queue(maxsize=1)`. `push_snapshot()` calls `_change_queue.put_nowait()` from the APScheduler thread via `call_soon_threadsafe`. If `wait_for_change()` is not being awaited (e.g., no active WebSocket client), the queue fills after the first push. Subsequent `put_nowait()` calls raise `asyncio.QueueFull` — which is silently caught by the `except RuntimeError` block in `push_snapshot()`.

Wait: `QueueFull` is NOT a `RuntimeError` — it is `asyncio.QueueFull(Exception)`. The current except clause only catches `RuntimeError` (for closed-loop case). `QueueFull` propagates up uncaught and will be swallowed by `call_soon_threadsafe`'s exception handling, which discards exceptions in the scheduled callback.

Actually: `call_soon_threadsafe` schedules `_change_queue.put_nowait` as the callback. If `put_nowait` raises, the exception is logged by the event loop as an unhandled callback exception — NOT raised in the APScheduler thread. This means the APScheduler thread never sees it, but the asyncio event loop logs an ERROR-level exception trace every 3-5 seconds.

**Warning signs:**
- asyncio event loop printing `Exception in callback Queue.put_nowait()` every poll cycle
- Dashboard WebSocket not receiving updates despite bot running
- Log file filling with asyncio exception traces

**Prevention:**
Replace the `put_nowait` strategy with a "replace if full" pattern:

```python
def _enqueue_snapshot(self, snapshot: dict) -> None:
    """Called in asyncio thread via call_soon_threadsafe."""
    if self._change_queue is None:
        return
    # Drain old value if queue is full (we only need latest state)
    while not self._change_queue.empty():
        try:
            self._change_queue.get_nowait()
        except asyncio.QueueEmpty:
            break
    try:
        self._change_queue.put_nowait(snapshot)
    except asyncio.QueueFull:
        pass  # Should never happen after drain, but safe fallback
```

This ensures the queue always holds at most the latest snapshot. No exception risk.

**Phase:** Phase 6 (Dashboard / WebSocket). Fix in BotStateHub before WebSocket route is written.

---

### Pitfall 5: Config Hot-Reload Creating Inconsistent Engine State

**Confidence:** HIGH

**What goes wrong:**
A `/config` POST endpoint that writes new config.toml and then calls `engine.reload()` (or reinitializes engine) is dangerous if called while `run_session()` is mid-poll:

1. `run_session()` iterates `config.symbols` (from the old `AppConfig` it captured at startup via closure)
2. New config removes symbol `005930`
3. `engine._symbols` is updated to remove `005930`
4. Next iteration of `run_session()`'s for loop calls `engine.tick(prices)` with `005930` still in prices dict
5. `tick()` skips it (symbol not in `_symbols`) — benign BUT `_states` still has `005930` entry
6. If new config adds `000660` at threshold 5%, engine doesn't know about it until session restart

The fundamental issue: `run_session()` is a long-lived closure that captured `config` at creation time. The config object inside the closure cannot be hot-reloaded — it is immutable (`frozen=True` dataclass).

**Why it happens:**
Developer writes config.toml, reloads `AppConfig`, and updates `engine._symbols` from a FastAPI route. The `run_session()` closure still holds a reference to the OLD `config` object and uses it for `config.symbols` iteration and `config.market_close_hour` check.

**Warning signs:**
- New symbol added via UI not being monitored in current session
- Removed symbol still appearing in logs
- `market_close_hour` change not taking effect in current session

**Prevention:**
Config changes take effect at the NEXT session start, not mid-session. The UI must clearly communicate this: "Changes saved. Will apply on next market session (tomorrow 09:00 KST)."

Implementation:
1. Write config.toml atomically (see Pitfall 6)
2. Validate new config with `load_config()` before writing — if invalid, return 422 with error
3. Do NOT attempt to hot-reload engine mid-session
4. Store "pending config" path in hub; apply at next scheduler job execution

**Phase:** Phase 8 (Config editor). Must not attempt mid-session reload.

---

### Pitfall 6: Non-Atomic Config File Write Corrupting config.toml

**Confidence:** HIGH

**What goes wrong:**
A naive `open("config.toml", "w")` write from a FastAPI route can leave a partial file if the process crashes mid-write, or if the APScheduler thread tries to read config.toml concurrently (e.g., for a manual session trigger). A corrupted config.toml on the next bot start crashes the process entirely with a `tomllib.TOMLDecodeError`.

Additionally: Python's `tomllib` (stdlib in 3.11+) only supports READ, not write. There is no stdlib TOML writer. The common approach is using `tomli-w` (write counterpart to `tomllib`). If the endpoint serializes config back to TOML using string formatting instead of a proper serializer, it can produce malformed TOML (e.g., floats like `1e-05` instead of `0.00001`, which some parsers reject).

**Why it happens:**
- Direct file open/write without atomic temp-file pattern
- String-building TOML instead of using `tomli-w`
- No pre-write validation with `load_config()`

**Warning signs:**
- config.toml is 0 bytes after server crash
- `TOMLDecodeError` on next bot start
- Threshold values serialized in scientific notation

**Prevention:**
1. Use `tomli-w` for serialization (install as dependency: `tomli-w>=1.0`)
2. Apply the same `tempfile.mkstemp() + os.replace()` pattern already used in `StateStore.save()`
3. Validate: call `load_config(tmp_path)` before `os.replace()` — if it raises, discard temp file and return 422
4. Use a `threading.Lock` around the write operation (shared with any future config-read paths)

```python
# Atomic config write pattern (mirrors StateStore.save())
import tempfile, os, tomli_w

_config_lock = threading.Lock()

def save_config(new_data: dict, path: Path) -> None:
    with _config_lock:
        fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as f:
                tomli_w.dump(new_data, f)
            # Validate before committing
            load_config(tmp)  # raises on invalid
            os.replace(tmp, path)
        except BaseException:
            try: os.unlink(tmp)
            except OSError: pass
            raise
```

**Phase:** Phase 8 (Config editor). `tomli-w` must be added to dependencies before Phase 8.

---

### Pitfall 7: Blocking File I/O in Async FastAPI Routes (Log Parsing)

**Confidence:** HIGH

**What goes wrong:**
`loguru` writes to `logs/mutrade.log` (rotating, up to 10 MB). A `/trades` endpoint that reads this file synchronously with `open()` + `readlines()` blocks the asyncio event loop for the duration of the read. For a 10 MB file, this can take 50-200ms — enough to delay ALL other pending requests, including WebSocket heartbeats and the health endpoint.

This is the most commonly made mistake when adding "simple" read endpoints to FastAPI. It is invisible in development (small log file) but degrades in production.

**Why it happens:**
`open()` in an async def route is not async — it blocks. The asyncio event loop has no other coroutine scheduled while the file read runs.

**Warning signs:**
- Dashboard WebSocket disconnects during log fetch (event loop blocked, heartbeat missed)
- `/health` endpoint times out during `/trades` request
- 10 MB log file fetch takes >100ms

**Prevention:**
Two options:

1. **`asyncio.to_thread()`** (Python 3.9+, preferred for simplicity):
```python
import asyncio

@app.get("/trades")
async def get_trades():
    records = await asyncio.to_thread(_read_trade_logs, "logs/mutrade.log")
    return records

def _read_trade_logs(path: str) -> list[dict]:
    # sync file read — runs in thread pool, does not block event loop
    ...
```

2. **`aiofiles`** for full async file I/O (adds dependency, marginally better for large files):
```python
import aiofiles
async with aiofiles.open("logs/mutrade.log") as f:
    content = await f.read()
```

Prefer option 1 (`asyncio.to_thread`) — no extra dependency, idiomatic Python 3.9+. `aiofiles` is overkill for a single endpoint.

**Tail-reading optimization:** For large log files, don't read the whole file. Read the last N bytes (configurable, default 512 KB) with `seek(-524288, 2)`, then parse `[TRADE]` markers from that segment. This caps read latency regardless of log file size.

**Phase:** Phase 9 (Trade history endpoint). Pattern must be enforced for ALL file I/O in async routes.

---

## Moderate Pitfalls

---

### Pitfall 8: WebSocket Connection Leak on Client Disconnect

**Confidence:** HIGH

**What goes wrong:**
A WebSocket route that does `await hub.wait_for_change()` in a loop will block indefinitely when the browser tab is closed, because the disconnect is not detected until the next `await websocket.send_text()` fails. If the bot stops sending updates (e.g., market is closed), the coroutine hangs forever, accumulating leaked connections.

Each leaked WebSocket connection holds the coroutine frame in memory. For a personal bot with a handful of users this is a memory leak, not a crisis — but it prevents clean server shutdown (uvicorn waits for coroutines to complete).

**Warning signs:**
- `uvicorn` takes >10 seconds to shut down after Ctrl+C
- Number of active connections grows without bound during development
- `wait_for_change()` never returns between sessions

**Prevention:**
Wrap the receive loop with `asyncio.wait_for()` timeout and catch `WebSocketDisconnect`:

```python
from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
import asyncio

@app.websocket("/ws/status")
async def ws_status(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            try:
                snapshot = await asyncio.wait_for(
                    hub.wait_for_change(), timeout=30.0
                )
            except asyncio.TimeoutError:
                # Send heartbeat ping
                await websocket.send_json({"type": "ping"})
                continue
            await websocket.send_json(snapshot)
    except WebSocketDisconnect:
        pass  # Clean exit on browser close
```

The 30-second timeout serves as both a keepalive mechanism and a disconnect-detection heartbeat.

**Phase:** Phase 6 (Dashboard WebSocket). Required pattern from the first WebSocket route written.

---

### Pitfall 9: SSE / WebSocket Broadcasting to Multiple Clients via Single `asyncio.Queue`

**Confidence:** HIGH

**What goes wrong:**
`BotStateHub._change_queue` is a single `asyncio.Queue`. `wait_for_change()` does `queue.get()`, which CONSUMES the item. If two browser tabs both call `/ws/status`, only one WebSocket coroutine receives each snapshot — the other blocks until the next push. This is a fan-in, not fan-out.

**Why it happens:**
Single queue was designed for single-consumer (simple dashboard). Adding a second browser tab or a second endpoint (e.g., both WebSocket and SSE) breaks the single-queue assumption.

**Warning signs:**
- Second browser tab shows stale data while first tab updates correctly
- Alternating updates between two tabs (each gets every other update)

**Prevention:**
Replace the single queue with a broadcast pattern — `asyncio.Event` + shared snapshot:

```python
# In BotStateHub:
self._update_event = asyncio.Event()

def _notify_update(self):
    """Called in asyncio thread via call_soon_threadsafe."""
    self._update_event.set()

async def wait_for_change(self) -> dict:
    await self._update_event.wait()
    self._update_event.clear()  # Reset for next update
    return self.get_snapshot()
```

OR use `asyncio.Condition` for proper multi-waiter fan-out:

```python
async def wait_for_change(self) -> dict:
    async with self._condition:
        await self._condition.wait()
        return self.get_snapshot()

def _notify_update(self):
    # call_soon_threadsafe(self._condition.notify_all)  # NOT safe directly
    # Must wrap in coroutine
    asyncio.run_coroutine_threadsafe(self._async_notify(), self._loop)

async def _async_notify(self):
    async with self._condition:
        self._condition.notify_all()
```

For v1.1 (personal single-user dashboard), Pitfall 9 is LOW severity. Design the API to support fan-out from the start, but a TODO comment is acceptable if only one tab is expected.

**Phase:** Phase 6 (Dashboard). Decide fan-out strategy before writing WebSocket route. Single queue is fine for single user; document the limitation.

---

### Pitfall 10: `scheduler.shutdown(wait=False)` Not Stopping Active `run_session()`

**Confidence:** HIGH

**What goes wrong:**
`app.py`'s lifespan shutdown calls `scheduler.shutdown(wait=False)`. This stops APScheduler from scheduling NEW jobs but does NOT interrupt an already-running `run_session()` job. If shutdown happens during market hours, `run_session()`'s `while True` loop continues running in the APScheduler thread — the thread is not a daemon thread by default in recent APScheduler versions.

The result: uvicorn completes shutdown (asyncio loop stops), but the APScheduler thread is still alive, making KIS API calls. Python's main process cannot exit until all non-daemon threads complete. The process hangs.

**Why it happens:**
`wait=False` is used to avoid blocking the shutdown, but it does not signal the job to stop.

**Warning signs:**
- `python mutrade/main.py` does not exit after Ctrl+C during market hours
- Log continues to show `Polled N symbols` after uvicorn shutdown line
- Process requires `kill -9` to stop

**Prevention:**
The shutdown sequence in `lifespan` must:
1. Call `hub.request_stop()` first (already done)
2. Wait for `hub.is_running()` to go False, with timeout:
```python
# In lifespan shutdown
hub.request_stop()
# Wait up to 10 seconds for session to acknowledge stop
deadline = asyncio.get_event_loop().time() + 10.0
while hub.is_running() and asyncio.get_event_loop().time() < deadline:
    await asyncio.sleep(0.5)
scheduler.shutdown(wait=False)
```

The `run_session()` loop checks `is_stop_requested()` at the top of each iteration — max latency is one `poll_interval` (3-5 seconds). A 10-second wait covers this.

**Phase:** Phase 7 (Bot control). The graceful shutdown logic must be in `app.py`'s lifespan BEFORE Phase 7 ships.

---

## Minor Pitfalls

---

### Pitfall 11: `asyncio.get_event_loop()` Deprecation Warning in Python 3.12

**Confidence:** HIGH

`app.py` currently uses `asyncio.get_running_loop()` — correct for Python 3.10+. But if any new code (routes, utilities) uses `asyncio.get_event_loop()` outside a running coroutine, Python 3.12 emits a DeprecationWarning that becomes an error in 3.14+. Always use `asyncio.get_running_loop()` inside async functions.

**Phase:** General code quality — enforce in all new async code.

---

### Pitfall 12: `threading.RLock` in `BotStateHub` Is Reentrant — Not a Bug, But Easy to Misread

**Confidence:** HIGH

`BotStateHub` uses `threading.RLock` (reentrant lock). This allows the same thread to acquire the lock multiple times without deadlocking. This is correct for the current design: `push_snapshot()` and `set_running()` both acquire `_lock`, and if called sequentially from the same APScheduler thread, they do not deadlock.

However: if future code ever calls `push_snapshot()` from within a `get_snapshot()` lock scope (nested acquisition), the behavior is correct but confusing. And if the lock is ever replaced with a plain `threading.Lock`, nested calls will deadlock silently.

**Prevention:** Document in `BotStateHub` docstring that `_lock` is RLock intentionally, and why. Do not add nested lock acquisition without understanding this.

**Phase:** Documentation only — no code change needed.

---

### Pitfall 13: Loguru's Log Rotation Truncating Active `[TRADE]` Entry

**Confidence:** MEDIUM

When `loguru` rotates `logs/mutrade.log` at 10 MB, a log entry that spans the rotation boundary (extremely unlikely but possible for long Telegram notification bodies) will be split between two files. Log parser reading only the latest file will miss the partial entry. For `[TRADE]` markers, this would result in a missing trade record in the UI.

**Prevention:** Parse both the current log file AND the most recent rotated file (`.1` suffix). `loguru`'s rotation naming pattern: `mutrade.log`, `mutrade.log.1`, etc. In practice this is low-probability for short [TRADE] entries.

**Phase:** Phase 9 (Trade history). Note in log parser implementation.

---

## Phase-Specific Warning Matrix

| Phase Topic | Likely Pitfall | Pitfall # | Mitigation |
|-------------|---------------|-----------|------------|
| BotStateHub QueueFull | Queue overflow on no active WebSocket | #4 | Replace put_nowait with drain-then-put pattern |
| Dashboard WebSocket | Connection leak on browser close | #8 | asyncio.wait_for() + WebSocketDisconnect catch |
| Dashboard WebSocket | Single consumer queue, multi-tab | #9 | Design for fan-out; document single-user limitation |
| Dashboard routes | Direct engine.states access | #1 | Route → hub.get_snapshot() only |
| Bot start endpoint | Double-start race condition | #2 | threading.Lock for check-then-act |
| Bot stop endpoint | Stop-during-sell race | #3 | Executor-aware stop; graceful shutdown with status |
| Graceful shutdown | Session not stopping on uvicorn exit | #10 | Wait loop in lifespan + hub.request_stop() |
| Config editor | Non-atomic TOML write | #6 | tempfile+os.replace; tomli-w dependency |
| Config editor | Mid-session hot-reload | #5 | Apply on next session only; UI must communicate this |
| Trade history | Blocking file I/O in async route | #7 | asyncio.to_thread() + tail-read optimization |
| All async routes | asyncio.get_event_loop() deprecation | #11 | Use get_running_loop() everywhere |

---

## Dependency Gap: `tomli-w`

The config editor (Phase 8) requires TOML serialization. Python 3.11+ stdlib `tomllib` is read-only. `tomli-w` must be added to `pyproject.toml` before Phase 8 begins.

```
tomli-w>=1.0
```

This is the only new dependency required for the Admin UI milestone.

---

*Research grounded in MuTrade codebase as of 2026-04-12. Thread-safety analysis based on CPython behavior and known asyncio+threading integration patterns.*
