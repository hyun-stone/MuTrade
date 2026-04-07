# Phase 4: Notifications and Operational Polish - Research

**Researched:** 2026-04-08
**Domain:** python-telegram-bot 21.x 알림, loguru 구조적 로그, pydantic-settings model_validator
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `TELEGRAM_BOT_TOKEN`과 `TELEGRAM_CHAT_ID`를 `Settings`에 선택적 필드(None 허용)로 추가. 미설정 시 알림 없이 봇 정상 실행. 두 필드 중 하나만 있으면 ValidationError (둘 다 있거나 둘 다 없어야 함).
- **D-02:** Telegram 알림 전송 실패 시 `logger.error()`로 기록 후 무시. 알림 실패가 매도 주문 흐름을 차단하지 않음 (NOTIF-02 충족).
- **D-03:** Telegram 알림은 `acc.sell()` 성공 직후(주문번호 반환 시점) 즉시 전송. `_confirm_fill()` 폴링을 기다리지 않음.
- **D-04:** 메시지 형식:
  ```
  🚨 매도 주문 제출
  종목: {name} ({code})
  수량: {qty}주 / 현재가: {current_price:,}원
  고점: {peak_price:,}원 / 하락률: {drop_pct:.2%}
  임계값: {threshold:.1%}
  시간: {KST timestamp}
  ```

### Claude's Discretion

- **비동기 알림 구현:** `threading.Thread(target=..., daemon=True)` 백그라운드 전송.
- **거래 이력 로그(NOTIF-03):** 기존 `logs/mutrade.log`에 통합. `logger.info("[TRADE] ...")` 마커 사용.
- **봇 종료 로그(NOTIF-04):** `start_scheduler()`의 `except (KeyboardInterrupt, SystemExit)` 블록에서 `engine.states` 순회 후 종료.
- **알림 모듈 위치:** `mutrade/notifier/telegram.py` 신설. `TelegramNotifier(token, chat_id)` 클래스.

### Deferred Ideas (OUT OF SCOPE)

없음.

</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| NOTIF-01 | 매도 실행 시 Telegram으로 종목명·매도가·수량을 포함한 알림을 전송한다 | `Bot.send_message()` + `asyncio.run()` 패턴, `TelegramNotifier` 클래스 설계 |
| NOTIF-02 | 알림 전송은 매도 주문 제출 이후 비동기로 처리한다 | `threading.Thread(daemon=True)` 패턴으로 BlockingScheduler 블로킹 없이 처리 |
| NOTIF-03 | 모든 매도 이력을 타임스탬프와 함께 로그 파일에 기록한다 | loguru `[TRADE]` 마커 패턴, 기존 `logs/mutrade.log` 활용 |
| NOTIF-04 | 봇 시작·종료 시 현재 모니터링 대상 종목 목록과 고점 데이터를 로그에 기록한다 | `engine.states` 순회 패턴, `start_scheduler()` except 블록 삽입 지점 |

</phase_requirements>

---

## Summary

Phase 4는 Phase 1~3의 완성된 파이프라인에 알림·로그 훅만 추가하는 단계다. 핵심 기술 과제는 두 가지다: (1) `python-telegram-bot 21.x`의 asyncio-only API를 BlockingScheduler 단일 스레드 환경에서 안전하게 사용하는 방법, (2) pydantic-settings model_validator를 사용한 선택적 자격증명 쌍 검증.

`python-telegram-bot` v20.0부터 모든 Bot API 메서드가 코루틴이 되었다. [VERIFIED: github.com/python-telegram-bot wiki] 단순 알림 전송(수신 없음)의 경우 `Application` 없이 `Bot` 객체 직접 사용이 권장된다. daemon 스레드 내에서 `asyncio.run(bot.send_message(...))` 패턴이 정상 동작한다 — 각 스레드가 독립적인 이벤트 루프를 생성하므로 "Event loop is closed" 오류가 발생하지 않는다. [VERIFIED: github.com/python-telegram-bot discussions #4167]

PyPI 최신 버전은 **22.5**다 [VERIFIED: pip index versions]. CLAUDE.md는 21.x를 지정하지만, 21.11.1이 마지막 21.x 릴리스다. 22.x는 21.x와 호환성 유지 (send_message API 변경 없음). [ASSUMED] `pyproject.toml`에 `python-telegram-bot`이 현재 없으므로 추가가 필요하다.

**Primary recommendation:** `mutrade/notifier/telegram.py`에 `TelegramNotifier` 클래스를 구현하고, daemon Thread 내 `asyncio.run(bot.send_message(...))`으로 알림을 전송한다. `OrderExecutor.__init__`에서 주입받고, `_submit_order()` L85-91 직후(주문번호 로그 다음 줄)에 `notifier.notify(signal, qty)` 호출한다.

---

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `python-telegram-bot` | 21.11.1 (21.x 최신) | Telegram Bot API 클라이언트 | CLAUDE.md 지정. asyncio-native, Bot.send_message 단일 호출로 알림 전송 가능 |
| `loguru` | 0.7.3 (현재 설치) | 구조적 로그, [TRADE] 마커 | 이미 사용 중. 추가 설정 불필요 |
| `pydantic-settings` | 2.13.1 (현재 설치) | Settings 확장, model_validator | 이미 사용 중. validate_virtual_credentials 패턴 재사용 |

[VERIFIED: `pip index versions python-telegram-bot` — 22.5가 최신이나 21.11.1이 21.x 마지막. pyproject.toml 현재 미포함]

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `asyncio` (stdlib) | 3.11+ | `asyncio.run()` - daemon thread에서 코루틴 실행 | TelegramNotifier 내부에서만 사용 |
| `threading` (stdlib) | 3.11+ | daemon Thread 생성 | BlockingScheduler 블로킹 방지 |
| `zoneinfo` (stdlib) | 3.9+ | KST 타임스탬프 생성 | 알림 메시지 시간 포맷 |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `python-telegram-bot 21.x` | `requests`로 직접 Telegram Bot API REST 호출 | requests는 asyncio 불필요하나, 라이브러리 없이 에러 처리 직접 구현 필요. CLAUDE.md가 21.x 지정이므로 사용하지 않음 |
| `threading.Thread` daemon | `concurrent.futures.ThreadPoolExecutor` | ThreadPoolExecutor도 유효하나, 단발성 알림에는 Thread가 더 간단 |

**Installation:**
```bash
pip install "python-telegram-bot==21.11.1"
```

그리고 `pyproject.toml` dependencies에 추가:
```
"python-telegram-bot==21.11.1",
```

---

## Architecture Patterns

### Recommended Project Structure
```
mutrade/
├── notifier/
│   ├── __init__.py          # 빈 파일 또는 TelegramNotifier 재export
│   └── telegram.py          # TelegramNotifier 클래스
├── executor/
│   └── order_executor.py    # TelegramNotifier 주입 받아 사용 (수정)
├── monitor/
│   └── scheduler.py         # 종료 로그 추가 (수정)
├── settings.py              # TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID 추가 (수정)
└── main.py                  # TelegramNotifier 초기화 및 주입 (수정)
```

### Pattern 1: TelegramNotifier 클래스 설계

**What:** `Bot` 객체를 감싸는 얇은 래퍼. 설정 미완료 시 no-op. 실패 시 로그만 남기고 무시.
**When to use:** `OrderExecutor`에 주입, `notify()` 메서드 한 번 호출로 완료.

```python
# Source: [VERIFIED: github.com/python-telegram-bot transition guide v20.0]
# mutrade/notifier/telegram.py
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from telegram import Bot

KST = ZoneInfo("Asia/Seoul")


class TelegramNotifier:
    """Telegram 알림 전송기.

    token/chat_id가 None이면 no-op 모드로 동작 (알림 없이 정상 실행).
    전송 실패 시 logger.error()로 기록 후 무시 — 매도 흐름 차단 없음 (D-02).
    """

    def __init__(self, token: str | None, chat_id: str | None):
        self._token = token
        self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    def notify(self, signal, qty: int) -> None:
        """매도 신호에 대한 Telegram 알림을 daemon 스레드에서 비동기 전송.

        Args:
            signal: SellSignal 인스턴스
            qty: 실제 매도 수량 (orderable 조회 값)
        """
        if not self._enabled:
            return

        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
        text = (
            "🚨 매도 주문 제출\n"
            f"종목: {signal.name} ({signal.code})\n"
            f"수량: {qty:,}주 / 현재가: {signal.current_price:,.0f}원\n"
            f"고점: {signal.peak_price:,.0f}원 / 하락률: {signal.drop_pct:.2%}\n"
            f"임계값: {signal.threshold:.1%}\n"
            f"시간: {now_kst}"
        )

        def _send():
            try:
                asyncio.run(self._send_message(text))
            except Exception as e:
                logger.error("Telegram 알림 전송 실패: {}", e)

        threading.Thread(target=_send, daemon=True).start()

    async def _send_message(self, text: str) -> None:
        bot = Bot(token=self._token)
        await bot.send_message(chat_id=self._chat_id, text=text)
```

[VERIFIED: github.com/python-telegram-bot discussions #4167 — daemon thread에서 Bot.send_message를 asyncio.run으로 호출하는 패턴 확인]
[VERIFIED: github.com/python-telegram-bot wiki Transition guide v20.0 — `asyncio.run(bot.send_message(...))` 동기 컨텍스트에서 사용 가능]

### Pattern 2: Settings 확장 — 선택적 자격증명 쌍 검증

**What:** 기존 `validate_virtual_credentials` 패턴을 재사용. 두 필드가 "둘 다 있거나 둘 다 없어야 함" 조건.
**When to use:** `Settings` 클래스 수정 시.

```python
# Source: [VERIFIED: 기존 mutrade/settings.py validate_virtual_credentials 패턴]
# mutrade/settings.py 추가 필드 및 validator

telegram_bot_token: str | None = Field(None, alias="TELEGRAM_BOT_TOKEN")
telegram_chat_id: str | None = Field(None, alias="TELEGRAM_CHAT_ID")

@model_validator(mode="after")
def validate_telegram_credentials(self) -> "Settings":
    """TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID는 둘 다 있거나 둘 다 없어야 함."""
    has_token = bool(self.telegram_bot_token)
    has_chat_id = bool(self.telegram_chat_id)
    if has_token != has_chat_id:
        missing = "TELEGRAM_CHAT_ID" if has_token else "TELEGRAM_BOT_TOKEN"
        raise ValueError(
            f"Telegram 설정 불완전: {missing}가 누락되었습니다. "
            "TELEGRAM_BOT_TOKEN과 TELEGRAM_CHAT_ID는 둘 다 설정하거나 둘 다 생략하세요."
        )
    return self
```

### Pattern 3: [TRADE] 마커 로그 — NOTIF-03

**What:** `logger.info("[TRADE] ...")` 한 줄로 매도 이력 기록. 별도 파일 불필요.
**When to use:** `_submit_order()` 내 주문번호 로그 직후 (또는 체결 확인 후).

```python
# Source: [VERIFIED: 기존 mutrade/main.py loguru 설정 확인]
# _submit_order() 내 order = acc.sell(...) 성공 직후
logger.info(
    "[TRADE] 매도 주문 제출: {} ({}) qty={} price={:,.0f} peak={:,.0f} "
    "drop={:.2%} threshold={:.1%} order_no={}",
    signal.code, signal.name, qty,
    signal.current_price, signal.peak_price,
    signal.drop_pct, signal.threshold,
    order.number,
)
```

`grep "[TRADE]" logs/mutrade.log`으로 거래 이력만 추출 가능. [VERIFIED: 기존 main.py loguru 파일 핸들러 `logs/mutrade.log`에 이미 기록됨]

### Pattern 4: 봇 종료 로그 — NOTIF-04

**What:** `start_scheduler()` except 블록에서 `engine.states` 순회.
**When to use:** `KeyboardInterrupt` / `SystemExit` 핸들러.

```python
# Source: [VERIFIED: 기존 mutrade/monitor/scheduler.py L149-152]
# start_scheduler() except 블록 수정
except (KeyboardInterrupt, SystemExit):
    logger.info("Scheduler stopped by user. Final state snapshot:")
    for code, state in engine.states.items():
        logger.info(
            "  [SHUTDOWN] {} peak={:,.0f} warm={}",
            code, state.peak_price, state.warm,
        )
    logger.info("MuTrade shutdown complete.")
```

`engine`을 `start_scheduler()` 파라미터로 이미 받고 있으므로 추가 의존성 없음. [VERIFIED: 기존 scheduler.py L113-115]

### Pattern 5: main.py TelegramNotifier 초기화 및 주입

```python
# Source: [VERIFIED: 기존 mutrade/main.py OrderExecutor 초기화 패턴]
# main.py 수정 — OrderExecutor 초기화 직전
from mutrade.notifier.telegram import TelegramNotifier

notifier = TelegramNotifier(
    token=settings.telegram_bot_token,
    chat_id=settings.telegram_chat_id,
)
executor = OrderExecutor(kis=kis, dry_run=settings.dry_run, notifier=notifier)
```

### Anti-Patterns to Avoid

- **`asyncio.get_event_loop().run_until_complete()` 사용:** Python 3.10+에서 deprecated. `asyncio.run()` 사용 필수.
- **Bot 객체를 인스턴스 변수로 유지하며 재사용:** `Bot.__init__`이 새 httpx 세션을 생성하므로 단발 알림에서는 매번 새 Bot 생성이 올바름. Application 없이 Bot만 사용 시 `async with Bot(token) as bot:` 패턴이 더 안전. [ASSUMED — connection pool cleanup 관련]
- **알림 실패 시 raise:** D-02 위반. 반드시 `except Exception: logger.error(...)` 후 pass.
- **`signal.dry_run` 검사 없이 알림 전송:** dry_run 시 실매도 없으므로 알림도 없어야 함. `execute()` 메서드의 dry_run 분기에서 `notify()` 호출하지 않도록 주의.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Telegram HTTP 요청 | 직접 `requests.post()` 또는 `httpx.post()` | `python-telegram-bot Bot.send_message()` | 에러 코드 파싱, rate limit 처리, HTML/Markdown 이스케이프 내장 |
| asyncio 이벤트 루프 재사용 | 글로벌 이벤트 루프 공유 | 각 daemon thread에서 `asyncio.run()` | BlockingScheduler 단일 스레드에서 글로벌 루프는 안전하지 않음 |
| 구조적 로그 포맷터 | 커스텀 JSON logger | loguru `[TRADE]` 마커 | 이미 설정된 loguru 핸들러 재사용. `grep "[TRADE]"`으로 충분 |

---

## Common Pitfalls

### Pitfall 1: `asyncio.run()` 중첩 호출 오류
**What goes wrong:** daemon thread 내에서 이미 실행 중인 이벤트 루프가 있으면 `asyncio.run()`이 `RuntimeError: This event loop is already running`을 발생시킴.
**Why it happens:** 일부 환경(Jupyter 등)에서는 이미 이벤트 루프가 실행 중. BlockingScheduler 환경에서는 해당 없음.
**How to avoid:** BlockingScheduler는 asyncio를 사용하지 않으므로 daemon thread의 `asyncio.run()`은 안전. 단, `asyncio.get_event_loop()`나 `loop.run_until_complete()` 대신 반드시 `asyncio.run()` 사용.
**Warning signs:** `RuntimeError: This event loop is already running` 오류 메시지.

### Pitfall 2: `async with Bot(...)` vs `Bot(...)` 직접 인스턴스
**What goes wrong:** `Bot` 객체를 `await bot.initialize()` 없이 사용하면 일부 메서드에서 경고 또는 연결 오류 발생.
**Why it happens:** v21에서 Bot은 내부 httpx 클라이언트를 초기화해야 함.
**How to avoid:** `_send_message` 내부에서 `async with Bot(token=self._token) as bot: await bot.send_message(...)` 패턴 사용. [ASSUMED — v21 Bot context manager 권장 여부 불확실, 추가 검증 권장]
**Warning signs:** 연결 관련 경고 로그, 간헐적 타임아웃.

### Pitfall 3: dry_run 시 알림 전송
**What goes wrong:** dry_run 매도 신호에서도 `notify()`가 호출되어 실제 Telegram 메시지 전송.
**Why it happens:** `execute()`에서 dry_run 분기 반환 전에 알림 호출이 삽입되는 경우.
**How to avoid:** `_submit_order()` 내부 (`acc.sell()` 직후)에만 알림 삽입. `execute()`의 dry_run 분기(L38-44)에는 알림 없음. [VERIFIED: 기존 order_executor.py L38-44 dry_run 분기 확인]

### Pitfall 4: `OrderExecutor.__init__` 시그니처 변경으로 테스트 파손
**What goes wrong:** `notifier` 파라미터 추가 후 기존 `test_order_executor.py`가 `OrderExecutor(kis)` 형태로 호출하여 TypeError.
**Why it happens:** 기존 테스트 14개가 `OrderExecutor(kis)` 또는 `OrderExecutor(kis, dry_run=...)` 패턴 사용.
**How to avoid:** `notifier: TelegramNotifier | None = None` 기본값으로 추가. 기존 테스트 수정 불필요. [VERIFIED: 기존 test_order_executor.py make_kis_mock, TestOrderExecutor 패턴 확인]

### Pitfall 5: `engine.states` 접근 시점 — 종료 로그
**What goes wrong:** `start_scheduler()` except 블록에서 `engine`을 참조할 수 없음.
**Why it happens:** 현재 `start_scheduler()`가 `engine`을 파라미터로 받으나, except 블록에서 스코프 내에 있는지 확인 필요.
**How to avoid:** [VERIFIED: 기존 scheduler.py L113-115] `start_scheduler(engine: TrailingStopEngine)`으로 이미 파라미터 있음. except 블록(L149-152)에서 `engine`은 함수 스코프 내에 있으므로 접근 가능.

---

## Code Examples

### TelegramNotifier 완전한 구현 (Bot context manager 패턴)

```python
# Source: [CITED: github.com/python-telegram-bot transition guide v20.0]
# mutrade/notifier/telegram.py

import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from telegram import Bot

KST = ZoneInfo("Asia/Seoul")


class TelegramNotifier:
    def __init__(self, token: str | None, chat_id: str | None):
        self._token = token
        self._chat_id = chat_id
        self._enabled = bool(token and chat_id)

    def notify(self, signal, qty: int) -> None:
        if not self._enabled:
            return
        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
        text = (
            "🚨 매도 주문 제출\n"
            f"종목: {signal.name} ({signal.code})\n"
            f"수량: {qty:,}주 / 현재가: {signal.current_price:,.0f}원\n"
            f"고점: {signal.peak_price:,.0f}원 / 하락률: {signal.drop_pct:.2%}\n"
            f"임계값: {signal.threshold:.1%}\n"
            f"시간: {now_kst}"
        )
        threading.Thread(target=self._send_in_thread, args=(text,), daemon=True).start()

    def _send_in_thread(self, text: str) -> None:
        try:
            asyncio.run(self._send_message(text))
        except Exception as e:
            logger.error("Telegram 알림 전송 실패: {}", e)

    async def _send_message(self, text: str) -> None:
        async with Bot(token=self._token) as bot:
            await bot.send_message(chat_id=self._chat_id, text=text)
```

### OrderExecutor 수정 지점

```python
# Source: [VERIFIED: 기존 mutrade/executor/order_executor.py L60-92]
# _submit_order() 내 order = acc.sell(...) 직후

order = acc.sell(
    market="KRX",
    symbol=signal.code,
    price=None,
    qty=qty,
)
logger.warning(
    "[LIVE] 매도 주문 제출: {} ({}) qty={} 주문번호={}",
    signal.code, signal.name, qty, order.number,
)
# [NEW] NOTIF-03: 거래 이력 로그
logger.info(
    "[TRADE] {} ({}) qty={} current_price={:,.0f} peak={:,.0f} "
    "drop={:.2%} threshold={:.1%} order_no={}",
    signal.code, signal.name, qty,
    signal.current_price, signal.peak_price,
    signal.drop_pct, signal.threshold,
    order.number,
)
# [NEW] NOTIF-01/02: Telegram 알림 (daemon thread, 비동기)
if self._notifier is not None:
    self._notifier.notify(signal, qty)

self._confirm_fill(acc, order, signal.code)
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `bot.send_message()` (sync) | `await bot.send_message()` | v20.0 (2022) | asyncio.run() 래퍼 필요 |
| `Updater` 클래스 | `Application.builder()` | v20.0 (2022) | 단순 알림은 Bot 직접 사용으로 대응 |
| LINE Notify | 사용 불가 (2025-03-31 종료) | 2025-03-31 | Telegram 사용 |

**Deprecated/outdated:**
- LINE Notify: 2025-03-31 완전 종료. [VERIFIED: CLAUDE.md]
- `python-telegram-bot` 13.x 이하의 동기 API: 더 이상 지원 안 됨.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `async with Bot(token) as bot:` 패턴이 v21.x에서 connection pool 정상 해제 | Code Examples | 연결 누수 가능성 (단발 알림이므로 실제 영향 낮음) |
| A2 | `python-telegram-bot 22.x`가 21.x와 `Bot.send_message` API 호환 | Standard Stack | 22.x로 업그레이드 시 코드 수정 불필요 |

---

## Open Questions

1. **`python-telegram-bot` 21.x vs 22.x 선택**
   - What we know: CLAUDE.md가 21.x를 지정. PyPI 최신은 22.5.
   - What's unclear: 22.x가 21.x와 완전 호환인지 breaking change 여부.
   - Recommendation: CLAUDE.md 지시에 따라 21.11.1 핀. 이후 마이그레이션은 별도 결정.

2. **`async with Bot(...)` vs `Bot(...)` 직접 인스턴스화**
   - What we know: v20+ 공식 예제는 `async with Bot(...)` 패턴 사용. 직접 인스턴스도 동작하나 경고 가능성.
   - What's unclear: v21.11.1에서 직접 인스턴스화 시 httpx 세션 정리 여부.
   - Recommendation: `async with Bot(...)` 패턴 사용 (명시적 cleanup).

---

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `python-telegram-bot` | NOTIF-01, NOTIF-02 | ✗ (미설치) | — | 없음 — `pip install` 필요 |
| `loguru` | NOTIF-03, NOTIF-04 | ✓ | 0.7.3 | — |
| `pydantic-settings` | D-01 Settings 확장 | ✓ | 2.13.1 | — |
| Python `asyncio` (stdlib) | TelegramNotifier | ✓ | 3.11+ (stdlib) | — |
| Python `threading` (stdlib) | NOTIF-02 | ✓ | 3.11+ (stdlib) | — |
| Python `zoneinfo` (stdlib) | KST 타임스탬프 | ✓ | 3.11+ (stdlib) | — |

**Missing dependencies with no fallback:**
- `python-telegram-bot==21.11.1` — Wave 0 또는 첫 태스크에서 `pyproject.toml`에 추가 후 설치 필요.

[VERIFIED: `pyproject.toml` dependencies 목록에 `python-telegram-bot` 없음]

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (설치됨) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `python -m pytest tests/ -x -q` |
| Full suite command | `python -m pytest tests/ -v` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| NOTIF-01 | TelegramNotifier.notify()가 Bot.send_message를 호출함 | unit | `python -m pytest tests/test_telegram_notifier.py -x` | ❌ Wave 0 |
| NOTIF-02 | notify()가 daemon Thread를 생성하고 즉시 반환 | unit | `python -m pytest tests/test_telegram_notifier.py::test_notify_is_nonblocking -x` | ❌ Wave 0 |
| NOTIF-02 | 알림 실패 시 예외가 main thread로 전파되지 않음 | unit | `python -m pytest tests/test_telegram_notifier.py::test_notify_failure_does_not_raise -x` | ❌ Wave 0 |
| NOTIF-03 | `[TRADE]` 마커가 매도 후 로그에 기록됨 | unit | `python -m pytest tests/test_order_executor.py::test_trade_log_emitted -x` | ❌ Wave 0 추가 |
| NOTIF-04 | 종료 시 engine.states 각 종목이 로그에 출력됨 | unit | `python -m pytest tests/test_scheduler.py::test_shutdown_logs_state -x` | ❌ Wave 0 추가 |
| D-01 | TELEGRAM_BOT_TOKEN만 설정 시 ValidationError | unit | `python -m pytest tests/test_settings.py::test_telegram_partial_config_raises -x` | ❌ Wave 0 추가 |
| D-01 | 둘 다 없으면 정상 초기화 | unit | `python -m pytest tests/test_settings.py::test_telegram_both_absent_ok -x` | ❌ Wave 0 추가 |

### Sampling Rate
- **Per task commit:** `python -m pytest tests/ -x -q`
- **Per wave merge:** `python -m pytest tests/ -v`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_telegram_notifier.py` — NOTIF-01, NOTIF-02 커버리지
- [ ] `mutrade/notifier/__init__.py` — 패키지 파일
- [ ] `mutrade/notifier/telegram.py` — TelegramNotifier 구현
- [ ] `tests/test_settings.py` — D-01 Telegram 검증 케이스 추가 (파일 이미 존재, 테스트 케이스 추가)
- [ ] `tests/test_order_executor.py` — NOTIF-03 [TRADE] 로그 케이스 추가 (파일 이미 존재)
- [ ] `tests/test_scheduler.py` — NOTIF-04 종료 로그 케이스 추가 (파일 이미 존재)
- [ ] `pyproject.toml` — `python-telegram-bot==21.11.1` 추가

---

## Project Constraints (from CLAUDE.md)

| Directive | Category | Impact on Phase 4 |
|-----------|----------|-------------------|
| KIS API만 사용 | API | 해당 없음 (알림은 Telegram) |
| 민감 정보는 환경변수/설정 파일로 분리 | 보안 | TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID를 .env에 저장. gitignore 이미 적용됨 |
| `python-telegram-bot 21.x` 사용 | 스택 | 21.11.1 핀. Application 불필요, Bot.send_message 직접 사용 |
| LINE Notify 사용 금지 (2025-03-31 종료) | 스택 | 해당 없음 |
| `loguru 0.7.x` 사용 | 스택 | 이미 설치됨. [TRADE] 마커로 재사용 |
| `pydantic-settings 2.x` 사용 | 스택 | model_validator 패턴 재사용 |
| `APScheduler 3.x BlockingScheduler` | 스택 | 단일 스레드 제약 → daemon Thread로 알림 비동기 처리 |
| FastAPI/Flask 금지 | 스택 | 해당 없음 |
| SQLite 금지 (v1) | 스택 | [TRADE] 로그를 loguru로 처리. DB 없음 |
| YAML 금지 | 스택 | 해당 없음 |

---

## Sources

### Primary (HIGH confidence)
- [VERIFIED: `pip index versions python-telegram-bot`] — 최신 버전 22.5, 21.11.1이 21.x 마지막
- [VERIFIED: 기존 `mutrade/executor/order_executor.py`] — `_submit_order()` 삽입 지점, `_confirm_fill()` 위치
- [VERIFIED: 기존 `mutrade/monitor/scheduler.py`] — `start_scheduler()` except 블록, `engine.states` 접근 스코프
- [VERIFIED: 기존 `mutrade/settings.py`] — `validate_virtual_credentials` model_validator 재사용 패턴
- [VERIFIED: 기존 `mutrade/engine/models.py`] — SellSignal 필드 목록 (code, name, current_price, peak_price, drop_pct, threshold)
- [VERIFIED: 기존 `pyproject.toml`] — `python-telegram-bot` 미설치 확인

### Secondary (MEDIUM confidence)
- [CITED: github.com/python-telegram-bot/discussions/4167] — daemon thread에서 Bot.send_message 사용 패턴
- [CITED: github.com/python-telegram-bot wiki Transition guide v20.0] — asyncio.run() 동기 컨텍스트 사용법

### Tertiary (LOW confidence)
- 해당 없음

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — PyPI 버전 직접 확인, 기존 의존성 확인
- Architecture: HIGH — 기존 코드 직접 읽어 삽입 지점 확인
- Pitfalls: MEDIUM — python-telegram-bot 동작은 문서로 확인, asyncio.run 사용 패턴은 Medium
- Test coverage: HIGH — 기존 테스트 파일 구조 직접 확인

**Research date:** 2026-04-08
**Valid until:** 2026-05-08 (python-telegram-bot 21.x API는 안정적이나, 22.x 변경 가능성)
