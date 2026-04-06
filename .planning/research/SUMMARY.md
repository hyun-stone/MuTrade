# Project Research Summary

**Project:** MuTrade — 자동 트레일링 스탑 트레이딩 봇
**Domain:** Personal automated stop-loss trading bot (Korea Investment & Securities / KIS API)
**Researched:** 2026-04-06
**Confidence:** MEDIUM (training data only; no live web search; verify KIS API specifics before implementation)

---

## Executive Summary

MuTrade is a personal-scale automated trailing-stop bot that monitors selected Korean stock holdings during KRX market hours (09:00–15:30 KST) and submits a market-sell order when any holding falls 10% or more from its tracked peak. The established approach in the Korean trading bot community is a single Python process using REST polling (not WebSocket) for price data, in-process APScheduler-based market-hours gating, and a flat JSON file for persisting high-water marks across restarts. This is a well-understood problem domain: the core algorithm is trivially simple, but the operational correctness requirements — token lifecycle management, peak persistence, safe order execution — are where personal bots most commonly fail silently.

The recommended build strategy is incremental bottom-up: establish reliable KIS API connectivity with proper token caching and response parsing first, then wire in the trailing-stop engine against that foundation, then add live order execution behind a dry-run flag, and finally add notification. This order is critical because all other components depend on a robust API client, and production bugs in that layer (rate limit violations, stale-token failures, HTTP-200 error responses) are the most common causes of silent bot malfunction.

The top risks are not algorithmic — they are operational. KIS access tokens expire every 24 hours, high-water marks are lost on any restart without explicit persistence, and the KIS API returns error information inside HTTP 200 responses (not as HTTP error codes), making naive error handling dangerously incorrect. All three of these must be solved in Phase 1 before any trailing-stop or order logic is written.

---

## Key Findings

### Recommended Stack

The Python ecosystem has a clear recommended path for KIS-based bots. The `python-kis` library (Soju06/python-kis, PyPI `python-kis>=4.0`) is the dominant community KIS wrapper and handles OAuth token management, price queries, balance queries, and order placement. If `python-kis` proves problematic, the KIS REST API is plain HTTP+JSON and `httpx` is a viable direct-call fallback. All other dependencies are standard Python ecosystem choices with multi-year stability.

**Core technologies:**
- `python-kis 4.x`: KIS REST + WebSocket wrapper — handles OAuth token refresh, typed responses, and covers all required endpoints
- `Python 3.11/3.12`: runtime — 3.11 is stable LTS; 3.12 adds minor perf gains; avoid 3.13
- `pydantic-settings 2.x` + `python-dotenv 1.x`: typed config from `.env` — catches misconfiguration at startup before market open
- `tomllib` (stdlib 3.11+): `config.toml` for per-symbol trading rules — no extra dependency
- `APScheduler 3.10.x`: market-hours scheduling with KST timezone — `CronTrigger` + `zoneinfo.ZoneInfo("Asia/Seoul")`
- `loguru 0.7.x`: logging with automatic rotation — eliminates all stdlib `logging` boilerplate
- `python-telegram-bot 21.x`: push notifications — simpler and more operationally robust than KakaoTalk for a headless bot
- `httpx 0.27.x`: async HTTP for direct KIS REST calls / fallback

**On KakaoTalk:** KakaoTalk "나에게 보내기" is technically feasible but requires OAuth refresh every 30 days and has no official Python SDK. Recommended approach: use Telegram as primary, add KakaoTalk direct REST calls if specifically required, and never depend on a community Kakao SDK.

**What to avoid:** `mojito` (outdated KIS wrapper), `yaml`/PyYAML (implicit type coercion bugs with stock codes starting with `0`), `celery`/`rq` (overkill), `FastAPI`/`Flask` (no web server needed), `LINE Notify` (shut down March 2025).

### Expected Features

**Must have (table stakes) — v1 blockers:**
- KIS OAuth 2.0 token management with automatic 24h refresh — everything depends on this
- Current price polling per symbol (REST, 3–5s interval) — core data input
- Per-symbol trailing high-water mark tracking — the core algorithm
- Drop percentage calculation: `(peak - price) / peak >= threshold`
- Market-sell order execution (`시장가 매도`) — guaranteed fill
- Dry-run mode — must exist before any live testing
- Watchlist config file — user controls which symbols are monitored
- Market hours gate: 09:00–15:20 KST, weekdays only (conservative: stop before 장후 동시호가)
- High-water mark persistence to disk (JSON) — survives restarts
- API retry with exponential backoff — handles transient KIS failures
- Trade history log file — audit trail
- Secrets in `.env` / env vars, gitignored — non-negotiable

**Should have (high-value, low-effort differentiators):**
- Per-symbol trailing-stop threshold (not one global value) — stocks have different volatility profiles
- Manual initial peak override in config — captures historical peaks before bot started
- KakaoTalk or Telegram sell notification — operator informed without watching logs
- KRX holiday calendar — prevents wasteful runs on non-trading days

**Defer to v2+:**
- WebSocket real-time price feed — polling at 3–5s is sufficient for 10% trailing stop; WebSocket adds reconnect complexity
- Order fill confirmation polling — market orders on KRX liquid stocks have near-100% fill rate
- VI (Volatility Interruption) detection — rare event, high complexity
- Daily operations report
- Auto-buy — explicitly out of scope per PROJECT.md

### Architecture Approach

The architecture is a single long-running Python process with clear layer boundaries: Config/Logger at the foundation, Auth Manager and KIS API Client above it, Price Feed and State Manager as the data layer, Trailing Stop Engine as the core logic layer, and Order Executor + Notifier as the execution layer, all orchestrated by the Scheduler. Components are independent Python modules so the trailing-stop engine can be unit-tested with mock prices without touching the KIS API. State flows in one direction; no component calls "down" into a higher layer.

**Major components:**
1. **Config Loader** — parses `.env` (secrets) and `config.toml` (trading rules); validates at startup via pydantic-settings
2. **Auth Manager** — obtains and caches KIS OAuth2 token; proactively refreshes before 24h expiry; never calls token endpoint on every request
3. **KIS API Client** — thin HTTP wrapper over KIS REST; always checks `rt_cd == "0"` in response body (not just HTTP status); raises typed exceptions on errors
4. **Price Feed** — polls current price per symbol with inter-call sleep to stay within rate limits
5. **State Manager** — persists `{symbol: high_price}` to `state.json` via atomic temp-file rename; loads on startup
6. **Trailing Stop Engine** — updates high-water mark; emits sell signal when drop threshold crossed; warming period on startup to avoid false first-tick triggers
7. **Order Executor** — guards against duplicate orders; queries `ord_psbl_qty` (not `hldg_qty`) for sell quantity; tracks `SELL_PENDING` state; confirms fill post-submission
8. **Notifier** — async, fire-and-forget; order submission always precedes notification
9. **Scheduler** — gates all activity to market hours using `ZoneInfo("Asia/Seoul")`; uses 09:00–15:20 KST window (conservative)
10. **Logger** — loguru with daily rotation; separate permanent trade log

### Critical Pitfalls

1. **KIS API returns errors inside HTTP 200 responses** — always check `response['rt_cd'] == '0'`; treat `stck_prpr == "0"` as a parse error, not a real price. A missing check here causes the trailing stop to fire instantly on any API error. Address in Phase 1.

2. **Access token silently expires mid-session** — KIS tokens are valid 24h; the token issuance endpoint is rate-limited to ~1 req/min. Cache token with `expires_at`; proactively refresh at 08:30 KST daily; never call the token endpoint on every request. Address in Phase 1.

3. **High-water mark lost on any restart** — in-memory peak state resets to current price on crash or reboot, silently widening the effective stop-loss. Write `state.json` atomically after every peak update. Address in Phase 2.

4. **Market hours edge cases: 동시호가 and holidays** — the active monitoring window is `09:00 <= now < 15:20 KST` (not 15:30); 동시호가 (08:00–09:00, 15:20–15:30) uses indicative prices that can trigger false sells. Add KRX holiday check. Address in Phase 1.

5. **Polling too fast violates rate limits** — KIS real-account REST limit is ~20 req/sec; mock accounts are ~5 req/sec. With 10 symbols polling at 1s, the bot is already at the limit. Use 0.5s sleep between symbol calls and 3s outer loop cadence. Address in Phase 1 before any polling loop is written.

---

## Implications for Roadmap

Based on the dependency graph in ARCHITECTURE.md and the critical pitfalls identified in PITFALLS.md, the recommended phase structure is:

### Phase 1: Foundation and KIS API Connectivity

**Rationale:** All other components depend on a working, robust KIS API client. The three most common causes of silent bot failure (stale token, HTTP-200 error parsing, rate limit violations) all live here. This phase must be airtight before anything else is built.

**Delivers:** A tested, production-ready KIS API client with token lifecycle management, correct error handling, and rate-aware price/balance queries. Also establishes config, secrets, logging, and market-hours scheduling.

**Addresses features:**
- KIS OAuth 2.0 token management (24h expiry, proactive refresh)
- Current price polling (`현재가 조회`)
- Holdings balance query (`잔고 조회`)
- Secrets in `.env` + `.gitignore`
- Market hours gate with KST timezone
- Config file structure (`config.toml` + `pydantic-settings`)
- Logging with rotation (`loguru`)

**Avoids:** Pitfall 1 (rate limits), Pitfall 2 (token expiry), Pitfall 7 (HTTP 200 errors), Pitfall 8 (KST timezone), Pitfall 13 (hardcoded secrets), Pitfall 15 (log rotation)

### Phase 2: Trailing Stop Engine

**Rationale:** The core algorithm and its persistence layer. Can be fully unit-tested against mock prices without live KIS API. Must be correct before order execution is wired in.

**Delivers:** Trailing stop logic with persisted high-water marks and dry-run mode. The bot can be run in dry-run against live prices to validate logic before any real orders are placed.

**Addresses features:**
- Per-symbol trailing high-water mark tracking
- Drop percentage calculation and sell-signal emission
- High-water mark persistence (`state.json`, atomic writes)
- Startup warmup period (no sell trigger on first tick)
- Dry-run mode (log "would sell" without calling order API)
- Per-symbol threshold configuration (low effort, high value — add here)
- Manual initial peak override in config

**Avoids:** Pitfall 3 (동시호가 false trigger), Pitfall 4 (peak lost on restart), Pitfall 12 (false startup trigger)

### Phase 3: Order Execution

**Rationale:** Connects the sell signal to real KIS order submission. Must be built behind the dry-run flag established in Phase 2 and validated in KIS paper trading (모의투자) before using production credentials.

**Delivers:** Live sell order submission with idempotency guard, correct quantity handling, fill confirmation, and error-state alerting.

**Addresses features:**
- Market-sell order execution (`시장가 매도`)
- `ord_psbl_qty` (not `hldg_qty`) for sell quantity
- `SELL_PENDING` state flag to prevent duplicate orders
- Order fill confirmation with status polling
- Error handling for 매매 정지, partial fills, network interruptions
- `tr_id` constants keyed by environment (mock vs. real)
- Exponential backoff retry on transient failures

**Avoids:** Pitfall 5 (order failure / partial fill), Pitfall 6 (network interruption / duplicate order), Pitfall 10 (mock vs. real tr_id mismatch), Pitfall 11 (hldg_qty vs. ord_psbl_qty)

### Phase 4: Notifications and Operational Polish

**Rationale:** Adds the user-facing notification channel and operational reliability features. Non-critical for correctness but important for daily usability and incident awareness.

**Delivers:** Sell notifications (Telegram primary, KakaoTalk optional), trade history log, startup/shutdown summary messages, and watchdog alerting for sustained API failures.

**Addresses features:**
- Sell notification on execution (Telegram or KakaoTalk)
- Async notification pattern (order first, notify second)
- Trade history log (append-only JSONL)
- KRX holiday handling (local list or KIS holiday API)
- Operator alerting on token refresh failure or sustained network loss

**Avoids:** Pitfall 14 (blocking notification call delays sell execution)

### Phase Ordering Rationale

- **Layer dependency**: Auth Manager and KIS API Client are foundations for every feature; correctness there protects all upstream logic.
- **Risk sequencing**: The three silent-failure modes (token expiry, HTTP-200 errors, rate limits) are grouped in Phase 1 so they cannot hide behind later complexity.
- **Test isolation**: Phase 2 is fully unit-testable without KIS API; Phase 3 uses KIS paper trading (모의투자) before production keys are ever used.
- **Dry-run gate**: Phase 2 establishes dry-run mode before Phase 3 connects real orders — this is the safety gate for all live testing.
- **Notification is last**: Notification failure must never block order execution; building it last reinforces that ordering discipline.

### Research Flags

Phases needing verification against current KIS Developers portal before implementation:

- **Phase 1 (KIS API Client):** Verify current OAuth2 endpoint URL, token TTL, and exact rate limits for real vs. mock accounts. Training data is MEDIUM confidence on these specifics. Also confirm `python-kis` v4.x is still actively maintained (`pip index versions python-kis`, check GitHub last commit).
- **Phase 3 (Order Execution):** Verify current `tr_id` values for sell orders in production (`TTTC0801U`) and paper trading (`VTTC0801U`). These are documented in KIS Developers portal and may change.
- **Phase 4 (KakaoTalk):** If KakaoTalk is chosen over Telegram, verify current OAuth 2.0 refresh token expiry and "나에게 보내기" API endpoint before implementing. Do not rely on community SDK.

Phases with standard, well-documented patterns (research-phase can be skipped):

- **Phase 2 (Trailing Stop Engine):** Pure Python logic; the algorithm and JSON persistence pattern are straightforward and implementation-defined.
- **Phase 4 (Telegram):** `python-telegram-bot 21.x` documentation is comprehensive and stable.

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | MEDIUM | Core Python ecosystem choices (loguru, pydantic-settings, APScheduler) are HIGH confidence. `python-kis` version and API surface is MEDIUM — verify on PyPI and GitHub before pinning. |
| Features | MEDIUM | KIS API constraints (token TTL, rate limits, order endpoints) are MEDIUM — drawn from training data and community patterns, not live portal verification. Core feature set is HIGH confidence. |
| Architecture | MEDIUM | Layer structure and patterns are HIGH confidence as general software design. KIS-specific details (WebSocket approval flow, exact endpoint paths) are MEDIUM. |
| Pitfalls | HIGH | Token expiry, rate limits, market hours edge cases, and high-water mark persistence are well-documented operational failure modes consistent across multiple training data sources. |

**Overall confidence:** MEDIUM

### Gaps to Address

- **`python-kis` version and API surface:** Run `pip index versions python-kis` and check `https://github.com/Soju06/python-kis` for last commit date and v4.x changelog before committing to this library. If unmaintained, fall back to `httpx` direct REST calls.
- **KIS REST rate limits:** Documented as ~20 req/sec for real accounts, ~5 req/sec for mock. Verify against current KIS Developers portal — the gap between mock and real rate limits is critical for test-to-production transition.
- **KIS OAuth2 endpoint and token TTL:** Confirm `POST /oauth2/tokenP` path and `expires_in: 86400` against current portal. Token TTL determines proactive refresh timing.
- **`tr_id` values:** Confirm sell `tr_id` values for production (`TTTC0801U`) and paper trading (`VTTC0801U`) before Phase 3. Wrong `tr_id` in production is a silent failure.
- **KIS KSX holiday API:** If using the KIS holiday API endpoint rather than a local list, find the endpoint path in the portal during Phase 1 research.

---

## Sources

### Primary (HIGH confidence)
- KIS Developers Portal: `https://apiportal.koreainvestment.com` — OAuth2 flow, endpoint structure, token TTL
- KIS official GitHub: `https://github.com/koreainvestment/open-trading-api` — `tr_id` values, request/response schemas
- KRX market rules (stable, long-documented): trading hours, 동시호가 periods, settlement rules

### Secondary (MEDIUM confidence)
- `python-kis` GitHub: `https://github.com/Soju06/python-kis` — wrapper API surface, community usage patterns
- `python-kis` PyPI: `https://pypi.org/project/python-kis/` — version verification needed
- Korean developer community patterns — rate limit behavior, KIS error code catalog, mock vs. real account differences

### Tertiary (LOW confidence / needs validation)
- KakaoTalk Developers API: `https://developers.kakao.com/docs/latest/ko/kakaotalk-channel/common` — "나에게 보내기" endpoint; refresh token expiry behavior needs live verification
- KIS WebSocket protocol details — reconnection behavior extrapolated from general WebSocket patterns + community reports

---

## Stack (recommended technologies with brief rationale)

| Technology | Purpose | Rationale |
|------------|---------|-----------|
| `python-kis 4.x` | KIS API client | Community-standard wrapper; handles OAuth token refresh, price/balance/order endpoints |
| `Python 3.11/3.12` | Runtime | Stable LTS; 3.11+ required for stdlib `tomllib` |
| `pydantic-settings 2.x` | Typed config from `.env` | Validates secrets and config at startup before market open |
| `tomllib` (stdlib) | `config.toml` trading rules | No extra dependency; human-readable; avoids YAML implicit type coercion bugs |
| `APScheduler 3.10.x` | Market-hours gating | KST-aware cron triggers; in-process (no daemon) |
| `loguru 0.7.x` | Logging + rotation | Zero boilerplate; automatic daily rotation; permanent trade log filter |
| `python-telegram-bot 21.x` | Push notifications | Simpler than KakaoTalk for headless bot; no 30-day OAuth refresh complexity |
| `httpx 0.27.x` | Async HTTP fallback | Async-native; used if bypassing `python-kis` for specific endpoints |
| `zoneinfo` (stdlib 3.9+) | KST timezone | Use `ZoneInfo("Asia/Seoul")` — never naive datetime or manual UTC+9 offset |

---

## Table Stakes

Must-have for v1. Absence makes the bot unreliable or dangerous:

- KIS OAuth 2.0 token management with automatic 24h refresh and disk cache
- Current price polling per symbol with rate-aware throttling
- Per-symbol trailing high-water mark tracking persisted to `state.json`
- Drop percentage calculation: `(peak - price) / peak >= threshold`
- Market-sell order execution using `ord_psbl_qty` (sellable quantity)
- Dry-run mode active before any live execution
- Watchlist config with per-symbol threshold overrides
- Market hours gate: `09:00 <= now < 15:20 KST`, weekdays only
- API response validation: check `rt_cd == "0"`, reject `stck_prpr == "0"`
- Exponential backoff retry on transient API failures
- Trade history log (append-only JSONL)
- Secrets in `.env` gitignored from first commit

---

## Watch Out For

Top 5 critical pitfalls that cause silent losses or complete bot failure:

1. **HTTP 200 errors silently ignored** — KIS API returns `rt_cd: "1"` inside HTTP 200 responses. Naive `status_code == 200` check treats all errors as success. `stck_prpr == "0"` in an error response immediately triggers the trailing stop. Fix: always check `rt_cd == "0"` in the API client wrapper before any caller sees the data.

2. **Access token expires mid-session without alerting** — 24h token TTL combined with a rate-limited token endpoint (~1 req/min) means naive "refresh on 401" patterns lock the bot out of re-authentication. Fix: cache token with `expires_at`; proactively refresh at 08:30 KST daily; never call token endpoint per-request.

3. **High-water mark lost on any restart** — crash, reboot, or manual restart resets peak to current price, silently widening the effective stop-loss without any indication. Fix: atomic write to `state.json` on every peak update; load on startup; log loaded values explicitly.

4. **동시호가 false triggers** — bot started before 09:00 KST receives indicative (not real) prices from the pre-open auction period; a sell triggered at 08:55 on phantom data is a real market order. Fix: active monitoring window is strictly `09:00 <= now < 15:20 KST`.

5. **Duplicate sell orders on network retry** — a network interruption after an order is submitted but before the response is received causes the bot to retry, potentially submitting two full-quantity sell orders. Fix: persist `SELL_PENDING` flag per symbol; query open orders before retrying; never re-submit without confirming the first order's status.

---

## Build Order

Recommended phase sequence (each phase testable independently):

1. **Foundation + KIS API Client** — Config, secrets, logging, auth token management, price/balance query wrappers with `rt_cd` checking and rate limiting. Testable: can authenticate and fetch live prices.

2. **Trailing Stop Engine** — High-water mark tracking with `state.json` persistence, drop calculation, dry-run sell signal emission, startup warmup period. Testable: unit tests against mock prices; dry-run against live prices.

3. **Order Execution** — Live sell order submission with idempotency guard, `ord_psbl_qty` usage, fill confirmation, environment-keyed `tr_id` constants. Testable: end-to-end in KIS paper trading (모의투자) before production credentials.

4. **Scheduler + Notifications** — Market-hours orchestration (APScheduler), Telegram/KakaoTalk sell alerts (async, order-first), KRX holiday handling, watchdog alerting for sustained failures. Testable: full market-hours run in paper trading.

---

## Open Questions

Items requiring verification against current KIS Developers portal before implementation:

- Is `python-kis 4.x` still actively maintained? Check `pip index versions python-kis` and last commit date on GitHub.
- Current `tr_id` values for domestic sell orders: production (`TTTC0801U`?) and paper trading (`VTTC0801U`?)? Confirm in portal.
- Exact OAuth2 token endpoint path and `expires_in` value for current KIS API version.
- Real-account vs. mock-account REST rate limits — confirm the ~20 req/sec / ~5 req/sec figures.
- KIS holiday API endpoint path, if using API-based holiday detection rather than a local calendar list.
- KakaoTalk "나에게 보내기" OAuth refresh token expiry — is it still 30 days? Relevant only if KakaoTalk is chosen over Telegram.

---
*Research completed: 2026-04-06*
*Ready for roadmap: yes*
