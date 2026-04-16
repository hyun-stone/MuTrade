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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from loguru import logger

from mutrade.admin.hub import BotStateHub

# 정적 파일 디렉터리 — Path(__file__).parent / "static" 절대 경로 (실행 디렉터리 독립)
# 테스트에서 patch.object(app_module, "STATIC_DIR", ...) 로 교체 가능
STATIC_DIR = Path(__file__).parent / "static"


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
