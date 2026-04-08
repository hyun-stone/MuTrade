---
phase: 03-order-execution
verified: 2026-04-07T08:00:00Z
status: human_needed
score: 9/10 must-haves verified
human_verification:
  - test: "KIS 모의투자(모의투자) 환경에서 DRY_RUN=False로 봇 실행, 실제 매도 신호 발생 시 KIS 주문 ID가 로그에 출력되는지 확인"
    expected: "[LIVE] 매도 주문 제출: {종목코드} ({종목명}) qty={수량} 주문번호={주문번호} 로그 출력 + 체결 확인 로그 출력"
    why_human: "실제 KIS 모의투자 자격증명 필요. paper trading tr_id 값으로 acc.sell() 호출이 실제 KIS API를 통해 성공하는지, daily_orders().order()가 모의투자 환경에서 체결 레코드를 반환하는지는 런타임 검증만 가능."
---

# Phase 3: Order Execution Verification Report

**Phase Goal:** The bot submits a real market-sell order when a sell signal is triggered, using the correct sellable quantity, without ever submitting duplicate orders — validated in KIS paper trading (모의투자) before production credentials are used.
**Verified:** 2026-04-07T08:00:00Z
**Status:** human_needed
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths

#### 03-01-PLAN Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 1  | OrderExecutor.execute(signal)가 kis.account().sell(market='KRX', symbol=code, price=None, qty=orderable)를 호출한다 | VERIFIED | `order_executor.py:79-84` — acc.sell(market="KRX", symbol=signal.code, price=None, qty=qty). test_market_sell_called PASS. |
| 2  | 매도 수량은 balance.stock(code).orderable 값을 그대로 사용한다 | VERIFIED | `order_executor.py:67-78` — acc.balance("KR").stock(signal.code).orderable 조회 후 qty에 할당. test_orderable_qty_used(orderable=25) PASS. |
| 3  | 동일 종목에 대해 두 번째 execute 호출은 sell()을 호출하지 않는다 (SELL_PENDING) | VERIFIED | `order_executor.py:46-51` — signal.code in self._pending 체크. test_sell_pending_blocks_duplicate PASS. |
| 4  | 주문 성공 후 daily_orders().order(order)로 체결 확인을 시도한다 | VERIFIED | `order_executor.py:116-117` — acc.daily_orders().order(order) 호출. test_fill_confirmed PASS. |
| 5  | dry_run=True인 SellSignal은 실제 주문 없이 로그만 출력한다 | VERIFIED | `order_executor.py:38-44` — signal.dry_run 또는 self._dry_run 이면 즉시 return. test_dry_run_skips_sell + test_executor_level_dry_run PASS. |
| 6  | 주문 실패 시 SELL_PENDING 플래그가 해제된다 | VERIFIED | `order_executor.py:57-58` — except Exception: self._pending.discard(signal.code). test_sell_failure_clears_pending PASS. |

#### 03-02-PLAN Truths

| #  | Truth | Status | Evidence |
|----|-------|--------|----------|
| 7  | scheduler 폴링 루프에서 SellSignal 발생 시 dry_run=False이면 executor.execute(signal)이 호출된다 | VERIFIED | `scheduler.py:99-100` — if not sig.dry_run: executor.execute(sig). test_live_signal_calls_executor PASS. |
| 8  | dry_run=True이면 기존처럼 로그만 출력하고 executor.execute를 호출하지 않는다 | VERIFIED | `scheduler.py:91-100` — 로그는 항상 출력, executor.execute는 dry_run=False 조건 내에만 위치. test_dry_run_signal_skips_executor PASS. |
| 9  | main.py에서 OrderExecutor가 초기화되고 scheduler에 전달된다 | VERIFIED | `main.py:83-90` — OrderExecutor(kis=kis, dry_run=settings.dry_run) 초기화 후 start_scheduler(kis, config, engine, executor) 전달. |
| 10 | KIS 모의투자(모의투자) end-to-end 검증 | ? NEEDS HUMAN | 런타임에 KIS 모의투자 자격증명이 있어야 검증 가능. |

**Score:** 9/10 truths verified (1 needs human)

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `mutrade/executor/__init__.py` | 패키지 마커 | VERIFIED | 파일 존재, 빈 파일(패키지 마커로 정상). |
| `mutrade/executor/order_executor.py` | OrderExecutor 클래스 — execute(), _confirm_fill() | VERIFIED | 140줄, class OrderExecutor 정의, execute / _submit_order / _confirm_fill 메서드 모두 실질 구현. |
| `tests/test_order_executor.py` | EXEC-01~04 단위 테스트 (min 80줄) | VERIFIED | 211줄, 11개 테스트 함수, 전체 통과. |
| `mutrade/monitor/scheduler.py` | executor.execute(signal) 호출 경로 | VERIFIED | executor.execute(sig) 가 if not sig.dry_run: 블록 내에 위치. |
| `mutrade/main.py` | OrderExecutor 초기화 및 scheduler 전달 | VERIFIED | OrderExecutor(kis=kis, dry_run=settings.dry_run) + start_scheduler(..., executor). |
| `tests/test_scheduler.py` | executor 통합 테스트 (2 신규 테스트) | VERIFIED | test_live_signal_calls_executor + test_dry_run_signal_skips_executor 모두 존재 및 통과. |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `mutrade/executor/order_executor.py` | `mutrade/engine/models.py` | SellSignal import | WIRED | `from mutrade.engine.models import SellSignal` (line 17). |
| `mutrade/executor/order_executor.py` | pykis | acc.sell() 호출 | WIRED | `acc.sell(market="KRX", symbol=..., price=None, qty=qty)` (lines 79-84). |
| `mutrade/monitor/scheduler.py` | `mutrade/executor/order_executor.py` | executor.execute(sig) 호출 | WIRED | Pattern `executor\.execute\(sig\)` 확인 (line 100). `from mutrade.executor.order_executor import OrderExecutor` (line 27). |
| `mutrade/main.py` | `mutrade/executor/order_executor.py` | OrderExecutor(kis=kis, dry_run=settings.dry_run) | WIRED | `OrderExecutor(kis=kis, dry_run=settings.dry_run)` (line 83). `from mutrade.executor.order_executor import OrderExecutor` (line 29). |
| `mutrade/main.py` | `mutrade/monitor/scheduler.py` | start_scheduler(..., executor) | WIRED | `start_scheduler(kis, config, engine, executor)` (line 90). 시그니처에 executor 파라미터 포함. |

---

### Data-Flow Trace (Level 4)

`order_executor.py`는 렌더링 컴포넌트가 아닌 실행기이므로 UI 데이터 흐름 추적 대신 KIS API 호출 체인을 확인한다.

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| `order_executor.py` | `qty` (orderable) | `acc.balance("KR").stock(signal.code).orderable` | YES — PyKis 잔고 조회 (런타임 KIS API 호출) | FLOWING (mock 기반 검증) |
| `order_executor.py` | `order` (주문 결과) | `acc.sell(market="KRX", ...)` | YES — PyKis 매도 주문 API 호출, 반환값 order 객체 | FLOWING (mock 기반 검증) |
| `order_executor.py` | `record` (체결 레코드) | `acc.daily_orders().order(order)` | YES — PyKis 일별 주문 조회 API 호출 | FLOWING (mock 기반 검증) |

주의: mock 기반 검증이므로 실제 PyKis API 동작은 모의투자 환경 인수 테스트에서만 확인 가능. (Success Criterion 4 — human_needed)

---

### Behavioral Spot-Checks

런타임에 KIS 자격증명이 필요한 실제 API 호출이 포함되어 있어 서버 시작 없이 자동으로 동작을 검증하기 어렵다. pytest 기반 unit/integration 테스트로 대체 검증.

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| 11개 OrderExecutor 단위 테스트 통과 | `/opt/homebrew/bin/pytest tests/test_order_executor.py -x -v` | 11 passed in 0.08s | PASS |
| 8개 Scheduler 통합 테스트 통과 (executor 포함) | `/opt/homebrew/bin/pytest tests/test_scheduler.py -x -v` | 8 passed in 1.43s | PASS |
| 전체 테스트 스위트 통과 | `/opt/homebrew/bin/pytest tests/ -x -q` | 64 passed in 1.49s | PASS |
| KIS 모의투자 end-to-end | 실제 모의투자 자격증명으로 봇 실행 필요 | 미실행 | ? SKIP (외부 서비스) |

---

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|----------|
| EXEC-01 | 03-01, 03-02 | 매도 신호 발생 시 해당 종목을 시장가로 즉시 매도한다 | SATISFIED | acc.sell(market="KRX", price=None, qty=orderable) 구현 확인. test_market_sell_called PASS. |
| EXEC-02 | 03-01, 03-02 | 매도 가능 수량(ord_psbl_qty)을 조회하여 매도 수량으로 사용한다 | SATISFIED | acc.balance("KR").stock(code).orderable 조회 패턴 구현. test_orderable_qty_used PASS. |
| EXEC-03 | 03-01, 03-02 | 동일 종목에 대해 SELL_PENDING 플래그로 중복 주문을 방지한다 | SATISFIED | _pending: set[str] 구현, signal.code in self._pending 체크. test_sell_pending_blocks_duplicate + test_sell_failure_clears_pending PASS. |
| EXEC-04 | 03-01, 03-02 | 주문 제출 후 체결 여부를 확인한다 | SATISFIED | _confirm_fill() — daily_orders().order() 최대 5회 폴링, 타임아웃 시 pending 해제. test_fill_confirmed + test_fill_timeout_clears_pending PASS. |

REQUIREMENTS.md에서 Phase 3에 추가로 맵핑된 고아 요구사항(orphaned requirement): 없음. 4개 EXEC 요구사항 모두 두 플랜에서 동일하게 선언되고 구현됨.

---

### Anti-Patterns Found

`mutrade/executor/order_executor.py`, `mutrade/monitor/scheduler.py`, `mutrade/main.py`, `tests/test_order_executor.py` 스캔 결과:

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| — | — | — | — | 발견 없음 |

- TODO/FIXME/PLACEHOLDER 없음
- return null / return {} 없음 (dry_run 분기의 `return`은 의도된 early exit)
- 하드코딩된 빈 데이터 없음
- `_pending.discard()` 모든 종료 경로에 보장됨 (정상 패턴)

---

### Human Verification Required

#### 1. KIS 모의투자 End-to-End 매도 주문 검증

**Test:** KIS 모의투자 자격증명(KIS_APP_KEY, KIS_APP_SECRET, KIS_ACCOUNT_NO, KIS_MOCK=True, DRY_RUN=False)을 `.env`에 설정 후 봇 실행. 모니터링 중인 종목의 가격이 트레일링 스탑 임계값 이하로 하락하도록 config.toml의 threshold를 낮게 설정(예: 0.001)하거나 peak를 수동 조작하여 SellSignal을 강제 발생.

**Expected:**
1. `[LIVE] SELL SIGNAL: {종목코드} (...)` 로그 출력
2. `[LIVE] 매도 주문 제출: {종목코드} ({종목명}) qty={수량} 주문번호={번호}` 로그 출력
3. `체결 확인 {종목코드}: 체결수량={수량} 미체결수량=0 체결단가={단가}` 로그 출력 또는 `체결 확인 시간 초과` 로그
4. KIS 모의투자 앱/웹에서 주문 내역 확인

**Why human:** 실제 KIS 모의투자 자격증명과 paper trading `tr_id` 값으로 acc.sell() 호출이 실제로 성공하는지, daily_orders()가 모의투자 환경에서 체결 레코드를 반환하는지는 런타임 인수 테스트로만 확인 가능. mock 기반 테스트는 PyKis API 인터페이스를 가정하고 있으며 실제 KIS API 응답 형식과의 일치 여부는 검증 불가.

---

### Gaps Summary

자동화 검증 범위에서 갭은 없다. EXEC-01~04 요구사항 모두 구현되었고, 64개 전체 테스트가 통과한다.

단, Success Criterion 4 ("End-to-end sell flow completes successfully in KIS paper trading (모의투자) with paper trading `tr_id` values")는 mock 기반 테스트로 검증 불가한 런타임 외부 서비스 동작이다. 이는 ROADMAP.md에서 명시한 phase goal의 일부이므로 인수 테스트가 완료될 때까지 status는 `human_needed`로 유지된다.

ROADMAP.md의 Phase 3 상태 표기(1/2 plans executed)는 이미 03-02가 완료되었으므로 실제 코드와 불일치한다. 이는 ROADMAP.md 업데이트 누락이며 코드 동작에 영향 없음.

---

_Verified: 2026-04-07T08:00:00Z_
_Verifier: Claude (gsd-verifier)_
