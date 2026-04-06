# Phase 1: Foundation and KIS API Connectivity - Research

**Researched:** 2026-04-06
**Domain:** KIS REST API authentication, price polling, configuration management, scheduling
**Confidence:** MEDIUM-HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `python-kis 4.x`를 메인 KIS API 클라이언트로 사용한다. OAuth 토큰 관리, `fetch_price` / `create_order` / `fetch_balance` 메서드를 활용한다.
- **D-02:** python-kis가 지원하지 않는 엔드포인트(예: KRX 공휴일 확인용 KIS 시장 상태 API)는 `httpx`로 직접 호출하여 보완한다.
- **D-03:** 모의투자(paper trading)와 실계좌 전환은 `.env` 파일의 `KIS_MOCK=true/false` 환경변수로 관리한다. Phase 3 테스트 시 `.env`만 바꾸면 전환 가능하도록 한다.

### Claude's Discretion

- 동시성 모델(sync vs asyncio): Claude가 결정 — Phase 1은 단순 폴링 루프이므로 동기 구현이 적합하나, v2 WebSocket 업그레이드를 위한 async 래퍼 구조 여부는 구현 단계에서 판단.
- config.toml 스키마 세부 구조: Claude가 결정 — REQUIREMENTS.md의 CONF-03, ENG-04 기준 충족하는 방향으로 설계.
- KRX 공휴일 감지 방법: Claude가 결정 — `exchange_calendars` 라이브러리 또는 KIS 시장 상태 API 중 더 신뢰성 있는 방법 선택.
- 프로젝트 디렉터리 구조: Claude가 결정 — 단일 파일 vs 모듈 패키지.

### Deferred Ideas (OUT OF SCOPE)

None — 논의가 페이즈 범위 내에서 유지됨.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONF-01 | 시스템이 KIS OAuth 2.0 토큰을 취득하고 24시간 만료 전 자동 갱신한다 | python-kis PyKis(keep_token=True) handles token caching; access token TTL is 24h; token reissuance capped at once per minute |
| CONF-02 | API 키·시크릿 등 민감 정보를 .env 파일로 분리하고 .gitignore에 포함한다 | pydantic-settings BaseSettings with env_file=".env"; ValidationError at startup if required fields missing |
| CONF-03 | 사용자가 config.toml 파일로 모니터링 종목과 매도 조건을 설정할 수 있다 | Python 3.11+ tomllib (stdlib); schema design at Claude's discretion |
| CONF-04 | 시스템이 KRX 공휴일에는 모니터링을 자동으로 건너뛴다 | exchange_calendars 4.13.2, XKRX calendar, krx.is_session(date) — recommended over httpx KIS API call |
| FEED-01 | 시스템이 시장 운영 시간(09:00~15:20 KST) 중에만 가격을 폴링한다 | APScheduler 3.11.2 CronTrigger with timezone='Asia/Seoul'; inner loop checks datetime.now() for 15:20 cutoff |
| FEED-02 | 시스템이 설정된 종목의 현재가를 3~5초 간격으로 조회한다 | kis.stock(symbol).quote() returns KisDomesticQuote; time.sleep(N) between symbols in sync loop |
| FEED-03 | 시스템이 KIS API 레이트 리밋을 초과하지 않도록 요청 간격을 조절한다 | KIS limit: 20 req/s (confirmed); EGW00201 = rate limit error; safe practice: 15 req/s target with per-request sleep |
| FEED-04 | 시스템이 KIS API 응답의 rt_cd 값을 확인하여 HTTP 200 내 에러를 올바르게 처리한다 | KisAPIError carries rt_cd field; catch KisAPIError, log error, do NOT propagate price=0 |
</phase_requirements>

---

## Summary

python-kis의 현재 PyPI 최신 버전은 **2.1.6**이다. CLAUDE.md의 "4.x"는 과거 버전 체계 오류로 추정되며, 실제로는 v2.0.0에서 완전 재설계된 후 현재 2.1.x 계열이 활발히 유지되고 있다. Python 3.10+ 필수이며, 로컬 환경의 Python 3.9.6은 요구사항을 충족하지 않으므로 Python 3.11 또는 3.12 환경이 필요하다.

KIS OAuth access token TTL은 **24시간**이다(갱신 발급 주기 최소 1분, 서비스 기간 1년). python-kis의 `keep_token=True` 옵션이 토큰 파일 캐시와 자동 갱신을 처리한다. **중요한 발견:** 모의투자(virtual) 계좌는 실전 계좌와 **별도의 AppKey/AppSecret**이 필요하다. `KIS_MOCK=true/false`로 전환하려면 두 쌍의 자격증명을 `.env`에 모두 포함시켜야 한다.

KRX 공휴일 처리는 `exchange_calendars` 라이브러리(최신 4.13.2, XKRX 캘린더 지원)로 오프라인 처리하는 것이 httpx로 KIS API를 직접 호출하는 것보다 신뢰성이 높다. KIS API 레이트 리밋은 초당 20건(실전) / 더 낮음(모의)이며, 안전 마진으로 15 req/s 이하를 권장한다.

**Primary recommendation:** python-kis 2.1.6을 `pip install python-kis`로 설치하고, Python 3.11+ 환경에서 `PyKis(keep_token=True)`로 초기화하며, `exchange_calendars`로 KRX 공휴일을 처리하고, `pydantic-settings`로 `.env` 검증을 수행한다.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-kis` | 2.1.6 | KIS REST + WebSocket 클라이언트 | OAuth 토큰 자동 갱신, quote/order/balance API 제공, 타입 힌트 완비. v2.0.0에서 완전 재설계됨. |
| Python | 3.11 or 3.12 | Runtime | python-kis requires >=3.10; 3.11 adds tomllib stdlib; 3.12 minor perf gains |
| `pydantic-settings` | 2.13.1 | .env 로드 + 타입 검증 | BaseSettings가 startup 시 누락 필드를 ValidationError로 잡아줌 |
| `python-dotenv` | 1.2.2 | .env 파일 로드 | pydantic-settings가 내부적으로 사용; 직접 사용 가능 |
| `loguru` | 0.7.3 | 구조화 로깅 + 파일 로테이션 | 단일 import, 설정 30줄 → 1줄 |
| `APScheduler` | 3.11.2 | 시장 시간 스케줄링 | CronTrigger + timezone='Asia/Seoul' 지원 |
| `exchange_calendars` | 4.13.2 | KRX 공휴일 판정 | XKRX 캘린더 내장, is_session() 메서드, 오프라인 동작 |
| `httpx` | 0.28.1 | KIS 미지원 엔드포인트 직접 호출 | D-02 결정에 따라 python-kis 보완용 |
| `tomllib` | stdlib (3.11+) | config.toml 파싱 | 외부 의존 없음 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytz` or `zoneinfo` | stdlib (3.9+) | KST timezone 처리 | `zoneinfo` 모듈이 3.9+에 내장됨. `ZoneInfo("Asia/Seoul")` |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `exchange_calendars` | httpx + KIS 시장 상태 API | KIS API는 인터넷 의존, 외부 장애 위험. exchange_calendars는 오프라인 동작, 갱신 주기도 빠름 (v4.13.2 = 2026-03 릴리즈) |
| Sync polling loop | asyncio + httpx | Phase 1 심플 폴링 20종목 이하에는 sync가 충분; async는 WebSocket v2 업그레이드 시 고려 |

**Installation:**
```bash
pip install python-kis==2.1.6 pydantic-settings==2.13.1 python-dotenv==1.2.2 \
            loguru==0.7.3 APScheduler==3.11.2 exchange-calendars==4.13.2 httpx==0.28.1
```

**Version verification (2026-04-06):**
- python-kis: 2.1.6 (released Oct 2025, confirmed via PyPI JSON API)
- exchange-calendars: 4.13.2 (released Mar 10, 2026, includes 2025 Presidential election holiday)
- pydantic-settings: 2.13.1
- APScheduler: 3.11.2
- loguru: 0.7.3
- python-dotenv: 1.2.2
- httpx: 0.28.1

> **CRITICAL NOTE:** CLAUDE.md references `python-kis 4.x` — this version does NOT exist on PyPI. The current latest is **2.1.6**. The library underwent a complete redesign at v2.0.0 (August 2024). All API patterns below are based on v2.x. The `fetch_price()` method referenced in CLAUDE.md is now `stock.quote()` in v2.x.

---

## Architecture Patterns

### Recommended Project Structure

```
mutrade/
├── main.py                  # Entry point: init + start scheduler
├── settings.py              # pydantic-settings BaseSettings
├── config.toml              # User-editable: symbols, thresholds
├── .env                     # Secrets (gitignored)
├── .env.example             # Template committed to git
├── .gitignore
├── pyproject.toml           # Dependencies
├── kis/
│   ├── __init__.py
│   ├── client.py            # PyKis initialization, token management
│   └── price_feed.py        # Polling loop, rate limiter
├── monitor/
│   ├── __init__.py
│   ├── scheduler.py         # APScheduler setup, market hours
│   └── holiday.py           # exchange_calendars KRX check
├── config/
│   ├── __init__.py
│   └── loader.py            # tomllib config.toml loader + dataclasses
└── logs/
    └── .gitkeep
```

### Pattern 1: PyKis Client Initialization with Mock Switch

**What:** `.env`의 `KIS_MOCK=true/false`로 모의/실전 계좌를 선택해 별도 PyKis 인스턴스 생성

**When to use:** 봇 시작 시 settings 로드 후 1회 실행

**Critical finding:** 모의투자(virtual)는 실전과 별도 AppKey/AppSecret이 필요하다.

```python
# Source: python-kis README + KIS Developers community findings
from pykis import PyKis, KisAuth
from settings import Settings

def create_kis_client(settings: Settings) -> PyKis:
    if settings.kis_mock:
        # 모의투자: 별도 AppKey/AppSecret 필요 (virtual=True 계좌)
        return PyKis(
            id=settings.kis_virtual_id,
            account=settings.kis_virtual_account,
            appkey=settings.kis_virtual_appkey,
            secretkey=settings.kis_virtual_secretkey,
            virtual=True,          # python-kis에 모의투자임을 알림
            keep_token=True,       # 토큰 파일 캐시 + 자동 갱신
        )
    else:
        # 실전투자
        return PyKis(
            id=settings.kis_id,
            account=settings.kis_account,
            appkey=settings.kis_appkey,
            secretkey=settings.kis_secretkey,
            virtual=False,
            keep_token=True,
        )
```

### Pattern 2: pydantic-settings .env Validation

**What:** 봇 시작 시 모든 필수 환경변수를 타입 검증, 누락 시 즉시 실패

**When to use:** `main.py` 최상단, 모든 초기화 이전

```python
# Source: https://docs.pydantic.dev/latest/concepts/pydantic_settings/
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    # 실전투자 자격증명
    kis_id: str = Field(..., alias="KIS_ID")
    kis_account: str = Field(..., alias="KIS_ACCOUNT")
    kis_appkey: str = Field(..., alias="KIS_APPKEY")
    kis_secretkey: str = Field(..., alias="KIS_SECRETKEY")

    # 모의투자 자격증명 (KIS_MOCK=true 시 필수)
    kis_virtual_id: str | None = Field(None, alias="KIS_VIRTUAL_ID")
    kis_virtual_account: str | None = Field(None, alias="KIS_VIRTUAL_ACCOUNT")
    kis_virtual_appkey: str | None = Field(None, alias="KIS_VIRTUAL_APPKEY")
    kis_virtual_secretkey: str | None = Field(None, alias="KIS_VIRTUAL_SECRETKEY")

    kis_mock: bool = Field(False, alias="KIS_MOCK")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )
```

`.env` 파일 예시:
```bash
KIS_ID=your_hts_id
KIS_ACCOUNT=00000000-01
KIS_APPKEY=PSxxxxxxxxx
KIS_SECRETKEY=RRxxxxxxxxx

KIS_VIRTUAL_ID=your_hts_id
KIS_VIRTUAL_ACCOUNT=00000000-01
KIS_VIRTUAL_APPKEY=VSxxxxxxxxx
KIS_VIRTUAL_SECRETKEY=VRxxxxxxxxx

KIS_MOCK=false
```

### Pattern 3: KRX Holiday Check with exchange_calendars

**What:** 오늘이 KRX 거래일인지 오프라인으로 판정

**When to use:** APScheduler job 시작 시점에서 먼저 확인

```python
# Source: https://github.com/gerrymanoim/exchange_calendars
import exchange_calendars as xcals
from datetime import date

def is_krx_trading_day(today: date | None = None) -> bool:
    krx = xcals.get_calendar("XKRX")
    check_date = today or date.today()
    return krx.is_session(check_date.isoformat())
```

### Pattern 4: Price Polling Loop with Rate Limiting

**What:** 설정된 종목들을 3~5초 간격으로 폴링, 15 req/s 이하 유지

**When to use:** APScheduler가 시작한 polling job 내부

```python
# Source: python-kis README + KIS rate limit findings
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from loguru import logger
from pykis import KisAPIError

KST = ZoneInfo("Asia/Seoul")
MARKET_CLOSE = 15 * 60 + 20  # 15:20 in minutes since midnight
MIN_INTERVAL = 1.0 / 15       # 15 req/s = 66.7ms between requests

def poll_prices(kis, symbols: list[str]) -> dict[str, float]:
    """Poll current prices for all symbols. Returns {symbol: price}."""
    prices = {}
    for symbol in symbols:
        # 시장 마감 체크 (15:20 KST)
        now_kst = datetime.now(KST)
        current_minutes = now_kst.hour * 60 + now_kst.minute
        if current_minutes >= MARKET_CLOSE:
            logger.info("Market close time reached (15:20 KST). Stopping poll.")
            break

        try:
            quote = kis.stock(symbol).quote()
            price = float(quote.price)
            prices[symbol] = price
            logger.debug(f"{symbol}: {price}")
        except KisAPIError as e:
            # rt_cd != "0": HTTP 200 내 에러 — 절대 price=0 전달 금지
            logger.error(
                f"KIS API error for {symbol}: rt_cd={e.rt_cd}, "
                f"msg_cd={e.msg_cd}, msg={e.msg1}"
            )
            # prices[symbol] 에 넣지 않음 — 호출자가 누락 처리
        except Exception as e:
            logger.error(f"Unexpected error fetching {symbol}: {e}")

        time.sleep(MIN_INTERVAL)  # Rate limit guard

    return prices
```

### Pattern 5: APScheduler Market Hours Scheduling

**What:** 09:00 KST에 폴링 시작, 15:20는 내부 루프에서 처리

**When to use:** `main.py`에서 봇 초기화 후 scheduler 시작

```python
# Source: https://apscheduler.readthedocs.io/en/3.x/
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

def start_scheduler(poll_job_fn):
    scheduler = BlockingScheduler(timezone="Asia/Seoul")

    # 월~금 09:00 KST에 폴링 세션 시작
    scheduler.add_job(
        poll_job_fn,
        CronTrigger(
            day_of_week="mon-fri",
            hour=9,
            minute=0,
            timezone="Asia/Seoul",
        ),
        id="market_poll",
        name="KIS Market Price Poll",
    )

    logger.info("Scheduler started. Waiting for 09:00 KST (Mon-Fri)...")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped.")
```

### Pattern 6: config.toml Schema Design

**What:** 모니터링 종목과 개별 매도 임계값을 사람이 편집 가능한 TOML로 관리

**When to use:** 봇 시작 시 1회 로드 (Phase 2 ENG-04 요구사항도 충족)

```toml
# config.toml
[settings]
poll_interval_seconds = 3   # 3~5 사이 권장
trailing_stop_pct = 10.0    # 기본 하락률 임계값 (%)

[[symbols]]
code = "005930"             # 삼성전자
name = "삼성전자"
trailing_stop_pct = 10.0    # 개별 종목 임계값 (없으면 settings.trailing_stop_pct 사용)

[[symbols]]
code = "000660"             # SK하이닉스
name = "SK하이닉스"
# trailing_stop_pct 생략 → settings.trailing_stop_pct 적용
```

```python
# Source: Python 3.11+ stdlib tomllib docs
import tomllib
from dataclasses import dataclass, field

@dataclass
class SymbolConfig:
    code: str
    name: str
    trailing_stop_pct: float | None = None  # None = use global default

@dataclass
class AppConfig:
    poll_interval_seconds: int
    trailing_stop_pct: float
    symbols: list[SymbolConfig]

def load_config(path: str = "config.toml") -> AppConfig:
    with open(path, "rb") as f:
        raw = tomllib.load(f)

    global_pct = raw["settings"]["trailing_stop_pct"]
    symbols = [
        SymbolConfig(
            code=s["code"],
            name=s["name"],
            trailing_stop_pct=s.get("trailing_stop_pct"),  # may be absent
        )
        for s in raw.get("symbols", [])
    ]
    return AppConfig(
        poll_interval_seconds=raw["settings"]["poll_interval_seconds"],
        trailing_stop_pct=global_pct,
        symbols=symbols,
    )
```

### Anti-Patterns to Avoid

- **`fetch_price()` 호출:** v2.x에서 해당 메서드는 존재하지 않는다. `kis.stock(symbol).quote()`를 사용한다.
- **python-kis "4.x" pip install:** PyPI에 4.x 버전은 없다. `pip install python-kis`로 최신(2.1.6) 설치한다.
- **YAML 설정 파일:** 종목코드 "005930"이 정수 5930으로 파싱될 수 있다. 반드시 TOML을 사용한다.
- **모의투자에 실전 AppKey 사용:** KIS 서버가 자격증명 불일치로 OAuth 오류를 반환한다. 별도 키 발급 필요.
- **rt_cd 에러 시 price=0 전파:** 0 가격이 트레일링 스탑 엔진에서 100% 하락으로 인식되어 즉시 매도 트리거 가능. 에러 시 해당 심볼 skip 처리.
- **토큰 1분 내 재발급:** KIS 제한으로 실패한다. keep_token=True로 캐시 토큰 재사용.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OAuth token 캐시/갱신 | 커스텀 token_manager.py | `python-kis keep_token=True` | KIS의 1분 재발급 제한 처리, 파일 저장/로드, 만료 체크 내장 |
| KRX 공휴일 데이터 | 하드코딩 holiday list | `exchange_calendars` XKRX | 연간 업데이트, 임시공휴일 포함, 2026 대선 등 이미 반영 |
| Rate limiter | sliding window 직접 구현 | `time.sleep(1/15)` per request | 단일 심볼 폴링 루프에서는 간단한 sleep이 충분; 복잡한 구현 불필요 |
| env 검증 | 수동 os.environ.get + assert | `pydantic-settings BaseSettings` | ValidationError로 누락 필드 메시지, 타입 변환, prefix 지원 |
| 스케줄링 | crontab 외부 의존 | `APScheduler CronTrigger` | in-process, timezone aware, no daemon |

**Key insight:** python-kis가 KIS OAuth의 가장 복잡한 부분(토큰 갱신 1분 제한, 파일 캐시, 만료 감지)을 모두 처리한다. 이를 직접 구현하면 edge case 처리에 수십 줄이 추가된다.

---

## Common Pitfalls

### Pitfall 1: python-kis API 버전 불일치

**What goes wrong:** CLAUDE.md의 "python-kis 4.x" 및 `fetch_price()` 메서드명으로 코드 작성 시 ImportError 또는 AttributeError.
**Why it happens:** PyPI 현재 버전은 2.1.6. v2.0.0에서 완전 재설계되어 메서드명이 변경됨.
**How to avoid:** `pip install python-kis` (최신 = 2.1.6) 설치 후 `stock.quote()` 사용.
**Warning signs:** `AttributeError: 'KisDomesticStock' object has no attribute 'fetch_price'`

### Pitfall 2: 모의투자 자격증명 분리 미인지

**What goes wrong:** 실전 AppKey/AppSecret으로 `virtual=True` 초기화 시 KIS OAuth 오류 발생.
**Why it happens:** KIS는 모의투자/실전투자를 별도 API 신청 프로세스로 분리. 키도 별도 발급.
**How to avoid:** `.env`에 `KIS_VIRTUAL_APPKEY`, `KIS_VIRTUAL_SECRETKEY` 별도 설정. KIS Developers 포털에서 모의투자 서비스 별도 신청 필요.
**Warning signs:** `KisAPIError: rt_cd=1` 또는 인증 오류 메시지

### Pitfall 3: rt_cd 에러 시 price=0 전파

**What goes wrong:** API 에러 발생 시 price 변수에 0 또는 기본값이 남아 트레일링 스탑 엔진에 전달됨.
**Why it happens:** 에러 핸들링 없이 기본값 사용.
**How to avoid:** `KisAPIError` catch 후 해당 심볼 결과를 prices dict에 포함하지 않는다. 호출자는 심볼이 dict에 없으면 skip.
**Warning signs:** 로그에 에러가 있지만 매도 신호가 동시에 발생

### Pitfall 4: 레이트 리밋 초과 (EGW00201)

**What goes wrong:** 모의투자 계좌에서 연속 호출 시 EGW00201 에러 발생. 실전보다 제한이 낮음.
**Why it happens:** KIS 슬라이딩 윈도우 방식. Token bucket 구현 시에도 발생 사례 있음.
**How to avoid:** 심볼당 최소 `1/15`초 sleep. 20종목 기준 약 1.3초 = 안전.
**Warning signs:** `KisAPIError: msg_cd=EGW00201`

### Pitfall 5: 시장 운영 시간 오해

**What goes wrong:** 15:30까지 폴링하면 장 마감 후 API 호출. REQUIREMENTS.md는 15:20 마감.
**Why it happens:** 장 마감(15:30)과 폴링 중단 시간(15:20)이 다름.
**How to avoid:** 내부 루프에서 `datetime.now(KST).hour * 60 + minute >= 15*60+20` 체크. APScheduler CronTrigger는 09:00 시작만 처리.
**Warning signs:** 15:20 이후에도 폴링 로그가 찍힘

### Pitfall 6: Python 3.9 호환성

**What goes wrong:** 로컬 환경(macOS 기본) Python 3.9.6으로 실행 시 python-kis가 3.10+ 요구로 ImportError.
**Why it happens:** python-kis `requires_python = ">=3.10"`.
**How to avoid:** `pyenv` 또는 직접 Python 3.11/3.12 설치 후 가상환경 사용. `python3.11 -m venv .venv`
**Warning signs:** `pip install python-kis` 성공하나 import 시 오류

---

## Code Examples

### Complete .env.example Template

```bash
# Source: KIS Developers portal + python-kis README patterns
# 실전투자
KIS_ID=your_hts_id
KIS_ACCOUNT=00000000-01     # 계좌번호-상품코드
KIS_APPKEY=PSxxxxxxxxxxxxxxxx
KIS_SECRETKEY=RRxxxxxxxxxxxxxxxx

# 모의투자 (KIS_MOCK=true 시 사용 — KIS Developers 포털에서 별도 신청 필요)
KIS_VIRTUAL_ID=your_hts_id
KIS_VIRTUAL_ACCOUNT=00000000-01
KIS_VIRTUAL_APPKEY=VSxxxxxxxxxxxxxxxx
KIS_VIRTUAL_SECRETKEY=VRxxxxxxxxxxxxxxxx

# 모드 전환 (false=실전, true=모의)
KIS_MOCK=false
```

### KisAPIError Handling

```python
# Source: python-kis pykis/client/exceptions.py
from pykis import KisAPIError, KisHTTPError, KisException

try:
    quote = kis.stock("005930").quote()
    price = float(quote.price)
except KisAPIError as e:
    # HTTP 200이지만 rt_cd != "0" (KIS 내부 에러)
    logger.error(
        f"KIS API returned error: rt_cd={e.rt_cd}, "
        f"msg_cd={e.msg_cd}, msg={e.msg1}, tr_id={e.tr_id}"
    )
    # price 변수를 설정하지 않음 → 호출자에서 skip
except KisHTTPError as e:
    # HTTP 레벨 오류 (4xx, 5xx)
    logger.error(f"HTTP error: {e}")
except KisException as e:
    logger.error(f"KIS client error: {e}")
```

### Token Validity Check on Startup

```python
# PyKis with keep_token=True handles this automatically.
# On startup, confirm connectivity by fetching one quote.
# Source: python-kis README
from loguru import logger
from pykis import KisAPIError

def verify_auth(kis) -> bool:
    """Verify token is valid by making a test API call."""
    try:
        # Use a liquid, always-available stock for connectivity test
        quote = kis.stock("005930").quote()
        logger.info(
            f"KIS auth verified. Test quote: 삼성전자 = {quote.price}"
        )
        return True
    except KisAPIError as e:
        logger.error(f"KIS auth verification failed: {e}")
        return False
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-kis 1.x (hand-rolled error handling) | python-kis 2.x (KisAPIError with rt_cd field) | Aug 2024 (v2.0.0) | Structured exception hierarchy replaces ValueError |
| `fetch_price()` method | `stock.quote()` method | Aug 2024 (v2.0.0) | Complete API redesign; old method names gone |
| Separate token management | `PyKis(keep_token=True)` | Aug 2024 (v2.0.0) | Library handles token file cache internally |

**Deprecated/outdated:**
- `fetch_price()`: v2.0.0에서 제거됨. `stock.quote()` 사용.
- `python-kis "4.x"`: 해당 버전은 존재하지 않음. 최신은 2.1.6.
- `mojito`/`mojito2`: KIS API v2 변경 미반영, 2023년 이후 비활성.

---

## Open Questions

1. **python-kis `virtual=True` 파라미터 동작 확인 필요**
   - What we know: python-kis README에 `virtual=False/True` 파라미터가 존재하고, 별도 virtual 계좌 자격증명 지원
   - What's unclear: `virtual=True` 시 KIS WebSocket endpoint가 자동으로 모의투자 서버로 전환되는지; 가격 조회 REST endpoint도 전환되는지 확인 필요
   - Recommendation: Phase 1 구현 시 `virtual=True`로 초기화 후 `stock.quote()` 호출이 성공하는지 실제 테스트 필요

2. **KIS 모의투자 레이트 리밋 정확한 값**
   - What we know: "모의투자 계좌는 REST API 호출 제한이 낮다" (공식 언급), 실전은 20 req/s
   - What's unclear: 모의투자 정확한 req/s 값이 문서화되지 않음
   - Recommendation: 모의투자 테스트 시 15 req/s 시작, EGW00201 발생 시 10 req/s로 낮춤

3. **exchange_calendars 임시공휴일 반영 주기**
   - What we know: v4.13.2 (2026-03-10)에 2025 대선일 포함. 활발히 갱신됨
   - What's unclear: 갑작스러운 임시공휴일(예: 국가 행사) 반영까지 얼마나 걸리는지
   - Recommendation: Phase 1에서는 exchange_calendars 사용. 향후 httpx로 KIS 시장 상태 API 보완 고려 (D-02 이미 결정됨)

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11+ | python-kis (>=3.10), tomllib stdlib | ✗ | 3.9.6 (system) | pyenv install 3.11 or 3.12 |
| pip | Package installation | ✓ | 21.2.4 | — |
| python-kis | KIS API calls | ✗ (not installed) | — | pip install python-kis==2.1.6 |
| exchange-calendars | KRX holiday detection | ✗ (not installed) | — | pip install exchange-calendars==4.13.2 |
| APScheduler | Market hours scheduling | ✗ (not installed) | — | pip install APScheduler==3.11.2 |
| pydantic-settings | .env validation | ✗ (not installed) | — | pip install pydantic-settings==2.13.1 |
| loguru | Logging | ✗ (not installed) | — | pip install loguru==0.7.3 |
| httpx | KIS supplementary calls | ✗ (not installed) | — | pip install httpx==0.28.1 |
| python-dotenv | .env loading | ✗ (not installed) | — | pip install python-dotenv==1.2.2 |

**Missing dependencies with no fallback:**
- Python 3.11 or 3.12: system Python is 3.9.6. `python-kis` requires >=3.10. **Must install Python 3.11+ before anything else.** Use `pyenv install 3.11.9 && pyenv local 3.11.9` or install directly.

**Missing dependencies with fallback:**
- All Python packages: none installed yet (greenfield project). All installable via pip once Python 3.11+ is active.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (not yet installed) |
| Config file | none — Wave 0 creates pytest.ini or pyproject.toml [tool.pytest] |
| Quick run command | `pytest tests/ -x -q` |
| Full suite command | `pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONF-01 | PyKis 초기화 시 토큰 발급 및 만료 전 자동 갱신 | integration (needs real API key) | manual-only — requires KIS credentials | ❌ Wave 0 |
| CONF-02 | 필수 .env 필드 누락 시 ValidationError 발생 | unit | `pytest tests/test_settings.py -x` | ❌ Wave 0 |
| CONF-03 | config.toml 파싱 및 SymbolConfig 생성 | unit | `pytest tests/test_config.py -x` | ❌ Wave 0 |
| CONF-04 | KRX 공휴일에 is_session() = False 반환 | unit | `pytest tests/test_holiday.py -x` | ❌ Wave 0 |
| FEED-01 | 09:00~15:20 KST 범위 체크 로직 | unit | `pytest tests/test_scheduler.py -x` | ❌ Wave 0 |
| FEED-02 | quote() 결과를 price float으로 변환 | unit (mock KIS) | `pytest tests/test_price_feed.py -x` | ❌ Wave 0 |
| FEED-03 | 15 req/s 제한 시 sleep 간격 계산 | unit | `pytest tests/test_price_feed.py::test_rate_limit -x` | ❌ Wave 0 |
| FEED-04 | KisAPIError 수신 시 prices dict에 심볼 미포함 | unit (mock KisAPIError) | `pytest tests/test_price_feed.py::test_api_error -x` | ❌ Wave 0 |

> Note: CONF-01 (OAuth 토큰 획득)은 실제 KIS 자격증명이 필요하므로 자동화 테스트 불가. 성공 기준 #1 ("python main.py 실행 후 토큰 만료 타임스탬프 출력")으로 수동 검증.

### Sampling Rate
- **Per task commit:** `pytest tests/ -x -q --ignore=tests/integration`
- **Per wave merge:** `pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/__init__.py`
- [ ] `tests/test_settings.py` — covers CONF-02
- [ ] `tests/test_config.py` — covers CONF-03
- [ ] `tests/test_holiday.py` — covers CONF-04
- [ ] `tests/test_scheduler.py` — covers FEED-01
- [ ] `tests/test_price_feed.py` — covers FEED-02, FEED-03, FEED-04
- [ ] `pyproject.toml` — `[tool.pytest.ini_options]` + dependency declarations
- [ ] Framework install: `pip install pytest pytest-mock` — if not yet in pyproject.toml

---

## Project Constraints (from CLAUDE.md)

| Directive | Constraint |
|-----------|------------|
| KIS API only | 한국투자증권 KIS Developers API만 사용 |
| Stable runtime | 시장 시간 내 로컬 또는 서버 환경에서 안정 실행 |
| Secrets isolation | API 키, 시크릿은 환경변수 또는 별도 설정 파일로 분리 |
| python-kis 4.x | **OVERRIDDEN BY RESEARCH:** 실제 최신 버전은 2.1.6. 동일 라이브러리의 현재 버전 사용 |
| `fetch_price()` | **OVERRIDDEN BY RESEARCH:** v2.x에서 `stock.quote()`로 변경됨 |
| No YAML | TOML 사용 (종목코드 정수 파싱 버그 방지) |
| No mojito/mojito2 | 유지보수 중단 |
| No LINE Notify | 2025-03-31 서비스 종료 |
| No Celery/Redis | 오버킬 |
| No FastAPI/Flask | 불필요 |
| GSD workflow | Edit/Write 사용 전 GSD 커맨드 경유 필수 |

---

## Sources

### Primary (HIGH confidence)
- [python-kis PyPI](https://pypi.org/project/python-kis/) — version 2.1.6, Python >=3.10 requirement (confirmed 2026-04-06)
- [python-kis GitHub README](https://github.com/Soju06/python-kis) — PyKis init patterns, stock.quote() API, KisAPIError structure
- [pydantic-settings official docs](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — BaseSettings, SettingsConfigDict, env_file
- [exchange_calendars PyPI](https://pypi.org/project/exchange_calendars/) — version 4.13.2, XKRX support, is_session() API
- [APScheduler 3.x docs](https://apscheduler.readthedocs.io/en/3.x/) — CronTrigger, timezone parameter

### Secondary (MEDIUM confidence)
- [KIS Developers 토큰 문서](https://apiportal.koreainvestment.com/provider-doc4) — access token 24h TTL, refresh endpoint /oauth2/tokenP, 1분 재발급 제한
- [KIS API 쓰로틀링 분석](https://hky035.github.io/web/kis-api-throttling/) — sliding window rate limit, EGW00201 에러코드, 20 req/s 공식 한도, 15 req/s 안전 마진 권장
- [KIS open-trading-api GitHub](https://github.com/koreainvestment/open-trading-api) — EGW00201 코드 확인, 모의투자 호출 제한 낮음 언급

### Tertiary (LOW confidence — needs validation)
- KIS 모의투자 정확한 req/s 한도 — 공식 문서 미발견, 실제 테스트 시 확인 필요

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyPI version confirmed 2026-04-06, official docs verified
- Architecture: MEDIUM — patterns derived from README examples and community best practices; virtual account behavior needs live test
- Pitfalls: MEDIUM-HIGH — most pitfalls verified via official docs or multiple sources

**Research date:** 2026-04-06
**Valid until:** 2026-05-06 (30 days; python-kis 2.x is actively developed)
