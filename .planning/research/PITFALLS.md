# Domain Pitfalls: KIS API Korean Automated Trading Bot

**Domain:** Personal automated stock trading bot (KIS API, trailing stop, Korean market)
**Researched:** 2026-04-06
**Confidence note:** External search tools unavailable. All findings are from training data (KIS Developers documentation, Python KIS community repos, and known Korean fintech developer patterns up to mid-2025). Confidence levels reflect this.

---

## Critical Pitfalls

Mistakes that cause silent losses, incorrect sells, or complete bot failure.

---

### Pitfall 1: KIS API Rate Limit Violations Causing Silent Throttling

**Confidence:** HIGH (well-documented in KIS Developers portal and community)

**What goes wrong:**
KIS API enforces per-second rate limits. For the real-account REST API, the limit is approximately 20 requests/second for most endpoints (현재가 조회, 잔고 조회, 주문 등). In mock (모의) accounts the limit is lower — often 5 req/sec. If you exceed the limit, the API returns HTTP 429 or an error code like `EGW00201` ("초당 거래건수를 초과하였습니다"). Critically, some rate-limit responses return HTTP 200 with an error body, so naive success-checking on HTTP status alone misses these errors entirely.

**Why it happens:**
Developers polling multiple tickers in a tight loop without any throttle. A bot monitoring 10 tickers at 1-second intervals fires 10 requests/second minimum — already at the limit before accounting for order submission and balance queries.

**Consequences:**
- Price data silently not updated; bot operates on stale prices
- Trailing stop high-water mark never updates (고점이 갱신되지 않음)
- Sell order may never fire, or fires on wrong data
- Multiple tickers may work fine in dev (small watchlist) but fail in production

**Prevention:**
- Enforce a rate limiter (e.g., `ratelimit` library or `asyncio` semaphore) at 15 req/sec maximum — leave buffer below the documented limit
- Always check response body for error codes, not just HTTP status
- For a small watchlist (< 10 tickers), a 1-second polling interval with sequential requests is safe; for larger lists, use a queue with inter-request delay
- Consider using the WebSocket (실시간 체결가 스트리밍) for price data to eliminate polling overhead entirely

**Warning signs:**
- Log shows consistent HTTP 200 but prices stop updating
- Error code `EGW00201` or `EGW00202` in response body
- Sell never triggers despite price clearly below threshold

**Phase:** Address in Phase 1 (API integration layer) before any polling loop is written.

---

### Pitfall 2: Access Token Expiry Causing Silent Bot Freeze

**Confidence:** HIGH

**What goes wrong:**
KIS OAuth2 access tokens expire after 24 hours. A bot started before market open (08:50) and left running continuously will have its token expire the next day — mid-session if not handled. When the token expires, all API calls return `EGW00123` or similar auth errors. If the bot does not re-authenticate automatically, it silently stops monitoring prices and never sells, even as prices fall through the trailing stop threshold.

The additional trap: the token issuance endpoint (`/oauth2/tokenP`) is itself rate-limited to approximately 1 request/minute. Calling it on every request (common mistake when naively "refreshing on failure") causes the bot to get locked out of token renewal.

**Why it happens:**
- Developers test for a few hours, never hit the 24h expiry in dev
- Token stored in memory only; restart re-authenticates but long-running bots don't restart daily
- Retry-on-failure logic triggers repeated token requests, hitting the issuance rate limit

**Consequences:**
- Bot becomes completely inoperative mid-session without any alert
- No sells execute; positions ride losses down without the trailing stop firing

**Prevention:**
- Store token with `expires_at = issued_at + 86400 seconds` and check before every request batch
- Proactively refresh at a scheduled time (e.g., 08:30 KST daily, before market open)
- Cache the token to disk/file (not just memory) so restarts don't issue unnecessary new tokens
- Implement exponential backoff with a 60-second minimum retry for token issuance failures
- Send an alert (KakaoTalk or log) when token refresh fails so the operator can intervene

**Warning signs:**
- Sudden burst of `EGW00123` / `EGW00124` errors after ~24h of operation
- All price queries returning auth errors simultaneously
- Bot log shows requests sent but no price updates

**Phase:** Address in Phase 1 (authentication module). This is the single most common long-running bot failure.

---

### Pitfall 3: Market Hours Edge Cases — 동시호가 and 장외 시간 Not Handled

**Confidence:** HIGH

**What goes wrong:**
KSX market structure has multiple distinct time periods, each with different behavior:

| Period | Time (KST) | Behavior |
|--------|-----------|----------|
| 장전 동시호가 | 08:00–09:00 | Order matching queued; no real-time execution |
| 정규 시장 | 09:00–15:20 | Normal continuous trading |
| 장후 동시호가 | 15:20–15:30 | Closing auction; prices can move significantly |
| 시간외 단일가 | 15:30–16:00 | After-hours; limited liquidity |
| 시간외 종가 | 16:00–18:00 | Fixed at closing price |

Common mistakes:
1. Bot starts at 08:50, receives quote prices from 동시호가 which are indicative/expected prices, not real prices — trailing stop logic runs on phantom data
2. Bot treats 15:20–15:30 as normal; a market order submitted during 장후 동시호가 may execute at the auction clearing price (potentially significantly different from expected)
3. Bot doesn't stop at 15:30 and submits orders during 시간외 단일가 when market order semantics differ
4. No휴장일 (공휴일, 임시 휴장) handling — bot runs on a non-trading day and makes API calls all day, burning rate limit quota and potentially misinterpreting "no price change" as a flat market

**Why it happens:**
Developers test on weekdays, don't encounter edge cases; simple `09:00 <= now <= 15:30` check used without per-period logic.

**Consequences:**
- Trailing stop fires on 동시호가 indicative prices, executing a real sell based on pre-open phantom data
- Market order during 장후 동시호가 executes at unexpected auction price
- Crash or unexpected behavior on holidays

**Prevention:**
- Use `09:00 <= now < 15:20` for the active monitoring window (conservative: stop 10 minutes before close)
- Explicitly check KRX holiday calendar before starting; the `pandas_market_calendars` library has `XKRX` support or maintain a local holiday list
- Do not issue market orders during 동시호가 periods unless intentional
- Add a startup check: if current time is outside `08:00–16:00 KST`, log a warning and idle

**Warning signs:**
- Bot places sells at 08:55
- Sells executing at prices dramatically different from last seen quote
- Bot running on a Saturday or public holiday

**Phase:** Address in Phase 1 (scheduler/time guard). Must be solved before any live order logic.

---

### Pitfall 4: 고점(High-Water Mark) Lost on Process Restart

**Confidence:** HIGH

**What goes wrong:**
The trailing stop logic depends on tracking the highest price seen since monitoring began. If this value is stored only in memory (e.g., a Python dict), any process restart — crash, server reboot, manual restart — resets the high-water mark to the current price. After restart, the new "peak" is the current (already lower) price. The trailing stop threshold resets downward. A stock that has fallen 8% from its true peak will appear to be at its new "peak" post-restart, and requires an additional 10% fall from that lower level before triggering — effectively widening the stop-loss silently.

**Why it happens:**
The simplest implementation tracks peak in memory. Developers test within a single session and never restart. On the first real crash or reboot, peak data is lost.

**Consequences:**
- True loss protection disabled after any restart
- Bot may hold a position through a much larger loss than intended
- User believes the trailing stop is protecting them; it is not

**Prevention:**
- Persist the high-water mark to disk (JSON file, SQLite) after every update
- On startup, load persisted peaks; only reset to current price if no persisted value exists for a ticker
- Log clearly at startup: "Loaded persisted peak for 삼성전자: 82,000 KRW (saved 2026-04-05 14:23)"
- Consider: persist peak with a timestamp and warn if the saved peak is more than 1 trading day old (user may have sold the position manually)
- Allow manual override via config: `initial_peak` per ticker for cases where user knows the true peak

**Warning signs:**
- Peak value in logs resets to current price every time bot starts
- Peak equals the price at startup time, not the highest observed price
- Sells triggering at unexpectedly low prices after a restart

**Phase:** Address in Phase 2 (trailing stop engine). Core correctness requirement.

---

### Pitfall 5: Order Failure and Partial Fill Not Handled

**Confidence:** HIGH

**What goes wrong:**
KIS API market order submission (`/uapi/domestic-stock/v1/trading/order-cash`) returns success for order placement, not for order execution. Scenarios that cause failures:

1. **Insufficient balance/shares:** If the bot thinks you hold 100 shares but you manually sold 50 earlier that day, the sell order for 100 shares is rejected
2. **Circuit breaker / 매매 정지:** Individual stocks can be halted mid-session; market order submission returns an error code
3. **Partial fill:** While rare for market orders on liquid KSX stocks, illiquid small-cap (소형주) stocks can partially fill. Bot marks position as "sold" but shares remain
4. **Duplicate order:** On network timeout, the bot retries an order that already succeeded — submitting two sell orders for 100% of the position each; second order fails but the retry logic may not handle this gracefully

**Why it happens:**
Developers test with liquid large-cap stocks; error handling is added as an afterthought. The simple path (place order → assume filled) works 99% of the time, making the failure cases invisible in testing.

**Consequences:**
- Partial fill leaves residual position that never triggers the trailing stop again (state machine stuck)
- Duplicate order attempt on retry causes confusion about position status
- Bot may attempt to sell a stock that has been halted — burning retries with no resolution

**Prevention:**
- After submitting a sell order, query order status (`/uapi/domestic-stock/v1/trading/inquire-daily-ccld`) to confirm fill
- On partial fill: either (a) submit remainder immediately, or (b) alert operator and pause that ticker
- Track a per-ticker `sell_submitted` state flag to prevent duplicate orders on retry
- Handle 매매 정지 error codes explicitly: pause that ticker, alert operator, do not retry automatically
- On startup, reconcile local state against actual holdings from the API

**Warning signs:**
- Order submission succeeds but position still shows in balance query
- Log shows sell submitted but no subsequent fill confirmation
- Sell order returned error code related to 매매 정지 or 수량 부족

**Phase:** Address in Phase 3 (order execution layer). Required before production use.

---

### Pitfall 6: Network Interruption Causes Sell Order Loss

**Confidence:** HIGH

**What goes wrong:**
A sell condition is triggered. The bot calls the order API. A network interruption occurs mid-request. The bot sees a connection error and assumes the order failed — but the order may have been received and queued by KIS servers before the connection dropped. On retry, the bot submits a duplicate sell order.

The inverse failure: the network drops before the API call is made. The bot's retry logic does not fire (e.g., exception swallowed, state not updated). Price continues to fall. No sell happens.

**Why it happens:**
Network error handling is an afterthought. Developers code the happy path: `try: place_order() except Exception: log_error()` — which handles neither the duplicate-order nor the missed-order case.

**Consequences:**
- Duplicate order: second order for full quantity fails (no shares left) but causes confusion in logs
- Missed order: no sell despite condition being met; loss exceeds trailing stop threshold silently
- Long network outage (>5 minutes): bot misses price movements; trailing stop never fires even as price collapses

**Prevention:**
- On network error after order submission: wait 3–5 seconds, then query open orders to check if the order exists before retrying
- Implement a "pending sell" state: once a sell is triggered, mark ticker as `SELL_PENDING` persistently; do not re-trigger until confirmed filled or explicitly cleared
- For sustained network loss (>60 seconds), alert the operator immediately — do not silently retry
- Use connection timeout (e.g., `requests` timeout=10) to fail fast rather than hanging indefinitely
- Consider a watchdog: if no successful API response in N minutes during market hours, send an alert

**Warning signs:**
- `ConnectionError` or `Timeout` in logs followed by no subsequent "sell confirmed" entry
- Multiple sell submissions for the same ticker in the same minute
- Bot log shows no activity for >5 minutes during market hours

**Phase:** Address in Phase 3 (order execution layer). Also affects Phase 1 (API client robustness).

---

## Moderate Pitfalls

---

### Pitfall 7: API Response Parsing — Error Codes in HTTP 200 Responses

**Confidence:** HIGH

**What goes wrong:**
KIS API frequently returns HTTP 200 with a JSON body containing `rt_cd: "1"` (failure) and a `msg_cd` error code. Naive code checking only `response.status_code == 200` silently treats failures as successes. Examples:

- `EGW00201`: Rate limit exceeded — treated as valid price response (returns empty or stale data)
- `40310000`: Authentication failure — treated as valid data
- `40100000`: App key error — silently ignored

The current price field (`stck_prpr`) may be `"0"` or `""` in error responses. If the bot parses this as price=0, it immediately triggers the trailing stop condition (any price below peak).

**Prevention:**
- Always check `response_body['rt_cd'] == '0'` before processing data
- Treat `stck_prpr == "0"` or `""` as a parse error, not as a valid price
- Build a single API wrapper function that raises a typed exception for non-zero `rt_cd` — never let callers handle raw responses
- Log `msg_cd` and `msg1` fields on every error for debugging

**Phase:** Address in Phase 1 (API client layer). Single-point fix that protects all downstream logic.

---

### Pitfall 8: KST Timezone Handling — Server vs. Local Time

**Confidence:** HIGH

**What goes wrong:**
The bot must operate within Korean Standard Time (KST, UTC+9). If the hosting machine uses UTC or another timezone (common for cloud VMs, Docker containers), `datetime.now()` returns the wrong time. A bot running on a UTC server with naive `datetime.now()` will think market opens at 00:00 UTC (09:00 KST) and will idle or activate at wrong times. It will also log timestamps in UTC, making log debugging confusing.

**Prevention:**
- Always use `datetime.now(tz=ZoneInfo('Asia/Seoul'))` or `pytz.timezone('Asia/Seoul')`
- Never use naive `datetime.now()` anywhere in time-sensitive logic
- Log all timestamps in KST with explicit timezone label
- In Docker/server environments, set `TZ=Asia/Seoul` environment variable as a safety net, but still use explicit timezone in code

**Phase:** Address in Phase 1 (scheduler). Easy fix; devastating if missed.

---

### Pitfall 9: WebSocket Connection Drops Not Detected (실시간 체결가 스트리밍)

**Confidence:** MEDIUM (based on general WebSocket behavior + KIS API community reports)

**What goes wrong:**
If using KIS WebSocket for real-time price streaming instead of REST polling, the WebSocket connection can silently drop without triggering the `on_close` callback in some network environments. The bot continues running, believes it is receiving prices, but the last-received price is stale. The trailing stop may never fire because it never sees the current (lower) price.

**Prevention:**
- Implement a heartbeat/ping mechanism — if no message received for >30 seconds during market hours, treat connection as dead and reconnect
- Track `last_received_at` timestamp; if `now - last_received_at > 30s` during active hours, alert and reconnect
- Always reconnect on any exception in the WebSocket message handler, not just on `on_close`

**Phase:** Address in Phase 2 (price feed) if WebSocket approach chosen.

---

### Pitfall 10: 모의(Mock) vs. 실계좌(Real) Account API Differences

**Confidence:** HIGH

**What goes wrong:**
KIS API has separate endpoints and different request headers for 모의투자 (paper trading) vs. 실계좌 (real account). The `tr_id` header values differ between environments. A common mistake:
- Develop and test with mock account using mock `tr_id` values
- Switch to real account by changing credentials only
- Forget to update `tr_id` values — real account orders submitted with mock `tr_id` are rejected

Also: mock account rate limits are lower (approximately 5 req/sec vs. 20 req/sec real), so a bot that works cleanly in mock can hit rate limits in production if timing is tight.

**Prevention:**
- Centralize all `tr_id` values in a config or constants file keyed by environment (`MOCK` / `REAL`)
- Use an explicit environment flag (`TRADING_ENV=mock|real`) that switches both credentials AND `tr_id` values atomically
- Never hardcode `tr_id` strings inline — always reference the environment-keyed constant
- Test rate limit headroom explicitly before moving from mock to real

**Phase:** Address in Phase 1 (API client configuration). Catches most before live trading.

---

### Pitfall 11: 보유 수량 vs. 매도 가능 수량 Confusion

**Confidence:** HIGH

**What goes wrong:**
The KIS balance inquiry API (`/uapi/domestic-stock/v1/trading/inquire-balance`) returns multiple quantity fields:
- `hldg_qty`: Total held quantity
- `ord_psbl_qty`: Orderable (sellable) quantity

If you have an open buy order or recently bought shares that haven't settled (T+1 for KSX), `ord_psbl_qty` may be less than `hldg_qty`. Submitting a sell for `hldg_qty` when only `ord_psbl_qty` is available causes an order rejection.

**Prevention:**
- Always use `ord_psbl_qty` for sell order quantity, not `hldg_qty`
- If `ord_psbl_qty == 0` for a ticker that should be sellable, log a warning and alert operator — do not silently skip

**Phase:** Address in Phase 3 (order execution). Straightforward field selection fix.

---

### Pitfall 12: Sell on First Tick — False Trigger at Bot Startup

**Confidence:** HIGH

**What goes wrong:**
On startup, if the high-water mark is initialized to current price (no persisted value), and the current price is already below a meaningful peak (e.g., stock opened gap-down), the trailing stop condition is not met. This is correct. However, if the initial price poll returns a stale/zero value (due to a transient API error), the high-water mark is set to 0 and any real price appears to be above 0, which is fine — BUT: if stale data returns the previous day's closing price and the current price happens to be 10%+ lower than the prior close (gap-down open), the bot fires a sell immediately on first price update.

The more subtle version: developer initializes `peak = 0`, then sets `peak = max(peak, current_price)` on first tick, which is correct — BUT forgets to skip the trailing stop check on the initialization tick.

**Prevention:**
- On startup, perform a "warming" period of 1–2 price polls before enabling the sell trigger
- Validate the first received price is non-zero and within a reasonable range before setting it as the peak
- Log explicitly: "Initial peak set to X for ticker Y at startup — sell trigger active from next poll"

**Phase:** Address in Phase 2 (trailing stop engine initialization logic).

---

## Minor Pitfalls

---

### Pitfall 13: API Key and Secret Hardcoded in Source Code

**Confidence:** HIGH

**What goes wrong:**
Developers commit `app_key`, `app_secret`, and account numbers directly into source files. Even if the repo is private, this is a critical security risk — secrets in git history are permanent.

**Prevention:**
- Use `.env` file with `python-dotenv` and add `.env` to `.gitignore` from day one
- Use environment variables (`os.environ.get(...)`) not config files committed to the repo
- Add a startup check: if any secret contains a placeholder value (e.g., "your_key_here"), refuse to start
- Consider using a local secrets file pattern: `config.secrets.yaml` + `.gitignore` entry

**Phase:** Address in Phase 1, first thing. Non-negotiable before any code reaches git.

---

### Pitfall 14: KakaoTalk Alert Failures Silently Block Bot Execution

**Confidence:** MEDIUM

**What goes wrong:**
If KakaoTalk notification (카카오톡 메시지 API) is called synchronously in the sell execution path, and the Kakao API is slow or down, the notification call blocks the bot. In worst case, the HTTP timeout (default in Python's `requests` is no timeout) causes the bot to hang indefinitely on the notification call while the price continues to fall and no sell order is submitted.

**Prevention:**
- Always send notifications asynchronously (thread, asyncio task, or fire-and-forget)
- Set explicit timeouts on all outbound HTTP calls (Kakao, any other webhook): `timeout=5`
- Notification failure must never prevent order submission: wrap in `try/except` with logging
- Order first, notify second — always

**Phase:** Address in Phase 4 (notifications). Alert is secondary to order execution.

---

### Pitfall 15: Log Files Growing Unboundedly

**Confidence:** MEDIUM

**What goes wrong:**
A bot polling 10 tickers every second generates ~86,000 log entries per market day. Plain file logging with no rotation fills disk over weeks. On resource-constrained servers (Raspberry Pi, small VPS), this can cause disk full errors that crash the bot — mid-session.

**Prevention:**
- Use Python's `RotatingFileHandler` or `TimedRotatingFileHandler` from day one
- Separate log levels: INFO for price polls to a high-volume log, WARNING/ERROR to a separate critical log
- Keep at least 7 days of rotated logs for debugging; prune older automatically

**Phase:** Address in Phase 1 (logging setup). Cheap to fix upfront; painful to fix retroactively.

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| Phase 1: API client | Rate limits (Pitfall 1), Token expiry (Pitfall 2), HTTP 200 error parsing (Pitfall 7) | Build a robust API wrapper with rate limiting, token lifecycle management, and `rt_cd` checking before anything else |
| Phase 1: Auth module | Token issuance rate limit on retry (Pitfall 2) | Implement token cache + scheduled refresh; never call token endpoint on every request |
| Phase 1: Config/secrets | API keys in source (Pitfall 13) | `.env` + `.gitignore` before first commit |
| Phase 1: Scheduler | Timezone bugs (Pitfall 8), Market hours edge cases (Pitfall 3) | Use `ZoneInfo('Asia/Seoul')` everywhere; handle 동시호가 periods |
| Phase 2: Trailing stop engine | Peak lost on restart (Pitfall 4), Startup false trigger (Pitfall 12) | Persist peak to disk; add startup warmup period |
| Phase 2: Price feed | WebSocket silent drops (Pitfall 9) | Heartbeat check if using WebSocket streaming |
| Phase 3: Order execution | Partial fill (Pitfall 5), Network interruption (Pitfall 6), Duplicate orders (Pitfall 6), 매도가능수량 confusion (Pitfall 11) | Stateful order tracking; query order status post-submission |
| Phase 3: Mock-to-real transition | tr_id mismatch (Pitfall 10) | Environment-keyed tr_id constants |
| Phase 4: Notifications | Blocking notification call (Pitfall 14) | Async notification; order-first discipline |
| All phases | Log disk growth (Pitfall 15) | Rotating file handler from day one |

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| KIS API rate limits | HIGH | Well-documented; 20 req/sec for real accounts is consistent across multiple community sources in training data |
| Token expiry (24h) | HIGH | Official KIS API documentation was consistent on this |
| Market hours structure | HIGH | KSX operating hours are stable, well-known facts |
| 동시호가 behavior | HIGH | Korean market microstructure; stable knowledge |
| High-water mark restart | HIGH | Logic-level pitfall independent of specific API |
| Order failure scenarios | HIGH | KSX settlement rules and KIS error codes are stable |
| WebSocket silent drops | MEDIUM | General WebSocket behavior; specific KIS WebSocket behavior extrapolated from community patterns |
| Mock vs. real tr_id differences | HIGH | Documented in KIS API portal; consistent community reports |
| KakaoTalk API behavior | MEDIUM | General API integration pattern; specific Kakao latency/availability characteristics extrapolated |

---

## Sources

All findings are from training data (knowledge cutoff mid-2025). External search tools were unavailable during this research session. Recommended verification sources:

- KIS Developers Portal: https://apiportal.koreainvestment.com
- KIS API GitHub (official): https://github.com/koreainvestment/open-trading-api
- Community Python wrapper reference: https://github.com/sharebook-kr/pykis (review issues for real-world failure reports)
- KRX 시장 운영 시간: https://www.krx.co.kr

**Verification recommended for:** Pitfalls 7 (exact error codes), 9 (WebSocket reconnection behavior), and 10 (current tr_id values for each endpoint) — these should be confirmed against current KIS API documentation before implementation.
