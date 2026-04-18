# Phase 7: 봇 제어 - Research

**Researched:** 2026-04-18
**Domain:** FastAPI REST 엔드포인트 + APScheduler 즉시 발화 + 스레드 안전 상태 수정 + Vanilla HTML/JS 제어 UI
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**봇 시작 트리거**
- D-01: 시작 버튼은 시장 시간(09:00~15:20 KST)에만 동작한다. 시장 시간 외 → "시장 시간이 아닙니다 (09:00~15:20 KST)" 메시지 표시, 실행하지 않음.
- D-02: 시작 메커니즘 — APScheduler 3.x `scheduler.modify_job("market_poll", next_run_time=datetime.now(tz))` 사용. (CONTEXT.md에는 `trigger_job()`으로 기술되어 있으나 APScheduler 3.11.2에 해당 메서드가 없음 — 아래 Critical Finding 참고)
- D-03: `POST /api/start` — 시장 시간 체크 → `modify_job()` 호출. `hub.is_running()` True이면 409 응답.

**봇 중지**
- D-04: `POST /api/stop` — `hub.request_stop()` 호출. 기존 `stop_event` 플래그 활용.
- D-05: SELL_PENDING 종목 있을 때 중지 요청 시 프론트엔드에서 `window.confirm()` 확인 다이얼로그.
- D-06: SELL_PENDING 여부는 `hub.get_snapshot()` 스냅샷의 `sell_pending` 필드로 판단.

**드라이런 토글**
- D-07: `POST /api/toggle-dry-run` — `engine._dry_run`과 `executor._dry_run` 런타임 직접 수정. `.env` 파일 변경 없음 → 재시작 시 원래 값으로 초기화.
- D-08: 현재 드라이런 모드는 WebSocket 스냅샷에 `dry_run: bool` 필드로 포함, 헤더 배지로 표시.
- D-09 (Claude 재량): 토글 API 응답에 "재시작 시 .env 설정으로 초기화됩니다" 안내 포함.

**수동 매도**
- D-10: 종목 테이블 각 행에 "즉시 매도" 버튼. 클릭 시 `window.confirm()` 확인 후 실행.
- D-11: `POST /api/sell/{code}` — `executor.execute()` 직접 호출 (SellSignal 생성 후 전달). 드라이런 모드 무관 항상 실거래.
- D-12 (Claude 재량): SELL_PENDING 중인 행의 "즉시 매도" 버튼 비활성화.
- D-13: 수동 매도 결과는 페이지 상단 배너로 표시. 4초 후 자동 숨김.

### Claude's Discretion

- API 라우트 설계: `POST /api/start`, `POST /api/stop`, `POST /api/toggle-dry-run`, `POST /api/sell/{code}` — 모두 JSON 응답 (`{"ok": true, "message": "..."}`)
- UI 레이아웃: 기존 `index.html` 헤더 영역에 시작/중지 버튼, 드라이런 배지 추가. 수동 매도 버튼은 각 종목 행 마지막 열.
- 드라이런 토글: `engine._dry_run` + `executor._dry_run` 런타임 직접 수정. `hub._lock` 내에서 수정하거나 setter 추가.
- `hub.get_snapshot()` 확장: `dry_run` 필드 포함.

### Deferred Ideas (OUT OF SCOPE)

- 드라이런 모드 `.env` 영속화 (Phase 9)
- 봇 자동 시작 스케줄 변경 (Phase 9)
- SELL_PENDING 완료 알림 (현재는 다음 폴링 주기 스냅샷으로 반영)
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CTRL-01 | 사용자는 UI에서 모니터링 세션을 시작할 수 있다 | `POST /api/start` → `scheduler.modify_job(next_run_time=now)` 즉시 발화. D-01/D-02/D-03 구현 경로 확인됨. |
| CTRL-02 | 사용자는 UI에서 모니터링 세션을 중지할 수 있다 | `POST /api/stop` → `hub.request_stop()`. 기존 `stop_event` 플래그 완전 구현됨 확인. |
| CTRL-03 | 사용자는 UI에서 드라이런 ↔ 실매도 모드를 전환할 수 있다 | `POST /api/toggle-dry-run` → `engine._dry_run` / `executor._dry_run` 직접 수정. 스레드 안전 setter 패턴 필요. |
| CTRL-04 | 사용자는 UI에서 특정 종목을 즉시 시장가 매도할 수 있다 | `POST /api/sell/{code}` → `SellSignal` 생성 후 `executor.execute()`. dry_run 무관 실거래 강제 경로 확인됨. |
</phase_requirements>

---

## Summary

Phase 7은 기존 FastAPI 앱(`create_app()`)에 4개의 POST 엔드포인트를 추가하고, `index.html`에 시작/중지 버튼·드라이런 배지·즉시 매도 버튼을 추가하는 작업이다. 백엔드와 프론트엔드 작업이 균형 있게 나뉘며, 외부 라이브러리 추가 없이 기존 코드를 최대한 재활용할 수 있다.

**핵심 발견 — CONTEXT.md D-02 수정 필요:** CONTEXT.md에는 `scheduler.trigger_job()`을 사용하라고 명시되어 있으나, **APScheduler 3.11.2(설치된 버전)에는 `trigger_job()` 메서드가 존재하지 않는다.** [VERIFIED: python3.11 실행 결과] 올바른 즉시 발화 방법은 `scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))`이며, 실제 동작을 확인했다.

드라이런 토글의 스레드 안전성이 핵심 구현 과제다. `engine._dry_run`과 `executor._dry_run`은 APScheduler BackgroundScheduler 스레드에서 읽히므로, `hub._lock`(이미 존재하는 `threading.RLock`)을 활용하거나 각 클래스에 `dry_run` setter를 추가하는 방식으로 보호해야 한다. WebSocket 스냅샷에 `dry_run` 필드를 추가하려면 `hub.push_snapshot()` 또는 `hub.get_snapshot()`이 `engine._dry_run`을 읽어야 하므로, hub에 `engine` 참조를 주입하거나 `dry_run` 인자를 `push_snapshot()`에 추가하는 두 가지 접근이 가능하다.

**Primary recommendation:** `scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))`으로 즉시 발화. dry_run 토글은 `hub._lock` 내에서 `engine._dry_run`과 `executor._dry_run`을 동시 수정. `hub.push_snapshot()` 시그니처에 `dry_run: bool` 인자 추가.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| 시작/중지 명령 수신 | API / Backend (FastAPI) | — | 상태 변경은 서버 측 hub/scheduler가 소유 |
| APScheduler 즉시 발화 | API / Backend | — | BackgroundScheduler는 서버 프로세스에서만 접근 가능 |
| 드라이런 플래그 수정 | API / Backend | — | 엔진/실행기는 서버 스레드에서 실행 — 클라이언트 직접 접근 불가 |
| 수동 매도 주문 제출 | API / Backend | — | KIS API 호출은 서버 측 executor만 가능 |
| 시장 시간 유효성 검사 | API / Backend | Browser (보조 UX) | 서버가 권위적 판단, UI는 사용자 피드백용 |
| UI 상태 표시 (시작/중지 버튼 활성화) | Browser / Client | — | `is_running` 필드를 WebSocket 스냅샷에서 읽어 토글 |
| 드라이런 배지 표시 | Browser / Client | — | WebSocket 스냅샷 `dry_run` 필드 기반 실시간 갱신 |
| SELL_PENDING 확인 다이얼로그 | Browser / Client | — | 프론트엔드가 스냅샷 데이터로 판단 (D-06) |
| 수동 매도 확인 다이얼로그 | Browser / Client | — | `window.confirm()` 브라우저 네이티브 |
| 배너 표시 / 자동 숨김 | Browser / Client | — | setTimeout 4000ms JS 패턴 (D-13) |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.3 | REST 엔드포인트 추가 | 이미 설치됨 (`pyproject.toml`). `create_app()`에 라우트 추가만 필요. |
| APScheduler | 3.11.2 | 스케줄러 즉시 발화 | 이미 설치됨. `modify_job(next_run_time=...)` 패턴으로 즉시 발화. |
| threading (stdlib) | — | 스레드 안전 dry_run 수정 | `hub._lock` (RLock) 재사용. 추가 의존성 없음. |
| zoneinfo (stdlib 3.9+) | — | KST 시장 시간 체크 | 이미 scheduler.py에서 사용 중. |

[VERIFIED: pyproject.toml 확인, python3.11 실행 검증]

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| loguru | 0.7.3 | API 엔드포인트 로그 | 기존 패턴 그대로 적용 |
| python-multipart | 0.0.26 | (선택) Form 데이터 | 이번 Phase는 JSON Body 사용 — 불필요하나 이미 설치됨 |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `modify_job(next_run_time)` | 새 BackgroundTask 직접 실행 | 기존 job ID와 스냅샷 `is_running` 플래그 연동이 깨질 수 있음. modify_job이 더 안전. |
| `hub._lock` 내 dry_run 수정 | `threading.Lock` 별도 추가 | hub에 이미 `_lock: RLock` 존재 — 재사용이 더 단순 |
| `window.confirm()` | 커스텀 모달 다이얼로그 | CONTEXT.md에 `window.confirm()` 명시 (D-05, D-10). 바닐라 HTML 프로젝트. |

**Installation:** 추가 패키지 설치 불필요. 기존 의존성만으로 구현 가능.

---

## Architecture Patterns

### System Architecture Diagram

```
Browser (index.html)
       │
       │  Click: 시작/중지/드라이런 배지/즉시 매도
       ▼
  POST /api/start        → Hub.is_running() 확인 → modify_job(next_run_time=now)
  POST /api/stop         → Hub.request_stop()
  POST /api/toggle-dry-run → Hub._lock 내 engine._dry_run / executor._dry_run 수정
  POST /api/sell/{code}  → SellSignal 생성 → executor.execute(sig)
       │
       │  JSON {"ok": true, "message": "..."}
       ▼
  showBanner(msg, type)  → setTimeout(hideBanner, 4000)
       │
       │  WebSocket /ws  (기존 경로 유지)
       ▼
  Hub.push_snapshot(states, prices, pending, dry_run)
       │
       │  JSON {is_running, dry_run, symbols: {code: {sell_pending, ...}}}
       ▼
  renderTable(data)  →  버튼 disabled 상태 갱신 / 배지 색상 갱신
```

### Recommended Project Structure

```
mutrade/
├── admin/
│   ├── app.py           # 기존 파일 — 4개 라우트 추가
│   ├── hub.py           # 기존 파일 — push_snapshot(dry_run 인자) 수정
│   └── static/
│       └── index.html   # 기존 파일 — 헤더 제어 UI + 배너 + 테이블 6열
mutrade/
├── engine/
│   └── trailing_stop.py # 기존 파일 — dry_run setter 추가 (선택)
└── executor/
    └── order_executor.py# 기존 파일 — dry_run setter 추가 (선택)
tests/
└── test_app_routes.py   # 기존 파일 — Phase 7 라우트 테스트 추가
```

### Pattern 1: FastAPI 엔드포인트에서 app.state 접근

**What:** `request.app.state.hub` / `.scheduler` / `.engine`으로 의존성 접근
**When to use:** POST 엔드포인트 내부에서 hub, scheduler, engine 호출 시

```python
# Source: [VERIFIED: python3.11 FastAPI testclient 실행 확인]
# app.py lifespan startup에서:
app.state.hub = hub
app.state.scheduler = kwargs.get("scheduler")
app.state.engine = kwargs.get("engine")
app.state.executor = kwargs.get("executor")

# 엔드포인트에서:
@app.post("/api/start")
async def start(request: Request):
    hub: BotStateHub = request.app.state.hub
    scheduler = request.app.state.scheduler
    ...
```

### Pattern 2: APScheduler 즉시 발화 (CRITICAL — CONTEXT.md D-02 수정)

**What:** `modify_job(next_run_time=datetime.now(timezone.utc))`으로 즉시 발화
**When to use:** `POST /api/start` 처리 시

```python
# Source: [VERIFIED: python3.11 APScheduler 3.11.2 실행 확인]
# trigger_job()은 APScheduler 3.x에 존재하지 않음!
# 올바른 패턴:
from datetime import datetime, timezone
scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))
```

### Pattern 3: POST /api/start 전체 흐름

```python
# Source: [VERIFIED: CONTEXT.md D-01/D-03, 코드베이스 확인]
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException

KST = ZoneInfo("Asia/Seoul")

@app.post("/api/start")
async def api_start(request: Request):
    hub: BotStateHub = request.app.state.hub
    scheduler = request.app.state.scheduler

    if hub.is_running():
        raise HTTPException(status_code=409, detail="이미 실행 중입니다")

    now_kst = datetime.now(KST)
    current_min = now_kst.hour * 60 + now_kst.minute
    market_open = 9 * 60   # 09:00
    market_close = 15 * 60 + 20  # 15:20
    if not (market_open <= current_min < market_close):
        raise HTTPException(status_code=400, detail="시장 시간이 아닙니다 (09:00~15:20 KST)")

    hub.clear_stop()  # 이전 중지 플래그 초기화
    scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))
    return {"ok": True, "message": "모니터링 세션 시작됨"}
```

### Pattern 4: 드라이런 토글 — 스레드 안전 수정

**What:** `hub._lock` 내에서 engine과 executor의 `_dry_run` 동시 수정
**When to use:** `POST /api/toggle-dry-run` 처리 시

```python
# Source: [VERIFIED: hub.py _lock RLock 확인, trailing_stop.py executor.py _dry_run 확인]
@app.post("/api/toggle-dry-run")
async def api_toggle_dry_run(request: Request):
    hub: BotStateHub = request.app.state.hub
    engine = request.app.state.engine
    executor = request.app.state.executor

    with hub._lock:
        new_val = not engine._dry_run
        engine._dry_run = new_val
        executor._dry_run = new_val

    direction = "드라이런" if new_val else "실매도"
    return {
        "ok": True,
        "dry_run": new_val,
        "message": f"{direction} 모드로 전환됨. 재시작 시 .env 설정으로 초기화됩니다",
    }
```

### Pattern 5: 수동 매도 — dry_run 우회 실거래

**What:** SellSignal의 `dry_run=False`를 명시적으로 지정하여 executor.execute() 직접 호출
**When to use:** `POST /api/sell/{code}` 처리 시

```python
# Source: [VERIFIED: order_executor.py execute() 로직, engine/models.py SellSignal 확인]
from mutrade.engine.models import SellSignal

@app.post("/api/sell/{code}")
async def api_sell(code: str, request: Request):
    executor = request.app.state.executor
    hub: BotStateHub = request.app.state.hub

    snapshot = hub.get_snapshot()
    sym = snapshot.get(code)
    if sym is None:
        raise HTTPException(status_code=404, detail=f"종목 {code}를 찾을 수 없습니다")

    # dry_run=False 명시 — D-11: 수동 매도는 항상 실거래
    sig = SellSignal(
        code=code,
        name=sym.get("code", code),  # 종목명 없으면 code 사용
        current_price=sym.get("current_price", 0.0),
        peak_price=sym.get("peak_price", 0.0),
        drop_pct=sym.get("drop_pct", 0.0),
        threshold=0.0,  # 수동 매도는 threshold 무관
        dry_run=False,  # 항상 실거래
    )
    executor.execute(sig)
    return {"ok": True, "message": "매도 주문 제출됨 — 체결 확인 필요"}
```

### Pattern 6: hub.push_snapshot에 dry_run 필드 추가

**What:** 스냅샷에 `is_running`과 `dry_run` 최상위 필드 포함
**When to use:** `hub.push_snapshot()` 수정 시

```python
# Source: [VERIFIED: hub.py push_snapshot 현재 시그니처, CONTEXT.md D-08]
# 옵션 A — push_snapshot 인자 추가:
def push_snapshot(self, states, prices=None, pending_codes=None, dry_run=False):
    ...
    meta = {"is_running": self._is_running, "dry_run": dry_run}
    serialized = {"_meta": meta, **serialized}

# 옵션 B (더 단순) — get_snapshot()에서 engine 참조로 dry_run 읽기:
# create_app lifespan에서 hub.engine = engine 주입
# get_snapshot()이 self._engine._dry_run을 포함
```

### Pattern 7: WebSocket 스냅샷 수신 → UI 버튼 상태 갱신

```javascript
// Source: [VERIFIED: 기존 index.html renderTable() + CONTEXT.md D-06/D-08 확인]
ws.onmessage = function(e) {
    var data = JSON.parse(e.data);
    var meta = data._meta || {};
    var isRunning = meta.is_running || false;
    var isDryRun = meta.dry_run !== undefined ? meta.dry_run : true;

    // 버튼 활성화 상태 갱신
    document.getElementById('btn-start').disabled = isRunning;
    document.getElementById('btn-stop').disabled = !isRunning;

    // 배지 갱신
    updateDryRunBadge(isDryRun);

    // 테이블 갱신 (symbols 부분만)
    renderTable(data);
};
```

### Anti-Patterns to Avoid

- **`trigger_job()` 호출:** APScheduler 3.x에 없는 메서드. `modify_job(next_run_time=now)` 사용.
- **`asyncio.run_in_executor()`로 executor.execute() 호출:** `executor.execute()`는 blocking I/O(KIS API). FastAPI 엔드포인트에서 직접 호출하면 uvicorn 이벤트 루프가 블로킹됨. `asyncio.get_event_loop().run_in_executor(None, executor.execute, sig)` 또는 `BackgroundTasks` 활용 권장.
- **`engine._dry_run` 락 없이 수정:** BackgroundScheduler 스레드와 동시 읽기 발생 가능. 반드시 `hub._lock` 내에서 수정.
- **스냅샷 없이 종목명 조회:** `hub.get_snapshot()`의 `code` 필드는 코드 문자열이므로 종목명(name) 필드는 별도 config에서 가져와야 함.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| APScheduler 즉시 발화 | 새 스레드로 run_session() 직접 호출 | `scheduler.modify_job(next_run_time=now)` | 기존 job ID와 스냅샷 is_running 플래그가 연동되어 있음. 직접 호출하면 hub.set_running() 타이밍 불일치 발생 |
| 스레드 간 상태 공유 | 별도 Lock 클래스 작성 | `hub._lock` (이미 존재하는 RLock) | hub에 이미 _lock이 있으며 hub 상태 수정에 사용 중 |
| 시장 시간 체크 | 외부 라이브러리 | `datetime.now(KST).hour * 60 + minute` | scheduler.py에서 이미 같은 패턴 사용 중 (재사용) |
| UI 상태 동기화 | polling `/api/status` | WebSocket 스냅샷에 필드 추가 | 기존 WebSocket 연결이 이미 있음. 추가 polling 불필요. |

**Key insight:** Phase 7의 모든 핵심 메커니즘(stop_event, is_running, push_snapshot, execute)이 이미 구현되어 있다. 새로 작성하는 것보다 연결하는 작업이다.

---

## Common Pitfalls

### Pitfall 1: trigger_job() 존재하지 않음 (CRITICAL)

**What goes wrong:** CONTEXT.md D-02에 `scheduler.trigger_job("market_poll")` 사용 지시되어 있으나 APScheduler 3.11.2에 해당 메서드가 없어 `AttributeError` 발생.
**Why it happens:** APScheduler 4.x에는 `trigger_job()`이 있으나 3.x 브랜치에는 없음. CONTEXT.md는 3.x 기준 검증 없이 작성됨.
**How to avoid:** `scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))` 사용. [VERIFIED: APScheduler 3.11.2 `dir()` 확인, 실행 검증]
**Warning signs:** `AttributeError: 'BackgroundScheduler' object has no attribute 'trigger_job'`

### Pitfall 2: dry_run 수정 중 스레드 경합

**What goes wrong:** FastAPI 이벤트 루프 스레드에서 `engine._dry_run = new_val` 직접 수정 시, BackgroundScheduler 스레드가 동시에 `engine._dry_run`을 읽어 미수정 값으로 SellSignal 생성.
**Why it happens:** Python GIL이 일부 보호하지만 복합 연산(engine + executor 동시 수정)은 보호하지 못함.
**How to avoid:** `with hub._lock:` 블록 내에서 engine과 executor 두 속성을 함께 수정.
**Warning signs:** 드라이런 토글 후에도 실거래 실행되거나 반대 현상 발생.

### Pitfall 3: executor.execute()가 uvicorn 이벤트 루프를 블로킹

**What goes wrong:** `POST /api/sell/{code}` 핸들러에서 `executor.execute(sig)`를 직접 `await` 없이 호출하면 KIS API blocking I/O가 uvicorn 이벤트 루프를 점유. 다른 요청·WebSocket이 멈춤.
**Why it happens:** `executor.execute()`는 동기 함수(time.sleep 포함). FastAPI async 핸들러 내 동기 blocking I/O는 루프를 블로킹함.
**How to avoid:** `asyncio.get_event_loop().run_in_executor(None, executor.execute, sig)` 또는 FastAPI `BackgroundTasks` 사용.
**Warning signs:** 매도 버튼 클릭 후 WebSocket 스냅샷 갱신이 수 초간 멈춤.

### Pitfall 4: 스냅샷 포맷 변경으로 기존 renderTable 깨짐

**What goes wrong:** `hub.push_snapshot()`이 전송하는 JSON 최상위 구조를 바꾸면 기존 `renderTable(data)`가 종목 코드를 찾지 못함.
**Why it happens:** 현재 스냅샷은 `{code: {symbol_data}}` 최상위 구조. `_meta` 필드를 추가하면 `Object.keys(data)`에 `_meta`가 포함됨.
**How to avoid:** `renderTable(data)`에서 `_meta` 키를 건너뛰는 필터 추가, 또는 `{meta: {...}, symbols: {...}}` 구조로 변경 후 `renderTable(data.symbols)` 호출.
**Warning signs:** 테이블에 undefined 행이 렌더링됨.

### Pitfall 5: SELL_PENDING 중인 종목에 수동 매도 중복 주문

**What goes wrong:** `executor.execute()`는 `_pending` set으로 중복 방지하지만, 프론트엔드에서 버튼 비활성화 없이 빠르게 두 번 클릭하면 두 번째 호출이 executor에 도달함.
**Why it happens:** 첫 번째 API 호출 응답을 받기 전에 두 번째 클릭 가능.
**How to avoid:** D-12에 명시된 대로 SELL_PENDING 종목 행의 버튼을 WebSocket 스냅샷 기반으로 disabled 처리. API 수신 즉시 버튼 임시 비활성화도 추가.
**Warning signs:** 동일 종목 중복 주문 로그.

### Pitfall 6: 시장 시간 체크를 클라이언트에서만 하는 경우

**What goes wrong:** 시장 시간 체크를 JS에서만 하면 직접 API 호출 시 우회 가능.
**Why it happens:** 프론트엔드 유효성 검사는 UX용, 권위적 검사는 항상 서버.
**How to avoid:** `POST /api/start` 서버 핸들러에서 반드시 시장 시간 체크 (D-01/D-03).

---

## Code Examples

### 즉시 발화 확인 코드

```python
# Source: [VERIFIED: python3.11 APScheduler 3.11.2 실행]
from datetime import datetime, timezone
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler(timezone="Asia/Seoul")
# ... add_job("market_poll", ...) ...

# POST /api/start 에서:
scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))
# → 해당 job이 즉시 실행됨 (실험적으로 0.1초 이내 발화 확인)
```

### WebSocket 스냅샷에 메타 필드 추가

```python
# Source: [VERIFIED: hub.py 기존 push_snapshot 분석]
# hub.py push_snapshot() 수정 방향:
def push_snapshot(self, states, prices=None, pending_codes=None, dry_run=False):
    ...  # 기존 serialized 구성 유지
    with self._lock:
        self._snapshot = {
            "_meta": {
                "is_running": self._is_running,
                "dry_run": dry_run,
            },
            **serialized,
        }
    ...  # call_soon_threadsafe 기존 패턴 유지
```

### BackgroundTasks로 비동기 매도 실행

```python
# Source: [VERIFIED: FastAPI 공식 문서 패턴 - ASSUMED API 세부]
from fastapi import BackgroundTasks

@app.post("/api/sell/{code}")
async def api_sell(code: str, request: Request, background_tasks: BackgroundTasks):
    ...
    background_tasks.add_task(executor.execute, sig)
    return {"ok": True, "message": "매도 주문 제출됨 — 체결 확인 필요"}
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| APScheduler `trigger_job()` (4.x) | `modify_job(next_run_time=now)` (3.x) | 3.x 설계 | CONTEXT.md D-02 수정 필요 |
| polling `/api/status` | WebSocket 스냅샷에 `is_running`/`dry_run` 포함 | Phase 6 기반 | 추가 API 엔드포인트 불필요 |

**Deprecated/outdated:**
- `scheduler.trigger_job()`: APScheduler 3.x에 없음. `modify_job(next_run_time=...)` 사용.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `executor.execute()`를 FastAPI BackgroundTasks로 오프로드하면 안전하다 | Pitfall 3 / Pattern 5 | BackgroundTasks가 완료되기 전에 응답 반환 → 에러 피드백 불가. 사용자가 성공 배너를 보지만 실제로는 실패할 수 있음. 대안: `run_in_executor` 사용 후 결과 반환. | [ASSUMED]
| A2 | `hub._lock`을 `engine._dry_run` 수정에 직접 사용해도 `engine` 내부 로직과 충돌하지 않는다 | Pattern 4 | engine 내부에 별도 lock이 있다면 deadlock 가능. 현재 trailing_stop.py에는 별도 lock 없음 확인됨. [VERIFIED: trailing_stop.py 코드 확인] → 위험 낮음 | [ASSUMED] |
| A3 | `SellSignal` 수동 매도에서 `threshold=0.0`으로 설정해도 executor가 정상 처리한다 | Pattern 5 | executor가 threshold를 검증하지 않음 확인됨. [VERIFIED: order_executor.py execute() 확인] | [ASSUMED — LOW RISK] |
| A4 | config에서 종목명(name)을 가져올 수 있다 | Pattern 5 | config.symbols에 name 필드 있음. AppConfig 구조 확인 필요. | [ASSUMED] |

---

## Open Questions

1. **수동 매도에서 종목명(name) 조회 경로**
   - 알고 있는 것: `hub.get_snapshot()`의 각 symbol dict에 `code` 필드는 있음.
   - 불명확한 것: `name` 필드가 스냅샷에 포함되지 않음. `config.symbols`에서 가져와야 하나?
   - 권고: `POST /api/sell/{code}` 핸들러에서 `request.app.state.config.symbols`에서 name 조회. 없으면 code를 name으로 사용.

2. **hub.push_snapshot()에 engine 참조 주입 vs 인자 추가**
   - 알고 있는 것: `dry_run` 값을 스냅샷에 포함해야 함 (D-08).
   - 불명확한 것: `hub.push_snapshot(dry_run=engine._dry_run)` 방식이면 scheduler.py도 수정 필요. hub에 engine 직접 참조 주입이 더 단순할 수 있음.
   - 권고: scheduler.py `run_session()` 내 `hub.push_snapshot()` 호출에 `dry_run=engine._dry_run` 인자 추가. 가장 침습도가 낮음.

3. **BackgroundTasks vs run_in_executor**
   - 알고 있는 것: `executor.execute()`는 blocking I/O(KIS API, time.sleep 포함).
   - 불명확한 것: 사용자에게 주문 실패 즉시 피드백이 필요한지 여부.
   - 권고: `asyncio.get_event_loop().run_in_executor(None, executor.execute, sig)` 사용. 실패 시 예외를 catch하여 5xx 응답 반환 가능.

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| FastAPI | POST 엔드포인트 | ✓ | 0.135.3 | — |
| APScheduler 3.x | `modify_job()` 즉시 발화 | ✓ | 3.11.2 | — |
| Python 3.11 (Homebrew) | zoneinfo, tomllib | ✓ | 3.11.x | — |
| uvicorn | FastAPI 서버 | ✓ | 0.44.0 | — |

[VERIFIED: pyproject.toml, python3.11 경로 확인]

**Missing dependencies with no fallback:** 없음.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (dev 의존성) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python3.11 -m pytest tests/test_app_routes.py -x -q` |
| Full suite command | `python3.11 -m pytest tests/ -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CTRL-01 | POST /api/start → 200 OK, modify_job 호출 | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_start_ok -x` | ❌ Wave 0 |
| CTRL-01 | POST /api/start → 409 (already running) | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_start_409 -x` | ❌ Wave 0 |
| CTRL-01 | POST /api/start → 400 (시장 시간 외) | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_start_market_closed -x` | ❌ Wave 0 |
| CTRL-02 | POST /api/stop → 200 OK, request_stop 호출 | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_stop_ok -x` | ❌ Wave 0 |
| CTRL-03 | POST /api/toggle-dry-run → engine._dry_run 반전 | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_toggle_dry_run -x` | ❌ Wave 0 |
| CTRL-04 | POST /api/sell/{code} → executor.execute 호출 | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_sell_ok -x` | ❌ Wave 0 |
| CTRL-04 | POST /api/sell/{code} → 404 (종목 없음) | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_sell_404 -x` | ❌ Wave 0 |
| D-08 | hub.push_snapshot() dry_run 필드 포함 | unit | `python3.11 -m pytest tests/test_hub.py::TestBotStateHubPhase7 -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** `python3.11 -m pytest tests/test_app_routes.py tests/test_hub.py -x -q`
- **Per wave merge:** `python3.11 -m pytest tests/ -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_app_routes.py::TestControlRoutes` — CTRL-01~04 커버 (기존 파일에 클래스 추가)
- [ ] `tests/test_hub.py::TestBotStateHubPhase7` — dry_run 필드 포함 스냅샷 테스트 (기존 파일에 클래스 추가)

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | 개인용 봇, 인증 없음 (Out of Scope) |
| V3 Session Management | no | 세션 없음 |
| V4 Access Control | no | 단일 사용자 |
| V5 Input Validation | yes | FastAPI path param `code` — KIS 종목코드 형식 검증 필요 |
| V6 Cryptography | no | 이번 Phase 해당 없음 |

### Known Threat Patterns for FastAPI + 수동 매도

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| 종목 코드 path param에 악성 문자 삽입 | Tampering | `code` 파라미터를 `^[0-9A-Za-z]{1,12}$` 정규식으로 검증. 기존 `sanitizeCode()` JS 패턴과 동일 서버 측 적용. |
| 브라우저에서 시장 시간 체크 우회 | Elevation of Privilege | 서버 핸들러에서 반드시 KST 시간 재검증 (D-01/D-03) |
| 중복 매도 요청 (빠른 연속 클릭) | Tampering | `executor._pending` set이 중복 방지. 프론트엔드 버튼 disabled 추가(D-12). |

---

## Sources

### Primary (HIGH confidence)

- `mutrade/admin/hub.py` 코드 직접 분석 [VERIFIED]
- `mutrade/admin/app.py` 코드 직접 분석 [VERIFIED]
- `mutrade/monitor/scheduler.py` 코드 직접 분석 [VERIFIED]
- `mutrade/executor/order_executor.py` 코드 직접 분석 [VERIFIED]
- `mutrade/engine/trailing_stop.py` 코드 직접 분석 [VERIFIED]
- APScheduler 3.11.2 `dir(BackgroundScheduler())` 실행 — `trigger_job` 미존재 확인 [VERIFIED]
- `modify_job(next_run_time=datetime.now(timezone.utc))` 즉시 발화 실험 [VERIFIED]
- FastAPI `request.app.state` 의존성 접근 패턴 실험 [VERIFIED]
- `pyproject.toml` 의존성 목록 [VERIFIED]

### Secondary (MEDIUM confidence)

- CONTEXT.md 07-CONTEXT.md — 사용자 결정 사항
- 07-UI-SPEC.md — UI 디자인 계약

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — 모든 의존성이 pyproject.toml로 확인됨. 추가 설치 없음.
- Architecture: HIGH — 기존 코드 패턴 직접 분석 완료. 연결 경로 검증됨.
- Pitfalls: HIGH — `trigger_job()` 부재는 실행으로 확인. 스레드 안전성 위험은 코드 분석으로 식별.

**Research date:** 2026-04-18
**Valid until:** 2026-05-18 (APScheduler 3.x는 안정적, FastAPI 0.13x는 안정적)
