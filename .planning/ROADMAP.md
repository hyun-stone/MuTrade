# ROADMAP: MuTrade — 자동 트레일링 스탑 트레이딩 봇

## Milestones

- ✅ **v1.0 MVP** — Phases 1-4 (shipped 2026-04-08)
- 🔄 **v1.1 Admin UI** — Phases 5-9 (active)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-4) — SHIPPED 2026-04-08</summary>

- [x] Phase 1: Foundation and KIS API Connectivity (2/2 plans) — completed 2026-04-06
- [x] Phase 2: Trailing Stop Engine (2/2 plans) — completed 2026-04-06
- [x] Phase 3: Order Execution (2/2 plans) — completed 2026-04-08
- [x] Phase 4: Notifications and Operational Polish (2/2 plans) — completed 2026-04-08

See `.planning/milestones/v1.0-ROADMAP.md` for full phase details.

</details>

### v1.1 Admin UI

- [x] **Phase 5: Process Architecture Migration** — BotStateHub + BackgroundScheduler + uvicorn 전환 (완료 2026-04-12)
- [ ] **Phase 6: 모니터링 대시보드** — 인프라 버그 수정 + WebSocket 기반 실시간 종목 상태 대시보드
- [ ] **Phase 7: 봇 제어** — UI에서 세션 시작/중지, 드라이런 토글, 수동 매도 실행
- [ ] **Phase 8: 거래 이력** — [TRADE] 로그 파싱 및 매도 이력 목록 표시
- [ ] **Phase 9: Config 편집** — UI에서 config.toml 편집 및 원자적 저장

---

## Phase Details

### Phase 5: Process Architecture Migration ✅ COMPLETE

**Goal:** FastAPI/uvicorn이 메인 스레드를 차지할 수 있도록 APScheduler를 BackgroundScheduler로 전환하고, BotStateHub 스레드 브릿지를 구축한다.
**Completed:** 2026-04-12 (b6f4df6)
**Plans:** 2/2
**Deliverables:** `mutrade/admin/hub.py`, `mutrade/admin/app.py`, `mutrade/monitor/scheduler.py` (BackgroundScheduler), `mutrade/main.py` (uvicorn entrypoint)

---

### Phase 6: 모니터링 대시보드
**Goal**: 사용자가 브라우저에서 각 종목의 실시간 가격 상태를 확인할 수 있다 (인프라 버그 수정 포함)
**Depends on**: Phase 5 (완료)
**Requirements**: INFRA-01, INFRA-02, DASH-01, DASH-02, DASH-03
**Success Criteria** (what must be TRUE):
  1. WebSocket 연결 시 asyncio ERROR 로그가 더 이상 발생하지 않는다 (QueueFull 버그 수정)
  2. hub.get_snapshot() 응답에 current_price, drop_pct, SELL_PENDING 필드가 포함된다
  3. 브라우저에서 각 종목의 현재가, 고점, 하락률을 행 단위로 확인할 수 있다
  4. SELL_PENDING 중인 종목이 시각적으로 구분된다 (배지 또는 색상 강조)
  5. 페이지 새로고침 없이 WebSocket으로 데이터가 자동 갱신된다
**Plans:** 3 plans
Plans:
- [x] 06-01-PLAN.md — 인프라 버그 수정: hub.py QueueFull + push_snapshot 시그니처 확장 + pending_codes() 노출
- [x] 06-02-PLAN.md — FastAPI 앱 확장: /ws WebSocket 엔드포인트 + StaticFiles + GET /
- [ ] 06-03-PLAN.md — 대시보드 UI: index.html 단일 파일 (HTML + 인라인 CSS + 인라인 JS)
**UI hint**: yes

### Phase 7: 봇 제어
**Goal**: 사용자가 브라우저에서 봇 세션을 시작·중지하고 매도 모드를 제어할 수 있다
**Depends on**: Phase 6
**Requirements**: CTRL-01, CTRL-02, CTRL-03, CTRL-04
**Success Criteria** (what must be TRUE):
  1. UI에서 시작 버튼을 누르면 모니터링 세션이 시작되고 대시보드에 반영된다
  2. UI에서 중지 버튼을 누르면 세션이 중지되고 봇 상태가 비활성으로 갱신된다
  3. UI에서 드라이런 ↔ 실매도 모드를 전환할 수 있으며 현재 모드가 대시보드에 표시된다
  4. UI에서 특정 종목의 수동 시장가 매도를 실행할 수 있으며 결과 피드백이 화면에 표시된다
  5. SELL_PENDING 중 중지 요청 시 "매도 진행 중" 경고가 표시된다
**Plans**: TBD
**UI hint**: yes

### Phase 8: 거래 이력
**Goal**: 사용자가 브라우저에서 과거 매도 이력을 목록으로 확인할 수 있다
**Depends on**: Phase 6
**Requirements**: HIST-01
**Success Criteria** (what must be TRUE):
  1. logs/mutrade.log의 [TRADE] 항목이 파싱되어 종목코드·수량·가격·시각 열로 표시된다
  2. 드라이런 매도와 실매도가 구분 표시된다
  3. 로그 파일이 없거나 [TRADE] 항목이 없을 때 빈 목록이 오류 없이 표시된다
**Plans**: TBD
**UI hint**: yes

### Phase 9: Config 편집
**Goal**: 사용자가 브라우저에서 config.toml을 직접 편집하고 저장할 수 있다
**Depends on**: Phase 8
**Requirements**: CONF-01, CONF-02
**Success Criteria** (what must be TRUE):
  1. UI에서 config.toml의 전체 내용이 텍스트 에디터로 표시된다
  2. 수정 후 저장 버튼을 누르면 변경 사항이 파일에 원자적으로 반영된다 (임시 파일 + os.replace 패턴)
  3. TOML 파싱 오류가 있는 경우 저장이 거부되고 오류 메시지가 표시된다
  4. 저장 성공 시 "다음 봇 세션 시작 시 적용됩니다" 안내 문구가 표시된다
**Plans**: TBD
**UI hint**: yes

---

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation and KIS API Connectivity | v1.0 | 2/2 | Complete | 2026-04-06 |
| 2. Trailing Stop Engine | v1.0 | 2/2 | Complete | 2026-04-06 |
| 3. Order Execution | v1.0 | 2/2 | Complete | 2026-04-08 |
| 4. Notifications and Operational Polish | v1.0 | 2/2 | Complete | 2026-04-08 |
| 5. Process Architecture Migration | v1.1 | 2/2 | Complete | 2026-04-12 |
| 6. 모니터링 대시보드 | v1.1 | 0/3 | Not started | - |
| 7. 봇 제어 | v1.1 | 0/? | Not started | - |
| 8. 거래 이력 | v1.1 | 0/? | Not started | - |
| 9. Config 편집 | v1.1 | 0/? | Not started | - |

---

## Coverage (v1.1)

| Requirement | Phase | Category |
|-------------|-------|----------|
| INFRA-01 | Phase 6 | Infrastructure |
| INFRA-02 | Phase 6 | Infrastructure |
| DASH-01 | Phase 6 | Dashboard |
| DASH-02 | Phase 6 | Dashboard |
| DASH-03 | Phase 6 | Dashboard |
| CTRL-01 | Phase 7 | Control |
| CTRL-02 | Phase 7 | Control |
| CTRL-03 | Phase 7 | Control |
| CTRL-04 | Phase 7 | Control |
| HIST-01 | Phase 8 | History |
| CONF-01 | Phase 9 | Config |
| CONF-02 | Phase 9 | Config |

**Mapped: 12/12 requirements (100%)**

---
*v1.0 archived: 2026-04-08 — See milestones/v1.0-ROADMAP.md for full details*
*v1.1 roadmap created: 2026-04-12 (Phase 5 already complete at roadmap creation)*
