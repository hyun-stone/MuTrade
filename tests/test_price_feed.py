"""
tests/test_price_feed.py

TDD: price_feed.poll_prices 및 kis/client.create_kis_client 테스트.

커버리지:
- poll_prices: 정상 가격 반환
- poll_prices: KisAPIError 발생 시 해당 종목 제외 (price=0 없음)
- poll_prices: 예상치 못한 예외 발생 시 계속 진행
- poll_prices: 레이트 리밋 (time.sleep >= 0.066 초)
- poll_prices: 장 마감 시간 도달 시 폴링 중단
- create_kis_client: kis_mock=False → 실전 자격증명 사용
- create_kis_client: kis_mock=True → 가상 자격증명 사용
"""
import time
from datetime import datetime
from unittest.mock import MagicMock, patch, call
from zoneinfo import ZoneInfo

import pytest

from mutrade.config.loader import AppConfig, SymbolConfig
from mutrade.kis.price_feed import poll_prices, MIN_INTERVAL

KST = ZoneInfo("Asia/Seoul")


# ─── 픽스처 ────────────────────────────────────────────────────────────────

def make_config(
    symbols=None,
    market_close_hour=15,
    market_close_minute=20,
    poll_interval=3.0,
):
    if symbols is None:
        symbols = [
            SymbolConfig(code="005930", name="삼성전자", threshold=0.10),
            SymbolConfig(code="000660", name="SK하이닉스", threshold=0.10),
        ]
    return AppConfig(
        poll_interval=poll_interval,
        default_threshold=0.10,
        symbols=symbols,
        market_close_hour=market_close_hour,
        market_close_minute=market_close_minute,
    )


def make_quote(price: float):
    """mock quote 객체 — .price 속성을 가짐."""
    q = MagicMock()
    q.price = price
    return q


def make_kis_mock(prices: dict):
    """kis mock — kis.stock(code).quote() 가 해당 종목 가격 반환."""
    kis = MagicMock()
    def stock_side_effect(code):
        stock = MagicMock()
        stock.quote.return_value = make_quote(prices[code])
        return stock
    kis.stock.side_effect = stock_side_effect
    return kis


# ─── poll_prices 테스트 ────────────────────────────────────────────────────

class TestPollPrices:
    """poll_prices 정상 동작 테스트."""

    def test_returns_prices_for_all_symbols(self):
        """모든 종목의 가격을 dict 로 반환해야 한다."""
        prices_map = {"005930": 75000.0, "000660": 185000.0}
        kis = make_kis_mock(prices_map)
        config = make_config()

        # 장 마감 시간보다 훨씬 이전으로 설정
        now_kst = datetime(2026, 4, 7, 10, 0, 0, tzinfo=KST)
        with patch("mutrade.kis.price_feed.datetime") as mock_dt, \
             patch("mutrade.kis.price_feed.time") as mock_time:
            mock_dt.now.return_value = now_kst
            result = poll_prices(kis, config)

        assert result == {"005930": 75000.0, "000660": 185000.0}

    def test_skips_symbol_on_kis_api_error(self):
        """KisAPIError 발생 종목은 결과에 포함되지 않아야 한다 (price=0 없음)."""
        from pykis import KisAPIError

        kis = MagicMock()

        # 첫 번째 종목: 정상
        stock_ok = MagicMock()
        stock_ok.quote.return_value = make_quote(75000.0)

        # 두 번째 종목: KisAPIError 서브클래스를 직접 발생시킴
        stock_err = MagicMock()

        class FakeKisAPIError(KisAPIError):
            """테스트용 KisAPIError — 생성자 없이 속성만 설정."""
            def __init__(self):
                # 부모 __init__ 호출 없이 직접 속성 설정
                self.rt_cd = 1
                self.msg_cd = "EGW00201"
                self.msg1 = "오류 발생"
                self.args = ("KIS API error",)

        stock_err.quote.side_effect = FakeKisAPIError()

        def stock_side_effect(code):
            if code == "005930":
                return stock_ok
            return stock_err

        kis.stock.side_effect = stock_side_effect
        config = make_config()

        now_kst = datetime(2026, 4, 7, 10, 0, 0, tzinfo=KST)
        with patch("mutrade.kis.price_feed.datetime") as mock_dt, \
             patch("mutrade.kis.price_feed.time") as mock_time:
            mock_dt.now.return_value = now_kst
            result = poll_prices(kis, config)

        # 오류 종목은 결과에 없어야 함
        assert "005930" in result
        assert "000660" not in result
        # price=0 이 없어야 함
        assert 0 not in result.values()

    def test_skips_symbol_on_unexpected_exception(self):
        """예상치 못한 예외 발생 시 해당 종목 건너뛰고 계속 진행해야 한다."""
        kis = MagicMock()

        stock_ok = MagicMock()
        stock_ok.quote.return_value = make_quote(75000.0)

        stock_err = MagicMock()
        stock_err.quote.side_effect = RuntimeError("네트워크 오류")

        def stock_side_effect(code):
            if code == "005930":
                return stock_ok
            return stock_err

        kis.stock.side_effect = stock_side_effect
        config = make_config()

        now_kst = datetime(2026, 4, 7, 10, 0, 0, tzinfo=KST)
        with patch("mutrade.kis.price_feed.datetime") as mock_dt, \
             patch("mutrade.kis.price_feed.time") as mock_time:
            mock_dt.now.return_value = now_kst
            result = poll_prices(kis, config)

        assert "005930" in result
        assert "000660" not in result

    def test_rate_limit_sleep_called_between_requests(self):
        """각 종목 요청 사이에 time.sleep(MIN_INTERVAL) 이 호출되어야 한다."""
        prices_map = {"005930": 75000.0, "000660": 185000.0}
        kis = make_kis_mock(prices_map)
        config = make_config()

        now_kst = datetime(2026, 4, 7, 10, 0, 0, tzinfo=KST)
        with patch("mutrade.kis.price_feed.datetime") as mock_dt, \
             patch("mutrade.kis.price_feed.time") as mock_time:
            mock_dt.now.return_value = now_kst
            poll_prices(kis, config)

        # 2개 종목 → 2번 sleep 호출
        assert mock_time.sleep.call_count == 2
        for c in mock_time.sleep.call_args_list:
            sleep_val = c.args[0]
            assert sleep_val >= 0.066, f"sleep 값 {sleep_val}이 0.066 미만"

    def test_stops_at_market_close_time(self):
        """현재 시간이 장 마감 시간 이상이면 폴링을 즉시 중단해야 한다."""
        prices_map = {"005930": 75000.0, "000660": 185000.0}
        kis = make_kis_mock(prices_map)

        # 장 마감 시간: 15:20, 현재 시간: 15:20 (마감 시간과 같음)
        config = make_config(market_close_hour=15, market_close_minute=20)
        now_kst = datetime(2026, 4, 7, 15, 20, 0, tzinfo=KST)

        with patch("mutrade.kis.price_feed.datetime") as mock_dt, \
             patch("mutrade.kis.price_feed.time") as mock_time:
            mock_dt.now.return_value = now_kst
            result = poll_prices(kis, config)

        # 장 마감 시간에 도달했으므로 아무 종목도 폴링하지 않음
        assert result == {}
        kis.stock.assert_not_called()


# ─── create_kis_client 테스트 ──────────────────────────────────────────────

class TestCreateKisClient:
    """create_kis_client 팩토리 함수 테스트."""

    def _make_real_settings(self):
        from mutrade.settings import Settings
        return Settings(
            KIS_ID="real_id",
            KIS_ACCOUNT="12345678-01",
            KIS_APPKEY="real_appkey",
            KIS_SECRETKEY="real_secretkey",
            KIS_MOCK=False,
        )

    def _make_mock_settings(self):
        from mutrade.settings import Settings
        return Settings(
            KIS_ID="real_id",
            KIS_ACCOUNT="12345678-01",
            KIS_APPKEY="real_appkey",
            KIS_SECRETKEY="real_secretkey",
            KIS_MOCK=True,
            KIS_VIRTUAL_ID="virtual_id",
            KIS_VIRTUAL_ACCOUNT="98765432-01",
            KIS_VIRTUAL_APPKEY="virtual_appkey",
            KIS_VIRTUAL_SECRETKEY="virtual_secretkey",
        )

    def test_real_mode_uses_real_credentials(self):
        """kis_mock=False 시 실전 자격증명으로 PyKis 생성해야 한다."""
        from mutrade.kis.client import create_kis_client

        settings = self._make_real_settings()

        with patch("mutrade.kis.client.PyKis") as mock_pykis:
            mock_pykis.return_value = MagicMock()
            create_kis_client(settings)

        mock_pykis.assert_called_once()
        call_kwargs = mock_pykis.call_args.kwargs
        assert call_kwargs["id"] == "real_id"
        assert call_kwargs["appkey"] == "real_appkey"
        assert call_kwargs["secretkey"] == "real_secretkey"
        assert call_kwargs["keep_token"] is True
        # 가상 자격증명은 넘기지 않아야 함
        assert "virtual_id" not in call_kwargs or call_kwargs.get("virtual_id") is None

    def test_mock_mode_uses_virtual_credentials(self):
        """kis_mock=True 시 가상 자격증명도 포함하여 PyKis 생성해야 한다."""
        from mutrade.kis.client import create_kis_client

        settings = self._make_mock_settings()

        with patch("mutrade.kis.client.PyKis") as mock_pykis:
            mock_pykis.return_value = MagicMock()
            create_kis_client(settings)

        mock_pykis.assert_called_once()
        call_kwargs = mock_pykis.call_args.kwargs
        assert call_kwargs["id"] == "real_id"
        assert call_kwargs["appkey"] == "real_appkey"
        assert call_kwargs["secretkey"] == "real_secretkey"
        assert call_kwargs["virtual_id"] == "virtual_id"
        assert call_kwargs["virtual_appkey"] == "virtual_appkey"
        assert call_kwargs["virtual_secretkey"] == "virtual_secretkey"
        assert call_kwargs["keep_token"] is True
