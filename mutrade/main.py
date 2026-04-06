"""
mutrade/main.py

MuTrade 봇 엔트리포인트.

실행 흐름:
  1. loguru 핸들러 설정 (콘솔 INFO + 파일 DEBUG, 10MB 로테이션)
  2. Settings 로드 (pydantic-settings — .env 또는 환경변수)
  3. AppConfig 로드 (config.toml)
  4. PyKis 클라이언트 초기화 (keep_token=True — 24h 토큰 자동 갱신)
  5. APScheduler 시작 (블로킹 — Mon-Fri 09:00 KST 자동 폴링)

Usage:
  python mutrade/main.py
  python -m mutrade.main
"""
import sys

from loguru import logger

from mutrade.settings import Settings
from mutrade.config.loader import load_config
from mutrade.kis.client import create_kis_client
from mutrade.monitor.scheduler import start_scheduler


def main() -> None:
    """MuTrade 봇을 초기화하고 스케줄러를 시작한다."""
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

    # 스케줄러 시작 (블로킹 — 종료까지 반환 안 됨)
    start_scheduler(kis, config)


if __name__ == "__main__":
    main()
