# Phase 3: Order Execution - Research

**Researched:** 2026-04-07
**Domain:** PyKis 매도 주문 API, 중복 주문 방지 패턴, 체결 확인
**Confidence:** HIGH

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | 매도 신호 발생 시 해당 종목을 시장가로 즉시 매도 | PyKis `account.sell(market, symbol, price=None)` — price=None이 시장가 |
| EXEC-02 | 매도 가능 수량(ord_psbl_qty)을 조회하여 매도 수량으로 사용 | `KisBalanceStock.orderable` 필드가 `ord_psbl_qty` 를 직접 래핑 |
| EXEC-03 | 동일 종목에 대해 SELL_PENDING 플래그로 중복 주문 방지 | 인-메모리 set으로 구현; 폴링 루프와 같은 스레드이므로 thread-safe |
| EXEC-04 | 주문 제출 후 체결 여부를 확인 | `account.daily_orders()` 반환 `KisDailyOrder.executed_quantity` / `pending_quantity` |
</phase_requirements>

---

## Summary

Phase 3은 Phase 2에서 생성된 `SellSignal`을 실제 KIS 매도 주문으로 전환하는 단계다. 핵심 과제는 세 가지다: (1) PyKis `account` 스코프를 통한 시장가 매도 주문 제출, (2) 동일 종목 중복 주문 방지를 위한 `SELL_PENDING` 플래그 관리, (3) 주문 후 체결 확인을 위한 `daily_orders()` 폴링.

PyKis 2.1.6에서 매도 주문의 핵심 경로는 `kis.account().sell('KRX', symbol, price=None, qty=qty)` 이며, 매도 가능 수량은 `kis.account().balance('KR').stock(symbol).orderable` 속성에서 직접 읽는다. 이 값은 KIS REST 응답의 `ord_psbl_qty` 필드를 래핑한 것으로, EXEC-02 요구사항과 정확히 일치한다.

모의투자(paper trading) 환경에서의 주요 제약: PyKis 소스 코드(`ORDER_CONDITION_MAP`)에서 확인한 바로는 `시간외단일가`, `IOC/FOK`, 장전/장후 주문은 모의투자 미지원이다. 시장 중 시장가(`price=None`) 매도는 실전·모의 모두 지원된다. `settings.kis_mock=True` 이면 `kis.virtual=True` 이므로 PyKis가 자동으로 모의투자 엔드포인트를 사용한다.

**Primary recommendation:** `OrderExecutor` 클래스를 `mutrade/executor/` 패키지에 새로 만들고, `SellSignal`을 받아 수량 조회→주문→체결 확인의 3단계를 처리하도록 설계하라. `SELL_PENDING` 플래그는 `OrderExecutor` 내부 `set[str]`로 관리한다.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-kis` | 2.1.6 (pyproject.toml 고정) | KIS 매도 주문, 잔고/체결 조회 | 프로젝트에 이미 사용 중; `account().sell()` API 확인됨 |
| `loguru` | 0.7.3 | 주문 이벤트 로깅 | 이미 전체 코드베이스에 사용 중 |
| `pytest` + `pytest-mock` | dev 의존성 | 주문 실행기 단위 테스트 | Phase 2와 동일 패턴 |

### No New Dependencies Required
Phase 3는 pyproject.toml에 이미 있는 라이브러리만으로 구현 가능하다. 새 패키지 설치 없음.

---

## Architecture Patterns

### Recommended Project Structure
```
mutrade/
├── executor/
│   ├── __init__.py
│   └── order_executor.py   # OrderExecutor 클래스
├── engine/
│   └── (기존 — 변경 없음)
├── monitor/
│   └── scheduler.py        # execute_signals() 호출 추가
└── main.py                 # OrderExecutor 초기화 추가
```

### Pattern 1: 시장가 매도 주문 (PyKis account scope)

**What:** `kis.account()` 스코프를 통해 KRX 시장가 매도 주문 제출
**When to use:** `SellSignal` 수신 후 dry_run=False일 때

```python
# Source: /opt/homebrew/lib/python3.11/site-packages/pykis/adapter/account/order.py
# Source: /opt/homebrew/lib/python3.11/site-packages/pykis/adapter/account_product/order.py

# 방법 1: account 스코프에서 직접 호출 (권장)
acc = kis.account()
order = acc.sell(
    market="KRX",
    symbol="005930",
    price=None,   # price=None → 시장가
    qty=qty,      # Decimal 또는 int
)
# order: KisOrder — order.branch, order.number 로 주문번호 식별

# 방법 2: account product(stock scope)에서 호출
stock_scope = kis.stock("005930")
order = stock_scope.sell(price=None, qty=qty)
```

### Pattern 2: 매도 가능 수량 조회 (ord_psbl_qty)

**What:** KisBalance에서 특정 종목의 매도 가능 수량 직접 읽기
**When to use:** 주문 제출 직전 실제 수량 확인

```python
# Source: /opt/homebrew/lib/python3.11/site-packages/pykis/api/account/balance.py
# KisBalanceStockDomesticResponse.orderable = KisDecimal["ord_psbl_qty"]

acc = kis.account()
balance = acc.balance("KR")          # 국내 잔고 조회
stock = balance.stock("005930")      # KisBalanceStock or None
if stock is None:
    # 보유 없음 — 주문 불가
    return
qty = stock.orderable               # Decimal — KIS ord_psbl_qty
```

### Pattern 3: SELL_PENDING 플래그 (중복 주문 방지, EXEC-03)

**What:** 동일 종목에 대한 중복 매도 주문 방지
**When to use:** 항상 — scheduler 폴링 루프와 동일 스레드에서 실행

```python
# mutrade/executor/order_executor.py

class OrderExecutor:
    def __init__(self, kis: PyKis, dry_run: bool = False):
        self._kis = kis
        self._dry_run = dry_run
        self._pending: set[str] = set()  # SELL_PENDING 플래그

    def execute(self, signal: SellSignal) -> None:
        if signal.code in self._pending:
            logger.warning(
                "SELL_PENDING 중복 방지: {} — 이미 주문 진행 중", signal.code
            )
            return

        self._pending.add(signal.code)
        try:
            self._submit_order(signal)
        except Exception as e:
            logger.error("주문 실패 {}: {}", signal.code, e)
            self._pending.discard(signal.code)  # 실패 시 플래그 해제
```

**주의:** APScheduler `BlockingScheduler`는 단일 스레드이므로 `set` 자료구조로 충분히 thread-safe하다. 별도 Lock 불필요.

### Pattern 4: 체결 확인 (EXEC-04)

**What:** 주문 제출 후 체결 여부를 `daily_orders()`로 폴링 확인
**When to use:** `account.sell()` 성공 후 fill confirmation 단계

```python
# Source: /opt/homebrew/lib/python3.11/site-packages/pykis/api/account/daily_order.py
# KisDailyOrder.executed_quantity = KisDecimal["tot_ccld_qty"]
# KisDailyOrder.pending_quantity  = 미체결수량

import time
from pykis import KisAPIError

def confirm_fill(
    self,
    order: KisOrder,
    symbol: str,
    max_attempts: int = 5,
    interval_sec: float = 3.0,
) -> None:
    acc = self._kis.account()
    for attempt in range(max_attempts):
        try:
            daily = acc.daily_orders()
            record = daily.order(order)   # KisOrder 또는 주문번호 str
            if record is not None:
                logger.info(
                    "체결 확인 {}: 체결수량={} 미체결수량={} 체결단가={}",
                    symbol,
                    record.executed_quantity,
                    record.pending_quantity,
                    record.price,
                )
                self._pending.discard(symbol)
                return
        except KisAPIError as e:
            logger.warning("체결 확인 API 오류 (attempt {}): {}", attempt + 1, e)
        time.sleep(interval_sec)

    # max_attempts 초과 — 로그 후 플래그 해제
    logger.warning("체결 확인 시간 초과: {} — SELL_PENDING 해제", symbol)
    self._pending.discard(symbol)
```

### Pattern 5: DRY_RUN 모드에서 주문 실행 차단

**What:** `signal.dry_run=True`이면 실제 주문 없이 로그만 출력
**When to use:** KIS_MOCK=True 또는 DRY_RUN=True 환경

```python
def _submit_order(self, signal: SellSignal) -> None:
    if signal.dry_run:
        logger.info(
            "[DRY-RUN] 매도 주문 시뮬레이션: {} ({}) qty=?",
            signal.code, signal.name,
        )
        self._pending.discard(signal.code)
        return

    # 실제 주문 경로
    acc = self._kis.account()
    balance = acc.balance("KR")
    stock = balance.stock(signal.code)
    if stock is None or stock.orderable <= 0:
        logger.warning("매도 불가 {}: 잔고 없음", signal.code)
        self._pending.discard(signal.code)
        return

    qty = stock.orderable
    order = acc.sell(market="KRX", symbol=signal.code, price=None, qty=qty)
    logger.warning(
        "[LIVE] 매도 주문 제출: {} ({}) qty={} 주문번호={}",
        signal.code, signal.name, qty, order.number,
    )
    self.confirm_fill(order, signal.code)
```

### Anti-Patterns to Avoid

- **price=0을 시장가로 오해하기:** PyKis에서 시장가는 `price=None`. `price=0`은 `ValueError`를 발생시킨다 (`ensure_price` 검증).
- **OrderExecutor 없이 scheduler에 직접 주문 코드 작성:** 중복 방지 로직이 분산되어 테스트 불가.
- **`kis.stock(code).sell()` 만 사용:** account scope 없이 stock scope에서 매도 시 어떤 계좌를 사용할지 명시적이지 않음. `kis.account().sell(market, symbol)` 패턴이 더 명확하다.
- **체결 확인 없이 SELL_PENDING 영구 보유:** 주문 후 확인 없으면 다음 매도 신호에도 영구 차단됨.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| 매도 가능 수량 계산 | 잔고에서 직접 수량 계산 | `balance.stock(code).orderable` | `ord_psbl_qty` 필드 직접 래핑 — T+2 결제 등 복잡한 계산을 KIS 서버가 처리 |
| 시장가 주문 조건 코드 | `tr_id`, 주문구분코드 직접 구성 | `account.sell(price=None)` | PyKis `ORDER_CONDITION_MAP`이 올바른 KIS 코드 "01"(시장가)을 자동 선택 |
| 체결 여부 폴링 루프 자체 구조 | 커스텀 폴링 + 타임아웃 | `daily_orders().order(order_num)` | PyKis가 `KisDailyOrder` 스키마 파싱 처리; `tot_ccld_qty` 필드 직접 제공 |
| OAuth 토큰 재발급 | 토큰 만료 감지 코드 | `keep_token=True` (이미 설정) | Phase 1에서 해결됨; 재구현 불필요 |

**Key insight:** PyKis `account` 스코프는 KIS REST API의 복잡한 파라미터 매핑을 완전히 추상화한다. 주문 구분 코드, 시장 코드, 모의/실전 엔드포인트 전환 등은 모두 라이브러리가 처리한다.

---

## Common Pitfalls

### Pitfall 1: 모의투자 환경에서 실전 계좌 API 호출
**What goes wrong:** `KIS_MOCK=True`인데 `kis.account()` 대신 직접 REST를 호출하거나, 실전 appkey로 KIS 모의투자 엔드포인트를 접근하면 인증 오류.
**Why it happens:** PyKis는 `virtual_appkey` 존재 여부로 모의/실전 분기. `kis.virtual=True`이면 자동으로 `https://openapivts.koreainvestment.com`을 사용.
**How to avoid:** 항상 `kis.account().sell()` 경로 사용. 직접 HTTP 호출 금지.
**Warning signs:** `KisHTTPError` 401 또는 `rt_cd != "0"` with `msg_cd="EGW00123"`.

### Pitfall 2: price=None 시 qty를 반드시 지정
**What goes wrong:** `account.sell(market="KRX", symbol=code, price=None)` — qty 생략 시 PyKis가 잔고 전량을 조회해 자동 결정 시도하지만, 이 동작이 항상 `ord_psbl_qty`를 사용한다는 보장이 명시적이지 않음.
**How to avoid:** EXEC-02 요구사항 충족을 위해 명시적으로 `balance.stock(code).orderable`를 읽어 `qty=orderable`로 전달한다.

### Pitfall 3: SELL_PENDING 해제 누락
**What goes wrong:** 주문 성공 후 체결 확인 중 예외 발생 → `finally` 없이 `_pending` 미해제 → 해당 종목 영구 차단.
**How to avoid:** 체결 확인 함수는 성공/실패/타임아웃 모든 경로에서 `_pending.discard(code)` 호출. `try/finally` 구조 사용.

### Pitfall 4: daily_orders()의 당일 범위 제한
**What goes wrong:** `daily_orders()`는 당일 체결 내역만 반환. 주문 직후 즉시 조회하면 결과에 나타나기까지 수초 지연 가능.
**How to avoid:** `max_attempts=5, interval_sec=3.0` 기본값으로 폴링. 체결 미확인을 오류가 아닌 경고로 처리하고 SELL_PENDING은 해제.

### Pitfall 5: 모의투자 일부 주문조건 미지원
**What goes wrong:** PyKis `ORDER_CONDITION_MAP`에서 모의투자는 `시간외단일가(07)`, `IOC/FOK(11-16)` 미지원으로 명시. 이 조건으로 주문 시 `ValueError: 모의투자는 해당 주문조건을 지원하지 않습니다.`
**How to avoid:** 시장가(`price=None, condition=None`) 만 사용하면 실전/모의 모두 지원됨.

---

## Code Examples

### 시장가 매도 전체 흐름

```python
# Source: pykis/adapter/account/order.py, pykis/api/account/balance.py

from pykis import PyKis, KisAPIError
from mutrade.engine.models import SellSignal

def execute_sell(kis: PyKis, signal: SellSignal) -> None:
    """시장가 매도 주문 제출 + 체결 로그."""
    acc = kis.account()

    # 1. 매도 가능 수량 조회 (EXEC-02)
    balance = acc.balance("KR")
    stock = balance.stock(signal.code)
    if stock is None or stock.orderable <= 0:
        logger.warning("매도 불가 {}: orderable=0 또는 잔고 없음", signal.code)
        return

    qty = stock.orderable  # KisDecimal["ord_psbl_qty"]

    # 2. 시장가 매도 주문 (EXEC-01)
    order = acc.sell(
        market="KRX",
        symbol=signal.code,
        price=None,   # 시장가
        qty=qty,
    )
    logger.warning(
        "[LIVE] 매도 주문 제출: {} qty={} branch={} number={}",
        signal.code, qty, order.branch, order.number,
    )
```

### 체결 확인 폴링

```python
# Source: pykis/api/account/daily_order.py
# KisDailyOrder: executed_quantity=tot_ccld_qty, pending_quantity=미체결수량

def confirm_fill(acc, order, symbol: str, attempts: int = 5) -> None:
    import time
    for i in range(attempts):
        time.sleep(3)
        try:
            daily = acc.daily_orders()
            rec = daily.order(order)
            if rec:
                logger.info(
                    "체결 확인 {}: filled={} pending={} price={}",
                    symbol, rec.executed_quantity, rec.pending_quantity, rec.price,
                )
                return
        except KisAPIError as e:
            logger.warning("체결 확인 오류 attempt {}: {}", i + 1, e)
    logger.warning("체결 확인 타임아웃: {}", symbol)
```

### scheduler.py 통합 패턴

```python
# mutrade/monitor/scheduler.py 에서 signals 처리 부분 수정

for sig in signals:
    if sig.dry_run:
        logger.warning("[DRY-RUN] SELL SIGNAL: {} ...", sig.code)
    else:
        executor.execute(sig)   # OrderExecutor.execute(signal)
```

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (dev dependency, pyproject.toml) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` — testpaths=["tests"] |
| Quick run command | `pytest tests/test_order_executor.py -x` |
| Full suite command | `pytest tests/ -x` |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| EXEC-01 | 시장가 매도 주문 제출 시 `account().sell(price=None, qty=qty)` 호출됨 | unit (mock) | `pytest tests/test_order_executor.py::TestOrderExecutor::test_market_sell_called -x` | Wave 0 |
| EXEC-02 | `balance.stock(code).orderable` 값이 qty로 사용됨 | unit (mock) | `pytest tests/test_order_executor.py::TestOrderExecutor::test_orderable_qty_used -x` | Wave 0 |
| EXEC-03 | 동일 종목 두 번째 신호에서 주문 호출 없음 | unit (mock) | `pytest tests/test_order_executor.py::TestOrderExecutor::test_sell_pending_blocks_duplicate -x` | Wave 0 |
| EXEC-04 | 주문 후 `daily_orders().order()` 호출되고 체결 결과 로그 | unit (mock) | `pytest tests/test_order_executor.py::TestOrderExecutor::test_fill_confirmed -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `pytest tests/test_order_executor.py -x`
- **Per wave merge:** `pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/test_order_executor.py` — EXEC-01~04 커버리지 (Phase 2 `test_engine.py` 패턴 참고)
- [ ] `mutrade/executor/__init__.py` — 패키지 파일

*(기존 테스트 인프라는 정상 작동; pytest, pytest-mock 이미 설치됨)*

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python 3.11 | 런타임 | system homebrew | 3.11.x | — |
| python-kis 2.1.6 | 주문 API | homebrew site-packages | 2.1.6 | — |
| KIS 모의투자 계좌 자격증명 | EXEC-04 종단 검증 | 사용자 환경 변수 | — | 단위 테스트에서 mock으로 대체 |

**Missing dependencies with no fallback:**
- KIS 모의투자 자격증명(`KIS_VIRTUAL_*`)이 없으면 실제 모의투자 환경 테스트 불가. 단위 테스트(mock)는 자격증명 없이도 가능.

---

## Open Questions

1. **`daily_orders()` 모의투자 지원 여부**
   - What we know: PyKis 소스에서 `domestic_daily_orders`는 국내주식 일별주문체결 조회 엔드포인트를 호출함
   - What's unclear: KIS 모의투자 API가 일별주문체결 조회를 지원하는지 명시적으로 확인하지 못함
   - Recommendation: 모의투자 테스트 시 `daily_orders()` 호출 후 오류 발생하면 체결 확인을 skip하고 경고 로그만 출력하는 폴백을 구현하라

2. **`acc.balance("KR")` vs `acc.balance()`**
   - What we know: PyKis `balance()` 인자로 `COUNTRY_TYPE`("KR") 또는 생략 가능
   - What's unclear: 생략 시 기본값이 국내인지 전체 조회인지 미확인
   - Recommendation: 명시적으로 `"KR"` 전달

---

## Sources

### Primary (HIGH confidence)
- `/opt/homebrew/lib/python3.11/site-packages/pykis/adapter/account_product/order.py` — sell(), buy(), orderable_amount() 프로토콜 및 docstring
- `/opt/homebrew/lib/python3.11/site-packages/pykis/adapter/account/order.py` — KisOrderableAccount.sell() 시그니처
- `/opt/homebrew/lib/python3.11/site-packages/pykis/api/account/balance.py` — `KisBalanceStock.orderable = KisDecimal["ord_psbl_qty"]` 확인
- `/opt/homebrew/lib/python3.11/site-packages/pykis/api/account/daily_order.py` — `KisDailyOrder.executed_quantity = KisDecimal["tot_ccld_qty"]` 확인
- `/opt/homebrew/lib/python3.11/site-packages/pykis/api/account/order.py` — `ORDER_CONDITION_MAP` 모의투자 미지원 조건 확인

### Secondary (MEDIUM confidence)
- `/opt/homebrew/lib/python3.11/site-packages/pykis/scope/account.py` — `kis.account()` 팩토리 패턴 확인

---

## Metadata

**Confidence breakdown:**
- Standard Stack: HIGH — pyproject.toml 고정 버전, 설치된 라이브러리 소스 직접 확인
- Architecture (OrderExecutor 설계): HIGH — PyKis API 시그니처 검증됨; 기존 코드베이스 패턴과 일치
- PyKis sell() API: HIGH — 소스 코드 직접 확인
- 체결 확인 daily_orders(): MEDIUM — 소스 확인됨, 모의투자 지원 여부는 런타임 검증 필요
- SELL_PENDING 패턴: HIGH — APScheduler BlockingScheduler 단일 스레드 특성 기반, thread-safe 보장

**Research date:** 2026-04-07
**Valid until:** 2026-07-07 (python-kis 2.1.6 고정이므로 안정적)
