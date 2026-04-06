# MuTrade — 자동 트레일링 스탑 트레이딩 봇

## What This Is

한국투자증권 API를 활용한 개인용 자동 주식 매도 프로그램이다. 사용자가 선택한 보유 종목을 시장 운영 시간(09:00~15:30) 동안 실시간으로 모니터링하여, 고점 대비 10% 이상 하락하면 즉시 시장가로 자동 매도한다. 매도 실행 시 알림과 로그를 통해 결과를 기록한다.

## Core Value

조건 충족 시 사람의 개입 없이 즉시 자동 매도하여 손실을 방어한다.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] 한국투자증권 API 연동 (보유 종목 조회, 현재가 조회, 매도 주문)
- [ ] 모니터링 대상 종목을 사용자가 직접 설정 가능
- [ ] 각 종목별 보유 기간 중 최고가(고점) 자동 추적
- [ ] 고점 대비 -10% 이상 하락 시 시장가 즉시 매도 실행
- [ ] 시장 운영 시간(09:00~15:30)에만 모니터링 실행
- [ ] 매도 실행 시 클라이언트 알림 (카카오톡 또는 기타 채널)
- [ ] 매도 이력 및 실행 로그 파일 기록
- [ ] 설정 파일로 종목별 매도 조건 관리

### Out of Scope

- 매수 자동화 — 손실 방어가 핵심 목적, 매수는 수동 유지
- 복수 증권사 지원 — 한국투자증권 단일 지원으로 복잡도 관리
- 웹/앱 UI — CLI 및 설정 파일로 충분, 과도한 구현 비용 회피
- 백테스팅 — v1 범위 외, 실거래 검증 우선

## Context

- 한국투자증권은 공식 REST API(KIS Developers)를 제공하며, OAuth 2.0 방식 인증 사용
- 시장가 매도는 체결 보장이 높아 트레일링 스탑에 적합
- Python 기반 구현이 KIS API 커뮤니티에서 가장 활발함
- 트레일링 스탑 고점은 프로그램 실행 후부터 추적 (과거 고점은 별도 설정 가능하게 고려)

## Constraints

- **API**: 한국투자증권 KIS Developers API만 사용
- **운영 환경**: 시장 시간 내 안정적 실행 가능한 로컬 또는 서버 환경 필요
- **보안**: API 키, 앱 시크릿 등 민감 정보는 환경변수 또는 별도 설정 파일로 분리

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 트레일링 스탑 (고점 대비 하락) | 매수가 기준보다 수익을 지킬 수 있어 더 효과적 | — Pending |
| 시장가 즉시 매도 | 조건 충족 시 확실한 체결 보장 | — Pending |
| 선택적 종목 적용 | 전체 보유 종목 강제 적용 시 의도치 않은 매도 위험 | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-06 after initialization*
