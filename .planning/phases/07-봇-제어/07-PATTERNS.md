# Phase 7: 봇 제어 — Pattern Map

**Mapped:** 2026-04-18
**Files analyzed:** 5 (수정 대상 파일 기준)
**Analogs found:** 5 / 5

---

## File Classification

| 수정/추가 파일 | Role | Data Flow | 가장 가까운 Analog | Match Quality |
|----------------|------|-----------|-------------------|---------------|
| `mutrade/admin/app.py` | controller (route handler) | request-response | `mutrade/admin/app.py` 기존 라우트 | exact — 동일 파일에 라우트 추가 |
| `mutrade/admin/hub.py` | state-bridge | event-driven | `mutrade/admin/hub.py` 기존 push_snapshot | exact — 동일 파일에 인자 추가 |
| `mutrade/monitor/scheduler.py` | service | event-driven | `mutrade/monitor/scheduler.py` 기존 run_session | exact — 동일 파일에 dry_run 인자 전달 |
| `mutrade/admin/static/index.html` | component (vanilla JS UI) | request-response + WebSocket | `mutrade/admin/static/index.html` 기존 renderTable | exact — 동일 파일에 UI 추가 |
| `tests/test_app_routes.py` | test | request-response | `tests/test_app_routes.py` 기존 TestWebSocketEndpoint | exact — 동일 파일에 클래스 추가 |
| `tests/test_hub.py` | test | event-driven | `tests/test_hub.py` 기존 TestBotStateHubPhase6 | exact — 동일 파일에 클래스 추가 |

---

## Pattern Assignments

### `mutrade/admin/app.py` — 4개 POST 라우트 추가

**Analog:** `mutrade/admin/app.py` (기존 GET 라우트 패턴)

**Import 패턴** (lines 16-24):
```python
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from mutrade.admin.hub import BotStateHub
```

Phase 7에서 추가할 import:
```python
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from mutrade.engine.models import SellSignal
```

**app.state 의존성 주입 패턴** (lines 47-58, lifespan):
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_running_loop()
    hub.attach_loop(loop)
    app.state.hub = hub
    # Phase 7: 추가 주입
    app.state.scheduler = kwargs.get("scheduler")
    app.state.engine = kwargs.get("engine")
    app.state.executor = kwargs.get("executor")
    app.state.config = kwargs.get("config")
    logger.info("Admin server started. BotStateHub loop attached.")
    yield
    hub.request_stop()
    scheduler = kwargs.get("scheduler")
    if scheduler is not None:
        scheduler.shutdown(wait=False)
    logger.info("Admin server shutting down.")
```

**기존 GET 라우트 패턴** (lines 69-81) — POST 라우트도 동일 구조 따름:
```python
@app.get("/health")
async def health() -> dict:
    return {
        "status": "ok",
        "bot_running": hub.is_running(),
        "stop_requested": hub.is_stop_requested(),
    }
```

**POST /api/start 구현 패턴** (RESEARCH.md Pattern 3 기반):
```python
KST = ZoneInfo("Asia/Seoul")

@app.post("/api/start")
async def api_start(request: Request):
    _hub: BotStateHub = request.app.state.hub
    scheduler = request.app.state.scheduler

    if _hub.is_running():
        raise HTTPException(status_code=409, detail="이미 실행 중입니다")

    now_kst = datetime.now(KST)
    current_min = now_kst.hour * 60 + now_kst.minute
    if not (9 * 60 <= current_min < 15 * 60 + 20):
        raise HTTPException(
            status_code=400,
            detail="시장 시간이 아닙니다 (09:00~15:20 KST)"
        )

    _hub.clear_stop()
    scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))
    logger.info("Admin UI: 봇 시작 요청 — modify_job 발화")
    return {"ok": True, "message": "모니터링 세션 시작됨"}
```

**POST /api/stop 구현 패턴** (RESEARCH.md Pattern, hub.request_stop 재사용):
```python
@app.post("/api/stop")
async def api_stop(request: Request):
    _hub: BotStateHub = request.app.state.hub
    _hub.request_stop()
    logger.info("Admin UI: 봇 중지 요청")
    return {"ok": True, "message": "중지 요청됨"}
```

**POST /api/toggle-dry-run 구현 패턴** (RESEARCH.md Pattern 4 기반):
```python
@app.post("/api/toggle-dry-run")
async def api_toggle_dry_run(request: Request):
    _hub: BotStateHub = request.app.state.hub
    engine = request.app.state.engine
    executor = request.app.state.executor

    with _hub._lock:
        new_val = not engine._dry_run
        engine._dry_run = new_val
        executor._dry_run = new_val

    direction = "드라이런" if new_val else "실매도"
    logger.info("Admin UI: dry_run={}", new_val)
    return {
        "ok": True,
        "dry_run": new_val,
        "message": f"{direction} 모드로 전환됨. 재시작 시 .env 설정으로 초기화됩니다",
    }
```

**POST /api/sell/{code} 구현 패턴** (RESEARCH.md Pattern 5 기반):
```python
@app.post("/api/sell/{code}")
async def api_sell(code: str, request: Request):
    import re
    if not re.match(r'^[0-9A-Za-z]{1,12}$', code):
        raise HTTPException(status_code=400, detail="유효하지 않은 종목 코드")

    _hub: BotStateHub = request.app.state.hub
    executor = request.app.state.executor
    _config = request.app.state.config

    snapshot = _hub.get_snapshot()
    sym = snapshot.get(code)
    if sym is None:
        raise HTTPException(status_code=404, detail=f"종목 {code}를 찾을 수 없습니다")

    # config에서 종목명 조회, 없으면 code 사용
    name = code
    if _config is not None:
        sym_cfg = next((s for s in _config.symbols if s.code == code), None)
        if sym_cfg:
            name = sym_cfg.name

    sig = SellSignal(
        code=code,
        name=name,
        current_price=sym.get("current_price", 0.0),
        peak_price=sym.get("peak_price", 0.0),
        drop_pct=sym.get("drop_pct", 0.0),
        threshold=0.0,
        dry_run=False,  # D-11: 수동 매도는 항상 실거래
    )
    # Pitfall 3 방어: blocking I/O를 threadpool로 오프로드
    await run_in_threadpool(executor.execute, sig)
    logger.warning("Admin UI: 수동 매도 주문 제출 — {}", code)
    return {"ok": True, "message": "매도 주문 제출됨 — 체결 확인 필요"}
```

**오류 응답 패턴** — HTTPException 사용 (기존 /health와 동일한 FastAPI 관례):
```python
# 409: 이미 실행 중
raise HTTPException(status_code=409, detail="이미 실행 중입니다")
# 400: 잘못된 요청 (시장 시간 외, 잘못된 코드)
raise HTTPException(status_code=400, detail="메시지")
# 404: 종목 없음
raise HTTPException(status_code=404, detail=f"종목 {code}를 찾을 수 없습니다")
```

---

### `mutrade/admin/hub.py` — push_snapshot에 dry_run 필드 추가

**Analog:** `mutrade/admin/hub.py` push_snapshot (lines 31-83)

**기존 push_snapshot 시그니처** (lines 31-36):
```python
def push_snapshot(
    self,
    states: dict,
    prices: "dict[str, float] | None" = None,
    pending_codes: "frozenset[str] | None" = None,
) -> None:
```

**Phase 7 수정 방향 — dry_run 인자 추가**:
```python
def push_snapshot(
    self,
    states: dict,
    prices: "dict[str, float] | None" = None,
    pending_codes: "frozenset[str] | None" = None,
    dry_run: bool = False,         # Phase 7 추가 (D-08)
) -> None:
    ...
    with self._lock:
        self._snapshot = {
            "_meta": {
                "is_running": self._is_running,
                "dry_run": dry_run,
            },
            **serialized,
        }
    ...
```

**스냅샷 구조 변경 시 renderTable 호환성 주의** (Pitfall 4):
```python
# 기존 renderTable(data)는 Object.keys(data)로 종목 코드를 순회함
# _meta 키가 포함되면 undefined 행이 렌더링될 수 있음
# → index.html renderTable에서 _meta 키를 건너뛰는 필터 추가 필요
```

**set_running 패턴** (lines 131-134) — is_running 상태 관리 참조:
```python
def set_running(self, running: bool) -> None:
    """APScheduler 스레드가 세션 시작/종료 시 호출."""
    with self._lock:
        self._is_running = running
```

---

### `mutrade/monitor/scheduler.py` — push_snapshot 호출에 dry_run 인자 전달

**Analog:** `mutrade/monitor/scheduler.py` run_session (lines 58-131)

**기존 hub.push_snapshot 호출** (line 116):
```python
if hub is not None:
    hub.push_snapshot(engine.states, prices, executor.pending_codes())
    hub.set_running(True)
```

**Phase 7 수정 — dry_run 인자 추가**:
```python
if hub is not None:
    hub.push_snapshot(
        engine.states,
        prices,
        executor.pending_codes(),
        dry_run=engine._dry_run,   # Phase 7 추가 (D-08)
    )
    hub.set_running(True)
```

**KST 시간 체크 패턴** (lines 88-97) — POST /api/start 시장 시간 검증과 동일 패턴:
```python
now_kst = datetime.now(KST)
current_minutes = now_kst.hour * 60 + now_kst.minute

if current_minutes >= close_minutes:
    logger.info(
        "Market session ended ({:02d}:{:02d} KST).",
        config.market_close_hour,
        config.market_close_minute,
    )
    break
```

**stop 플래그 확인 패턴** (lines 82-86) — 기존 그대로 유지:
```python
if hub is not None and hub.is_stop_requested():
    logger.info("Admin UI 중단 요청 — 세션 종료.")
    hub.clear_stop()
    break
```

---

### `mutrade/admin/static/index.html` — 제어 UI 추가

**Analog:** `mutrade/admin/static/index.html` 기존 전체 파일

**기존 헤더 구조** (lines 60-66) — 제어 버튼 그룹 삽입 위치:
```html
<div id="header">
  <span id="title">MuTrade 모니터링</span>
  <span id="ws-status">
    <span id="ws-dot"></span>
    <span id="ws-text">연결 중...</span>
  </span>
</div>
```

**Phase 7 헤더 수정 방향** — `#ws-status` 왼쪽에 제어 영역 삽입:
```html
<div id="header">
  <span id="title">MuTrade 모니터링</span>
  <span id="header-controls" style="display:flex;align-items:center;gap:8px;">
    <span id="dry-run-badge" onclick="toggleDryRun()"
      style="font-size:12px;font-weight:600;padding:4px 8px;border-radius:4px;cursor:pointer;">
      드라이런
    </span>
    <button id="btn-start" onclick="startBot()"
      style="font-size:14px;font-weight:600;padding:8px 16px;border-radius:6px;
             border:none;cursor:pointer;background:#3b82f6;color:#fff;">
      시작
    </button>
    <button id="btn-stop" onclick="stopBot()" disabled
      style="font-size:14px;font-weight:600;padding:8px 16px;border-radius:6px;
             border:none;cursor:pointer;background:#dc2626;color:#fff;">
      중지
    </button>
    <span id="ws-status">
      <span id="ws-dot"></span>
      <span id="ws-text">연결 중...</span>
    </span>
  </span>
</div>
```

**배너 요소** (헤더 아래, 컨테이너 위 — 기존 없음, 신규 추가):
```html
<div id="banner" role="alert"
  style="display:none;padding:12px 24px;font-size:14px;font-weight:400;">
</div>
```

**기존 테이블 구조** (lines 70-81) — 6번째 열 추가:
```html
<thead>
  <tr>
    <th>종목코드</th>
    <th>현재가</th>
    <th>고점</th>
    <th>하락률</th>
    <th>상태</th>
    <th style="width:80px;text-align:center;">액션</th>  <!-- Phase 7 추가 -->
  </tr>
</thead>
```

**기존 renderTable 패턴** (lines 133-159) — Phase 7에서 _meta 필터 + 즉시 매도 버튼 추가:
```javascript
function renderTable(data) {
  // Phase 7: _meta 키 건너뛰기 (Pitfall 4 방어)
  var symbols = {};
  Object.keys(data).forEach(function(k) {
    if (k !== '_meta') symbols[k] = data[k];
  });

  var keys = Object.keys(symbols);
  if (keys.length === 0) {
    tbody.innerHTML = '';
    table.style.display = 'none';
    emptyState.style.display = 'block';
    return;
  }
  table.style.display = '';
  emptyState.style.display = 'none';
  tbody.innerHTML = keys.map(function(code) {
    var sym = symbols[code];
    var isPending = sym.sell_pending;
    var safeCode = sanitizeCode(sym.code);
    // 즉시 매도 버튼 (D-12: SELL_PENDING 시 disabled)
    var sellBtn = '<button onclick="manualSell(\'' + safeCode + '\')" ' +
      (isPending ? 'disabled ' : '') +
      'style="font-size:12px;font-weight:600;padding:4px 8px;border-radius:4px;' +
      'border:none;cursor:' + (isPending ? 'not-allowed' : 'pointer') + ';' +
      'background:' + (isPending ? '#374151' : '#dc2626') + ';' +
      'color:' + (isPending ? '#6b7280' : '#fff') + ';">' +
      '즉시 매도</button>';
    return '<tr class="' + (isPending ? 'sell-pending' : '') + '">' +
      '<td>' + safeCode + '</td>' +
      '<td>' + fmtPrice(sym.current_price) + '</td>' +
      '<td>' + fmtPrice(sym.peak_price) + '</td>' +
      '<td style="color:' + getDropColor(sym.drop_pct) + '">' + fmtDrop(sym.drop_pct, sym.warm) + '</td>' +
      '<td><span class="status-badge">' + getStatusText(sym) + '</span></td>' +
      '<td style="text-align:center;">' + sellBtn + '</td>' +
      '</tr>';
  }).join('');
}
```

**WebSocket onmessage 패턴** (lines 165-169) — Phase 7에서 메타 필드 처리 추가:
```javascript
// 기존
ws.onmessage = function(e) {
  try { renderTable(JSON.parse(e.data)); } catch(err) { console.error('parse error', err); }
};

// Phase 7 수정
ws.onmessage = function(e) {
  try {
    var data = JSON.parse(e.data);
    var meta = data._meta || {};
    var isRunning = meta.is_running || false;
    var isDryRun = meta.dry_run !== undefined ? meta.dry_run : true;

    // 버튼 활성화 상태 갱신
    var btnStart = document.getElementById('btn-start');
    var btnStop = document.getElementById('btn-stop');
    if (btnStart) btnStart.disabled = isRunning;
    if (btnStop) btnStop.disabled = !isRunning;

    updateDryRunBadge(isDryRun);
    renderTable(data);
  } catch(err) { console.error('parse error', err); }
};
```

**배너 함수 패턴** (신규 추가):
```javascript
var bannerTimer = null;

function showBanner(msg, type) {
  // type: 'success' | 'error'
  var el = document.getElementById('banner');
  if (!el) return;
  el.textContent = msg;
  el.style.display = 'block';
  el.style.background = type === 'success' ? '#14532d' : '#7f1d1d';
  el.style.color = type === 'success' ? '#86efac' : '#fca5a5';
  if (bannerTimer) clearTimeout(bannerTimer);
  bannerTimer = setTimeout(function() { el.style.display = 'none'; }, 4000);
}

function hideBanner() {
  var el = document.getElementById('banner');
  if (el) el.style.display = 'none';
}
```

**드라이런 배지 갱신 함수** (신규 추가):
```javascript
function updateDryRunBadge(isDryRun) {
  var badge = document.getElementById('dry-run-badge');
  if (!badge) return;
  badge.textContent = isDryRun ? '드라이런' : '실매도';
  badge.style.background = isDryRun ? '#78350f' : '#7f1d1d';
  badge.style.color = isDryRun ? '#fbbf24' : '#f87171';
}
```

**버튼 클릭 핸들러 패턴** (신규 추가):
```javascript
function startBot() {
  fetch('/api/start', {method: 'POST'})
    .then(function(r) {
      return r.json().then(function(body) { return {ok: r.ok, body: body}; });
    })
    .then(function(res) {
      if (!res.ok) showBanner(res.body.detail || '시작 실패', 'error');
      // 200 시 배너 없음 — WebSocket 스냅샷으로 버튼 상태 갱신
    })
    .catch(function(e) { showBanner('요청 실패: ' + e, 'error'); });
}

function stopBot() {
  var snapshot = window._lastSnapshot || {};
  var meta = snapshot._meta || {};
  var hasPending = Object.keys(snapshot).some(function(k) {
    return k !== '_meta' && snapshot[k].sell_pending;
  });
  if (hasPending) {
    if (!confirm('매도 진행 중인 종목이 있습니다. 그래도 중지하시겠습니까?')) return;
  }
  fetch('/api/stop', {method: 'POST'})
    .then(function(r) { return r.json(); })
    .catch(function(e) { showBanner('요청 실패: ' + e, 'error'); });
}

function toggleDryRun() {
  fetch('/api/toggle-dry-run', {method: 'POST'})
    .then(function(r) { return r.json(); })
    .then(function(body) {
      if (body.ok) showBanner(body.message, 'success');
      else showBanner(body.message || '토글 실패', 'error');
    })
    .catch(function(e) { showBanner('요청 실패: ' + e, 'error'); });
}

function manualSell(code) {
  if (!confirm('[' + code + ']을(를) 시장가로 매도하시겠습니까?')) return;
  fetch('/api/sell/' + code, {method: 'POST'})
    .then(function(r) {
      return r.json().then(function(body) { return {ok: r.ok, body: body}; });
    })
    .then(function(res) {
      if (res.ok) showBanner(res.body.message || '매도 주문 제출됨 — 체결 확인 필요', 'success');
      else showBanner('매도 실패: ' + (res.body.detail || res.body.message || '오류'), 'error');
    })
    .catch(function(e) { showBanner('요청 실패: ' + e, 'error'); });
}
```

---

### `tests/test_app_routes.py` — TestControlRoutes 클래스 추가

**Analog:** `tests/test_app_routes.py` TestWebSocketEndpoint (lines 94-182)

**픽스처 패턴** (lines 23-39) — Phase 7 테스트도 동일 픽스처 재사용:
```python
@pytest.fixture
def hub():
    """테스트용 BotStateHub (실제 인스턴스)."""
    return BotStateHub()

@pytest.fixture
def app(hub, tmp_path):
    """static 디렉터리 + index.html이 있는 FastAPI 앱."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>dashboard</html>")

    import mutrade.admin.app as app_module
    with patch.object(app_module, "STATIC_DIR", static_dir, create=True):
        _app = create_app(hub)
    return _app
```

**TestClient 패턴** (lines 117-120) — POST 엔드포인트 테스트에 동일 방식 적용:
```python
with TestClient(app) as client:
    resp = client.post("/api/start")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
```

**MagicMock 주입 패턴** (lines 103-115) — scheduler, engine, executor mock:
```python
# Phase 7 테스트 픽스처 예시
from unittest.mock import MagicMock, patch
from apscheduler.schedulers.background import BackgroundScheduler

@pytest.fixture
def mock_scheduler():
    sched = MagicMock(spec=BackgroundScheduler)
    return sched

@pytest.fixture
def app_with_deps(hub, tmp_path, mock_scheduler):
    from mutrade.engine.trailing_stop import TrailingStopEngine
    from mutrade.executor.order_executor import OrderExecutor

    engine = MagicMock(spec=TrailingStopEngine)
    engine._dry_run = True
    executor = MagicMock(spec=OrderExecutor)

    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html/>")

    import mutrade.admin.app as app_module
    with patch.object(app_module, "STATIC_DIR", static_dir, create=True):
        _app = create_app(hub, scheduler=mock_scheduler, engine=engine, executor=executor)
    return _app
```

---

### `tests/test_hub.py` — TestBotStateHubPhase7 클래스 추가

**Analog:** `tests/test_hub.py` TestBotStateHubPhase6 (lines 158-286)

**클래스 구조 패턴** (lines 158-173):
```python
class TestBotStateHubPhase7:
    """Phase 7 — push_snapshot dry_run 필드 TDD 테스트."""

    def _make_hub(self):
        from mutrade.admin.hub import BotStateHub
        return BotStateHub()

    def _make_fake_state(self, code="005930", peak=86200.0):
        class FakeState:
            def __init__(self, code, peak):
                self.code = code
                self.peak_price = peak
                self.warm = True
        return FakeState(code, peak)
```

**dry_run 필드 검증 테스트 패턴** (기존 TestBotStateHubPhase6.test_get_snapshot_contains_sell_pending_true 참조):
```python
def test_push_snapshot_with_dry_run_true(self):
    """push_snapshot(dry_run=True) 시 _meta.dry_run=True."""
    hub = self._make_hub()
    states = {"005930": self._make_fake_state()}
    hub.push_snapshot(states, dry_run=True)
    snap = hub.get_snapshot()
    assert "_meta" in snap
    assert snap["_meta"]["dry_run"] is True

def test_push_snapshot_with_dry_run_false(self):
    """push_snapshot(dry_run=False) 시 _meta.dry_run=False."""
    hub = self._make_hub()
    states = {"005930": self._make_fake_state()}
    hub.push_snapshot(states, dry_run=False)
    snap = hub.get_snapshot()
    assert snap["_meta"]["dry_run"] is False

def test_push_snapshot_dry_run_default_false(self):
    """push_snapshot dry_run 기본값=False — 하위 호환."""
    hub = self._make_hub()
    states = {"005930": self._make_fake_state()}
    hub.push_snapshot(states)
    snap = hub.get_snapshot()
    assert snap["_meta"]["dry_run"] is False

def test_meta_contains_is_running(self):
    """_meta.is_running 필드도 포함되어야 한다."""
    hub = self._make_hub()
    states = {"005930": self._make_fake_state()}
    hub.set_running(True)
    hub.push_snapshot(states)
    snap = hub.get_snapshot()
    assert snap["_meta"]["is_running"] is True
```

---

## Shared Patterns

### 로깅 패턴
**Source:** `mutrade/admin/app.py` line 24, `mutrade/monitor/scheduler.py` lines 64-72
**Apply to:** 모든 POST 엔드포인트 핸들러
```python
from loguru import logger

# 정보 로그
logger.info("Admin UI: 봇 시작 요청 — modify_job 발화")
# 경고 로그 (매도 관련)
logger.warning("Admin UI: 수동 매도 주문 제출 — {}", code)
```

### hub._lock RLock 패턴
**Source:** `mutrade/admin/hub.py` lines 18, 71-73, 131-134
**Apply to:** `toggle-dry-run` 엔드포인트, hub.push_snapshot 수정
```python
# threading.RLock 재사용 패턴
with self._lock:
    self._is_running = running

# 복합 속성 동시 수정 시 (engine + executor)
with _hub._lock:
    engine._dry_run = new_val
    executor._dry_run = new_val
```

### APScheduler modify_job 패턴
**Source:** RESEARCH.md Pattern 2 (VERIFIED: APScheduler 3.11.2)
**Apply to:** POST /api/start 엔드포인트
```python
# CRITICAL: trigger_job()은 APScheduler 3.x에 없음 — modify_job 사용
from datetime import datetime, timezone
scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))
```

### SellSignal 생성 패턴
**Source:** `mutrade/engine/trailing_stop.py` lines 121-128
**Apply to:** POST /api/sell/{code} 엔드포인트
```python
from mutrade.engine.models import SellSignal

signal = SellSignal(
    code=code,
    name=name,
    current_price=price,
    peak_price=peak,
    drop_pct=drop,
    threshold=threshold,
    dry_run=False,          # 수동 매도는 항상 False (D-11)
)
```

### run_in_threadpool 패턴 (blocking I/O 오프로드)
**Source:** RESEARCH.md Pitfall 3
**Apply to:** POST /api/sell/{code} 엔드포인트에서 executor.execute() 호출
```python
from fastapi.concurrency import run_in_threadpool

# executor.execute()는 blocking I/O (KIS API + time.sleep)
# FastAPI async 핸들러에서 직접 호출 시 uvicorn 이벤트 루프 블로킹
await run_in_threadpool(executor.execute, sig)
```

### sanitizeCode XSS 방어 패턴
**Source:** `mutrade/admin/static/index.html` lines 118-122
**Apply to:** POST /api/sell/{code} 서버 측 검증 + index.html manualSell JS
```python
# 서버 측 (app.py)
import re
if not re.match(r'^[0-9A-Za-z]{1,12}$', code):
    raise HTTPException(status_code=400, detail="유효하지 않은 종목 코드")
```
```javascript
// 클라이언트 측 (index.html — 기존 sanitizeCode 재사용)
function sanitizeCode(code) {
  if (typeof code !== 'string') return '';
  return code.replace(/[^0-9A-Za-z]/g, '');
}
```

---

## No Analog Found

없음. Phase 7의 모든 파일은 기존 코드의 확장이며 동일 파일 내에 추가된다.

---

## Critical Notes for Planner

### APScheduler API (CRITICAL)
- `scheduler.trigger_job("market_poll")` — APScheduler 3.11.2에 **존재하지 않음**
- 올바른 패턴: `scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))`
- Source: RESEARCH.md Pitfall 1 [VERIFIED: 실행 확인]

### 스냅샷 구조 변경 시 renderTable 호환성 (CRITICAL)
- `_meta` 키가 추가되면 기존 `renderTable(data)`에서 undefined 행이 렌더링됨
- `renderTable` 내부에 `if (k !== '_meta') symbols[k] = data[k]` 필터 반드시 추가
- Source: RESEARCH.md Pitfall 4

### executor.execute() blocking I/O (IMPORTANT)
- `order_executor.py` 내 `time.sleep(interval_sec)` (line 142) 포함 → uvicorn 이벤트 루프 블로킹
- `run_in_threadpool(executor.execute, sig)` 로 반드시 오프로드
- Source: RESEARCH.md Pitfall 3

---

## Metadata

**Analog search scope:** `mutrade/admin/`, `mutrade/monitor/`, `mutrade/executor/`, `mutrade/engine/`, `tests/`
**Files scanned:** 10
**Pattern extraction date:** 2026-04-18
