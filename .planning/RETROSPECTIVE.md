# Retrospective: MuTrade

This is a living document. Each milestone appends a new section.

---

## Milestone: v1.0 — MVP

**Shipped:** 2026-04-08
**Phases:** 4 | **Plans:** 8

### What Was Built

- **Phase 1:** Python 3.11 프로젝트 스캐폴드, pydantic-settings 설정 검증, KIS OAuth 인증, 15 req/s 레이트 리밋 가격 폴링 루프, APScheduler KRX 거래일 스케줄러 (23개 테스트)
- **Phase 2:** TDD 기반 TrailingStopEngine — 고점 추적, 하락률 계산, SellSignal 발생, tempfile+os.replace 원자적 state.json 저장, 드라이런 모드 통합
- **Phase 3:** PyKis acc.sell() 시장가 매도 실행기 — SELL_PENDING 중복 방지, 잔고 수량 조회, daily_orders() 체결 확인 폴링, scheduler/main.py 파이프라인 완성
- **Phase 4:** daemon Thread + asyncio.run() TelegramNotifier, [TRADE] 로그 마커, 종료 시 engine.states 순회 로깅 (전체 78개 테스트 통과)

### What Worked

- **TDD 선행:** 모든 핵심 모듈(TrailingStopEngine, OrderExecutor, TelegramNotifier)을 TDD로 구현하여 회귀 없이 통합 완료
- **의존성 그래프 기반 페이즈 순서:** auth → engine → order → notification 순서가 명확하여 각 페이즈가 이전 페이즈 결과물을 그대로 활용
- **선택적 Telegram 필드:** `telegram_bot_token=None` 기본값으로 알림 미설정 시에도 봇이 정상 동작 — 개발/테스트 중 불필요한 설정 없이 진행 가능
- **[TRADE] 로그 마커:** DB 없이 grep으로 거래 이력 추출 가능한 단순하고 효과적인 패턴

### What Was Inefficient

- **REQUIREMENTS.md 업데이트 누락:** Phase 4 완료 후 NOTIF-01~04 체크박스가 업데이트되지 않아 마일스톤 완료 시 문서 불일치 발생 — 페이즈 전환 시 requirements 체크박스를 SUMMARY 작성과 함께 업데이트해야 함
- **ROADMAP.md Progress 테이블 지연 업데이트:** Phase 3 완료 후에도 "1/2 plans - In Progress"로 남아있었음

### Patterns Established

- `TYPE_CHECKING` 가드로 순환 임포트 방지하면서 타입 힌트 유지
- `model_validator`로 환경변수 쌍(token + chat_id) 검증
- `KIS_MOCK=true` 시 `DRY_RUN` 자동 강제 — 모의투자 환경에서 실매도 방지
- python-kis 실제 PyPI 버전 확인 필수 (CLAUDE.md 권고 4.x vs 실제 2.1.6)

### Key Lessons

- KIS API `tr_id` 값은 프로덕션/모의투자 구분이 필수 — 실거래 전 반드시 KIS Developers 포털에서 확인
- `exchange_calendars` XKRX가 KRX 공휴일 오프라인 판정에 충분 — 별도 API 호출 불필요
- `python-telegram-bot` 21.x의 `asyncio.run()` 패턴은 동기 컨텍스트에서 안정적으로 동작

### Cost Observations

- Sessions: ~2일 (2026-04-06 ~ 2026-04-08)
- Timeline: Foundation → Engine → Orders → Notifications 순차 진행
- 78 tests, 0 failures at milestone close

---

## Cross-Milestone Trends

| Metric | v1.0 |
|--------|------|
| Phases | 4 |
| Plans | 8 |
| Tests at close | 78 |
| Timeline (days) | 2 |
| LOC | ~11,900 |
