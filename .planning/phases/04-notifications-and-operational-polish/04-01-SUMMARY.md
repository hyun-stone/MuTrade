---
phase: 04-notifications-and-operational-polish
plan: "01"
subsystem: notifications
tags: [telegram, notifier, settings, tdd, daemon-thread]
dependency_graph:
  requires:
    - mutrade/engine/models.py (SellSignal)
    - mutrade/settings.py (BaseSettings pattern)
  provides:
    - mutrade/notifier/telegram.py (TelegramNotifier)
    - mutrade/settings.py (telegram_bot_token, telegram_chat_id fields)
  affects:
    - 04-02 (TelegramNotifier 통합 — import 경로 확정)
tech_stack:
  added:
    - python-telegram-bot==21.11.1
  patterns:
    - daemon Thread + asyncio.run() in send function
    - pydantic model_validator for paired credential validation
key_files:
  created:
    - mutrade/notifier/__init__.py
    - mutrade/notifier/telegram.py
    - tests/test_telegram_notifier.py
  modified:
    - mutrade/settings.py
    - pyproject.toml
    - tests/test_settings.py
decisions:
  - "daemon Thread 방식으로 Telegram 알림 비동기 전송 — BlockingScheduler 단일 스레드 차단 방지"
  - "repr=False로 telegram_bot_token/chat_id 필드 로그/repr 노출 방지 (T-04-02)"
  - "notify() 내 예외는 logger.error()로만 기록 — 매도 흐름 차단 없음 (D-02)"
metrics:
  duration: "~15 minutes"
  completed: "2026-04-08"
  tasks_completed: 2
  files_changed: 6
---

# Phase 04 Plan 01: TelegramNotifier 모듈 및 Settings Telegram 필드 추가 Summary

**One-liner:** daemon Thread + asyncio.run() 패턴으로 비동기 Telegram 알림 전송기 구현, pydantic model_validator로 자격증명 쌍 검증.

## What Was Built

### Task 1: TelegramNotifier 모듈 (TDD)

`mutrade/notifier/telegram.py`에 `TelegramNotifier` 클래스를 구현했다.

- `notify(signal: SellSignal, qty: int)` — daemon Thread를 생성하여 `asyncio.run(bot.send_message(...))` 비동기 전송
- token/chat_id 중 하나라도 None이면 즉시 반환 (D-01)
- 전송 실패 시 `logger.error("Telegram 알림 전송 실패: {}", e)` — Bot 객체(토큰) 절대 로깅 금지 (T-04-01)
- D-04 메시지 형식: 종목명/코드, 수량, 현재가, 고점, 하락률, 임계값, KST 타임스탬프

### Task 2: Settings Telegram 선택적 필드 (TDD)

`mutrade/settings.py`에 Telegram 자격증명 필드와 validator를 추가했다.

- `telegram_bot_token: str | None` — `Field(None, alias="TELEGRAM_BOT_TOKEN", repr=False)`
- `telegram_chat_id: str | None` — `Field(None, alias="TELEGRAM_CHAT_ID", repr=False)`
- `validate_telegram_credentials()` — 부분 설정(한 필드만 있음) 시 `ValidationError` 발생 (D-01)
- `repr=False`로 설정 객체 repr/로그에서 민감 정보 제외 (T-04-02)

## Test Results

| Suite | Tests | Result |
|-------|-------|--------|
| tests/test_telegram_notifier.py | 5 | PASSED |
| tests/test_settings.py (TestTelegramSettings) | 4 | PASSED |
| tests/ (전체) | 73 | PASSED |

## Commits

| Task | Commit | Description |
|------|--------|-------------|
| Task 1 | `26e16e5` | feat(04-01): implement TelegramNotifier with daemon-thread send |
| Task 2 | `da9ab75` | feat(04-01): add Telegram optional fields to Settings with validator |

## Files Created/Modified

| File | Action | Description |
|------|--------|-------------|
| `mutrade/notifier/__init__.py` | Created | 패키지 초기화 (빈 파일) |
| `mutrade/notifier/telegram.py` | Created | TelegramNotifier 클래스 |
| `tests/test_telegram_notifier.py` | Created | TelegramNotifier 단위 테스트 5개 |
| `mutrade/settings.py` | Modified | telegram_bot_token/chat_id 필드 + validator |
| `pyproject.toml` | Modified | python-telegram-bot==21.11.1 의존성 추가 |
| `tests/test_settings.py` | Modified | TestTelegramSettings 클래스 4개 테스트 추가 |

## Next Plan (04-02) Integration Point

```python
from mutrade.notifier.telegram import TelegramNotifier
```

`OrderExecutor.__init__`에 `TelegramNotifier(token, chat_id)`를 주입하고, `_submit_order()` 내 `acc.sell()` 성공 직후 `notifier.notify(signal, qty)` 호출 (D-03).

## Deviations from Plan

None — 플랜대로 정확히 실행됨.

## Known Stubs

없음. 모든 기능이 실제 구현으로 완성됨 (Telegram API 연결은 실 토큰 없이 단위 테스트 mock으로 검증).

## Threat Flags

없음. 플랜의 threat_model이 모두 구현에 반영됨:
- T-04-01: `logger.error("Telegram 알림 전송 실패: {}", e)` — Bot 객체 로깅 없음
- T-04-02: `repr=False` on both telegram fields

## Self-Check: PASSED

- `mutrade/notifier/__init__.py` — FOUND
- `mutrade/notifier/telegram.py` — FOUND
- `tests/test_telegram_notifier.py` — FOUND
- commit `26e16e5` — FOUND
- commit `da9ab75` — FOUND
- 73 tests passed
