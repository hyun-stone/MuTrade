---
phase: 07-봇-제어
verified: 2026-04-18T07:00:00Z
status: human_needed
score: 10/10
overrides_applied: 0
human_verification:
  - test: "브라우저에서 서버 시작 후 헤더 시작/중지 버튼, 드라이런 배지 렌더링 확인"
    expected: "헤더에 파란색 시작 버튼, 비활성 빨간 중지 버튼, 노란 드라이런 배지가 보임"
    why_human: "HTML 렌더링 및 CSS 적용 결과는 브라우저에서만 확인 가능"
  - test: "시장 시간 외 시작 버튼 클릭 → 빨간 배너 표시, 4초 후 자동 숨김"
    expected: "상단에 '시장 시간이 아닙니다 (09:00~15:20 KST)' 빨간 배너 표시 후 4초 경과 시 자동 숨김"
    why_human: "setTimeout 자동 숨김 동작은 실 브라우저에서만 검증 가능"
  - test: "드라이런 배지 클릭 → 초록 배너 + 배지 텍스트·색상 전환 확인"
    expected: "'실매도 모드로 전환됨...' 초록 배너 표시, 배지가 '실매도'(빨간색)로 변경"
    why_human: "fetch → showBanner → updateDryRunBadge 연쇄 동작은 브라우저 통합 확인 필요"
  - test: "종목 데이터 있을 때 테이블 6열 확인 및 즉시 매도 버튼 표시"
    expected: "각 종목 행의 마지막 열에 '즉시 매도' 버튼이 표시되고 SELL_PENDING 종목은 disabled"
    why_human: "WebSocket 스냅샷 수신 후 renderTable의 실제 렌더링 결과는 브라우저에서만 확인 가능"
  - test: "WebSocket 연결 시 is_running에 따른 시작/중지 버튼 disabled 토글"
    expected: "is_running=true이면 시작 버튼 disabled, 중지 버튼 활성; false이면 반대"
    why_human: "실시간 WebSocket 스냅샷 기반 버튼 상태 동기화는 라이브 환경 확인 필요"
---

# Phase 7: 봇 제어 Verification Report

**Phase Goal:** 사용자가 브라우저에서 봇 세션을 시작·중지하고 매도 모드를 제어할 수 있다
**Verified:** 2026-04-18T07:00:00Z
**Status:** human_needed
**Re-verification:** No — 초기 검증

---

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | UI에서 시작 버튼을 누르면 모니터링 세션이 시작되고 대시보드에 반영된다 | ✓ VERIFIED | app.py `api_start`: 시장 시간 검증(KST) → `hub.clear_stop()` → `scheduler.modify_job("market_poll", ...)` 구현. index.html `startBot()` → `fetch('/api/start', {method:'POST'})` 연결. 테스트 `test_start_ok` PASSED |
| 2 | UI에서 중지 버튼을 누르면 세션이 중지되고 봇 상태가 비활성으로 갱신된다 | ✓ VERIFIED | app.py `api_stop`: `hub.request_stop()` 호출. index.html `stopBot()` → `fetch('/api/stop', ...)`. 테스트 `test_stop_ok` PASSED |
| 3 | UI에서 드라이런 ↔ 실매도 모드를 전환할 수 있으며 현재 모드가 대시보드에 표시된다 | ✓ VERIFIED | app.py `api_toggle_dry_run`: `_hub._lock` 안에서 `engine._dry_run`, `executor._dry_run` 원자 반전. hub.py `push_snapshot(dry_run=...)` → `_meta.dry_run` 포함. index.html `ws.onmessage`에서 `updateDryRunBadge(isDryRun)` 호출. 테스트 `test_toggle_dry_run` PASSED |
| 4 | UI에서 특정 종목의 수동 시장가 매도를 실행할 수 있으며 결과 피드백이 화면에 표시된다 | ✓ VERIFIED | app.py `api_sell`: 정규식 검증(`re.match`) → 스냅샷 조회 → `SellSignal(dry_run=False)` → `run_in_threadpool(executor.execute, sig)`. index.html `manualSell(code)` → confirm 다이얼로그 → fetch → `showBanner`. 테스트 `test_sell_ok`, `test_sell_404` PASSED |
| 5 | SELL_PENDING 중 중지 요청 시 "매도 진행 중" 경고가 표시된다 | ✓ VERIFIED | index.html `stopBot()`: `_lastSnapshot`에서 `sell_pending=true` 종목 존재 여부 확인 → `confirm('매도 진행 중인 종목이 있습니다. 그래도 중지하시겠습니까?')` 다이얼로그 |
| 6 | POST /api/start: 시장 시간이면 200, 아니면 400, 이미 실행 중이면 409 | ✓ VERIFIED | app.py 97~103행: KST 시간 검증. 테스트 `test_start_ok`(200), `test_start_market_closed`(400), `test_start_409`(409) 모두 PASSED |
| 7 | POST /api/stop: hub.request_stop()이 실행된다 | ✓ VERIFIED | app.py 113행: `_hub.request_stop()` 직접 호출. 테스트 `test_stop_ok`: `hub.is_stop_requested()` is True 검증 |
| 8 | POST /api/toggle-dry-run: engine._dry_run과 executor._dry_run이 반전된다 | ✓ VERIFIED | app.py 123~126행: `with _hub._lock:` 블록 내 원자적 반전. 테스트 `test_toggle_dry_run` PASSED |
| 9 | POST /api/sell/{code}: executor.execute()가 dry_run=False SellSignal로 실행된다 | ✓ VERIFIED | app.py 163행: `dry_run=False` 하드코딩. 165행: `run_in_threadpool(executor.execute, sig)`. 테스트 `test_sell_ok`에서 SellSignal.dry_run=False 검증 |
| 10 | WebSocket 스냅샷에 _meta.is_running과 _meta.dry_run 필드가 포함된다 | ✓ VERIFIED | hub.py 73~81행: `_meta` 키 생성 후 `{**meta, **serialized}` 병합. scheduler.py 116행: `dry_run=engine._dry_run` 전달. TestBotStateHubPhase7 4개 테스트 모두 PASSED |

**Score:** 10/10 truths verified

---

### Required Artifacts

| Artifact | 제공 기능 | Status | Details |
|----------|----------|--------|---------|
| `mutrade/admin/app.py` | 4개 POST 엔드포인트 | ✓ VERIFIED | `api_start`, `api_stop`, `api_toggle_dry_run`, `api_sell` 모두 존재. 192행. SellSignal import, run_in_threadpool import 확인 |
| `mutrade/admin/hub.py` | push_snapshot에 dry_run 인자 및 _meta 필드 | ✓ VERIFIED | 36행: `dry_run: bool = False` 인자. 73~81행: `_meta` 딕셔너리. 149행 전체 구현 |
| `mutrade/monitor/scheduler.py` | push_snapshot에 dry_run=engine._dry_run 전달 | ✓ VERIFIED | 116행: `hub.push_snapshot(engine.states, prices, executor.pending_codes(), dry_run=engine._dry_run)` |
| `mutrade/admin/static/index.html` | 시작/중지 버튼, 드라이런 배지, 배너, 즉시 매도 버튼, JS 핸들러 | ✓ VERIFIED | `btn-start`, `btn-stop`, `dry-run-badge`, `banner(role=alert)`, `startBot`, `stopBot`, `toggleDryRun`, `manualSell`, `showBanner`, `updateDryRunBadge` 모두 존재. 312행 |
| `tests/test_app_routes.py` | TestControlRoutes — 7개 테스트 | ✓ VERIFIED | 224행: `class TestControlRoutes`. 7 passed |
| `tests/test_hub.py` | TestBotStateHubPhase7 — 4개 테스트 | ✓ VERIFIED | 288행: `class TestBotStateHubPhase7`. 4 passed |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| `app.py` 엔드포인트 | `hub.py` BotStateHub | `request.app.state.hub` | ✓ WIRED | app.py 91, 112, 119, 141행에서 `request.app.state.hub` 참조 확인 |
| `app.py` api_sell | `engine/models.py` SellSignal | `from mutrade.engine.models import SellSignal` | ✓ WIRED | app.py 31행: import 확인. 157~165행: SellSignal 생성 및 사용 확인 |
| `scheduler.py` run_session | `hub.py` push_snapshot | `dry_run=engine._dry_run` | ✓ WIRED | scheduler.py 116행: `dry_run=engine._dry_run` 패턴 확인 |
| `index.html` JS | `app.py POST /api/start` | `fetch('/api/start', {method:'POST'})` | ✓ WIRED | index.html 200행: `fetch('/api/start', {method: 'POST'})` |
| `index.html` JS | `app.py POST /api/sell/{code}` | `fetch('/api/sell/'+code)` | ✓ WIRED | index.html 234행: `fetch('/api/sell/' + code, {method: 'POST'})` |
| `index.html` ws.onmessage | `hub.py _meta` 필드 | `data._meta` | ✓ WIRED | index.html 291행: `var meta = data._meta \|\| {}` |

---

### Data-Flow Trace (Level 4)

| Artifact | 데이터 변수 | 소스 | 실 데이터 생성 여부 | Status |
|----------|----------|-----|-----------------|--------|
| `index.html` 버튼 상태 | `isRunning`, `isDryRun` | WebSocket `_meta` ← `hub.push_snapshot(dry_run=engine._dry_run)` ← scheduler poll 루프 | 예 — scheduler.py가 `engine._dry_run` 실값 전달 | ✓ FLOWING |
| `index.html` renderTable | `symbols` (종목별 데이터) | WebSocket data ← `hub.push_snapshot(engine.states, prices)` | 예 — `_meta` 키는 `k !== '_meta'` 필터로 제외됨 | ✓ FLOWING |
| `app.py` api_sell | `sym` (snapshot 종목 데이터) | `_hub.get_snapshot().get(code)` | 예 — 스냅샷에 종목 없으면 404, 있으면 실 데이터로 SellSignal 생성 | ✓ FLOWING |

---

### Behavioral Spot-Checks

| 동작 | 명령 | 결과 | Status |
|------|-----|------|--------|
| TestBotStateHubPhase7 4개 테스트 | `python3.11 -m pytest tests/test_hub.py::TestBotStateHubPhase7 -q` | 4 passed in 0.xx s | ✓ PASS |
| TestControlRoutes 7개 테스트 | `python3.11 -m pytest tests/test_app_routes.py::TestControlRoutes -v` | 7 passed (test_start_ok, test_start_409, test_start_market_closed, test_stop_ok, test_toggle_dry_run, test_sell_ok, test_sell_404) | ✓ PASS |
| 전체 테스트 스위트 (test_client.py 제외) | `python3.11 -m pytest tests/ -x -q --ignore=tests/test_client.py` | 131 passed | ✓ PASS |

---

### Requirements Coverage

| Requirement | 출처 Plan | 설명 | Status | Evidence |
|-------------|---------|-----|--------|---------|
| CTRL-01 | 07-01, 07-02 | 사용자는 UI에서 모니터링 세션을 시작할 수 있다 | ✓ SATISFIED | `POST /api/start` + `startBot()` 구현. 시장 시간 검증, modify_job 트리거 |
| CTRL-02 | 07-01, 07-02 | 사용자는 UI에서 모니터링 세션을 중지할 수 있다 | ✓ SATISFIED | `POST /api/stop` + `stopBot()` 구현. SELL_PENDING confirm 다이얼로그 포함 |
| CTRL-03 | 07-01, 07-02 | 사용자는 UI에서 드라이런 ↔ 실매도 모드를 전환할 수 있다 | ✓ SATISFIED | `POST /api/toggle-dry-run` + `toggleDryRun()` + `updateDryRunBadge()` 구현 |
| CTRL-04 | 07-01, 07-02 | 사용자는 UI에서 특정 종목을 즉시 시장가 매도할 수 있다 | ✓ SATISFIED | `POST /api/sell/{code}` + `manualSell(code)` + renderTable 즉시 매도 버튼 구현 |

---

### Anti-Patterns Found

없음 — 스캔 결과 블로커/경고 패턴 없음.

- TODO/FIXME/PLACEHOLDER 없음
- 스텁 반환(`return null`, `return {}`) 없음
- 핸들러 미연결 없음 (모든 fetch 호출에 응답 처리 존재)
- 하드코딩된 빈 데이터 없음 (dry_run=False는 의도적 설계)

---

### Human Verification Required

자동화 검증은 모두 통과했습니다. 아래 항목은 브라우저 통합 환경에서만 확인 가능합니다.

#### 1. 헤더 UI 초기 렌더링

**테스트:** `python3.11 -m mutrade` 또는 `uvicorn mutrade.admin.app:create_app --factory`로 서버 시작 후 `http://localhost:8000` 접속
**예상:** 헤더에 파란색 "시작" 버튼, 비활성(회색) "중지" 버튼, 노란 배경의 "드라이런" 배지가 보임
**왜 사람이 필요한가:** CSS 적용 결과와 초기 disabled 상태는 브라우저에서만 확인 가능

#### 2. 시장 시간 외 시작 클릭 → 배너 표시

**테스트:** 시장 시간 외(예: 저녁)에 "시작" 버튼 클릭
**예상:** 상단에 빨간 배너 "시장 시간이 아닙니다 (09:00~15:20 KST)" 표시 → 4초 후 자동 숨김
**왜 사람이 필요한가:** `setTimeout` 기반 자동 숨김은 실 브라우저에서만 검증 가능

#### 3. 드라이런 배지 클릭 → 모드 전환 + 배너

**테스트:** "드라이런" 배지 클릭
**예상:** 초록 배너 "실매도 모드로 전환됨. 재시작 시 .env 설정으로 초기화됩니다" 표시, 배지가 "실매도" 텍스트에 빨간 배경으로 변경
**왜 사람이 필요한가:** fetch → JSON 응답 → showBanner → updateDryRunBadge 연쇄 동작의 시각적 결과

#### 4. 종목 테이블 6열 + 즉시 매도 버튼

**테스트:** 봇이 실행 중일 때 테이블에 종목이 표시되는 상태에서 마지막 열 확인
**예상:** 각 행 마지막 열에 빨간 "즉시 매도" 버튼이 표시되고, SELL_PENDING 상태의 종목은 버튼이 disabled(회색)
**왜 사람이 필요한가:** WebSocket 스냅샷 수신 후 renderTable의 실 렌더링 결과

#### 5. WebSocket is_running 기반 버튼 토글

**테스트:** 봇 실행 중(is_running=true) 상태에서 대시보드 확인
**예상:** "시작" 버튼이 disabled(회색), "중지" 버튼이 활성(빨간색)으로 전환됨
**왜 사람이 필요한가:** 실시간 WebSocket 스냅샷 기반 상태 동기화는 라이브 환경 필요

---

### Gaps Summary

갭 없음. 모든 백엔드 및 프론트엔드 구현이 완료되었으며 11개 신규 테스트와 전체 131개 테스트 스위트가 통과합니다. 브라우저 시각적 동작 확인만 남아 있습니다.

---

_Verified: 2026-04-18T07:00:00Z_
_Verifier: Claude (gsd-verifier)_
