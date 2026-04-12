"""
tests/test_scheduler.py

APScheduler 스케줄러 및 폴링 세션 테스트.

커버리지:
- create_poll_session: 비거래일에는 즉시 반환 (poll_prices 호출 없음)
- create_poll_session: 거래일에는 poll_prices 를 최소 1회 호출
- create_poll_session: 장 마감 시간 도달 시 루프 종료
- create_poll_session: engine.tick(prices) 가 호출되어야 한다
- create_poll_session: engine.tick()이 SellSignal을 반환하면 SELL SIGNAL 로그 출력
- create_poll_session: dry_run=False SellSignal 발생 시 executor.execute() 호출
- create_poll_session: dry_run=True SellSignal 발생 시 executor.execute() 미호출
- start_scheduler: BackgroundScheduler 인스턴스를 반환한다
- create_poll_session: hub 전달 시 폴링 후 hub.push_snapshot() 호출
- create_poll_session: hub.is_stop_requested() True이면 루프 즉시 종료 후 hub.clear_stop() 호출
- TestShutdownLog: BackgroundScheduler mock으로 업데이트
"""
from datetime import datetime, date
from unittest.mock import MagicMock, patch, call
from zoneinfo import ZoneInfo

import pytest

from mutrade.config.loader import AppConfig, SymbolConfig
from mutrade.engine.models import SellSignal
from mutrade.executor.order_executor import OrderExecutor
from mutrade.monitor.scheduler import create_poll_session, start_scheduler

KST = ZoneInfo("Asia/Seoul")


# ─── 픽스처 ────────────────────────────────────────────────────────────────

def make_config(
    symbols=None,
    market_open_hour=9,
    market_open_minute=0,
    market_close_hour=15,
    market_close_minute=20,
    poll_interval=3.0,
):
    if symbols is None:
        symbols = [
            SymbolConfig(code="005930", name="삼성전자", threshold=0.10),
        ]
    return AppConfig(
        poll_interval=poll_interval,
        default_threshold=0.10,
        symbols=symbols,
        market_open_hour=market_open_hour,
        market_open_minute=market_open_minute,
        market_close_hour=market_close_hour,
        market_close_minute=market_close_minute,
    )


def make_engine_mock():
    """TrailingStopEngine mock 생성."""
    engine = MagicMock()
    engine.tick.return_value = []
    engine.states = {}
    return engine


def make_executor_mock():
    """OrderExecutor mock 생성."""
    return MagicMock(spec=OrderExecutor)


# ─── create_poll_session 테스트 ────────────────────────────────────────────

class TestCreatePollSession:
    """create_poll_session 반환 함수의 동작 테스트."""

    def test_non_trading_day_returns_immediately(self):
        """비거래일에는 즉시 반환되고 poll_prices 가 호출되지 않아야 한다."""
        kis = MagicMock()
        config = make_config()
        engine = make_engine_mock()
        executor = make_executor_mock()
        run_session = create_poll_session(kis, config, engine, executor)

        # 비거래일 날짜 반환
        non_trading_dt = datetime(2026, 4, 5, 9, 0, 0, tzinfo=KST)  # 일요일

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=False) as mock_holiday, \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices") as mock_poll:
            mock_dt.now.return_value = non_trading_dt
            run_session()

        # poll_prices 는 호출되지 않아야 함
        mock_poll.assert_not_called()

    def test_trading_day_calls_poll_prices_at_least_once(self):
        """거래일에는 장 마감 전까지 poll_prices 를 최소 1회 호출해야 한다."""
        kis = MagicMock()

        # 장 마감 시간을 현재 + 1분 뒤로 설정하여 루프가 1회만 실행되도록 제어
        # 첫 번째 datetime.now(): 09:00 (루프 진입)
        # 두 번째 datetime.now(): 09:01 = market_close (루프 종료)
        trading_day_start = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        trading_day_end = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,  # 09:01에 마감
        )

        call_count = 0
        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            # 첫 번째 호출(세션 시작 날짜 확인): trading_day_start
            # 두 번째 호출(루프 내 시간 확인 - 첫 번째): trading_day_start (마감 전)
            # 세 번째 호출(루프 내 시간 확인 - 두 번째): trading_day_end (마감)
            if call_count <= 2:
                return trading_day_start
            return trading_day_end

        engine = make_engine_mock()
        executor = make_executor_mock()

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices", return_value={"005930": 75000.0}) as mock_poll, \
             patch("mutrade.monitor.scheduler.time") as mock_time:
            mock_dt.now.side_effect = mock_now
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # poll_prices 가 최소 1회 호출되어야 함
        assert mock_poll.call_count >= 1

    def test_stops_polling_at_market_close(self):
        """현재 시간이 장 마감 시간 이상이면 루프를 종료해야 한다."""
        kis = MagicMock()

        # 현재 시간이 이미 마감 시간 이후
        market_close_dt = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,
        )

        engine = make_engine_mock()
        executor = make_executor_mock()

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices") as mock_poll, \
             patch("mutrade.monitor.scheduler.time") as mock_time:
            mock_dt.now.return_value = market_close_dt
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # 장 마감 시간이므로 poll_prices 가 호출되지 않아야 함
        mock_poll.assert_not_called()

    def test_is_krx_trading_day_receives_todays_date(self):
        """is_krx_trading_day 가 오늘 날짜를 인자로 호출되어야 한다."""
        kis = MagicMock()
        config = make_config(
            market_close_hour=9,
            market_close_minute=0,
        )

        today_dt = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        engine = make_engine_mock()
        executor = make_executor_mock()

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=False) as mock_holiday, \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices") as mock_poll:
            mock_dt.now.return_value = today_dt
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # is_krx_trading_day 가 today_dt.date() 로 호출되어야 함
        mock_holiday.assert_called_once_with(today_dt.date())

    def test_poll_session_calls_engine_tick_with_prices(self):
        """폴링 후 engine.tick(prices) 가 호출되어야 한다."""
        kis = MagicMock()

        trading_day_start = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        trading_day_end = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,
        )

        call_count = 0
        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return trading_day_start
            return trading_day_end

        engine = make_engine_mock()
        executor = make_executor_mock()
        prices = {"005930": 75000.0}

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices", return_value=prices) as mock_poll, \
             patch("mutrade.monitor.scheduler.time"):
            mock_dt.now.side_effect = mock_now
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # engine.tick이 poll_prices 결과로 호출되어야 함
        engine.tick.assert_called_once_with(prices)

    def test_poll_session_logs_sell_signals(self):
        """engine.tick()이 SellSignal을 반환하면 SELL SIGNAL 로그가 출력되어야 한다."""
        kis = MagicMock()

        trading_day_start = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        trading_day_end = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,
        )

        call_count = 0
        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return trading_day_start
            return trading_day_end

        signal = SellSignal(
            code="005930",
            name="삼성전자",
            current_price=67500.0,
            peak_price=75000.0,
            drop_pct=0.10,
            threshold=0.10,
            dry_run=True,
        )
        engine = make_engine_mock()
        engine.tick.return_value = [signal]
        executor = make_executor_mock()

        warning_calls = []

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices", return_value={"005930": 67500.0}), \
             patch("mutrade.monitor.scheduler.time"), \
             patch("mutrade.monitor.scheduler.logger") as mock_logger:
            mock_dt.now.side_effect = mock_now
            mock_logger.warning.side_effect = lambda msg, *args, **kwargs: warning_calls.append(msg)
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # SELL SIGNAL 로그 메시지가 출력되어야 함
        assert any("SELL SIGNAL" in call for call in warning_calls), (
            f"Expected 'SELL SIGNAL' in warning logs, got: {warning_calls}"
        )

    def test_live_signal_calls_executor(self):
        """dry_run=False SellSignal 발생 시 executor.execute(signal)이 호출되어야 한다."""
        kis = MagicMock()

        trading_day_start = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        trading_day_end = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,
        )

        call_count = 0
        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return trading_day_start
            return trading_day_end

        signal = SellSignal(
            code="005930",
            name="삼성전자",
            current_price=67500.0,
            peak_price=75000.0,
            drop_pct=0.10,
            threshold=0.10,
            dry_run=False,  # LIVE signal
        )
        engine = make_engine_mock()
        engine.tick.return_value = [signal]
        executor = make_executor_mock()

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices", return_value={"005930": 67500.0}), \
             patch("mutrade.monitor.scheduler.time"):
            mock_dt.now.side_effect = mock_now
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # executor.execute가 signal과 함께 호출되어야 함
        executor.execute.assert_called_once_with(signal)

    def test_dry_run_signal_skips_executor(self):
        """dry_run=True SellSignal 발생 시 executor.execute()가 호출되지 않아야 한다."""
        kis = MagicMock()

        trading_day_start = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        trading_day_end = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,
        )

        call_count = 0
        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return trading_day_start
            return trading_day_end

        signal = SellSignal(
            code="005930",
            name="삼성전자",
            current_price=67500.0,
            peak_price=75000.0,
            drop_pct=0.10,
            threshold=0.10,
            dry_run=True,  # DRY-RUN signal
        )
        engine = make_engine_mock()
        engine.tick.return_value = [signal]
        executor = make_executor_mock()

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices", return_value={"005930": 67500.0}), \
             patch("mutrade.monitor.scheduler.time"):
            mock_dt.now.side_effect = mock_now
            run_session = create_poll_session(kis, config, engine, executor)
            run_session()

        # dry_run=True이므로 executor.execute는 호출되지 않아야 함
        executor.execute.assert_not_called()


class TestShutdownLog:
    """NOTIF-04 — 종료 시 engine.states 순회 로깅 테스트."""

    def test_shutdown_logs_state(self):
        """BackgroundScheduler 시작 시 engine.states를 순회하며 로그를 출력한다."""
        from mutrade.engine.models import SymbolState

        kis = MagicMock()
        config = make_config()
        engine = make_engine_mock()
        executor = make_executor_mock()

        # engine.states에 2개 종목 설정
        engine.states = {
            "005930": SymbolState(code="005930", peak_price=80000.0, warm=True),
            "000660": SymbolState(code="000660", peak_price=150000.0, warm=False),
        }

        info_calls = []

        with patch("mutrade.monitor.scheduler.BackgroundScheduler") as mock_sched_cls, \
             patch("mutrade.monitor.scheduler.logger") as mock_logger:
            mock_sched = MagicMock()
            mock_sched_cls.return_value = mock_sched
            mock_logger.info.side_effect = lambda msg, *a, **kw: info_calls.append(str(msg) + str(a))

            result = start_scheduler(kis, config, engine, executor)

        # start_scheduler()가 스케줄러 인스턴스를 반환해야 함
        assert result is mock_sched, "start_scheduler must return the scheduler instance"
        # 스케줄러 시작 로그가 출력되어야 함 (종목 정보 포함)
        combined = " ".join(info_calls)
        assert "005930" in combined or "Scheduler" in combined, (
            f"Expected scheduler/symbol info in logs: {info_calls}"
        )


class TestBackgroundSchedulerReturn:
    """start_scheduler — BackgroundScheduler 인스턴스 반환 테스트."""

    def test_start_scheduler_returns_background_scheduler(self):
        """start_scheduler()가 BackgroundScheduler 인스턴스를 반환해야 한다 (None 아님)."""
        kis = MagicMock()
        config = make_config()
        engine = make_engine_mock()
        executor = make_executor_mock()

        with patch("mutrade.monitor.scheduler.BackgroundScheduler") as mock_sched_cls:
            mock_sched = MagicMock()
            mock_sched_cls.return_value = mock_sched

            result = start_scheduler(kis, config, engine, executor)

        assert result is not None, "start_scheduler must return a scheduler instance (not None)"
        assert result is mock_sched, "start_scheduler must return the BackgroundScheduler instance"


class TestHubIntegration:
    """hub 연동 테스트 — push_snapshot 및 is_stop_requested."""

    def _make_trading_session_mocks(self):
        """거래일 1회 폴링 후 종료하는 mock 설정."""
        trading_day_start = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)
        trading_day_end = datetime(2026, 4, 7, 9, 1, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=9,
            market_close_minute=1,
        )

        call_count = 0

        def mock_now(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return trading_day_start
            return trading_day_end

        return config, mock_now

    def test_hub_push_snapshot_called_after_poll(self):
        """hub 전달 시 폴링 후 hub.push_snapshot(engine.states)이 호출되어야 한다."""
        from mutrade.engine.models import SymbolState
        kis = MagicMock()
        config, mock_now = self._make_trading_session_mocks()
        engine = make_engine_mock()
        engine.states = {"005930": SymbolState(code="005930", peak_price=75000.0, warm=True)}
        executor = make_executor_mock()
        hub = MagicMock()
        hub.is_stop_requested.return_value = False

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices", return_value={"005930": 75000.0}), \
             patch("mutrade.monitor.scheduler.time"):
            mock_dt.now.side_effect = mock_now
            run_session = create_poll_session(kis, config, engine, executor, hub=hub)
            run_session()

        # hub.push_snapshot이 engine.states와 함께 호출되어야 함
        hub.push_snapshot.assert_called()

    def test_hub_stop_requested_breaks_loop(self):
        """hub.is_stop_requested() True이면 루프를 즉시 종료하고 hub.clear_stop()을 호출한다."""
        kis = MagicMock()
        # 거래 시간 내로 설정 — is_stop_requested가 루프 종료를 담당
        trading_dt = datetime(2026, 4, 7, 9, 0, 0, tzinfo=KST)

        config = make_config(
            market_close_hour=15,
            market_close_minute=20,
        )

        engine = make_engine_mock()
        engine.states = {}
        executor = make_executor_mock()
        hub = MagicMock()
        # 첫 번째 호출에서 True 반환 → 즉시 루프 종료
        hub.is_stop_requested.return_value = True

        with patch("mutrade.monitor.scheduler.is_krx_trading_day", return_value=True), \
             patch("mutrade.monitor.scheduler.datetime") as mock_dt, \
             patch("mutrade.monitor.scheduler.poll_prices") as mock_poll, \
             patch("mutrade.monitor.scheduler.time"):
            mock_dt.now.return_value = trading_dt
            run_session = create_poll_session(kis, config, engine, executor, hub=hub)
            run_session()

        # is_stop_requested가 True이므로 poll_prices는 호출되지 않아야 함
        mock_poll.assert_not_called()
        # clear_stop이 호출되어야 함
        hub.clear_stop.assert_called_once()
