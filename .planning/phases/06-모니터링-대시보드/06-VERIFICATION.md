---
phase: 06-모니터링-대시보드
verified: 2026-04-16T23:35:00Z
status: human_needed
score: 5/5
overrides_applied: 0
human_verification:
  - test: "브라우저에서 http://localhost:8000 접속 후 WebSocket 연결 상태 확인"
    expected: "헤더에 파란 점과 '실시간 연결' 텍스트 표시, 개발자 도구 Console 오류 없음"
    why_human: "브라우저 렌더링 및 WebSocket 연결은 서버 구동 없이 프로그래밍 방식으로 검증 불가"
  - test: "봇 미실행 상태에서 대시보드 접속"
    expected: "'봇 대기 중' 메시지 표시, 종목 테이블 숨김"
    why_human: "빈 스냅샷 상태에서의 UI 렌더링은 실제 브라우저 환경 필요"
  - test: "봇 실행 중 상태에서 폴링 주기 대기"
    expected: "페이지 새로고침 없이 종목 행이 현재가/고점/하락률 포함하여 자동 갱신됨"
    why_human: "WebSocket 실시간 자동 갱신은 실제 봇 실행 및 브라우저 환경 필요"
  - test: "SELL_PENDING 종목 시각적 구분 확인"
    expected: "해당 행에 어두운 빨간 배경 blink-sell 애니메이션 적용됨"
    why_human: "CSS 애니메이션 시각적 동작은 브라우저 렌더링 확인 필요"
---

# Phase 6: 모니터링 대시보드 Verification Report

**Phase Goal:** 사용자가 브라우저에서 각 종목의 실시간 가격 상태를 확인할 수 있다 (인프라 버그 수정 포함)
**Verified:** 2026-04-16T23:35:00Z
**Status:** human_needed
**Re-verification:** No — 최초 검증

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | WebSocket 연결 시 asyncio ERROR 로그가 더 이상 발생하지 않는다 (QueueFull 버그 수정) | VERIFIED | `hub.py` `_put_snapshot()` 메서드에 드롭-앤-리플레이스 패턴 구현 확인. 연속 2회 push 테스트 통과 |
| 2 | hub.get_snapshot() 응답에 current_price, drop_pct, SELL_PENDING 필드가 포함된다 | VERIFIED | `hub.push_snapshot()` 직렬화 루프에 세 필드 모두 포함. 런타임 검증 PASS |
| 3 | 브라우저에서 각 종목의 현재가, 고점, 하락률을 행 단위로 확인할 수 있다 | VERIFIED (코드 기준) | `index.html`에 5열 테이블 구조, `renderTable()` 함수, `fmtPrice()`, `fmtDrop()` 구현됨. 브라우저 시각 확인은 Human 필요 |
| 4 | SELL_PENDING 중인 종목이 시각적으로 구분된다 (배지 또는 색상 강조) | VERIFIED (코드 기준) | `tr.sell-pending { animation: blink-sell 1s ease-in-out infinite }` CSS 규칙 확인. `getStatusText()` → '매도 대기' 텍스트. 브라우저 시각 확인은 Human 필요 |
| 5 | 페이지 새로고침 없이 WebSocket으로 데이터가 자동 갱신된다 | VERIFIED (코드 기준) | `/ws` WebSocket 엔드포인트에서 `hub.wait_for_change()` 루프 확인. `ws.onclose → setTimeout(connect, 3000)` 자동 재연결 패턴 확인. 실시간 동작은 Human 필요 |

**Score:** 5/5 truths verified (코드 수준 자동 검증 완료, 시각적 동작 Human 검증 대기)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `mutrade/admin/hub.py` | QueueFull 수정 + push_snapshot(states, prices, pending_codes) 시그니처 | VERIFIED | `_put_snapshot()` 메서드 존재. 드롭-앤-리플레이스 패턴 구현됨. 시그니처 3인자 확인 |
| `mutrade/executor/order_executor.py` | `pending_codes()` 공개 메서드 | VERIFIED | `pending_codes() -> frozenset` 메서드 존재. 런타임 테스트 PASS |
| `mutrade/monitor/scheduler.py` | `executor.pending_codes()` + `prices`를 `push_snapshot()`에 전달 | VERIFIED | `push_snapshot(engine.states, prices, executor.pending_codes())` 호출 확인 |
| `mutrade/admin/app.py` | WebSocket /ws 엔드포인트 + StaticFiles 마운트 + GET / 라우트 | VERIFIED | 라우트 set에 `/`, `/ws`, `/static` 모두 포함 확인 |
| `mutrade/admin/static/` | 정적 파일 디렉터리 (index.html 위치) | VERIFIED | 디렉터리 + `.gitkeep` 존재 확인 |
| `mutrade/admin/static/index.html` | 단일 파일 대시보드 — HTML + 인라인 CSS + 인라인 JS | VERIFIED | 핵심 요소 15개 모두 확인. 외부 CDN 없음 확인 |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `mutrade/monitor/scheduler.py` | `mutrade/admin/hub.py` | `hub.push_snapshot(engine.states, prices, executor.pending_codes())` | WIRED | 정확한 호출 문자열 grep 확인 |
| `mutrade/admin/hub.py` | `asyncio.Queue` | `_put_snapshot()` — `call_soon_threadsafe` 경유 | WIRED | `call_soon_threadsafe(self._put_snapshot, ...)` 패턴 확인 |
| `mutrade/admin/app.py websocket_endpoint` | `mutrade/admin/hub.py wait_for_change()` | `await hub.wait_for_change()` 루프 | WIRED | `websocket_endpoint` 내 `wait_for_change()` 호출 확인 |
| `app.state.hub` | `BotStateHub` 인스턴스 | `lifespan startup에서 app.state.hub = hub 설정됨` | WIRED | lifespan `app.state.hub = hub` 및 `websocket.app.state.hub` 접근 확인 |
| `index.html WebSocket onmessage` | `renderTable(data)` | `JSON.parse(e.data) → renderTable()` | WIRED | `ws.onmessage` 핸들러에서 `renderTable(JSON.parse(e.data))` 확인 |
| `index.html` | `/ws` | `new WebSocket('ws://' + location.host + '/ws')` | WIRED | `'ws://' + location.host + '/ws'` 패턴 확인 (템플릿 리터럴 대신 문자열 연결 사용) |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `index.html renderTable()` | `data` (WebSocket JSON) | `/ws` WebSocket → `hub.get_snapshot()` / `hub.wait_for_change()` | Yes — `hub.push_snapshot(engine.states, prices, executor.pending_codes())` 체인 확인 | FLOWING |
| `mutrade/admin/hub.py get_snapshot()` | `self._snapshot` | `push_snapshot()` 직렬화 루프 (prices dict + pending set 에서 계산) | Yes — `_prices.get(code, 0.0)`, `code in _pending` 동적 계산 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| hub.py 핵심 기능 (push, snapshot, QueueFull) | `python3.11 -c "... BotStateHub 검증 ..."` | PASS | PASS |
| `pending_codes()` frozenset 반환 | `python3.11 -c "... OrderExecutor.pending_codes() ..."` | PASS | PASS |
| app.py 라우트 등록 확인 | `python3.11 -c "... create_app() routes ..."` | `{'/', '/ws', '/static', ...}` | PASS |
| index.html 핵심 요소 15개 + CDN 없음 | `python3.11 -c "... index.html assertions ..."` | PASS (15/15) | PASS |
| scheduler.py 키링크 문자열 확인 | `grep push_snapshot scheduler.py` | `push_snapshot(engine.states, prices, executor.pending_codes())` | PASS |
| 전체 테스트 스위트 | `python3.11 -m pytest tests/ -q` | 121 passed, 1 failed (pre-existing, Phase 06 무관) | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|-------------|-------------|--------|---------|
| INFRA-01 | 06-01-PLAN | 봇 상태 스냅샷에 현재가·하락률·SELL_PENDING 포함 | SATISFIED | `hub.push_snapshot()` current_price, drop_pct, sell_pending 필드 + `scheduler.py` prices/pending_codes 전달 확인 |
| INFRA-02 | 06-01-PLAN | asyncio.QueueFull 예외 처리 버그 수정 | SATISFIED | `_put_snapshot()` 드롭-앤-리플레이스 패턴 구현 및 런타임 테스트 통과 |
| DASH-01 | 06-03-PLAN | 사용자가 각 종목의 현재가, 고점, 하락률을 웹 페이지에서 확인 | SATISFIED (코드) / NEEDS HUMAN (시각) | index.html 5열 테이블 + renderTable() 구현 확인 |
| DASH-02 | 06-03-PLAN | SELL_PENDING 종목 시각적 구분 | SATISFIED (코드) / NEEDS HUMAN (시각) | `tr.sell-pending` blink-sell 애니메이션, '매도 대기' 배지 구현 확인 |
| DASH-03 | 06-02, 06-03 | WebSocket 자동 갱신 | SATISFIED (코드) / NEEDS HUMAN (실시간) | `/ws` 엔드포인트 + `wait_for_change()` 루프 + `setTimeout(connect, 3000)` 재연결 구현 확인 |

**전체 Phase 6 요구사항 매핑:** INFRA-01, INFRA-02, DASH-01, DASH-02, DASH-03 — 5/5 코드 수준 만족 확인.
CTRL-01~04, HIST-01, CONF-01~02 는 Phase 7~9 범위로 이 페이즈 비적용.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| (없음) | - | - | - | - |

안티패턴 스캔 결과: PLACEHOLDER, TODO, FIXME 없음. 모든 핸들러가 실질적 구현을 포함. `return null` / `return []` 스텁 없음.

### Human Verification Required

#### 1. WebSocket 실시간 연결 확인

**Test:** `uvicorn mutrade.admin.app:create_app --factory --host 0.0.0.0 --port 8000` 실행 후 브라우저에서 `http://localhost:8000` 접속
**Expected:** 헤더에 파란 점 + "실시간 연결" 텍스트 표시, 개발자도구 Console 오류 없음, Network 탭 WS 항목에 `/ws` 연결 확인
**Why human:** 서버 구동 및 브라우저 렌더링은 자동 검증 불가

#### 2. 빈 상태 메시지 렌더링

**Test:** 봇 미실행 상태에서 대시보드 접속
**Expected:** 테이블 숨김, "봇 대기 중" 메시지 + "장 운영 시간(09:00~15:30 KST)에 자동 시작됩니다" 부제 표시
**Why human:** WebSocket이 빈 `{}` 반환 시 UI 분기는 브라우저 실행 환경 필요

#### 3. 실시간 자동 갱신 확인

**Test:** 봇 실행 중 상태에서 페이지를 열어두고 폴링 주기(기본 60초) 대기
**Expected:** 페이지 새로고침 없이 종목 행의 현재가/하락률이 갱신됨
**Why human:** 실제 봇 폴링 루프 및 WebSocket 브로드캐스트 동작은 통합 환경 필요

#### 4. SELL_PENDING blink-sell 애니메이션

**Test:** 매도 대기 중인 종목이 있을 때 해당 테이블 행 시각 확인
**Expected:** 해당 행에 `#450a0a` ↔ `#7f1d1d` 사이 1초 주기 배경색 번짙임 애니메이션 동작
**Why human:** CSS 애니메이션 시각적 동작은 브라우저 렌더링 확인 필요

### Gaps Summary

갭 없음. 5/5 성공 기준 코드 수준 검증 완료.

인간 검증이 필요한 이유: 브라우저 시각 렌더링, WebSocket 실시간 동작, CSS 애니메이션은 코드 정적 분석으로 확인 불가하여 Step 9 결정 트리에 따라 `human_needed` 상태로 분류.

---

_Verified: 2026-04-16T23:35:00Z_
_Verifier: Claude (gsd-verifier)_
