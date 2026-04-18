---
phase: 7
slug: 봇-제어
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-18
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `python3.11 -m pytest tests/test_app_routes.py tests/test_hub.py -x -q` |
| **Full suite command** | `python3.11 -m pytest tests/ -q` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3.11 -m pytest tests/test_app_routes.py tests/test_hub.py -x -q`
- **After every plan wave:** Run `python3.11 -m pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 7-W0-01 | W0 | 0 | CTRL-01 | — | N/A | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_start_ok -x` | ❌ W0 | ⬜ pending |
| 7-W0-02 | W0 | 0 | CTRL-01 | — | N/A | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_start_409 -x` | ❌ W0 | ⬜ pending |
| 7-W0-03 | W0 | 0 | CTRL-01 | — | N/A | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_start_market_closed -x` | ❌ W0 | ⬜ pending |
| 7-W0-04 | W0 | 0 | CTRL-02 | — | N/A | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_stop_ok -x` | ❌ W0 | ⬜ pending |
| 7-W0-05 | W0 | 0 | CTRL-03 | — | N/A | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_toggle_dry_run -x` | ❌ W0 | ⬜ pending |
| 7-W0-06 | W0 | 0 | CTRL-04 | T-7-01 | 종목코드 형식 검증 후 실행 | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_sell_ok -x` | ❌ W0 | ⬜ pending |
| 7-W0-07 | W0 | 0 | CTRL-04 | T-7-01 | 존재하지 않는 종목 404 | unit | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes::test_sell_404 -x` | ❌ W0 | ⬜ pending |
| 7-W0-08 | W0 | 0 | D-08 | — | N/A | unit | `python3.11 -m pytest tests/test_hub.py::TestBotStateHubPhase7 -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_app_routes.py::TestControlRoutes` — CTRL-01~04 커버 (기존 파일에 클래스 추가)
- [ ] `tests/test_hub.py::TestBotStateHubPhase7` — dry_run 필드 포함 스냅샷 테스트 (기존 파일에 클래스 추가)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SELL_PENDING 중 중지 요청 시 confirm 다이얼로그 | CTRL-02 | 브라우저 window.confirm() — 자동화 불가 | 1) 시장 시간 중 봇 시작 2) 종목이 SELL_PENDING 상태일 때 중지 클릭 3) confirm 다이얼로그 확인 |
| 드라이런 토글 시 재시작 초기화 안내 | CTRL-03 | 텍스트 배지 표시 확인 | 1) 드라이런 토글 2) 대시보드 헤더 배지 확인 3) 재시작 후 .env 원래 값으로 복원 확인 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
