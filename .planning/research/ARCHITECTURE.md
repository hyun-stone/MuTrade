# Architecture Patterns: FastAPI Admin Dashboard Integration

**Domain:** 기존 단일 프로세스 트레이딩 봇에 Admin Web UI 추가
**Researched:** 2026-04-12
**Confidence:** HIGH (코드베이스 직접 분석 + FastAPI 공식 패턴)

> 이 파일은 v1.1 Admin Dashboard 마일스톤을 위해 갱신된 버전이다.
> 이전 v1.0 아키텍처 문서는 하단 "v1.0 원본 아키텍처" 섹션에 보존한다.

---

## 핵심 결정: 동일 프로세스 vs 별도 프로세스

### 결론: 동일 프로세스 (In-Process), uvicorn이 메인 루프를 담당

**근거:**

1. **TrailingStopEngine 상태 공유가 목적 자체다.** 별도 프로세스는 IPC 없이 in-memory `_states` dict를 공유할 수 없다. state.json 폴링도 가능하지만 3~5초 폴링 지연이 발생해 실시간 WebSocket의 의미가 없어진다.

2. **기존 main.py가 이미 다중 스레드 구조다.** `TelegramListener`가 daemon thread에서 asyncio loop를 실행한다. FastAPI/uvicorn을 동일한 방식(daemon thread)으로 추가하면 기존 패턴과 일관된다.

3. **단일 사용자 개인용 봇이다.** Admin Dashboard 접속자는 운영자 한 명뿐이다. Redis PubSub, 멀티 워커 같은 분산 구조는 불필요하다.

4. **별도 프로세스의 복잡도가 이득보다 크다.** 별도 프로세스는 프로세스 관리(systemd 2개), 포트 충돌, IPC 레이어가 추가된다.

**별도 프로세스를 선택해야 하는 경우:** 훗날 다중 사용자, 봇 장애가 Dashboard에 전파되면 안 되는 요구, 또는 봇을 Docker 컨테이너로 격리할 때. v1.1 범위에서는 해당 없음.

---

## 현재 아키텍처 (v1.0 기준)

```
메인 스레드 (BlockingScheduler — 여기서 블로킹)
  └── APScheduler BlockingScheduler.start()
        └── run_session() 클로저 (Mon-Fri 09:00 KST 실행)
              ├── poll_prices() → KIS REST API
              ├── TrailingStopEngine.tick(prices)  ← _states dict 변경
              └── OrderExecutor.execute(signal)    ← _pending set 변경

TelegramListener 스레드 (daemon)
  └── asyncio.run(run())  ← 별도 이벤트 루프
        └── python-telegram-bot Application polling
              └── /status 핸들러 → engine.states 읽기 (read-only)
```

**현재 스레드 안전성:**
- `TrailingStopEngine._states`: 메인 스레드만 쓰고, TelegramListener는 읽기만 함. `engine.states` 프로퍼티가 `dict(self._states)` 복사본을 반환하므로 현재는 안전함.
- `OrderExecutor._pending`: 메인 스레드 단독 접근 → Lock 불필요 (코드 주석에도 명시됨).
- `StateStore.save()`: tempfile + os.replace() 원자적 쓰기 → 파일 수준 안전.

---

## v1.1 목표 아키텍처

```
메인 스레드
  └── uvicorn.run(app, host="127.0.0.1", port=8080)  ← NEW: 블로킹 역할 이전

APScheduler 스레드 (daemon)  ← CHANGED: BlockingScheduler → BackgroundScheduler
  └── run_session() 클로저 (기존과 동일 로직)
        ├── poll_prices() → KIS REST API
        ├── TrailingStopEngine.tick(prices)
        ├── hub.push_snapshot(engine.states)  ← NEW: 상태 브로드캐스트
        └── OrderExecutor.execute(signal)

TelegramListener 스레드 (daemon)  ← 변경 없음
  └── asyncio loop + python-telegram-bot polling

FastAPI 이벤트 루프 (uvicorn 내부)
  ├── WebSocket 연결 관리 (ConnectionManager)
  ├── REST 엔드포인트 (봇 제어, config 편집, 거래 이력)
  └── 상태 브로드캐스트 백그라운드 태스크
```

**핵심 변경:** `start_scheduler()`의 `BlockingScheduler`를 `BackgroundScheduler`로 교체하고, `main.py` 마지막에서 `uvicorn.run()`으로 블로킹한다.

---

## 컴포넌트 경계

| 컴포넌트 | 역할 | 파일 위치 | 변경 여부 |
|----------|------|-----------|-----------|
| `TrailingStopEngine` | 고점 추적, 매도 신호 발생 | `engine/trailing_stop.py` | 수정 없음 |
| `StateStore` | state.json 원자적 저장 | `engine/state_store.py` | 수정 없음 |
| `OrderExecutor` | 매도 주문 실행 | `executor/order_executor.py` | 수정 없음 |
| `TelegramListener` | /status 명령 수신 | `notifier/telegram_listener.py` | 수정 없음 |
| `BotStateHub` | 봇 shared state 중앙 허브 | `admin/hub.py` | **신규** |
| `FastAPI app` | HTTP/WebSocket 서버 | `admin/app.py` | **신규** |
| `ConnectionManager` | WebSocket 연결 풀 관리 | `admin/ws.py` | **신규** |
| `TradeLogReader` | [TRADE] 로그 파싱 | `admin/log_reader.py` | **신규** |
| `ConfigEditor` | config.toml 읽기/쓰기/검증 | `admin/config_editor.py` | **신규** |
| `static/index.html` | 단일 파일 대시보드 UI | `admin/static/index.html` | **신규** |
| `scheduler.py` | APScheduler 스케줄러 | `monitor/scheduler.py` | **수정** |
| `main.py` | 엔트리포인트 | `mutrade/main.py` | **수정** |

---

## 스레드 안전성 상세 분석

### 문제: FastAPI asyncio 루프 ↔ APScheduler 스레드 간 공유 상태

APScheduler `BackgroundScheduler`의 잡 함수는 APScheduler 내부 스레드풀에서 실행된다. `TrailingStopEngine.tick()`이 `_states` dict를 수정하는 것도 이 스레드에서 일어난다.

FastAPI WebSocket 브로드캐스트는 uvicorn asyncio 이벤트 루프(메인 스레드)에서 실행된다.

두 실행 컨텍스트가 공유 객체에 동시 접근하는 것은 안전하지 않다.

### 해결책: `BotStateHub` — thread-safe 상태 허브

`TrailingStopEngine`은 건드리지 않는다. `BotStateHub`가 두 세계 사이의 브릿지 역할을 한다.

```
APScheduler 스레드                    FastAPI asyncio 루프 (메인 스레드)
      │                                          │
      │ engine.tick() 완료 후                   │ GET /api/state
      │ hub.push_snapshot(states)               │ hub.get_snapshot()
      │                                          │
      └────────────► BotStateHub ◄──────────────┘
                  ┌──────────────────────────────┐
                  │ _lock: threading.RLock        │
                  │ _snapshot: dict               │  ← RLock으로 보호
                  │ _loop: asyncio event loop     │
                  │ _change_queue: asyncio.Queue  │  ← 브로드캐스트 알림
                  │ _stop_event: threading.Event  │  ← 봇 제어
                  │ _is_running: bool             │  ← 봇 실행 상태
                  └──────────────────────────────┘
```

**APScheduler 스레드 → FastAPI 루프 방향 (push_snapshot):**

`asyncio.Queue`는 이벤트 루프 내부에서만 안전하게 쓸 수 있다. APScheduler 스레드에서 직접 `queue.put_nowait()`를 호출하면 스레드 안전하지 않다. 반드시 `loop.call_soon_threadsafe(queue.put_nowait, data)`를 사용해야 한다.

**FastAPI 루프 → APScheduler 스레드 방향 (stop/start):**

`threading.Event`는 스레드 안전하다. FastAPI 엔드포인트에서 `hub.request_stop()`을 호출하면 APScheduler 잡 루프에서 `hub.is_stop_requested()`로 확인하여 소프트 스탑이 가능하다.

### `BotStateHub` 인터페이스

```python
# mutrade/admin/hub.py
import asyncio
import threading
from mutrade.engine.models import SymbolState

class BotStateHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: dict = {}
        self._loop: asyncio.AbstractEventLoop | None = None
        self._change_queue: asyncio.Queue | None = None
        self._stop_event = threading.Event()
        self._is_running = False

    # FastAPI lifespan에서 호출 — 이벤트 루프와 큐 연결
    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        self._change_queue = asyncio.Queue()

    # APScheduler 스레드에서 호출 (tick 완료 후)
    def push_snapshot(self, states: dict[str, SymbolState]) -> None:
        serialized = {
            code: {
                "code": s.code,
                "peak_price": s.peak_price,
                "warm": s.warm,
            }
            for code, s in states.items()
        }
        with self._lock:
            self._snapshot = serialized
        if self._loop and self._change_queue:
            self._loop.call_soon_threadsafe(
                self._change_queue.put_nowait, serialized
            )

    # FastAPI asyncio 루프에서 호출
    def get_snapshot(self) -> dict:
        with self._lock:
            return dict(self._snapshot)

    async def wait_for_change(self) -> dict:
        """브로드캐스트 태스크에서 await — 새 스냅샷이 올 때까지 대기."""
        return await self._change_queue.get()

    # 봇 제어 (FastAPI → APScheduler 스레드)
    def request_stop(self) -> None:
        self._stop_event.set()

    def clear_stop(self) -> None:
        self._stop_event.clear()

    def is_stop_requested(self) -> bool:
        return self._stop_event.is_set()

    # 봇 실행 상태 (APScheduler 스레드가 set/clear)
    def set_running(self, running: bool) -> None:
        with self._lock:
            self._is_running = running

    def is_running(self) -> bool:
        with self._lock:
            return self._is_running
```

---

## 데이터 흐름: 봇 상태 → WebSocket → 브라우저

```
1. APScheduler 스레드 (3~5초마다)
   poll_prices()
     → engine.tick(prices)           ← _states 갱신
     → hub.push_snapshot(states)
         → loop.call_soon_threadsafe(queue.put_nowait, snapshot)

2. FastAPI asyncio 루프 (브로드캐스트 백그라운드 태스크)
   async def broadcast_loop():
       while True:
           snapshot = await hub.wait_for_change()  ← 새 데이터 올 때까지 대기
           msg = json.dumps({"type": "state", "data": snapshot})
           await connection_manager.broadcast(msg)

3. 브라우저 WebSocket 클라이언트
   ws.onmessage = (event) => {
       const {type, data} = JSON.parse(event.data)
       if (type === "state") updateTable(data)
   }
```

브로드캐스트 태스크는 `asyncio.create_task()`로 FastAPI lifespan에서 시작한다. WebSocket 연결이 없을 때는 `broadcast()`가 즉시 반환하므로 무해하다.

---

## 봇 시작/중지 제어

### 소프트 스탑: `threading.Event` 삽입

`run_session()` 루프에 체크 포인트 추가:

```python
# monitor/scheduler.py run_session() 내부
while True:
    if hub.is_stop_requested():
        logger.info("Admin UI 중단 요청 — 세션 종료.")
        hub.clear_stop()
        break

    now_kst = datetime.now(KST)
    if current_minutes >= close_minutes:
        break

    prices = poll_prices(kis, config)
    signals = engine.tick(prices)
    hub.push_snapshot(engine.states)   # ← 신규
    hub.set_running(True)              # ← 신규

    for sig in signals:
        if not sig.dry_run:
            executor.execute(sig)

    time.sleep(config.poll_interval)

hub.set_running(False)  # ← 세션 종료 시
```

### 즉시 시작: APScheduler `trigger_job()`

`start_scheduler()`가 scheduler 인스턴스를 반환하도록 수정. FastAPI 엔드포인트에서:

```python
# POST /api/bot/start
scheduler.trigger_job("market_poll")  # 다음 스케줄 기다리지 않고 즉시 실행
```

---

## config.toml 편집 흐름

```
브라우저 PUT /api/config (JSON payload)
       │
       ▼
ConfigEditor.validate(payload)   ← Pydantic 모델 검증
       │ 검증 실패 → 422 응답 반환
       │ 검증 성공
       ▼
ConfigEditor.write(payload)      ← config.toml 원자적 쓰기 (tempfile+replace)
       │
       ▼
hub.reload_config()
       │
       ├── load_config() 재실행 → 새 AppConfig
       ├── engine._symbols 갱신 (TrailingStopEngine에 새 symbols 주입)
       └── scheduler 잡 재등록 (새 poll_interval 반영)
```

### Pydantic 검증 모델

```python
# mutrade/admin/config_editor.py
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
    symbols: list[SymbolUpdate] = Field(min_length=1)
```

**symbols 목록 변경 시 `TrailingStopEngine` hot-reload:**
- `frozen=True` dataclass라 `AppConfig` 직접 수정 불가
- `engine._symbols`는 dict이므로 직접 교체 가능. 단, 이 조작은 APScheduler 스레드가 `tick()` 중에 수행되면 안 되므로 RLock으로 보호하거나, 새 세션 시작 시에만 반영하도록 설계
- 가장 안전한 방법: config 변경 후 현재 세션이 있으면 다음 세션 시작 시 적용 (즉각 반영 불필요)

---

## 거래 이력: [TRADE] 로그 파싱

`logs/mutrade.log`에서 `[TRADE]` 마커 라인 추출:

```
[TRADE] 매도 주문 제출: 005930 (삼성전자) qty=100 current_price=75,000
        peak=80,000 drop=6.25% threshold=10.0% order=1234567
```

```python
# mutrade/admin/log_reader.py
import re
from pathlib import Path

TRADE_PATTERN = re.compile(
    r"\[TRADE\] 매도 주문 제출: (\S+) \((.+?)\) qty=(\d+) "
    r"current_price=([\d,]+) peak=([\d,]+) drop=([\d.]+)% "
    r"threshold=([\d.]+)% order=(\S+)"
)

def read_trade_history(
    log_path: str | Path = "logs/mutrade.log",
    limit: int = 100,
) -> list[dict]:
    """[TRADE] 마커 라인을 파싱하여 최근 limit건의 거래 이력 반환."""
    ...
```

전체 로그 파일은 최대 10MB (loguru rotation). 전체 읽기로도 충분하지만 파일 끝에서 역방향으로 limit줄만 읽는 tail 패턴을 권장한다.

---

## 프론트엔드 전략: 단일 HTML 파일

별도 빌드 툴체인(React, Vue, webpack 등) 없이 FastAPI `StaticFiles` + 단일 `index.html`로 구성한다. 개인 봇 대시보드에 JS 빌드 파이프라인은 과도하다.

```
mutrade/admin/
  ├── static/
  │   └── index.html      ← 인라인 CSS + JS, CDN에서 필요 라이브러리 로드
  ├── app.py              ← FastAPI 앱 팩토리
  ├── hub.py              ← BotStateHub
  ├── ws.py               ← ConnectionManager
  ├── log_reader.py       ← [TRADE] 파서
  └── config_editor.py    ← config 검증/쓰기
```

**WebSocket 클라이언트:** 브라우저 네이티브 `WebSocket` API. 빌드 툴 불필요.
**테이블 렌더링:** vanilla JS DOM manipulation.
**차트 (선택):** Chart.js CDN (가격 추이 표시용).

---

## main.py 변경 포인트

```python
# mutrade/main.py (변경 후 마지막 부분)

hub = BotStateHub()

# scheduler: BackgroundScheduler 반환으로 변경
scheduler = start_scheduler(kis, config, engine, executor, hub)

# FastAPI 앱 생성 (의존성 주입)
app = create_app(hub=hub, engine=engine, executor=executor,
                 config=config, scheduler=scheduler)

# uvicorn이 메인 루프 담당 (블로킹)
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8080, log_level="warning")
```

`TelegramListener`는 기존과 동일하게 daemon thread에서 시작한 후 uvicorn.run()을 호출하면 된다.

---

## API 엔드포인트 목록

| Method | Path | 기능 | 구현 위치 |
|--------|------|------|-----------|
| `GET` | `/` | Dashboard HTML | `app.py` |
| `WebSocket` | `/ws/state` | 실시간 상태 스트림 | `app.py` + `ws.py` |
| `GET` | `/api/state` | 현재 스냅샷 (REST) | `app.py` + `hub.py` |
| `GET` | `/api/history` | 거래 이력 | `app.py` + `log_reader.py` |
| `GET` | `/api/config` | 현재 config.toml 내용 | `app.py` + `config_editor.py` |
| `PUT` | `/api/config` | config 수정 (검증+저장) | `app.py` + `config_editor.py` |
| `GET` | `/api/bot/status` | 봇 실행 상태 | `app.py` + `hub.py` |
| `POST` | `/api/bot/stop` | 세션 중단 요청 | `app.py` + `hub.py` |
| `POST` | `/api/bot/start` | 세션 즉시 시작 | `app.py` + `scheduler` |

---

## 빌드 순서 (Phase 분해)

이전 단계에 의존하므로 순차 구현 필수.

**Phase 1: 기반 — BotStateHub + Scheduler 수정**
1. `admin/hub.py` — BotStateHub 구현 및 단위 테스트 (threading.RLock, Event 동작 검증)
2. `monitor/scheduler.py` — BackgroundScheduler 전환 + `hub.push_snapshot()` 연동
3. `main.py` — uvicorn 통합 (엔드포인트 없어도 서버가 뜨는지 확인)

**Phase 2: 상태 조회 (읽기 전용)**
4. `admin/ws.py` — ConnectionManager 구현
5. `admin/app.py` — `GET /api/state` + `WebSocket /ws/state` 브로드캐스트 태스크
6. `admin/static/index.html` — 현황 테이블 + WebSocket 클라이언트

**Phase 3: 거래 이력**
7. `admin/log_reader.py` — [TRADE] 정규식 파서 + 테스트
8. `admin/app.py` — `GET /api/history` 엔드포인트
9. `index.html` — 거래 이력 테이블 섹션 추가

**Phase 4: 봇 제어**
10. `hub.py` 확장 — stop/start Event + `is_running` 플래그
11. `admin/app.py` — `POST /api/bot/stop`, `POST /api/bot/start`, `GET /api/bot/status`
12. `index.html` — 제어 버튼 + 봇 상태 표시

**Phase 5: 설정 변경**
13. `admin/config_editor.py` — Pydantic 검증 모델 + 원자적 쓰기
14. `admin/app.py` — `GET /api/config`, `PUT /api/config`
15. TrailingStopEngine hot-reload 연동 (symbols 변경 처리)
16. `index.html` — 설정 폼 섹션

**각 Phase는 pytest + httpx `TestClient`로 독립 검증 가능.** WebSocket 테스트는 `starlette.testclient.TestClient`의 `websocket_connect()` 사용.

---

## 보안 주의 사항

- FastAPI는 기본 `host="127.0.0.1"`로 바인딩. 로컬 전용.
- 외부 접속이 필요하면 SSH 터널 권장 (`ssh -L 8080:localhost:8080 server`).
- KIS API 자격증명, Telegram 토큰은 절대 `/api/config` 응답에 포함하지 않는다. `ConfigEditor`는 `config.toml`만 다루고 `.env`는 건드리지 않는다.
- `PUT /api/config` 입력은 Pydantic 검증 통과 후에만 파일 쓰기.
- `index.html`에 Basic Auth 추가는 v1.2+에서 고려 (현재 로컬 바인딩으로 충분).

---

## 확장성 고려

| 우려 사항 | v1.1 (개인 봇) | 추후 필요 시 |
|-----------|---------------|-------------|
| WebSocket 연결 수 | 1~2개 | Redis PubSub으로 멀티 워커 지원 |
| config 동시 편집 | 단일 운영자, 충돌 없음 | ETag 낙관적 잠금 |
| 로그 파일 크기 | loguru 10MB 로테이션, 전체 읽기 허용 | SQLite 거래 이력 DB |
| 인증 | 127.0.0.1 로컬 바인딩으로 충분 | Basic Auth / 토큰 (외부 노출 시) |
| APScheduler 버전 | BackgroundScheduler 3.x | APScheduler 4.x AsyncIO 전환 |

---

## Sources

- FastAPI WebSocket 공식 문서: https://fastapi.tiangolo.com/advanced/websockets/
- FastAPI 비동기/스레딩 공식 문서: https://fastapi.tiangolo.com/async/
- APScheduler BackgroundScheduler 공식 문서: https://apscheduler.readthedocs.io/en/3.x/
- Python threading.Event 공식: https://docs.python.org/3/library/threading.html#threading.Event
- asyncio 스레드 안전 브릿지: https://docs.python.org/3/library/asyncio-eventloop.html#asyncio.loop.call_soon_threadsafe
- 기존 코드베이스 직접 분석 (HIGH confidence) — mutrade/main.py, engine/trailing_stop.py, monitor/scheduler.py, notifier/telegram_listener.py

---

## v1.0 원본 아키텍처 (보존)

아래 내용은 v1.0 설계 기록이다. v1.1 구현과 충돌하는 부분이 있으나 의사결정 히스토리 보존을 위해 유지한다.

### v1.0 컴포넌트 다이어그램

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

### v1.0 Anti-Patterns (여전히 유효)

- **Re-issuing Token on Every Request:** `/oauth2/tokenP` 매 호출마다 발급 금지. python-kis가 keep_token=True로 자동 관리.
- **Selling on Failed Price Fetch:** 가격 조회 실패를 매도 신호로 처리 금지.
- **In-Memory-Only High-Water Marks:** state.json 원자적 저장으로 재시작 후 복원.
- **Hardcoding KST as UTC+9 Offset:** `zoneinfo.ZoneInfo("Asia/Seoul")` 사용.
- **Polling Too Fast:** KIS rate limit 준수 (3초 간격, symbols 수 × REST call).
