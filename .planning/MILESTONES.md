# Milestones

## v1.0 MVP (Shipped: 2026-04-08)

**Phases completed:** 4 phases, 8 plans, 12 tasks

**Key accomplishments:**

- Python 3.11 패키지 스캐폴드 + pydantic-settings 환경변수 검증 + tomllib config.toml 로더 + exchange_calendars KRX 거래일 판정, 12개 테스트 통과
- PyKis 2.1.6 클라이언트 팩토리, 15 req/s 레이트 리밋 가격 폴링 루프(KisAPIError 방어 포함), APScheduler Mon-Fri KRX 거래일 스케줄러, loguru 봇 엔트리포인트 구현 완료 — 전체 테스트 23개 통과
- TrailingStopEngine.tick()으로 고점 추적 → 하락률 계산 → SellSignal 반환, StateStore가 tempfile+os.replace로 원자적 state.json 저장
- Settings DRY_RUN 필드 + KIS_MOCK 자동 강제 model_validator, TrailingStopEngine·StateStore를 scheduler·main.py에 통합하여 드라이런 매도 신호 로그 파이프라인 완성
- PyKis acc.sell(market="KRX", price=None, qty=orderable) 시장가 매도 실행기 — SELL_PENDING 중복 방지, 잔고 수량 조회, daily_orders() 체결 확인 폴링을 mock TDD로 구현
- scheduler.py에 executor 파라미터 추가 및 main.py에서 OrderExecutor를 초기화하여 poll_prices → engine.tick → executor.execute 전체 파이프라인 완성
- daemon Thread + asyncio.run() 패턴으로 비동기 TelegramNotifier 구현, pydantic model_validator로 자격증명 쌍 검증, python-telegram-bot 21.x 연동
- OrderExecutor에 TelegramNotifier 주입, [TRADE] 로그 마커 삽입, 종료 시 engine.states 순회 로깅으로 NOTIF-01~04 전체 충족 (전체 테스트 78개 통과)

---
