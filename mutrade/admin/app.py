"""
mutrade/admin/app.py

FastAPI 앱 팩토리.

lifespan:
- startup: asyncio 이벤트 루프를 BotStateHub에 연결 (attach_loop)
- shutdown: hub 상태 정리

엔드포인트:
- GET /health — 서버 생존 확인
"""
import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from loguru import logger

from mutrade.admin.hub import BotStateHub


def create_app(hub: BotStateHub, **kwargs: Any) -> FastAPI:
    """
    FastAPI 앱 인스턴스를 생성한다.

    Args:
        hub: BotStateHub 인스턴스 (봇 상태 브릿지)
        **kwargs: 추후 engine, scheduler 등 의존성 주입용 (Phase 6~7에서 사용)

    Returns:
        FastAPI 앱 인스턴스
    """

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

    return app
