"""
tests/test_order_executor.py

TDD: OrderExecutor 매도 주문 실행기 테스트.

커버리지:
- EXEC-01: 시장가 매도 주문 — acc.sell(market="KRX", price=None, qty=orderable) 호출
- EXEC-02: 매도 가능 수량 — balance.stock(code).orderable 값 사용
- EXEC-03: SELL_PENDING 중복 방지 — 동일 종목 두 번째 execute는 sell() 미호출
- EXEC-04: 체결 확인 — sell 성공 후 daily_orders().order() 호출
"""
from unittest.mock import MagicMock, patch, call
from decimal import Decimal

import pytest

from mutrade.engine.models import SellSignal
from mutrade.executor.order_executor import OrderExecutor


# ─── 픽스처 헬퍼 ─────────────────────────────────────────────────────────────

def make_signal(code="005930", name="삼성전자", dry_run=False) -> SellSignal:
    return SellSignal(
        code=code,
        name=name,
        current_price=70000.0,
        peak_price=80000.0,
        drop_pct=0.125,
        threshold=0.10,
        dry_run=dry_run,
    )


def make_kis_mock(orderable=10):
    """PyKis mock — account().balance("KR").stock(code).orderable 체인."""
    kis = MagicMock()
    acc = MagicMock()
    balance = MagicMock()
    stock_item = MagicMock()
    stock_item.orderable = orderable
    balance.stock.return_value = stock_item
    acc.balance.return_value = balance
    order = MagicMock()
    order.branch = "00"
    order.number = "12345"
    acc.sell.return_value = order
    # daily_orders mock
    daily = MagicMock()
    record = MagicMock()
    record.executed_quantity = orderable
    record.pending_quantity = 0
    record.price = 70000.0
    daily.order.return_value = record
    acc.daily_orders.return_value = daily
    kis.account.return_value = acc
    return kis, acc, order


# ─── 테스트 ───────────────────────────────────────────────────────────────────

class TestOrderExecutor:
    """OrderExecutor EXEC-01~04 요구사항 단위 테스트."""

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_market_sell_called(self, mock_sleep):
        """EXEC-01: execute(signal) 후 acc.sell(market="KRX", symbol="005930", price=None, qty=10) 호출."""
        kis, acc, order = make_kis_mock(orderable=10)
        executor = OrderExecutor(kis)

        executor.execute(make_signal())

        acc.sell.assert_called_once_with(
            market="KRX",
            symbol="005930",
            price=None,
            qty=10,
        )

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_dry_run_skips_sell(self, mock_sleep):
        """EXEC-01: dry_run=True signal → acc.sell 미호출."""
        kis, acc, order = make_kis_mock()
        executor = OrderExecutor(kis)

        executor.execute(make_signal(dry_run=True))

        acc.sell.assert_not_called()

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_orderable_qty_used(self, mock_sleep):
        """EXEC-02: orderable=25로 mock → qty=25로 sell 호출."""
        kis, acc, order = make_kis_mock(orderable=25)
        executor = OrderExecutor(kis)

        executor.execute(make_signal())

        acc.sell.assert_called_once_with(
            market="KRX",
            symbol="005930",
            price=None,
            qty=25,
        )

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_no_stock_skips_sell(self, mock_sleep):
        """EXEC-02: balance.stock() returns None → sell 미호출."""
        kis, acc, order = make_kis_mock()
        acc.balance.return_value.stock.return_value = None
        executor = OrderExecutor(kis)

        executor.execute(make_signal())

        acc.sell.assert_not_called()

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_zero_orderable_skips(self, mock_sleep):
        """EXEC-02: orderable=0 → sell 미호출."""
        kis, acc, order = make_kis_mock(orderable=0)
        executor = OrderExecutor(kis)

        executor.execute(make_signal())

        acc.sell.assert_not_called()

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_sell_pending_blocks_duplicate(self, mock_sleep):
        """EXEC-03: execute 2회 → sell 1회만 호출.

        체결 확인 중(daily_orders().order() returns None)에 두 번째 execute 호출 시
        SELL_PENDING으로 차단되어야 한다.
        """
        kis, acc, order = make_kis_mock()
        # 체결 확인을 항상 None 반환으로 설정 → _pending이 max_attempts 후 해제
        # 하지만 첫 execute가 끝나기 전에 두 번째를 호출하려면 _pending이 채워진 상태여야 함.
        # 간단한 방법: sell() 이후 직접 _pending 상태에서 두 번째 execute 호출을 검증.
        acc.daily_orders.return_value.order.return_value = None  # 체결 미확인
        executor = OrderExecutor(kis)

        executor.execute(make_signal())  # 첫 번째: sell 호출 + 체결 타임아웃 후 pending 해제
        # pending이 해제되기 전 상태를 시뮬레이션:
        # execute 중간에 _pending을 강제로 설정하여 중복 차단을 테스트
        executor._pending.add("005930")
        executor.execute(make_signal())  # 두 번째: SELL_PENDING으로 차단

        assert acc.sell.call_count == 1

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_sell_failure_clears_pending(self, mock_sleep):
        """EXEC-03: sell()에서 예외 발생 시 _pending에서 code 제거 → 재시도 가능."""
        from pykis import KisAPIError
        kis, acc, order = make_kis_mock()
        acc.sell.side_effect = KisAPIError.__new__(KisAPIError)
        executor = OrderExecutor(kis)

        # 첫 번째 execute — sell 예외 발생
        executor.execute(make_signal())
        assert "005930" not in executor._pending

        # sell을 정상으로 복원 후 재시도 가능해야 함
        acc.sell.side_effect = None
        acc.sell.return_value = order
        executor.execute(make_signal())
        assert acc.sell.call_count == 2

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_fill_confirmed(self, mock_sleep):
        """EXEC-04: sell 후 daily_orders().order(order)가 호출된다."""
        kis, acc, order = make_kis_mock()
        executor = OrderExecutor(kis)

        executor.execute(make_signal())

        acc.daily_orders.assert_called()
        acc.daily_orders.return_value.order.assert_called()

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_fill_timeout_clears_pending(self, mock_sleep):
        """EXEC-04: daily_orders().order() returns None 반복 → _pending에서 code 제거."""
        kis, acc, order = make_kis_mock()
        # order() 가 항상 None 반환 → 타임아웃
        acc.daily_orders.return_value.order.return_value = None
        executor = OrderExecutor(kis)

        executor.execute(make_signal())

        assert "005930" not in executor._pending

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_confirm_fill_after_success_clears_pending(self, mock_sleep):
        """EXEC-03/EXEC-04: 체결 확인 후 같은 code로 다시 execute 가능."""
        kis, acc, order = make_kis_mock()
        executor = OrderExecutor(kis)

        # 첫 번째 execute — 체결 확인까지 완료
        executor.execute(make_signal())
        assert "005930" not in executor._pending

        # 다시 execute 가능해야 함 (sell 재호출)
        executor.execute(make_signal())
        assert acc.sell.call_count == 2

    @patch("mutrade.executor.order_executor.time.sleep")
    def test_executor_level_dry_run(self, mock_sleep):
        """OrderExecutor(kis, dry_run=True)이면 signal.dry_run 상관없이 sell 미호출."""
        kis, acc, order = make_kis_mock()
        executor = OrderExecutor(kis, dry_run=True)

        executor.execute(make_signal(dry_run=False))

        acc.sell.assert_not_called()
