# ROADMAP: MuTrade — 자동 트레일링 스탑 트레이딩 봇

**Milestone:** v1 — Personal Automated Trailing Stop Bot
**Phases:** 4
**Granularity:** Standard
**Coverage:** 21/21 v1 requirements mapped
**Created:** 2026-04-06

---

## Phases

- [ ] **Phase 1: Foundation and KIS API Connectivity** — Config, secrets, auth token lifecycle, price/balance queries with correct error handling and rate limiting
- [x] **Phase 2: Trailing Stop Engine** — Per-symbol high-water mark tracking, drop calculation, sell signal emission, state persistence, dry-run mode (completed 2026-04-06)
- [x] **Phase 3: Order Execution** — Live market-sell order submission with idempotency guard, correct quantity handling, and fill confirmation (completed 2026-04-08)
- [ ] **Phase 4: Notifications and Operational Polish** — Telegram alerts, trade history log, startup/shutdown logging, KRX holiday handling

---

## Phase Details

### Phase 1: Foundation and KIS API Connectivity
**Goal**: The bot can authenticate with KIS, fetch live prices for monitored symbols, and is safe to leave running — secrets are protected, rate limits are respected, and API errors are never silently ignored.
**Depends on**: Nothing (first phase)
**Requirements**: CONF-01, CONF-02, CONF-03, CONF-04, FEED-01, FEED-02, FEED-03, FEED-04
**Success Criteria** (what must be TRUE):
  1. Running `python main.py` authenticates with KIS OAuth 2.0 and prints a valid token expiry timestamp without error
  2. The bot polls current prices for all symbols in `config.toml` at a 3–5 second interval during market hours (09:00–15:20 KST) and stops automatically outside those hours
  3. A KIS API error response (rt_cd != "0") is logged as an error and does not propagate a zero-price value into the trailing stop engine
  4. Sensitive credentials (.env file) are absent from version control and rejected at startup if missing required fields
  5. The bot skips polling on KRX public holidays and logs a skip message
**Plans:** 2/2 plans complete
Plans:
- [x] 01-01-PLAN.md — Project skeleton, settings validation, config.toml loader, KRX holiday check
- [x] 01-02-PLAN.md — KIS client factory, price feed with rate limiting, APScheduler, main.py entry point

### Phase 2: Trailing Stop Engine
**Goal**: The bot correctly tracks peak prices per symbol across restarts and emits sell signals in dry-run mode when a symbol drops the configured threshold from its high-water mark — fully testable without touching real orders.
**Depends on**: Phase 1
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-04, ENG-05
**Success Criteria** (what must be TRUE):
  1. After a price update, `state.json` is written and the high-water mark for that symbol is correctly updated (visible in the file)
  2. A bot restart loads `state.json` and continues tracking from the persisted peak, not from the current price
  3. When a symbol's price drops >= the configured threshold from its peak, a "SELL SIGNAL" log entry is emitted in dry-run mode (no order is placed)
  4. A per-symbol threshold set in `config.toml` overrides the default -10% threshold for that symbol
  5. No sell signal is emitted on the first price tick after startup, even if the opening price is below the persisted peak
**Plans:** 2/2 plans complete
Plans:
- [x] 02-01-PLAN.md — TDD: 트레일링 스탑 엔진 코어 (모델, 상태 저장소, 엔진 로직)
- [x] 02-02-PLAN.md — 엔진 통합 (Settings DRY_RUN, 스케줄러 연결, main.py 와이어링)

### Phase 3: Order Execution
**Goal**: The bot submits a real market-sell order when a sell signal is triggered, using the correct sellable quantity, without ever submitting duplicate orders — validated in KIS paper trading (모의투자) before production credentials are used.
**Depends on**: Phase 2
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-04
**Success Criteria** (what must be TRUE):
  1. A triggered sell signal results in a market-sell order submitted to KIS using `ord_psbl_qty` (sellable quantity) for the full available position
  2. A SELL_PENDING flag is set for a symbol immediately after order submission; a second sell signal for the same symbol before fill confirmation does not submit a second order
  3. After order submission, the bot confirms fill status and logs the result (filled quantity and execution price)
  4. End-to-end sell flow completes successfully in KIS paper trading (모의투자) with paper trading `tr_id` values
**Plans:** 1/2 plans executed
Plans:
- [x] 03-01-PLAN.md — TDD: OrderExecutor 핵심 로직 (시장가 매도, 수량 조회, SELL_PENDING, 체결 확인)
- [x] 03-02-PLAN.md — OrderExecutor 통합 (scheduler 연결, main.py 와이어링)

### Phase 4: Notifications and Operational Polish
**Goal**: Every sell execution generates an immediate Telegram notification with order details, all trade events are durably logged, and the bot reports its monitoring state on start and stop.
**Depends on**: Phase 3
**Requirements**: NOTIF-01, NOTIF-02, NOTIF-03, NOTIF-04
**Success Criteria** (what must be TRUE):
  1. A Telegram message containing symbol name, sell price, and quantity is received within seconds of a sell order being submitted
  2. The Telegram notification is sent after the order submission completes, not before — a notification failure does not delay or block the sell order
  3. Each sell execution appends a timestamped record to the trade history log file, readable after bot restart
  4. On bot startup, the log shows the list of monitored symbols and their loaded high-water marks; on shutdown, a final log entry is written
**Plans:** 2 plans
Plans:
- [x] 04-01-PLAN.md — TelegramNotifier 모듈 신설 + Settings Telegram 필드 + 의존성 추가 (Wave 1)
- [x] 04-02-PLAN.md — OrderExecutor 통합 ([TRADE] 로그, notifier 주입) + 종료 로그 + main.py 와이어링 (Wave 2)

---

## Progress

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation and KIS API Connectivity | 2/2 | Complete | 2026-04-06 |
| 2. Trailing Stop Engine | 2/2 | Complete   | 2026-04-06 |
| 3. Order Execution | 1/2 | In Progress|  |
| 4. Notifications and Operational Polish | 0/2 | Not started | - |

---

## Coverage Validation

| Requirement | Phase | Category |
|-------------|-------|----------|
| CONF-01 | Phase 1 | 인증 및 설정 |
| CONF-02 | Phase 1 | 인증 및 설정 |
| CONF-03 | Phase 1 | 인증 및 설정 |
| CONF-04 | Phase 1 | 인증 및 설정 |
| FEED-01 | Phase 1 | 가격 모니터링 |
| FEED-02 | Phase 1 | 가격 모니터링 |
| FEED-03 | Phase 1 | 가격 모니터링 |
| FEED-04 | Phase 1 | 가격 모니터링 |
| ENG-01 | Phase 2 | 트레일링 스탑 엔진 |
| ENG-02 | Phase 2 | 트레일링 스탑 엔진 |
| ENG-03 | Phase 2 | 트레일링 스탑 엔진 |
| ENG-04 | Phase 2 | 트레일링 스탑 엔진 |
| ENG-05 | Phase 2 | 트레일링 스탑 엔진 |
| EXEC-01 | Phase 3 | 매도 주문 실행 |
| EXEC-02 | Phase 3 | 매도 주문 실행 |
| EXEC-03 | Phase 3 | 매도 주문 실행 |
| EXEC-04 | Phase 3 | 매도 주문 실행 |
| NOTIF-01 | Phase 4 | 알림 및 로그 |
| NOTIF-02 | Phase 4 | 알림 및 로그 |
| NOTIF-03 | Phase 4 | 알림 및 로그 |
| NOTIF-04 | Phase 4 | 알림 및 로그 |

**Total v1 requirements:** 21
**Mapped:** 21
**Unmapped:** 0

---
*Roadmap created: 2026-04-06*
*Last updated: 2026-04-08 after Phase 4 planning*
