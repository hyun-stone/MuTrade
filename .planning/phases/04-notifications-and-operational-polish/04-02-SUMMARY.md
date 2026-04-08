---
phase: 04-notifications-and-operational-polish
plan: "02"
subsystem: notifications
tags: [telegram, notifier, order-executor, scheduler, trade-log, tdd]
dependency_graph:
  requires:
    - mutrade/notifier/telegram.py (TelegramNotifier — 04-01)
    - mutrade/executor/order_executor.py (OrderExecutor — Phase 3)
    - mutrade/monitor/scheduler.py (start_scheduler — Phase 3)
    - mutrade/settings.py (telegram_bot_token, telegram_chat_id — 04-01)
  provides:
    - OrderExecutor.notifier injection point
    - "[TRADE] log marker in logs/mutrade.log"
    - engine.states shutdown logging
    - TelegramNotifier wired end-to-end in main.py
  affects:
    - NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04 (all satisfied)
tech_stack:
  added: []
  patterns:
    - TYPE_CHECKING guard for notifier dependency (avoids circular import)
    - notifier=None default parameter (backward-compatible injection)
    - "[TRADE] log marker for grep-extractable trade history"
key_files:
  created:
    - tests/test_order_executor.py (TestNotifierIntegration — 4 new tests)
    - tests/test_scheduler.py (TestShutdownLog — 1 new test)
  modified:
    - mutrade/executor/order_executor.py
    - mutrade/monitor/scheduler.py
    - mutrade/main.py
decisions:
  - "TYPE_CHECKING guard for TelegramNotifier import in order_executor.py — avoids runtime circular import while preserving type hints"
  - "notifier=None default in OrderExecutor.__init__ — fully backward compatible, no changes needed in existing tests"
  - "token not logged in main.py — only chat_id printed (T-04-06 mitigated)"
metrics:
  duration: "~20 minutes"
  completed: "2026-04-08"
  tasks_completed: 2
  files_changed: 5
---

# Phase 04 Plan 02: TelegramNotifier 통합 및 [TRADE] 로그 추가 Summary

**One-liner:** OrderExecutor에 TelegramNotifier 주입, [TRADE] 로그 마커 삽입, 종료 시 engine.states 순회 로깅으로 NOTIF-01~04 전체 충족.

## What Was Built

### Task 1: OrderExecutor에 notifier 주입 및 [TRADE] 로그 추가 (TDD)

`mutrade/executor/order_executor.py`에 TelegramNotifier 통합을 구현했다.

- `__init__` 시그니처에 `notifier: TelegramNotifier | None = None` 추가 (기존 코드 완전 호환)
- `TYPE_CHECKING` 가드로 순환 임포트 방지하면서 타입 힌트 유지
- `_submit_order()` 내 `acc.sell()` 성공 직후에 두 줄 삽입:
  - `logger.info("[TRADE] 매도 주문 제출: ...")` — grep 가능한 거래 이력 마커 (NOTIF-03)
  - `self._notifier.notify(signal, qty)` — notifier가 None이 아닐 때만 호출 (NOTIF-01, D-03)
- dry_run=True 시 _submit_order 자체가 호출되지 않으므로 notifier.notify() 도 자동으로 미호출

### Task 2: 종료 로그 및 main.py 통합 (TDD)

**scheduler.py:** `start_scheduler()` except 블록에 shutdown 로깅 추가 (NOTIF-04).
- KeyboardInterrupt/SystemExit 시 `engine.states.items()` 전체 순회
- 각 SymbolState의 code, peak_price, warm 상태를 INFO 로그로 출력

**main.py:** TelegramNotifier 초기화 및 OrderExecutor 주입 완성.
- `from mutrade.notifier.telegram import TelegramNotifier` import 추가
- `TelegramNotifier(token=settings.telegram_bot_token, chat_id=settings.telegram_chat_id)` 생성
- Telegram 활성화 여부를 로그로 출력 (token 값 자체는 절대 출력 안 함 — T-04-06)
- `OrderExecutor(kis=kis, dry_run=settings.dry_run, notifier=notifier)` 주입

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/test_order_executor.py (TestNotifierIntegration) | 4 (신규) | PASSED |
| tests/test_scheduler.py (TestShutdownLog) | 1 (신규) | PASSED |
| tests/ (전체) | 78 | PASSED |

기존 73개 테스트 회귀 없음. 신규 5개 테스트 추가.

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `ea6fb6c` | feat(04-02): integrate TelegramNotifier into OrderExecutor with [TRADE] log |
| Task 2 | `de81d58` | feat(04-02): add shutdown state log and wire TelegramNotifier in main.py |

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `mutrade/executor/order_executor.py` | Modified | notifier 주입 + [TRADE] 로그 + notify() 호출 |
| `mutrade/monitor/scheduler.py` | Modified | 종료 시 engine.states 순회 로깅 |
| `mutrade/main.py` | Modified | TelegramNotifier 초기화 및 OrderExecutor 주입 |
| `tests/test_order_executor.py` | Modified | TestNotifierIntegration 4개 테스트 추가 |
| `tests/test_scheduler.py` | Modified | TestShutdownLog 1개 테스트 추가 |

## Phase 4 완료 확인

| 요구사항 | 설명 | 충족 계획 | 상태 |
|----------|------|-----------|------|
| NOTIF-01 | 매도 실행 시 Telegram 알림 전송 | 04-01 (TelegramNotifier), 04-02 (주입) | DONE |
| NOTIF-02 | 알림 실패가 매도 흐름을 차단하지 않음 | 04-01 (daemon Thread + try/except) | DONE |
| NOTIF-03 | 거래 이력을 logs/mutrade.log에 [TRADE] 마커로 기록 | 04-02 | DONE |
| NOTIF-04 | 종료 시 모니터링 종목·고점 상태 로깅 | 04-02 | DONE |

## 수동 검증 필요 사항

- 실제 Telegram 봇 토큰과 chat_id를 `.env`에 설정하고 end-to-end 알림 수신 확인
- `grep "[TRADE]" logs/mutrade.log` 로 거래 이력 추출 가능 여부 확인 (실거래 실행 후)

## Deviations from Plan

None — 플랜대로 정확히 실행됨.

## Known Stubs

없음. 모든 기능이 실제 구현으로 완성됨.

## Threat Flags

없음. 플랜의 threat_model이 모두 구현에 반영됨:
- T-04-06: main.py에서 `telegram_bot_token` 값을 logger에 전달하지 않음 (chat_id만 출력)
- T-04-07: notifier.notify() 예외는 TelegramNotifier 내부에서 포착 — order_executor.py에 추가 try/except 없음
- T-04-08: [TRADE] 로그에 종목코드·가격·수량만 기록, API 키/토큰 미포함

## Self-Check: PASSED

- `mutrade/executor/order_executor.py` — FOUND, contains `self._notifier` and `[TRADE]`
- `mutrade/monitor/scheduler.py` — FOUND, contains `engine.states`
- `mutrade/main.py` — FOUND, contains `TelegramNotifier` and `notifier=notifier`
- `tests/test_order_executor.py` — FOUND, TestNotifierIntegration 4 tests
- `tests/test_scheduler.py` — FOUND, TestShutdownLog 1 test
- commit `ea6fb6c` — FOUND
- commit `de81d58` — FOUND
- 78 tests passed, 0 failures
