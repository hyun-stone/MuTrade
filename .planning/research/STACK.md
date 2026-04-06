# Technology Stack

**Project:** MuTrade — 자동 트레일링 스탑 트레이딩 봇
**Domain:** Personal automated stock trading bot (Korea Investment & Securities / KIS API)
**Researched:** 2026-04-06
**Knowledge cutoff:** August 2025 (web search unavailable — all findings from training data; see Confidence Notes)

---

## Recommended Stack

### KIS API Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-kis` | 4.x (latest on PyPI) | KIS REST + WebSocket client | The most complete community wrapper for KIS Developers API. Covers OAuth token management, account inquiry, current price, order placement, and WebSocket real-time feeds. Actively maintained by Bhban (GitHub: `Soju06/python-kis`). Type-annotated, async-compatible. |

**How to install:**
```bash
pip install python-kis
```

**What it gives you:**
- `PyKis` client with automatic access-token refresh (tokens expire every 24 hours under KIS OAuth 2.0)
- `.fetch_price()` — current price of a domestic stock
- `.create_order()` — market/limit buy/sell
- `.fetch_balance()` — holdings query
- WebSocket subscription for real-time price/execution notifications

**Fallback (raw REST):** If `python-kis` API changes break something, the KIS REST API is plain HTTP + JSON. The underlying calls are well-documented at `https://apiportal.koreainvestment.com`. Fall back to `httpx` (async-native) or `requests` (sync) directly. This is always an option because KIS responses are straightforward JSON.

**Confidence: MEDIUM** — `python-kis` (Soju06) was the dominant community library as of mid-2025. Cannot verify current PyPI version without web access. Verify with `pip index versions python-kis` before pinning.

---

### Core Framework — Python Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11 or 3.12 | Runtime | 3.11 is the stable LTS target; 3.12 added minor perf improvements. Both are well-supported. Avoid 3.13 until ecosystem catches up. |

**Confidence: HIGH** — This is stable ecosystem knowledge.

---

### Real-Time Price: WebSocket vs Polling

**Decision: Start with polling, add WebSocket only if latency matters.**

For a trailing-stop bot that sells on a -10% drawdown from peak, the trigger latency requirement is loose — a 1–5 second poll is sufficient. A stock must drop 10% from its peak; this rarely happens in under 10 seconds. Polling is simpler, more debuggable, and avoids WebSocket reconnection complexity.

**Polling approach (recommended):**

```python
# asyncio + httpx pattern
import asyncio
import httpx

async def poll_prices(symbols: list[str], interval_seconds: float = 3.0):
    async with httpx.AsyncClient() as client:
        while True:
            for symbol in symbols:
                price = await fetch_price(client, symbol)
                check_trailing_stop(symbol, price)
            await asyncio.sleep(interval_seconds)
```

Use `asyncio` for the main loop with `asyncio.sleep()` between polls. This avoids blocking and uses a single thread efficiently for a small watchlist (< 30 symbols).

**WebSocket approach (future upgrade):**

`python-kis` exposes a WebSocket subscription that pushes real-time execution confirmations and price ticks (체결가). This is useful if you later need sub-second reaction time or want push-based sell confirmations. KIS WebSocket uses a custom binary protocol that `python-kis` handles internally.

Use KIS WebSocket for:
- Real-time execution (체결) confirmation after a sell order
- Reducing API call count if watchlist grows beyond ~20 symbols

KIS imposes rate limits: roughly 20 requests/second for REST price queries. With polling every 3 seconds per symbol, 20 symbols = ~7 req/s, well within limits.

**Confidence: HIGH** — KIS rate limits and the trailing-stop latency argument are well-established.

---

### Scheduling / Process Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `APScheduler` | 3.10.x | Schedule market-hours window (09:00–15:30 KST) | Mature, no daemon required, works in-process. `CronTrigger` handles the 09:00 start; a simple `datetime.now()` check handles the 15:30 stop. |
| `systemd` (Linux) or `launchd` (macOS) | OS-provided | Keep the process alive across reboots | For always-on server deployment. On macOS dev machine, a launchd plist is sufficient. |

**Alternative rejected — `schedule` library:** Simpler API but lacks timezone-aware scheduling and has no async support. KST (UTC+9) handling requires explicit timezone; `APScheduler` handles this natively with `timezone='Asia/Seoul'`.

**Alternative rejected — `cron` (system-level):** Starting/stopping the Python process via cron is fragile — token state is lost on restart, and there's no graceful shutdown handling. Keep the process running 24/7; use in-process scheduling to pause monitoring outside market hours.

**Recommended pattern:**
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

KST = pytz.timezone('Asia/Seoul')
scheduler = AsyncIOScheduler(timezone=KST)
scheduler.add_job(start_monitoring, CronTrigger(hour=9, minute=0, timezone=KST))
scheduler.add_job(stop_monitoring,  CronTrigger(hour=15, minute=30, timezone=KST))
```

**Confidence: HIGH** — APScheduler 3.x is stable and the pattern is standard.

---

### Notification

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-telegram-bot` | 21.x | Push notifications to Telegram | Telegram Bot API is the easiest personal notification channel in 2025: free, no approval process, instant setup. Send a message on sell execution. |
| `kakao-python-sdk` (unofficial) or direct REST | N/A | KakaoTalk notification (optional) | KakaoTalk is the PROJECT.md requirement. See notes below. |

**KakaoTalk — important caveats (MEDIUM confidence):**

KakaoTalk "나에게 보내기" (send-to-self) uses the Kakao REST API (`https://kapi.kakao.com/v2/api/talk/memo/default/send`). It requires:
1. A Kakao Developers app registration
2. OAuth 2.0 user token (requires browser login to generate initially)
3. Token refresh every 30 days (refresh token expiry)

The refresh-token management adds operational complexity for a headless bot. There is no official Python SDK from Kakao — the community library `kakaotalk-api` or `python-kakao` exists but has inconsistent maintenance.

**Recommendation:** Use Telegram as primary notification. It is more operationally robust for a headless bot. If KakaoTalk is a hard requirement, implement direct REST calls to the Kakao API and store refresh tokens in the secrets file — do not rely on a community SDK.

**Telegram setup** (2 minutes):
1. Create a bot via @BotFather → get `TELEGRAM_BOT_TOKEN`
2. Get your chat ID via `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Send message: `await bot.send_message(chat_id=CHAT_ID, text="...")`

```python
from telegram import Bot
bot = Bot(token=os.environ["TELEGRAM_BOT_TOKEN"])
await bot.send_message(chat_id=CHAT_ID, text=f"[MuTrade] 매도 실행: {symbol} @ {price}원")
```

**Confidence: HIGH** for Telegram. **MEDIUM** for KakaoTalk operational complexity.

---

### Configuration and Secrets Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-dotenv` | 1.0.x | Load `.env` file into `os.environ` | Simple, zero-dependency pattern. Secrets in `.env` (gitignored), code reads from `os.environ`. |
| `pydantic-settings` | 2.x | Typed config with validation | `BaseSettings` reads from env vars + `.env` and validates types at startup. Catches misconfiguration before market open. Prefer over raw `os.environ` dict access. |
| TOML config file (`config.toml`) | stdlib (`tomllib` in 3.11+) | Per-symbol trading rules | Which symbols to monitor, custom trailing-stop percentages per symbol, optional manual peak price overrides. Use TOML (human-readable) over JSON for config that users edit. `tomllib` is stdlib in Python 3.11+, no extra install. |

**Pattern:**
```
.env                    ← secrets (APP_KEY, APP_SECRET, ACCOUNT_NO, TELEGRAM_BOT_TOKEN)
config.toml             ← trading rules (symbols, thresholds, etc.)
settings.py             ← pydantic BaseSettings reading .env
```

```python
# settings.py
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    app_key: str
    app_secret: str
    account_no: str
    telegram_bot_token: str
    telegram_chat_id: str

    class Config:
        env_file = ".env"
```

```toml
# config.toml
[symbols]
"005930" = { name = "삼성전자", trailing_stop_pct = 10.0, peak_override = null }
"000660" = { name = "SK하이닉스", trailing_stop_pct = 8.0, peak_override = null }
```

**What NOT to use:** `configparser` (INI format) — no native type coercion, ugly for nested config. `yaml` — requires `PyYAML` dependency and YAML's implicit type coercion causes subtle bugs (e.g., `yes` → `True`).

**Confidence: HIGH** — pydantic-settings 2.x and python-dotenv 1.x are the current standard Python pattern.

---

### Logging

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `loguru` | 0.7.x | Application logging | Single-import, structured output, automatic file rotation, built-in exception formatting. Replaces stdlib `logging` boilerplate entirely. For a personal bot, `loguru` eliminates 30+ lines of handler setup. |

**Configuration:**
```python
from loguru import logger

logger.add(
    "logs/mutrade_{time:YYYY-MM-DD}.log",
    rotation="1 day",
    retention="30 days",
    level="INFO",
    encoding="utf-8",
)
logger.add(
    "logs/trades.log",           # permanent trade history
    filter=lambda r: "TRADE" in r["extra"],
    retention=None,
    encoding="utf-8",
)

# Usage
logger.info("모니터링 시작: {symbols}", symbols=watchlist)
logger.bind(TRADE=True).info("매도 실행 | {symbol} | 가격: {price} | 수량: {qty}", ...)
```

**What NOT to use:** stdlib `logging` — verbose setup, no built-in rotation without `RotatingFileHandler` boilerplate. `structlog` — excellent for services but overkill for a personal CLI bot.

**Confidence: HIGH** — loguru 0.7.x is stable and widely adopted.

---

### HTTP Client (underlying REST calls)

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | 0.27.x | Async HTTP for direct KIS REST calls | If bypassing `python-kis` for specific endpoints or fallback. `httpx` is async-native, has connection pooling, and is compatible with `asyncio`. Prefer over `aiohttp` for new code (simpler API). |
| `requests` | 2.31.x | Sync HTTP (test scripts / one-offs) | Fine for debugging and one-off token generation scripts. Not for the main async loop. |

**Confidence: HIGH** — httpx 0.27.x is current and stable.

---

### Async Runtime

Use `asyncio` from stdlib. Do NOT add `trio` or `anyio` — they add complexity without benefit for this single-application use case. The bot's concurrency requirement is simple: poll N symbols in sequence with sleep intervals.

---

## Full Dependency List

```toml
# pyproject.toml (pip-installable)
[project]
requires-python = ">=3.11"
dependencies = [
    "python-kis>=4.0",          # KIS API client — verify latest version on PyPI
    "httpx>=0.27",              # async HTTP (fallback / direct calls)
    "pydantic-settings>=2.0",   # typed config from .env
    "python-dotenv>=1.0",       # .env file loading
    "apscheduler>=3.10",        # market-hours scheduling
    "loguru>=0.7",              # logging
    "python-telegram-bot>=21.0",# notifications
    "pytz>=2024.1",             # timezone handling (KST)
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-mock>=3.12",
]
```

---

## What NOT to Use

| Category | Avoid | Why |
|----------|-------|-----|
| KIS client | `mojito` (mojito2) | Older community library targeting multiple brokers. Heavier abstraction, last active maintenance was 2023, KIS API v2 changes may not be reflected. |
| KIS client | Hand-rolling OAuth from scratch | KIS OAuth access-token refresh is non-trivial (24h expiry, needs re-auth). `python-kis` solves this. Only go raw if `python-kis` becomes unmaintained. |
| Notification | LINE Notify | LINE Notify API was **shut down on March 31, 2025**. Do not use. |
| Notification | Slack | Requires workspace setup; overkill for personal bot. Bot token setup is more complex than Telegram. |
| Scheduling | `celery` | Distributed task queue — massive overkill for a single-process personal bot. Adds Redis/RabbitMQ dependency. |
| Scheduling | `rq` (Redis Queue) | Same problem as Celery — needs Redis. |
| Config | `yaml` / PyYAML | Implicit type coercion bugs (e.g., stock codes starting with `0` may be parsed as integers). Use TOML. |
| Config | Hardcoded credentials | PROJECT.md constraint: all secrets via env vars or separate file. |
| Process mgmt | `supervisord` | Outdated. Use systemd (Linux) or launchd (macOS). |
| Database | SQLite / SQLAlchemy | Unnecessary for v1. A structured log file (loguru) is sufficient for trade history. Add SQLite only if querying trade history becomes a need. |
| Framework | FastAPI / Flask | No web server needed. The bot is a CLI process, not a service. Adding HTTP adds attack surface and complexity. |

---

## Confidence Notes

**Important:** All web search and WebFetch tools were unavailable during this research session. All findings are from training data with knowledge cutoff of August 2025. The following confidence assessments reflect training-data quality only.

| Area | Confidence | Verification Action Required |
|------|------------|------------------------------|
| `python-kis` as primary KIS client | MEDIUM | Run `pip index versions python-kis` and check GitHub `Soju06/python-kis` for last commit date and v4.x changelog |
| KIS REST API structure (OAuth, endpoints) | HIGH | Stable API; confirm at `https://apiportal.koreainvestment.com` |
| LINE Notify shutdown (March 2025) | HIGH | Announced by LINE Corp well before knowledge cutoff |
| KakaoTalk OAuth refresh complexity | HIGH | This is a known operational pain point documented in Korean dev communities |
| Telegram Bot API stability | HIGH | Long-stable API, `python-telegram-bot` v21 released 2024 |
| APScheduler 3.10.x API | HIGH | Stable for 3+ years |
| loguru 0.7.x API | HIGH | Stable for 3+ years |
| pydantic-settings 2.x | HIGH | Released 2023, API stable |
| KIS WebSocket protocol | MEDIUM | Confirm WebSocket endpoint details in KIS Developers portal; protocol may have changed since training data |
| KIS rate limits (~20 req/s) | MEDIUM | Verify current limits in KIS Developers API documentation |

---

## Sources

All findings are from training data. Verification URLs:

- KIS Developers portal: `https://apiportal.koreainvestment.com`
- `python-kis` GitHub: `https://github.com/Soju06/python-kis`
- `python-kis` PyPI: `https://pypi.org/project/python-kis/`
- APScheduler docs: `https://apscheduler.readthedocs.io/en/3.x/`
- pydantic-settings docs: `https://docs.pydantic.dev/latest/concepts/pydantic_settings/`
- python-telegram-bot docs: `https://python-telegram-bot.org/`
- loguru docs: `https://loguru.readthedocs.io/`
- LINE Notify shutdown announcement: `https://notify-bot.line.me/closing-announce`
