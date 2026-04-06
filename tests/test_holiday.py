"""
KRX 공휴일 체크 테스트

테스트 시나리오:
1. 2026-01-01 (신정, 공휴일) → is_krx_trading_day returns False
2. 2026-04-06 (월요일, 평일) → is_krx_trading_day returns True
3. 2026-01-03 (토요일) → is_krx_trading_day returns False
"""
from datetime import date
import pytest

from mutrade.monitor.holiday import is_krx_trading_day


def test_new_year_is_not_trading_day():
    """2026-01-01 (신정)은 거래일이 아니어야 한다."""
    assert is_krx_trading_day(date(2026, 1, 1)) is False


def test_normal_weekday_is_trading_day():
    """2026-04-06 (월요일, 평일)은 거래일이어야 한다."""
    assert is_krx_trading_day(date(2026, 4, 6)) is True


def test_saturday_is_not_trading_day():
    """2026-01-03 (토요일)은 거래일이 아니어야 한다."""
    assert is_krx_trading_day(date(2026, 1, 3)) is False
