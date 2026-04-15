# Phase 6: 모니터링 대시보드 - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

두 가지 작업을 포함한다:

1. **인프라 버그 수정** — `asyncio.QueueFull` 버그 수정 (INFRA-02), `hub.push_snapshot()`에 `current_price` / `drop_pct` / `SELL_PENDING` 필드 추가 (INFRA-01)
2. **실시간 대시보드 UI** — WebSocket 기반 종목 상태 테이블 (DASH-01~03)

범위 밖: 봇 제어(Phase 7), 거래 이력(Phase 8), Config 편집(Phase 9).

</domain>

<decisions>
## Implementation Decisions

### 프론트엔드 구현 방식

- **D-01:** Vanilla HTML + JavaScript만 사용한다. npm 빌드 단계 없음. FastAPI `StaticFiles`로 `mutrade/admin/static/index.html` 서빙.
- **D-02:** 단일 `index.html` 파일에 HTML + 인라인 CSS + 인라인 JS 모두 포함. 분리 파일 없음.
- **D-03:** WebSocket 연결이 끊어지면 JS에서 `setTimeout`으로 자동 재연결 시도. 사용자가 페이지를 유지하면 자동 복구됨.

### 대시보드 레이아웃 및 스타일

- **D-04:** 테이블 행 레이아웃 — `종목코드 | 현재가 | 고점 | 하락률 | 상태` 열 구성.
- **D-05:** SELL_PENDING 중인 종목은 **번짙이는 빨간 배경 행**으로 강조. CSS `@keyframes` 점멸 애니메이션.
- **D-06:** 봇 비활성(모니터링 세션 없음) 상태 — 빈 테이블 + "봇 대기 중" 메시지 표시. WebSocket은 연결 유지.

### Claude's Discretion

- **QueueFull 버그 수정 방식:** `put_nowait` 호출 전 큐가 가득 찼으면 `get_nowait()`로 기존 항목을 버리고 새 스냅샷 삽입. 항상 최신 상태만 유지하는 패턴. `asyncio.QueueFull` 예외 catch도 병행.
- **SELL_PENDING 노출 방식:** `OrderExecutor`에 `pending_codes() -> frozenset[str]` 공개 메서드 추가. `scheduler.py`의 `push_snapshot()` 호출 시 `executor.pending_codes()`를 함께 전달. `hub.push_snapshot(states, pending_codes)`로 시그니처 확장.
- **WebSocket 엔드포인트:** `/ws` — 연결 시 현재 스냅샷 즉시 전송 후, 변경 발생 때마다 브로드캐스트. `hub.wait_for_change()` await 패턴 활용.
- **`GET /` 라우트:** `index.html` 반환 (StaticFiles mount 또는 FileResponse).

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 요구사항
- `.planning/REQUIREMENTS.md` §INFRA, §DASH — INFRA-01, INFRA-02, DASH-01, DASH-02, DASH-03
- `.planning/ROADMAP.md` §Phase 6 — Goal, Success Criteria 5개 항목

### 핵심 구현 파일 (수정 대상)
- `mutrade/admin/hub.py` — `BotStateHub.push_snapshot()`: 필드 추가 + QueueFull 수정 대상. `asyncio.Queue(maxsize=1)` → 드롭-앤-리플레이스 패턴.
- `mutrade/admin/app.py` — FastAPI 앱 팩토리: `/ws` WebSocket 엔드포인트, StaticFiles 마운트, `GET /` 라우트 추가.
- `mutrade/monitor/scheduler.py` — `push_snapshot()` 호출 시 `executor.pending_codes()` 포함하도록 수정.
- `mutrade/executor/order_executor.py` — `pending_codes() -> frozenset[str]` 공개 메서드 추가.
- `mutrade/engine/models.py` — `SymbolState` 참조 (current_price 필드가 없음 — scheduler에서 prices dict로 별도 전달 필요).

### 기술 스택
- `CLAUDE.md` §Technology Stack — FastAPI, uvicorn, loguru 패턴

</canonical_refs>

<code_context>
## Existing Code Insights

### 버그 위치
- `mutrade/admin/hub.py:54` — `self._change_queue.put_nowait(dict(serialized))`: `asyncio.Queue(maxsize=1)` + put_nowait 조합. WebSocket 브로드캐스트가 큐를 비우기 전에 두 번 push되면 `asyncio.QueueFull` 발생.

### SymbolState 필드 현황
- `mutrade/engine/models.py` `SymbolState`: `code`, `peak_price`, `warm` 필드만 존재. `current_price`가 없음.
- `scheduler.py`의 `poll_prices()` 반환값 `prices: dict[str, float]`에 현재가가 있음 — `push_snapshot(engine.states, prices)` 형태로 함께 전달해야 함.

### 재사용 가능한 패턴
- `hub.wait_for_change()` — WebSocket 브로드캐스트 루프의 await 포인트 (이미 구현됨)
- `hub.is_running()` — 봇 활성 상태 확인 (이미 구현됨)
- `app.state.hub` — FastAPI dependency injection 없이 hub 접근 가능

### 신규 추가 필요
- `mutrade/admin/static/` 디렉터리
- `mutrade/admin/static/index.html` — 단일 파일 대시보드

</code_context>

<specifics>
## Specific Ideas

- SELL_PENDING 강조: CSS `@keyframes blink { 0%, 100% { background: #fee2e2; } 50% { background: #fca5a5; } }` 패턴 — 번짙이는 빨간 배경
- 빈 상태 메시지: "봇 대기 중 — 장 운영 시간(09:00~15:30 KST)에 자동 시작됩니다"
- 테이블 헤더: 종목코드, 현재가, 고점, 하락률, 상태

</specifics>

<deferred>
## Deferred Ideas

없음.

</deferred>

---

*Phase: 06-모니터링-대시보드*
*Context gathered: 2026-04-13*
