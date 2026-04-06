"""
mutrade/monitor/scheduler.py

APScheduler 기반 시장 시간 스케줄러.

동작:
  - BlockingScheduler + CronTrigger(Mon-Fri, 09:00 KST)로 시장 개장 시 자동 실행
  - 실행 전 is_krx_trading_day() 로 KRX 거래일 여부 확인
  - 거래일이면 15:20 KST 까지 poll_prices() 루프 실행
  - 비거래일(주말, 공휴일)이면 즉시 반환
  - KeyboardInterrupt / SystemExit 으로 안전하게 종료
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger

from mutrade.monitor.holiday import is_krx_trading_day
from mutrade.config.loader import AppConfig
from mutrade.kis.price_feed import poll_prices

KST = ZoneInfo("Asia/Seoul")


def create_poll_session(kis, config: AppConfig):
    """
    폴링 세션 함수를 생성한다.

    APScheduler 잡으로 등록되는 클로저를 반환한다.
    실행 시 KRX 거래일 확인 후 장 마감 시간(기본 15:20 KST)까지 반복 폴링한다.

    Args:
        kis: 초기화된 PyKis 인스턴스
        config: AppConfig 인스턴스

    Returns:
        인자 없이 호출 가능한 폴링 세션 함수
    """
    def run_session():
        today = datetime.now(KST).date()

        if not is_krx_trading_day(today):
            logger.info("Today ({}) is not a KRX trading day. Skipping.", today)
            return

        logger.info(
            "Market session started. Monitoring {} symbols.", len(config.symbols)
        )
        for s in config.symbols:
            logger.info(
                "  {} ({}) threshold={:.1%}", s.code, s.name, s.threshold
            )

        close_minutes = config.market_close_hour * 60 + config.market_close_minute

        while True:
            now_kst = datetime.now(KST)
            current_minutes = now_kst.hour * 60 + now_kst.minute

            if current_minutes >= close_minutes:
                logger.info(
                    "Market session ended ({:02d}:{:02d} KST).",
                    config.market_close_hour,
                    config.market_close_minute,
                )
                break

            prices = poll_prices(kis, config)
            # Phase 2 에서 트레일링 스탑 엔진이 prices 를 소비한다
            logger.info(
                "Polled {} symbols: {}",
                len(prices),
                {k: f"{v:,.0f}" for k, v in prices.items()},
            )

            time.sleep(config.poll_interval)

    return run_session


def start_scheduler(kis, config: AppConfig) -> None:
    """
    APScheduler BlockingScheduler 를 시작한다.

    주 1회 (Mon-Fri, market_open_hour:market_open_minute KST) 실행되는
    폴링 세션 잡을 등록하고 블로킹 실행한다.

    Args:
        kis: 초기화된 PyKis 인스턴스
        config: AppConfig 인스턴스 (시장 시간 포함)
    """
    scheduler = BlockingScheduler(timezone="Asia/Seoul")
    poll_session = create_poll_session(kis, config)

    scheduler.add_job(
        poll_session,
        CronTrigger(
            day_of_week="mon-fri",
            hour=config.market_open_hour,
            minute=config.market_open_minute,
            timezone="Asia/Seoul",
        ),
        id="market_poll",
        name="KIS Market Price Poll",
    )

    logger.info(
        "Scheduler ready. Next trigger: Mon-Fri {:02d}:{:02d} KST.",
        config.market_open_hour,
        config.market_open_minute,
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Scheduler stopped by user.")
