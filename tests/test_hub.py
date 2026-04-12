"""
tests/test_hub.py

BotStateHub 스레드 안전성 TDD 테스트.

TDD RED 단계에서 작성됨. mutrade/admin/hub.py 구현 전.
"""
import asyncio
import threading
import unittest
from unittest.mock import MagicMock, patch


class TestBotStateHub:
    """BotStateHub 스레드 안전성 테스트."""

    def _make_hub(self):
        from mutrade.admin.hub import BotStateHub
        return BotStateHub()

    def test_push_snapshot_without_loop_no_error(self):
        """Test 1: attach_loop() 전 push_snapshot() 호출 시 예외 없음 (방어 처리)."""
        hub = self._make_hub()
        states = {"005930": {"code": "005930", "peak_price": 75000.0, "warm": True}}
        # attach_loop() 없이 호출해도 예외 없어야 함
        hub.push_snapshot(states)

    def test_push_snapshot_after_attach_loop_calls_call_soon_threadsafe(self):
        """Test 2: attach_loop() 후 push_snapshot() 시 call_soon_threadsafe 호출 검증."""
        hub = self._make_hub()
        mock_loop = MagicMock()
        hub.attach_loop(mock_loop)

        states = {"005930": {"code": "005930", "peak_price": 75000.0, "warm": True}}
        hub.push_snapshot(states)

        # call_soon_threadsafe가 호출되었는지 검증
        mock_loop.call_soon_threadsafe.assert_called_once()
        call_args = mock_loop.call_soon_threadsafe.call_args
        # 첫 번째 인자는 queue.put_nowait
        assert call_args[0][0].__name__ == "put_nowait"

    def test_get_snapshot_returns_last_pushed_value(self):
        """Test 3: get_snapshot()은 push_snapshot()이 마지막으로 전달한 dict의 복사본 반환."""
        hub = self._make_hub()
        states = {"005930": {"code": "005930", "peak_price": 75000.0, "warm": True}}
        hub.push_snapshot(states)

        snapshot = hub.get_snapshot()
        assert "005930" in snapshot
        assert snapshot["005930"]["peak_price"] == 75000.0

    def test_request_stop_sets_flag(self):
        """Test 4: request_stop() 호출 후 is_stop_requested()가 True."""
        hub = self._make_hub()
        assert not hub.is_stop_requested()
        hub.request_stop()
        assert hub.is_stop_requested()

    def test_clear_stop_clears_flag(self):
        """Test 5: clear_stop() 호출 후 is_stop_requested()가 False."""
        hub = self._make_hub()
        hub.request_stop()
        assert hub.is_stop_requested()
        hub.clear_stop()
        assert not hub.is_stop_requested()

    def test_set_running_true(self):
        """Test 6: set_running(True) 후 is_running()이 True."""
        hub = self._make_hub()
        assert not hub.is_running()
        hub.set_running(True)
        assert hub.is_running()
        hub.set_running(False)
        assert not hub.is_running()

    def test_concurrent_push_and_get_no_race_condition(self):
        """Test 7: push_snapshot()과 get_snapshot()이 다른 스레드에서 동시 호출 시 경합 없음."""
        hub = self._make_hub()
        errors = []

        def pusher():
            for i in range(50):
                try:
                    hub.push_snapshot(
                        {"005930": {"code": "005930", "peak_price": float(i), "warm": True}}
                    )
                except Exception as e:
                    errors.append(e)

        def getter():
            for _ in range(50):
                try:
                    snap = hub.get_snapshot()
                    # 스냅샷이 dict여야 함
                    assert isinstance(snap, dict)
                except Exception as e:
                    errors.append(e)

        t1 = threading.Thread(target=pusher)
        t2 = threading.Thread(target=getter)
        t1.start()
        t2.start()
        t1.join()
        t2.join()

        assert errors == [], f"Race condition errors: {errors}"

    def test_push_snapshot_without_attach_loop_no_attribute_error(self):
        """Test 8: attach_loop 없이 push_snapshot() 시 AttributeError/RuntimeError 없음."""
        from mutrade.admin.hub import BotStateHub
        hub = BotStateHub()
        # loop=None 상태에서 push_snapshot 호출
        try:
            hub.push_snapshot({"000000": {"code": "000000", "peak_price": 0.0, "warm": False}})
        except (AttributeError, RuntimeError) as e:
            raise AssertionError(f"예외가 발생하면 안 됨: {e}")

    def test_get_snapshot_returns_copy_not_reference(self):
        """get_snapshot()이 참조가 아닌 복사본을 반환하는지 확인 (T-05-01 위협 방어)."""
        hub = self._make_hub()
        states = {"005930": {"code": "005930", "peak_price": 75000.0, "warm": True}}
        hub.push_snapshot(states)

        snap1 = hub.get_snapshot()
        snap1["new_key"] = "should_not_affect_internal"

        snap2 = hub.get_snapshot()
        assert "new_key" not in snap2, "get_snapshot()이 내부 상태 참조를 노출해서는 안 됨"

    def test_push_snapshot_serializes_dataclass_like_objects(self):
        """push_snapshot()이 dataclass-like 객체(SymbolState)를 직렬화하여 저장."""
        hub = self._make_hub()

        # SymbolState-like 객체 (dataclass 흉내)
        class FakeSymbolState:
            def __init__(self, code, peak_price, warm):
                self.code = code
                self.peak_price = peak_price
                self.warm = warm

        states = {
            "005930": FakeSymbolState("005930", 75000.0, True),
        }
        hub.push_snapshot(states)

        snap = hub.get_snapshot()
        assert "005930" in snap
        assert snap["005930"]["peak_price"] == 75000.0
        assert snap["005930"]["warm"] is True
