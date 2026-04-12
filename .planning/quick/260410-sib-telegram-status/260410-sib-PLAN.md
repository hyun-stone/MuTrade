---
phase: quick
plan: 260410-sib
type: execute
wave: 1
depends_on: []
files_modified:
  - mutrade/notifier/telegram_listener.py
  - mutrade/main.py
  - tests/test_telegram_listener.py
autonomous: true
must_haves:
  truths:
    - "/status 명령 수신 시 모니터링 중인 종목별 현재가, 고점, 하락률을 포맷된 메시지로 응답한다"
    - "token/chat_id 미설정 시 listener가 비활성화되어 스레드를 생성하지 않는다"
    - "기존 TelegramNotifier(단방향 전송)는 변경 없이 정상 동작한다"
  artifacts:
    - path: "mutrade/notifier/telegram_listener.py"
      provides: "TelegramListener 클래스 — /status 핸들러, daemon thread polling"
    - path: "tests/test_telegram_listener.py"
      provides: "_build_status_message 포맷 검증, token 없을 때 no-op 검증"
  key_links:
    - from: "mutrade/notifier/telegram_listener.py"
      to: "engine.states"
      via: "start(engine, kis)로 주입된 참조"
    - from: "mutrade/notifier/telegram_listener.py"
      to: "kis.stock(code).quote()"
      via: "현재가 조회"
    - from: "mutrade/main.py"
      to: "mutrade/notifier/telegram_listener.py"
      via: "listener.start(engine=engine, kis=kis)"
---

<objective>
Telegram /status 명령어 수신 기능을 구현한다. 사용자가 Telegram 봇에 /status를 보내면,
TrailingStopEngine의 현재 states를 순회하여 종목별 현재가(KIS API 조회), 고점, 하락률을
포맷된 메시지로 응답한다.

Purpose: 봇 실행 중 모바일에서 모니터링 현황을 즉시 확인할 수 있다.
Output: TelegramListener 클래스, main.py 통합, 테스트.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@mutrade/notifier/telegram.py (기존 TelegramNotifier 패턴 참조 — daemon thread + asyncio.run)
@mutrade/engine/trailing_stop.py (engine.states: dict[str, SymbolState])
@mutrade/engine/models.py (SymbolState: code, peak_price, warm)
@mutrade/kis/price_feed.py (kis.stock(code).quote() 패턴)
@mutrade/settings.py (telegram_bot_token, telegram_chat_id, dry_run, kis_mock)
@mutrade/main.py (진입점 — listener 통합 위치)
@mutrade/config/loader.py (SymbolConfig: code, name, threshold)

<interfaces>
<!-- TrailingStopEngine.states -->
From mutrade/engine/trailing_stop.py:
```python
@property
def states(self) -> dict[str, SymbolState]:
    """현재 종목별 상태 복사본 반환 (읽기 전용 뷰)."""
    return dict(self._states)
```

From mutrade/engine/models.py:
```python
@dataclass
class SymbolState:
    code: str          # 종목 코드
    peak_price: float  # 고점
    warm: bool = False
```

From mutrade/config/loader.py:
```python
@dataclass
class SymbolConfig:
    code: str           # "005930"
    name: str           # "삼성전자"
    threshold: float    # 0.10
```

<!-- KIS quote 패턴 (price_feed.py) -->
```python
quote = kis.stock(symbol_code).quote()
price = float(quote.price)
```

<!-- TelegramNotifier 비활성화 패턴 -->
```python
if not self._token or not self._chat_id:
    return  # no-op
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: TelegramListener 구현 및 테스트</name>
  <files>mutrade/notifier/telegram_listener.py, tests/test_telegram_listener.py</files>
  <behavior>
    - Test: token=None일 때 start() 호출 시 스레드를 생성하지 않는다 (no-op)
    - Test: chat_id=None일 때 start() 호출 시 스레드를 생성하지 않는다 (no-op)
    - Test: _build_status_message()가 SymbolState dict와 prices dict를 받아 올바른 포맷 문자열을 반환한다
      - 종목코드, 현재가(쉼표 포맷), 고점(쉼표 포맷), 하락률(소수점 1자리 %) 포함 확인
      - dry_run/kis_mock 상태 표시 확인
    - Test: _build_status_message()에 빈 states dict를 넘기면 "모니터링 종목 없음" 메시지 반환
    - Test: 하락률 계산이 정확한지 확인 — peak=100000, current=93000 -> -7.0%
  </behavior>
  <action>
1. tests/test_telegram_listener.py 작성 (RED):
   - TelegramListener를 import
   - test_start_noop_without_token: token=None으로 TelegramListener 생성, start() 호출 후 threading.Thread가 생성되지 않았는지 확인 (listener._thread is None)
   - test_start_noop_without_chat_id: chat_id=None 동일 패턴
   - test_build_status_message_format: _build_status_message(states, prices, symbols, dry_run, kis_mock) 순수 함수 직접 호출. states={"005930": SymbolState(code="005930", peak_price=218000, warm=True)}, prices={"005930": 204000}, symbols={"005930": SymbolConfig(code="005930", name="삼성전자", threshold=0.10)}. 반환 문자열에 "005930", "삼성전자", "204,000", "218,000", "-6.4%" 포함 확인
   - test_build_status_message_empty: 빈 states → "모니터링 종목 없음" 포함 확인
   - test_drop_pct_calculation: peak=100000, current=93000 → "-7.0%" 포함 확인

2. mutrade/notifier/telegram_listener.py 구현 (GREEN):
   - `_build_status_message(states, prices, symbols, dry_run, kis_mock)` 를 모듈 레벨 순수 함수로 작성 (테스트 용이)
     - datetime.now(KST).strftime("%Y-%m-%d %H:%M KST") 타임스탬프
     - states가 비어있으면 "모니터링 종목 없음" 반환
     - states 순회: code별 현재가는 prices[code]에서 가져옴, 없으면 "조회실패"
     - 하락률: (peak - current) / peak * 100, 소수점 1자리
     - 포맷: 종목코드 종목명 / 현재가: X원 | 고점: Y원 | 하락률: -Z.Z%
     - 하단에 DRY_RUN: ON/OFF | 모의투자: ON/OFF 표시

   - `TelegramListener` 클래스:
     - __init__(self, token: str | None, chat_id: str | None): token, chat_id 저장. _thread = None, _app = None
     - start(self, engine, kis, symbols, dry_run, kis_mock): token/chat_id 없으면 즉시 return (no-op). 있으면 self._engine, self._kis, self._symbols, self._dry_run, self._kis_mock 저장. daemon Thread 시작 → self._run_polling()
     - _run_polling(self): 새 asyncio 이벤트 루프에서 python-telegram-bot Application 생성, /status 핸들러 등록, run_polling() 실행
     - async _handle_status(self, update, context): engine.states 순회, 각 종목 kis.stock(code).quote()로 현재가 조회 (try/except — 실패 시 None), _build_status_message() 호출, update.message.reply_text() 응답. chat_id 검증: str(update.effective_chat.id) != self._chat_id이면 무시 (보안)
     - stop(self): _app이 있으면 _app.stop() 시도 (best-effort, 로그만)

   - 보안: T-04-01 준수 — token을 로그에 절대 출력하지 않음. chat_id 검증으로 허가된 사용자만 응답.

3. 테스트 실행하여 GREEN 확인.
  </action>
  <verify>
    <automated>cd /Users/sean/Study/MuTrade/MuTrade && python -m pytest tests/test_telegram_listener.py -x -v</automated>
  </verify>
  <done>
    - TelegramListener 클래스가 /status 핸들러를 등록하고 daemon thread에서 polling
    - _build_status_message가 종목별 현재가, 고점, 하락률을 정확히 포맷
    - token/chat_id 없으면 start()가 no-op (스레드 미생성)
    - 모든 테스트 통과
  </done>
</task>

<task type="auto">
  <name>Task 2: main.py에 TelegramListener 통합</name>
  <files>mutrade/main.py</files>
  <action>
mutrade/main.py 수정:

1. import 추가:
   ```python
   from mutrade.notifier.telegram_listener import TelegramListener
   ```

2. main() 함수에서 `start_scheduler()` 호출 직전에 TelegramListener 초기화 및 시작 코드 추가:
   ```python
   # Telegram /status 수신 리스너 (token/chat_id 없으면 no-op)
   listener = TelegramListener(
       token=settings.telegram_bot_token,
       chat_id=settings.telegram_chat_id,
   )
   listener.start(
       engine=engine,
       kis=kis,
       symbols={s.code: s for s in config.symbols},
       dry_run=settings.dry_run,
       kis_mock=settings.kis_mock,
   )
   if settings.telegram_bot_token:
       logger.info("Telegram /status 리스너 활성화.")
   ```

3. 기존 TelegramNotifier 코드는 변경하지 않음.

4. 전체 테스트 실행하여 기존 테스트 깨지지 않는지 확인.
  </action>
  <verify>
    <automated>cd /Users/sean/Study/MuTrade/MuTrade && python -m pytest tests/ -x -v</automated>
  </verify>
  <done>
    - main.py에서 TelegramListener가 start_scheduler() 전에 초기화 및 시작됨
    - 기존 TelegramNotifier는 변경 없음
    - 전체 테스트 스위트 통과 (기존 + 신규)
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| Telegram -> Bot | 외부 사용자가 /status 명령을 보낼 수 있음 |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-quick-01 | Spoofing | /status handler | mitigate | chat_id 검증: update.effective_chat.id != 설정된 chat_id이면 응답 무시 |
| T-quick-02 | Information Disclosure | _build_status_message | accept | 종목코드/가격은 민감 정보가 아님. 봇 토큰/API 키는 메시지에 포함하지 않음 |
| T-quick-03 | Denial of Service | run_polling | accept | 개인용 봇이므로 대량 요청 가능성 낮음. python-telegram-bot이 기본 rate limit 처리 |
</threat_model>

<verification>
1. `python -m pytest tests/ -x -v` 전체 통과
2. `python -c "from mutrade.notifier.telegram_listener import TelegramListener"` import 성공
</verification>

<success_criteria>
- TelegramListener가 /status 명령에 종목별 현재가, 고점, 하락률 포맷 메시지로 응답
- token/chat_id 미설정 시 no-op (스레드 미생성, 에러 없음)
- 기존 TelegramNotifier 변경 없음
- 전체 테스트 스위트 통과
</success_criteria>

<output>
After completion, create `.planning/quick/260410-sib-telegram-status/260410-sib-SUMMARY.md`
</output>
