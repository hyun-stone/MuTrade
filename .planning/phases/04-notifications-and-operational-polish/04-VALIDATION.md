---
phase: 4
slug: notifications-and-operational-polish
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-08
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python -m pytest tests/ -x -q` |
| **Full suite command** | `python -m pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python -m pytest tests/ -x -q`
- **After every plan wave:** Run `python -m pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 0 | NOTIF-01 | — | N/A | unit | `python -m pytest tests/test_telegram_notifier.py -x` | ❌ W0 | ⬜ pending |
| 04-01-02 | 01 | 0 | NOTIF-02 | — | 알림 실패가 매도 흐름 차단 안 함 | unit | `python -m pytest tests/test_telegram_notifier.py::test_notify_is_nonblocking -x` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | NOTIF-01, NOTIF-02 | — | notify() daemon thread, 즉시 반환 | unit | `python -m pytest tests/test_telegram_notifier.py -x` | ❌ W0 | ⬜ pending |
| 04-01-04 | 01 | 1 | NOTIF-02 | — | 알림 실패 시 예외 전파 없음 | unit | `python -m pytest tests/test_telegram_notifier.py::test_notify_failure_does_not_raise -x` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 0 | NOTIF-03 | — | N/A | unit | `python -m pytest tests/test_order_executor.py::test_trade_log_emitted -x` | ❌ W0 추가 | ⬜ pending |
| 04-02-02 | 02 | 0 | NOTIF-04 | — | N/A | unit | `python -m pytest tests/test_scheduler.py::test_shutdown_logs_state -x` | ❌ W0 추가 | ⬜ pending |
| 04-02-03 | 02 | 1 | D-01 | — | 토큰/ID 부분 설정 시 ValidationError | unit | `python -m pytest tests/test_settings.py::test_telegram_partial_config_raises -x` | ❌ W0 추가 | ⬜ pending |
| 04-02-04 | 02 | 1 | D-01 | — | 둘 다 없으면 정상 초기화 | unit | `python -m pytest tests/test_settings.py::test_telegram_both_absent_ok -x` | ❌ W0 추가 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_telegram_notifier.py` — NOTIF-01, NOTIF-02 stub (TelegramNotifier 단위 테스트)
- [ ] `mutrade/notifier/__init__.py` — 패키지 파일 (빈 파일)
- [ ] `mutrade/notifier/telegram.py` — TelegramNotifier 클래스 구현
- [ ] `tests/test_order_executor.py` — `test_trade_log_emitted` 케이스 추가 (NOTIF-03)
- [ ] `tests/test_scheduler.py` — `test_shutdown_logs_state` 케이스 추가 (NOTIF-04)
- [ ] `tests/test_settings.py` — Telegram 부분 설정 검증 케이스 추가 (D-01)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| 실제 Telegram 메시지 수신 확인 | NOTIF-01 | 실제 Bot API 토큰 필요 | `.env`에 토큰/채팅ID 설정 후 드라이런 OFF로 봇 실행, 매도 신호 발생 후 Telegram 메시지 확인 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
