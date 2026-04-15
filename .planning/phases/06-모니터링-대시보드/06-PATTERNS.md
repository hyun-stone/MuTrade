# Phase 6: 모니터링 대시보드 - Pattern Map

**Mapped:** 2026-04-15
**Files analyzed:** 6 (수정 대상 5 + 신규 생성 1)
**Analogs found:** 6 / 6

---

## File Classification

| 신규/수정 파일 | Role | Data Flow | 가장 가까운 Analog | Match Quality |
|----------------|------|-----------|-------------------|---------------|
| `mutrade/admin/hub.py` | service (state bridge) | event-driven | 자기 자신 (수정 대상) | exact |
| `mutrade/admin/app.py` | controller (FastAPI factory) | request-response + streaming | 자기 자신 (수정 대상) | exact |
| `mutrade/monitor/scheduler.py` | service (scheduler loop) | event-driven | 자기 자신 (수정 대상) | exact |
| `mutrade/executor/order_executor.py` | service (KIS order) | request-response | 자기 자신 (수정 대상) | exact |
| `mutrade/admin/static/index.html` | component (단일 파일 프론트엔드) | streaming (WebSocket) | 없음 (신규 생성) | no-analog |
| `tests/test_hub.py` | test | — | `tests/test_scheduler.py` | role-match |

---

## Pattern Assignments

### `mutrade/admin/hub.py` (service, event-driven) — 수정 대상

**수정 내용:** `push_snapshot()` 시그니처 확장 (INFRA-01) + `asyncio.QueueFull` 버그 수정 (INFRA-02)

**현재 파일 위치:** `/Users/sean/Study/MuTrade/MuTrade/mutrade/admin/hub.py`

**기존 imports 패턴** (lines 1-13):
```python
import asyncio
import threading
from typing import Optional
```

**기존 `push_snapshot()` 시그니처** (lines 31-61):
```python
def push_snapshot(self, states: dict) -> None:
    """
    APScheduler 스레드에서 호출. engine.states 딕셔너리를 직렬화하여 저장.
    attach_loop()가 호출된 경우 asyncio.Queue에도 push.
    states: engine.states (SymbolState dict 또는 이미 직렬화된 dict)
    """
    serialized: dict = {}
    for code, s in states.items():
        if hasattr(s, '__dataclass_fields__') or hasattr(s, 'peak_price'):
            serialized[code] = {
                "code": getattr(s, 'code', code),
                "peak_price": getattr(s, 'peak_price', 0.0),
                "warm": getattr(s, 'warm', False),
            }
        else:
            serialized[code] = s  # 이미 dict인 경우

    with self._lock:
        self._snapshot = serialized

    if self._loop is not None and self._change_queue is not None:
        try:
            self._loop.call_soon_threadsafe(
                self._change_queue.put_nowait, dict(serialized)  # ← QueueFull 버그 위치 (line 57)
            )
        except RuntimeError:
            pass
```

**수정 패턴 1 — 시그니처 확장 (INFRA-01):**
- 기존 `push_snapshot(self, states: dict)` → `push_snapshot(self, states: dict, prices: dict[str, float] | None = None, pending_codes: frozenset[str] | None = None)` 로 확장
- 직렬화 시 `current_price`, `drop_pct`, `sell_pending` 필드 추가
- `drop_pct` 계산: `((current - peak) / peak)` — peak > 0 and current > 0 방어 필요

**수정 패턴 2 — QueueFull 버그 수정 (INFRA-02):**
- `call_soon_threadsafe(self._change_queue.put_nowait, ...)` 직접 전달 방식 변경
- 대신 내부 `_put_snapshot` 메서드를 만들어 `call_soon_threadsafe(self._put_snapshot, data)` 패턴으로 전환
- `_put_snapshot` 내부에서 큐가 가득 찼으면 `get_nowait()`로 기존 항목 버리기

**핵심 수정 대상 코드 (line 54-61):**
```python
# 현재 (버그 있음):
if self._loop is not None and self._change_queue is not None:
    try:
        self._loop.call_soon_threadsafe(
            self._change_queue.put_nowait, dict(serialized)
        )
    except RuntimeError:
        pass

# 수정 후 패턴:
if self._loop is not None and self._change_queue is not None:
    try:
        self._loop.call_soon_threadsafe(self._put_snapshot, dict(serialized))
    except RuntimeError:
        pass

def _put_snapshot(self, data: dict) -> None:
    """asyncio 이벤트 루프 스레드 내에서 실행 (call_soon_threadsafe 통해 스케줄됨)."""
    assert self._change_queue is not None
    if self._change_queue.full():
        try:
            self._change_queue.get_nowait()  # 기존 항목 버리기
        except asyncio.QueueEmpty:
            pass  # 경합 조건 방어
    try:
        self._change_queue.put_nowait(data)
    except asyncio.QueueFull:
        pass  # 극히 드문 경합 — 무시
```

---

### `mutrade/admin/app.py` (controller, request-response + streaming) — 수정 대상

**수정 내용:** `/ws` WebSocket 엔드포인트 추가 + `StaticFiles` 마운트 + `GET /` 라우트 추가

**현재 파일 위치:** `/Users/sean/Study/MuTrade/MuTrade/mutrade/admin/app.py`

**기존 imports 패턴** (lines 1-20):
```python
import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from loguru import logger

from mutrade.admin.hub import BotStateHub
```

**추가할 imports:**
```python
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
```

**기존 lifespan 패턴** (lines 35-48) — 변경 없음:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    hub.attach_loop(loop)
    app.state.hub = hub
    logger.info("Admin server started. BotStateHub loop attached.")
    yield
    hub.request_stop()
    scheduler = kwargs.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("Admin server shutting down.")
```

**기존 엔드포인트 패턴** (lines 57-64) — `GET /health` 참조:
```python
@app.get("/health")
async def health() -> dict:
    """서버 생존 확인 및 봇 실행 상태 반환."""
    return {
        "status": "ok",
        "bot_running": hub.is_running(),
        "stop_requested": hub.is_stop_requested(),
    }
```

**추가할 StaticFiles + GET / 패턴:**
```python
STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
```

**추가할 WebSocket 엔드포인트 패턴:**
```python
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    await websocket.send_json(hub.get_snapshot())
    try:
        while True:
            snapshot = await hub.wait_for_change()
            await websocket.send_json(snapshot)
    except WebSocketDisconnect:
        pass  # 정상 종료 — 로깅 불필요
```

**`hub` 접근 패턴:** `app.state.hub`가 아닌 클로저 방식으로 `hub` 직접 캡처 (기존 패턴 유지)

---

### `mutrade/monitor/scheduler.py` (service, event-driven) — 수정 대상

**수정 내용:** `hub.push_snapshot()` 호출 시 `prices` + `executor.pending_codes()` 추가 전달

**현재 파일 위치:** `/Users/sean/Study/MuTrade/MuTrade/mutrade/monitor/scheduler.py`

**수정 대상 코드** (lines 114-117):
```python
# 현재:
if hub is not None:
    hub.push_snapshot(engine.states)
    hub.set_running(True)

# 수정 후:
if hub is not None:
    hub.push_snapshot(
        engine.states,
        prices=prices,
        pending_codes=executor.pending_codes(),
    )
    hub.set_running(True)
```

**기존 imports 패턴** (lines 16-30) — 변경 없음, `executor`는 이미 파라미터로 전달됨:
```python
from mutrade.executor.order_executor import OrderExecutor
```

**`prices` 변수 가용성:** `prices = poll_prices(kis, config)` (line 99) — 루프 내 이미 존재함

---

### `mutrade/executor/order_executor.py` (service, request-response) — 수정 대상

**수정 내용:** `pending_codes() -> frozenset[str]` 공개 메서드 추가

**현재 파일 위치:** `/Users/sean/Study/MuTrade/MuTrade/mutrade/executor/order_executor.py`

**기존 `_pending` 필드** (line 41):
```python
self._pending: set[str] = set()
```

**추가할 메서드 — 삽입 위치:** `execute()` 메서드 앞 또는 클래스 마지막:
```python
def pending_codes(self) -> frozenset[str]:
    """현재 SELL_PENDING 중인 종목 코드 집합을 반환한다.

    scheduler.py가 push_snapshot() 호출 시 pending_codes 인자로 전달한다.
    frozenset 반환으로 불변성 보장 — 호출자가 내부 set을 수정 불가.

    Returns:
        frozenset[str]: 현재 주문 진행 중인 종목 코드 집합
    """
    return frozenset(self._pending)
```

**클래스 내 접근 패턴 참조:** `self._pending.add()` / `self._pending.discard()` (lines 65, 70, 87, 150, 163)

---

### `mutrade/admin/static/index.html` (component, streaming) — 신규 생성

**Analog:** 없음 (신규 파일). RESEARCH.md Pattern 5와 06-UI-SPEC.md를 기반으로 구현.

**파일 구조 (단일 파일, 섹션 순서):**
1. `<!DOCTYPE html>` + `<html lang="ko">`
2. `<head>` — charset, viewport, `<title>`, `<style>` (인라인 CSS 전체)
3. `<body>` — HTML 마크업
4. `<script>` (인라인 JS 전체, body 닫기 전)

**인라인 CSS 필수 패턴 (06-UI-SPEC.md 기준):**
```css
* { font-family: system-ui, -apple-system, 'Segoe UI', sans-serif; }

body {
  background-color: #111827;  /* gray-900 */
  color: #f9fafb;             /* gray-50 */
  margin: 0; padding: 0;
}

.container {
  max-width: 800px;
  margin: 32px auto;
  padding: 0 24px;
}

table {
  width: 100%;
  border-collapse: collapse;
  background-color: #1f2937;  /* gray-800 */
  table-layout: fixed;
}

th, td {
  padding: 8px 12px;
  border-bottom: 1px solid #374151;  /* gray-700 */
  font-size: 14px;
}

th {
  color: #9ca3af;  /* gray-400 */
  font-weight: 600;
  text-align: left;
}

td { color: #f9fafb; }

/* 열 너비 */
th:nth-child(1), td:nth-child(1) { width: 100px; }
th:nth-child(2), td:nth-child(2) { width: 120px; text-align: right; }
th:nth-child(3), td:nth-child(3) { width: 120px; text-align: right; }
th:nth-child(4), td:nth-child(4) { width: 100px; text-align: right; }
th:nth-child(5), td:nth-child(5) { width: 120px; text-align: center; }

/* SELL_PENDING 번짙임 애니메이션 (다크 테마) */
@keyframes blink-sell {
  0%, 100% { background-color: #450a0a; }
  50%       { background-color: #7f1d1d; }
}

tr.sell-pending {
  animation: blink-sell 1s ease-in-out infinite;
}

tr.sell-pending td { color: #fca5a5; }

tr.sell-pending .status-badge {
  color: #ef4444;
  font-weight: 600;
}

tr:hover { background-color: #374151; }  /* gray-700 */

/* 연결 상태 dot */
.dot {
  display: inline-block;
  width: 8px; height: 8px;
  border-radius: 50%;
  margin-right: 6px;
}

.dot.connected   { background-color: #3b82f6; }  /* blue-500 */
.dot.reconnecting { background-color: #f59e0b; } /* amber-500 */
.dot.disconnected { background-color: #6b7280; } /* gray-500 */
```

**JS WebSocket 자동 재연결 패턴 (RESEARCH.md Pattern 5, D-03):**
```javascript
const WS_URL = `ws://${location.host}/ws`;
let ws;

function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    setStatus('connected', '실시간 연결');
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    renderTable(data);
  };

  ws.onclose = () => {
    setStatus('reconnecting', '재연결 중...');
    setTimeout(connect, 3000);  // 3초 후 재연결 시도
  };

  ws.onerror = () => {
    setStatus('disconnected', '연결 끊김');
    ws.close();
  };
}

connect();
```

**테이블 렌더링 패턴:**
```javascript
const STATUS_LABELS = {
  'MONITORING': '모니터링 중',
  'SELL_PENDING': '매도 대기',
  'WARMING_UP': '워밍업',
};

function formatPrice(val) {
  if (!val || val === 0) return '—';
  return Number(val).toLocaleString('ko-KR') + '원';
}

function formatDrop(val, warm) {
  if (!warm) return '—';
  const pct = Number(val);
  let color = '#9ca3af';  // 정상: gray-400
  if (pct <= -9) color = '#ef4444';       // 임계: red-500
  else if (pct <= -5) color = '#f59e0b';  // 경고: amber-500
  return `<span style="color:${color}">${pct.toFixed(2)}%</span>`;
}

function renderTable(data) {
  const tbody = document.getElementById('symbol-table-body');
  const codes = Object.keys(data);

  if (codes.length === 0) {
    tbody.innerHTML = `
      <tr>
        <td colspan="5" style="text-align:center;padding:32px;color:#9ca3af">
          <div style="font-size:16px;font-weight:600">봇 대기 중</div>
          <div style="font-size:12px;margin-top:4px">장 운영 시간(09:00~15:30 KST)에 자동 시작됩니다</div>
        </td>
      </tr>`;
    return;
  }

  tbody.innerHTML = codes.map(code => {
    const s = data[code];
    const isPending = s.sell_pending;
    const statusText = isPending ? '매도 대기' : (!s.warm ? '워밍업' : '모니터링 중');
    return `
      <tr class="${isPending ? 'sell-pending' : ''}">
        <td>${s.code}</td>
        <td style="text-align:right">${formatPrice(s.current_price)}</td>
        <td style="text-align:right">${formatPrice(s.peak_price)}</td>
        <td style="text-align:right">${formatDrop(s.drop_pct, s.warm)}</td>
        <td style="text-align:center"><span class="status-badge">${statusText}</span></td>
      </tr>`;
  }).join('');
}
```

**WebSocket 데이터 계약 (06-UI-SPEC.md 기준):**
```json
{
  "005930": {
    "code": "005930",
    "peak_price": 86200.0,
    "current_price": 84500.0,
    "drop_pct": -1.97,
    "warm": true,
    "sell_pending": false
  }
}
```

---

### `tests/test_hub.py` (test) — 수정 대상

**수정 내용:** `push_snapshot()` 시그니처 변경 반영 + QueueFull 방어 테스트 추가

**현재 파일 위치:** `/Users/sean/Study/MuTrade/MuTrade/tests/test_hub.py`

**기존 테스트 파일 패턴** (lines 1-20):
```python
"""
tests/test_hub.py

BotStateHub 스레드 안전성 TDD 테스트.
"""
import asyncio
import threading
import unittest
from unittest.mock import MagicMock, patch


class TestBotStateHub:
    """BotStateHub 스레드 안전성 테스트."""

    def _make_hub(self):
        from mutrade.admin.hub import BotStateHub
        return BotStateHub()
```

**기존 dataclass-like 객체 테스트 패턴** (lines 131-150) — Phase 6 확장 테스트 참조:
```python
def test_push_snapshot_serializes_dataclass_like_objects(self):
    hub = self._make_hub()

    class FakeSymbolState:
        def __init__(self, code, peak_price, warm):
            self.code = code
            self.peak_price = peak_price
            self.warm = warm

    states = {"005930": FakeSymbolState("005930", 75000.0, True)}
    hub.push_snapshot(states)

    snap = hub.get_snapshot()
    assert "005930" in snap
    assert snap["005930"]["peak_price"] == 75000.0
    assert snap["005930"]["warm"] is True
```

**추가할 테스트 패턴:**
- `test_push_snapshot_with_prices_includes_current_price` — prices 전달 시 스냅샷에 `current_price` 포함 확인
- `test_push_snapshot_with_pending_codes_includes_sell_pending` — pending_codes 전달 시 `sell_pending` 필드 확인
- `test_push_snapshot_drop_pct_calculation` — drop_pct 계산 정확성 (75000 → 70000 = -6.67%)
- `test_put_snapshot_no_queue_full_on_rapid_push` — `asyncio.Queue(maxsize=1)` 빠른 이중 push 시 예외 없음

**asyncio 이벤트 루프 테스트 패턴** (`test_scheduler.py` lines 439-459 참조):
```python
# test_scheduler.py의 hub mock 패턴 — 테스트에서 hub 접근 방식
hub = MagicMock()
hub.is_stop_requested.return_value = False
hub.push_snapshot.assert_called()
```

---

## Shared Patterns

### 1. `threading.RLock` + `asyncio.Queue` 스레드 안전 패턴

**출처:** `mutrade/admin/hub.py` lines 17-30
**적용 대상:** `hub.py` 수정 전반
```python
class BotStateHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: dict = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._change_queue: Optional[asyncio.Queue] = None

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        with self._lock:
            self._loop = loop
            self._change_queue = asyncio.Queue(maxsize=1)
```

### 2. `loguru` 로깅 패턴

**출처:** `mutrade/admin/app.py` lines 18, 41, 48
**적용 대상:** 모든 Python 수정 파일
```python
from loguru import logger
logger.info("Admin server started. BotStateHub loop attached.")
logger.info("Admin server shutting down.")
```

### 3. FastAPI lifespan + `app.state` 의존성 패턴

**출처:** `mutrade/admin/app.py` lines 35-48, 40
**적용 대상:** `app.py` WebSocket 엔드포인트 추가 시
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    hub.attach_loop(loop)
    app.state.hub = hub  # ← hub를 클로저 캡처로 접근 (app.state 대신 클로저 직접 사용)
    yield
    hub.request_stop()
```

### 4. `getattr` 방어적 직렬화 패턴

**출처:** `mutrade/admin/hub.py` lines 40-47
**적용 대상:** `hub.py` `push_snapshot()` 필드 추가 시
```python
for code, s in states.items():
    if hasattr(s, '__dataclass_fields__') or hasattr(s, 'peak_price'):
        serialized[code] = {
            "code": getattr(s, 'code', code),
            "peak_price": getattr(s, 'peak_price', 0.0),
            "warm": getattr(s, 'warm', False),
            # Phase 6에서 추가:
            # "current_price": _prices.get(code, 0.0),
            # "drop_pct": ...,
            # "sell_pending": code in _pending,
        }
    else:
        serialized[code] = s  # 이미 dict인 경우
```

### 5. 테스트 — mock 픽스처 패턴

**출처:** `tests/test_scheduler.py` lines 57-69
**적용 대상:** `tests/test_hub.py` 신규 테스트 케이스
```python
def _make_hub(self):
    from mutrade.admin.hub import BotStateHub
    return BotStateHub()

# mock_loop 패턴 (test_hub.py line 32-34)
mock_loop = MagicMock()
hub.attach_loop(mock_loop)
mock_loop.call_soon_threadsafe.assert_called_once()
```

---

## No Analog Found

| 파일 | Role | Data Flow | 이유 |
|------|------|-----------|------|
| `mutrade/admin/static/index.html` | component | streaming | 기존 코드베이스에 프론트엔드 파일 없음. RESEARCH.md Pattern 5 + 06-UI-SPEC.md를 기반으로 신규 작성. |

---

## Metadata

**Analog 탐색 범위:** `mutrade/admin/`, `mutrade/monitor/`, `mutrade/executor/`, `mutrade/engine/`, `tests/`
**스캔한 파일 수:** 7개 (hub.py, app.py, scheduler.py, order_executor.py, models.py, test_hub.py, test_scheduler.py)
**Pattern extraction date:** 2026-04-15
