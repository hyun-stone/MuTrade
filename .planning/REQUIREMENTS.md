# Requirements — MuTrade v1.1 Admin UI

*Created: 2026-04-12*

## v1.1 Requirements

### INFRA — 인프라 기반 (UI 기능의 전제 조건)

- [ ] **INFRA-01**: 봇 상태 스냅샷에 현재가·하락률·SELL_PENDING이 포함된다 (`hub.push_snapshot()` + `scheduler.py` 수정)
- [ ] **INFRA-02**: 스냅샷 큐 오버플로 버그가 수정된다 (`asyncio.QueueFull` 예외 처리, `hub.py`)

### DASH — 모니터링 대시보드

- [ ] **DASH-01**: 사용자는 각 종목의 현재가, 고점, 하락률을 웹 페이지에서 확인할 수 있다
- [ ] **DASH-02**: 사용자는 SELL_PENDING 중인 종목을 시각적으로 구분할 수 있다
- [ ] **DASH-03**: 대시보드는 WebSocket으로 자동 갱신된다 (페이지 새로고침 불필요)

### CTRL — 봇 제어

- [ ] **CTRL-01**: 사용자는 UI에서 모니터링 세션을 시작할 수 있다
- [ ] **CTRL-02**: 사용자는 UI에서 모니터링 세션을 중지할 수 있다
- [ ] **CTRL-03**: 사용자는 UI에서 드라이런 ↔ 실매도 모드를 전환할 수 있다
- [ ] **CTRL-04**: 사용자는 UI에서 특정 종목을 즉시 시장가 매도할 수 있다

### HIST — 거래 이력

- [ ] **HIST-01**: 사용자는 `[TRADE]` 로그에서 파싱된 매도 이력(종목·수량·가격·시각)을 목록으로 확인할 수 있다

### CONF — Config 편집

- [ ] **CONF-01**: 사용자는 UI에서 `config.toml` 전체 내용을 편집할 수 있다
- [ ] **CONF-02**: 사용자는 변경 사항을 저장할 수 있다 (다음 세션 시작 시 적용)

---

## Future Requirements (v1.2+)

- 프로덕션 `tr_id` 검증 및 실거래 end-to-end 테스트
- WebSocket 실시간 시세 수신 (KIS WebSocket으로 폴링 대체)
- 초기 고점을 config에서 수동 지정 (봇 시작 전 매수 종목 지원)
- 로그 스트림 실시간 표시 (logs/mutrade.log tail)

## Out of Scope

- 민감 정보(.env) 편집 UI — 보안상 서버 직접 편집 유지
- 실시간 캔들차트 — KIS API 부하 대비 가치 없음
- config 변경 즉시 적용 (hot-reload) — frozen dataclass 구조상 다음 세션 적용만 가능
- 자동 매수 — 손실 방어가 핵심 목적
- 복수 증권사 지원 — 한국투자증권 단일 지원 유지
- 다중 사용자 인증 — 개인용 봇, 불필요

---

## Traceability

| REQ-ID | Phase | Category |
|--------|-------|----------|
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
| INFRA-01 | Phase 5 | Infrastructure |
| INFRA-02 | Phase 5 | Infrastructure |
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
