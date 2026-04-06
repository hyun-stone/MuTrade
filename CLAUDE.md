<!-- GSD:project-start source:PROJECT.md -->
## Project

**MuTrade — 자동 트레일링 스탑 트레이딩 봇**

한국투자증권 API를 활용한 개인용 자동 주식 매도 프로그램이다. 사용자가 선택한 보유 종목을 시장 운영 시간(09:00~15:30) 동안 실시간으로 모니터링하여, 고점 대비 10% 이상 하락하면 즉시 시장가로 자동 매도한다. 매도 실행 시 알림과 로그를 통해 결과를 기록한다.

**Core Value:** 조건 충족 시 사람의 개입 없이 즉시 자동 매도하여 손실을 방어한다.

### Constraints

- **API**: 한국투자증권 KIS Developers API만 사용
- **운영 환경**: 시장 시간 내 안정적 실행 가능한 로컬 또는 서버 환경 필요
- **보안**: API 키, 앱 시크릿 등 민감 정보는 환경변수 또는 별도 설정 파일로 분리
<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->
## Technology Stack

## Recommended Stack
### KIS API Client
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-kis` | 4.x (latest on PyPI) | KIS REST + WebSocket client | The most complete community wrapper for KIS Developers API. Covers OAuth token management, account inquiry, current price, order placement, and WebSocket real-time feeds. Actively maintained by Bhban (GitHub: `Soju06/python-kis`). Type-annotated, async-compatible. |
- `PyKis` client with automatic access-token refresh (tokens expire every 24 hours under KIS OAuth 2.0)
- `.fetch_price()` — current price of a domestic stock
- `.create_order()` — market/limit buy/sell
- `.fetch_balance()` — holdings query
- WebSocket subscription for real-time price/execution notifications
### Core Framework — Python Runtime
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11 or 3.12 | Runtime | 3.11 is the stable LTS target; 3.12 added minor perf improvements. Both are well-supported. Avoid 3.13 until ecosystem catches up. |
### Real-Time Price: WebSocket vs Polling
# asyncio + httpx pattern
- Real-time execution (체결) confirmation after a sell order
- Reducing API call count if watchlist grows beyond ~20 symbols
### Scheduling / Process Management
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `APScheduler` | 3.10.x | Schedule market-hours window (09:00–15:30 KST) | Mature, no daemon required, works in-process. `CronTrigger` handles the 09:00 start; a simple `datetime.now()` check handles the 15:30 stop. |
| `systemd` (Linux) or `launchd` (macOS) | OS-provided | Keep the process alive across reboots | For always-on server deployment. On macOS dev machine, a launchd plist is sufficient. |
### Notification
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-telegram-bot` | 21.x | Push notifications to Telegram | Telegram Bot API is the easiest personal notification channel in 2025: free, no approval process, instant setup. Send a message on sell execution. |
| `kakao-python-sdk` (unofficial) or direct REST | N/A | KakaoTalk notification (optional) | KakaoTalk is the PROJECT.md requirement. See notes below. |
### Configuration and Secrets Management
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-dotenv` | 1.0.x | Load `.env` file into `os.environ` | Simple, zero-dependency pattern. Secrets in `.env` (gitignored), code reads from `os.environ`. |
| `pydantic-settings` | 2.x | Typed config with validation | `BaseSettings` reads from env vars + `.env` and validates types at startup. Catches misconfiguration before market open. Prefer over raw `os.environ` dict access. |
| TOML config file (`config.toml`) | stdlib (`tomllib` in 3.11+) | Per-symbol trading rules | Which symbols to monitor, custom trailing-stop percentages per symbol, optional manual peak price overrides. Use TOML (human-readable) over JSON for config that users edit. `tomllib` is stdlib in Python 3.11+, no extra install. |
# settings.py
# config.toml
### Logging
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `loguru` | 0.7.x | Application logging | Single-import, structured output, automatic file rotation, built-in exception formatting. Replaces stdlib `logging` boilerplate entirely. For a personal bot, `loguru` eliminates 30+ lines of handler setup. |
# Usage
### HTTP Client (underlying REST calls)
| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | 0.27.x | Async HTTP for direct KIS REST calls | If bypassing `python-kis` for specific endpoints or fallback. `httpx` is async-native, has connection pooling, and is compatible with `asyncio`. Prefer over `aiohttp` for new code (simpler API). |
| `requests` | 2.31.x | Sync HTTP (test scripts / one-offs) | Fine for debugging and one-off token generation scripts. Not for the main async loop. |
### Async Runtime
## Full Dependency List
# pyproject.toml (pip-installable)
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
## Confidence Notes
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
## Sources
- KIS Developers portal: `https://apiportal.koreainvestment.com`
- `python-kis` GitHub: `https://github.com/Soju06/python-kis`
- `python-kis` PyPI: `https://pypi.org/project/python-kis/`
- APScheduler docs: `https://apscheduler.readthedocs.io/en/3.x/`
- pydantic-settings docs: `https://docs.pydantic.dev/latest/concepts/pydantic_settings/`
- python-telegram-bot docs: `https://python-telegram-bot.org/`
- loguru docs: `https://loguru.readthedocs.io/`
- LINE Notify shutdown announcement: `https://notify-bot.line.me/closing-announce`
<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->
## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->
## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:workflow-start source:GSD defaults -->
## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:
- `/gsd:quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd:debug` for investigation and bug fixing
- `/gsd:execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->



<!-- GSD:profile-start -->
## Developer Profile

> Profile not yet configured. Run `/gsd:profile-user` to generate your developer profile.
> This section is managed by `generate-claude-profile` -- do not edit manually.
<!-- GSD:profile-end -->
