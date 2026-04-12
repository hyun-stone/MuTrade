# Research Summary — MuTrade v1.1 Admin UI

**Synthesized:** 2026-04-12
**Sources:** STACK.md, FEATURES.md, ARCHITECTURE.md, PITFALLS.md
**Consumer:** Requirements + Roadmap steps

---

## Executive Summary

MuTrade v1.1 adds a FastAPI-based admin dashboard to an already-running single-process trading bot. The infrastructure foundation is largely complete: Phase 5 delivered `BackgroundScheduler`, `BotStateHub` (thread-safe bridge), and `uvicorn` as the main-thread entry point. What remains is building the API routes, WebSocket broadcast layer, log parser, and config editor on top of this foundation — plus fixing one pre-existing data gap before any monitoring UI can work.

The recommended approach is to layer the dashboard in four discrete phases ordered by dependency: WebSocket state monitoring first (requires fixing the `current_price` snapshot gap), then bot control endpoints, then trade history, then config editing. Each phase is independently shippable and testable. No new architectural decisions are needed — the thread-safety primitives are already in place and correct.

The primary risk is not architectural complexity but a set of known, specific pitfalls: a queue overflow bug in BotStateHub that will emit asyncio exception traces immediately on WebSocket connection, a double-start race condition in the bot start endpoint, and blocking file I/O in async routes. All have concrete prevention patterns documented in the research.

---

## Stack Additions (v1.1 only)

| Library | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.135.3 | REST + WebSocket API server |
| `uvicorn[standard]` | 0.44.0 | ASGI server (Phase 5에서 이미 추가됨) |
| `jinja2` | 3.1.6 | HTML template rendering |
| `tomlkit` | 0.14.0 | config.toml read+write with comment preservation |
| `python-multipart` | 0.0.26 | FastAPI Form handling (HTML form submit 시만 필요) |

**Frontend:** Vanilla JS + browser-native WebSocket API. No build pipeline. Chart.js 4.5.1 via CDN if charting added later.

**Not added:** `sse-starlette`, `aiofiles`, `tomli-w` (tomlkit이 대체), Redis, SQLite, React/Vue/Svelte.

**Note:** PITFALLS.md는 `tomli-w`를 권장하지만 STACK.md의 `tomlkit`이 우선 — read+write+comment 보존을 하나로 처리.

---

## Feature Table Stakes

### Category 1 — Real-Time Position Monitoring
- Per-symbol row: code, current price, peak price, drop_pct, SELL_PENDING indicator
- Data freshness timestamp (last_updated), bot running status badge
- **Blocker:** `push_snapshot()`에 `current_price`가 없음 — scheduler.py 수정 필요
- **Blocker:** `OrderExecutor._pending`이 hub에 미노출 — 노출 방법 결정 필요

### Category 2 — Bot Control
- POST /api/bot/stop — hub.request_stop() 이미 준비됨
- POST /api/bot/start — scheduler.trigger_job() 패턴
- Dry-run mode 표시 (읽기 전용, 쓰기 토글은 v1.2로 연기)
- Safety: 멱등성 가드, SELL_PENDING 중 stop 시 UX 경고

### Category 3 — Trade History
- GET /api/history — logs/mutrade.log에서 [TRADE] 라인 파싱
- Fields: timestamp, code, name, qty, price, peak, drop%, dry-run/live
- 로그 포맷 확정됨 (order_executor.py 106-112행 기준)

### Category 4 — Config Editing
- GET /api/config — raw TOML 텍스트 반환 (textarea 표시용)
- PUT /api/config — 검증(tomlkit.parse + load_config) + atomic write
- "변경사항은 다음 세션에 적용" 안내 문구 필수
- .env 내용은 절대 응답에 포함 금지

### Defer to v1.2+
- WebSocket 실시간 push (프론트엔드 5초 폴링으로 v1.1 충분)
- Dry-run write 토글 (engine + executor 원자적 업데이트 필요)
- Config hot-reload 중간 세션 적용 (상태 관리 위험)
- 가격 스파크라인 히스토리 (스토리지 레이어 없음)

---

## Architecture

### 신규 생성 파일

| 파일 | 역할 |
|------|------|
| `mutrade/admin/ws.py` | ConnectionManager (WebSocket 연결 풀, broadcast) |
| `mutrade/admin/log_reader.py` | [TRADE] 역방향 로그 파서 |
| `mutrade/admin/config_editor.py` | ConfigUpdate Pydantic 모델 + tomlkit atomic write |
| `mutrade/admin/routers/__init__.py` | 패키지 |
| `mutrade/admin/routers/state.py` | GET /api/state, WebSocket /ws/state |
| `mutrade/admin/routers/bot.py` | GET/POST /api/bot/* |
| `mutrade/admin/routers/history.py` | GET /api/history |
| `mutrade/admin/routers/config.py` | GET/PUT /api/config |
| `mutrade/admin/static/index.html` | 단일 파일 대시보드 UI |

### 수정 파일

| 파일 | 변경 내용 |
|------|-----------|
| `mutrade/admin/app.py` | 라우터 include, StaticFiles 마운트, broadcast 백그라운드 태스크 |
| `mutrade/main.py` | engine + config를 app.state에 저장 (kwargs에 이미 있음) |
| `mutrade/admin/hub.py` | QueueFull 버그 fix (Pitfall 4) |
| `mutrade/monitor/scheduler.py` | push_snapshot()에 current_price 추가 |

### 수정 없는 파일
`trailing_stop.py`, `state_store.py`, `order_executor.py`, `settings.py`, `config/loader.py`

### 빌드 순서 (의존성 기반)

```
Phase A — WebSocket 모니터링
  사전 작업: hub.py QueueFull fix + scheduler.py current_price 추가
  admin/ws.py → admin/routers/state.py → admin/app.py 수정 → admin/static/index.html

Phase B — 봇 제어
  admin/routers/bot.py → admin/app.py lifespan에 scheduler 저장 → index.html 컨트롤 추가

Phase C — 거래 이력
  admin/log_reader.py → admin/routers/history.py → index.html 이력 섹션

Phase D — 설정 편집
  pyproject.toml +tomlkit → admin/config_editor.py → admin/routers/config.py → index.html 설정 폼
```

### 핵심 데이터 흐름

```
APScheduler 스레드 → hub.push_snapshot() → asyncio.Queue → broadcast task → WebSocket → 브라우저
FastAPI 엔드포인트 → hub.request_stop() (threading.Event) → run_session() break
FastAPI 엔드포인트 → scheduler.trigger_job() → 새 run_session() 즉시 실행
```

**규칙:** FastAPI 라우트는 항상 `hub.get_snapshot()` 경유 — `engine.states` 직접 접근 금지.

---

## Top Pitfalls (우선순위 순)

### Critical — 각 Phase 전에 반드시 처리

**1. [기존 버그] QueueFull이 asyncio 에러 로그 폭탄** (Pitfall 4)
- `_change_queue.put_nowait()`이 WebSocket 소비자가 없으면 `asyncio.QueueFull`을 throw. `call_soon_threadsafe`가 삼키지만 event loop가 3-5초마다 ERROR 로그를 찍음.
- **Fix:** `hub.py`에서 drain-then-put 패턴으로 교체. WebSocket 라우트 작성 전에 반드시 적용.

```python
def _enqueue_snapshot(self, snapshot: dict) -> None:
    while not self._change_queue.empty():
        try: self._change_queue.get_nowait()
        except asyncio.QueueEmpty: break
    try: self._change_queue.put_nowait(snapshot)
    except asyncio.QueueFull: pass
```

**2. `engine.states` 직접 접근** (Pitfall 1)
- GIL이 dict 반복 중 크기 변경을 막지 않음 → 비결정적 `RuntimeError`.
- **Rule:** 라우트는 반드시 `hub.get_snapshot()` 사용.

**3. Bot start 이중 실행 경쟁 조건** (Pitfall 2)
- `is_running()` 체크 후 `set_running(True)` 사이에 두 번째 요청 진입 가능.
- **Fix:** `threading.Lock`으로 check-then-act 원자화.

**4. async 라우트에서 동기 파일 I/O** (Pitfall 7)
- `open()` in `async def`는 event loop를 블록 → WebSocket heartbeat 누락.
- **Fix:** `asyncio.to_thread(_read_trade_logs, path)` 사용.

**5. config.toml 비원자적 쓰기** (Pitfall 6)
- 프로세스 크래시 시 0바이트 파일 → 다음 시작 시 `TOMLDecodeError`.
- **Fix:** `tempfile.NamedTemporaryFile` + `os.replace()` (StateStore.save()와 동일 패턴).

**6. graceful shutdown 행** (Pitfall 10)
- `scheduler.shutdown(wait=False)`는 실행 중인 `run_session()`을 중단하지 않음.
- **Fix:** lifespan shutdown에서 `hub.request_stop()` 후 최대 10초 대기.

**7. Stop-during-sell 경쟁 조건** (Pitfall 3)
- `hub.is_running() == False`지만 executor가 여전히 주문 대기 중일 수 있음.
- **v1.1 최소 대응:** 응답에 `"status": "stopping"` 반환 + UI 경고 문구.

### Moderate (설계 결정)
- WebSocket 연결 누수 (Pitfall 8): `asyncio.wait_for(timeout=30)` + `WebSocketDisconnect` catch
- 단일 큐 / 멀티탭 (Pitfall 9): 단일 사용자 허용, 제한 문서화
- Config hot-reload (Pitfall 5): mid-session 절대 시도 금지, UI에 "다음 세션" 명시

---

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack versions | HIGH | PyPI 직접 확인됨 |
| Feature scope | HIGH | 소스 코드 직접 분석 기반 |
| Architecture | HIGH | Phase 5 완료 상태 코드베이스 분석 |
| Pitfalls | HIGH | CPython/asyncio 동작 기반, 추측 아님 |
| [TRADE] log format | HIGH | order_executor.py 106-112행 확인됨 |

**구현 전 확인 필요:**
- `scheduler.trigger_job()` vs `.get_job("market_poll").modify()` — APScheduler 3.11.2 설치 버전에서 API 확인
- `OrderExecutor._pending` 필드명 및 접근 가능성 확인 후 SELL_PENDING 노출 전략 결정
- loguru 로테이션 파일 명명 패턴 (`.1` 접미사 가정) 확인 후 다중 파일 파서 작성
