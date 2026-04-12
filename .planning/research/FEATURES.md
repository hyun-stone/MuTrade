# Feature Landscape

**Domain:** Personal automated trailing stop / stop-loss trading bot (KRX / 한국투자증권)
**Researched:** 2026-04-06 (v1.0 MVP), 2026-04-12 (v1.1 Admin Dashboard 추가)
**Confidence:** MEDIUM — training knowledge for well-established domain; KIS API specifics verified against documented public API behavior

---

## v1.1 Admin Dashboard — 피처 분석

> 이 섹션은 v1.1 Admin Dashboard 마일스톤 전용이다.
> 기존 v1.0 MVP 피처는 하단 "v1.0 MVP 피처" 섹션 참조.

### 컨텍스트: 기존 봇 상태

Admin Dashboard가 의존하는 기존 봇 구현:

| 컴포넌트 | 클래스/모듈 | 노출 가능한 데이터 |
|----------|-------------|-------------------|
| `TrailingStopEngine` | `mutrade.engine.trailing_stop` | `engine.states` → `{code: SymbolState(code, peak_price, warm)}` |
| `SymbolState` | `mutrade.engine.models` | `code`, `peak_price`, `warm` |
| `SellSignal` | `mutrade.engine.models` | `code`, `name`, `current_price`, `peak_price`, `drop_pct`, `threshold`, `dry_run` |
| `AppConfig` | `mutrade.config.loader` | `symbols`, `poll_interval`, `default_threshold`, market hours |
| `SymbolConfig` | `mutrade.config.loader` | `code`, `name`, `threshold` |
| `[TRADE]` 로그 | `logs/mutrade.log` | 매도 주문 제출 레코드 (구조화된 텍스트 라인) |
| `state.json` | `StateStore` | 종목별 고점 JSON |

`[TRADE]` 로그 라인 포맷 (order_executor.py 기준):
```
[TRADE] 매도 주문 제출: {code} ({name}) qty={qty} current_price={price:,.0f} peak={peak:,.0f} drop={drop:.2%} threshold={threshold:.1%} order={order_number}
```

loguru 기본 앞머리 포맷:
```
2026-04-12 09:31:42 | INFO     | mutrade.executor.order_executor:_submit_order | [TRADE] 매도 주문 제출: ...
```

---

### Table Stakes (없으면 대시보드가 무의미함)

#### 1. 실시간 모니터링 뷰

**왜 필수인가:** 대시보드의 핵심 가치는 "지금 봇이 무엇을 보고 있는가"를 인간이 확인하는 것이다.

| Feature | Why Expected | Complexity | 기존 봇 의존성 |
|---------|--------------|------------|---------------|
| 종목별 현재가 표시 | 폴링 중인 가격을 사람이 확인할 수 있어야 함 | Low | `TrailingStopEngine.tick()` 호출 시점의 price dict |
| 종목별 고점(peak) 표시 | 트레일링 스탑 기준선. 이게 틀리면 봇이 망가진 것 | Low | `SymbolState.peak_price` |
| 고점 대비 하락률(%) 표시 | 매도 임박 여부를 직관적으로 표시 | Low | `(peak - current) / peak * 100` |
| 임계값(threshold) 표시 | 얼마나 더 내려야 매도인지 기준 표시 | Low | `SymbolConfig.threshold` |
| 마지막 업데이트 시각 | 봇이 살아있는지 확인하는 가장 기본적인 신호 | Low | tick 호출 타임스탬프 |
| 모니터링 상태 뱃지 (warm/pending/sold) | `warm=False` 종목은 아직 추적 안 됨 → 색상으로 구분 필요 | Low | `SymbolState.warm`, `OrderExecutor._pending` |
| WebSocket 실시간 푸시 | HTTP 폴링 방식은 봇 폴링 간격(3~5초)과 UI 폴링이 중복됨. WS 한 번 연결이 깨끗함 | Medium | FastAPI `@app.websocket()` |

**표시 컬럼 권고:**

```
| 종목코드 | 종목명 | 현재가 | 고점 | 하락률 | 임계값 | 상태 | 최종갱신 |
```

- **하락률 컬럼**: 임계값의 70%~90% 구간은 주황, 90% 이상은 빨강 (위험 근접 시각화)
- **상태 뱃지**: `WARM` (정상 추적) / `COLD` (warm=False, 첫 tick 미도달) / `PENDING` (매도 주문 중)
- **현재가/고점**: 한국 원화 쉼표 포맷 (`{:,}원`)

#### 2. 봇 제어 패널

**왜 필수인가:** UI 없이 봇 재시작은 SSH 접속 → 프로세스 kill → 재실행이다. 단순 시작/중지라도 UI로 제공해야 대시보드 가치가 있다.

| Feature | Why Expected | Complexity | 기존 봇 의존성 |
|---------|--------------|------------|---------------|
| 봇 상태 표시 (RUNNING/STOPPED/MARKET_CLOSED) | 봇이 켜져 있는지 꺼져 있는지 모르면 제어 불가 | Low | APScheduler job 상태, 시장 시간 여부 |
| 봇 시작/중지 버튼 | 핵심 제어 액션 | Medium | APScheduler `pause_job()`/`resume_job()` 또는 내부 플래그 |
| 드라이런 모드 토글 표시 | 실매도 여부가 가장 중요한 보안 정보 | Low | `Settings.dry_run` 읽기 전용 표시 |
| 모니터링 종목 추가 | 새 종목을 UI에서 추가 → config.toml 반영 | High | `config.toml` 쓰기 + engine 재초기화 필요 |
| 모니터링 종목 제거 | 더 이상 추적 안 할 종목 제거 | High | 동일 |

**안전 UX 패턴 (반드시 적용):**

1. **봇 중지 확인 다이얼로그**: "봇을 중지하면 모니터링이 멈춥니다. 진행하시겠습니까?" — NN/g 연구에서 irreversible action에 확인 다이얼로그 필수
2. **드라이런 상태 상시 표시**: 빨간 배너 또는 상단 고정 뱃지 "LIVE MODE — 실제 매도 실행 중" vs "DRY-RUN MODE" — 실수로 라이브 모드인지 모르는 것이 최악의 시나리오
3. **종목 추가/제거는 즉시 적용 안 함**: "저장 후 다음 폴링 사이클부터 적용" 안내 문구 필요. 즉시 engine 재초기화는 race condition 유발 가능
4. **Hold-to-Confirm 패턴**: 봇 중지처럼 결과가 즉각적인 액션에는 버튼 길게 누르기(2초) 또는 타이핑 확인("STOP" 입력) 패턴 사용 — 오터치 방지

#### 3. 거래 이력 테이블

**왜 필수인가:** "실제로 팔렸는가?"가 봇 사용의 핵심 관심사다. 매도 로그를 수동으로 grep하는 것은 불편하다.

| Feature | Why Expected | Complexity | 기존 봇 의존성 |
|---------|--------------|------------|---------------|
| [TRADE] 로그 파싱 및 테이블 표시 | 브라우저에서 매도 이력 확인 | Medium | `logs/mutrade.log` 파일 읽기 + regex 파싱 |
| 최신순 정렬 | 가장 최근 매도가 먼저 보여야 함 | Low | 파싱 후 datetime 역순 정렬 |
| 드라이런/실매도 구분 표시 | DRY-RUN과 LIVE 주문 섞이면 혼란 | Low | `[DRY-RUN]` vs `[LIVE]` 로그 레벨 파싱 |

**테이블 컬럼 권고:**

```
| 시각 | 종목코드 | 종목명 | 매도수량 | 현재가 | 고점 | 하락률 | 임계값 | 주문번호 | 모드 |
```

**[TRADE] 로그 파싱 정규식:**

loguru 출력 앞머리:
```
^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) \| \w+ +\| [^|]+ \| \[TRADE\] 매도 주문 제출: (?P<code>\S+) \((?P<name>[^)]+)\) qty=(?P<qty>\d+) current_price=(?P<price>[\d,]+) peak=(?P<peak>[\d,]+) drop=(?P<drop>[\d.]+)% threshold=(?P<threshold>[\d.]+)% order=(?P<order>\S+)
```

- `current_price` / `peak` 필드는 쉼표 제거 후 int로 파싱
- `drop` / `threshold`는 이미 `%` 단위 (`:.2%` 포맷 = `10.00%`)
- 파싱 실패 라인은 무시하고 계속 처리 (로테이션 후 불완전 라인 가능)

#### 4. 설정 편집기 (config.toml UI)

**왜 필수인가:** 종목 추가, 임계값 조정을 위해 SSH로 들어가 vim으로 편집하는 것은 불편하다.

| Feature | Why Expected | Complexity | 기존 봇 의존성 |
|---------|--------------|------------|---------------|
| 현재 config.toml 내용 표시 | 편집 전 현재 상태 확인 | Low | `load_config()` 결과 또는 raw file 읽기 |
| 종목별 임계값 편집 | 가장 빈번한 편집 작업 | Medium | `config.toml` 쓰기 |
| 기본 임계값(default_threshold) 편집 | 전체 기본값 조정 | Low | 동일 |
| poll_interval 편집 | 폴링 속도 조정 | Low | 동일 |
| 저장 후 유효성 검사 피드백 | 잘못된 값 저장 방지 | Medium | 서버 측 `load_config()` 재실행으로 검증 |

---

### Differentiators (가치는 있으나 MVP 외)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| 하락률 진행 바(progress bar) | 임계값 대비 현재 위험도를 시각적으로 표현. 숫자보다 직관적 | Low | CSS width: `(drop_pct / threshold) * 100%`, max 100% |
| 고점 갱신 이벤트 토스트 | 새 고점 경신 시 화면 우측 하단 토스트 알림 | Low | WebSocket 이벤트 타입 `PEAK_UPDATED` 추가 |
| 시장 운영 시간 카운트다운 | 장 마감까지 남은 시간 표시 (15:20 기준) | Low | 클라이언트 JS 타이머로 충분 |
| config.toml 변경 시 봇 재시작 없이 핫 리로드 | 종목 추가 후 봇 재시작 필요 없음 | High | `TrailingStopEngine` hot-swap 필요. race condition 주의 |
| 거래 이력 CSV 다운로드 | 엑셀로 수익/손실 분석 | Low | `text/csv` 응답 엔드포인트 추가 |
| 연결된 클라이언트 수 표시 | WS 연결 상태 디버깅 용 | Low | ConnectionManager.active_connections 길이 |
| 봇 중지 후 포지션 잔존 경고 | 봇 중지 시 "현재 {N}개 종목 모니터링 중. 중지하면 트레일링 스탑이 해제됩니다" | Low | 중지 다이얼로그에 현재 상태 주입 |
| KIS 모의투자/실전 모드 표시 | `KIS_MOCK` 값을 UI에 상시 표시 | Low | `Settings.kis_mock` 읽기 전용 |

---

### Anti-Features (명시적으로 구현하지 않을 것)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| React / Vue / Angular SPA | 개인용 단일 사용자 봇에 프론트엔드 빌드 파이프라인은 과도함. 빌드 오류, 의존성 관리, HMR 등 관리 비용이 기능 구현보다 큼 | Vanilla JS + WebSocket API. 또는 HTMX + Jinja2 (서버 렌더) |
| 사용자 인증 / 로그인 | 로컬 또는 사설 서버에서 혼자 사용. 인증 추가 시 토큰 관리, 세션 만료, 비밀번호 초기화 등 관리 부담 급증 | 네트워크 수준 접근 제어(로컬호스트 only 또는 VPN) |
| DB 기반 거래 이력 저장 | `logs/mutrade.log`의 `[TRADE]` 마커가 이미 존재. DB 추가는 이중 기록 + 마이그레이션 부담 | 기존 로그 파일 파싱으로 충분. 파일 로테이션(10MB) 고려한 파싱만 구현 |
| 다중 사용자 / 권한 분리 | 개인용 봇. 역할 기반 권한 관리는 완전히 범위 초과 | 단일 관리자 UI |
| 그래프 / 차트 라이브러리 (Chart.js, D3) | 가격 차트, 고점 추이 차트는 개인 봇 운영에 실질적 도움 낮음. 라이브러리 용량 대비 가치 낮음 | 숫자 테이블 + 색상 코딩 + progress bar로 충분 |
| WebSocket 스케일아웃 (Redis Pub/Sub) | 단일 프로세스, 단일 사용자. Redis 추가는 순수 오버엔지니어링 | 인-메모리 ConnectionManager 패턴으로 충분 |
| 주문 실행 UI (매수/매도 버튼) | 대시보드는 모니터링 + 설정 도구. 주문 실행 UI는 실수로 잘못 클릭 시 실제 손실 발생 | 봇 자동 매도만 허용. 수동 주문은 HTS/MTS 사용 |
| 알림 설정 편집 UI (Telegram 토큰 등) | 민감 정보를 웹 UI에서 편집하면 브라우저 히스토리, 네트워크 전송 등 보안 위협 | .env 파일 직접 편집 유지. 민감 정보는 UI 외부로 격리 |
| 실시간 가격 차트 (캔들스틱) | KIS API 호출 횟수 증가 + WebSocket 부하 증가. 개인 봇 운영에 불필요 | 현재가 숫자 + 고점 표시로 충분 |

---

### Feature Dependencies (Admin Dashboard 전용)

```
기존 TrailingStopEngine (봇 프로세스)
    └── FastAPI 앱 (공유 상태 참조)
            ├── WebSocket 엔드포인트
            │       └── 실시간 모니터링 뷰 (현재가, 고점, 하락률)
            │               └── ConnectionManager (브로드캐스트 허브)
            │
            ├── REST /api/status
            │       └── 봇 상태 표시 (RUNNING/STOPPED)
            │
            ├── REST /api/control (POST start/stop)
            │       └── 봇 제어 패널
            │               └── 안전 UX 패턴 (확인 다이얼로그)
            │
            ├── REST /api/trades (GET)
            │       └── 거래 이력 테이블
            │               └── logs/mutrade.log 파싱
            │
            └── REST /api/config (GET/POST)
                    └── 설정 편집기
                            └── config.toml 읽기/쓰기
                                    └── load_config() 유효성 검사
```

**핵심 의존성 주의점:**

- FastAPI 앱은 봇 메인 프로세스(`main.py`)와 **같은 프로세스**에서 실행해야 `TrailingStopEngine` 참조 가능. 별도 프로세스면 IPC(파이프, 소켓) 추가 필요 → 복잡도 급증
- `start_scheduler()`는 블로킹 호출이므로 FastAPI + APScheduler 공존 시 **asyncio 통합** 또는 **스레드 분리** 필요. APScheduler `AsyncScheduler`(4.x) 또는 `BackgroundScheduler`(3.x) + FastAPI `lifespan` 패턴 사용
- config.toml 편집 후 engine 재초기화는 현재 폴링 사이클과 race condition 발생 가능 → 다음 사이클 시작 전까지 변경 보류(pending config) 패턴 필요

---

### 복잡도 요약

| Feature | Complexity | 기존 봇 변경 필요 여부 |
|---------|------------|----------------------|
| 실시간 모니터링 뷰 (현재가/고점/하락률) | Medium | 최소 (상태 노출 인터페이스 추가) |
| WebSocket 브로드캐스트 허브 | Medium | 없음 (FastAPI 신규) |
| 봇 상태 표시 | Low | 없음 |
| 봇 시작/중지 | Medium | APScheduler 제어 인터페이스 추가 |
| 드라이런 상시 표시 | Low | 없음 |
| 종목 추가/제거 | High | engine 재초기화 로직 추가 |
| [TRADE] 로그 파싱 테이블 | Medium | 없음 (로그 파일 읽기) |
| config.toml 편집기 | Medium | 없음 (파일 읽기/쓰기) |
| 유효성 검사 피드백 | Low | load_config() 재사용 |

---

## v1.0 MVP 피처

> 아래는 v1.0 MVP 기준 피처 분석 (2026-04-06 리서치 기준, 모두 구현 완료).

### Table Stakes

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

### Differentiators

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

### Anti-Features (v1.0)

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| 자동 매수 (auto-buy) | Scope creep. Buy logic requires entry strategy, which is a separate domain with separate risk. Mixing buy/sell in v1 complicates the codebase and decision surface. | Manual buy remains user's responsibility. Out of scope per PROJECT.md. |
| 백테스팅 엔진 | Requires historical OHLCV data pipeline, simulation loop, performance metrics. Doubles the project scope. | Accept forward-only validation. Backtest as a separate future project if needed. |
| 다중 증권사 지원 | Each broker has a different API contract. Abstraction layer adds indirection that's worthless until a second broker is needed. | KIS-only for v1. Abstract the broker interface at the module boundary so it can be extended later. |
| ML 기반 동적 임계값 | Algorithmic threshold tuning requires labeled outcome data, model training, and ongoing validation. Risk of silent misconfiguration far outweighs benefit for personal use. | Fixed per-stock thresholds in config. User adjusts manually based on experience. |
| 포트폴리오 최적화 / 리밸런싱 | Entirely different product category. Not related to stop-loss. | Not in scope. |
| 복잡한 주문 타입 (조건부 주문, OCO) | KIS API supports limited order types. Conditional order types add complexity and may not be reliably supported. | Stick to 시장가 (market order) for guaranteed fill. |
| DB 기반 이력 관리 | SQLite or Postgres for a personal bot that executes a few sells per week is over-engineering. | Append-only log files. CSV or JSONL is queryable enough with standard tools. |

---

### Feature Dependencies (v1.0)

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

### KRX / KIS-Specific Constraints Affecting Features

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

- KIS Developers API documentation (공식 문서): https://apiportal.koreainvestment.com/apiservice
- FastAPI WebSocket patterns: https://medium.com/@connect.hashblock/10-fastapi-websocket-patterns-for-live-dashboards-3e36f3080510
- FastAPI + HTMX real-time dashboards: https://medium.com/codex/building-real-time-dashboards-with-fastapi-and-htmx-01ea458673cb
- NN/g Confirmation Dialogs: https://www.nngroup.com/articles/confirmation-dialog/
- Destructive action modal UX: https://uxpsychology.substack.com/p/how-to-design-better-destructive
- APScheduler 3.x docs: https://apscheduler.readthedocs.io/en/3.x/
- Confidence note: KIS API rate limits and specific endpoint paths are MEDIUM confidence — must be verified against current KIS Developers portal before implementation
