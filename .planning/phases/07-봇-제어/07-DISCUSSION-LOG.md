# Phase 7: 봇 제어 - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-18
**Phase:** 07-봇-제어
**Areas discussed:** 봇 시작 트리거, 수동 매도 확인 절차, SELL_PENDING 중 중지 처리

---

## 봇 시작 트리거

| Option | Description | Selected |
|--------|-------------|----------|
| 시장 시간이면 즉시, 외라면 거부 | 09:00~15:20 KST 시간대에만 시작 가능. 외에는 메시지 표시. | ✓ |
| 시간에 상관없이 즉시 실행 | 시장 시간 외에도 강제 시작. 개발/테스트용. | |

**User's choice:** 시장 시간이면 즉시, 외라면 거부

| Option | Description | Selected |
|--------|-------------|----------|
| scheduler.trigger_job() | APScheduler 3.x 공식 API. 기존 market_poll 잡 즉시 발화. | ✓ |
| 별도 스레드 실행 | threading.Thread로 직접 실행. APScheduler 의존성 없음. | |

**User's choice:** scheduler.trigger_job()

---

## 수동 매도 확인 절차

| Option | Description | Selected |
|--------|-------------|----------|
| 확인 다이얼로그 후 실행 | 종목명 포함 확인창 표시 후 실행. 실수 클릭 방지. | ✓ |
| 원클릭 즉시 실행 | 확인 없이 바로 매도 주문. | |

**User's choice:** 확인 다이얼로그 후 실행

| Option | Description | Selected |
|--------|-------------|----------|
| 상단 배너 | 성공/실패 결과를 페이지 상단 배너로 표시. 3~5초 후 사라짐. | ✓ |
| 종목 행 인라인 표시 | 해당 종목 행에 인라인으로 상태 변경. | |

**User's choice:** 상단 배너

---

## SELL_PENDING 중 중지 처리

| Option | Description | Selected |
|--------|-------------|----------|
| 경고 후 강제 중지 가능 | '매도 진행 중입니다. 그래도 중지하시겠습니까?' 다이얼로그 후 중지 가능. | ✓ |
| 친절 경고만, 중지 가능 | 경고 배너만 표시 후 바로 중지 실행. 다이얼로그 없음. | |
| 중지 차단 | SELL_PENDING 중 중지 버튼 비활성화. 완료 후 자동 중지 가능. | |

**User's choice:** 경고 후 강제 중지 가능

---

## Claude's Discretion

- 드라이런 토글 방식: engine.dry_run + executor.dry_run 런타임 직접 수정. 재시작 시 .env 값으로 초기화됨.
- API 라우트 설계: POST /api/start, /api/stop, /api/toggle-dry-run, /api/sell/{code}
- UI 레이아웃: 기존 헤더에 제어 버튼 추가, 수동 매도는 종목 행 마지막 열

## Deferred Ideas

- 드라이런 영속화 — Phase 9 config.toml 편집에서 처리
- 봇 시작 스케줄 변경 — Phase 9 범위
- SELL_PENDING 체결 확인 후 즉시 UI 업데이트 — 현재는 다음 폴링 스냅샷 반영
