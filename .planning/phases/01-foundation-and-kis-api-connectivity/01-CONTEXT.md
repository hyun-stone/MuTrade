# Phase 1: Foundation and KIS API Connectivity - Context

**Gathered:** 2026-04-06
**Status:** Ready for planning

<domain>
## Phase Boundary

KIS OAuth 2.0 인증, 모니터링 종목의 실시간 가격 폴링, 시크릿 보호, 레이트 리밋 준수, API 에러 처리 — 이후 모든 페이즈가 의존하는 기반 레이어를 구축한다.

Phase 2 이후 기능(트레일링 스탑 엔진, 매도 주문, 알림)은 이 페이즈 범위 밖이다.

</domain>

<decisions>
## Implementation Decisions

### KIS API 클라이언트

- **D-01:** `python-kis 4.x`를 메인 KIS API 클라이언트로 사용한다. OAuth 토큰 관리, `fetch_price` / `create_order` / `fetch_balance` 메서드를 활용한다.
- **D-02:** python-kis가 지원하지 않는 엔드포인트(예: KRX 공휴일 확인용 KIS 시장 상태 API)는 `httpx`로 직접 호출하여 보완한다.

### 모의투자 / 실계좌 전환

- **D-03:** 모의투자(paper trading)와 실계좌 전환은 `.env` 파일의 `KIS_MOCK=true/false` 환경변수로 관리한다. Phase 3 테스트 시 `.env`만 바꾸면 전환 가능하도록 한다.

### Claude's Discretion

- 동시성 모델(sync vs asyncio): Claude가 결정 — Phase 1은 단순 폴링 루프이므로 동기 구현이 적합하나, v2 WebSocket 업그레이드를 위한 async 래퍼 구조 여부는 구현 단계에서 판단.
- config.toml 스키마 세부 구조: Claude가 결정 — REQUIREMENTS.md의 CONF-03, ENG-04 기준 충족하는 방향으로 설계.
- KRX 공휴일 감지 방법: Claude가 결정 — `exchange_calendars` 라이브러리 또는 KIS 시장 상태 API 중 더 신뢰성 있는 방법 선택.
- 프로젝트 디렉터리 구조: Claude가 결정 — 단일 파일 vs 모듈 패키지.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 요구사항
- `.planning/REQUIREMENTS.md` — v1 요구사항 전체. Phase 1 담당: CONF-01~04, FEED-01~04
- `.planning/ROADMAP.md` §Phase 1 — 성공 기준 5개 항목 (인증 토큰 출력, 폴링 동작, 에러 처리, .env 보안, KRX 공휴일 스킵)

### 기술 스택
- `CLAUDE.md` §Technology Stack — 권장 라이브러리 목록 및 신뢰도 주석. `python-kis` 검증 액션 포함.

### 외부 참고
- `https://apiportal.koreainvestment.com` — KIS Developers 공식 포털. OAuth2 토큰 엔드포인트, rt_cd 에러 코드, 레이트 리밋 확인
- `https://github.com/Soju06/python-kis` — python-kis GitHub. v4.x 최신 커밋 날짜 및 changelog 확인 필수 (CLAUDE.md 신뢰도 '보통')
- `https://pypi.org/project/python-kis/` — PyPI 최신 버전 확인

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- 없음 — 첫 번째 페이즈, 코드베이스 공백 상태

### Established Patterns
- 아직 없음 — 이 페이즈에서 기반 패턴 확립

### Integration Points
- 이 페이즈에서 생성된 KIS 클라이언트 인스턴스와 가격 피드가 Phase 2 트레일링 스탑 엔진의 입력이 됨

</code_context>

<specifics>
## Specific Ideas

- 모의투자 전환: `.env`의 `KIS_MOCK=true/false` 단일 변수로 처리 — Phase 3 live 테스트 전 paper trading 검증 흐름에 직결
- python-kis 사용 전 PyPI + GitHub 최신 상태 반드시 확인할 것 (CLAUDE.md 명시)

</specifics>

<deferred>
## Deferred Ideas

None — 논의가 페이즈 범위 내에서 유지됨.

</deferred>

---

*Phase: 01-foundation-and-kis-api-connectivity*
*Context gathered: 2026-04-06*
