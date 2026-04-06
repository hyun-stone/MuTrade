---
phase: 02-trailing-stop-engine
plan: "02"
subsystem: engine-integration
tags: [trailing-stop, scheduler, settings, dry-run, engine-wiring]
dependency_graph:
  requires: ["02-01"]
  provides: ["trailing-stop-polling-pipeline", "dry-run-setting", "engine-main-wiring"]
  affects: ["mutrade/settings.py", "mutrade/monitor/scheduler.py", "mutrade/main.py"]
tech_stack:
  added: []
  patterns:
    - "DRY_RUN env var with KIS_MOCK auto-force via model_validator"
    - "engine.tick(prices) in polling loop with SellSignal warning log"
    - "StateStore + TrailingStopEngine initialization in main() entrypoint"
key_files:
  created: []
  modified:
    - mutrade/settings.py
    - mutrade/monitor/scheduler.py
    - mutrade/main.py
    - tests/test_settings.py
    - tests/test_scheduler.py
decisions:
  - "KIS_MOCK=true 시 DRY_RUN 자동 강제 — 모의투자 환경에서 실매도는 의미 없으므로 model_validator에서 강제"
  - "엔진 상태(peak/warm)를 세션 시작 시 로깅 — 재시작 후 state.json 복원 확인용"
metrics:
  duration_seconds: 129
  completed_date: "2026-04-06"
  tasks_completed: 2
  files_modified: 5
---

# Phase 02 Plan 02: Engine Integration Summary

트레일링 스탑 엔진을 폴링 루프(scheduler)와 봇 엔트리포인트(main.py)에 통합하고, Settings에 DRY_RUN 필드를 추가하여 가격 폴링 → 고점 추적 → 매도 신호 로깅 파이프라인을 완성했다.

## What Was Built

**Settings DRY_RUN 필드:**
- `dry_run: bool = Field(False, alias="DRY_RUN")` 추가
- `KIS_MOCK=true` 시 `validate_virtual_credentials` validator에서 `dry_run` 자동 강제 활성화 (`object.__setattr__` 사용)

**Scheduler 엔진 통합:**
- `create_poll_session(kis, config, engine: TrailingStopEngine)` 시그니처 확장
- 폴링 루프 내 `signals = engine.tick(prices)` 호출 추가
- SellSignal 발생 시 `logger.warning("[DRY-RUN/LIVE] SELL SIGNAL: ...")` 로깅
- 세션 시작 시 `engine.states` 순회 → peak/warm 상태 로깅 (재시작 후 복원 확인)

**main.py 엔진 초기화:**
- `StateStore(path="state.json")` 인스턴스 생성
- `TrailingStopEngine(symbols=config.symbols, store=store, dry_run=settings.dry_run)` 초기화
- `start_scheduler(kis, config, engine)` 으로 엔진 전달

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Settings에 DRY_RUN 필드 추가 | eede82b | mutrade/settings.py, tests/test_settings.py |
| 2 | 스케줄러와 main.py에 엔진 통합 | 243dbb4 | mutrade/monitor/scheduler.py, mutrade/main.py, tests/test_scheduler.py |

## Test Results

전체 51개 테스트 통과 (Phase 1 + Phase 2 통합).
- `tests/test_settings.py`: 7 passed (TestDryRun 3개 신규 포함)
- `tests/test_scheduler.py`: 6 passed (engine.tick 호출, SELL SIGNAL 로깅 2개 신규)
- `tests/test_engine.py`: 16 passed (기존 유지)
- `tests/test_state_store.py`: 7 passed (기존 유지)
- `tests/test_price_feed.py`: 7 passed (기존 유지)
- `tests/test_holiday.py`: 3 passed (기존 유지)
- `tests/test_config.py`: 5 passed (기존 유지)

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. 파이프라인은 완전히 연결되었다 (poll_prices → engine.tick → SellSignal 로깅). 실제 매도 실행(주문)은 Phase 3에서 구현한다.

## Self-Check: PASSED

Files exist:
- mutrade/settings.py — FOUND
- mutrade/monitor/scheduler.py — FOUND
- mutrade/main.py — FOUND
- tests/test_settings.py — FOUND
- tests/test_scheduler.py — FOUND

Commits exist:
- eede82b (Task 1: DRY_RUN field) — FOUND
- 243dbb4 (Task 2: engine integration) — FOUND
