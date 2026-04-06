---
phase: 1
slug: foundation-and-kis-api-connectivity
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-06
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (미설치 — Wave 0에서 설치) |
| **Config file** | none — Wave 0에서 `pyproject.toml [tool.pytest.ini_options]` 생성 |
| **Quick run command** | `pytest tests/ -x -q --ignore=tests/integration` |
| **Full suite command** | `pytest tests/ -v` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `pytest tests/ -x -q --ignore=tests/integration`
- **After every plan wave:** Run `pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 1-01-01 | 01 | 0 | CONF-02 | unit | `pytest tests/test_settings.py -x` | ❌ W0 | ⬜ pending |
| 1-01-02 | 01 | 0 | CONF-03 | unit | `pytest tests/test_config.py -x` | ❌ W0 | ⬜ pending |
| 1-01-03 | 01 | 0 | CONF-04 | unit | `pytest tests/test_holiday.py -x` | ❌ W0 | ⬜ pending |
| 1-01-04 | 01 | 0 | FEED-01 | unit | `pytest tests/test_scheduler.py -x` | ❌ W0 | ⬜ pending |
| 1-01-05 | 01 | 0 | FEED-02,03,04 | unit | `pytest tests/test_price_feed.py -x` | ❌ W0 | ⬜ pending |
| 1-02-01 | 02 | 1 | CONF-01 | manual | `python main.py` — 토큰 만료 타임스탬프 출력 확인 | ❌ W1 | ⬜ pending |
| 1-02-02 | 02 | 1 | FEED-02,03 | unit | `pytest tests/test_price_feed.py -x` | ❌ W0 | ⬜ pending |
| 1-02-03 | 02 | 1 | FEED-04 | unit | `pytest tests/test_price_feed.py::test_api_error -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/__init__.py` — 패키지 마커
- [ ] `tests/test_settings.py` — covers CONF-02 (필수 필드 누락 시 ValidationError)
- [ ] `tests/test_config.py` — covers CONF-03 (TOML 파싱 및 SymbolConfig 생성)
- [ ] `tests/test_holiday.py` — covers CONF-04 (KRX 공휴일 is_session() 반환값)
- [ ] `tests/test_scheduler.py` — covers FEED-01 (09:00~15:20 KST 범위 체크)
- [ ] `tests/test_price_feed.py` — covers FEED-02, FEED-03, FEED-04
- [ ] `pyproject.toml` — `[tool.pytest.ini_options]` + 의존성 선언
- [ ] pytest 설치: `pip install pytest pytest-mock`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KIS OAuth 2.0 토큰 발급 및 타임스탬프 출력 | CONF-01 | 실제 KIS 자격증명 필요 (CI 환경 비노출) | `python main.py` 실행 후 콘솔에 토큰 만료 시각 출력 확인 |
| 모의투자 계정 virtual=True 전환 | CONF-01 | 별도 모의투자 AppKey/Secret 필요 | `KIS_MOCK=true python main.py` 후 모의투자 엔드포인트 호출 로그 확인 |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
