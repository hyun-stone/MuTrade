---
phase: 3
slug: order-execution
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-07
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml (기존) |
| **Quick run command** | `pytest tests/ -x -q` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 3-01-01 | 01 | 1 | EXEC-01 | unit | `pytest tests/test_order_executor.py -x -q` | ❌ W0 | ⬜ pending |
| 3-01-02 | 01 | 1 | EXEC-02 | unit | `pytest tests/test_order_executor.py::test_orderable_qty -x -q` | ❌ W0 | ⬜ pending |
| 3-01-03 | 01 | 2 | EXEC-03 | unit | `pytest tests/test_order_executor.py::test_sell_pending_flag -x -q` | ❌ W0 | ⬜ pending |
| 3-01-04 | 01 | 2 | EXEC-04 | unit | `pytest tests/test_order_executor.py::test_fill_confirmation -x -q` | ❌ W0 | ⬜ pending |
| 3-02-01 | 02 | 3 | EXEC-01,EXEC-02,EXEC-03,EXEC-04 | integration | `pytest tests/test_order_executor_integration.py -x -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_order_executor.py` — stubs for EXEC-01, EXEC-02, EXEC-03, EXEC-04
- [ ] `tests/test_order_executor_integration.py` — 모의투자 통합 테스트 stub

*기존 `tests/conftest.py` 활용 가능 (Phase 2에서 생성)*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KIS 모의투자 실제 주문 제출 | EXEC-01 | 실제 API 호출 필요 (자격증명 필요) | DRY_RUN=False, KIS_MOCK=True로 설정 후 봇 실행, 로그에서 주문 ID 확인 |
| 체결 확인 폴링 모의투자 지원 | EXEC-04 | daily_orders() 모의투자 지원 런타임 검증 필요 | 모의투자 환경에서 체결 후 로그 확인 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
