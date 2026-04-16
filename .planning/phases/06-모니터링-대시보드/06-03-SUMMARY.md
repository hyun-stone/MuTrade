---
phase: 06-모니터링-대시보드
plan: "03"
subsystem: admin/static/index.html
tags: [dashboard, websocket, vanilla-html, inline-css, inline-js, dash-01, dash-02, dash-03]
dependency_graph:
  requires:
    - 06-02 (GET / FileResponse + /ws WebSocket 엔드포인트 + /static StaticFiles)
  provides:
    - mutrade/admin/static/index.html (단일 파일 대시보드 — HTML + 인라인 CSS + 인라인 JS)
  affects:
    - mutrade/admin/static/index.html
tech_stack:
  added: []
  patterns:
    - "Vanilla HTML + 인라인 CSS + 인라인 JS 단일 파일 (외부 의존성 없음)"
    - "new WebSocket('ws://' + location.host + '/ws') 자동 연결"
    - "setTimeout(connect, 3000) 재연결 패턴"
    - "innerHTML 삽입 + sanitizeCode() XSS 방어 (T-06-08)"
key_files:
  created:
    - mutrade/admin/static/index.html
  modified: []
decisions:
  - "sym.code에 sanitizeCode() 적용 — innerHTML 삽입 시 T-06-08 XSS 방어, 개인용 봇이나 KIS 종목코드 형식 보장"
  - "template literal 대신 문자열 연결로 innerHTML 행 생성 — sanitizeCode() 삽입 포인트 명시"
metrics:
  duration_seconds: 53
  completed_date: "2026-04-16"
  tasks_completed: 1
  tasks_total: 2
  files_modified: 1
requirements_satisfied:
  - DASH-01
  - DASH-02
  - DASH-03
---

# Phase 6 Plan 03: 단일 파일 모니터링 대시보드 index.html Summary

**One-liner:** Vanilla HTML + 인라인 CSS + 인라인 JS 단일 파일로 WebSocket 자동 갱신 모니터링 대시보드 구현 — 외부 CDN 없이 브라우저에서 즉시 동작

## What Was Built

### Task 1: index.html — 단일 파일 대시보드 구현 (DASH-01, DASH-02, DASH-03)

- `mutrade/admin/static/index.html` — HTML + 인라인 CSS + 인라인 JS 단일 파일
- 헤더 바: "MuTrade 모니터링" 제목 + WebSocket 연결 상태 dot + 텍스트
  - connected: 파란 점 "실시간 연결" / reconnecting: amber 점 "재연결 중..." / disconnected: gray 점 "연결 끊김"
- 테이블 5열 구성: 종목코드(100px 좌) / 현재가(120px 우) / 고점(120px 우) / 하락률(100px 우) / 상태(120px 중앙)
- SELL_PENDING 행 `blink-sell` 애니메이션 (`#450a0a` ↔ `#7f1d1d`, 1s ease-in-out infinite)
- 빈 상태 "봇 대기 중" + 부제 "장 운영 시간(09:00~15:30 KST)에 자동 시작됩니다"
- WebSocket 자동 재연결: `ws.onclose` → `setTimeout(connect, 3000)`
- 하락률 색상 3단계: 0~-5% gray / -5~-9% amber / -9% 이상 red
- `warm: false` 시 하락률 "—" 표시, 상태 배지 "워밍업"
- T-06-08 XSS 방어: `sanitizeCode()` 함수로 `sym.code` 필드 sanitize

### Task 2: 브라우저 검증 (checkpoint:human-verify) — 대기 중

Wave 1~3 전체 통합 후 브라우저에서 http://localhost:8000 접속하여 다음을 확인해야 함:
- 헤더 파란 점 "실시간 연결" 표시
- 봇 미실행 시 "봇 대기 중" 메시지
- 봇 실행 시 종목 테이블 표시 + 자동 갱신
- SELL_PENDING 행 blink-sell 애니메이션
- 개발자도구 Console 오류 없음
- Network 탭 WS 연결 및 메시지 수신 확인

**상태: pending human verification**

## Commits

| Hash | Type | Description |
|------|------|-------------|
| 1b55586 | feat | 단일 파일 모니터링 대시보드 index.html 구현 (DASH-01, DASH-02, DASH-03) |

## Verification Results

```
python3 -c "... assertions ..."
PASS: index.html 검증 완료

확인 항목:
- MuTrade 모니터링 제목 ✓
- symbol-table-body tbody id ✓
- blink-sell 애니메이션 ✓
- 봇 대기 중 빈 상태 메시지 ✓
- 장 운영 시간(09:00~15:30 KST) 부제 ✓
- renderTable 함수 ✓
- location.host WebSocket 연결 코드 ✓
- setTimeout(connect 자동 재연결 ✓
- sell-pending 클래스 ✓
- 실시간 연결 WS 상태 텍스트 ✓
- 재연결 중 텍스트 ✓
- #450a0a blink-sell 다크 레드 ✓
- 매도 대기 / 모니터링 중 / 워밍업 상태 배지 ✓
- 외부 CDN 없음 ✓
```

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Security] T-06-08 XSS 방어: sanitizeCode() 추가**
- **Found during:** Task 1 구현 (threat_model T-06-08 검토)
- **Issue:** PLAN.md threat_model에서 `sym.code.replace(/[^0-9A-Za-z]/g, '')` sanitize를 `mitigate` disposition으로 명시. innerHTML 삽입 시 XSS 방어 필요.
- **Fix:** `sanitizeCode(code)` 함수 추가, `sym.code` 출력 시 항상 적용
- **Files modified:** `mutrade/admin/static/index.html`
- **Commit:** 1b55586

## Known Stubs

없음 — index.html은 WebSocket으로 실제 데이터를 수신하여 renderTable()로 렌더링한다. 하드코딩된 데이터 없음. Wave 1(hub.py), Wave 2(app.py /ws)가 제공하는 실제 스냅샷 데이터를 소비한다.

## Threat Flags

없음 — T-06-08(innerHTML XSS) sanitizeCode()로 mitigate 완료. T-06-09(WebSocket 무한 루프) accept 처리. T-06-10(외부 CDN) CDN 완전 차단 및 verify 스크립트로 검증 완료.

## Self-Check: PASSED

- [x] `mutrade/admin/static/index.html` — 존재 및 핵심 요소 포함
- [x] 커밋 1b55586 존재
- [x] 외부 CDN 없음 (verify 스크립트 통과)
- [x] blink-sell, renderTable, 봇 대기 중, setTimeout 재연결, sell-pending 모두 존재
