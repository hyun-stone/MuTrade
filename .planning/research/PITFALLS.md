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

## v1.1 Admin Dashboard 통합 함정

**추가 연구:** 2026-04-12
**범위:** 기존 단일 프로세스 Python 봇(APScheduler BlockingScheduler + time.sleep 폴링 루프)에 FastAPI + uvicorn + WebSocket 관리자 UI를 추가할 때 발생하는 통합 함정.

현재 코드베이스 구조 요약:
- `main.py`: 동기 엔트리포인트. `start_scheduler()`를 호출하면 `BlockingScheduler.start()`가 현재 스레드를 점유한다.
- `scheduler.py`: `BlockingScheduler` + `time.sleep(config.poll_interval)` 루프. 완전히 동기식.
- `TrailingStopEngine`: `dict[str, SymbolState]` 인-메모리 상태 (Lock 없음, 단일 스레드 가정).
- `OrderExecutor`: `_pending: set[str]` (Lock 없음, 단일 스레드 가정).
- `StateStore`: 원자적 JSON 파일 쓰기 (os.replace).
- `config.toml`: 시작 시 한 번만 로드, 런타임 갱신 없음.

---

### Pitfall 16: BlockingScheduler와 uvicorn 이벤트 루프 충돌 — 프로세스 시작 불가

**Confidence:** HIGH (APScheduler 공식 문서 + 다수 커뮤니티 확인)

**What goes wrong:**
현재 `start_scheduler()`는 `BlockingScheduler.start()`를 호출하고 현재 스레드를 영구 점유한다. uvicorn은 `asyncio.run()`을 통해 자체 이벤트 루프를 같은 스레드에서 실행해야 한다. 두 가지를 동일 스레드에서 실행하면 먼저 호출된 쪽이 다른 쪽을 차단한다.

`main.py`에서 `start_scheduler()` 다음에 `uvicorn.run(app)`을 추가하면 스케줄러가 uvicorn보다 먼저 호출되므로 uvicorn은 절대 시작되지 않는다. 순서를 바꿔도 uvicorn이 스케줄러를 차단한다.

**Why it happens:**
`BlockingScheduler`는 "프로세스에서 스케줄러만 실행"하는 시나리오를 위해 설계되었다. APScheduler 공식 문서는 "다른 코드와 함께 실행할 때는 `BackgroundScheduler`를 사용하라"고 명시한다.

**Consequences:**
- 두 서비스 중 하나가 절대 시작되지 않는다.
- 시작 오류가 없어서 "왜 웹 UI가 안 뜨지?" 상황이 되고 디버깅이 어렵다.

**Prevention:**
`BlockingScheduler`를 `BackgroundScheduler`로 교체한다. 폴링 루프 내 `time.sleep()`은 그대로 유지 가능하다 — `BackgroundScheduler`는 별도 스레드에서 잡을 실행하므로 sleep이 메인 스레드(uvicorn)를 차단하지 않는다.

```python
# 변경 전
from apscheduler.schedulers.blocking import BlockingScheduler
scheduler = BlockingScheduler(timezone="Asia/Seoul")

# 변경 후
from apscheduler.schedulers.background import BackgroundScheduler
scheduler = BackgroundScheduler(timezone="Asia/Seoul")
scheduler.start()
# 이후 uvicorn.run(app) 호출 가능
```

FastAPI lifespan 컨텍스트 매니저 안에서 `scheduler.start()` / `scheduler.shutdown()` 호출로 수명 주기를 관리한다.

**Warning signs:**
- 웹 UI가 절대 응답하지 않음 (포트 바인딩 안 됨)
- 또는 봇 폴링이 절대 시작되지 않음
- `uvicorn.run()`이 반환되지 않는데 FastAPI 엔드포인트가 도달 불가

**Phase:** v1.1 Phase 1 (FastAPI 뼈대 통합) — 최초 통합 시 반드시 해결.

---

### Pitfall 17: 스레드-비동기 경계에서 TrailingStopEngine 상태 불안전 접근

**Confidence:** HIGH

**What goes wrong:**
`BackgroundScheduler`로 전환하면 폴링 루프(`run_session`)는 APScheduler의 스레드 풀에서 실행된다 (별도 스레드). FastAPI WebSocket 핸들러는 uvicorn의 asyncio 이벤트 루프에서 실행된다 (다른 스레드). 둘 다 `TrailingStopEngine._states`(dict)와 `OrderExecutor._pending`(set)을 읽거나 쓴다.

현재 코드는 Lock이 없다. 이는 v1.0에서 단일 스레드였기 때문에 올바른 설계였다. v1.1에서는 더 이상 단일 스레드가 아니다.

Python의 GIL은 dict/set에 대한 단순 read/write를 원자적으로 만들지만, 다음 두 가지 복합 연산은 보호하지 않는다:
1. `check → act` 패턴: `if code not in self._pending: self._pending.add(code)` — 두 스레드가 동시에 "not in"을 확인하면 둘 다 add 가능
2. dict를 순회하며 동시에 다른 스레드가 항목을 추가/삭제하면 `RuntimeError: dictionary changed size during iteration`

**Why it happens:**
단일 스레드 코드에 Lock이 없는 것은 올바른 설계다. 스레드를 추가하면서 Lock 추가를 잊는 것이 가장 흔한 통합 실수다.

**Consequences:**
- WebSocket 핸들러가 상태를 읽는 동시에 폴링 루프가 상태를 수정 → `RuntimeError: dictionary changed size during iteration` (간헐적, 재현 어려움)
- 동일 종목에 중복 매도 주문 제출 가능 (SELL_PENDING 체크가 race condition에 노출)
- WebSocket으로 전송되는 상태가 부분 업데이트 중간 값을 포함할 수 있음

**Prevention:**
공유 상태 접근을 단일 Lock으로 보호한다. 가장 단순한 패턴:

```python
import threading

class TrailingStopEngine:
    def __init__(self, ...):
        ...
        self._lock = threading.Lock()

    def tick(self, prices):
        with self._lock:
            # 기존 로직 그대로
            ...

    def snapshot(self) -> dict:
        """WebSocket 핸들러용 읽기 전용 스냅샷 반환."""
        with self._lock:
            return {
                code: dataclasses.replace(state)
                for code, state in self._states.items()
            }
```

WebSocket 핸들러는 `engine._states`를 직접 접근하지 말고 항상 `engine.snapshot()`을 사용한다. `OrderExecutor._pending`도 동일하게 Lock으로 보호한다.

asyncio 측에서 Lock이 필요하면 `threading.Lock`을 사용한다 (asyncio.Lock은 동일 스레드 내 코루틴 간 전용이므로 스레드 간에는 작동하지 않는다).

**Warning signs:**
- `RuntimeError: dictionary changed size during iteration` 간헐적 발생
- 같은 종목에 2번 매도 주문 로그
- 상태 조회 API가 가끔 불완전한 데이터 반환

**Phase:** v1.1 Phase 1 (FastAPI 뼈대 통합) — BackgroundScheduler 전환과 동시에 해결.

---

### Pitfall 18: 스케줄러 스레드 → asyncio 이벤트 루프 WebSocket 브로드캐스트 크로스-스레드 호출

**Confidence:** HIGH (Python 공식 문서 asyncio-dev 섹션 명시)

**What goes wrong:**
가격 업데이트를 WebSocket 클라이언트에 실시간으로 Push하려면 폴링 루프(스케줄러 스레드)가 asyncio WebSocket 핸들러에 데이터를 전달해야 한다. 스케줄러 스레드에서 `asyncio` 코루틴을 직접 호출하면 다음 오류가 발생한다:

```
RuntimeError: This event loop is already running.
# 또는
RuntimeError: There is no current event loop in thread 'APScheduler...'.
```

`asyncio.run(coro())`를 스케줄러 스레드에서 호출해도 새 이벤트 루프를 만들어 기존 WebSocket 연결과 연결이 끊어진다.

**Why it happens:**
asyncio 이벤트 루프는 생성된 스레드에 귀속된다. 다른 스레드에서 코루틴을 직접 호출하는 것은 안전하지 않다.

**Consequences:**
- 스케줄러 스레드에서 WebSocket 브로드캐스트 시도 시 크래시
- 조용히 실패하면 WebSocket 클라이언트가 업데이트를 전혀 받지 못함
- 새 이벤트 루프를 잘못 만들면 기존 WebSocket 연결이 고아(orphan) 상태

**Prevention:**
`asyncio.run_coroutine_threadsafe()`를 사용해 스케줄러 스레드에서 asyncio 이벤트 루프로 코루틴을 안전하게 제출한다:

```python
import asyncio

# FastAPI 앱 시작 시 이벤트 루프 참조를 저장
loop = asyncio.get_event_loop()

# 스케줄러 스레드에서 (run_session 내부)
def broadcast_update(state_snapshot):
    future = asyncio.run_coroutine_threadsafe(
        websocket_manager.broadcast(state_snapshot),
        loop
    )
    # 결과 기다리지 않음 (fire-and-forget)
    # future.result()를 스케줄러 스레드에서 호출하면 데드락 위험
```

더 단순한 대안: 스케줄러 스레드는 `asyncio.Queue` 대신 `queue.Queue`(스레드 안전)에 업데이트를 넣고, asyncio 쪽에서 `asyncio.get_event_loop().run_in_executor()`나 별도 태스크로 큐를 소비한다.

**Warning signs:**
- `RuntimeError: This event loop is already running` 로그
- WebSocket 클라이언트 연결은 되지만 업데이트를 전혀 수신하지 못함
- 스케줄러 스레드의 예외가 조용히 삼켜짐

**Phase:** v1.1 Phase 2 (WebSocket 실시간 현황) — WebSocket 브로드캐스트 구현 시.

---

### Pitfall 19: config.toml 런타임 수정 — 파일 손상 및 엔진 상태 불일치

**Confidence:** HIGH

**What goes wrong:**
웹 UI에서 config.toml을 수정할 때 두 가지 위험이 있다.

**위험 1 — 파일 손상:** FastAPI 엔드포인트(asyncio 스레드)와 OS/사용자가 동시에 config.toml을 쓰면 파일이 손상된다. Python의 일반적인 `open(path, 'w') + write()` 패턴은 원자적이지 않다 — 쓰기 도중 읽으면 부분 파일이 노출된다.

**위험 2 — 엔진 상태 불일치:** config.toml을 파일에만 저장하고 실행 중인 `TrailingStopEngine`에는 반영하지 않으면 다음 재시작 전까지 새 설정이 적용되지 않는다. 사용자는 UI에서 임계값을 7%로 바꿨지만 실제 봇은 여전히 10%를 사용한다. 이는 매우 위험한 불일치다.

**Why it happens:**
파일 저장과 인메모리 상태 갱신을 동시에 하는 것을 망각한다. config.toml은 시작 시 한 번만 로드하는 불변 구조(`frozen=True` 데이터클래스)로 설계되어 있어서, 런타임 변경을 위한 업데이트 경로가 없다.

**Consequences:**
- 파일 손상 시 다음 봇 재시작에서 `TOMLDecodeError` — 봇 시작 불가
- 설정이 파일과 엔진 사이에 조용히 분기되어 사용자가 신뢰할 수 없는 UI 표시
- 임계값 낮춤(예: 10% → 5%)이 적용 안 되면 더 큰 손실 허용

**Prevention:**
1. **원자적 파일 쓰기:** 기존 `StateStore.save()`의 `tempfile.mkstemp() + os.replace()` 패턴을 config.toml 쓰기에도 동일하게 적용한다. `tomlkit` 라이브러리는 TOML 스타일(주석, 공백)을 보존하면서 쓰기 가능하다.
2. **파일 + 엔진 동시 갱신:** config.toml 저장 직후 `TrailingStopEngine`의 `_symbols` dict와 임계값을 갱신한다. 이를 위해 엔진에 `update_symbol_config(code, threshold)` 메서드를 추가한다.
3. **Lock 보호 필수:** 설정 갱신 중 폴링 루프가 `_symbols`를 읽을 수 있으므로 Lock으로 보호한다 (Pitfall 17 참조).

```python
# config 갱신 엔드포인트 패턴
@router.patch("/config/symbols/{code}")
async def update_symbol_threshold(code: str, threshold: float):
    # 1. 파일 원자적 쓰기
    await write_config_atomically(new_config)
    # 2. 엔진 인메모리 갱신
    engine.update_symbol_config(code, threshold)
    return {"status": "applied"}
```

**Warning signs:**
- UI에서 임계값 변경 후 실제 매도가 이전 임계값으로 발생
- 재시작 시 `TOMLDecodeError` (파일 손상)
- UI 표시 임계값과 로그의 임계값이 다름

**Phase:** v1.1 Phase 3 (설정 변경 UI) — 반드시 원자적 쓰기와 엔진 동기화를 함께 구현.

---

### Pitfall 20: 봇 시작/중지 제어 — 경쟁 조건과 부분 중지

**Confidence:** HIGH

**What goes wrong:**
웹 UI에서 "봇 중지" 버튼을 누르면 무엇을 중지해야 하는가? 현재 아키텍처에서는:
- `BackgroundScheduler`의 잡 실행 여부
- 현재 실행 중인 `run_session()` 내부의 `while True` 폴링 루프
- 진행 중인 KIS API 호출
- SELL_PENDING 상태의 체결 확인 폴링

이 중 하나만 멈추면 "부분 중지"가 된다. 전형적인 버그:

**버그 1 — 중지 신호 무시:** `scheduler.pause_job("market_poll")`은 다음 잡 실행을 막지만, 이미 실행 중인 `run_session()`의 `while True` 루프는 계속 돌아간다. UI에는 "중지됨"이라고 표시되지만 봇은 폴링 중이다.

**버그 2 — 중지 중 매도 실행:** "중지" 요청이 들어오는 순간 `executor.execute(signal)`이 진행 중이면 어떻게 되는가? 중지 플래그가 체결 확인 루프 중간에 설정되면 `_pending`이 영구히 남아 다음 시작 시 해당 종목이 매도 불가 상태가 된다.

**버그 3 — 재시작 중복 실행:** 빠르게 중지 → 시작을 반복하면 이전 `run_session()` 루프가 아직 살아있는 상태에서 새 루프가 시작된다. 동일 종목에 두 개의 폴링 루프가 동시에 실행된다.

**Why it happens:**
"중지"를 단일 플래그 하나로 구현하고, 진행 중인 작업이 해당 플래그를 검사하지 않는다.

**Consequences:**
- "중지" 상태에서 실제 매도 주문이 발생
- SELL_PENDING 영구 고착으로 다음 세션에서 해당 종목 매도 불가
- 중복 폴링 루프로 KIS API 호출이 2배가 되어 레이트 리밋 초과

**Prevention:**
중지 제어를 `threading.Event`로 구현한다:

```python
import threading

# 공유 중지 이벤트
stop_event = threading.Event()

# run_session 내 폴링 루프
while not stop_event.is_set():
    prices = poll_prices(kis, config)
    signals = engine.tick(prices)
    for sig in signals:
        if stop_event.is_set():
            break  # 중지 중이면 새 매도 처리 안 함
        executor.execute(sig)
    stop_event.wait(timeout=config.poll_interval)  # time.sleep 대신 사용
```

`stop_event.wait(timeout=N)`은 `time.sleep(N)`과 동일하게 동작하지만 이벤트가 설정되면 즉시 깨어난다.

중지 시 체결 확인 중인 주문은 완료될 때까지 기다리거나(안전) 타임아웃 후 강제 종료(위험)를 선택한다. 안전한 방법: "중지 요청됨" 상태를 두고 현재 실행 중인 `execute()` 완료를 기다린 후 완전 중지한다.

**Warning signs:**
- UI "중지" 후 로그에 폴링 계속 기록
- "중지" 상태에서 SELL SIGNAL 로그 발생
- 재시작 후 같은 종목 로그가 2배로 나타남

**Phase:** v1.1 Phase 2 (봇 제어 UI) — 중지 이벤트 설계를 폴링 루프와 함께 구현.

---

### Pitfall 21: 로그 파일 실시간 파싱 — 대용량 파일 및 로테이션 처리 누락

**Confidence:** HIGH

**What goes wrong:**
거래 이력 테이블을 위해 `logs/mutrade.log`에서 `[TRADE]` 마커를 파싱할 때 흔한 실수:

**실수 1 — 전체 파일 읽기:** `open("logs/mutrade.log").read()`로 파일 전체를 읽는다. 30일치 로그(loguru 설정상 최대 10MB)를 매 요청마다 전체 읽으면 응답이 느리고 메모리 낭비다.

**실수 2 — 로테이션 무시:** loguru는 10MB 초과 시 `mutrade.log.1`, `mutrade.log.2` 등으로 로테이션한다. `[TRADE]` 항목이 이전 파일에 있을 수 있다. `mutrade.log`만 파싱하면 이전 거래 이력이 누락된다.

**실수 3 — WebSocket 실시간 스트리밍 시 파일 핸들 누수:** 로그를 실시간으로 tail하여 WebSocket으로 보내는 패턴에서 `open()`은 했지만 연결 종료 시 파일 핸들을 닫지 않으면 FD(파일 디스크립터) 누수가 발생한다.

**실수 4 — asyncio에서 동기 파일 I/O:** `async def` 핸들러 안에서 `open().read()`를 직접 호출하면 이벤트 루프가 블락된다. 10MB 파일 읽기 중에 다른 WebSocket 연결이 응답하지 않는다.

**Why it happens:**
파일 읽기는 단순해 보이므로 엣지 케이스를 고려하지 않는다.

**Consequences:**
- 대용량 파일에서 거래 이력 API가 수 초간 응답 안 함
- 로테이션된 파일의 이전 거래 이력 누락
- 파일 핸들 누수로 장시간 운영 시 "Too many open files" 오류
- 이벤트 루프 블락으로 다른 WebSocket 클라이언트 연결 지연

**Prevention:**
- `asyncio.to_thread()` 또는 `loop.run_in_executor()`로 파일 I/O를 스레드 풀에서 실행한다.
- 거래 이력 조회는 현재 + 로테이션된 파일 모두를 스캔하되, 파일 목록을 `glob("logs/mutrade.log*")`로 수집한다.
- 파일을 처음부터 읽지 말고 `[TRADE]` 마커만 필터링하여 읽는다 (`grep` 등가).
- WebSocket 실시간 tail은 반드시 `async with` 또는 `try/finally`로 파일 핸들을 닫는다.
- 거래 이력이 빈번하게 조회된다면 시작 시 한 번 파싱 후 인메모리 캐시를 유지하고, 새 `[TRADE]` 로그 발생 시에만 갱신한다.

```python
# 올바른 패턴: 블로킹 파일 I/O를 executor로 오프로드
async def get_trade_history() -> list[TradeRecord]:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _parse_trade_logs_sync)

def _parse_trade_logs_sync() -> list[TradeRecord]:
    records = []
    for log_file in sorted(Path("logs").glob("mutrade.log*")):
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                if "[TRADE]" in line:
                    records.append(parse_trade_line(line))
    return records
```

**Warning signs:**
- 거래 이력 API 응답 시간이 초 단위로 느림
- 로테이션 후 이전 거래 이력 API에서 사라짐
- `OSError: [Errno 24] Too many open files` 오류

**Phase:** v1.1 Phase 3 (거래 이력 UI) — 처음부터 비동기 파일 I/O와 로테이션 파일 스캔으로 구현.

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
| **v1.1 Phase 1: FastAPI 통합** | **BlockingScheduler 충돌 (Pitfall 16)** | **BackgroundScheduler로 교체 + lifespan 관리** |
| **v1.1 Phase 1: FastAPI 통합** | **스레드-비동기 상태 경쟁 (Pitfall 17)** | **threading.Lock으로 공유 상태 보호, snapshot() 메서드 추가** |
| **v1.1 Phase 2: WebSocket 현황** | **크로스-스레드 asyncio 호출 (Pitfall 18)** | **run_coroutine_threadsafe() 또는 thread-safe Queue 사용** |
| **v1.1 Phase 2: 봇 제어 UI** | **부분 중지 경쟁 조건 (Pitfall 20)** | **threading.Event로 stop_event 구현, time.sleep → event.wait** |
| **v1.1 Phase 3: 설정 변경 UI** | **config.toml 손상 + 엔진 불일치 (Pitfall 19)** | **원자적 쓰기 + 엔진 동시 갱신 + Lock 보호** |
| **v1.1 Phase 3: 거래 이력 UI** | **대용량 파일 블로킹 + 로테이션 누락 (Pitfall 21)** | **run_in_executor + glob 로테이션 파일 스캔** |

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
| **BlockingScheduler 충돌 (Pitfall 16)** | **HIGH** | APScheduler 공식 문서 명시 + 웹 검색으로 다수 사례 확인 |
| **스레드-비동기 상태 경쟁 (Pitfall 17)** | **HIGH** | Python 스레드-asyncio 경계 동작은 언어 명세 수준으로 확정적 |
| **크로스-스레드 asyncio 호출 (Pitfall 18)** | **HIGH** | Python 공식 asyncio-dev 문서에 명시된 패턴 |
| **config.toml 런타임 수정 (Pitfall 19)** | **HIGH** | 파일 원자성은 OS 레벨 확정 사실; 엔진 불일치는 코드 구조에서 직접 확인 |
| **봇 부분 중지 (Pitfall 20)** | **HIGH** | threading.Event 패턴은 표준적, time.sleep과의 차이는 확정적 |
| **로그 파일 파싱 (Pitfall 21)** | **HIGH** | asyncio 블로킹 I/O 문제는 문서화된 패턴; loguru 로테이션 동작은 소스코드에서 확인 |

---

## Sources

All findings are from training data (knowledge cutoff mid-2025). External search tools were unavailable during this research session. Recommended verification sources:

- KIS Developers Portal: https://apiportal.koreainvestment.com
- KIS API GitHub (official): https://github.com/koreainvestment/open-trading-api
- Community Python wrapper reference: https://github.com/sharebook-kr/pykis (review issues for real-world failure reports)
- KRX 시장 운영 시간: https://www.krx.co.kr

**v1.1 Admin Dashboard 추가 참고:**
- APScheduler BlockingScheduler vs BackgroundScheduler: https://apscheduler.readthedocs.io/en/3.x/userguide.html
- Python asyncio 크로스-스레드 통신: https://docs.python.org/3/library/asyncio-dev.html
- run_coroutine_threadsafe 공식 문서: https://docs.python.org/3/library/asyncio-task.html#asyncio.run_coroutine_threadsafe
- FastAPI WebSocket 공식 가이드: https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI lifespan 이벤트: https://fastapi.tiangolo.com/advanced/events/

**Verification recommended for:** Pitfalls 7 (exact error codes), 9 (WebSocket reconnection behavior), and 10 (current tr_id values for each endpoint) — these should be confirmed against current KIS API documentation before implementation.
