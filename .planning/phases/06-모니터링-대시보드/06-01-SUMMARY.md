---
phase: 06-모니터링-대시보드
plan: "01"
subsystem: admin/hub + executor + scheduler
tags: [infra, bugfix, data-pipeline, tdd]
dependency_graph:
  requires: []
  provides:
    - hub.push_snapshot(states, prices, pending_codes) 확장 시그니처
    - hub._put_snapshot() QueueFull 드롭-앤-리플레이스 패턴
    - OrderExecutor.pending_codes() frozenset 공개 메서드
    - scheduler → hub 스냅샷에 prices + pending_codes 포함
  affects:
    - mutrade/admin/hub.py
    - mutrade/executor/order_executor.py
    - mutrade/monitor/scheduler.py
tech_stack:
  added: []
  patterns:
    - asyncio.Queue 드롭-앤-리플레이스 (QueueFull 방어)
    - call_soon_threadsafe + _put_snapshot bound method 패턴
    - frozenset 복사본 공개 메서드 패턴
key_files:
  created: []
  modified:
    - mutrade/admin/hub.py
    - mutrade/executor/order_executor.py
    - mutrade/monitor/scheduler.py
    - tests/test_hub.py
    - tests/test_order_executor.py
    - tests/test_scheduler.py
decisions:
  - "call_soon_threadsafe 대상을 put_nowait 람다에서 _put_snapshot bound method로 교체 — QueueFull 방어 로직을 루프 스레드 내에서 안전하게 실행하기 위함"
  - "pending_codes() 반환 타입을 frozenset으로 고정 — 불변 복사본 보장, 외부 수정 방지"
  - "drop_pct 계산 시 peak=0 또는 current=0이면 0.0 반환 — ZeroDivisionError 방어"
metrics:
  duration_seconds: 226
  completed_date: "2026-04-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 6
requirements_satisfied:
  - INFRA-01
  - INFRA-02
---

# Phase 6 Plan 01: 인프라 버그 수정 및 스냅샷 데이터 확장 Summary

**One-liner:** asyncio QueueFull 드롭-앤-리플레이스 패턴 적용 + push_snapshot(prices, pending_codes) 확장으로 Wave 2/3 전제조건 완성

## What Was Built

Wave 2(WebSocket 엔드포인트)와 Wave 3(대시보드 UI)의 전제조건인 인프라 버그 수정 및 데이터 파이프라인 확장.

### Task 1: hub.py QueueFull 수정 + push_snapshot 시그니처 확장 (INFRA-01, INFRA-02)

- `push_snapshot(states, prices=None, pending_codes=None)` — 확장 시그니처, 하위 호환 유지
- 직렬화 루프에 `current_price`, `drop_pct`, `sell_pending` 필드 추가
- `_put_snapshot()` 메서드 신설: 큐가 full일 때 `get_nowait()`로 기존 항목 드롭 후 `put_nowait()` 실행
- `call_soon_threadsafe` 대상을 `put_nowait` 람다에서 `_put_snapshot` bound method로 교체

### Task 2: order_executor.py + scheduler.py 갱신 (INFRA-01)

- `OrderExecutor.pending_codes()` 공개 메서드 추가 — `frozenset(self._pending)` 반환
- `scheduler.py` hub 연동 블록: `hub.push_snapshot(engine.states, prices, executor.pending_codes())`로 갱신

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED (Task 1) | fb63784 | test(06-01): add failing tests for hub push_snapshot signature + QueueFull fix |
| GREEN (Task 1) | fbd3ced | feat(06-01): hub.py QueueFull 수정 + push_snapshot 시그니처 확장 |
| RED (Task 2) | 7dd4801 | test(06-01): add failing tests for pending_codes() + scheduler push_snapshot args |
| GREEN (Task 2) | 9684deb | feat(06-01): pending_codes() 공개 메서드 추가 + scheduler push_snapshot 인자 갱신 |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| fb63784 | test | hub push_snapshot 시그니처 + QueueFull RED 테스트 |
| fbd3ced | feat | hub.py QueueFull 수정 + push_snapshot 확장 (INFRA-01, INFRA-02) |
| 7dd4801 | test | pending_codes() + scheduler push_snapshot 인자 RED 테스트 |
| 9684deb | feat | pending_codes() 공개 메서드 + scheduler push_snapshot 갱신 (INFRA-01) |

## Verification Results

```
python3.11 -m pytest tests/ -q --tb=short
114 passed, 1 failed (pre-existing: test_client.py::test_mock_mode_uses_virtual_account — 환경변수 불일치, 이번 플랜 무관)
```

플랜 검증 스크립트 2개 모두 `PASS`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 기존 test_hub.py 어설션이 낡은 인터페이스를 검증**
- **Found during:** Task 1 GREEN 단계
- **Issue:** `test_push_snapshot_after_attach_loop_calls_call_soon_threadsafe`가 `call_args[0][0].__name__ == "put_nowait"`를 검증 — INFRA-02 구현 후 `_put_snapshot`으로 변경됐으므로 테스트 실패
- **Fix:** 어설션을 `_put_snapshot` bound method 확인으로 업데이트
- **Files modified:** `tests/test_hub.py`
- **Commit:** fbd3ced

## Known Stubs

없음 — 모든 필드가 실제 데이터 소스(prices dict, pending set)에서 계산됨.

## Threat Flags

없음 — 이번 플랜은 기존 내부 상태 전달 경로를 수정할 뿐, 새로운 네트워크 엔드포인트나 외부 노출 경로를 추가하지 않음.

## Self-Check: PASSED

- [x] `mutrade/admin/hub.py` — 존재 및 `_put_snapshot` 메서드 포함
- [x] `mutrade/executor/order_executor.py` — 존재 및 `pending_codes()` 메서드 포함
- [x] `mutrade/monitor/scheduler.py` — `executor.pending_codes()` 호출 포함
- [x] 커밋 fb63784, fbd3ced, 7dd4801, 9684deb 모두 존재
- [x] 114 tests passing (기존 실패 1개는 pre-existing, 이번 플랜 무관)
