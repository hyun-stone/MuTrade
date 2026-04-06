# Phase 1: Foundation and KIS API Connectivity - Discussion Log

> **감사 추적 전용.** 플래닝·리서치·실행 에이전트의 입력으로 사용하지 말 것.
> 결정 사항은 CONTEXT.md에 기록됨 — 이 로그는 검토된 대안을 보존.

**Date:** 2026-04-06
**Phase:** 01-foundation-and-kis-api-connectivity
**Areas discussed:** KIS API 접근 방식

---

## KIS API 접근 방식

| Option | Description | Selected |
|--------|-------------|----------|
| python-kis 4.x 사용 | OAuth 토큰 관리, fetch_price/create_order/fetch_balance 내장. 구현 속도 빠름. 라이브러리 유지보수 리스크 존재. | ✓ |
| 직접 httpx REST 구현 | KIS 공식 문서 기반 직접 구현. 의존성 제로, 완전한 제어권. OAuth 24시간 만료 + 자동 갱신 직접 구현 필요. | |

**User's choice:** python-kis 4.x 사용
**Notes:** 미지원 엔드포인트는 httpx 폴백으로 보완

---

## 모의투자/실계좌 전환

| Option | Description | Selected |
|--------|-------------|----------|
| .env 파일로 전환 | KIS_MOCK=true/false 환경변수로 모의/실계좌 전환. .env만 바꾸면 돼 실수 위험 낮음. | ✓ |
| config.toml로 전환 | mock_mode = true/false를 config.toml에 선언. 설정 파일 한 곳에 집중 관리. | |

**User's choice:** .env 파일로 전환 (KIS_MOCK=true/false)

---

## Claude's Discretion

- 동시성 모델 (sync vs asyncio)
- config.toml 세부 스키마
- KRX 공휴일 감지 방법
- 프로젝트 디렉터리 구조

## Deferred Ideas

없음 — 논의가 페이즈 범위 내에서 유지됨.
