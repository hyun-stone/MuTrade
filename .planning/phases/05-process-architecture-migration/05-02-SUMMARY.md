---
phase: 05-process-architecture-migration
plan: 02
subsystem: scheduler + main
tags: [apscheduler, background-scheduler, uvicorn, hub-integration, tdd]
dependency_graph:
  requires: [05-01]
  provides: [BackgroundScheduler entrypoint, uvicorn main loop, hub-scheduler bridge]
  affects: [mutrade/monitor/scheduler.py, mutrade/main.py, tests/test_scheduler.py]
tech_stack:
  added: []
  patterns: [BackgroundScheduler (non-blocking), uvicorn.run (blocking main thread), hub.push_snapshot, hub.is_stop_requested]
key_files:
  created: []
  modified:
    - mutrade/monitor/scheduler.py
    - mutrade/main.py
    - tests/test_scheduler.py
decisions:
  - "BackgroundScheduler 전환: uvicorn이 메인 스레드를 담당하고 봇 폴링은 별도 스레드에서 실행"
  - "host=127.0.0.1 바인딩: T-05-06 mitigate — 0.0.0.0 대신 로컬 바인딩으로 노출 최소화"
  - "is_stop_requested() 체크를 루프 최상단에 배치: 마감 시간 체크 전에 Admin UI 중단 요청 우선 처리"
  - "time.sleep 유지 (threading.Event.wait 미사용): 테스트 호환성 + 중단은 다음 폴링 사이클에서 처리로 충분"
metrics:
  duration: "약 30분"
  completed: "2026-04-12"
  tasks_completed: 2
  tasks_total: 2
  files_created: 0
  files_modified: 3
---

# Phase 5 Plan 02: BackgroundScheduler 전환 + uvicorn 진입점 재구성 Summary

**One-liner:** BlockingScheduler를 BackgroundScheduler로 전환하고 uvicorn.run()을 메인 스레드 블로킹 진입점으로 재구성하여 FastAPI + 봇 폴링 동시 실행 아키텍처 완성

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| TDD RED | 신규 테스트 4개 추가 (실패 상태) | 833f913 | tests/test_scheduler.py |
| 1 | BackgroundScheduler 전환 + hub 연동 | 6b46161 | mutrade/monitor/scheduler.py, tests/test_scheduler.py |
| 2 | main.py 재구성 — uvicorn.run() 진입점 | 6ad7811 | mutrade/main.py |

## What Was Built

### scheduler.py — BackgroundScheduler 전환 + hub 연동

- `BlockingScheduler` → `BackgroundScheduler` (비블로킹 — 즉시 반환)
- `create_poll_session()`에 `hub=None` 파라미터 추가
- 루프 최상단: `hub.is_stop_requested()` True 시 즉시 루프 종료 + `hub.clear_stop()` 호출
- `engine.tick()` 후: `hub.push_snapshot(engine.states)` + `hub.set_running(True)` 호출
- 세션 종료 시: `hub.set_running(False)` 호출
- `start_scheduler()` 반환 타입: `None` → `BackgroundScheduler` (호출자에서 scheduler 참조 유지 가능)
- try/except KeyboardInterrupt 블록 제거 (BackgroundScheduler는 블로킹하지 않음)

### main.py — uvicorn.run() 진입점

- `BotStateHub()` 초기화 추가
- `start_scheduler(hub=hub)` 호출 — BackgroundScheduler를 별도 스레드에서 비블로킹 시작
- `create_app(hub=hub, scheduler=scheduler, engine=engine, config=config)` 호출
- `uvicorn.run(app, host="127.0.0.1", port=8000)` — 메인 스레드 블로킹 진입점
- docstring 실행 흐름 7~9단계 업데이트

### tests/test_scheduler.py — 테스트 업데이트

- `TestShutdownLog.test_shutdown_logs_state`: `BlockingScheduler` → `BackgroundScheduler` mock 대상 변경
- 신규 `TestBackgroundSchedulerReturn`: `start_scheduler()`가 `BackgroundScheduler` 인스턴스 반환 검증
- 신규 `TestHubIntegration.test_hub_push_snapshot_called_after_poll`: 폴링 후 `hub.push_snapshot()` 호출 검증
- 신규 `TestHubIntegration.test_hub_stop_requested_breaks_loop`: `is_stop_requested()` True 시 루프 종료 + `clear_stop()` 호출 검증

## Test Results

- TDD RED: 4개 신규 테스트 실패 확인 후 구현
- TDD GREEN: 12개 테스트 모두 PASS (기존 8개 + 신규 4개)
- 전체 테스트: 99개 실행, 98개 PASS (test_client.py 1개 pre-existing 실패 — 아래 참조)

## Deviations from Plan

### 테스트 수정 (Rule 1 — 버그 수정)

**[Rule 1 - Bug] TestHubIntegration.test_hub_push_snapshot_called_after_poll 테스트 수정**
- **발견 시점:** Task 1 GREEN 단계
- **문제:** 테스트에서 `engine.states`에 `dict` 객체를 사용했으나 `scheduler.py`의 상태 로깅이 `.peak_price` 속성으로 접근 → `AttributeError`
- **수정:** 테스트에서 `dict` → `SymbolState` 객체로 교체
- **수정 파일:** `tests/test_scheduler.py`
- **커밋:** 6b46161에 포함

## Deferred Issues

**test_client.py::test_mock_mode_uses_virtual_account** — pre-existing 실패
- **원인:** `.env`의 실제 KIS 가상계좌 번호(`73345839`)와 테스트 하드코딩값(`12345678`) 불일치
- **확인:** Plan 02 변경 이전(stash pop 이전)에도 동일하게 실패 확인
- **영향:** Plan 02 변경 사항과 무관. KIS 환경변수 또는 테스트 픽스처 정리 필요
- **조치:** Phase 6 이전 또는 별도 quick task로 처리

## Known Stubs

없음. 모든 인터페이스가 완전히 구현되었다.

## Threat Flags

| Flag | File | Description |
|------|------|-------------|
| T-05-06 mitigate applied | mutrade/main.py | uvicorn host=127.0.0.1 바인딩 — 0.0.0.0 대신 로컬 전용 바인딩으로 위협 완화 |

## Self-Check: PASSED

파일 존재 확인:
- mutrade/monitor/scheduler.py: FOUND
- mutrade/main.py: FOUND
- tests/test_scheduler.py: FOUND

커밋 확인:
- 833f913 (TDD RED): FOUND
- 6b46161 (feat scheduler): FOUND
- 6ad7811 (feat main.py): FOUND
