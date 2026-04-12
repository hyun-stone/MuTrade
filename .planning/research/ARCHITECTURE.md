# Architecture Patterns: FastAPI Admin Dashboard Integration

**Domain:** 기존 단일 프로세스 트레이딩 봇에 Admin Web UI 추가
**Researched:** 2026-04-12 (Phase 5 완료 후 현황 반영 갱신)
**Confidence:** HIGH (코드베이스 직접 분석 — 모든 소스 파일 확인)

---

## 현재 구현 상태 (Phase 5 완료 기준)

Phase 5 이후 이미 완료된 항목:

| 컴포넌트 | 파일 | 상태 |
|----------|------|------|
| `BotStateHub` | `mutrade/admin/hub.py` | **구현 완료** |
| `FastAPI app` | `mutrade/admin/app.py` | 기반 완료 (`/health` 엔드포인트, lifespan) |
| `BackgroundScheduler` 전환 | `mutrade/monitor/scheduler.py` | **구현 완료** |
| `uvicorn.run()` 메인 루프 | `mutrade/main.py` | **구현 완료** |
| `hub.push_snapshot()` 연동 | `mutrade/monitor/scheduler.py` | **구현 완료** |
| `hub.is_stop_requested()` 체크 | `mutrade/monitor/scheduler.py` | **구현 완료** |
| `hub.set_running()` 세션 상태 | `mutrade/monitor/scheduler.py` | **구현 완료** |

미구현 항목 (v1.1 신규 작업):

| 컴포넌트 | 파일 | 상태 |
|----------|------|------|
| `ConnectionManager` | `admin/ws.py` | 미존재 |
| `TradeLogReader` | `admin/log_reader.py` | 미존재 |
| `ConfigEditor` | `admin/config_editor.py` | 미존재 |
| 라우터 파일들 | `admin/routers/` | 미존재 |
| 정적 파일 | `admin/static/index.html` | 미존재 |

---

## 현재 프로세스 구조 (Phase 5 완료 후)

```
메인 스레드
  └── uvicorn.run(app, host="127.0.0.1", port=8000)   ← 블로킹 메인 루프
        └── FastAPI lifespan
              ├── hub.attach_loop(asyncio.get_running_loop())
              └── GET /health 만 존재

APScheduler 스레드 (BackgroundScheduler daemon)
  └── run_session() (Mon-Fri 09:00 KST 트리거)
        ├── poll_prices() → KIS REST API
        ├── engine.tick(prices) → _states 갱신
        ├── hub.push_snapshot(engine.states)   ← BotStateHub로 전달
        ├── hub.set_running(True)
        └── hub.is_stop_requested() 체크 → break 조건
```

`BotStateHub`의 `_change_queue`(asyncio.Queue)에 데이터가 쌓이고 있지만,
현재는 이를 소비하는 WebSocket 브로드캐스트 태스크가 없다. v1.1에서 구현한다.

---

## 핵심 설계 결정: 동일 프로세스 (In-Process)

별도 프로세스 대신 동일 프로세스를 선택한 이유:

1. **TrailingStopEngine 상태 공유가 목적 자체다.** 별도 프로세스는 in-memory `_states` dict를 공유할 수 없다. state.json 폴링도 가능하지만 3~5초 지연이 발생하여 실시간 표시 의미가 퇴색된다.
2. **BotStateHub가 이미 thread-safe 브릿지로 구현되어 있다.** 별도 프로세스를 선택하는 가장 큰 이유(스레드 복잡도 회피)가 이미 해결되어 있다.
3. **단일 사용자 개인용 봇이다.** 운영자 한 명이 브라우저에서 접속한다. 분산 구조(Redis PubSub, 멀티 워커)는 불필요하다.

---

## BotStateHub 인터페이스 (현재 구현)

`mutrade/admin/hub.py`에 완전히 구현되어 있다. v1.1 신규 컴포넌트는 다음 메서드들을 활용한다:

```
push_snapshot(states: dict)      APScheduler 스레드 → asyncio.Queue (call_soon_threadsafe)
get_snapshot() -> dict           FastAPI 엔드포인트에서 현재 스냅샷 읽기
wait_for_change() -> dict        WebSocket 브로드캐스트 태스크에서 await
request_stop()                   POST /api/bot/stop 에서 호출 (threading.Event.set)
clear_stop()                     stop 처리 후 scheduler 내부에서 호출
is_stop_requested() -> bool      APScheduler run_session 루프에서 폴링
set_running(bool)                APScheduler가 세션 시작/종료 시 호출
is_running() -> bool             GET /api/bot/status, /health에서 호출
attach_loop(loop)                FastAPI lifespan startup에서 호출 (이미 연결됨)
```

`_change_queue`의 `maxsize=1` 주의 사항: 현재 큐 용량이 1로 설정되어 있다. WebSocket 클라이언트가 느리거나 없는 상황에서 `put_nowait`가 `QueueFull`을 발생시킬 수 있다. `ws.py`의 브로드캐스트 태스크는 큐를 빠르게 소비해야 하며, 소비자가 없을 때 `push_snapshot`의 `except RuntimeError: pass` 처리로 무시된다.

---

## 라우터 구성 전략

`mutrade/admin/app.py`의 `create_app()`에 모든 엔드포인트를 직접 추가하지 않는다. FastAPI `APIRouter`로 기능별 파일을 분리한다.

```
mutrade/admin/
  ├── app.py              기존 — create_app(), lifespan, /health, 라우터 include
  ├── hub.py              기존 — BotStateHub (수정 없음)
  ├── routers/
  │   ├── __init__.py
  │   ├── state.py        GET /api/state, WebSocket /ws/state
  │   ├── bot.py          GET /api/bot/status, POST /api/bot/start, POST /api/bot/stop
  │   ├── history.py      GET /api/history
  │   └── config.py       GET /api/config, PUT /api/config
  ├── ws.py               ConnectionManager (WebSocket 연결 풀)
  ├── log_reader.py       [TRADE] 로그 파서
  ├── config_editor.py    Pydantic 검증 모델 + 원자적 파일 쓰기
  └── static/
      └── index.html      단일 파일 대시보드 UI
```

`app.py`의 `create_app()`에서 라우터를 include할 때 의존성을 주입한다:

```python
from mutrade.admin.routers import state, bot, history, config as config_router

app.include_router(state.router, prefix="/api")
app.include_router(bot.router, prefix="/api")
app.include_router(history.router, prefix="/api")
app.include_router(config_router.router, prefix="/api")
```

각 라우터는 `app.state.hub`, `app.state.scheduler`, `app.state.engine`, `app.state.config`를 `Request`를 통해 접근한다. 또는 `Depends()`로 주입한다.

---

## 실시간 모니터링: SSE vs WebSocket 결정

**결론: WebSocket을 선택한다.**

이유:

1. `BotStateHub.wait_for_change()`가 이미 `asyncio.Queue`를 사용하는 push 모델로 설계되어 있다. SSE는 클라이언트가 폴링하는 패턴이므로 이 설계와 맞지 않는다.
2. WebSocket은 서버 → 클라이언트 push와 클라이언트 → 서버 메시지(예: 미래에 수동 stop 트리거) 양방향이 가능하다.
3. FastAPI의 WebSocket 지원이 안정적이고 `starlette.testclient`로 테스트하기 쉽다.

SSE가 더 적합한 경우는 단방향 스트림이고 브라우저 재연결 자동 처리가 필요할 때다. 현재 요구사항에서는 WebSocket이 더 적합하다.

**데이터 흐름:**

```
APScheduler 스레드 (3~5초마다)
  poll_prices() → engine.tick() → hub.push_snapshot(states)
    └── loop.call_soon_threadsafe(queue.put_nowait, snapshot)

FastAPI asyncio 루프 — 백그라운드 태스크 (lifespan에서 create_task)
  async def broadcast_loop():
      while True:
          snapshot = await hub.wait_for_change()
          msg = json.dumps({"type": "state", "data": snapshot})
          await connection_manager.broadcast(msg)

브라우저 WebSocket 클라이언트
  ws.onmessage = ({data}) => updateDashboard(JSON.parse(data))
```

---

## 봇 제어 (start/stop) — APScheduler 스레드 안전 상호작용

### 중지 (POST /api/bot/stop)

```
FastAPI 엔드포인트 (asyncio 루프)
  hub.request_stop()   ← threading.Event.set() — 스레드 안전
    └── APScheduler run_session 루프 최상단에서 is_stop_requested() 확인
          └── hub.clear_stop(); break   ← 다음 poll_interval 내에 종료
```

이미 `monitor/scheduler.py`의 `run_session()` 루프에 `hub.is_stop_requested()` 체크가 구현되어 있다. FastAPI 엔드포인트는 `hub.request_stop()`만 호출하면 된다.

### 즉시 시작 (POST /api/bot/start)

```python
# admin/routers/bot.py
@router.post("/bot/start")
async def start_bot(request: Request):
    scheduler = request.app.state.scheduler
    hub = request.app.state.hub
    if hub.is_running():
        raise HTTPException(409, "봇이 이미 실행 중입니다.")
    hub.clear_stop()
    scheduler.get_job("market_poll").trigger()  # 즉시 실행
    return {"status": "started"}
```

`APScheduler 3.x`의 `scheduler.trigger_job("market_poll")`을 사용한다. 이 메서드는 스레드 안전하며, 다음 cron 트리거 시간을 기다리지 않고 즉시 잡을 실행한다.

**주의:** `trigger_job()`은 스케줄러 내부에서 새 스레드를 생성하여 실행하므로, FastAPI asyncio 루프에서 직접 호출해도 안전하다.

### dry_run 토글

`dry_run`은 `TrailingStopEngine`과 `OrderExecutor` 양쪽에 주입된 값이다. 런타임 토글은 두 객체 모두를 변경해야 한다. v1.1에서는 단순 상태 조회(is_dry_run)만 제공하고, 토글은 재시작을 안내하는 방식으로 설계한다. 이유: `dry_run=False` 상태에서 토글하면 미확인 매도 주문이 발생할 수 있어 안전하지 않다.

---

## config.toml 편집 흐름

```
브라우저 PUT /api/config (JSON)
  └── ConfigEditor.validate(payload)     Pydantic 검증 (필드 타입, 범위, 종목 코드 형식)
        ├── 실패: 422 Unprocessable Entity 반환
        └── 성공: ConfigEditor.write(payload)
              ├── tomlkit으로 TOML 직렬화 (tomllib은 읽기 전용)
              ├── tempfile.NamedTemporaryFile + os.replace() 원자적 쓰기
              └── load_config() 재실행 → app.state.config 갱신
```

### tomllib vs tomlkit

`tomllib`은 Python 3.11+ 표준 라이브러리이지만 **읽기 전용**이다. 쓰기를 위해 `tomlkit`(PyPI)을 추가 의존성으로 도입한다. `tomlkit`은 주석과 포매팅을 보존하는 round-trip 파서다.

```python
# admin/config_editor.py
import tomlkit
import tempfile
import os
from pathlib import Path
from pydantic import BaseModel, Field, field_validator

class SymbolUpdate(BaseModel):
    code: str
    name: str
    threshold: float = Field(default=0.10, gt=0.0, lt=1.0)

    @field_validator("code")
    @classmethod
    def code_must_be_6_digits(cls, v: str) -> str:
        if not v.isdigit() or len(v) != 6:
            raise ValueError("종목 코드는 6자리 숫자여야 합니다.")
        return v

class ConfigUpdate(BaseModel):
    poll_interval: float = Field(default=3.0, ge=1.0, le=60.0)
    default_threshold: float = Field(default=0.10, gt=0.0, lt=1.0)
    market_open_hour: int = Field(default=9, ge=0, le=23)
    market_open_minute: int = Field(default=0, ge=0, le=59)
    market_close_hour: int = Field(default=15, ge=0, le=23)
    market_close_minute: int = Field(default=20, ge=0, le=59)
    symbols: list[SymbolUpdate] = Field(min_length=1)

def write_config(payload: ConfigUpdate, path: Path = Path("config.toml")) -> None:
    doc = tomlkit.document()
    general = tomlkit.table()
    general.add("poll_interval", payload.poll_interval)
    general.add("default_threshold", payload.default_threshold)
    # ... 나머지 필드
    doc.add("general", general)
    symbols_array = tomlkit.aot()
    for s in payload.symbols:
        t = tomlkit.table()
        t.add("code", s.code)
        t.add("name", s.name)
        t.add("threshold", s.threshold)
        symbols_array.append(t)
    doc.add("symbols", symbols_array)

    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, delete=False, suffix=".tmp"
    ) as f:
        f.write(tomlkit.dumps(doc))
        tmp = f.name
    os.replace(tmp, path)
```

### AppConfig hot-reload 범위

config.toml 변경 후 `load_config()` 재실행으로 `app.state.config`를 갱신한다. 단, `TrailingStopEngine`과 `BackgroundScheduler`의 즉각 반영은 **다음 세션 시작 시**로 제한한다:

- `engine._symbols`: `frozen=True` AppConfig를 사용하지 않고 내부 dict로 관리 — 다음 `run_session()` 시작 시 `engine.reset_symbols(new_symbols)` 호출로 반영
- `poll_interval`: `time.sleep(config.poll_interval)` 참조값 — 현재 세션 중 변경 불가, 다음 세션 반영
- scheduler cron 트리거: `market_open_hour/minute` 변경 시 `scheduler.reschedule_job()` 필요

config 변경 후 응답에 `"effective": "next_session"` 필드를 포함하여 사용자에게 명확히 알린다.

---

## 거래 이력: [TRADE] 로그 파싱

`logs/mutrade.log`의 [TRADE] 마커 포맷 확인이 필요하다. 현재 `OrderExecutor`에서 어떤 포맷으로 기록하는지 기준으로 정규식을 작성한다.

```python
# admin/log_reader.py
import re
from pathlib import Path
from typing import Iterator

LOG_PATH = Path("logs/mutrade.log")
TRADE_PATTERN = re.compile(r"\[TRADE\].*")  # 실제 포맷 확인 후 구체화

def iter_trade_lines(path: Path = LOG_PATH) -> Iterator[str]:
    """파일 끝에서 역방향으로 [TRADE] 라인 스캔."""
    with open(path, "rb") as f:
        f.seek(0, 2)
        pos = f.tell()
        buf = b""
        while pos > 0:
            step = min(4096, pos)
            pos -= step
            f.seek(pos)
            chunk = f.read(step)
            buf = chunk + buf
            for line in reversed(buf.split(b"\n")):
                decoded = line.decode("utf-8", errors="replace")
                if "[TRADE]" in decoded:
                    yield decoded

def read_trade_history(limit: int = 100) -> list[dict]:
    lines = []
    for line in iter_trade_lines():
        parsed = parse_trade_line(line)
        if parsed:
            lines.append(parsed)
        if len(lines) >= limit:
            break
    return lines
```

역방향 읽기(tail 패턴)를 사용하는 이유: loguru 10MB 로테이션 기준 최대 수만 라인이 존재할 수 있다. 최근 100건만 필요하므로 파일 끝에서부터 스캔한다.

---

## 프론트엔드: 단일 HTML 파일

빌드 툴체인(React, Vue, webpack) 없이 FastAPI `StaticFiles` + 단일 `index.html`로 구성한다.

```python
# app.py create_app() 내부 추가
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

app.mount("/static", StaticFiles(directory="mutrade/admin/static"), name="static")

@app.get("/")
async def dashboard():
    return FileResponse("mutrade/admin/static/index.html")
```

`index.html` 구성:
- 인라인 CSS + 바닐라 JS
- CDN에서 로드: 없음 또는 최소한 (오프라인 환경 대비)
- WebSocket 클라이언트: 브라우저 네이티브 `WebSocket` API
- 테이블 렌더링: `innerHTML` 또는 `insertRow`/`insertCell`

---

## 완전한 API 엔드포인트 목록

| Method | Path | 기능 | 구현 파일 |
|--------|------|------|-----------|
| `GET` | `/` | Dashboard HTML | `app.py` + `static/index.html` |
| `GET` | `/health` | 서버/봇 상태 (기존) | `app.py` |
| `WebSocket` | `/ws/state` | 실시간 상태 스트림 | `routers/state.py` + `ws.py` |
| `GET` | `/api/state` | 현재 스냅샷 (REST 폴백) | `routers/state.py` |
| `GET` | `/api/bot/status` | 봇 실행/dry_run 상태 | `routers/bot.py` |
| `POST` | `/api/bot/stop` | 세션 중단 요청 | `routers/bot.py` |
| `POST` | `/api/bot/start` | 세션 즉시 시작 | `routers/bot.py` |
| `GET` | `/api/history` | 거래 이력 (최근 N건) | `routers/history.py` |
| `GET` | `/api/config` | config.toml 현재 내용 | `routers/config.py` |
| `PUT` | `/api/config` | config 수정 (검증+저장) | `routers/config.py` |

---

## 신규/수정 파일 목록 (v1.1 전체)

### 신규 생성

| 파일 | 역할 |
|------|------|
| `mutrade/admin/ws.py` | ConnectionManager (WebSocket 연결 풀, broadcast) |
| `mutrade/admin/log_reader.py` | [TRADE] 로그 역방향 파싱 |
| `mutrade/admin/config_editor.py` | ConfigUpdate Pydantic 모델, tomlkit 쓰기, 원자적 저장 |
| `mutrade/admin/routers/__init__.py` | 패키지 |
| `mutrade/admin/routers/state.py` | GET /api/state, WebSocket /ws/state |
| `mutrade/admin/routers/bot.py` | GET/POST /api/bot/* |
| `mutrade/admin/routers/history.py` | GET /api/history |
| `mutrade/admin/routers/config.py` | GET/PUT /api/config |
| `mutrade/admin/static/index.html` | 단일 파일 대시보드 UI |

### 수정

| 파일 | 변경 내용 |
|------|-----------|
| `mutrade/admin/app.py` | 라우터 include, StaticFiles 마운트, broadcast 백그라운드 태스크 추가, lifespan에 scheduler injection 강화 |
| `mutrade/main.py` | `create_app()`에 `engine`, `config` 추가 전달 (이미 kwargs에 있음 — app.state에 저장 추가) |

### 수정 없음

| 파일 | 이유 |
|------|------|
| `mutrade/admin/hub.py` | 이미 완전히 구현됨 |
| `mutrade/monitor/scheduler.py` | hub 연동 이미 완료 |
| `mutrade/engine/trailing_stop.py` | 변경 불필요 |
| `mutrade/engine/state_store.py` | 변경 불필요 |
| `mutrade/executor/order_executor.py` | 변경 불필요 |
| `mutrade/settings.py` | 변경 불필요 |
| `mutrade/config/loader.py` | 변경 불필요 (읽기는 그대로, 쓰기는 config_editor.py에서) |

---

## 빌드 순서 (의존성 기반)

Phase 5가 완료되어 BotStateHub와 BackgroundScheduler 기반이 갖춰진 상태다. 이를 기준으로 순서를 정한다.

### Phase A: 읽기 전용 상태 모니터링 (WebSocket 대시보드)

의존성: BotStateHub.wait_for_change() (구현됨), BotStateHub.get_snapshot() (구현됨)

1. `admin/ws.py` — ConnectionManager 구현 (WebSocket 연결 풀, broadcast)
2. `admin/routers/state.py` — GET /api/state + WebSocket /ws/state + 브로드캐스트 백그라운드 태스크
3. `admin/app.py` 수정 — 라우터 include, broadcast 태스크 시작, StaticFiles 마운트
4. `admin/static/index.html` — 현황 테이블 + WebSocket 연결 JS

검증 기준: 봇 실행 중 브라우저에서 종목별 peak_price/warm이 3~5초마다 갱신됨.

### Phase B: 봇 제어

의존성: hub.request_stop() (구현됨), scheduler.trigger_job() (APScheduler 3.x)

5. `admin/routers/bot.py` — GET /api/bot/status, POST /api/bot/stop, POST /api/bot/start
6. `admin/app.py` 수정 — app.state.scheduler 저장 (kwargs에 이미 있음 — lifespan에서 app.state에 할당)
7. `admin/static/index.html` — 제어 버튼 + 상태 표시 섹션 추가

검증 기준: POST /api/bot/stop 후 run_session 루프 종료 로그 확인.

### Phase C: 거래 이력

의존성: logs/mutrade.log 존재, [TRADE] 마커 포맷 확인

8. `admin/log_reader.py` — 역방향 파일 읽기 + [TRADE] 파싱 + 단위 테스트
9. `admin/routers/history.py` — GET /api/history
10. `admin/static/index.html` — 거래 이력 테이블 섹션 추가

검증 기준: DRY-RUN 매도 신호 발생 후 /api/history 응답에 해당 레코드 포함.

### Phase D: 설정 편집

의존성: tomlkit 설치, config.toml 스키마 안정적

11. `pyproject.toml` — `tomlkit` 의존성 추가
12. `admin/config_editor.py` — ConfigUpdate 모델 + 원자적 쓰기
13. `admin/routers/config.py` — GET /api/config, PUT /api/config
14. `admin/static/index.html` — 설정 폼 섹션 + 저장 버튼

검증 기준: PUT /api/config로 threshold 변경 후 config.toml 내용 갱신 확인.

---

## 스레드 안전성 요약

| 상호작용 | 방법 | 안전 여부 |
|----------|------|-----------|
| APScheduler → FastAPI: 상태 전달 | `loop.call_soon_threadsafe(queue.put_nowait, data)` | 안전 (이미 구현) |
| FastAPI → APScheduler: 중지 명령 | `threading.Event.set()` | 안전 (이미 구현) |
| FastAPI → APScheduler: 즉시 시작 | `scheduler.trigger_job()` (APScheduler 내부 잠금) | 안전 |
| FastAPI: 스냅샷 읽기 | `hub.get_snapshot()` + `threading.RLock` | 안전 |
| FastAPI: config.toml 쓰기 | `tempfile` + `os.replace()` 원자적 | 안전 |
| FastAPI: 로그 읽기 | 파일 읽기 전용, loguru가 별도 쓰기 | 안전 (읽기와 쓰기 순서 보장 필요 없음) |

---

## 보안 주의 사항

- FastAPI는 `host="127.0.0.1"`로 바인딩됨 — 로컬 전용 (현재 main.py 확인됨)
- 외부 접속 시 SSH 터널 권장: `ssh -L 8000:localhost:8000 server`
- `GET /api/config` 응답에 KIS API 키, Telegram 토큰 절대 포함 금지. `config_editor.py`는 `config.toml`만 다루고 `.env`는 건드리지 않는다
- `PUT /api/config` 입력은 Pydantic 검증 통과 후에만 파일 쓰기

---

## 확장성 고려

| 우려 사항 | v1.1 (개인 봇) | 추후 필요 시 |
|-----------|---------------|-------------|
| WebSocket 연결 수 | 1~2개 | Redis PubSub으로 멀티 워커 지원 |
| config 동시 편집 | 단일 운영자, 충돌 없음 | ETag 낙관적 잠금 |
| 로그 파일 크기 | loguru 10MB 로테이션, 역방향 읽기로 충분 | SQLite 거래 이력 DB |
| 인증 | 127.0.0.1 로컬 바인딩 | Basic Auth / 토큰 (외부 노출 시) |
| APScheduler 버전 | BackgroundScheduler 3.x, trigger_job() 사용 | APScheduler 4.x AsyncIO 전환 시 API 변경 확인 필요 |
| _change_queue maxsize=1 | 단일 소비자, 빠른 소비 | maxsize 제거 또는 조건부 drop 로직 |

---

## Sources

- 코드베이스 직접 분석 (HIGH confidence): `mutrade/main.py`, `mutrade/admin/hub.py`, `mutrade/admin/app.py`, `mutrade/monitor/scheduler.py`, `mutrade/settings.py`, `mutrade/config/loader.py`, `mutrade/engine/models.py`
- FastAPI WebSocket 공식 문서: https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI StaticFiles: https://fastapi.tiangolo.com/tutorial/static-files/
- APScheduler BackgroundScheduler trigger_job: https://apscheduler.readthedocs.io/en/3.x/modules/schedulers/base.html
- Python asyncio call_soon_threadsafe: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe
- tomlkit (round-trip TOML 쓰기): https://github.com/sdispater/tomlkit

---

## v1.0 원본 아키텍처 (보존)

아래 내용은 v1.0 설계 기록이다. 의사결정 히스토리 보존을 위해 유지한다.

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
│  │  Scheduler   │────▶│  Price       │◀────│  REST         │   │
│  │  (APSched)   │     │  Monitor     │     │  Price Feed   │   │
│  └──────────────┘     └──────┬───────┘     └───────────────┘   │
│                              ▼                                  │
│                       ┌──────────────┐                         │
│                       │  Trailing    │◀──── state.json         │
│                       │  Stop Engine │                         │
│                       └──────┬───────┘                         │
│                              ▼                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌───────────────┐   │
│  │  Notifier    │◀────│  Order       │────▶│  KIS Order    │   │
│  │  (Telegram)  │     │  Executor    │     │  API          │   │
│  └──────────────┘     └──────────────┘     └───────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```
