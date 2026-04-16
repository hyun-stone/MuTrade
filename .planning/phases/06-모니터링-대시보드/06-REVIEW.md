---
phase: 06-모니터링-대시보드
reviewed: 2026-04-16T00:00:00Z
depth: standard
files_reviewed: 9
files_reviewed_list:
  - mutrade/admin/hub.py
  - mutrade/executor/order_executor.py
  - mutrade/monitor/scheduler.py
  - mutrade/admin/app.py
  - mutrade/admin/static/index.html
  - tests/test_hub.py
  - tests/test_order_executor.py
  - tests/test_scheduler.py
  - tests/test_app_routes.py
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 6: 코드 리뷰 보고서

**검토 일시:** 2026-04-16
**깊이:** standard
**검토 파일 수:** 9
**상태:** issues_found

## 요약

Phase 6 모니터링 대시보드 구현을 검토했다. 전체적으로 설계가 탄탄하며 스레드 안전성(RLock, threading.Event), asyncio 브릿지(call_soon_threadsafe), XSS 방어(sanitizeCode) 등 핵심 패턴이 올바르게 적용되어 있다. Critical 수준의 보안 취약점은 없다. 다만 스레드 안전성 누락, 엣지 케이스 미처리, 테스트 신뢰성 관련 Warning 4건과 Info 5건이 발견되었다.

---

## Warnings

### WR-01: `OrderExecutor._pending` set에 대한 스레드 안전성 부재

**파일:** `mutrade/executor/order_executor.py:41`

**이슈:** `self._pending`은 일반 `set[str]`로 선언되어 있다. `execute()` 메서드는 APScheduler 백그라운드 스레드에서 호출되고, `pending_codes()`는 FastAPI의 asyncio 이벤트 루프 스레드에서 `push_snapshot()` 경유로 간접 호출된다. Python GIL이 단순 set 연산의 원자성을 어느 정도 보장하지만, `add/discard/in` 연산이 연속으로 실행되는 `execute()` 흐름(58~65행 체크-then-추가)은 두 스레드가 동시 접근할 경우 TOCTOU(time-of-check/time-of-use) 경합이 발생할 수 있다.

**수정:**
```python
import threading

class OrderExecutor:
    def __init__(self, kis, dry_run=False, notifier=None):
        self._kis = kis
        self._dry_run = dry_run
        self._pending: set[str] = set()
        self._pending_lock = threading.Lock()
        self._notifier = notifier

    def execute(self, signal: SellSignal) -> None:
        if signal.dry_run or self._dry_run:
            ...
            return

        with self._pending_lock:
            if signal.code in self._pending:
                logger.warning("SELL_PENDING 중복 방지: ...")
                return
            self._pending.add(signal.code)

        try:
            self._submit_order(signal)
        except Exception as e:
            logger.error("주문 실패 {}: {}", signal.code, e)
            with self._pending_lock:
                self._pending.discard(signal.code)

    def pending_codes(self) -> frozenset:
        with self._pending_lock:
            return frozenset(self._pending)
```

---

### WR-02: `BotStateHub.attach_loop()` 재호출 시 기존 Queue 유실

**파일:** `mutrade/admin/hub.py:25-29`

**이슈:** `attach_loop()`가 두 번 이상 호출되면(예: FastAPI 앱 재시작, 테스트 환경에서 여러 번 호출) `_change_queue`가 새 `asyncio.Queue`로 교체된다. 기존 큐를 `await`하고 있는 `wait_for_change()` 코루틴이 있다면 해당 코루틴은 영원히 깨어나지 못하고 WebSocket 연결이 멈춘다.

**수정:**
```python
def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
    with self._lock:
        if self._loop is not None:
            logger.warning(
                "attach_loop() 재호출 감지 — 기존 루프/큐를 교체합니다."
            )
        self._loop = loop
        self._change_queue = asyncio.Queue(maxsize=1)
```
경고 로그를 추가하면 운영 중 재호출 여부를 인지할 수 있다. 혹은 `if self._loop is None:` 조건으로 최초 1회만 초기화하도록 제한하는 방법도 있다.

---

### WR-03: `scheduler.py` — `hub.set_running(True)` 위치가 루프 내부에 있어 매 폴링마다 반복 호출

**파일:** `mutrade/monitor/scheduler.py:117`

**이슈:** `hub.set_running(True)`가 while 루프 내부 `if hub is not None:` 블록에 있다. 이 자체는 기능 오류가 아니지만, 의도는 "세션 시작 시 1회 설정"이다. 매 폴링 주기(기본 3초)마다 불필요하게 lock 획득 후 동일 값 쓰기가 발생한다. 더 큰 문제는, `hub.set_running(True)` 호출이 `poll_prices()` 및 `engine.tick()` 이후에 위치하므로, 세션이 시작됐음에도 **첫 번째 폴링 완료 전까지** `/health` API가 `bot_running: false`를 반환한다.

**수정:**
```python
# run_session() 함수 내 루프 진입 직전에 set_running(True) 이동
if hub is not None:
    hub.set_running(True)

while True:
    if hub is not None and hub.is_stop_requested():
        ...
        break
    ...
    prices = poll_prices(kis, config)
    signals = engine.tick(prices)
    ...
    if hub is not None:
        hub.push_snapshot(engine.states, prices, executor.pending_codes())
        # set_running(True) 제거 — 이미 루프 진입 전 호출됨
    ...
```

---

### WR-04: `index.html` — `innerHTML`을 통한 부분적 XSS 위험 (status badge 텍스트)

**파일:** `mutrade/admin/static/index.html:154-156`

**이슈:** `sanitizeCode()`로 종목 코드는 방어하고 있으나, `fmtPrice()`, `fmtDrop()`, `getStatusText()` 반환값은 `innerHTML` 문자열 연결에 직접 삽입된다. `fmtPrice()`와 `fmtDrop()`은 서버에서 받은 숫자 값을 포맷하므로 현재는 문제가 없다. 그러나 `getStatusText()`가 반환하는 문자열('매도 대기', '워밍업', '모니터링 중')은 하드코딩되어 있어 안전하다. 위험은 서버가 예상치 못한 타입(문자열 코드 등)을 `current_price`나 `peak_price`로 보낼 경우 `toLocaleString()`이 그대로 출력될 수 있다는 점이다.

**수정:** `innerHTML` 조립 대신 DOM 조작을 사용하거나, 최소한 숫자 필드를 명시적으로 `Number()`로 강제 변환한다:

```javascript
function fmtPrice(v) {
  const n = Number(v);
  if (!isFinite(n) || n === 0) return '—';
  return n.toLocaleString('ko-KR') + '원';
}

function fmtDrop(v, warm) {
  if (!warm) return '—';
  const n = Number(v);
  if (!isFinite(n)) return '—';
  return n.toFixed(2) + '%';
}
```

---

## Info

### IN-01: `BotStateHub._put_snapshot()` — `assert` 문 사용

**파일:** `mutrade/admin/hub.py:91`

**이슈:** `assert self._change_queue is not None`은 Python 최적화 모드(`python -O`)에서 제거된다. 이 assert는 내부 불변식 검증용이지만, 운영 환경에서 `-O` 플래그를 사용하면 방어 코드가 사라지고 `AttributeError`나 `NoneType` 오류로 이어진다.

**수정:**
```python
def _put_snapshot(self, data: dict) -> None:
    if self._change_queue is None:
        return  # attach_loop 미호출 시 무시
    ...
```

---

### IN-02: `order_executor.py` — `_confirm_fill()` 내 `time.sleep()` 블로킹

**파일:** `mutrade/executor/order_executor.py:141-142`

**이슈:** `_confirm_fill()`은 APScheduler 스레드에서 실행된다. 기본값 기준 최대 5 × 3.0 = 15초를 blocking sleep하는 동안 해당 APScheduler 스레드가 점유된다. APScheduler의 스레드 풀 크기 기본값은 10이므로 단일 종목에서는 문제가 없지만, 여러 종목이 동시에 매도 신호를 발생시킬 경우 스레드 풀 고갈 가능성이 있다. 현재 v1 규모에서는 허용 가능한 수준이지만, Info로 기록한다.

**수정:** 별도 스레드로 체결 확인을 오프로드하거나, 차후 규모 증가 시 `concurrent.futures.ThreadPoolExecutor`를 고려한다.

---

### IN-03: `scheduler.py` — `hub.set_running(False)` 는 stop_requested 경로에서만 호출됨

**파일:** `mutrade/monitor/scheduler.py:128-129`

**이슈:** `hub.set_running(False)`는 루프 종료 후 `if hub is not None:` 블록에서 호출된다. 그런데 `hub.is_stop_requested()`가 True일 때 `hub.clear_stop()`을 호출하고 `break`하면 루프를 빠져나와 `set_running(False)`까지 도달한다. 이는 올바르다. 다만 WR-03에서 제안한 대로 루프 진입 전 `set_running(True)`로 옮기면, 현재 코드의 `set_running(False)` 호출 위치도 함께 검토해야 한다 — `is_krx_trading_day()` 조기 반환 경로에서는 `set_running(True)`가 한 번도 호출되지 않으므로 `set_running(False)`도 불필요하다. WR-03 수정 시 비거래일 경로에서의 `set_running(False)` 중복 호출을 피하도록 조건을 추가할 것.

**수정:** WR-03 패치와 함께 처리.

---

### IN-04: `test_hub.py` — `TestBotStateHub` 클래스에 `unittest.TestCase` 미상속

**파일:** `tests/test_hub.py:14`

**이슈:** `TestBotStateHub`와 `TestBotStateHubPhase6`가 `unittest.TestCase`를 상속하지 않는 plain class이다. pytest는 이를 자동으로 수집하므로 기능상 문제없지만, `unittest.mock.patch`를 컨텍스트 매니저 대신 데코레이터로 사용하거나 `addCleanup`을 사용할 경우 `TestCase` 메서드가 없어 오류가 발생할 수 있다. 또한 테스트 파일 상단에 `import unittest`가 있으나 사용되지 않는 import이다.

**수정:**
```python
# unittest import 제거 (사용되지 않음)
# import unittest  # 삭제

class TestBotStateHub:
    ...
```

---

### IN-05: `index.html` — WebSocket URL이 `ws://`로 하드코딩되어 HTTPS 환경에서 실패

**파일:** `mutrade/admin/static/index.html:163`

**이슈:** `new WebSocket('ws://' + location.host + '/ws')`는 HTTP 환경에서만 동작한다. HTTPS로 서빙될 경우(리버스 프록시, ngrok, 미래 TLS 적용 등) 브라우저가 Mixed Content 정책으로 `ws://` 연결을 차단한다.

**수정:**
```javascript
function connect() {
  var protocol = location.protocol === 'https:' ? 'wss://' : 'ws://';
  ws = new WebSocket(protocol + location.host + '/ws');
  ...
}
```

---

_검토 일시: 2026-04-16_
_검토자: Claude (gsd-code-reviewer)_
_깊이: standard_
