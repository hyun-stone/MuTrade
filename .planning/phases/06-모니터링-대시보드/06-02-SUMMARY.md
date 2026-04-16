---
phase: 06-모니터링-대시보드
plan: "02"
subsystem: admin/app + WebSocket + StaticFiles
tags: [websocket, fastapi, tdd, static-files, dash-03]
dependency_graph:
  requires:
    - 06-01 (hub.get_snapshot, hub.wait_for_change 인터페이스)
  provides:
    - app.py GET / → FileResponse(index.html)
    - app.py /ws WebSocket 엔드포인트 (실시간 스냅샷 브로드캐스트)
    - app.py /static StaticFiles 마운트
    - mutrade/admin/static/ 디렉터리 (Wave 3 index.html 위치)
  affects:
    - mutrade/admin/app.py
    - mutrade/admin/static/.gitkeep
tech_stack:
  added:
    - fastapi.WebSocket, WebSocketDisconnect
    - fastapi.responses.FileResponse
    - fastapi.staticfiles.StaticFiles
  patterns:
    - WebSocket accept → send_json(get_snapshot()) → wait_for_change() 루프
    - WebSocketDisconnect except pass 정상 종료 패턴
    - Path(__file__).parent / "static" 절대 경로 상수 (경로 순회 방어)
    - STATIC_DIR.mkdir(exist_ok=True) RuntimeError 방어
key_files:
  created:
    - mutrade/admin/static/.gitkeep
  modified:
    - mutrade/admin/app.py
    - tests/test_app_routes.py
decisions:
  - "STATIC_DIR을 모듈 레벨 상수로 정의 — 테스트에서 patch.object()로 교체 가능, 절대 경로로 T-06-06 경로 순회 방어"
  - "hub 접근을 websocket.app.state.hub로 통일 — FastAPI DI 없이 lifespan에서 설정된 hub 직접 참조"
  - "WebSocket 테스트에서 AsyncMock side_effect 대신 async 함수 직접 할당 — coroutine iterator TypeError 방지"
metrics:
  duration_seconds: 180
  completed_date: "2026-04-16"
  tasks_completed: 2
  tasks_total: 2
  files_modified: 3
requirements_satisfied:
  - DASH-03
---

# Phase 6 Plan 02: WebSocket 엔드포인트 + StaticFiles + GET / Summary

**One-liner:** FastAPI app.py에 /ws WebSocket 브로드캐스트 + /static StaticFiles + GET / FileResponse 추가로 Wave 3 프론트엔드 로드 전제조건 완성

## What Was Built

Wave 3(대시보드 UI)가 로드될 수 있는 FastAPI 엔드포인트 레이어 구현.

### Task 1: app.py — WebSocket 엔드포인트 + StaticFiles + GET / (DASH-03)

- `STATIC_DIR = Path(__file__).parent / "static"` 모듈 레벨 절대 경로 상수
- `GET /` → `FileResponse(STATIC_DIR / "index.html")` 라우트 등록
- `/ws` WebSocket 엔드포인트:
  - 연결 즉시 `hub.get_snapshot()` JSON 전송
  - `await hub.wait_for_change()` 루프에서 스냅샷 변경 시 브로드캐스트
  - `WebSocketDisconnect` except pass — 정상 종료, 예외 전파 없음 (T-06-07)
- `/static` StaticFiles 마운트 (절대 경로 사용, T-06-06 방어)
- `STATIC_DIR.mkdir(parents=True, exist_ok=True)` — static/ 미존재 시 RuntimeError 방지

### Task 2: static/ 디렉터리 생성

- `mutrade/admin/static/.gitkeep` 추가 — Wave 3 index.html 위치 사전 확보
- StaticFiles 마운트 RuntimeError 완전 방지

## TDD Gate Compliance

| Gate | Commit | Status |
|------|--------|--------|
| RED | d5abefc | test(06-02): add failing tests for WebSocket endpoint + StaticFiles + GET / |
| GREEN | 729f3a3 | feat(06-02): WebSocket /ws 엔드포인트 + StaticFiles + GET / 추가 (DASH-03) |

## Commits

| Hash | Type | Description |
|------|------|-------------|
| d5abefc | test | WebSocket + StaticFiles + GET / RED 테스트 7개 |
| 729f3a3 | feat | app.py WebSocket /ws + StaticFiles + GET / 구현 (DASH-03) |
| 6adb5dd | chore | mutrade/admin/static/ 디렉터리 + .gitkeep 추가 |

## Verification Results

```
python3.11 -m pytest tests/ -q --tb=no
1 failed, 121 passed in 2.45s
(실패 1개: test_client.py::test_mock_mode_uses_virtual_account — pre-existing, 이번 플랜 무관)
```

플랜 검증 스크립트: PASS (GET /, /ws, /static 모두 app.routes에 등록됨)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] AsyncMock side_effect coroutine iterator TypeError**
- **Found during:** Task 1 GREEN 단계 (test_websocket_sends_initial_snapshot, test_websocket_disconnect_no_error)
- **Issue:** `AsyncMock(side_effect=never_return)` — asyncio.sleep(60) coroutine 객체를 side_effect에 직접 전달하면 `TypeError: 'coroutine' object is not an iterator` 발생
- **Fix:** AsyncMock side_effect 대신 async 함수 `long_wait`를 `hub.wait_for_change`에 직접 할당
- **Files modified:** `tests/test_app_routes.py`
- **Commit:** 729f3a3

## Known Stubs

없음 — GET /는 FileResponse로 실제 파일을 반환하고, /ws는 실제 hub.get_snapshot()/wait_for_change()를 호출한다. index.html은 Wave 3(06-03-PLAN) 범위로 현재 .gitkeep만 있으며 이는 의도된 상태.

## Threat Flags

없음 — T-06-06(경로 순회)과 T-06-07(WebSocketDisconnect 미처리)은 STRIDE 등록된 위협으로 이번 플랜에서 모두 mitigate 완료.

## Self-Check: PASSED

- [x] `mutrade/admin/app.py` — GET /, /ws, /static 라우트 등록됨
- [x] `mutrade/admin/static/.gitkeep` — 존재
- [x] 커밋 d5abefc, 729f3a3, 6adb5dd 모두 존재
- [x] 121 tests passing (기존 실패 1개 pre-existing)
