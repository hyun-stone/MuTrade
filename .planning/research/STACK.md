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
app.mount("/static", StaticFiles(directory="mutrade/admin/static"), name="static")
templates = Jinja2Templates(directory="mutrade/admin/templates")
```

**폴더 구조 권고:**
```
mutrade/
  admin/
    __init__.py
    app.py          ← FastAPI app 객체 (기존)
    hub.py          ← BotStateHub (기존)
    routes.py       ← REST + WebSocket 라우터 (신규)
    static/
      main.js
      style.css
    templates/
      index.html
```

**신뢰도: HIGH** — Jinja2 3.1.6 PyPI 확인됨(2025-03-05 릴리즈). FastAPI 공식 문서 패턴.

---

### 실시간 대시보드 업데이트: WebSocket 채택 (SSE 대비 비교)

**결론: WebSocket 채택 — Admin 대시보드는 단방향이 아니다**

| 기준 | WebSocket | SSE (Server-Sent Events) |
|------|-----------|--------------------------|
| 통신 방향 | 양방향 (full-duplex) | 단방향 (서버 → 클라이언트) |
| 봇 제어 (시작/중지) | 클라이언트 → 서버 메시지로 가능 | 불가능, 별도 REST 필요 |
| 실시간 가격 브로드캐스트 | 가능 | 가능 |
| FastAPI 내장 지원 | 네이티브 (추가 라이브러리 불필요) | `sse-starlette` 라이브러리 필요 |
| 연결 수 (개인용 봇) | 1~2개 탭 | 1~2개 탭 |
| 재연결 | 수동 처리 필요 | 브라우저 자동 재연결 |

**WebSocket 선택 근거:** Admin 대시보드는 가격 표시(서버→클라이언트)와 봇 제어 명령(클라이언트→서버)이 혼재한다. SSE는 봇 제어 명령에 별도 REST 엔드포인트가 필요해 구현이 분산된다. WebSocket 하나로 상태 스트림과 제어 명령을 동일 연결에서 처리하는 것이 단순하다.

**SSE가 더 나은 경우 (해당 없음):** 읽기 전용 모니터링, 브라우저 자동 재연결이 중요한 경우, nginx 프록시 뒤에서 응답 버퍼링 이슈 회피가 필요한 경우.

**WebSocket 브로드캐스트 패턴 (BotStateHub와 통합):**

BotStateHub는 이미 `wait_for_change()` async 메서드를 제공한다. WebSocket 태스크는 이를 그대로 사용한다:

```python
# mutrade/admin/routes.py
from fastapi import WebSocket, WebSocketDisconnect
from mutrade.admin.hub import BotStateHub

class ConnectionManager:
    def __init__(self):
        self.active: list[WebSocket] = []

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.active.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self.active:
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

manager = ConnectionManager()

@router.websocket("/ws/dashboard")
async def dashboard_ws(websocket: WebSocket):
    hub: BotStateHub = websocket.app.state.hub
    await manager.connect(websocket)
    try:
        while True:
            snapshot = await hub.wait_for_change()
            await websocket.send_json(snapshot)
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

**스레드 → asyncio 브릿지:** BotStateHub의 `push_snapshot()`은 이미 `loop.call_soon_threadsafe()`를 사용해 APScheduler 스레드에서 asyncio Queue로 데이터를 전달한다. WebSocket 라우터는 `hub.wait_for_change()`를 await하면 된다 — 추가 스레드 안전 처리 불필요.

**신뢰도: HIGH** — FastAPI 공식 문서 패턴, BotStateHub 기존 구현과 직접 통합.

---

### config.toml 편집: tomlkit 채택 (tomllib 대체 아님, 보완)

**문제:** Python 3.11 stdlib `tomllib`은 읽기 전용이다. config.toml UI 편집 후 저장하려면 쓰기 라이브러리가 필요하다.

**선택 비교:**

| 라이브러리 | 읽기 | 쓰기 | 스타일 보존 | 특이사항 |
|-----------|------|------|------------|---------|
| `tomllib` (stdlib) | 가능 | 불가 | N/A | Python 3.11+ 내장 |
| `tomli-w` 1.2.0 | 불가 (별도 tomli 필요) | 가능 | 없음 (재포맷) | 쓰기 전용, 주석 제거됨 |
| **`tomlkit` 0.14.0** | **가능** | **가능** | **완전 보존** | 주석, 들여쓰기, 공백 유지 |

**tomlkit 채택 이유:** config.toml은 사용자가 직접 편집하는 파일이다. `tomli-w`로 재저장하면 주석과 포맷이 모두 사라진다. `tomlkit`은 파일을 파싱 후 재직렬화할 때 원본 주석과 공백을 그대로 보존한다. Admin UI에서 수정 저장해도 수동 편집본이 망가지지 않는다.

```python
# mutrade/admin/routes.py — config.toml 읽기/쓰기
import tomlkit
from pathlib import Path

CONFIG_PATH = Path("config.toml")

def read_config() -> str:
    """config.toml 원문 반환 (UI 텍스트 에디터용)."""
    return CONFIG_PATH.read_text(encoding="utf-8")

def write_config(content: str) -> None:
    """
    저장 전 유효성 검사: tomlkit.parse()가 실패하면 SyntaxError raise.
    유효한 경우에만 덮어쓴다.
    """
    tomlkit.parse(content)   # 파싱 오류 시 여기서 예외 발생
    CONFIG_PATH.write_text(content, encoding="utf-8")
```

**UI 편집 패턴:** 텍스트 에디터(`<textarea>`)에 raw TOML 문자열을 표시하고, 저장 시 서버로 전송한다. 서버는 `tomlkit.parse()`로 구문 검증 후 파일에 저장한다. 사용자가 TOML 문법 오류를 낸 경우 400 Bad Request로 오류 메시지를 반환한다.

**설치:**
```bash
pip install "tomlkit==0.14.0"
```

**신뢰도: HIGH** — PyPI에서 0.14.0(2026-01-13 릴리즈) 직접 확인. tomlkit GitHub 활성 유지됨.

---

### 거래 이력 파싱: 동기 readline + regex (추가 라이브러리 없음)

**문제:** `[TRADE]` 마커가 포함된 로그 라인을 파싱해 거래 이력 목록을 만들어야 한다.

**결론:** 추가 라이브러리 없음. Python 표준 `re` + 동기 파일 읽기로 충분하다.

**근거:**
- loguru는 `logs/mutrade.log`에 구조화된 텍스트를 기록한다. 별도 파서 라이브러리가 필요 없다.
- 거래 이력 조회는 실시간이 아니다 — REST 엔드포인트(`GET /api/trades`)로 요청 시 파일을 읽으면 된다.
- 로그 파일 크기: 개인용 봇에서 하루 최대 수백 라인. 비동기 I/O 불필요.
- FastAPI에서 동기 파일 읽기는 `run_in_executor()`로 블로킹을 우회할 수 있지만, 로그 파일 크기상 직접 동기 호출도 무시 가능한 지연이다.

**패턴:**

loguru가 기록하는 `[TRADE]` 라인 예시:
```
2026-04-12 09:32:15.123 | INFO     | mutrade.executor:execute:88 - [TRADE] SELL 005930 55000 100 dry_run=False
```

파싱 코드:
```python
# mutrade/admin/routes.py
import re
from pathlib import Path
from datetime import datetime

LOG_PATH = Path("logs/mutrade.log")

# loguru 기본 포맷: YYYY-MM-DD HH:MM:SS.mmm | LEVEL | module:func:line - message
TRADE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)\s+\|\s+\w+\s+\|.*?\[TRADE\]\s+(?P<body>.+)$"
)

def parse_trade_log(limit: int = 100) -> list[dict]:
    """최신 [TRADE] 항목을 limit 개 반환. 파일 미존재 시 빈 리스트."""
    if not LOG_PATH.exists():
        return []
    trades = []
    with LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            m = TRADE_RE.match(line.rstrip())
            if m:
                trades.append({"timestamp": m.group("ts"), "detail": m.group("body")})
    return trades[-limit:]  # 최신 N건
```

**FastAPI 엔드포인트:**
```python
@router.get("/api/trades")
def get_trades(limit: int = 100) -> list[dict]:
    return parse_trade_log(limit=limit)
```

참고: loguru의 실제 `[TRADE]` 라인 포맷은 `mutrade/executor/` 구현에서 확인 후 regex 조정 필요. 위 패턴은 loguru 기본 포맷 기준.

**신뢰도: HIGH** — Python 표준 라이브러리, loguru 포맷 문서 기반. 별도 라이브러리 없음.

---

### 프론트엔드 — 빌드 단계 없는 바닐라 JS

Admin Dashboard는 개인용 도구다. React/Vue/Svelte 빌드 파이프라인은 불필요하다.

| 라이브러리 | 버전 | 로딩 방식 | 목적 | 이유 |
|-----------|------|----------|------|------|
| **Chart.js** | 4.5.1 | CDN `<script>` 태그 | 가격 추이 차트 | 빌드 불필요, CDN 한 줄로 추가. 바닐라 JS에서 직접 사용 가능. |
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
    "tomlkit==0.14.0",           # config.toml 스타일 보존 읽기/쓰기
]
```

**추가되지 않는 것 (이유):**

| 제외 항목 | 이유 |
|----------|------|
| `websockets` (직접) | `uvicorn[standard]`에 포함됨 |
| `starlette` (직접) | `fastapi` 의존성으로 자동 설치 |
| `aiofiles` | 정적 파일은 StaticFiles가 처리, 로그 파일 읽기는 동기 I/O로 충분 |
| `sse-starlette` | SSE 불채택. WebSocket이 봇 제어 명령 포함 양방향 통신에 더 적합. FastAPI 네이티브 지원 |
| `tomli-w` | tomlkit이 읽기+쓰기+스타일 보존을 모두 제공. tomli-w는 주석 제거 부작용 있음 |
| Redis | 단일 사용자, 단일 프로세스 — 인메모리 ConnectionManager로 충분 |
| React/Vue/Svelte | 빌드 파이프라인 불필요, 개인용 대시보드 |
| SQLite/SQLAlchemy | 거래 이력은 `[TRADE]` 로그 마커 파싱으로 처리 |

---

## lifespan 통합 패턴

FastAPI lifespan을 이용해 봇 스케줄러를 시작/종료한다. `on_event` 데코레이터는 deprecated, lifespan 방식이 현재 표준이다.

현재 `mutrade/admin/app.py`의 `create_app()` 함수는 이미 lifespan 패턴을 구현하고 있다. routes.py를 추가할 때 `app.include_router(router)` 한 줄만 삽입하면 된다:

```python
# mutrade/admin/app.py — create_app() 내부에 추가
from mutrade.admin.routes import router
app.include_router(router)
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
| `tomllib` (stdlib) | Python 3.11+ | config.toml 읽기 (기존) | |
| `tomlkit` | 0.14.0 | config.toml 읽기/쓰기 + 스타일 보존 (v1.1 신규) | |

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
| Config write | `tomli-w` | 주석 제거 부작용. tomlkit으로 대체 |
| Dashboard framework | React/Vue/Svelte | Build pipeline unnecessary for personal dashboard |
| Dashboard backend | Flask | FastAPI chosen for better async/WebSocket support |
| Real-time transport | SSE / `sse-starlette` | Admin 대시보드는 봇 제어 명령(클라이언트→서버) 포함 — 양방향 WebSocket이 필요 |
| WebSocket scaling | Redis pub/sub | Single user, single process — in-memory sufficient |
| DB for trade history | SQLite/SQLAlchemy | Log file parsing sufficient for v1.1 |

---

## Confidence Notes

| Area | Confidence | 검증 방법 |
|------|------------|----------|
| FastAPI 0.135.3 | HIGH | WebSearch PyPI 확인 (2026-04-01 릴리즈) |
| uvicorn 0.44.0 | HIGH | WebSearch PyPI 확인 (2026-04-06 릴리즈) |
| Jinja2 3.1.6 | HIGH | WebSearch PyPI 확인 (2025-03-05 릴리즈) |
| tomlkit 0.14.0 | HIGH | PyPI 직접 확인 (2026-01-13 릴리즈) |
| python-multipart 0.0.26 | MEDIUM | WebSearch 결과 단일 소스 |
| Chart.js 4.5.1 | MEDIUM | npmjs "6개월 전" 게시 기준, jsDelivr CDN 직접 확인 권장 |
| BackgroundScheduler + FastAPI 패턴 | HIGH | APScheduler 공식 문서 + 다수 2025 가이드 |
| asyncio.run_coroutine_threadsafe 패턴 | HIGH | Python 표준 라이브러리, asyncio 문서 |
| lifespan 통합 패턴 | HIGH | FastAPI 공식 문서 0.93+ |
| WebSocket vs SSE 결정 | HIGH | 공식 FastAPI WebSocket 문서 + SSE/WS 비교 다수 소스 |
| tomlkit 스타일 보존 특성 | HIGH | 공식 문서 + Real Python 가이드 |
| [TRADE] 로그 파싱 regex 패턴 | MEDIUM | loguru 기본 포맷 기반; 실제 포맷은 executor 코드에서 확인 필요 |

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
- tomlkit PyPI: https://pypi.org/project/tomlkit/
- tomlkit 스타일 보존 설명: https://runebook.dev/en/docs/python/library/tomllib/examples
- tomllib 읽기 전용 공식 문서: https://docs.python.org/3/library/tomllib.html
- SSE vs WebSocket 비교: https://potapov.me/en/make/websocket-sse-longpolling-realtime
- sse-starlette PyPI (불채택 근거 참조용): https://pypi.org/project/sse-starlette/
- FastAPI SSE 공식 문서: https://fastapi.tiangolo.com/tutorial/server-sent-events/
