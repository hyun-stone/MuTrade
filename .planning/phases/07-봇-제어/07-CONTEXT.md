# Phase 7: 봇 제어 - Context

**Gathered:** 2026-04-18
**Status:** Ready for planning

<domain>
## Phase Boundary

사용자가 브라우저 UI에서 봇 세션을 시작·중지하고, 드라이런 모드를 토글하며, 특정 종목을 수동으로 즉시 시장가 매도할 수 있다.

**범위 내:** CTRL-01 ~ CTRL-04 (시작, 중지, 드라이런 토글, 수동 매도)
**범위 밖:** 거래 이력(Phase 8), config.toml 편집(Phase 9)

</domain>

<decisions>
## Implementation Decisions

### 봇 시작 트리거

- **D-01:** 시작 버튼은 시장 시간(09:00~15:20 KST)에만 동작한다. 시장 시간 외에 누르면 "시장 시간이 아닙니다 (09:00~15:20 KST)" 메시지를 표시하고 실행하지 않는다. 실수 매도 방지.
- **D-02:** 시작 메커니즘은 `scheduler.trigger_job("market_poll")`을 사용한다. 기존 `create_poll_session()` 클로저를 그대로 활용하며 APScheduler 3.x 공식 API로 즉시 발화.
- **D-03:** `POST /api/start` 엔드포인트에서 시장 시간 체크 → `scheduler.trigger_job()` 호출. `hub.is_running()`이 True이면 이미 실행 중이므로 409 응답.

### 봇 중지

- **D-04:** `POST /api/stop` 엔드포인트에서 `hub.request_stop()` 호출. 이미 구현된 `stop_event` 플래그를 활용 — `run_session()` 루프 최상단에서 감지하여 세션 종료.
- **D-05:** SELL_PENDING 중인 종목이 있을 때 중지 요청 시 "매도 진행 중인 종목이 있습니다. 그래도 중지하시겠습니까?" 확인 다이얼로그를 표시한다. 사용자가 확인하면 강제 중지 실행.
- **D-06:** SELL_PENDING 여부는 `hub.get_snapshot()`에서 `sell_pending: true` 필드로 프론트엔드가 판단한다. 별도 API 호출 불필요.

### 드라이런 토글

- **D-07:** `POST /api/toggle-dry-run` 엔드포인트에서 `engine.dry_run`과 `executor.dry_run`을 런타임에 직접 수정한다. `.env` 파일은 변경하지 않으므로 재시작 시 원래 값으로 초기화된다.
- **D-08:** 현재 드라이런 모드 여부는 WebSocket 스냅샷 데이터에 `dry_run: bool` 필드로 포함하여 대시보드에 실시간 반영한다. 헤더에 "드라이런" / "실매도" 배지로 표시.
- **D-09 (Claude 재량):** 토글 API 응답에 "재시작 시 .env 설정으로 초기화됩니다" 안내 포함.

### 수동 매도

- **D-10:** 종목 테이블 각 행에 "즉시 매도" 버튼 추가. 클릭 시 "[종목명(코드)]을 시장가로 매도하시겠습니까?" 확인 다이얼로그 표시 후 실행.
- **D-11:** `POST /api/sell/{code}` 엔드포인트에서 `executor.execute()` 직접 호출 (SellSignal 생성 후 전달). 수동 매도는 `dry_run` 모드에 관계없이 항상 실거래 실행.
- **D-12 (Claude 재량):** SELL_PENDING 중인 종목 행의 "즉시 매도" 버튼은 비활성화(disabled). 중복 주문 방지.
- **D-13:** 수동 매도 실행 결과는 페이지 상단 배너로 표시 (성공: "매도 주문 제출됨 — 체결 확인 필요", 실패: 오류 메시지). 배너는 3~5초 후 자동으로 사라진다.

### Claude's Discretion

- **API 라우트 설계:** `POST /api/start`, `POST /api/stop`, `POST /api/toggle-dry-run`, `POST /api/sell/{code}` — 모두 JSON 응답 (`{"ok": true, "message": "..."}`)
- **UI 레이아웃:** 기존 `index.html` 헤더 영역에 시작/중지 버튼, 드라이런 배지 추가. 수동 매도 버튼은 각 종목 행 마지막 열.
- **드라이런 토글:** `engine.dry_run` + `executor.dry_run` 런타임 직접 수정. 스레드 안전성 — `hub._lock` 내에서 수정하거나 `engine`과 `executor`에 setter 추가.
- **`hub.get_snapshot()` 확장:** `dry_run` 필드 포함. `hub.push_snapshot()` 시그니처에 `dry_run: bool` 인자 추가 또는 hub 내부에서 `engine.dry_run` 직접 읽기.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 요구사항
- `.planning/REQUIREMENTS.md` §CTRL — CTRL-01, CTRL-02, CTRL-03, CTRL-04
- `.planning/ROADMAP.md` §Phase 7 — Goal, Success Criteria 5개 항목

### 핵심 구현 파일 (수정/추가 대상)
- `mutrade/admin/hub.py` — `BotStateHub`: `request_stop()`, `clear_stop()`, `set_running()`, `is_running()` 이미 구현됨. `push_snapshot()` 시그니처에 `dry_run` 필드 추가 필요.
- `mutrade/admin/app.py` — FastAPI 앱 팩토리: `POST /api/*` 라우트 추가. `engine`, `config`, `scheduler` 이미 kwargs로 주입됨.
- `mutrade/monitor/scheduler.py` — `create_poll_session()` / `start_scheduler()`: 기존 코드 변경 최소화. `trigger_job()` 외부 호출로 즉시 발화.
- `mutrade/admin/static/index.html` — 기존 대시보드에 제어 버튼 및 배너 UI 추가.
- `mutrade/executor/order_executor.py` — 수동 매도용 `execute()` 직접 호출 경로 확인.

### 기술 스택 참고
- `CLAUDE.md` §Technology Stack — APScheduler BackgroundScheduler API

### State.md 블로커 메모
- STATE.md: "Phase 7 시작 전: `scheduler.trigger_job()` vs `.get_job("market_poll").modify()` — APScheduler 3.11.2 API 확인 필요" → **결정됨: `trigger_job()` 사용.**

</canonical_refs>

<code_context>
## Existing Code Insights

### 재사용 가능한 자산
- `hub.request_stop()` / `hub.clear_stop()` / `hub.is_stop_requested()` — 중지 플래그 완전 구현
- `hub.set_running(True/False)` / `hub.is_running()` — 실행 상태 추적
- `hub.push_snapshot(states, prices, pending_codes)` — 스냅샷 브로드캐스트 (dry_run 필드 추가 필요)
- `create_app(hub, scheduler, engine, config)` — `scheduler`, `engine` 이미 kwargs로 주입됨
- `executor.execute(sig)` — SellSignal → 실제 매도 주문 (OrderExecutor)
- `executor.pending_codes()` → frozenset[str] — SELL_PENDING 종목 코드 집합
- `index.html` `renderTable()` / `blink-sell` CSS — 기존 대시보드 UI

### 통합 진입점
- `/api/*` 라우트는 `create_app()` 내부에서 등록 (기존 `/health`, `/`, `/ws`, `/static` 패턴 따라)
- `websocket.app.state.hub` 패턴 → `request.app.state.hub` + `request.app.state.scheduler` + `request.app.state.engine` 으로 의존성 접근

### 주의 사항
- `scheduler.trigger_job("market_poll")` — APScheduler 3.x에서는 `modify()` 대신 `trigger_job()` 사용. 플래너가 APScheduler 3.11.2 릴리즈 노트 확인 권장.
- `engine.dry_run` / `executor.dry_run` 런타임 수정은 APScheduler 백그라운드 스레드에서 읽히므로 가시성(visibility) 보장을 위해 `threading.Event` 또는 락 패턴 고려.

</code_context>

<specifics>
## Specific Ideas

- 시작/중지 버튼: 헤더 오른쪽에 위치. 상태에 따라 "시작" 또는 "중지"만 활성화 (현재 `is_running()` 상태 기반)
- 드라이런 배지: 헤더에 "드라이런 모드" (노란 배지) / "실매도 모드" (빨간 배지) 표시
- 상단 배너: `<div id="banner">` — 성공 시 초록, 실패 시 빨간. JavaScript `setTimeout(hideBanner, 4000)`으로 4초 후 자동 숨김
- 수동 매도 확인: `window.confirm('[종목명(코드)]을 시장가로 매도하시겠습니까?'` 또는 인라인 다이얼로그

</specifics>

<deferred>
## Deferred Ideas

- 드라이런 모드 `.env` 영속화 (재시작 시도 유지) — Phase 9 Config 편집에서 처리 가능
- 봇 자동 시작 스케줄 변경 (시장 개장 시간 수정) — Phase 9 config.toml 편집 범위
- SELL_PENDING 완료 알림 (매도 체결 확인 후 UI 업데이트) — 현재는 다음 폴링 주기 스냅샷으로 반영

</deferred>

---

*Phase: 07-봇-제어*
*Context gathered: 2026-04-18*
