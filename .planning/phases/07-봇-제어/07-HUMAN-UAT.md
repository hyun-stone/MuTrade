---
status: partial
phase: 07-봇-제어
source: [07-VERIFICATION.md]
started: 2026-04-19T07:01:00+09:00
updated: 2026-04-19T07:01:00+09:00
---

## Current Test

[awaiting human testing]

## Tests

### 1. 헤더 초기 렌더링
expected: 파란 시작 버튼, 회색(비활성) 중지 버튼, 노란/갈색 배경의 "드라이런" 배지가 헤더에 표시된다
result: [pending]

### 2. 시장 시간 외 시작 클릭
expected: 시작 버튼 클릭 시 빨간 배너 "시장 시간이 아닙니다 (09:00~15:20 KST)"가 표시되고 4초 후 자동으로 사라진다
result: [pending]

### 3. 드라이런 배지 클릭
expected: 배지 클릭 시 초록 배너 "실매도 모드로 전환됨..." 표시 + 배지 텍스트/색상이 "실매도"(빨간 배경)로 전환된다
result: [pending]

### 4. 테이블 6열 즉시 매도 버튼
expected: 테이블 마지막 열에 "즉시 매도" 버튼이 표시되고, SELL_PENDING 상태인 행의 버튼은 disabled 상태이다
result: [pending]

### 5. WebSocket is_running 기반 버튼 토글
expected: 봇 실행 중일 때 시작 버튼이 disabled, 중지 버튼이 활성화되고; 봇 정지 시 반대로 토글된다
result: [pending]

## Summary

total: 5
passed: 0
issues: 0
pending: 5
skipped: 0
blocked: 0

## Gaps
