# Phase 2: Trailing Stop Engine - Context

**Gathered:** 2026-04-07
**Status:** Ready for planning

<domain>
## Phase Boundary

종목별 고점(high-water mark) 추적, 재시작 후 복원, 임계값 하락 시 매도 신호 발생.
이 페이즈는 **드라이런 전용** — 실제 주문은 Phase 3 범위.

Phase 2가 만들어야 할 것: 가격 입력 → 고점 갱신 → 하락률 계산 → 매도 신호 발생 → state.json 저장.

</domain>

<decisions>
## Implementation Decisions

### 초기 고점 설정

- **D-01:** 봇 최초 실행 시(또는 state.json에 해당 종목이 없을 때) **첫 번째 폴링 가격을 초기 고점으로 설정**한다. 별도의 수동 지정 없이 즉시 추적 시작.
- **D-02:** 재시작 시 state.json이 있으면 고점 데이터를 복원한다. state.json의 종목과 config.toml의 종목이 불일치할 때 **config.toml 기준 우선** — config에 있는 종목만 추적, config에 없는 종목은 무시, config에 신규 추가된 종목은 현재가로 초기화.

### Claude's Discretion

- **드라이런 모드 활성화:** Phase 1의 `KIS_MOCK`과 별개로 `DRY_RUN` 환경변수(Settings에 추가)를 두거나, `KIS_MOCK=true`일 때 자동으로 dry-run으로 동작하는 방식 중 하나를 Claude가 선택. 두 모드의 조합(KIS_MOCK=true + DRY_RUN=false)이 의미가 있는지 판단하여 결정.
- **매도 신호 인터페이스:** `engine.tick(prices: dict) -> list[SellSignal]` 반환값 패턴 또는 콜백 패턴 중 Phase 3 설계에 가장 자연스러운 방식 선택. Phase 3 플래너가 이 인터페이스를 기반으로 주문 실행을 붙임.
- **신호 발생 후 종목 처리:** 매도 신호 발생 후 해당 종목의 모니터링 지속 여부는 Phase 3에서 주문 체결 완료 통보를 받는 구조로 설계. 드라이런 모드에서는 신호 발생 후에도 계속 모니터링 (재발생 가능, 로그로 확인).
- **상태 저장 빈도:** 고점이 갱신될 때마다 원자적 쓰기(tempfile + rename). 매 폴링마다 쓰지 않음.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 요구사항
- `.planning/REQUIREMENTS.md` §트레일링 스탑 엔진 (ENG) — ENG-01 ~ ENG-05: 고점 추적, state.json 원자적 저장, 하락률 계산, 종목별 임계값, 드라이런 모드
- `.planning/ROADMAP.md` §Phase 2 — Goal, success criteria, depends on Phase 1

### 기반 코드 (Phase 1 산출물)
- `mutrade/config/loader.py` — `AppConfig`, `SymbolConfig` (threshold 필드 포함). Phase 2 엔진이 이 타입을 그대로 사용
- `mutrade/kis/price_feed.py` — `poll_prices(kis, config) -> dict[str, float]`. 엔진의 가격 입력 소스
- `mutrade/settings.py` — `Settings` (pydantic-settings). DRY_RUN 필드 추가 위치
- `mutrade/monitor/scheduler.py` — 폴링 루프. Phase 2 엔진 호출 지점

### 기술 스택
- `CLAUDE.md` §Technology Stack — 의존성 목록 및 금지 목록

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `mutrade/config/loader.py::SymbolConfig` — `threshold: float` 필드 이미 존재 (ENG-04 완료)
- `mutrade/kis/price_feed.py::poll_prices()` — `dict[str, float]` 반환. 엔진 입력으로 바로 사용 가능
- `mutrade/settings.py::Settings` — pydantic-settings. `DRY_RUN: bool = False` 필드 추가만 하면 됨
- `tests/` — pytest 기반 테스트 스캐폴드 존재. `test_price_feed.py` 패턴 참조

### Established Patterns
- 동기(sync) 구현 — Phase 1은 동기 폴링 루프. Phase 2 엔진도 동기로 일관성 유지
- `loguru` 로깅 — `logger.info/debug/error()` 패턴 사용
- frozen dataclass — `AppConfig`, `SymbolConfig`가 frozen dataclass. 엔진 상태 객체는 mutable 필요
- `getattr(e, 'attr', None)` 패턴 — mock 호환 에러 처리

### Integration Points
- `mutrade/monitor/scheduler.py` — `poll_prices()` 호출 후 엔진 `tick()` 호출 추가 위치
- `mutrade/main.py` — 엔진 인스턴스 생성 및 스케줄러에 전달

</code_context>

<specifics>
## Specific Ideas

- state.json 경로: `logs/state.json` 또는 프로젝트 루트 `state.json` — Claude 결정
- ENG-02 "원자적 저장": `tempfile.NamedTemporaryFile` + `os.replace()` 패턴으로 전원 차단에도 안전하게
- 드라이런 매도 신호 로그 예시: `"[DRY-RUN] 매도 신호: 005930 (삼성전자) 현재가=68,000 고점=76,000 하락률=10.5%"`

</specifics>

<deferred>
## Deferred Ideas

- `initial_peak` config.toml 수동 지정 (ENG-V2-01) — v2 범위. 현재가 초기화로 v1 충분
- WebSocket 실시간 시세 (FEED-V2-01) — v2 범위

</deferred>

---

*Phase: 02-trailing-stop-engine*
*Context gathered: 2026-04-07*
