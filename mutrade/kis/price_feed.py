"""
mutrade/kis/price_feed.py

가격 폴링 루프 — 레이트 리밋 및 에러 처리 포함.

레이트 리밋: KIS API 는 초당 최대 15 요청 허용.
  MIN_INTERVAL = 1/15 ≈ 66.7ms 를 각 요청 사이에 sleep 으로 강제.

에러 처리:
  - KisAPIError: 로그 후 해당 종목 건너뜀 (price=0 전파 금지)
  - 기타 예외: 로그 후 계속 진행

장 마감 체크: 각 종목 폴링 전에 현재 KST 시간이 market_close 이상이면 즉시 중단.
"""
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from pykis import KisAPIError

from mutrade.config.loader import AppConfig

KST = ZoneInfo("Asia/Seoul")
MIN_INTERVAL = 1.0 / 15  # 15 req/s 상한 → ~66.7ms


def poll_prices(kis, config: AppConfig) -> dict[str, float]:
    """
    설정된 모든 종목의 현재가를 폴링한다.

    Returns:
        종목 코드 → 현재가 dict.
        KIS API 오류가 발생한 종목은 결과에서 제외된다 (price=0 없음).

    Side effects:
        - 각 요청 사이 MIN_INTERVAL(~66.7ms) sleep (레이트 리밋)
        - 장 마감 시간 도달 시 즉시 루프 종료
    """
    prices: dict[str, float] = {}
    close_minutes = config.market_close_hour * 60 + config.market_close_minute

    for symbol_cfg in config.symbols:
        # 장 마감 시간 체크
        now_kst = datetime.now(KST)
        current_minutes = now_kst.hour * 60 + now_kst.minute
        if current_minutes >= close_minutes:
            logger.info(
                "Market close time reached ({:02d}:{:02d} KST). Stopping poll.",
                config.market_close_hour,
                config.market_close_minute,
            )
            break

        try:
            quote = kis.stock(symbol_cfg.code).quote()
            price = float(quote.price)
            prices[symbol_cfg.code] = price
            logger.debug(
                "{} ({}): {:,.0f}",
                symbol_cfg.code,
                symbol_cfg.name,
                price,
            )
        except KisAPIError as e:
            logger.error(
                "KIS API error for {} ({}): rt_cd={}, msg_cd={}, msg={}",
                symbol_cfg.code,
                symbol_cfg.name,
                getattr(e, "rt_cd", None),
                getattr(e, "msg_cd", None),
                getattr(e, "msg1", str(e)),
            )
            # price=0 전파 금지 — 해당 종목을 결과에서 제외
        except Exception as e:
            logger.error(
                "Unexpected error fetching {} ({}): {}",
                symbol_cfg.code,
                symbol_cfg.name,
                e,
            )
            # 예외 발생 종목도 price=0 없이 건너뜀

        time.sleep(MIN_INTERVAL)

    return prices
