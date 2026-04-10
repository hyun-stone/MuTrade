"""
tests/test_telegram_listener.py

TelegramListener 단위 테스트.

테스트 시나리오:
1. token=None일 때 start() 호출 시 스레드를 생성하지 않는다 (no-op)
2. chat_id=None일 때 start() 호출 시 스레드를 생성하지 않는다 (no-op)
3. _build_status_message()가 종목별 현재가, 고점, 하락률을 올바르게 포맷
4. _build_status_message()에 빈 states를 넘기면 "모니터링 종목 없음" 반환
5. 하락률 계산: peak=100000, current=93000 -> -7.0%
"""
import pytest

from mutrade.engine.models import SymbolState
from mutrade.config.loader import SymbolConfig
from mutrade.notifier.telegram_listener import TelegramListener, _build_status_message


class TestTelegramListenerNoOp:
    """token/chat_id 미설정 시 no-op 검증."""

    def test_start_noop_without_token(self):
        """token=None으로 start() 호출 시 스레드를 생성하지 않는다."""
        listener = TelegramListener(token=None, chat_id="-100123456")
        # engine/kis/symbols를 mock 없이 None 전달 — no-op이라 호출 안 됨
        listener.start(engine=None, kis=None, symbols={}, dry_run=False, kis_mock=False)
        assert listener._thread is None

    def test_start_noop_without_chat_id(self):
        """chat_id=None으로 start() 호출 시 스레드를 생성하지 않는다."""
        listener = TelegramListener(token="bot123:ABC", chat_id=None)
        listener.start(engine=None, kis=None, symbols={}, dry_run=False, kis_mock=False)
        assert listener._thread is None


class TestBuildStatusMessage:
    """_build_status_message 순수 함수 검증."""

    @pytest.fixture
    def sample_state(self):
        return {
            "005930": SymbolState(code="005930", peak_price=218000, warm=True)
        }

    @pytest.fixture
    def sample_prices(self):
        return {"005930": 204000.0}

    @pytest.fixture
    def sample_symbols(self):
        return {
            "005930": SymbolConfig(code="005930", name="삼성전자", threshold=0.10)
        }

    def test_format_contains_code_name_price_peak_drop(
        self, sample_state, sample_prices, sample_symbols
    ):
        """종목코드, 종목명, 현재가, 고점, 하락률이 포함된 메시지를 반환한다."""
        msg = _build_status_message(
            states=sample_state,
            prices=sample_prices,
            symbols=sample_symbols,
            dry_run=False,
            kis_mock=False,
        )
        assert "005930" in msg, f"종목코드 미포함: {msg}"
        assert "삼성전자" in msg, f"종목명 미포함: {msg}"
        assert "204,000" in msg, f"현재가(쉼표 포맷) 미포함: {msg}"
        assert "218,000" in msg, f"고점(쉼표 포맷) 미포함: {msg}"
        # 하락률: (218000 - 204000) / 218000 * 100 = 6.422... → -6.4%
        assert "-6.4%" in msg, f"하락률 미포함: {msg}"

    def test_build_status_message_empty_states(self, sample_symbols):
        """빈 states를 넘기면 '모니터링 종목 없음' 메시지를 반환한다."""
        msg = _build_status_message(
            states={},
            prices={},
            symbols=sample_symbols,
            dry_run=False,
            kis_mock=False,
        )
        assert "모니터링 종목 없음" in msg, f"'모니터링 종목 없음' 미포함: {msg}"

    def test_drop_pct_calculation(self):
        """peak=100000, current=93000 → 하락률 -7.0%."""
        state = {"TEST": SymbolState(code="TEST", peak_price=100000, warm=True)}
        prices = {"TEST": 93000.0}
        symbols = {"TEST": SymbolConfig(code="TEST", name="테스트종목", threshold=0.10)}
        msg = _build_status_message(
            states=state,
            prices=prices,
            symbols=symbols,
            dry_run=False,
            kis_mock=False,
        )
        assert "-7.0%" in msg, f"하락률 -7.0% 미포함: {msg}"

    def test_dry_run_kis_mock_status_display(self, sample_state, sample_prices, sample_symbols):
        """DRY_RUN: ON | 모의투자: ON 상태 표시가 포함된다."""
        msg = _build_status_message(
            states=sample_state,
            prices=sample_prices,
            symbols=sample_symbols,
            dry_run=True,
            kis_mock=True,
        )
        assert "ON" in msg, f"ON 상태 표시 미포함: {msg}"
