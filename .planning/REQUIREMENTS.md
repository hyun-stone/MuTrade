# Requirements: MuTrade

**Defined:** 2026-04-06
**Core Value:** 조건 충족 시 사람의 개입 없이 즉시 자동 매도하여 손실을 방어한다.

## v1 Requirements

### 인증 및 설정 (CONF)

- [ ] **CONF-01**: 시스템이 KIS OAuth 2.0 토큰을 취득하고 24시간 만료 전 자동 갱신한다
- [x] **CONF-02**: API 키·시크릿 등 민감 정보를 .env 파일로 분리하고 .gitignore에 포함한다
- [x] **CONF-03**: 사용자가 config.toml 파일로 모니터링 종목과 매도 조건을 설정할 수 있다
- [x] **CONF-04**: 시스템이 KRX 공휴일에는 모니터링을 자동으로 건너뛴다

### 가격 모니터링 (FEED)

- [ ] **FEED-01**: 시스템이 시장 운영 시간(09:00~15:20 KST) 중에만 가격을 폴링한다
- [ ] **FEED-02**: 시스템이 설정된 종목의 현재가를 3~5초 간격으로 조회한다
- [ ] **FEED-03**: 시스템이 KIS API 레이트 리밋을 초과하지 않도록 요청 간격을 조절한다
- [ ] **FEED-04**: 시스템이 KIS API 응답의 rt_cd 값을 확인하여 HTTP 200 내 에러를 올바르게 처리한다

### 트레일링 스탑 엔진 (ENG)

- [ ] **ENG-01**: 시스템이 각 종목의 고점(최고가)을 자동으로 추적한다
- [ ] **ENG-02**: 시스템이 고점 데이터를 state.json에 원자적으로 저장하여 재시작 후에도 복원한다
- [ ] **ENG-03**: 고점 대비 하락률이 설정된 임계값(기본 -10%) 이상이면 매도 신호를 발생시킨다
- [ ] **ENG-04**: 각 종목별로 개별 하락 임계값을 config.toml에서 설정할 수 있다
- [ ] **ENG-05**: 드라이런 모드에서 실제 매도 없이 "매도 신호 발생" 로그만 기록한다

### 매도 주문 실행 (EXEC)

- [ ] **EXEC-01**: 매도 신호 발생 시 해당 종목을 시장가로 즉시 매도한다
- [ ] **EXEC-02**: 매도 가능 수량(ord_psbl_qty)을 조회하여 매도 수량으로 사용한다
- [ ] **EXEC-03**: 동일 종목에 대해 SELL_PENDING 플래그로 중복 주문을 방지한다
- [ ] **EXEC-04**: 주문 제출 후 체결 여부를 확인한다

### 알림 및 로그 (NOTIF)

- [ ] **NOTIF-01**: 매도 실행 시 Telegram으로 종목명·매도가·수량을 포함한 알림을 전송한다
- [ ] **NOTIF-02**: 알림 전송은 매도 주문 제출 이후 비동기로 처리한다
- [ ] **NOTIF-03**: 모든 매도 이력을 타임스탬프와 함께 로그 파일에 기록한다
- [ ] **NOTIF-04**: 봇 시작·종료 시 현재 모니터링 대상 종목 목록과 고점 데이터를 로그에 기록한다

## v2 Requirements

### 고급 모니터링

- **FEED-V2-01**: WebSocket 실시간 시세 수신 (폴링 대체)
- **FEED-V2-02**: 변동성 완화장치(VI) 발동 감지 및 대응

### 고급 트레일링 스탑

- **ENG-V2-01**: 초기 고점을 config에서 수동으로 지정 (봇 시작 전 매수한 종목의 역사적 고점 반영)
- **ENG-V2-02**: 매수가 기준 손절 조건 추가 (트레일링 스탑과 병행)

### 주문 고급 기능

- **EXEC-V2-01**: 지정가 매도 지원
- **EXEC-V2-02**: 부분 체결 처리 (잔여 미체결 수량 재주문)

### 운영 편의

- **OPS-V2-01**: 일별 거래 결과 요약 리포트 (매도 종목, 손익 등)
- **OPS-V2-02**: KakaoTalk 알림 추가 지원
- **OPS-V2-03**: API 연속 오류 발생 시 운영자 경보 전송

## Out of Scope

| Feature | Reason |
|---------|--------|
| 자동 매수 | 핵심 목적은 손실 방어이며, 매수는 사용자가 수동으로 판단 |
| 웹/앱 UI | CLI + 설정 파일로 충분, 과도한 구현 비용 |
| 복수 증권사 지원 | 한국투자증권 단일 지원으로 복잡도 관리 |
| 백테스팅 | v1 범위 외, 실거래 검증 우선 |
| 포트폴리오 리밸런싱 | 범위 외, 복잡도 높음 |
| ML 기반 임계값 자동 조정 | 범위 외, 투명한 규칙 기반 방어가 목적 |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| CONF-01 | Phase 1 | Pending |
| CONF-02 | Phase 1 | Complete |
| CONF-03 | Phase 1 | Complete |
| CONF-04 | Phase 1 | Complete |
| FEED-01 | Phase 1 | Pending |
| FEED-02 | Phase 1 | Pending |
| FEED-03 | Phase 1 | Pending |
| FEED-04 | Phase 1 | Pending |
| ENG-01 | Phase 2 | Pending |
| ENG-02 | Phase 2 | Pending |
| ENG-03 | Phase 2 | Pending |
| ENG-04 | Phase 2 | Pending |
| ENG-05 | Phase 2 | Pending |
| EXEC-01 | Phase 3 | Pending |
| EXEC-02 | Phase 3 | Pending |
| EXEC-03 | Phase 3 | Pending |
| EXEC-04 | Phase 3 | Pending |
| NOTIF-01 | Phase 4 | Pending |
| NOTIF-02 | Phase 4 | Pending |
| NOTIF-03 | Phase 4 | Pending |
| NOTIF-04 | Phase 4 | Pending |

**Coverage:**
- v1 requirements: 21 total
- Mapped to phases: 21
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-06*
*Last updated: 2026-04-06 after initial definition*
