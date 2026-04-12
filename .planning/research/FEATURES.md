# Feature Landscape — MuTrade Admin UI (v1.1)

**Domain:** Admin dashboard for algorithmic/automated trading bot (FastAPI layer on Python trading bot)
**Researched:** 2026-04-12
**Scope:** FastAPI-based web UI layered onto existing Python trading bot (v1.0 shipped)

---

## Existing Foundation (What's Already Built)

Before cataloguing what to build, the dependencies that constrain each feature:

| Component | Relevant State |
|-----------|----------------|
| `BotStateHub` | Thread-safe bridge (APScheduler thread ↔ FastAPI asyncio). `push_snapshot(states)`, `get_snapshot()`, `wait_for_change()`, `request_stop()`, `clear_stop()`, `is_running()`, `set_running()` — all already implemented. |
| `TrailingStopEngine.states` | Returns `dict[str, SymbolState]` — fields: `code`, `peak_price`, `warm`. **Missing:** `current_price`, `drop_pct`, `sell_pending` flag — these are NOT stored in SymbolState. |
| `hub.push_snapshot()` only serializes | `code`, `peak_price`, `warm` — current_price is absent. Scheduler calls push_snapshot AFTER tick, not after poll_prices. |
| `OrderExecutor._pending` | In-memory `set[str]` of codes with pending sell orders. Not exposed to hub or any external observer. |
| `AppConfig` + `load_config()` | TOML-based; frozen dataclasses. No write path. Config save requires new code. |
| Log file | `logs/mutrade.log`, `[TRADE]` marker in loguru lines. Format is a known fixed string (see `order_executor.py` line 106–112). |
| FastAPI app | `create_app()` in `admin/app.py`. Only `/health` endpoint exists. `engine` and `config` are already injected via `kwargs` in `main.py` but not yet used in routes. |

---

## Category 1: Real-Time Position Monitoring UI

### Table Stakes

Features that make the dashboard useful at all. Without these it is just a health check page.

| Feature | Why Expected | Complexity | Dependency Gap |
|---------|--------------|------------|----------------|
| Per-symbol row: code + name | Baseline identification | Low | `config.symbols` already accessible via injected `config` kwarg |
| Per-symbol current price | Core monitoring data — "is this symbol dangerous right now?" | Low-Medium | **Gap:** `current_price` is not in hub snapshot. Must be added to `push_snapshot()` call in scheduler. |
| Per-symbol peak price | Trailing stop anchor — essential to understand the reference point | Low | Already in hub snapshot (`peak_price`) |
| Per-symbol drop_pct (%) | The key signal: "how close is this to triggering?" | Low | **Gap:** Must be computed server-side from current/peak, or added to snapshot alongside current_price |
| SELL_PENDING indicator | Prevents confusion when a sell order is in-flight | Low | **Gap:** `OrderExecutor._pending` is private set; not exposed to hub. Requires either exposing via hub or injecting executor into routes. |
| Data freshness indicator (last updated timestamp) | Bot polls every 3–5s; UI must show when data is stale (e.g., bot not running) | Low | Add `updated_at` timestamp to snapshot in push_snapshot() |
| Bot running status badge | Is the bot active right now? | Low | `hub.is_running()` already works |

### Differentiators

Nice-to-have features that make monitoring better but are not required for v1.1.

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Color-coded drop_pct thresholds (green/yellow/red) | Instant visual danger level without reading numbers | Low | Pure frontend CSS — no backend work |
| Auto-refresh via SSE or WebSocket | Real-time push instead of manual page refresh | Medium | `hub.wait_for_change()` already exists for this purpose — clean path via SSE or WebSocket |
| "warm" indicator (initializing vs tracking) | Prevents confusion during first poll interval | Low | `warm` field already in snapshot |
| Market session status (open/closed, next open) | Context for why drop_pct is not changing | Low-Medium | Derive from APScheduler next_run_time or time-based logic |
| Threshold per symbol display | Reminds user when symbols have custom stop levels | Low | Available from config.symbols |

### Anti-Features

| Anti-Feature | Why Avoid |
|--------------|-----------|
| Price chart / sparkline history | Requires storing price history — no storage layer exists. Adds complexity disproportionate to v1.1 scope. |
| Portfolio P&L calculation | Requires purchase price data — not tracked anywhere in the bot. Out of scope. |
| Multiple account views | KIS single account. No multi-account need. |
| WebSocket-only real-time (no fallback) | `hub.wait_for_change()` queue has `maxsize=1` — drops updates if consumer is slow. Polling fallback (`GET /status` on interval) is safer for v1.1. |

### Implementation Notes

The snapshot gap is the primary blocker. `push_snapshot()` in `hub.py` serializes only `code`, `peak_price`, `warm`. For the monitoring dashboard to work, the scheduler must pass `current_price` (and optionally `drop_pct`) into the snapshot. Two options:

- **Option A (recommended):** Modify `push_snapshot()` call in `scheduler.py` to include current prices dict alongside engine states. Pass `prices` into the `run_session()` closure and merge into hub push.
- **Option B:** Add a separate `push_prices(prices: dict)` method to hub and merge in `get_snapshot()`.

Option A is simpler — one call site change in scheduler, no hub API expansion.

---

## Category 2: Bot Start/Stop Controls with Safety Guardrails

### Table Stakes

| Feature | Why Expected | Complexity | Dependency Gap |
|---------|--------------|------------|----------------|
| Stop bot button | Primary control — halt polling mid-session without killing the process | Low | `hub.request_stop()` + `hub.clear_stop()` already implemented. Route just needs to call it. |
| Bot status display (running/stopped) | Know current state before issuing a command | Low | `hub.is_running()` already works |
| Dry-run mode display (read-only) | Know whether real orders can fire | Low | `settings.dry_run` is not currently exposed to hub or routes — requires injecting Settings into the route or exposing via hub |
| Prevent double-stop (idempotency) | Clicking stop when already stopped should not error | Low | Check `hub.is_running()` before calling `request_stop()` |

### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| "Start bot manually" button (trigger session outside cron) | Useful for testing outside market hours, or when cron missed | Medium | APScheduler `scheduler.get_job("market_poll").modify(next_run_time=now)` — feasible but requires exposing scheduler to routes |
| Dry-run toggle (write) | Switch between dry-run and live without restarting process | Medium | `settings.dry_run` comes from env at startup. Runtime toggle requires mutable state on both `engine._dry_run` and `executor._dry_run`. Non-trivial: both are set in `__init__`. Either expose setters or track in hub. |
| Stop confirmation dialog | Prevents accidental clicks — important when bot is in live mode | Low | Pure frontend |
| Stop reason logged | "Bot stopped by admin at HH:MM" in logs | Low | One `logger.info()` call in the stop endpoint |

### Anti-Features

| Anti-Feature | Why Avoid |
|--------------|-----------|
| Emergency stop with position liquidation | Bot only sells on signal. Force-liquidating all positions is high-risk for a personal tool. Out of scope. |
| Scheduled restart UI | APScheduler already handles this via CronTrigger. Adding a UI restart scheduler duplicates logic. |
| Multi-instance control | Single-process personal bot. No multi-instance scenario. |

### Safety Guardrails (Critical)

These must be built-in, not optional:

1. **Stop during live sell flow:** `request_stop()` is checked at the top of the poll loop, not inside `OrderExecutor`. If a sell order is SELL_PENDING when stop is triggered, the dangling order remains in KIS — KIS will handle it, but the UI should warn the user when stopping with pending orders.

2. **Dry-run toggle write path:** If implemented, the toggle must update BOTH `engine._dry_run` and `executor._dry_run` atomically. Missing one causes silent inconsistency (engine signals dry-run, executor fires live order or vice versa).

3. **No process restart on stop:** `request_stop()` only signals the poll loop to exit. The scheduler and uvicorn remain running. This is correct behavior — the UI must clarify ("Monitoring paused. Server still running.").

---

## Category 3: Trade History Display from Log Files

### Table Stakes

| Feature | Why Expected | Complexity | Dependency Gap |
|---------|--------------|------------|----------------|
| List of completed trades (code, name, qty, price, timestamp) | Core audit trail for a trading bot | Medium | `[TRADE]` log lines exist but require parsing. Log format is known and fixed. |
| Timestamp of trade | When did the sell execute? | Low | Loguru line format includes timestamp as first field |
| Dry-run vs live distinction | Did this actually execute or was it simulated? | Low | `[DRY-RUN]` / `[LIVE]` prefix is in the log lines |

### Log Format

The `[TRADE]` line format from `order_executor.py` (line 106–112):

```
YYYY-MM-DD HH:mm:ss | INFO     | module:function | [TRADE] 매도 주문 제출: {code} ({name}) qty={qty} current_price={price} peak={peak} drop={drop:.2%} threshold={threshold:.1%} order={order_number}
```

This is a fixed, parseable format. A single regex capturing named groups covers all fields. No external parser needed.

### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Pagination or limit | Log files can grow large; avoid loading all 30 days at once | Low | Read last N lines or filter by date range |
| Computed P&L column | (sell price - peak) × qty shows actual loss prevented | Low | All values available in the log line — pure computation |
| Export as CSV | Useful for personal finance records | Low-Medium | Stream log lines filtered by `[TRADE]` and format as CSV |
| Filter by date range | "Show this week's trades" | Medium | Requires parsing timestamp from each line before filtering |

### Anti-Features

| Anti-Feature | Why Avoid |
|--------------|-----------|
| Real-time log streaming (tail -f equivalent) | Overkill for v1.1. The `[TRADE]` history is low-frequency. Full log streaming exposes internal debug data. |
| Database migration of log history | The `[TRADE]` grep approach was a deliberate v1.0 decision ("no DB for v1"). Reversing it for v1.1 is scope creep. |
| Edit or delete trade records | Log files are immutable audit trails by design. |

### Implementation Notes

The log parse endpoint reads `logs/mutrade.log`. Path is hardcoded in `main.py`. For routes, use a constant or inject from Settings.

The only risk: rotated log files. Loguru uses `rotation="10 MB"` with `retention="30 days"`. Rotated files are named `mutrade.log.1`, `mutrade.log.2`, etc. (loguru default naming). For v1.1, reading only the active file is acceptable. Document that rotated files are not included.

---

## Category 4: Live Config Editing with Validation

### Table Stakes

| Feature | Why Expected | Complexity | Dependency Gap |
|---------|--------------|------------|----------------|
| Display current config.toml contents | See what is configured without SSH or file access | Low | `load_config()` returns `AppConfig`; or read raw TOML text directly. |
| Edit symbols list (add/remove/modify threshold) | The primary config users need to change | Medium | No write path exists. `AppConfig` is a frozen dataclass. `config.toml` file must be written directly. |
| Edit poll_interval and default_threshold | Secondary config users may adjust | Low | Same write path as symbols |
| Validation before save | Prevent saving invalid config (empty symbols list, invalid code format, threshold out of range) | Medium | `load_config()` validation already exists — reuse by loading from new content before writing |
| Confirmation of save success | Config written successfully | Low | Return success/error in API response |

### Differentiators

| Feature | Value | Complexity | Notes |
|---------|-------|------------|-------|
| Raw TOML textarea edit | Power users can edit the full TOML text directly | Low | Simpler than a structured form; validation still applies |
| Structured form per symbol | User-friendly add/remove symbol UI | Medium-High | More frontend work; requires form generation from config schema |
| Schema validation error display | Show which field failed validation with the reason | Low | Pydantic or `load_config()` exception message already contains field name |
| Backup before save | Rename `config.toml` to `config.toml.bak` before writing | Low | One `shutil.copy()` call — strongly recommended |
| "Changes apply at next session" notice | Prevents confusion when config changes do not affect running bot | Low | Static text in UI |

### Anti-Features

| Anti-Feature | Why Avoid |
|--------------|-----------|
| Live reload / hot-apply config to running bot | `TrailingStopEngine` holds in-memory `SymbolState` per symbol. Adding or removing symbols mid-session is a state management problem that risks missed sell signals. Config changes should apply at next session start. |
| .env / secrets editing via UI | Never expose API keys through a web endpoint. Explicit CLAUDE.md constraint. |
| Config version history / diff | Git handles this if the user wants it. Overkill for v1.1. |

### Implementation Notes

The write path for config.toml must handle two failure modes:

1. **Validation failure (caught before write):** Parse new content with `load_config()` via `io.StringIO` or a temp file — if it raises, return HTTP 400 with the error message.
2. **Write failure (disk error):** Atomic write pattern — write to `config.toml.tmp`, then `os.replace("config.toml.tmp", "config.toml")` to prevent partial writes corrupting the active config.

The "config takes effect on next session" behavior must be clearly communicated. A response body note — "Changes saved. Will apply at next market session (09:00 KST)." — is sufficient for v1.1.

---

## Feature Dependency Map

```
Category 1 (Monitoring):
  requires -> push_snapshot() extended with current_price (scheduler.py change)
  requires -> OrderExecutor._pending exposed via hub or executor injected into routes
  requires -> GET /status endpoint (returns hub.get_snapshot())
  optional -> SSE or WebSocket endpoint (uses hub.wait_for_change())

Category 2 (Bot Control):
  requires -> POST /bot/stop calling hub.request_stop() (hub already ready)
  requires -> GET /bot/status returning hub.is_running() (hub already ready)
  optional -> scheduler exposure for manual trigger
  optional -> engine + executor setters for dry_run write toggle

Category 3 (Trade History):
  requires -> log file read access from FastAPI route
  requires -> [TRADE] line parser (one regex, ~5 lines of code)
  requires -> GET /trades endpoint

Category 4 (Config Edit):
  requires -> GET /config (read raw TOML text or structured AppConfig)
  requires -> POST /config (validate + atomic write)
  requires -> load_config() reuse for validation
```

No circular dependencies. Categories 1 and 2 are most tightly coupled to the existing engine (snapshot gap, SELL_PENDING exposure). Categories 3 and 4 are largely independent file operations.

---

## MVP Recommendation

Prioritize in this order:

1. **Category 1 — Monitoring (table stakes only):** Fix snapshot gap first (add current_price to push_snapshot via scheduler change), then implement GET /status endpoint and a polling-based HTML page. Delivers the core value immediately.

2. **Category 2 — Bot Control (table stakes only):** POST /bot/stop and GET /bot/status using existing hub methods. Dry-run read-only display. No write toggle for v1.1.

3. **Category 3 — Trade History (table stakes only):** GET /trades endpoint reading logs/mutrade.log. Regex parser. Simple list response. No pagination needed for v1.1 (30-day retention, personal bot with low trade frequency).

4. **Category 4 — Config Edit:** GET /config (raw TOML text display) + POST /config (validate + atomic write). Raw textarea, not structured form. "Changes apply at next session" notice.

Defer to v1.2+:
- SSE/WebSocket real-time push (polling every 5s from frontend is sufficient for v1.1)
- Manual bot start trigger (adds scheduler coupling complexity)
- Dry-run write toggle (requires engine + executor setters; atomicity risk)
- Config hot-reload (too risky for mid-session state)

---

## Complexity Summary

| Category | Backend Complexity | Frontend Complexity | Primary Risk |
|----------|--------------------|---------------------|--------------|
| Category 1 — Monitoring | Medium (snapshot gap to fix) | Low (polling table) | `current_price` not in snapshot; `SELL_PENDING` not exposed |
| Category 2 — Bot Control | Low (hub already ready) | Low | Stop during SELL_PENDING leaves dangling order — needs UX warning |
| Category 3 — Trade History | Low (file read + regex) | Low | Log rotation — rotated files not included in v1.1 |
| Category 4 — Config Edit | Low-Medium (atomic write + validation) | Low (textarea) | Config changes will not hot-reload — must communicate clearly |
