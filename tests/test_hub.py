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
        """Test 2: attach_loop() 후 push_snapshot() 시 call_soon_threadsafe 호출 검증.

        INFRA-02 이후: call_soon_threadsafe의 첫 번째 인자는 _put_snapshot bound method.
        """
        hub = self._make_hub()
        mock_loop = MagicMock()
        hub.attach_loop(mock_loop)

        states = {"005930": {"code": "005930", "peak_price": 75000.0, "warm": True}}
        hub.push_snapshot(states)

        # call_soon_threadsafe가 호출되었는지 검증
        mock_loop.call_soon_threadsafe.assert_called_once()
        call_args = mock_loop.call_soon_threadsafe.call_args
        # 첫 번째 인자는 _put_snapshot bound method
        first_arg = call_args[0][0]
        assert callable(first_arg)
        assert getattr(first_arg, '__name__', None) == '_put_snapshot'

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


class TestBotStateHubPhase6:
    """Phase 6 — push_snapshot 시그니처 확장 및 QueueFull 수정 TDD 테스트."""

    def _make_hub(self):
        from mutrade.admin.hub import BotStateHub
        return BotStateHub()

    def _make_fake_state(self, code="005930", peak=86200.0):
        class FakeState:
            def __init__(self, code, peak):
                self.code = code
                self.peak_price = peak
                self.warm = True
        return FakeState(code, peak)

    def test_push_snapshot_extended_signature_accepted(self):
        """INFRA-01: push_snapshot(states, prices, pending_codes) 시그니처가 예외 없이 동작."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state()}
        prices = {"005930": 84500.0}
        pending = frozenset({"005930"})
        # 새 시그니처로 호출 가능해야 함
        hub.push_snapshot(states, prices, pending)

    def test_get_snapshot_contains_current_price(self):
        """INFRA-01: get_snapshot() 반환값에 current_price 필드 포함."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state(peak=86200.0)}
        prices = {"005930": 84500.0}
        hub.push_snapshot(states, prices)
        snap = hub.get_snapshot()
        assert "current_price" in snap["005930"], f"current_price 없음: {snap}"
        assert snap["005930"]["current_price"] == 84500.0

    def test_get_snapshot_contains_drop_pct(self):
        """INFRA-01: get_snapshot() 반환값에 drop_pct 필드 포함 및 값 정확성."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state(peak=86200.0)}
        prices = {"005930": 84500.0}
        hub.push_snapshot(states, prices)
        snap = hub.get_snapshot()
        assert "drop_pct" in snap["005930"], f"drop_pct 없음: {snap}"
        expected = round(((84500.0 - 86200.0) / 86200.0) * 100, 2)
        assert snap["005930"]["drop_pct"] == expected, (
            f"drop_pct 불일치: {snap['005930']['drop_pct']} != {expected}"
        )

    def test_get_snapshot_contains_sell_pending_true(self):
        """INFRA-01: pending_codes에 해당 코드 포함 시 sell_pending=True."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state()}
        prices = {"005930": 84500.0}
        pending = frozenset({"005930"})
        hub.push_snapshot(states, prices, pending)
        snap = hub.get_snapshot()
        assert "sell_pending" in snap["005930"], f"sell_pending 없음: {snap}"
        assert snap["005930"]["sell_pending"] is True

    def test_get_snapshot_sell_pending_false_when_not_in_pending(self):
        """INFRA-01: pending_codes에 해당 코드 없으면 sell_pending=False."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state()}
        prices = {"005930": 84500.0}
        pending = frozenset()  # 빈 집합
        hub.push_snapshot(states, prices, pending)
        snap = hub.get_snapshot()
        assert snap["005930"]["sell_pending"] is False

    def test_backward_compat_prices_none(self):
        """INFRA-01: prices=None 생략 시 current_price=0.0, drop_pct=0.0 하위 호환."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state()}
        hub.push_snapshot(states)  # prices, pending_codes 생략
        snap = hub.get_snapshot()
        assert snap["005930"]["current_price"] == 0.0
        assert snap["005930"]["drop_pct"] == 0.0
        assert snap["005930"]["sell_pending"] is False

    def test_drop_pct_zero_when_peak_is_zero(self):
        """INFRA-01: peak=0 이면 ZeroDivisionError 없이 drop_pct=0.0."""
        hub = self._make_hub()
        states = {"005930": self._make_fake_state(peak=0.0)}
        prices = {"005930": 84500.0}
        hub.push_snapshot(states, prices)
        snap = hub.get_snapshot()
        assert snap["005930"]["drop_pct"] == 0.0

    def test_queue_full_no_exception(self):
        """INFRA-02: 루프 연결 후 연속 push_snapshot 2회 시 QueueFull 예외 없음."""
        import time
        hub = self._make_hub()
        loop = asyncio.new_event_loop()
        t = threading.Thread(target=loop.run_forever, daemon=True)
        t.start()
        hub.attach_loop(loop)

        states = {"005930": self._make_fake_state()}
        prices = {"005930": 84500.0}
        pending = frozenset({"005930"})

        # Queue(maxsize=1) — 2회 연속 push 시 QueueFull이 발생하면 안 됨
        hub.push_snapshot(states, prices, pending)
        hub.push_snapshot(states, prices, pending)  # 두 번째 — 기존 항목 드롭 후 삽입

        time.sleep(0.05)  # 비동기 처리 대기
        snap = hub.get_snapshot()
        assert "005930" in snap, f"스냅샷 비어있음: {snap}"

        loop.call_soon_threadsafe(loop.stop)

    def test_put_snapshot_method_used(self):
        """INFRA-02: call_soon_threadsafe 대상이 _put_snapshot 메서드임을 확인."""
        from mutrade.admin.hub import BotStateHub
        hub = BotStateHub()
        mock_loop = MagicMock()
        hub.attach_loop(mock_loop)

        states = {"005930": self._make_fake_state()}
        hub.push_snapshot(states)

        mock_loop.call_soon_threadsafe.assert_called_once()
        call_args = mock_loop.call_soon_threadsafe.call_args
        # 첫 번째 인자는 _put_snapshot 메서드여야 함
        first_arg = call_args[0][0]
        assert callable(first_arg), "첫 번째 인자가 callable이어야 함"
        assert hasattr(first_arg, '__func__') or hasattr(first_arg, '__self__'), (
            f"bound method여야 함: {first_arg}"
        )


class TestBotStateHubPhase7:
    """Phase 7 — push_snapshot dry_run 인자 및 _meta 최상위 필드 TDD 테스트."""

    def _make_hub(self):
        from mutrade.admin.hub import BotStateHub
        return BotStateHub()

    def _make_states(self):
        from mutrade.engine.models import SymbolState
        return {"005930": SymbolState(code="005930", peak_price=86200.0, warm=True)}

    def test_push_snapshot_with_dry_run_true(self):
        """dry_run=True 로 push_snapshot() 호출 시 _meta.dry_run이 True."""
        hub = self._make_hub()
        states = self._make_states()
        hub.push_snapshot(states, dry_run=True)
        snap = hub.get_snapshot()
        assert "_meta" in snap, f"_meta 키 없음: {snap}"
        assert snap["_meta"]["dry_run"] is True, f"dry_run 불일치: {snap['_meta']}"

    def test_push_snapshot_with_dry_run_false(self):
        """dry_run=False 로 push_snapshot() 호출 시 _meta.dry_run이 False."""
        hub = self._make_hub()
        states = self._make_states()
        hub.push_snapshot(states, dry_run=False)
        snap = hub.get_snapshot()
        assert "_meta" in snap, f"_meta 키 없음: {snap}"
        assert snap["_meta"]["dry_run"] is False, f"dry_run 불일치: {snap['_meta']}"

    def test_push_snapshot_dry_run_default_false(self):
        """dry_run 인자 없이 push_snapshot() 호출 시 _meta.dry_run이 False (하위 호환)."""
        hub = self._make_hub()
        states = self._make_states()
        hub.push_snapshot(states)  # dry_run 생략
        snap = hub.get_snapshot()
        assert "_meta" in snap, f"_meta 키 없음: {snap}"
        assert snap["_meta"]["dry_run"] is False, f"기본값 False 기대: {snap['_meta']}"

    def test_meta_contains_is_running(self):
        """set_running(True) 후 push_snapshot() 시 _meta.is_running이 True."""
        hub = self._make_hub()
        hub.set_running(True)
        states = self._make_states()
        hub.push_snapshot(states)
        snap = hub.get_snapshot()
        assert "_meta" in snap, f"_meta 키 없음: {snap}"
        assert snap["_meta"]["is_running"] is True, f"is_running 불일치: {snap['_meta']}"
