---
phase: 02-trailing-stop-engine
plan: 01
subsystem: engine
tags: [trailing-stop, high-water-mark, state-store, atomic-write, tdd, dry-run]

# Dependency graph
requires:
  - phase: 01-foundation-and-kis-api-connectivity
    provides: SymbolConfig/AppConfig dataclasses, poll_prices() dict[str, float] interface
provides:
  - TrailingStopEngine with tick(prices) -> list[SellSignal] interface
  - StateStore with atomic tempfile+os.replace read/write
  - SellSignal and SymbolState dataclasses
  - warm-up safety guard (no sell signal on first tick)
  - per-symbol threshold support
  - dry_run flag propagated into SellSignal
affects:
  - 02-02 (scheduler/main integration — will call engine.tick() after poll_prices())
  - 03-order-execution (consumes SellSignal.code, current_price, dry_run)

# Tech tracking
tech-stack:
  added: []  # no new dependencies — uses stdlib json, os, tempfile, pathlib
  patterns:
    - TDD Red→Green→Refactor with MagicMock isolation
    - tempfile.mkstemp + os.replace atomic file write pattern
    - warm=False first-tick safety guard on SymbolState
    - peak_updated flag to minimise StateStore.save() calls

key-files:
  created:
    - mutrade/engine/__init__.py
    - mutrade/engine/models.py
    - mutrade/engine/state_store.py
    - mutrade/engine/trailing_stop.py
    - tests/test_engine.py
    - tests/test_state_store.py
  modified: []

key-decisions:
  - "warm=False guard: 첫 tick에서는 절대 SellSignal 반환 안 함 — 재시작 직후 오탐 방지"
  - "peak_updated 플래그로 고점 갱신 시에만 StateStore.save() 호출 — 매 tick마다 I/O 없음"
  - "test_save_uses_atomic_write_with_os_replace: shutil.move를 wraps로 사용해 재귀 방지 (os.replace 직접 참조 시 RecursionError)"

patterns-established:
  - "Engine tests: StateStore를 MagicMock(spec=StateStore)으로 격리, 엔진 로직만 테스트"
  - "State persistence: 고점 갱신 tick에만 save() — 상태 저장 빈도 최소화"
  - "Warm-up pattern: warm=False → 첫 tick → warm=True, 이 구간은 신호 없음"

requirements-completed: [ENG-01, ENG-02, ENG-03, ENG-04, ENG-05]

# Metrics
duration: 3min
completed: 2026-04-07
---

# Phase 2 Plan 01: Trailing Stop Engine Summary

**TrailingStopEngine.tick()으로 고점 추적 → 하락률 계산 → SellSignal 반환, StateStore가 tempfile+os.replace로 원자적 state.json 저장**

## Performance

- **Duration:** 3 min
- **Started:** 2026-04-06T15:53:51Z
- **Completed:** 2026-04-06T15:56:51Z
- **Tasks:** 1
- **Files modified:** 6 (all new)

## Accomplishments

- `SellSignal` / `SymbolState` dataclass 정의 — Phase 3 주문 실행이 소비할 인터페이스
- `StateStore` 원자적 읽기/쓰기 — tempfile.mkstemp + os.replace 패턴, 구버전 `warm` 필드 없는 state.json 호환
- `TrailingStopEngine.tick()` — 신규/warm-up/정상 추적 3단계, 종목별 threshold, dry_run 플래그
- TDD: 16개 엔진 테스트 + 7개 StateStore 테스트 = 23개, Phase 1 포함 전체 46개 green

## Task Commits

1. **Task 1: 엔진 모델, 상태 저장소, 트레일링 스탑 엔진 (TDD)** - `60a984b` (feat)

**Plan metadata:** (docs commit to follow)

## Files Created/Modified

- `mutrade/engine/__init__.py` — 패키지 마커 (빈 파일)
- `mutrade/engine/models.py` — SellSignal(frozen dataclass), SymbolState(mutable dataclass)
- `mutrade/engine/state_store.py` — StateStore: load()/save() 원자적 I/O
- `mutrade/engine/trailing_stop.py` — TrailingStopEngine: tick(), states 프로퍼티
- `tests/test_engine.py` — 엔진 로직 16개 테스트 (warm-up, per-symbol threshold, dry_run, multi-symbol 독립 추적)
- `tests/test_state_store.py` — StateStore 7개 테스트 (atomic write, parent mkdir, warm 필드 기본값)

## Decisions Made

- **warm=False 안전장치:** 재시작 후 첫 tick에서 고점 대비 큰 낙폭이어도 SellSignal 없음. 시스템 재시작 직후 오탐 방지.
- **peak_updated 플래그:** 고점이 갱신된 tick에서만 StateStore.save() 호출. 매 tick마다 파일 I/O 없음.
- **atomic write 테스트 전략:** `patch("...os.replace", wraps=shutil.move)` — os.replace를 직접 참조하면 재귀 오류 발생, shutil.move로 우회.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_save_uses_atomic_write_with_os_replace 재귀 오류 수정**
- **Found during:** Task 1 (GREEN 단계 테스트 실행)
- **Issue:** `patch("...os.replace")` side_effect에서 `real_replace = os.replace` 후 호출 시 RecursionError — mock된 os.replace를 다시 호출하는 재귀 구조
- **Fix:** `patch(..., wraps=shutil.move)` 패턴으로 교체 — shutil.move는 os.replace와 동일한 효과, 재귀 없음
- **Files modified:** tests/test_state_store.py
- **Verification:** 전체 23개 테스트 pass
- **Committed in:** 60a984b (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug in test)
**Impact on plan:** 테스트 로직 버그 수정. 구현 코드 영향 없음.

## Issues Encountered

None.

## Next Phase Readiness

- `TrailingStopEngine` 인터페이스 확정: `tick(prices: dict[str, float]) -> list[SellSignal]`
- Phase 02-02: `mutrade/monitor/scheduler.py`에서 `poll_prices()` 호출 후 `engine.tick()` 연결 위치 준비됨
- Phase 03: `SellSignal.code`, `.current_price`, `.dry_run` 필드로 주문 실행 로직 연결 가능

---
*Phase: 02-trailing-stop-engine*
*Completed: 2026-04-07*
