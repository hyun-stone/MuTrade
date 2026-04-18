---
phase: 07-봇-제어
plan: 01
subsystem: admin-backend
tags: [fastapi, control-api, websocket, dry-run, trailing-stop]
dependency_graph:
  requires: []
  provides:
    - POST /api/start (시장 시간 검증 + APScheduler modify_job 트리거)
    - POST /api/stop (hub.request_stop())
    - POST /api/toggle-dry-run (engine._dry_run + executor._dry_run 원자 반전)
    - POST /api/sell/{code} (수동 매도 SellSignal, dry_run=False)
    - hub.push_snapshot() _meta 필드 (is_running, dry_run)
  affects:
    - mutrade/admin/hub.py
    - mutrade/admin/app.py
    - mutrade/monitor/scheduler.py
tech_stack:
  added: []
  patterns:
    - FastAPI Request 객체로 app.state 의존성 주입
    - run_in_threadpool으로 동기 executor.execute() 오프로드
    - RLock 내에서 engine._dry_run / executor._dry_run 원자적 반전
    - datetime.now(KST) 서버 측 시장 시간 검증 (T-7-02 mitigate)
    - re.match 종목 코드 입력 검증 (T-7-01 mitigate)
key_files:
  created: []
  modified:
    - mutrade/admin/hub.py
    - mutrade/admin/app.py
    - mutrade/monitor/scheduler.py
    - tests/test_hub.py
    - tests/test_app_routes.py
decisions:
  - "modify_job('market_poll', next_run_time=now) 사용 — trigger_job()은 APScheduler 3.x에서 미지원"
  - "수동 매도(/api/sell)는 dry_run=False 하드코딩 — 관리자 의도적 실거래 실행"
  - "시장 시간 상한을 15:20으로 설정 — config.market_close_hour/minute와 일치"
metrics:
  duration_seconds: 190
  completed_date: "2026-04-18"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 5
---

# Phase 07 Plan 01: 봇 제어 API 백엔드 Summary

**One-liner:** FastAPI 앱에 봇 시작/중지/드라이런 토글/수동 매도 4개 POST 엔드포인트 추가 및 hub 스냅샷에 _meta(is_running, dry_run) 필드 포함

## What Was Built

### Task 1 — hub.py _meta 필드 + scheduler.py dry_run 전달

`push_snapshot()` 시그니처에 `dry_run: bool = False` 인자를 추가하고, 스냅샷 최상위에 `_meta` 키를 삽입한다. `_meta`는 `is_running`과 `dry_run` 두 필드를 포함하며 프론트엔드(Plan 02)가 봇 상태를 렌더링하는 데 사용한다. `scheduler.py`의 `hub.push_snapshot()` 호출도 `dry_run=engine._dry_run`을 전달하도록 수정했다.

**커밋:** `8c616e2`

### Task 2 — app.py 4개 POST 엔드포인트 + 테스트

| 엔드포인트 | 동작 | 상태 코드 |
|-----------|------|---------|
| POST /api/start | KST 시장 시간 검증 → modify_job 트리거 | 200 / 400 / 409 |
| POST /api/stop | hub.request_stop() | 200 |
| POST /api/toggle-dry-run | engine+executor _dry_run 원자 반전 | 200 |
| POST /api/sell/{code} | 정규식 검증 → SellSignal(dry_run=False) → run_in_threadpool | 200 / 400 / 404 |

`app.state`에 scheduler, engine, executor, config를 lifespan startup에서 주입한다. `create_app()` kwargs 패턴으로 의존성을 전달하며 기존 구조를 그대로 유지한다.

**커밋:** `fe1741d`

## Test Results

| 테스트 클래스 | 통과 | 총계 |
|-------------|-----|-----|
| TestBotStateHubPhase7 (신규) | 4 | 4 |
| TestControlRoutes (신규) | 7 | 7 |
| tests/ 전체 (test_client.py 제외) | 131 | 131 |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] test_app_routes.py에 datetime import 누락**
- **Found during:** Task 2 테스트 실행
- **Issue:** `TestControlRoutes` 테스트 내 `datetime(2026, 4, 18, 10, 0, ...)` 호출에서 `NameError: name 'datetime' is not defined`
- **Fix:** 파일 상단에 `from datetime import datetime` import 추가
- **Files modified:** tests/test_app_routes.py
- **Commit:** fe1741d (Task 2 커밋에 포함)

## Deferred Issues

**test_client.py::test_mock_mode_uses_virtual_account** — 이번 플랜 이전부터 존재하는 기존 실패. 환경변수 격리 문제로 `.env`의 `KIS_VIRTUAL_ACCOUNT` 실제 값이 테스트 mock 설정보다 우선 적용됨. 이번 플랜 범위 외. `.planning/phases/07-봇-제어/deferred-items.md` 참조.

## Threat Model Coverage

| Threat ID | 상태 |
|-----------|------|
| T-7-01 (종목 코드 Tampering) | mitigated — `re.match(r"^[0-9A-Za-z]{1,12}$", code)` |
| T-7-02 (시장 시간 우회) | mitigated — 서버 KST 시간 검증 |
| T-7-03 (중복 주문) | accepted — executor._pending set |
| T-7-04 (DoS) | accepted — 개인용 로컬 봇 |

## Self-Check: PASSED

- mutrade/admin/hub.py: 존재 확인
- mutrade/admin/app.py: 존재 확인
- mutrade/monitor/scheduler.py: 존재 확인
- tests/test_hub.py: 존재 확인
- tests/test_app_routes.py: 존재 확인
- commit 8c616e2: 존재 확인
- commit fe1741d: 존재 확인
