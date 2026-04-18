---
phase: 07-봇-제어
plan: "02"
subsystem: ui
tags: [html, javascript, websocket, fetch-api, dashboard, bot-control]

# Dependency graph
requires:
  - phase: 07-봇-제어
    provides: "4개 REST 제어 API (POST /api/start, /api/stop, /api/toggle-dry-run, /api/sell/{code}) 및 WebSocket _meta 필드"
  - phase: 06-모니터링-대시보드
    provides: "index.html 기반 대시보드, WebSocket /ws 연결, renderTable, sanitizeCode 패턴"
provides:
  - "헤더 시작/중지 버튼 (btn-start, btn-stop) — WebSocket is_running에 따라 disabled 토글"
  - "드라이런 배지 (dry-run-badge) — 클릭 시 toggle-dry-run API 호출, WebSocket dry_run에 따라 텍스트/색상 갱신"
  - "상단 배너 (banner role=alert) — 성공(초록)/실패(빨강) 피드백, 4초 자동 숨김"
  - "테이블 6열 확장 — 액션 열에 즉시 매도 버튼 (SELL_PENDING 행은 disabled)"
  - "JS 핸들러: startBot, stopBot, toggleDryRun, manualSell, showBanner, updateDryRunBadge"
  - "renderTable _meta 키 필터 (Pitfall 4 방어)"
affects:
  - "07-봇-제어 이후 UI 관련 작업"

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "fetch POST → JSON 응답 → showBanner 패턴 (API 피드백 공통 패턴)"
    - "_lastSnapshot 전역 변수로 최신 WebSocket 스냅샷 캐싱"
    - "_meta 키 분리 패턴 — WebSocket 데이터에서 메타 정보와 종목 데이터를 분리"

key-files:
  created: []
  modified:
    - mutrade/admin/static/index.html

key-decisions:
  - "confirm() 다이얼로그로 SELL_PENDING 중지 및 즉시 매도 이중 확인 — 실수 방지"
  - "showBanner 4초 자동 숨김 타이머 — bannerTimer로 중복 호출 시 리셋"
  - "stopBot에서 _lastSnapshot 참조로 SELL_PENDING 여부 판단 — 별도 API 호출 불필요"

patterns-established:
  - "fetch POST 핸들러 패턴: fetch('/api/...', {method: 'POST'}).then(r => r.json()).then(body => showBanner(...))"
  - "_meta 분리 패턴: Object.keys(data).forEach(k => { if (k !== '_meta') symbols[k] = data[k]; })"

requirements-completed:
  - CTRL-01
  - CTRL-02
  - CTRL-03
  - CTRL-04

# Metrics
duration: 15min
completed: 2026-04-18
---

# Phase 07-02: 봇 제어 프론트엔드 UI Summary

**WebSocket _meta 기반으로 실시간 상태가 토글되는 시작/중지 버튼, 드라이런 배지, 배너, 즉시 매도 버튼을 index.html에 추가**

## Performance

- **Duration:** 15 min
- **Started:** 2026-04-18T05:55:00Z
- **Completed:** 2026-04-18T06:10:00Z
- **Tasks:** 1 (+ 1 checkpoint)
- **Files modified:** 1

## Accomplishments

- 헤더에 시작/중지 버튼과 드라이런 배지 추가 — WebSocket is_running/dry_run 값에 따라 실시간 상태 토글
- 상단 배너 요소 추가 — API 호출 결과를 성공(초록)/실패(빨강)으로 표시하고 4초 후 자동 숨김
- 테이블 5열 → 6열 확장 — 마지막 "액션" 열에 즉시 매도 버튼 (SELL_PENDING 상태이면 disabled)
- 사용자 확인(confirm) 다이얼로그로 중지 시 SELL_PENDING 경고, 즉시 매도 시 이중 확인
- renderTable에 `_meta` 키 필터 추가 — 종목 코드로 잘못 렌더링되는 Pitfall 4 방어

## Task Commits

1. **Task 1: index.html 헤더 제어 영역 + 배너 + 테이블 6열 + JS 핸들러 전체 구현** - `ed1819a` (feat)

**Plan metadata:** (this SUMMARY commit)

## Files Created/Modified

- `mutrade/admin/static/index.html` - 헤더 제어 영역(시작/중지 버튼, 드라이런 배지), 배너 요소, 테이블 6열(액션 열), JS 핸들러 6종(startBot, stopBot, toggleDryRun, manualSell, showBanner, updateDryRunBadge), ws.onmessage 및 renderTable 수정

## Decisions Made

- confirm() 내장 다이얼로그 사용 — Plan 01에서 확립된 UI 단순성 방침에 따라 외부 모달 라이브러리 불사용
- stopBot에서 _lastSnapshot 전역 변수로 SELL_PENDING 여부 판단 — API 추가 호출 없이 클라이언트 캐시 활용
- bannerTimer로 showBanner 중복 호출 시 타이머 리셋 — 배너가 겹쳐서 표시되는 문제 방지

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 07의 모든 계획된 기능이 완성됨 (REST API 4종 + 프론트엔드 제어 UI)
- 봇을 웹 대시보드에서 완전히 제어할 수 있는 상태
- 향후 작업: 실제 시장 운영 시간 테스트, 트레일링 스탑 조건 검증

---
*Phase: 07-봇-제어*
*Completed: 2026-04-18*
