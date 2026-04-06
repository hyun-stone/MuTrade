# Architecture Patterns

**Domain:** Personal automated trailing-stop trading bot (KIS API, Korea)
**Researched:** 2026-04-06
**Confidence:** MEDIUM — Based on training knowledge of KIS API community patterns (August 2025 cutoff). No live web verification possible; verify token TTL and WebSocket protocol details against current KIS Developers portal before implementation.

---

## Recommended Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        MuTrade Process                          │
│                                                                 │
│  ┌──────────────┐     ┌──────────────┐     ┌───────────────┐   │
│  │  Config      │────▶│  Auth        │────▶│  KIS API      │   │
│  │  Loader      │     │  Manager     │     │  Client       │   │
│  └──────────────┘     └──────┬───────┘     └──────┬────────┘   │
│                              │                    │            │
│                              ▼                    ▼            │
│  ┌──────────────┐     ┌──────────────┐     ┌───────────────┐   │
│  │  Scheduler   │────▶│  Price       │◀────│  REST / WS    │   │
│  │  (market hrs)│     │  Monitor     │     │  Price Feed   │   │
│  └──────────────┘     └──────┬───────┘     └───────────────┘   │
│                              │                                  │
│                              ▼                                  │
│                       ┌──────────────┐                         │
│                       │  State       │                         │
│                       │  Manager     │◀──── state.json         │
│                       │  (고점 추적)  │                         │
│                       └──────┬───────┘                         │
│                              │                                  │
│                              ▼                                  │
│                       ┌──────────────┐                         │
│                       │  Trail Stop  │                         │
│                       │  Engine      │                         │
│                       └──────┬───────┘                         │
│                              │ trigger                         │
│                              ▼                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌───────────────┐   │
│  │  Notifier    │◀────│  Order       │────▶│  KIS API      │   │
│  │  (Kakao/etc) │     │  Executor    │     │  Order API    │   │
│  └──────────────┘     └──────────────┘     └───────────────┘   │
│          │                                                      │
│          ▼                                                      │
│  ┌──────────────┐                                               │
│  │  Logger      │────▶ trade_log.jsonl / app.log               │
│  └──────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘
```

---

## Component Boundaries

| Component | Responsibility | Reads From | Writes To | Calls |
|-----------|---------------|------------|-----------|-------|
| Config Loader | Parse `.env` / `config.yaml`; expose typed settings | `.env`, `config.yaml` | — | — |
| Auth Manager | Obtain OAuth 2.0 access token; refresh before expiry; cache to file | Config Loader | `token_cache.json` | KIS `/oauth2/tokenP` |
| KIS API Client | Thin HTTP wrapper over KIS REST endpoints; injects auth header | Auth Manager | — | KIS REST API |
| Price Feed | Deliver current price per symbol; choose polling or WebSocket | KIS API Client | — | KIS price endpoint or WS |
| Scheduler | Gate all activity to market hours (09:00–15:30 KST); trigger start/stop | system clock | — | Price Monitor |
| State Manager | Persist and load per-symbol high-water marks; survive restarts | `state.json` | `state.json` | — |
| Trailing Stop Engine | Compare current price to tracked high; update high; emit sell signal if -10% | Price Feed, State Manager | State Manager | Order Executor |
| Order Executor | Submit market-sell order via KIS API; confirm fill; record outcome | Trailing Stop Engine | Logger | KIS API Client |
| Notifier | Send sell notification to configured channel (KakaoTalk / Telegram) | Order Executor | — | External notification API |
| Logger | Write structured trade events and errors to append-only log file | all components | `trade_log.jsonl`, `app.log` | — |

---

## Data Flow

### 1. Startup

```
Config Loader
  └─▶ Auth Manager: load/validate token from cache
        └─▶ if expired or missing: POST /oauth2/tokenP → store new token
  └─▶ State Manager: load state.json → restore {symbol: high_price} map
  └─▶ Scheduler: check clock → if in market hours, start immediately
                              → else wait until 09:00 KST
```

### 2. Price Monitoring Loop (per tick)

```
Scheduler (09:00 KST)
  └─▶ Price Feed: for each monitored symbol
        └─▶ KIS API Client: GET current price
              └─▶ Trailing Stop Engine:
                    ├─ if price > stored_high → State Manager: update high
                    ├─ if (stored_high - price) / stored_high >= 0.10 → SELL SIGNAL
                    └─ else → no action

SELL SIGNAL
  └─▶ Order Executor: POST market-sell order
        └─▶ KIS API Client: confirm order receipt / fill status
        └─▶ State Manager: remove symbol from tracking (sold)
        └─▶ Notifier: send sell notification
        └─▶ Logger: append trade record
```

### 3. Token Lifecycle

```
Auth Manager (background)
  └─▶ KIS access token TTL: ~24 hours (verify on portal)
  └─▶ Strategy: check token age before each API call
        └─▶ if age > (TTL - 30min) → proactive refresh
        └─▶ if API returns 401 → immediate refresh + retry once
```

### 4. Shutdown / Market Close (15:30 KST)

```
Scheduler (15:30 KST)
  └─▶ Price Feed: stop polling
  └─▶ State Manager: flush state.json (final write)
  └─▶ Logger: write session-end record
```

---

## KIS API Authentication Flow (Detail)

**Confidence:** MEDIUM — pattern is stable in community usage; verify exact endpoint paths against KIS Developers portal.

```
POST https://openapi.koreainvestment.com:9443/oauth2/tokenP
Content-Type: application/json

{
  "grant_type": "client_credentials",
  "appkey": "<APP_KEY>",
  "appsecret": "<APP_SECRET>"
}

Response:
{
  "access_token": "...",
  "token_type": "Bearer",
  "expires_in": 86400,   ← 24 hours (production)
  "access_token_token_expired": "2026-04-07 09:00:00"
}
```

**Token cache strategy:**
- Store `{access_token, expires_at}` in `token_cache.json` (gitignored)
- On process start, load cache; if `expires_at - now > 30min` → reuse
- Token revocation endpoint exists; call on clean shutdown (optional)
- Paper trading (모의투자) uses a different base URL and separate credentials — keep as a config flag

---

## Price Feed: Polling vs WebSocket

**Recommended for v1: polling with 3–5 second interval.**

| Approach | Pros | Cons | Use When |
|----------|------|------|----------|
| REST polling (3–5s) | Simple, no connection management, trivially restartable | Slightly stale price; API rate limits apply | v1, ≤ ~10 symbols |
| KIS WebSocket (실시간 시세) | True real-time, lower latency | Persistent connection management, reconnect logic, more complex | v2+ or if latency matters |

**KIS rate limit context (MEDIUM confidence):** KIS limits REST calls per second per account. For personal use monitoring 5–20 symbols, a 3-second interval per symbol with a small sleep between calls stays safely within limits. WebSocket is available for real-time quotes but requires a separate WebSocket approval token.

**Polling loop pattern:**
```python
while market_is_open():
    for symbol in monitored_symbols:
        price = kis_client.get_current_price(symbol)
        engine.on_price(symbol, price)
        time.sleep(0.5)   # spread API calls
    time.sleep(3)         # outer loop cadence
```

---

## State Management: 고점 추적 Persistence

**Problem:** If the process crashes or is restarted, tracked highs are lost. Without persistence, the bot restarts tracking from current price, potentially missing a valid sell signal.

**Solution: append-write JSON file (`state.json`)**

```json
{
  "005930": {
    "high_price": 78500,
    "high_updated_at": "2026-04-06T10:23:11+09:00",
    "tracking_since": "2026-04-06T09:00:00+09:00"
  },
  "035720": {
    "high_price": 62000,
    "high_updated_at": "2026-04-06T11:05:44+09:00",
    "tracking_since": "2026-04-06T09:00:00+09:00"
  }
}
```

**Write strategy:** Write after every high update (atomic write via temp-file rename to avoid corruption). Do not write on every tick — only when high changes or on shutdown.

**Manual override:** `config.yaml` allows setting `initial_high` per symbol so users can seed a historical high on first run.

**Cross-day behavior:** Decide in config whether to reset highs each morning or persist across days. Resetting at 09:00 KST each day is the safer default for trailing stop semantics.

---

## Order Execution Flow

```
Trailing Stop Engine emits: SellSignal(symbol, current_price, high_price, drop_pct)
  │
  ▼
Order Executor:
  1. Guard: check symbol not already in "sell_in_progress" set (idempotency)
  2. Mark symbol as "sell_in_progress"
  3. Fetch current holding quantity from KIS holdings API
  4. If quantity == 0 → already sold, log warning, remove from tracking, return
  5. POST market-sell order (전량 매도)
  6. Receive order number (주문번호)
  7. Poll order status until FILLED or FAILED (up to N retries, ~10s timeout)
  8. On FILLED: log, notify, remove from State Manager
  9. On FAILED: log error, notify, clear "sell_in_progress", allow retry on next tick
```

**KIS market-sell endpoint (MEDIUM confidence):**
```
POST /uapi/domestic-stock/v1/trading/order-cash
tr_id: TTTC0801U (production sell) / VTTC0801U (paper trading sell)
```

---

## Error Handling and Retry Strategy

| Error Type | Detection | Action |
|------------|-----------|--------|
| 401 Unauthorized | HTTP 401 from any KIS call | Refresh token once, retry request; if still 401 → halt and alert |
| Rate limit exceeded | HTTP 429 or KIS error code | Exponential backoff (1s → 2s → 4s), max 3 retries |
| Network timeout | `requests.Timeout` | Retry up to 3 times with 2s delay; after 3 failures → log and continue next tick |
| Order failed (KIS error) | KIS `rt_cd != "0"` | Log KIS error code + message; notify user; do NOT retry immediately (manual review needed) |
| Price fetch failure | Exception or bad response | Log warning; skip symbol this tick; do NOT sell on stale data |
| State file corrupt | JSON parse error | Log critical; fall back to empty state (re-initialize highs from current prices); alert user |
| Process crash (SIGKILL) | — | State file survives because of atomic writes; on restart, load last known highs |

**Design principle:** Never execute a sell order on uncertain data. If price fetch fails, skip. If order status is ambiguous, log and alert rather than retry blindly.

---

## Notification Integration Points

**Events that trigger notifications:**

| Event | Severity | Content |
|-------|----------|---------|
| Sell order executed | CRITICAL | Symbol, sell price, quantity, drop %, estimated P&L |
| Sell order failed | HIGH | Symbol, KIS error code, message |
| Token refresh failed | HIGH | "Bot cannot authenticate, manual intervention needed" |
| Bot started / stopped | INFO | Session start/end, monitored symbols list |
| Symbol removed from tracking (sold elsewhere) | INFO | Symbol, reason |

**Recommended channel: KakaoTalk (카카오톡 알림톡)**
- KakaoTalk REST API (카카오 알림톡) works for personal use but requires business registration for template messages. For purely personal use, the KakaoTalk [나에게 보내기] channel via the KakaoTalk Developers REST API is simpler and has no template requirement.
- **Fallback:** Telegram Bot API is easier to set up programmatically, has no template restrictions, and is the recommended default for personal bots.

**Notifier is a pluggable interface:** Define a `Notifier` abstract base class; provide `KakaoNotifier` and `TelegramNotifier` implementations. Config selects which one.

---

## Scheduling for Market Hours

**KST market hours:** 09:00–15:30 (Korea Standard Time, UTC+9)

**Implementation pattern:**
```python
import zoneinfo
from datetime import datetime, time

KST = zoneinfo.ZoneInfo("Asia/Seoul")
MARKET_OPEN = time(9, 0)
MARKET_CLOSE = time(15, 30)

def is_market_open() -> bool:
    now = datetime.now(KST)
    if now.weekday() >= 5:   # Saturday=5, Sunday=6
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE
```

**Scheduling strategy for v1: simple sleep-loop (no cron, no celery)**
- Process starts at any time; Scheduler blocks until 09:00 if pre-market
- After 15:30, Scheduler calls shutdown; process exits (or sleeps until next day)
- For persistent operation, use systemd service or a simple cron to start the process at 08:55 KST daily

**Public holidays:** KRX (Korea Exchange) has ~13 public holidays per year when market is closed. v1: document as manual skip (user does not run the bot). v2: query KRX holiday calendar API or maintain a local holiday list.

---

## Suggested Build Order

Dependencies flow bottom-up: each layer depends on the one below it.

```
Layer 0 (Foundation)
  └─▶ Config Loader        ← everything else reads config
  └─▶ Logger               ← everything else writes logs

Layer 1 (KIS Connectivity)
  └─▶ Auth Manager         ← depends on: Config Loader, Logger
  └─▶ KIS API Client       ← depends on: Auth Manager, Logger

Layer 2 (Data)
  └─▶ Price Feed (REST polling) ← depends on: KIS API Client
  └─▶ State Manager        ← depends on: Config Loader, Logger

Layer 3 (Core Logic)
  └─▶ Trailing Stop Engine ← depends on: Price Feed, State Manager

Layer 4 (Execution)
  └─▶ Order Executor       ← depends on: KIS API Client, State Manager, Logger
  └─▶ Notifier             ← depends on: Config Loader, Logger

Layer 5 (Orchestration)
  └─▶ Scheduler            ← depends on: all above layers
  └─▶ Main entrypoint      ← wires everything together
```

**Recommended build sequence for phased delivery:**

| Phase | Components | Deliverable | Testable Without |
|-------|------------|-------------|-----------------|
| 1 | Config Loader + Logger + Auth Manager | Can authenticate with KIS API | Real orders |
| 2 | KIS API Client + Price Feed | Can fetch live prices | Real orders |
| 3 | State Manager + Trailing Stop Engine | Core logic with unit tests on mock prices | KIS API at all |
| 4 | Order Executor | End-to-end in paper trading (모의투자) | Production keys |
| 5 | Scheduler | Full market-hours gate | — |
| 6 | Notifier | Sell notifications delivered | — |

---

## Anti-Patterns to Avoid

### Anti-Pattern 1: Re-issuing Token on Every Request
**What:** Calling `/oauth2/tokenP` before each API call.
**Why bad:** Rate-limited; token TTL is 24h — unnecessary calls waste quota and may trigger account flags.
**Instead:** Cache token; check expiry proactively; refresh only when needed.

### Anti-Pattern 2: Selling on Failed Price Fetch
**What:** Treating a price fetch exception as "price dropped to zero" and triggering sell.
**Why bad:** Network blip causes all positions to be sold instantly.
**Instead:** On price fetch failure, log and skip the symbol for this tick; require N consecutive failures before alerting.

### Anti-Pattern 3: In-Memory-Only High-Water Marks
**What:** Storing `{symbol: high}` only in a dict, no persistence.
**Why bad:** Any restart — intentional or crash — resets tracking from current price, potentially deferring a valid trailing stop trigger.
**Instead:** Write state to file on every high update using atomic rename.

### Anti-Pattern 4: Hardcoding KST as UTC+9 Offset
**What:** `datetime.now() + timedelta(hours=9)` for KST.
**Why bad:** Breaks if system timezone changes; does not handle edge cases cleanly.
**Instead:** Use `zoneinfo.ZoneInfo("Asia/Seoul")` (Python 3.9+, stdlib).

### Anti-Pattern 5: Polling Too Fast
**What:** Fetching price every 0.5 seconds for many symbols.
**Why bad:** KIS API has per-account rate limits (estimated ~20 calls/second for REST). Exceeding limits causes 429s or temporary blocks.
**Instead:** Spread calls with `time.sleep(0.5)` between symbols and a 3s outer loop. For high-frequency needs, switch to WebSocket.

### Anti-Pattern 6: Single Monolithic Script
**What:** All logic in one `main.py` with no module boundaries.
**Why bad:** Impossible to unit-test trailing stop logic without KIS API. Auth bugs mix with business logic bugs.
**Instead:** Follow the layer structure above; each component is independently importable and testable.

---

## Scalability Considerations

This bot is intentionally personal-scale. Scalability is not a goal for v1.

| Concern | At 5–20 symbols (target) | At 100+ symbols | Notes |
|---------|--------------------------|-----------------|-------|
| Price polling | REST polling viable | Switch to WebSocket subscription | KIS WS supports multi-symbol subscription |
| State file | Single JSON file, fine | Still fine for personal use | |
| Order concurrency | Sequential is fine | Would need async order queue | Multiple simultaneous sell signals rare |
| API rate limits | 3–5s polling loop is safe | Need careful throttling | |

---

## Sources

**Confidence notes:** All findings are from training data (knowledge cutoff August 2025) covering the KIS Developers community (apiportal.koreainvestment.com), GitHub repositories of open-source KIS Python wrappers (e.g., `python-kis`, `mojito`), and Korean developer blog posts. Web verification was not possible in this session.

- KIS Developers portal: https://apiportal.koreainvestment.com (verify current endpoint paths and token TTL)
- KIS Python community wrapper `mojito`: https://github.com/changwookjun/mojito (reference implementation patterns)
- KIS Python wrapper `python-kis`: https://github.com/Soju06/python-kis (community-maintained, active as of training cutoff)
- KakaoTalk Developers (나에게 보내기 API): https://developers.kakao.com/docs/latest/ko/kakaotalk-channel/common
- Telegram Bot API: https://core.telegram.org/bots/api

**Verify before implementing:**
- Exact OAuth2 endpoint URL and token TTL (may differ between production and paper trading)
- WebSocket approval process and endpoint (separate auth token required)
- Current REST rate limits per account type
- KIS `tr_id` values for sell orders (production vs paper trading differ)
