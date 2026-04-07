# Phase 4: Notifications and Operational Polish - Context

**Gathered:** 2026-04-08
**Status:** Ready for planning

<domain>
## Phase Boundary

매도 실행 시 즉각 Telegram 알림 전송, 모든 거래 이력을 로그 파일에 타임스탬프와 함께 기록, 봇 시작·종료 시 모니터링 종목 목록과 고점 상태 로깅.

이 페이즈는 Phase 3 OrderExecutor가 이미 완성된 이후 단계 — 새로운 매도 로직 없음. 기존 파이프라인에 알림·로그 훅만 추가.

범위 밖: KakaoTalk, 웹 인터페이스, 일별 리포트, API 오류 경보 (v2 범위).

</domain>

<decisions>
## Implementation Decisions

### Telegram 설정

- **D-01:** `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`를 `Settings`에 **선택적 필드(None 허용)**로 추가한다. 미설정 시 알림 없이 봇 정상 실행. Settings 유효성 검사: 두 필드 중 하나만 있으면 ValidationError (둘 다 있거나 둘 다 없어야 함).

- **D-02:** Telegram 알림 전송 실패(네트워크 오류, 토큰 만료 등) 시 `logger.error()`로 기록 후 무시한다. 알림 실패가 매도 주문 흐름을 차단하지 않는다 (NOTIF-02 충족).

### 알림 전송 시점

- **D-03:** Telegram 알림은 `acc.sell()` 성공 직후(주문번호 반환 시점) 즉시 전송한다. `_confirm_fill()` 폴링을 기다리지 않는다. 시장가 주문이므로 미체결 가능성은 극히 낮고, 빠른 알림이 우선.

### 알림 메시지 형식

- **D-04:** Telegram 메시지에 다음 정보를 포함한다:
  ```
  🚨 매도 주문 제출
  종목: {name} ({code})
  수량: {qty}주 / 현재가: {current_price:,}원
  고점: {peak_price:,}원 / 하락률: {drop_pct:.2%}
  임계값: {threshold:.1%}
  시간: {KST timestamp}
  ```
  SellSignal의 모든 필드(code, name, current_price, peak_price, drop_pct, threshold)를 활용.

### Claude's Discretion

- **비동기 알림 구현:** BlockingScheduler 단일 스레드 환경에서 `threading.Thread(target=..., daemon=True)`로 백그라운드 전송. asyncio 오버헤드 불필요. 실패해도 메인 스레드 차단 없음 (D-02와 일관성).

- **거래 이력 로그(NOTIF-03):** 별도 파일 없이 기존 `logs/mutrade.log`에 통합. loguru `logger.info("[TRADE] ...")`로 구조적 로그라인 작성. 필요 시 `grep "[TRADE]"`로 추출 가능.

- **봇 종료 로그(NOTIF-04):** `start_scheduler()`의 `except (KeyboardInterrupt, SystemExit)` 블록에서 현재 `engine.states` 전체를 순회해 종목코드·고점·warm 상태를 INFO 로그로 출력 후 종료. NOTIF-04 "final log entry" 요건 충족.

- **알림 모듈 위치:** `mutrade/notifier/telegram.py` 신설. `TelegramNotifier(token, chat_id)` 클래스로 캡슐화. `OrderExecutor`는 생성 시 주입받음.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 요구사항
- `.planning/REQUIREMENTS.md` §알림 및 로그 (NOTIF) — NOTIF-01~04: 알림 전송, 비동기 처리, 거래 이력 로그, 시작/종료 로그
- `.planning/ROADMAP.md` §Phase 4 — Goal, success criteria 4개 항목

### 기반 코드 (Phase 1~3 산출물)
- `mutrade/executor/order_executor.py` — `_submit_order()`: 알림 삽입 지점 (acc.sell() 직후). `execute()`: dry_run 분기 확인.
- `mutrade/monitor/scheduler.py` — `run_session()`: 시작 로그 지점 (종목/고점 이미 출력). `start_scheduler()::except` 블록: 종료 로그 삽입 지점.
- `mutrade/main.py` — loguru 핸들러 설정, Settings/Config 로드 순서. `OrderExecutor` 초기화 위치.
- `mutrade/settings.py` — `Settings` (pydantic-settings). `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` 선택적 필드 추가 위치. model_validator 패턴 참조.
- `mutrade/engine/models.py` — `SellSignal` 필드 목록 (알림 메시지 구성에 사용).

### 기술 스택
- `CLAUDE.md` §Notification — `python-telegram-bot 21.x` 채택. KakaoTalk 제외 이유 포함.
- `CLAUDE.md` §Technology Stack — 금지 목록 (LINE Notify 종료 등)

</canonical_refs>

<code_context>
## Existing Code Insights

### 알림 삽입 지점
- `mutrade/executor/order_executor.py::_submit_order()` L63-70: `order = acc.sell(...)` 이후, `logger.warning("[LIVE] ...")` 다음 줄이 알림 전송 위치
- `mutrade/executor/order_executor.py::execute()` L38-43: dry_run 분기 — dry_run 시 알림 없음 (실거래 알림만)

### 로그 훅 지점
- `mutrade/monitor/scheduler.py::run_session()` L38-48: 시작 시 종목 목록/고점 이미 로그됨 → "[TRADE]" 마커 추가만 하면 됨
- `mutrade/monitor/scheduler.py::start_scheduler()` L95-97: `except (KeyboardInterrupt, SystemExit)` 블록 — 종료 시 고점 요약 로그 삽입 위치

### 기존 패턴
- loguru `logger.add("logs/mutrade.log", ...)` — 이미 설정됨. 새 로그 파일 추가 불필요.
- `Settings` model_validator 패턴 — `validate_virtual_credentials()` 참조 (token/chat_id 쌍 검증에 동일 패턴 적용)

### 신규 모듈
- `mutrade/notifier/` 디렉터리 신설 필요
- `mutrade/notifier/__init__.py`
- `mutrade/notifier/telegram.py` — `TelegramNotifier` 클래스

</code_context>

<deferred>
## Deferred Ideas

없음.
</deferred>
