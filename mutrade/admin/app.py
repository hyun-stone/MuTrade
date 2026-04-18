"""
mutrade/admin/app.py

FastAPI 앱 팩토리.

lifespan:
- startup: asyncio 이벤트 루프를 BotStateHub에 연결 (attach_loop)
- shutdown: hub 상태 정리

엔드포인트:
- GET /health — 서버 생존 확인
- GET / — index.html (대시보드)
- GET /ws — WebSocket (실시간 스냅샷 브로드캐스트)
- /static — StaticFiles 마운트
"""
import asyncio
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from mutrade.admin.hub import BotStateHub
from mutrade.engine.models import SellSignal

# 정적 파일 디렉터리 — Path(__file__).parent / "static" 절대 경로 (실행 디렉터리 독립)
# 테스트에서 patch.object(app_module, "STATIC_DIR", ...) 로 교체 가능
STATIC_DIR = Path(__file__).parent / "static"

KST = ZoneInfo("Asia/Seoul")


def create_app(hub: BotStateHub, **kwargs: Any) -> FastAPI:
    """
    FastAPI 앱 인스턴스를 생성한다.

    Args:
        hub: BotStateHub 인스턴스 (봇 상태 브릿지)
        **kwargs: 추후 engine, scheduler 등 의존성 주입용 (Phase 6~7에서 사용)

    Returns:
        FastAPI 앱 인스턴스
    """
    # static/ 디렉터리가 없으면 생성 (StaticFiles 마운트 RuntimeError 방지)
    STATIC_DIR.mkdir(parents=True, exist_ok=True)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # startup: 현재 asyncio 이벤트 루프를 hub에 연결 (get_running_loop — Python 3.10+ 권장)
        loop = asyncio.get_running_loop()
        hub.attach_loop(loop)
        app.state.hub = hub
        app.state.scheduler = kwargs.get("scheduler")
        app.state.engine = kwargs.get("engine")
        app.state.executor = kwargs.get("executor")
        app.state.config = kwargs.get("config")
        logger.info("Admin server started. BotStateHub loop attached.")
        yield
        # shutdown: 봇 폴링 중단 요청 + BackgroundScheduler 종료
        hub.request_stop()
        scheduler = kwargs.get("scheduler")
        if scheduler is not None:
            scheduler.shutdown(wait=False)
        logger.info("Admin server shutting down.")

    app = FastAPI(
        title="MuTrade Admin",
        description="트레일링 스탑 봇 관리 대시보드",
        version="1.1.0",
        lifespan=lifespan,
    )

    @app.get("/health")
    async def health() -> dict:
        """서버 생존 확인 및 봇 실행 상태 반환."""
        return {
            "status": "ok",
            "bot_running": hub.is_running(),
            "stop_requested": hub.is_stop_requested(),
        }

    @app.post("/api/start")
    async def api_start(request: Request):
        _hub: BotStateHub = request.app.state.hub
        scheduler = request.app.state.scheduler

        if _hub.is_running():
            raise HTTPException(status_code=409, detail="이미 실행 중입니다")

        now_kst = datetime.now(KST)
        current_min = now_kst.hour * 60 + now_kst.minute
        if not (9 * 60 <= current_min < 15 * 60 + 20):
            raise HTTPException(
                status_code=400,
                detail="시장 시간이 아닙니다 (09:00~15:20 KST)",
            )

        _hub.clear_stop()
        scheduler.modify_job("market_poll", next_run_time=datetime.now(timezone.utc))
        logger.info("Admin UI: 봇 시작 요청 — modify_job 발화")
        return {"ok": True, "message": "모니터링 세션 시작됨"}

    @app.post("/api/stop")
    async def api_stop(request: Request):
        _hub: BotStateHub = request.app.state.hub
        _hub.request_stop()
        logger.info("Admin UI: 봇 중지 요청")
        return {"ok": True, "message": "중지 요청됨"}

    @app.post("/api/toggle-dry-run")
    async def api_toggle_dry_run(request: Request):
        _hub: BotStateHub = request.app.state.hub
        engine = request.app.state.engine
        executor = request.app.state.executor

        with _hub._lock:
            new_val = not engine._dry_run
            engine._dry_run = new_val
            executor._dry_run = new_val

        direction = "드라이런" if new_val else "실매도"
        logger.info("Admin UI: dry_run={}", new_val)
        return {
            "ok": True,
            "dry_run": new_val,
            "message": f"{direction} 모드로 전환됨. 재시작 시 .env 설정으로 초기화됩니다",
        }

    @app.post("/api/sell/{code}")
    async def api_sell(code: str, request: Request):
        if not re.match(r"^[0-9A-Za-z]{1,12}$", code):
            raise HTTPException(status_code=400, detail="유효하지 않은 종목 코드")

        _hub: BotStateHub = request.app.state.hub
        executor = request.app.state.executor
        _config = request.app.state.config

        snapshot = _hub.get_snapshot()
        sym = snapshot.get(code)
        if sym is None:
            raise HTTPException(status_code=404, detail=f"종목 {code}를 찾을 수 없습니다")

        # config에서 종목명 조회, 없으면 code 사용
        name = code
        if _config is not None:
            sym_cfg = next((s for s in _config.symbols if s.code == code), None)
            if sym_cfg is not None:
                name = sym_cfg.name

        sig = SellSignal(
            code=code,
            name=name,
            current_price=sym.get("current_price", 0.0),
            peak_price=sym.get("peak_price", 0.0),
            drop_pct=sym.get("drop_pct", 0.0),
            threshold=0.0,
            dry_run=False,  # 수동 매도는 항상 실거래
        )
        await run_in_threadpool(executor.execute, sig)
        logger.warning("Admin UI: 수동 매도 주문 제출 — {}", code)
        return {"ok": True, "message": "매도 주문 제출됨 — 체결 확인 필요"}

    @app.get("/")
    async def index() -> FileResponse:
        """대시보드 index.html 반환."""
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket) -> None:
        """실시간 스냅샷 브로드캐스트 — 연결 즉시 현재 스냅샷 전송 후 변경 시마다 push."""
        _hub: BotStateHub = websocket.app.state.hub
        await websocket.accept()
        await websocket.send_json(_hub.get_snapshot())
        try:
            while True:
                snapshot = await _hub.wait_for_change()
                await websocket.send_json(snapshot)
        except WebSocketDisconnect:
            pass  # 정상 종료 — 예외 전파 불필요

    # /static 마운트 — STATIC_DIR 절대 경로 사용 (T-06-06 경로 순회 방어)
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    return app
