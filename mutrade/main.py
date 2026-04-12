"""
mutrade/main.py

MuTrade 봇 엔트리포인트.

실행 흐름:
  1. loguru 핸들러 설정 (콘솔 INFO + 파일 DEBUG, 10MB 로테이션)
  2. Settings 로드 (pydantic-settings — .env 또는 환경변수)
  3. AppConfig 로드 (config.toml)
  4. PyKis 클라이언트 초기화 (keep_token=True — 24h 토큰 자동 갱신)
  5. TrailingStopEngine 초기화 (StateStore에서 고점 복원)
  6. OrderExecutor 초기화 (매도 주문 실행기)
  7. BotStateHub 초기화 (봇 ↔ FastAPI 브릿지)
  8. BackgroundScheduler 시작 (비블로킹 — 별도 스레드)
  9. uvicorn.run() 시작 (블로킹 — FastAPI 메인 루프)

Usage:
  python mutrade/main.py
  python -m mutrade.main
"""
import sys

import uvicorn
from loguru import logger

from mutrade.settings import Settings
from mutrade.config.loader import load_config
from mutrade.kis.client import create_kis_client
from mutrade.monitor.scheduler import start_scheduler
from mutrade.engine.state_store import StateStore
from mutrade.engine.trailing_stop import TrailingStopEngine
from mutrade.executor.order_executor import OrderExecutor
from mutrade.notifier.telegram import TelegramNotifier
from mutrade.admin.hub import BotStateHub
from mutrade.admin.app import create_app


def main() -> None:
    """MuTrade 봇을 초기화하고 uvicorn + BackgroundScheduler를 시작한다."""
    # loguru 핸들러 재설정
    logger.remove()  # 기본 stderr 핸들러 제거
    logger.add(
        sys.stderr,
        level="INFO",
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{function}</cyan> | "
            "<level>{message}</level>"
        ),
    )
    logger.add(
        "logs/mutrade.log",
        rotation="10 MB",
        retention="30 days",
        level="DEBUG",
    )

    logger.info("MuTrade starting...")

    # 설정 로드
    settings = Settings()
    logger.info("Settings loaded. KIS_MOCK={}", settings.kis_mock)

    config = load_config()
    logger.info(
        "Config loaded. {} symbols, poll_interval={}s",
        len(config.symbols),
        config.poll_interval,
    )

    # KIS 클라이언트 초기화
    kis = create_kis_client(settings)
    logger.info("KIS client initialized. Token will auto-refresh (keep_token=True).")

    # 트레일링 스탑 엔진 초기화
    store = StateStore(path="state.json")
    engine = TrailingStopEngine(
        symbols=config.symbols,
        store=store,
        dry_run=settings.dry_run,
    )
    logger.info(
        "Trailing stop engine initialized. dry_run={}, {} symbols tracked",
        settings.dry_run, len(engine.states),
    )

    # Telegram 알림기 초기화 (D-01: 둘 다 없으면 None 반환 — 알림 없이 정상 실행)
    notifier = TelegramNotifier(
        token=settings.telegram_bot_token,
        chat_id=settings.telegram_chat_id,
    )
    if settings.telegram_bot_token:
        logger.info("Telegram 알림 활성화. chat_id={}", settings.telegram_chat_id)
    else:
        logger.info("Telegram 알림 비활성화 (TELEGRAM_BOT_TOKEN 미설정).")

    # 매도 주문 실행기 초기화
    executor = OrderExecutor(kis=kis, dry_run=settings.dry_run, notifier=notifier)
    logger.info(
        "Order executor initialized. dry_run={}",
        settings.dry_run,
    )

    # BotStateHub 초기화 (봇 ↔ FastAPI 브릿지)
    hub = BotStateHub()

    # BackgroundScheduler 시작 (비블로킹 — 별도 스레드)
    scheduler = start_scheduler(kis, config, engine, executor, hub=hub)

    # FastAPI 앱 생성 (hub, scheduler 주입 — Phase 6~7에서 라우트 추가)
    app = create_app(hub=hub, scheduler=scheduler, engine=engine, config=config)

    # uvicorn이 메인 스레드 담당 (블로킹 — 프로세스 종료까지 실행)
    logger.info("Starting uvicorn on http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


if __name__ == "__main__":
    main()
