---
phase: 05-process-architecture-migration
plan: 01
subsystem: admin
tags: [fastapi, threading, asyncio, tdd, bridge]
dependency_graph:
  requires: []
  provides: [BotStateHub, FastAPI app factory]
  affects: [mutrade/admin/hub.py, mutrade/admin/app.py]
tech_stack:
  added: [fastapi==0.135.3, uvicorn[standard]==0.44.0, jinja2==3.1.6, python-multipart==0.0.26]
  patterns: [threading.RLock, asyncio.Queue, call_soon_threadsafe, FastAPI lifespan]
key_files:
  created:
    - mutrade/admin/__init__.py
    - mutrade/admin/hub.py
    - mutrade/admin/app.py
    - tests/test_hub.py
  modified:
    - pyproject.toml
decisions:
  - "asyncio.Queue(maxsize=1) 선택: 최신 스냅샷만 유지, 큐 폭발 방지 (T-05-02 accept)"
  - "call_soon_threadsafe로 스레드 → asyncio 큐 삽입: 별도 Lock 없이 스레드 안전 보장"
  - "get_snapshot() dict() 복사본 반환: 호출자 수정이 내부 상태에 영향 없음 (T-05-01 mitigate)"
  - "attach_loop 없이 push_snapshot() 호출 시 RuntimeError 억제: shutdown 중 오류 방지"
metrics:
  duration: "약 20분"
  completed: "2026-04-12"
  tasks_completed: 2
  tasks_total: 2
  files_created: 4
  files_modified: 1
---

# Phase 5 Plan 01: BotStateHub + FastAPI 최소 앱 인프라 Summary

**One-liner:** threading.RLock + asyncio.Queue + call_soon_threadsafe 패턴으로 APScheduler 스레드와 uvicorn asyncio 루프 사이 상태 브릿지 구현

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | BotStateHub 구현 (TDD) | 8c70b9d | mutrade/admin/__init__.py, mutrade/admin/hub.py, tests/test_hub.py |
| 2 | FastAPI 최소 앱 + pyproject.toml 의존성 추가 | 507bfcf | mutrade/admin/app.py, pyproject.toml |

## What Was Built

### BotStateHub (mutrade/admin/hub.py)

APScheduler 봇 폴링 스레드와 FastAPI asyncio 이벤트 루프 사이의 상태 브릿지.

- `attach_loop(loop)`: FastAPI lifespan startup에서 호출, asyncio 이벤트 루프 연결
- `push_snapshot(states)`: APScheduler 스레드에서 호출, `call_soon_threadsafe`로 asyncio.Queue에 삽입
- `get_snapshot()`: dict() 복사본 반환, 내부 상태 보호
- `wait_for_change()`: WebSocket 브로드캐스트용 async 메서드
- `request_stop/clear_stop/is_stop_requested`: threading.Event 기반 스레드 안전 플래그
- `set_running/is_running`: 봇 실행 상태 관리

### FastAPI 앱 팩토리 (mutrade/admin/app.py)

- `create_app(hub, **kwargs)`: FastAPI 인스턴스 생성
- lifespan startup: `asyncio.get_running_loop()`로 루프 획득 후 `hub.attach_loop()` 호출
- lifespan shutdown: `hub.request_stop()` + scheduler 종료 (선택적)
- `GET /health`: `{"status": "ok", "bot_running": bool, "stop_requested": bool}` 반환

## Test Results

- TDD RED: 10개 테스트 실패 확인 후 구현
- TDD GREEN: 10개 테스트 모두 PASS
- 전체 테스트: 88개 PASS (기존 78개 + 신규 10개, regression 없음)

## Deviations from Plan

### 추가 테스트 (Rule 2 — 누락 기능 자동 추가)

플랜의 8개 테스트 명세 외에 2개 테스트를 추가했다:
- `test_get_snapshot_returns_copy_not_reference`: T-05-01 위협 모델의 복사본 반환 검증
- `test_push_snapshot_serializes_dataclass_like_objects`: SymbolState-like 객체 직렬화 검증

두 테스트 모두 threat_model에서 `mitigate` disposition으로 지정된 T-05-01 보호를 위해 필요한 정확성 요구사항이다.

## Known Stubs

없음. 모든 인터페이스가 완전히 구현되었다.

## Threat Flags

없음. 새로운 위협 표면이 추가되지 않았다. `/health` 엔드포인트는 플랜의 threat_model(T-05-03, T-05-04)에서 이미 `accept`로 처리되었다.

## Self-Check: PASSED

파일 존재 확인:
- mutrade/admin/__init__.py: FOUND
- mutrade/admin/hub.py: FOUND
- mutrade/admin/app.py: FOUND
- tests/test_hub.py: FOUND

커밋 확인:
- b0718a1 (TDD RED): FOUND
- 8c70b9d (feat BotStateHub): FOUND
- 507bfcf (feat FastAPI app): FOUND
