"""
KRX 거래일 판정 모듈

exchange_calendars 라이브러리의 XKRX 캘린더를 사용하여
특정 날짜가 KRX 거래일인지 오프라인으로 판정한다.

D-02 결정: exchange_calendars가 httpx + KIS 시장 상태 API보다
신뢰성이 높고 외부 장애에 독립적이므로 선택.
"""
import exchange_calendars as xcals
from datetime import date

# 모듈 로드 시 한 번만 캘린더 객체를 생성 (재사용)
_krx = xcals.get_calendar("XKRX")


def is_krx_trading_day(today: date | None = None) -> bool:
    """
    주어진 날짜가 KRX 거래일인지 반환한다.

    Args:
        today: 확인할 날짜 (None 이면 오늘 날짜 사용)

    Returns:
        True  — 거래일 (평일, 공휴일 아님)
        False — 비거래일 (주말, 공휴일, 임시 휴장일 등)
    """
    check_date = today or date.today()
    return _krx.is_session(check_date.isoformat())
