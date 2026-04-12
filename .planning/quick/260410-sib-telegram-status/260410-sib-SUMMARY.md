---
phase: quick
plan: 260410-sib
subsystem: notifier
tags: [telegram, listener, status-command, polling, daemon-thread]
one_liner: "Telegram /status 명령 수신 리스너 구현 — chat_id 검증, daemon thread polling, _build_status_message 순수 함수"
dependency_graph:
  requires: [mutrade/engine/trailing_stop.py, mutrade/engine/models.py, mutrade/config/loader.py]
  provides: [mutrade/notifier/telegram_listener.py]
  affects: [mutrade/main.py]
tech_stack:
  added: [python-telegram-bot ApplicationBuilder/CommandHandler]
  patterns: [daemon thread polling, pure function for formatting, no-op guard pattern]
key_files:
  created:
    - mutrade/notifier/telegram_listener.py
    - tests/test_telegram_listener.py
  modified:
    - mutrade/main.py
decisions:
  - "_build_status_message를 모듈 레벨 순수 함수로 분리하여 클래스 인스턴스 없이 테스트 가능"
  - "하락률 표시 포맷을 음수 부호(-) 포함으로 통일 (계획 지정: -Z.Z%)"
metrics:
  duration: "~15min"
  completed_date: "2026-04-10"
  tasks_completed: 2
  files_created: 2
  files_modified: 1
  tests_added: 6
  tests_total: 86
---

# Quick 260410-sib: Telegram /status 명령 수신 기능 Summary

## 완료된 작업

### Task 1: TelegramListener 구현 및 테스트 (TDD)

**커밋:** `9c20d49`

**구현 내용:**

`mutrade/notifier/telegram_listener.py` 신규 생성:

- `_build_status_message(states, prices, symbols, dry_run, kis_mock)` — 모듈 레벨 순수 함수
  - 종목별 현재가(쉼표 포맷), 고점, 하락률(-Z.Z% 형식) 포맷
  - 빈 states일 때 "모니터링 종목 없음" 반환
  - DRY_RUN / 모의투자 상태 하단 표시
  - KST 타임스탬프 포함

- `TelegramListener` 클래스
  - `start()`: token/chat_id 중 하나라도 None이면 no-op (스레드 미생성)
  - `_run_polling()`: daemon thread에서 asyncio 이벤트 루프 + ApplicationBuilder 실행
  - `_handle_status()`: T-quick-01 — chat_id 검증, 미허가 요청 무시
  - `stop()`: best-effort stop (daemon thread이므로 프로세스 종료 시 자동 정리)

**테스트 (6개):**

| 테스트 | 설명 |
|--------|------|
| test_start_noop_without_token | token=None → _thread is None |
| test_start_noop_without_chat_id | chat_id=None → _thread is None |
| test_format_contains_code_name_price_peak_drop | 포맷 검증 (코드, 종목명, 현재가, 고점, 하락률) |
| test_build_status_message_empty_states | 빈 states → "모니터링 종목 없음" |
| test_drop_pct_calculation | peak=100000, current=93000 → -7.0% |
| test_dry_run_kis_mock_status_display | ON/OFF 상태 표시 |

### Task 2: main.py에 TelegramListener 통합

**커밋:** `a04b56d`

- `TelegramListener` import 추가
- `start_scheduler()` 직전에 listener 초기화 및 `start()` 호출
- token 설정 시 "Telegram /status 리스너 활성화" 로그 출력
- 기존 `TelegramNotifier` 변경 없음

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] 하락률 음수 부호 누락**
- **Found during:** Task 1 GREEN 단계 테스트 실행
- **Issue:** `_build_status_message`에서 하락률을 `{drop_pct:.1f}%`로 포맷해 양수값 출력. 계획 스펙 `-Z.Z%`와 불일치
- **Fix:** `f"하락률: -{drop_pct:.1f}%"` — 항상 음수 부호 명시 (하락은 정의상 양수값이므로 고정 부호)
- **Files modified:** mutrade/notifier/telegram_listener.py
- **Commit:** 9c20d49 (구현과 함께 즉시 수정)

## Threat Model Coverage

| Threat ID | Status | Implementation |
|-----------|--------|----------------|
| T-quick-01 Spoofing | mitigated | `_handle_status`에서 `str(update.effective_chat.id) != str(self._chat_id)` 검증 후 무시 |
| T-quick-02 Information Disclosure | accepted | 토큰/API 키 메시지 미포함. T-04-01: token 로그 출력 금지 주석 명시 |
| T-quick-03 DoS | accepted | 개인용 봇, python-telegram-bot 기본 rate limit 처리 |

## Verification

- `python -m pytest tests/ -v` → **86 passed** (신규 6 + 기존 80)
- `python -c "from mutrade.notifier.telegram_listener import TelegramListener"` → import OK

## Self-Check: PASSED

- mutrade/notifier/telegram_listener.py 존재 확인: FOUND
- tests/test_telegram_listener.py 존재 확인: FOUND
- 커밋 9c20d49 존재: FOUND
- 커밋 a04b56d 존재: FOUND
- 전체 테스트 86 passed: CONFIRMED
