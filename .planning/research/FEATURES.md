# Feature Landscape

**Domain:** Personal automated trailing stop / stop-loss trading bot (KRX / 한국투자증권)
**Researched:** 2026-04-06
**Confidence:** MEDIUM — training knowledge for well-established domain; KIS API specifics verified against documented public API behavior

---

## Table Stakes

Features where absence makes the bot unreliable or unusable. These are not optional for v1.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| 트레일링 고점 추적 (per-stock peak tracking) | Without this, "trailing" stop becomes a fixed stop. Core mechanism. | Low | In-memory dict keyed by ticker. Reset on each run unless persisted. |
| 고점 대비 하락율 계산 | The trigger condition itself. Must be accurate to avoid false triggers or missed triggers. | Low | `(peak - current) / peak >= threshold`. Float precision matters for near-threshold cases. |
| 시장가 매도 주문 실행 | Stop-loss value is destroyed if the sell never executes. Market order guarantees fill. | Medium | KIS API: `POST /uapi/domestic-stock/v1/trading/order`. Requires order type `01` (시장가). |
| KIS OAuth 2.0 토큰 관리 | All KIS API calls require a valid access token. Token expires after 24h. | Medium | Token must be refreshed automatically before expiry. Store token + expiry timestamp. Silent refresh needed. |
| 보유 종목 조회 | Must confirm position still exists before placing sell order. Selling a zero-position is an API error. | Medium | KIS API: `GET /uapi/domestic-stock/v1/trading/inquire-balance`. |
| 현재가 조회 (실시간 or polling) | Without price data, no trailing stop is possible. | Medium | KIS WebSocket (실시간 체결가) preferred. Polling fallback every N seconds acceptable for personal use. |
| 워치리스트 설정 (종목 선택) | User must control which holdings are monitored. Full-portfolio forced application risks unintended sells. | Low | Config file (YAML/JSON). List of ticker codes + optional per-stock overrides. |
| 매도 이력 로그 (파일) | Without a record, the user cannot audit what happened or debug misfires. | Low | Append-only log file. Each entry: timestamp, ticker, trigger price, peak price, drop %, quantity, order ID. |
| 시장 시간 게이팅 (09:00–15:30 KST) | KRX does not accept orders outside trading hours. Attempting orders outside hours returns API errors. | Low | Check `datetime.now(KST)` before each cycle. Also gate on weekdays + KRX holiday calendar. |
| 드라이런 모드 (dry-run) | Without a safe test mode, every bug test risks real money. Essential for development and verification. | Low | Flag in config. When set, log "would sell" but do not call the order API. |
| 크래시 복구 / 재시작 고점 보존 | If the process restarts mid-session, in-memory peaks are lost. Bot may silently not protect positions. | Medium | Persist peak state to disk (JSON file) on each update. Load on startup. |
| API 오류 재시도 로직 | KIS API has rate limits and occasional transient failures. A single failure must not silence the bot. | Medium | Exponential backoff, max 3 retries. Fatal errors (auth failure, invalid ticker) must not loop. |
| 민감 정보 분리 (API 키 등) | Hardcoded credentials in source = security incident waiting to happen. | Low | `.env` file or env vars. Never commit to git. `.gitignore` enforced. |

---

## Differentiators

Features that add meaningful value beyond basic reliability, but are not required for a functional v1.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 카카오톡 알림 (KakaoTalk notification) | Real-time push notification to phone when sell executes. User knows immediately without watching logs. | Medium | KakaoTalk Developers API (카카오 알림톡 or 나에게 보내기). Requires Kakao app registration. Good UX for personal bots. |
| 종목별 개별 임계값 설정 | Different stocks have different volatility. A volatile small-cap may need 15% threshold; blue-chip 7%. One global threshold is suboptimal. | Low | Config structure: `stocks: [{ticker: "005930", threshold: 0.08}]`. Fallback to global default if not specified. |
| 초기 고점 수동 설정 | Bot tracks peak from start of run. If stock peaked last week at a higher price, the trailing stop starts from today's open, not the true peak. Manual override captures historical peaks. | Low | Optional `initial_peak` field per stock in config. If set, use as floor for peak tracking. |
| 매도 수량 부분 설정 (partial sell) | Selling 100% of a position may not be user's intent. Selling half locks in partial gains while staying in the position. | Medium | Config: `sell_quantity: "all" | "half" | N`. Requires balance query to calculate. |
| 체결 확인 및 미체결 처리 | Market orders rarely fail to fill, but in extreme volatility or halt situations they might. Untracked open orders are dangerous. | Medium | Poll order status after submission. Alert if not filled within N minutes. |
| 일일 운영 리포트 | After market close, a summary of the day's monitoring: tickers watched, peak updates, any sells, errors. | Low | Written to file or sent via notification channel. Good for personal audit trail. |
| KRX 휴장일 자동 인식 | Hardcoded weekday check misses public holidays. Bot will start, find market closed, and loop wastefully (or worse, error). | Medium | KRX publishes holiday calendar. Can pre-populate a yearly list in config, or call the KIS holiday API endpoint. |
| 공매도/VI 발동 감지 | During Volatility Interruption (VI), all orders are suspended. If VI triggers mid-sell, the order bounces. | High | KIS API includes VI status in market data. Detect and queue sell for post-VI resumption. Adds significant complexity. |
| 다중 알림 채널 (fallback) | If Kakao fails, an email or Slack fallback ensures the alert reaches the user. | Low | Abstract notification interface, multiple backends. |
| 프로세스 상태 헬스체크 | For server/daemon deployments: a simple HTTP endpoint or heartbeat file that confirms the bot is alive. | Low | Useful when running on a remote server (e.g., Raspberry Pi, VPS). |

---

## Anti-Features

Features to deliberately NOT build in v1. Each has a reason and a deferral strategy.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| 자동 매수 (auto-buy) | Scope creep. Buy logic requires entry strategy, which is a separate domain with separate risk. Mixing buy/sell in v1 complicates the codebase and decision surface. | Manual buy remains user's responsibility. Out of scope per PROJECT.md. |
| 백테스팅 엔진 | Requires historical OHLCV data pipeline, simulation loop, performance metrics. Doubles the project scope. | Accept forward-only validation. Backtest as a separate future project if needed. |
| 웹 UI / 대시보드 | Over-engineering for a personal tool. CLI + config file + log file is sufficient for one user. | Config via YAML file. Status via log tailing or daily report. |
| 다중 증권사 지원 | Each broker has a different API contract. Abstraction layer adds indirection that's worthless until a second broker is needed. | KIS-only for v1. Abstract the broker interface at the module boundary so it can be extended later. |
| ML 기반 동적 임계값 | Algorithmic threshold tuning requires labeled outcome data, model training, and ongoing validation. Risk of silent misconfiguration far outweighs benefit for personal use. | Fixed per-stock thresholds in config. User adjusts manually based on experience. |
| 포트폴리오 최적화 / 리밸런싱 | Entirely different product category. Not related to stop-loss. | Not in scope. |
| 복잡한 주문 타입 (조건부 주문, OCO) | KIS API supports limited order types. Conditional order types add complexity and may not be reliably supported. | Stick to 시장가 (market order) for guaranteed fill. |
| DB 기반 이력 관리 | SQLite or Postgres for a personal bot that executes a few sells per week is over-engineering. | Append-only log files. CSV or JSONL is queryable enough with standard tools. |

---

## Feature Dependencies

```
KIS OAuth 토큰 관리
    └── 보유 종목 조회
    └── 현재가 조회
    └── 시장가 매도 주문 실행
            └── 체결 확인 및 미체결 처리 (differentiator)

워치리스트 설정
    └── 종목별 개별 임계값 설정 (differentiator)
    └── 초기 고점 수동 설정 (differentiator)

트레일링 고점 추적
    └── 크래시 복구 / 재시작 고점 보존
    └── 고점 대비 하락율 계산
            └── 시장가 매도 주문 실행

시장 시간 게이팅
    └── KRX 휴장일 자동 인식 (differentiator)

시장가 매도 주문 실행
    └── 매도 이력 로그
    └── 카카오톡 알림 (differentiator)
```

---

## MVP Recommendation

**Build first (table stakes, in this order):**

1. KIS OAuth 토큰 관리 — everything depends on this
2. 현재가 조회 (polling, not WebSocket) — simpler than WebSocket; validate API integration first
3. 보유 종목 조회 — confirm position before ordering
4. 트레일링 고점 추적 + 하락율 계산 — the core algorithm
5. 드라이런 모드 — must be in place before any live testing
6. 워치리스트 설정 (config file) — user control over scope
7. 시장 시간 게이팅 — prevent out-of-hours errors
8. 시장가 매도 주문 실행 — live execution (behind dry-run flag until validated)
9. 매도 이력 로그 — audit trail
10. 크래시 복구 / 재시작 고점 보존 — required for production reliability
11. API 오류 재시도 로직 — required for production reliability
12. 민감 정보 분리 — required before any real credential use

**Add in second pass (high-value differentiators):**

- 카카오톡 알림 — high personal utility, moderate effort
- 종목별 개별 임계값 설정 — low effort, significant value
- 초기 고점 수동 설정 — low effort, closes a real gap
- KRX 휴장일 자동 인식 — prevents wasteful weekend runs

**Defer:**

- WebSocket 실시간 체결가 — polling is sufficient for personal use; WebSocket adds reconnect complexity
- 체결 확인 및 미체결 처리 — market orders on KRX have near-100% fill rate in normal conditions
- VI 발동 감지 — very high complexity, rare event, not v1 priority
- 일일 운영 리포트 — nice to have, zero urgency

---

## KRX / KIS-Specific Constraints Affecting Features

These are market-specific facts that directly shape feature implementation (MEDIUM confidence — based on documented KIS API behavior and KRX market rules):

| Constraint | Impact on Features |
|------------|-------------------|
| KIS access token expires after 24h | Token refresh must be automatic, not manual |
| KIS API rate limit: approximately 20 req/sec (REST) | Polling interval must be >= 1s per ticker; with 10 stocks, minimum 10s cycle time or concurrent calls with rate throttle |
| KRX 동시호가 (08:30–09:00, 15:20–15:30) | During call auction periods, market orders behave differently. Gate monitoring to 09:00–15:20 to avoid auction-period ambiguity |
| KRX 상한가/하한가 제한 (±30%) | The trailing stop trigger will never be missed due to price limits, but the fill price on a market sell during limit-down may be at the lower limit |
| 소수점 불가 (정수 주문만) | Sell quantity must be a whole number. `sell_all` = full balance quantity; no fractional shares |
| KIS sandbox 환경 존재 | Virtual trading (모의투자) environment available. Dry-run should prefer real sandbox over pure simulation for realistic validation |

---

## Sources

- Training knowledge: well-established patterns from open-source trading bot projects (backtrader, freqtrade, korean-stock-bot community patterns)
- KIS Developers API documentation (공식 문서): https://apiportal.koreainvestment.com/apiservice
- KRX market rules: standard KRX trading hours and auction period rules are stable, long-documented
- Confidence note: KIS API rate limits and specific endpoint paths are MEDIUM confidence — must be verified against current KIS Developers portal before implementation
