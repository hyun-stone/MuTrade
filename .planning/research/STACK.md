# Technology Stack

**Project:** MuTrade — 자동 트레일링 스탑 트레이딩 봇
**Domain:** Personal automated stock trading bot (Korea Investment & Securities / KIS API)
**Researched:** 2026-04-06 (v1.0), updated 2026-04-12 (v1.1 Admin Dashboard 추가)
**Knowledge cutoff:** August 2025 (web search 병행 사용 — v1.1 섹션은 웹 검색으로 버전 검증됨)

---

## v1.1 Admin Dashboard — 신규 스택 추가

> 이 섹션은 v1.1 Admin Dashboard 마일스톤에 필요한 라이브러리만 다룬다.
> 기존 v1.0 스택(python-kis, APScheduler, loguru, pydantic-settings, Telegram)은 재연구하지 않는다.

### 핵심 결정: 프로세스 아키텍처

**결론: 단일 프로세스 — FastAPI(uvicorn) + APScheduler BackgroundScheduler를 같은 프로세스에서 실행**

현재 코드는 `BlockingScheduler`를 사용해 메인 스레드를 점유한다(`start_scheduler`가 블로킹 반환). FastAPI와 공존하려면 스케줄러를 백그라운드 스레드로 옮겨야 한다. 두 가지 방법이 있다:

| 방법 | 설명 | 선택 여부 |
|------|------|-----------|
| **BackgroundScheduler** | 별도 스레드에서 실행, APScheduler 3.x의 기본 방식 | **채택** |
| AsyncIOScheduler | uvicorn의 event loop 위에서 실행 | 기존 폴링 루프가 `time.sleep()` 사용 — async 아님, 변환 비용 큼 |
| 별도 프로세스 | FastAPI 프로세스 + 봇 프로세스 분리 | IPC 복잡도 증가, 개인용 봇에 과도 |

**왜 BackgroundScheduler인가:**
- 기존 `scheduler.py`의 `time.sleep()` 기반 폴링 루프를 그대로 유지할 수 있다
- FastAPI는 uvicorn asyncio event loop 위에서 실행
- 두 컨텍스트는 Python 객체(엔진, 상태)를 직접 공유 가능 (GIL 하에서 thread-safe read는 문제없음)
- 쓰기 경합이 있는 상태(`engine.states`, `state.json`)는 `threading.Lock`으로 보호

**migration 요약:**
```
기존: BlockingScheduler.start() → 메인 스레드 점유
변경: BackgroundScheduler.start() → 백그라운드 스레드
      uvicorn.run(app) → 메인 스레드 (FastAPI)
```

---

### Web Framework

| 라이브러리 | 버전 | 목적 | 이유 |
|-----------|------|------|------|
| `fastapi` | 0.135.3 | HTTP REST API + WebSocket 엔드포인트 | WebSocket 내장 지원, Starlette 기반, 타입 검증 자동화. 개인용 대시보드에 딱 맞는 크기. |
| `uvicorn[standard]` | 0.44.0 | ASGI 서버 | FastAPI 공식 권장 서버. `[standard]`는 `websockets` + `httptools` 포함. |
| `starlette` | (fastapi 의존성, 자동 설치) | StaticFiles, WebSocket 기반 | fastapi가 요구하는 버전 자동 설치됨, 직접 명시 불필요. |

**설치:**
```bash
pip install "fastapi==0.135.3" "uvicorn[standard]==0.44.0"
```

`uvicorn[standard]`에 포함되는 것: `websockets`, `httptools`, `uvloop`(Linux/macOS), `watchfiles`(개발용 reload)

**신뢰도: HIGH** — PyPI에서 2026-04-01(fastapi), 2026-04-06(uvicorn) 릴리즈 확인됨.

---

### 템플릿 및 정적 파일 서빙

| 라이브러리 | 버전 | 목적 | 이유 |
|-----------|------|------|------|
| `jinja2` | 3.1.6 | HTML 템플릿 렌더링 | FastAPI 공식 지원 템플릿 엔진. 빌드 단계 없이 서버 사이드 렌더링. |

`StaticFiles`는 Starlette 내장 — 추가 설치 불필요.

```python
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app = FastAPI()
app.mount("/static", StaticFiles(directory="mutrade/dashboard/static"), name="static")
templates = Jinja2Templates(directory="mutrade/dashboard/templates")
```

**폴더 구조 권고:**
```
mutrade/
  dashboard/
    __init__.py
    app.py          ← FastAPI app 객체
    routes.py       ← REST + WebSocket 라우터
    static/
      main.js
      style.css
    templates/
      index.html
```

**신뢰도: HIGH** — Jinja2 3.1.6 PyPI 확인됨(2025-03-05 릴리즈). FastAPI 공식 문서 패턴.

---

### WebSocket 브로드캐스트 패턴

FastAPI는 WebSocket을 네이티브 지원한다. 브라우저 탭 하나~몇 개를 대상으로 하는 개인용 대시보드에는 Redis 없이 인메모리 `ConnectionManager`로 충분하다.

```python
# mutrade/dashboard/connection_manager.py
import asyncio
from fastapi import WebSocket

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        self.active.remove(ws)

    async def broadcast(self, data: dict):
        dead = []
        for ws in self.active:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.active.remove(ws)
```

**봇 엔진 → WebSocket 브로드캐스트 연결:**

봇 폴링 루프(스레드)에서 asyncio 이벤트 루프로 데이터를 넘기려면 `asyncio.run_coroutine_threadsafe()`를 사용한다. 이것이 BackgroundScheduler 패턴의 핵심 연결 지점이다.

```python
# 스레드 내 봇 코드에서 WebSocket 브로드캐스트 호출
loop = asyncio.get_event_loop()  # uvicorn이 사용하는 loop
asyncio.run_coroutine_threadsafe(
    manager.broadcast({"prices": prices_dict}),
    loop
)
```

**신뢰도: HIGH** — FastAPI 공식 문서 패턴, asyncio 표준 라이브러리.

---

### 프론트엔드 — 빌드 단계 없는 바닐라 JS

Admin Dashboard는 개인용 도구다. React/Vue/Svelte 빌드 파이프라인은 불필요하다.

| 라이브러리 | 버전 | 로딩 방식 | 목적 | 이유 |
|-----------|------|----------|------|------|
| **Chart.js** | 4.5.1 | CDN `<script>` 태그 | 가격 추이 차트 | 빌드 불필요, CDN 한 줄로 추가. 바닐라 JS에서 직접 사용 가능. 4.x는 트리 쉐이킹 지원(CDN에서는 불필요). |
| 없음 (바닐라 JS) | — | — | UI 동적 업데이트 | 개인용 대시보드 규모에서 프레임워크 불필요. 네이티브 WebSocket API + DOM 조작으로 충분. |

**Chart.js CDN:**
```html
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
```

**왜 HTMX는 추천하지 않는가:**
HTMX는 서버 렌더링 부분 업데이트에 강하지만, WebSocket 실시간 데이터 스트림을 처리하는 방식이 바닐라 JS `WebSocket` API보다 추상화가 복잡해진다. 실시간 가격 업데이트 + Chart.js 그래프 조합에는 바닐라 JS가 더 단순하다.

**신뢰도: MEDIUM** — Chart.js 4.5.1은 npmjs 기준 "6개월 전 게시"로 확인. jsDelivr CDN 가용성은 항상 HIGH.

---

### 폼 데이터 처리 (설정 변경 API)

config.toml 수정 API에서 폼 제출을 받으려면 `python-multipart`가 필요하다.

| 라이브러리 | 버전 | 목적 |
|-----------|------|------|
| `python-multipart` | 0.0.26 | FastAPI Form 파라미터 처리 |

```bash
pip install python-multipart==0.0.26
```

단, JSON body로 설정을 받는다면 불필요하다. HTML `<form>` 사용 시에만 필요.

**신뢰도: MEDIUM** — PyPI 검색 결과에서 0.0.26(2026-04-10) 확인.

---

## 업데이트된 전체 의존성 목록 (v1.1)

```toml
# pyproject.toml
[project]
requires-python = ">=3.11"
dependencies = [
    # v1.0 기존
    "python-kis==2.1.6",
    "pydantic-settings==2.13.1",
    "python-dotenv==1.2.2",
    "loguru==0.7.3",
    "APScheduler==3.11.2",
    "exchange-calendars==4.13.2",
    "httpx==0.28.1",
    "python-telegram-bot==21.11.1",
    # v1.1 신규 추가
    "fastapi==0.135.3",
    "uvicorn[standard]==0.44.0",
    "jinja2==3.1.6",
    "python-multipart==0.0.26",  # config 폼 제출 시만 필요
]
```

**추가되지 않는 것 (이유):**

| 제외 항목 | 이유 |
|----------|------|
| `websockets` (직접) | `uvicorn[standard]`에 포함됨 |
| `starlette` (직접) | `fastapi` 의존성으로 자동 설치 |
| `aiofiles` | 정적 파일은 StaticFiles가 처리, 로그 파일 읽기는 동기 I/O로 충분 |
| Redis | 단일 사용자, 단일 프로세스 — 인메모리 ConnectionManager로 충분 |
| React/Vue/Svelte | 빌드 파이프라인 불필요, 개인용 대시보드 |
| SQLite/SQLAlchemy | 거래 이력은 `[TRADE]` 로그 마커 파싱으로 처리 |

---

## lifespan 통합 패턴

FastAPI lifespan을 이용해 봇 스케줄러를 시작/종료한다. `on_event` 데코레이터는 deprecated, lifespan 방식이 현재 표준이다.

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    # startup: 봇 컴포넌트 초기화 후 BackgroundScheduler 시작
    loop = asyncio.get_event_loop()
    app.state.loop = loop
    app.state.engine = engine
    app.state.manager = ConnectionManager()
    scheduler.start()          # BackgroundScheduler — 별도 스레드
    yield
    # shutdown: 스케줄러 종료
    scheduler.shutdown(wait=False)

app = FastAPI(lifespan=lifespan)
```

**신뢰도: HIGH** — FastAPI 0.93+ 공식 문서 패턴, 2025-2026 가이드에서 일관되게 확인됨.

---

## v1.0 원본 스택 (변경 없음)

### KIS API Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-kis` | 2.1.6 | KIS REST + WebSocket client | The most complete community wrapper for KIS Developers API. Covers OAuth token management, account inquiry, current price, order placement, and WebSocket real-time feeds. Actively maintained by Bhban (GitHub: `Soju06/python-kis`). Type-annotated, async-compatible. |

**Confidence: MEDIUM** — Run `pip index versions python-kis` and check GitHub `Soju06/python-kis` for last commit date and v4.x changelog

---

### Core Framework — Python Runtime

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| Python | 3.11 or 3.12 | Runtime | 3.11 is the stable LTS target; 3.12 added minor perf improvements. Both are well-supported. Avoid 3.13 until ecosystem catches up. |

**Confidence: HIGH**

---

### Real-Time Price: WebSocket vs Polling

**Decision: Start with polling, add WebSocket only if latency matters.**

For a trailing-stop bot that sells on a -10% drawdown from peak, the trigger latency requirement is loose — a 1–5 second poll is sufficient.

**Polling approach (current):**
```python
# asyncio + httpx pattern
import asyncio, httpx

async def poll_prices(symbols, interval_seconds=3.0):
    async with httpx.AsyncClient() as client:
        while True:
            for symbol in symbols:
                price = await fetch_price(client, symbol)
                check_trailing_stop(symbol, price)
            await asyncio.sleep(interval_seconds)
```

KIS rate limits: ~20 req/s. 20 symbols × 1 req/poll = 7 req/s at 3s interval — well within limits.

**Confidence: HIGH**

---

### Scheduling / Process Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `APScheduler` | 3.11.2 | Schedule market-hours window (09:00–15:20 KST) | Mature, no daemon required, works in-process. |
| `systemd` / `launchd` | OS-provided | Keep the process alive across reboots | |

**v1.1 변경:** `BlockingScheduler` → `BackgroundScheduler` 교체 필요 (FastAPI 메인 스레드 확보).

**Confidence: HIGH**

---

### Notification

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-telegram-bot` | 21.11.1 | Push notifications | Free, instant setup, no approval needed. |

**Confidence: HIGH**

---

### Configuration and Secrets Management

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `python-dotenv` | 1.2.2 | Load `.env` | |
| `pydantic-settings` | 2.13.1 | Typed config | |
| `tomllib` (stdlib) | Python 3.11+ | config.toml | |

**Confidence: HIGH**

---

### Logging

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `loguru` | 0.7.3 | Application logging + [TRADE] markers | |

**Confidence: HIGH**

---

### HTTP Client

| Technology | Version | Purpose | Why |
|------------|---------|---------|-----|
| `httpx` | 0.28.1 | Async HTTP | |

**Confidence: HIGH**

---

## What NOT to Use

| Category | Avoid | Why |
|----------|-------|-----|
| KIS client | `mojito` (mojito2) | Older, last maintained 2023 |
| Notification | LINE Notify | Shut down March 31, 2025 |
| Scheduling | `celery`, `rq` | Overkill, needs Redis |
| Config | `yaml` / PyYAML | Implicit type coercion bugs |
| Dashboard framework | React/Vue/Svelte | Build pipeline unnecessary for personal dashboard |
| Dashboard backend | Flask | FastAPI chosen for better async/WebSocket support |
| WebSocket scaling | Redis pub/sub | Single user, single process — in-memory sufficient |
| DB for trade history | SQLite/SQLAlchemy | Log file parsing sufficient for v1.1 |

---

## Confidence Notes

| Area | Confidence | 검증 방법 |
|------|------------|----------|
| FastAPI 0.135.3 | HIGH | WebSearch PyPI 확인 (2026-04-01 릴리즈) |
| uvicorn 0.44.0 | HIGH | WebSearch PyPI 확인 (2026-04-06 릴리즈) |
| Jinja2 3.1.6 | HIGH | WebSearch PyPI 확인 (2025-03-05 릴리즈) |
| python-multipart 0.0.26 | MEDIUM | WebSearch 결과 단일 소스 |
| Chart.js 4.5.1 | MEDIUM | npmjs "6개월 전" 게시 기준, jsDelivr CDN 직접 확인 권장 |
| BackgroundScheduler + FastAPI 패턴 | HIGH | APScheduler 공식 문서 + 다수 2025 가이드 |
| asyncio.run_coroutine_threadsafe 패턴 | HIGH | Python 표준 라이브러리, asyncio 문서 |
| lifespan 통합 패턴 | HIGH | FastAPI 공식 문서 0.93+ |

---

## Sources

- FastAPI PyPI: https://pypi.org/project/fastapi/
- FastAPI 릴리즈 노트: https://fastapi.tiangolo.com/release-notes/
- uvicorn PyPI: https://pypi.org/project/uvicorn/
- FastAPI WebSocket 공식 문서: https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI 정적 파일 문서: https://fastapi.tiangolo.com/tutorial/static-files/
- FastAPI Jinja2 템플릿: https://fastapi.tiangolo.com/advanced/templates/
- FastAPI lifespan: https://fastapi.tiangolo.com/advanced/events/
- APScheduler BackgroundScheduler: https://apscheduler.readthedocs.io/en/3.x/userguide.html
- Chart.js 설치: https://www.chartjs.org/docs/latest/getting-started/installation.html
- Chart.js jsDelivr CDN: https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js
- python-multipart PyPI: https://pypi.org/project/python-multipart/
- Jinja2 PyPI: https://pypi.org/project/Jinja2/
