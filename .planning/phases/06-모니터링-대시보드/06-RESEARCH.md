# Phase 6: 모니터링 대시보드 - Research

**Researched:** 2026-04-15
**Domain:** FastAPI WebSocket + Vanilla JS 단일 파일 대시보드 + asyncio.Queue 버그 수정
**Confidence:** HIGH

---

## Summary

Phase 6은 두 가지 독립적인 작업으로 구성된다. 첫 번째는 인프라 버그 수정으로, `hub.py`의 `asyncio.QueueFull` 예외와 `push_snapshot()` 시그니처 확장(`current_price`, `drop_pct`, `sell_pending` 필드 추가)이다. 두 번째는 WebSocket 기반 실시간 대시보드 UI로, FastAPI의 `/ws` 엔드포인트 + StaticFiles + 단일 `index.html` 조합으로 구현한다.

기존 코드베이스(Phase 5)는 이미 `BotStateHub.wait_for_change()`, `is_running()`, `app.state.hub` 접근 패턴을 제공하므로 WebSocket 브로드캐스트 루프 구현의 뼈대가 준비되어 있다. `asyncio.Queue(maxsize=1)` + `put_nowait` 조합이 QueueFull 버그의 근원이며, 드롭-앤-리플레이스 패턴으로 해결한다. `SymbolState`에 `current_price` 필드가 없어 `scheduler.py`에서 `prices` dict를 함께 전달하는 방식으로 보완해야 한다.

UI는 npm 빌드 없이 단일 `index.html`에 HTML + 인라인 CSS + 인라인 JS 전부 포함한다. WebSocket 메시지는 JSON 객체(종목코드 → 상태 필드 맵)로 수신하며 JS가 테이블을 동적 갱신한다. 모든 디자인 세부사항은 06-UI-SPEC.md에 확정되어 있다.

**Primary recommendation:** INFRA 수정(Wave 0) → WebSocket 엔드포인트(Wave 1) → 정적 파일 서빙(Wave 1) → index.html 구현(Wave 2) 순서로 진행. 버그 수정이 UI 개발의 전제조건이다.

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Vanilla HTML + JavaScript만 사용한다. npm 빌드 단계 없음. FastAPI `StaticFiles`로 `mutrade/admin/static/index.html` 서빙.
- **D-02:** 단일 `index.html` 파일에 HTML + 인라인 CSS + 인라인 JS 모두 포함. 분리 파일 없음.
- **D-03:** WebSocket 연결이 끊어지면 JS에서 `setTimeout`으로 자동 재연결 시도. 사용자가 페이지를 유지하면 자동 복구됨.
- **D-04:** 테이블 행 레이아웃 — `종목코드 | 현재가 | 고점 | 하락률 | 상태` 열 구성.
- **D-05:** SELL_PENDING 중인 종목은 **번짙이는 빨간 배경 행**으로 강조. CSS `@keyframes` 점멸 애니메이션.
- **D-06:** 봇 비활성(모니터링 세션 없음) 상태 — 빈 테이블 + "봇 대기 중" 메시지 표시. WebSocket은 연결 유지.

### Claude's Discretion
- **QueueFull 버그 수정 방식:** `put_nowait` 호출 전 큐가 가득 찼으면 `get_nowait()`로 기존 항목을 버리고 새 스냅샷 삽입. 항상 최신 상태만 유지하는 패턴. `asyncio.QueueFull` 예외 catch도 병행.
- **SELL_PENDING 노출 방식:** `OrderExecutor`에 `pending_codes() -> frozenset[str]` 공개 메서드 추가. `scheduler.py`의 `push_snapshot()` 호출 시 `executor.pending_codes()`를 함께 전달. `hub.push_snapshot(states, pending_codes)`로 시그니처 확장.
- **WebSocket 엔드포인트:** `/ws` — 연결 시 현재 스냅샷 즉시 전송 후, 변경 발생 때마다 브로드캐스트. `hub.wait_for_change()` await 패턴 활용.
- **`GET /` 라우트:** `index.html` 반환 (StaticFiles mount 또는 FileResponse).

### Deferred Ideas (OUT OF SCOPE)
없음.
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| INFRA-01 | 봇 상태 스냅샷에 현재가·하락률·SELL_PENDING이 포함된다 (`hub.push_snapshot()` + `scheduler.py` 수정) | `hub.py` 시그니처 확장 패턴, `OrderExecutor._pending` set 노출 방법 확인됨 |
| INFRA-02 | 스냅샷 큐 오버플로 버그가 수정된다 (`asyncio.QueueFull` 예외 처리, `hub.py`) | `asyncio.Queue(maxsize=1)` 드롭-앤-리플레이스 패턴 확인됨 |
| DASH-01 | 사용자는 각 종목의 현재가, 고점, 하락률을 웹 페이지에서 확인할 수 있다 | WebSocket JSON 데이터 계약 및 테이블 렌더링 패턴 확인됨 (06-UI-SPEC.md) |
| DASH-02 | 사용자는 SELL_PENDING 중인 종목을 시각적으로 구분할 수 있다 | CSS `@keyframes blink-sell` 패턴 확인됨 (06-UI-SPEC.md) |
| DASH-03 | 대시보드는 WebSocket으로 자동 갱신된다 (페이지 새로고침 불필요) | FastAPI WebSocket + `hub.wait_for_change()` 패턴 확인됨 |
</phase_requirements>

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| QueueFull 버그 수정 | Backend (hub.py) | — | asyncio.Queue는 서버 사이드 브릿지 레이어 |
| SELL_PENDING 노출 | Backend (executor + hub) | — | `OrderExecutor._pending`이 서버 상태 — 클라이언트에 전달만 함 |
| current_price/drop_pct 필드 추가 | Backend (scheduler.py → hub.py) | — | 가격 데이터는 서버의 `prices` dict에 존재 |
| WebSocket 브로드캐스트 | Backend (app.py) | — | FastAPI `@app.websocket()` — 서버가 push |
| 정적 파일 서빙 | Backend (app.py StaticFiles) | — | FastAPI mount, 클라이언트는 수동적 소비자 |
| 테이블 렌더링 / 업데이트 | Frontend (index.html 인라인 JS) | — | WebSocket 메시지 수신 후 DOM 조작 |
| WebSocket 자동 재연결 | Frontend (index.html 인라인 JS) | — | `setTimeout` 재연결 루프 — 브라우저 책임 |
| SELL_PENDING 시각화 | Frontend (index.html 인라인 CSS) | — | CSS animation class 토글 |
| 데이터 포매팅 (천 단위, %) | Frontend (index.html 인라인 JS) | — | 순수 표현 계층 — 서버는 raw 숫자만 전송 |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.3 (설치됨) | WebSocket 엔드포인트, StaticFiles 마운트, FileResponse | 이미 설치됨. `@app.websocket()` + `StaticFiles` 네이티브 지원 |
| uvicorn[standard] | 0.44.0 (설치됨) | ASGI 서버 | Phase 5에서 이미 엔트리포인트로 사용 중 |
| loguru | 0.7.3 (설치됨) | 서버 이벤트 로깅 | 프로젝트 표준 |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| asyncio.Queue (stdlib) | Python 3.11 stdlib | 스레드↔asyncio 브릿지 큐 | hub.py 내 이미 사용 중 |
| fastapi.staticfiles.StaticFiles | FastAPI 내장 | 정적 디렉터리 서빙 | `mutrade/admin/static/` 마운트 시 |
| fastapi.responses.FileResponse | FastAPI 내장 | `GET /` → index.html 반환 | StaticFiles에 `html=True` 옵션 대신 명시적 라우트 사용 시 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Vanilla JS | React/Vue | 결정됨(D-01) — 빌드 없음 원칙 |
| StaticFiles | FileResponse 직접 반환 | StaticFiles mount가 더 간결. `html=True` 옵션 사용 시 GET / 자동 처리됨 |
| asyncio.Queue maxsize=1 | asyncio.Queue maxsize=0 (무한) | maxsize=1이 최신 상태만 유지하는 의도에 맞음 |

**Installation:**
```bash
# 추가 설치 불필요 — 모든 의존성이 이미 pyproject.toml에 포함됨
```

**Version verification:** [VERIFIED: pyproject.toml + pip show]
- `fastapi==0.135.3` — 설치됨
- `uvicorn[standard]==0.44.0` — 설치됨

---

## Architecture Patterns

### System Architecture Diagram

```
[APScheduler Thread]          [asyncio Event Loop (uvicorn)]
      |                                    |
      |  poll_prices()                     |
      |  engine.tick()                     |
      |  executor.pending_codes()          |
      v                                    |
hub.push_snapshot(               hub.wait_for_change()
  states,                              |
  prices,               ←─────── [asyncio.Queue(maxsize=1)]
  pending_codes         call_soon_threadsafe
)                                        |
                               hub._snapshot (RLock 보호)
                                         |
                              [WebSocket /ws 브로드캐스트 태스크]
                              websocket.send_json(snapshot)
                                         |
                              [Browser WebSocket Client]
                              onmessage → renderTable(data)
                                         |
                              [index.html DOM — <tbody>]
```

### Recommended Project Structure
```
mutrade/
├── admin/
│   ├── hub.py          # push_snapshot() 시그니처 확장 + QueueFull 수정
│   ├── app.py          # /ws 엔드포인트 + StaticFiles + GET / 추가
│   └── static/
│       └── index.html  # 단일 파일 대시보드 (HTML + 인라인 CSS + 인라인 JS)
├── executor/
│   └── order_executor.py   # pending_codes() 공개 메서드 추가
└── monitor/
    └── scheduler.py    # push_snapshot() 호출 시 prices + pending_codes 전달
tests/
└── test_hub.py         # push_snapshot 시그니처 변경 반영 + QueueFull 테스트 추가
```

### Pattern 1: asyncio.Queue 드롭-앤-리플레이스 (QueueFull 버그 수정)

**What:** `maxsize=1` 큐에 push 시, 가득 찼으면 기존 항목을 버리고 새 항목 삽입
**When to use:** "최신 상태만 의미있고, 이전 상태는 버려도 된다"는 경우 (대시보드 스냅샷)
**Example:**
```python
# Source: CONTEXT.md + asyncio 공식 docs 패턴
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
        pass  # 극히 드문 경합 — 무시 (다음 tick에서 재시도됨)
```

### Pattern 2: push_snapshot() 시그니처 확장 (INFRA-01)

**What:** `states` dict + `prices` dict + `pending_codes` frozenset을 받아 병합 직렬화
**When to use:** 스케줄러가 현재가 + SELL_PENDING 정보를 동시에 전달해야 할 때
**Example:**
```python
# Source: CONTEXT.md + 기존 hub.py 코드 분석
def push_snapshot(
    self,
    states: dict,
    prices: dict[str, float] | None = None,
    pending_codes: frozenset[str] | None = None,
) -> None:
    _prices = prices or {}
    _pending = pending_codes or frozenset()
    serialized: dict = {}
    for code, s in states.items():
        peak = getattr(s, 'peak_price', 0.0)
        current = _prices.get(code, 0.0)
        drop = ((current - peak) / peak) if peak > 0 and current > 0 else 0.0
        serialized[code] = {
            "code": getattr(s, 'code', code),
            "peak_price": peak,
            "current_price": current,
            "drop_pct": round(drop * 100, 2),  # % 단위, 소수점 2자리
            "warm": getattr(s, 'warm', False),
            "sell_pending": code in _pending,
        }
    # ... 이후 기존 _snapshot 저장 + 큐 push
```

### Pattern 3: FastAPI WebSocket 브로드캐스트 (DASH-03)

**What:** 연결 즉시 현재 스냅샷 전송 → `wait_for_change()` loop로 변경 시마다 브로드캐스트
**When to use:** 서버 push 방식 실시간 갱신
**Example:**
```python
# Source: Context7 /fastapi/fastapi + CONTEXT.md
from fastapi import WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # 연결 즉시 현재 스냅샷 전송
    await websocket.send_json(hub.get_snapshot())
    try:
        while True:
            snapshot = await hub.wait_for_change()
            await websocket.send_json(snapshot)
    except WebSocketDisconnect:
        pass  # 정상 종료 — 로깅 불필요
```

### Pattern 4: StaticFiles + GET / 라우트 (DASH-01)

**What:** `mutrade/admin/static/` 디렉터리를 `/static` 경로에 마운트, GET /는 index.html 반환
**When to use:** 단일 HTML 파일 서빙
**Example:**
```python
# Source: Context7 /fastapi/fastapi
from pathlib import Path
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).parent / "static"

app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

@app.get("/")
async def index():
    return FileResponse(str(STATIC_DIR / "index.html"))
```

### Pattern 5: JS WebSocket 자동 재연결 (D-03)

**What:** `onclose`/`onerror` 핸들러에서 `setTimeout`으로 재연결
**Example:**
```javascript
// Source: CONTEXT.md D-03 + 표준 WebSocket 패턴 [ASSUMED]
let ws;
function connect() {
    ws = new WebSocket(`ws://${location.host}/ws`);
    ws.onopen = () => setStatus('connected');
    ws.onmessage = (e) => renderTable(JSON.parse(e.data));
    ws.onclose = () => {
        setStatus('reconnecting');
        setTimeout(connect, 3000);
    };
    ws.onerror = () => ws.close();
}
connect();
```

### Pattern 6: pending_codes() 공개 메서드 (CONTEXT.md Claude's Discretion)

**What:** `OrderExecutor._pending` set의 불변 복사본 반환
**Example:**
```python
def pending_codes(self) -> frozenset[str]:
    """현재 SELL_PENDING 중인 종목 코드 집합. 스레드 안전 복사본."""
    return frozenset(self._pending)
```

### Anti-Patterns to Avoid

- **`asyncio.Queue(maxsize=0)` (무한 큐) 사용:** 대시보드 스냅샷은 최신 1개만 의미 있다. 무한 큐는 메모리 누수 위험.
- **`put_nowait` 예외 미처리:** 기존 코드의 버그 원인. `full()` 확인 → `get_nowait()` → `put_nowait()` 순서 필수.
- **`hub.wait_for_change()` 밖에서 `asyncio.Queue.get()` 직접 호출:** 캡슐화 위반 + 다중 consumer 경합 위험.
- **WebSocket 핸들러에서 블로킹 작업:** `hub.wait_for_change()`는 coroutine — `await` 없이 호출 금지.
- **JS에서 외부 CDN 로드:** 06-UI-SPEC.md Registry Safety — 외부 의존성 없음. 단일 파일 자급자족 원칙.
- **`SymbolState`에 `current_price` 필드 직접 추가:** `SymbolState`는 엔진 내부 상태 모델. `scheduler.py`의 `prices` dict에서 가져와 직렬화 시 병합하는 것이 올바른 패턴.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| WebSocket 서버 | raw asyncio WebSocket | FastAPI `@app.websocket()` | 연결 수명주기, 예외 처리 내장 |
| 정적 파일 서빙 | 직접 파일 읽기 라우트 | `StaticFiles` mount | ETag, Last-Modified, 304 처리 자동 |
| JS 숫자 포매팅 | 커스텀 파서 | `Intl.NumberFormat` / `toLocaleString()` | 브라우저 내장 API로 충분 |
| 스레드↔asyncio 브릿지 | 직접 queue 공유 | `loop.call_soon_threadsafe()` | asyncio 스레드 안전성 보장 |

---

## Common Pitfalls

### Pitfall 1: asyncio.QueueFull (기존 버그)
**What goes wrong:** `asyncio.Queue(maxsize=1)` + `call_soon_threadsafe(put_nowait, data)` 조합에서 WebSocket 브로드캐스트가 큐를 비우기 전에 두 번째 push가 도착하면 `asyncio.QueueFull` 예외 발생. ERROR 로그로 노출됨.
**Why it happens:** `put_nowait`은 큐가 가득 찼을 때 예외를 던지지만, `call_soon_threadsafe`는 이미 스케줄된 콜백이라 재시도나 드롭 로직이 없음.
**How to avoid:** `_put_snapshot` 내부 메서드로 분리. `full()` → `get_nowait()` → `put_nowait()` 패턴.
**Warning signs:** `asyncio` 로그에 `QueueFull` 에러, 또는 `exception in callback` 로그.

### Pitfall 2: WebSocket 핸들러에서 `wait_for_change()` 취소 처리 누락
**What goes wrong:** 클라이언트가 갑자기 연결을 끊으면 `websocket.send_json()`에서 `WebSocketDisconnect`가 아닌 다른 예외 발생 가능. `wait_for_change()` await 중에 취소되면 `asyncio.CancelledError` 전파됨.
**How to avoid:** `WebSocketDisconnect`와 `Exception` 모두 처리. `CancelledError`는 re-raise.

### Pitfall 3: 복수 WebSocket 연결 시 `wait_for_change()` 경합
**What goes wrong:** 두 개의 브라우저 탭이 동시에 `/ws`에 연결되면 `asyncio.Queue.get()`이 단 하나의 consumer만 메시지를 받음 — 나머지 연결은 갱신 안 됨.
**Why it happens:** `asyncio.Queue`는 단일 consumer 패턴. 두 번째 `get()` 호출자는 다음 메시지를 기다림.
**How to avoid:** Phase 6 범위에서는 단일 브라우저 탭 사용 가정으로 무시 가능. Phase 7 이후 복수 연결 필요 시 fan-out 패턴(asyncio.Event + 스냅샷 공유) 고려.
**Warning signs:** 두 탭 중 하나가 갱신되지 않음.

### Pitfall 4: `drop_pct` 계산 시 0 나누기
**What goes wrong:** `peak_price=0` 또는 `current_price=0`일 때 나누기 오류.
**How to avoid:** `if peak > 0 and current > 0` 조건 방어. 초기 워밍업(`warm=False`) 종목은 `drop_pct=0` 처리.
**Warning signs:** ZeroDivisionError 또는 `inf`/`nan` 값이 JSON에 포함됨 (JSON 직렬화 실패).

### Pitfall 5: `mutrade/admin/static/` 디렉터리 미생성
**What goes wrong:** `StaticFiles(directory=...)` 마운트 시 디렉터리가 없으면 앱 시작 시 예외 발생.
**How to avoid:** Wave 0 태스크로 `mutrade/admin/static/` 디렉터리 생성 + `.gitkeep` 또는 `index.html` 배치 후 StaticFiles 마운트.

### Pitfall 6: `pending_codes()` 스레드 안전성
**What goes wrong:** `OrderExecutor._pending` set을 직접 반환하면 APScheduler 스레드와 FastAPI 스레드 간 경합 조건 발생.
**How to avoid:** `frozenset(self._pending)` — 불변 복사본 반환. `_pending` 자체 접근에 lock 불필요 (GIL 보호 + frozenset은 읽기 전용).

---

## Code Examples

### QueueFull 수정 전/후 비교
```python
# BEFORE (버그 있음) — hub.py:54
self._loop.call_soon_threadsafe(
    self._change_queue.put_nowait, dict(serialized)
)

# AFTER (수정) — _put_snapshot() 별도 메서드
def _put_snapshot(self, data: dict) -> None:
    """asyncio 이벤트 루프 스레드 전용. call_soon_threadsafe로만 호출."""
    if self._change_queue is None:
        return
    if self._change_queue.full():
        try:
            self._change_queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    try:
        self._change_queue.put_nowait(data)
    except asyncio.QueueFull:
        pass

# push_snapshot() 내부에서:
self._loop.call_soon_threadsafe(self._put_snapshot, dict(serialized))
```

### WebSocket 데이터 계약 (hub.py → JS)
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
빈 객체 `{}` → JS에서 "봇 대기 중" 빈 상태 메시지 렌더링.

### scheduler.py 수정 포인트
```python
# 기존
hub.push_snapshot(engine.states)

# 수정 후
hub.push_snapshot(
    engine.states,
    prices=prices,
    pending_codes=executor.pending_codes(),
)
```

### JS 테이블 렌더링 핵심 패턴
```javascript
// Source: 06-UI-SPEC.md 데이터 계약 기준
function renderTable(data) {
    const tbody = document.getElementById('symbol-table-body');
    const entries = Object.values(data);

    if (entries.length === 0) {
        // 빈 상태: "봇 대기 중" 메시지
        tbody.innerHTML = `<tr><td colspan="5" class="empty-msg">봇 대기 중</td></tr>`;
        return;
    }

    tbody.innerHTML = entries.map(s => {
        const isPending = s.sell_pending;
        const rowClass = isPending ? 'sell-pending' : '';
        const dropColor = s.drop_pct <= -9 ? '#ef4444'
            : s.drop_pct <= -5 ? '#f59e0b'
            : '#9ca3af';
        const currentStr = s.current_price > 0
            ? s.current_price.toLocaleString('ko-KR') + '원'
            : '—';
        const dropStr = s.warm && s.current_price > 0
            ? `${s.drop_pct.toFixed(2)}%`
            : '—';
        const statusText = {
            'MONITORING': '모니터링 중',
            'SELL_PENDING': '매도 대기',
            'WARMING_UP': '워밍업',
        }[isPending ? 'SELL_PENDING' : (s.warm ? 'MONITORING' : 'WARMING_UP')] || '—';

        return `<tr class="${rowClass}">
            <td>${s.code}</td>
            <td class="num">${currentStr}</td>
            <td class="num">${s.peak_price > 0 ? s.peak_price.toLocaleString('ko-KR') + '원' : '—'}</td>
            <td class="num" style="color:${dropColor}">${dropStr}</td>
            <td class="center"><span class="status-badge">${statusText}</span></td>
        </tr>`;
    }).join('');
}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `put_nowait` 직접 호출 | `_put_snapshot()` 메서드 분리 + 드롭-앤-리플레이스 | Phase 6 | QueueFull 버그 해소 |
| `push_snapshot(states)` | `push_snapshot(states, prices, pending_codes)` | Phase 6 | INFRA-01 충족 |
| `/health` 엔드포인트만 존재 | `/ws`, `/`, `/health` 3개 엔드포인트 | Phase 6 | 대시보드 접근 가능 |

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | JS `WebSocket` 재연결에 `setTimeout(connect, 3000)` 3초 간격이 적절함 | Pattern 5 | 너무 빠르면 서버 부하, 너무 느리면 UX 저하 — 낮음 |
| A2 | `frozenset(self._pending)` 반환이 GIL 하에서 충분히 스레드 안전함 | Pitfall 6 | CPython에서는 안전. PyPy에서는 검토 필요 — 현재 CPython 사용 중이므로 낮음 |
| A3 | 단일 브라우저 탭만 지원 (복수 탭 경합 미처리) | Pitfall 3 | Phase 6 범위 내에서는 허용됨. Phase 7 이전에 재검토 필요 |

---

## Open Questions

1. **`mutrade/admin/static/` 경로 기준 (절대 경로 vs 상대 경로)**
   - What we know: `StaticFiles(directory=...)` 는 문자열 경로를 받음. 상대 경로는 실행 디렉터리에 의존.
   - What's unclear: `uvicorn`을 어느 디렉터리에서 실행하는지에 따라 다름.
   - Recommendation: `Path(__file__).parent / "static"` 절대 경로 사용 — `app.py`의 `__file__` 기준으로 계산.

2. **`test_hub.py` 기존 테스트 호환성**
   - What we know: 기존 10개 테스트 모두 PASS 중. `push_snapshot()` 시그니처 변경 시 일부 테스트 수정 필요.
   - Recommendation: `prices=None`, `pending_codes=None` 기본값으로 하위호환성 유지. 기존 테스트 수정 최소화.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | tomllib stdlib, `X \| Y` 타입 힌트 | ✓ | 3.11.x (/opt/homebrew/bin/python3.11) | — |
| FastAPI | WebSocket, StaticFiles | ✓ | 0.135.3 | — |
| uvicorn[standard] | ASGI 서버 | ✓ | 0.44.0 | — |
| pytest | 테스트 실행 | ✓ | 설치됨 | — |

**Missing dependencies with no fallback:** 없음.

**주의:** 시스템 기본 `python3`은 3.9 (macOS 동봉). 테스트 실행 시 반드시 `python3.11 -m pytest` 사용.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (설치됨) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python3.11 -m pytest tests/test_hub.py -x -q` |
| Full suite command | `python3.11 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-02 | QueueFull 예외 발생하지 않음 | unit | `python3.11 -m pytest tests/test_hub.py::TestBotStateHub::test_queue_full_no_error -x` | ❌ Wave 0 |
| INFRA-01 | push_snapshot() 응답에 current_price, drop_pct, sell_pending 필드 포함 | unit | `python3.11 -m pytest tests/test_hub.py::TestBotStateHub::test_push_snapshot_includes_new_fields -x` | ❌ Wave 0 |
| INFRA-01 | scheduler.py가 prices와 pending_codes를 hub에 전달함 | unit | `python3.11 -m pytest tests/test_scheduler.py -x -q` (기존 테스트 + 수정) | ✅ (수정 필요) |
| DASH-01 | GET / 가 index.html 반환 | smoke | `python3.11 -m pytest tests/test_app.py::test_get_root_returns_html -x` | ❌ Wave 0 |
| DASH-03 | WebSocket /ws 연결 후 JSON 스냅샷 수신 | integration | `python3.11 -m pytest tests/test_app.py::test_websocket_sends_snapshot -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `python3.11 -m pytest tests/test_hub.py tests/test_scheduler.py -x -q`
- **Per wave merge:** `python3.11 -m pytest tests/ -q`
- **Phase gate:** 전체 스위트 그린 + 브라우저 수동 확인(WebSocket 갱신)

### Wave 0 Gaps
- [ ] `tests/test_hub.py` — `test_queue_full_no_error`, `test_push_snapshot_includes_new_fields` 테스트 케이스 추가
- [ ] `tests/test_app.py` — `test_get_root_returns_html`, `test_websocket_sends_snapshot` 신규 파일 생성
- [ ] `mutrade/admin/static/` 디렉터리 생성 (StaticFiles 마운트 전제조건)

---

## Security Domain

> 개인용 로컬/서버 환경. `CLAUDE.md` — 다중 사용자 인증 불필요(Out of Scope).

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 개인용 봇 — 인증 범위 외 |
| V3 Session Management | no | 세션 없음 |
| V4 Access Control | no | 단일 사용자 로컬 환경 |
| V5 Input Validation | 부분 | WebSocket은 서버→클라이언트 push만. 클라이언트→서버 입력 없음 (Phase 6) |
| V6 Cryptography | no | HTTPS 없음 (로컬 환경) |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| JSON 직렬화 시 `inf`/`nan` | Tampering | `drop_pct` 계산 시 0 나누기 방어, 숫자 범위 검증 |
| WebSocket 연결 폭주 | DoS | Phase 6 범위 외 (단일 사용자 가정) |

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: 기존 코드 직접 분석] `mutrade/admin/hub.py` — 버그 위치 라인 54 확인
- [VERIFIED: 기존 코드 직접 분석] `mutrade/executor/order_executor.py` — `_pending: set[str]` 필드 확인
- [VERIFIED: 기존 코드 직접 분석] `mutrade/engine/models.py` — `SymbolState` 필드 목록 확인 (current_price 없음)
- [VERIFIED: 기존 코드 직접 분석] `mutrade/monitor/scheduler.py` — `push_snapshot(engine.states)` 호출 위치 확인
- [VERIFIED: pyproject.toml] FastAPI 0.135.3, uvicorn[standard] 0.44.0 설치 확인
- [VERIFIED: python3.11 -m pytest] 기존 98개 테스트 중 97개 PASS (test_client.py 1개 환경 의존 실패)
- [CITED: Context7 /fastapi/fastapi] WebSocket 엔드포인트, StaticFiles, FileResponse 패턴
- [CITED: .planning/phases/06-모니터링-대시보드/06-UI-SPEC.md] 디자인 계약 (컬러, 타이포, CSS 애니메이션)
- [CITED: .planning/phases/06-모니터링-대시보드/06-CONTEXT.md] 구현 결정 D-01~D-06

### Secondary (MEDIUM confidence)
- [VERIFIED: 코드 분석] `asyncio.Queue(maxsize=1)` + `put_nowait` 패턴의 QueueFull 발생 조건

### Tertiary (LOW confidence)
- [ASSUMED] JS `setTimeout(connect, 3000)` 재연결 간격 (A1)

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — 모두 기존 설치된 라이브러리, 코드베이스에서 직접 확인
- Architecture: HIGH — 기존 코드 패턴 직접 분석 + Context7 FastAPI 문서 확인
- Pitfalls: HIGH — 버그 위치 코드에서 직접 확인 (hub.py:54)

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (안정적 스택 — 30일)
