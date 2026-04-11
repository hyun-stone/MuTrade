# MuTrade — 자동 트레일링 스탑 트레이딩 봇

## What This Is

한국투자증권 API를 활용한 개인용 자동 주식 매도 프로그램이다. 사용자가 선택한 보유 종목을 시장 운영 시간(09:00~15:30) 동안 실시간으로 모니터링하여, 고점 대비 10% 이상 하락하면 즉시 시장가로 자동 매도한다. 매도 실행 시 Telegram 알림과 로그 파일([TRADE] 마커)로 결과를 기록한다.

## Core Value

조건 충족 시 사람의 개입 없이 즉시 자동 매도하여 손실을 방어한다.

## Current Milestone: v1.1 Admin Dashboard

**Goal:** FastAPI + HTML/JS + WebSocket 기반 관리자 웹 UI를 추가하여 봇 현황 조회, 제어, 거래 이력 확인, 설정 변경을 브라우저에서 수행

**Target features:**
- 현황 조회 — 모니터링 종목별 현재가·고점·하락률 실시간 표시 (WebSocket)
- 봇 제어 — 봇 시작/중지, 종목 추가/제거
- 거래 이력 — 로그 [TRADE] 마커 파싱 → 매도 이력 테이블
- 설정 변경 — config.toml 임계값 등 UI에서 직접 수정

## Current State

**Shipped:** v1.0 MVP (2026-04-08)

- 4 phases, 8 plans, ~11,900 LOC (Python 3.11)
- 78 tests passing
- Tech stack: python-kis 2.1.6, APScheduler, loguru, pydantic-settings, python-telegram-bot 21.x
- Full pipeline: KIS OAuth → 가격 폴링 → 트레일링 스탑 엔진 → 시장가 매도 → Telegram 알림

**Known gaps before live use:**
- `tr_id` 값 프로덕션/모의투자 구분 확인 필요 (KIS Developers 포털)
- 실제 Telegram 봇 토큰·chat_id `.env` 설정 후 end-to-end 알림 수신 확인 필요

## Requirements

### Validated

- ✓ KIS OAuth 2.0 인증 및 자동 토큰 갱신 — v1.0
- ✓ API 키·시크릿 .env 분리 및 .gitignore 적용 — v1.0
- ✓ config.toml로 종목별 매도 조건 설정 — v1.0
- ✓ KRX 공휴일 모니터링 자동 건너뜀 — v1.0
- ✓ 시장 운영 시간(09:00~15:20 KST)에만 가격 폴링 — v1.0
- ✓ 현재가 3~5초 간격 조회 (15 req/s 레이트 리밋 준수) — v1.0
- ✓ KIS API rt_cd 에러 방어 처리 — v1.0
- ✓ 종목별 고점(최고가) 자동 추적 및 state.json 원자적 저장 — v1.0
- ✓ 고점 대비 임계값 하락 시 매도 신호 발생 (드라이런 모드) — v1.0
- ✓ 종목별 개별 임계값 config.toml 설정 — v1.0
- ✓ 드라이런 → 실매도 시장가 주문 실행 — v1.0
- ✓ SELL_PENDING 중복 주문 방지 — v1.0
- ✓ 체결 확인 폴링 — v1.0
- ✓ Telegram 알림 (매도 후 비동기 전송) — v1.0
- ✓ [TRADE] 마커로 거래 이력 로그 기록 — v1.0
- ✓ 봇 시작·종료 시 모니터링 종목·고점 로깅 — v1.0

### Active (v1.1)

- [ ] 관리자 웹 UI — 현황 조회 (종목별 현재가·고점·하락률 WebSocket 실시간)
- [ ] 관리자 웹 UI — 봇 제어 (시작/중지, 종목 추가/제거)
- [ ] 관리자 웹 UI — 거래 이력 ([TRADE] 로그 마커 파싱 테이블)
- [ ] 관리자 웹 UI — 설정 변경 (config.toml 임계값 등 UI 수정)

### Future (v1.2+)

- [ ] 프로덕션 `tr_id` 검증 및 실거래 end-to-end 테스트
- [ ] WebSocket 실시간 시세 수신 (폴링 대체)
- [ ] 초기 고점을 config에서 수동 지정 (봇 시작 전 매수 종목 지원)

### Out of Scope

- 자동 매수 — 손실 방어가 핵심 목적, 매수는 수동 유지
- 복수 증권사 지원 — 한국투자증권 단일 지원으로 복잡도 관리
- 웹/앱 UI — CLI 및 설정 파일로 충분, 과도한 구현 비용 회피
- 백테스팅 — v1 범위 외, 실거래 검증 우선
- KakaoTalk 알림 — Telegram으로 대체 (KakaoTalk OAuth 30일 갱신 복잡도 회피)

## Context

- 한국투자증권 공식 REST API(KIS Developers) 사용, OAuth 2.0 방식 인증
- python-kis 2.1.6 (Soju06/python-kis) — PyPI 최신 버전 기준 선택
- exchange_calendars XKRX로 KRX 공휴일 오프라인 판정
- Telegram 알림은 선택적 (토큰 미설정 시 알림 없이 정상 실행)
- [TRADE] 마커로 logs/mutrade.log에서 거래 이력 grep 추출 가능

## Constraints

- **API**: 한국투자증권 KIS Developers API만 사용
- **운영 환경**: 시장 시간 내 안정적 실행 가능한 로컬 또는 서버 환경 필요
- **보안**: API 키, 앱 시크릿 등 민감 정보는 환경변수 또는 별도 설정 파일로 분리

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 트레일링 스탑 (고점 대비 하락) | 매수가 기준보다 수익을 지킬 수 있어 더 효과적 | ✓ Good — 핵심 방어 로직으로 구현 완료 |
| 시장가 즉시 매도 | 조건 충족 시 확실한 체결 보장 | ✓ Good — PyKis acc.sell(price=None)으로 구현 |
| 선택적 종목 적용 | 전체 보유 종목 강제 적용 시 의도치 않은 매도 위험 | ✓ Good — config.toml 종목 리스트로 구현 |
| Telegram (KakaoTalk 대신) | OAuth 30일 갱신 복잡도 없음, 즉시 설정 가능 | ✓ Good — 선택적 필드로 구현 |
| SELL_PENDING 인-메모리 set | 단일 스레드이므로 Lock 불필요 | ✓ Good — 단순하고 충분 |
| [TRADE] 로그 마커 통합 | DB 없이 grep으로 거래 이력 추출 가능 | ✓ Good — v1 범위에 적합 |
| python-kis 2.1.6 | PyPI 최신 버전 사용 (CLAUDE.md에 4.x 권고했으나 실제 최신은 2.1.6) | ✓ Good — 실사용 가능 |

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
*Last updated: 2026-04-12 — v1.1 Admin Dashboard milestone started*
