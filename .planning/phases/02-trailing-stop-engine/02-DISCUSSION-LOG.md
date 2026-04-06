# Phase 2: Trailing Stop Engine - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-07
**Phase:** 02-trailing-stop-engine
**Areas discussed:** 초기 고점 설정

---

## Area: 초기 고점 설정

**Q1: 봇 최초 실행 시 초기 고점 설정 방법**

Options presented:
- 현재가로 초기화 (첫 번째 폴링 가격 = 초기 고점)
- config.toml에서 수동 지정 가능 (없으면 현재가 폴백)

Selected: **현재가로 초기화**

Rationale: 구현 단순, 대부분의 개인 트레이딩 봇 표준 방식. config 수동 지정은 v2(ENG-V2-01)로 이연.

---

**Q2: 재시작 시 config.toml과 state.json 불일치 처리**

Options presented:
- config 우선: config.toml 종목만 추적, 신규는 현재가 초기화, 제거된 종목 무시
- 병합: state.json + config.toml 합집합 추적

Selected: **config 우선**

Rationale: 의도치 않은 모니터링 방지. config에서 제거한 종목은 감시 중단 의도.

---

## Areas Deferred to Claude's Discretion

- 드라이런 모드 활성화: DRY_RUN 별도 플래그 vs KIS_MOCK 통합
- 매도 신호 인터페이스: 콜백 vs 반환값(tick → SellSignal[])
- 신호 후 종목 처리: 모니터링 계속 vs 즉시 제외
- 상태 저장 빈도

*Discussion log generated: 2026-04-07*
