---
phase: 07-봇-제어
reviewed: 2026-04-18T00:00:00Z
depth: standard
files_reviewed: 6
files_reviewed_list:
  - mutrade/admin/hub.py
  - mutrade/admin/app.py
  - mutrade/monitor/scheduler.py
  - tests/test_hub.py
  - tests/test_app_routes.py
  - mutrade/admin/static/index.html
findings:
  critical: 2
  warning: 4
  info: 3
  total: 9
status: issues_found
---

# Phase 07: Code Review Report

**Reviewed:** 2026-04-18T00:00:00Z
**Depth:** standard
**Files Reviewed:** 6
**Status:** issues_found

## Summary

Phase 7 봇 제어 구현(BotStateHub, FastAPI 제어 엔드포인트, APScheduler 세션, 대시보드 UI)을 리뷰했다. 전반적인 구조는 견고하나, 두 가지 Critical 문제가 발견됐다. 하나는 수동 매도 엔드포인트가 인증 없이 노출된 것이고, 다른 하나는 `api_toggle_dry_run`에서 내부 잠금 없이 공유 객체를 뮤테이션하는 경합 조건이다. Warning 수준 문제로는 scheduler가 None일 때 `api_start`에서 발생하는 AttributeError, hub의 `_is_running` 읽기 타이밍과 스냅샷 삽입 사이의 순서 역전, WebSocket 단일 소비자 제약, 그리고 `run_session` 내부에서 `hub.set_running(True)`가 루프 최상단이 아닌 폴링 후에 위치한 점이 있다.

---

## Critical Issues

### CR-01: 수동 매도 엔드포인트 — 인증 없이 임의 매도 주문 가능

**File:** `mutrade/admin/app.py:136-168`
**Issue:** `POST /api/sell/{code}` 엔드포인트는 인증 없이 호출 가능하다. 어드민 서버가 로컬호스트 전용이 아닌 네트워크에 바인딩된 경우(예: `uvicorn --host 0.0.0.0`), 동일 네트워크의 누구나 임의 종목의 시장가 매도를 트리거할 수 있다. `dry_run=False`를 하드코딩하여 항상 실거래로 실행된다.

**Fix:** 최소한 요청 IP 또는 간단한 API 토큰 검증을 추가하거나, 서버 바인딩을 loopback(127.0.0.1)으로 제한한다. 단기 방어:

```python
# app.py — api_sell 엔드포인트 상단에 IP 화이트리스트 체크 추가
@app.post("/api/sell/{code}")
async def api_sell(code: str, request: Request):
    if request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(status_code=403, detail="Forbidden")
    # ... 기존 로직
```

또는 `start_scheduler` 호출 측에서 `uvicorn.run(..., host="127.0.0.1")`으로 바인딩을 제한한다.

---

### CR-02: `api_toggle_dry_run` — `engine`/`executor`가 None일 때 AttributeError

**File:** `mutrade/admin/app.py:117-134`
**Issue:** `engine = request.app.state.engine`과 `executor = request.app.state.executor`가 `None`일 수 있다(kwargs에서 전달되지 않으면 `None`으로 설정됨, line 61-62). `with _hub._lock:` 블록 안에서 `engine._dry_run`을 직접 접근하면 `AttributeError`가 발생하고 RLock이 해제되지 않는 문제는 없지만(`with` 문이 보장), `None`에 대한 속성 접근 자체가 500 Internal Server Error를 유발한다. 또한 `_hub._lock`은 `hub` 내부의 private lock인데 외부 코드가 이를 직접 사용하는 것은 캡슐화 위반이다.

**Fix:** None 체크 추가 및 lock 외부화:

```python
@app.post("/api/toggle-dry-run")
async def api_toggle_dry_run(request: Request):
    _hub: BotStateHub = request.app.state.hub
    engine = request.app.state.engine
    executor = request.app.state.executor

    if engine is None or executor is None:
        raise HTTPException(status_code=503, detail="엔진이 초기화되지 않았습니다")

    # _hub._lock 대신 별도 lock 사용하거나 BotStateHub에 toggle_dry_run() 메서드 추가
    new_val = not engine._dry_run
    engine._dry_run = new_val
    executor._dry_run = new_val
    # ...
```

BotStateHub의 내부 lock(`_hub._lock`)을 app.py가 직접 획득하는 것은 설계 원칙에 맞지 않는다. `engine`/`executor`의 `_dry_run`은 자체 lock으로 보호하거나 원자적 플래그를 사용해야 한다.

---

## Warnings

### WR-01: `api_start` — `scheduler`가 None일 때 AttributeError 발생

**File:** `mutrade/admin/app.py:92-108`
**Issue:** `scheduler = request.app.state.scheduler`(line 92)가 None이면(create_app 호출 시 scheduler 미전달), line 106의 `scheduler.modify_job(...)` 호출에서 `AttributeError`가 발생하여 500을 반환한다. None 체크가 없다.

**Fix:**
```python
if scheduler is None:
    raise HTTPException(status_code=503, detail="스케줄러가 초기화되지 않았습니다")
```
line 105(`_hub.clear_stop()`) 이전에 추가한다.

---

### WR-02: `run_session` — `hub.set_running(True)` 위치가 첫 폴링 이후

**File:** `mutrade/monitor/scheduler.py:114-117`
**Issue:** `hub.set_running(True)`가 첫 번째 `poll_prices()` + `engine.tick()` 완료 후에 호출된다(line 117). 즉 첫 번째 폴링이 실행되는 동안 `is_running()`은 여전히 `False`를 반환한다. `/health` 엔드포인트나 UI가 이 값을 보여줄 때 세션이 이미 시작됐음에도 "미실행" 상태로 표시된다. 또한 `api_start`가 409를 반환해야 하는 시점에 200을 반환할 수 있다.

**Fix:** 루프 진입 직전에 `set_running(True)` 호출:
```python
# while True 루프 이전에 호출
if hub is not None:
    hub.set_running(True)

while True:
    # ... 기존 루프
```
루프 종료 후 `set_running(False)`는 현재 위치(line 129)가 올바르다.

---

### WR-03: WebSocket 엔드포인트 — 다중 클라이언트 시 단일 소비자 경합

**File:** `mutrade/admin/app.py:175-186`
**Issue:** `wait_for_change()`는 `asyncio.Queue.get()`을 직접 await한다. 두 개의 WebSocket 클라이언트가 동시에 연결되면 두 코루틴이 같은 Queue를 경합하여 한 클라이언트만 업데이트를 받는다. Queue에서 꺼낸 스냅샷이 다른 클라이언트로 전달되지 않는다.

**Fix:** 단기적으로 서버를 단일 클라이언트 전용으로 문서화하거나, fan-out 패턴(연결 시 Queue를 새로 생성하거나 pub/sub 방식)으로 전환한다:
```python
# 각 WebSocket 연결에 독립적인 Queue 할당 방식 고려
# 또는 BotStateHub에 subscribe()/unsubscribe() 메서드 추가
```
개인용 봇이라면 단일 클라이언트 제약을 주석으로 명시하는 것으로 충분할 수 있다.

---

### WR-04: `_put_snapshot` — `assert` 문 사용

**File:** `mutrade/admin/hub.py:100`
**Issue:** `assert self._change_queue is not None`는 Python 최적화 모드(`-O` 플래그)에서 제거된다. `_put_snapshot`은 `call_soon_threadsafe` 경유로만 호출되므로 실제로 None일 가능성은 매우 낮지만, 프로덕션 코드의 불변식은 `assert` 대신 명시적 예외로 보호해야 한다.

**Fix:**
```python
def _put_snapshot(self, data: dict) -> None:
    if self._change_queue is None:
        return  # 루프 연결 전 호출 — 무시
    # ...
```

---

## Info

### IN-01: `index.html` — `ws://` 하드코딩으로 HTTPS 환경 미지원

**File:** `mutrade/admin/static/index.html:285`
**Issue:** `new WebSocket('ws://' + location.host + '/ws')`는 HTTPS 환경에서 Mixed Content 오류를 유발한다. HTTPS로 서빙될 경우 `wss://`가 필요하다.

**Fix:**
```javascript
var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
ws = new WebSocket(proto + location.host + '/ws');
```

---

### IN-02: `push_snapshot` — `_is_running` 읽기가 lock 밖에서 발생

**File:** `mutrade/admin/hub.py:73-78`
**Issue:** `meta` 딕셔너리 생성(line 73-78)에서 `self._is_running`을 읽는 시점은 lock 획득 전이다. `set_running()`이 동시에 호출되면 직전 값이 스냅샷에 기록될 수 있다. 경합 윈도우는 매우 작지만 `_is_running` 읽기와 `_snapshot` 쓰기가 원자적이지 않다.

**Fix:** `meta` 생성을 lock 블록 내부로 이동:
```python
with self._lock:
    meta = {
        "_meta": {
            "is_running": self._is_running,
            "dry_run": dry_run,
        }
    }
    self._snapshot = {**meta, **serialized}
```

---

### IN-03: `test_app_routes.py` — `TestGetIndex.test_get_root_returns_html` 불완전한 테스트

**File:** `tests/test_app_routes.py:68-92`
**Issue:** 테스트 내에 `patched_create_app`을 정의하지만 실제로 사용하지 않는다(line 79-86이 dead code). 실제 STATIC_DIR 패치 없이 `create_app(hub)`를 직접 호출하고 있어, 테스트가 라우트 등록만 확인하고 응답 본문 검증은 하지 않는다. 주석(line 87-90)이 이를 인정하지만 dead code가 혼란을 준다.

**Fix:** 미사용 `patched_create_app` 함수와 관련 주석을 제거하고, `app` fixture를 사용하여 실제 HTML 응답을 검증하는 어서션을 추가한다.

---

_Reviewed: 2026-04-18T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
