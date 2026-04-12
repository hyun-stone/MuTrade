# ROADMAP: MuTrade — 자동 트레일링 스탑 트레이딩 봇

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-04-08)
- 🚧 **v1.1 Admin Dashboard** — Phases 5-8 (in progress)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-4) — SHIPPED 2026-04-08</summary>

- [x] Phase 1: Foundation and KIS API Connectivity (2/2 plans) — completed 2026-04-06
- [x] Phase 2: Trailing Stop Engine (2/2 plans) — completed 2026-04-06
- [x] Phase 3: Order Execution (2/2 plans) — completed 2026-04-08
- [x] Phase 4: Notifications and Operational Polish (2/2 plans) — completed 2026-04-08

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

### v1.1 Admin Dashboard (Phases 5-8)

- [ ] Phase 5: Process Architecture Migration (0/2 plans)
- [ ] Phase 6: Real-time Dashboard (0/0 plans)
- [ ] Phase 7: Bot Control and Trade History (0/0 plans)
- [ ] Phase 8: Config Editor (0/0 plans)

---

## Phase Details — v1.1 Admin Dashboard

### Phase 5: Process Architecture Migration

**Goal:** FastAPI/uvicorn이 메인 스레드를 차지할 수 있도록 APScheduler를 BackgroundScheduler로 전환하고, 봇 폴링 스레드와 FastAPI asyncio 루프 사이의 상태 브릿지(BotStateHub)를 구축한다.

**Requirements:** (인프라 단계 — 직접 사용자 요구사항 없음, Phase 6~8의 전제 조건)

**Plans: 2 plans**

Plans:
- [ ] 05-01-PLAN.md — BotStateHub + FastAPI 최소 앱 (TDD)
- [ ] 05-02-PLAN.md — BackgroundScheduler 전환 + main.py uvicorn 진입점 재구성

**Key deliverables:**
- `mutrade/admin/hub.py` — `BotStateHub` (threading.RLock + asyncio.Queue + threading.Event)
- `monitor/scheduler.py` — BlockingScheduler → BackgroundScheduler, `hub.push_snapshot()` 연동, `time.sleep` → `stop_event.wait(timeout)`
- `mutrade/main.py` — `uvicorn.run(app, host="0.0.0.0", port=8000)` 진입점으로 재구성

**Success criteria:**
1. `python -m mutrade` 실행 시 FastAPI 서버(포트 8000)와 봇 폴링이 동시에 동작한다
2. 봇 폴링 루프가 BackgroundScheduler 별도 스레드에서 실행되며 uvicorn 이벤트 루프와 충돌하지 않는다
3. 기존 테스트(86개)가 모두 통과한다
4. BotStateHub가 봇 폴링 스레드에서 쓰고 asyncio 루프에서 읽어도 RuntimeError가 발생하지 않는다

---

### Phase 6: Real-time Dashboard

**Goal:** WebSocket 기반 실시간 종목 현황 대시보드를 구현한다. 읽기 전용으로 봇 상태를 브라우저에 표시한다.

**Requirements:** UI-01, UI-02, UI-03, UI-04, UI-05, LOG-01

**Key deliverables:**
- `mutrade/admin/app.py` — FastAPI 앱 팩토리, `/ws` WebSocket 엔드포인트, `/api/status` REST
- `mutrade/admin/ws.py` — `ConnectionManager` (in-memory WebSocket 연결 풀)
- `mutrade/admin/log_reader.py` — `logs/mutrade.log` tail (asyncio.to_thread)
- `mutrade/admin/static/index.html` — 종목 현황 테이블 + WebSocket 클라이언트 (vanilla JS)

**Success criteria:**
1. 브라우저에서 `http://localhost:8000` 접속 시 모니터링 종목의 현재가·고점·하락률·임계값 테이블이 표시된다
2. 가격 변동이 페이지 새로고침 없이 3~5초 이내 자동 반영된다
3. `DRY_RUN=true` 환경에서 화면 상단에 드라이런 경고 배너가 표시된다
4. 각 종목의 상태 배지(모니터링 중 / 매도 신호 / SELL_PENDING)가 실제 엔진 상태와 일치한다
5. 봇 시작 시간과 마지막 가격 업데이트 시각이 표시된다
6. 로그 스트림 패널에 `logs/mutrade.log` 최신 줄이 실시간으로 표시된다

---

### Phase 7: Bot Control and Trade History

**Goal:** 봇 시작/중지·종목 추가/제거·드라이런 토글 제어 기능과 `[TRADE]` 로그 파싱 거래 이력 테이블을 구현한다.

**Requirements:** CTRL-01, CTRL-02, CTRL-03, CTRL-04, HIST-01

**Key deliverables:**
- `mutrade/admin/log_reader.py` — `[TRADE]` 정규식 파서 (로테이션 파일 포함, asyncio.to_thread)
- FastAPI 라우트: `POST /api/bot/start`, `POST /api/bot/stop`, `POST /api/symbols`, `DELETE /api/symbols/{symbol}`, `POST /api/dryrun`
- `index.html` 업데이트 — 제어 버튼, 중지 확인 다이얼로그, 거래 이력 테이블

**Success criteria:**
1. 시작 버튼 클릭 시 봇 폴링이 재개되고, 중지 버튼 클릭 시 확인 다이얼로그 후 폴링이 중단된다
2. 종목 추가/제거가 즉시 모니터링 테이블에 반영된다
3. 드라이런 토글이 즉시 `BotStateHub.dry_run` 상태에 반영된다
4. `[TRADE]` 마커가 있는 로그 줄이 파싱되어 날짜·종목·수량·가격·DRY/LIVE 구분 테이블로 표시된다
5. 봇 중지 후 빠른 재시작 시 중복 폴링 루프가 생성되지 않는다

---

### Phase 8: Config Editor

**Goal:** config.toml의 종목별 임계값을 브라우저에서 편집하고 원자적으로 저장하는 기능을 구현한다.

**Requirements:** CFG-01, CFG-02

**Key deliverables:**
- `mutrade/admin/config_editor.py` — `ConfigEditor` (Pydantic 검증 + tempfile+os.replace() 원자적 쓰기)
- FastAPI 라우트: `GET /api/config`, `PUT /api/config`
- `index.html` 업데이트 — 설정 편집 폼, 유효성 오류 표시, "다음 사이클 적용" 안내

**Success criteria:**
1. 설정 편집 페이지에서 config.toml 현재 내용(종목별 임계값)이 폼으로 표시된다
2. 잘못된 값(예: 음수 임계값, 범위 초과) 입력 시 저장 전 유효성 검증 오류가 인라인으로 표시된다
3. 저장 버튼 클릭 시 config.toml이 원자적으로 업데이트되고 성공 메시지가 표시된다
4. config 저장 중 봇 폴링이 중단되지 않는다
5. 잘못된 입력으로 인해 config.toml 파일이 손상되지 않는다

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation and KIS API Connectivity | v1.0 | 2/2 | Complete | 2026-04-06 |
| 2. Trailing Stop Engine | v1.0 | 2/2 | Complete | 2026-04-06 |
| 3. Order Execution | v1.0 | 2/2 | Complete | 2026-04-08 |
| 4. Notifications and Operational Polish | v1.0 | 2/2 | Complete | 2026-04-08 |
| 5. Process Architecture Migration | v1.1 | 0/2 | Not started | — |
| 6. Real-time Dashboard | v1.1 | 0/— | Not started | — |
| 7. Bot Control and Trade History | v1.1 | 0/— | Not started | — |
| 8. Config Editor | v1.1 | 0/— | Not started | — |

---
*v1.0 archived: 2026-04-08 — See milestones/v1.0-ROADMAP.md for full details*
