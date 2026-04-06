"""
tests/test_engine.py

TDD: TrailingStopEngine 트레일링 스탑 로직 테스트.

커버리지:
- Test 1: 첫 tick — 새 종목의 가격이 고점으로 설정됨, SellSignal 없음
- Test 2: 가격 상승 tick — 고점이 새 가격으로 갱신됨
- Test 3: 가격 하락 (threshold 미만) — 고점 유지, SellSignal 없음
- Test 4: 가격 하락 (threshold 이상) — SellSignal 반환 (symbol, price, peak, drop_pct 포함)
- Test 5: 종목별 threshold — SymbolConfig.threshold=0.05인 종목이 5% 하락 시 SellSignal 발생
- Test 6: 재시작 복원 — StateStore에서 로드한 고점으로 초기화, 이전 고점 기준 추적
- Test 7: 첫 tick 안전장치 — 재시작 후 첫 tick에서 고점 아래 가격이어도 SellSignal 없음 (warm-up)
- Test 8: 두 번째 tick부터 매도 신호 — warm-up 이후 threshold 이상 하락 시 SellSignal 발생
- Test 9: config에 없는 종목은 state에서 무시 — load 시 config 기준 필터링
- Test 10: config에 신규 추가 종목 — state에 없으면 첫 가격으로 초기화
- Test 11: 고점 갱신 시 StateStore.save() 호출됨
- Test 12: 고점 갱신 없으면 StateStore.save() 호출 안 됨
- Test 13: 드라이런 모드에서 SellSignal.dry_run=True
"""
from unittest.mock import MagicMock

import pytest

from mutrade.config.loader import AppConfig, SymbolConfig
from mutrade.engine.models import SellSignal, SymbolState
from mutrade.engine.state_store import StateStore
from mutrade.engine.trailing_stop import TrailingStopEngine


# ─── 픽스처 헬퍼 ─────────────────────────────────────────────────────────────

def make_symbol(code: str, name: str, threshold: float = 0.10) -> SymbolConfig:
    return SymbolConfig(code=code, name=name, threshold=threshold)


def make_store(states: dict[str, SymbolState] | None = None) -> MagicMock:
    """StateStore MagicMock — load()는 states를 반환한다."""
    store = MagicMock(spec=StateStore)
    store.load.return_value = states or {}
    return store


def make_engine(
    symbols: list[SymbolConfig] | None = None,
    states: dict[str, SymbolState] | None = None,
    dry_run: bool = False,
) -> tuple[TrailingStopEngine, MagicMock]:
    """엔진과 store mock을 함께 반환한다."""
    if symbols is None:
        symbols = [make_symbol("005930", "삼성전자")]
    store = make_store(states)
    engine = TrailingStopEngine(symbols=symbols, store=store, dry_run=dry_run)
    return engine, store


# ─── 테스트 ───────────────────────────────────────────────────────────────────

class TestTrailingStopEngine:
    """TrailingStopEngine 핵심 로직 테스트."""

    def test_first_tick_sets_peak_no_sell_signal(self):
        """Test 1: 첫 tick — 새 종목의 가격이 고점으로 설정되고 SellSignal은 없어야 한다."""
        engine, store = make_engine()

        signals = engine.tick({"005930": 75000.0})

        assert signals == []
        # 고점이 설정됨
        assert engine.states["005930"].peak_price == 75000.0

    def test_price_rise_updates_peak(self):
        """Test 2: 가격 상승 tick — 고점이 새 가격으로 갱신되어야 한다."""
        engine, store = make_engine()

        engine.tick({"005930": 75000.0})  # 초기화 (warm=False)
        engine.tick({"005930": 80000.0})  # warm=True, 고점 갱신

        assert engine.states["005930"].peak_price == 80000.0

    def test_small_drop_no_sell_signal(self):
        """Test 3: 가격 하락 (threshold 미만) — SellSignal이 없어야 한다."""
        engine, store = make_engine(
            symbols=[make_symbol("005930", "삼성전자", threshold=0.10)]
        )

        engine.tick({"005930": 75000.0})  # 초기화 (warm=False)
        engine.tick({"005930": 75000.0})  # warm=True

        # 9% 하락 (threshold 10% 미만)
        drop_price = 75000.0 * (1 - 0.09)  # 68250
        signals = engine.tick({"005930": drop_price})

        assert signals == []
        assert engine.states["005930"].peak_price == 75000.0

    def test_large_drop_returns_sell_signal(self):
        """Test 4: 가격 하락 (threshold 이상) — SellSignal 반환."""
        engine, store = make_engine(
            symbols=[make_symbol("005930", "삼성전자", threshold=0.10)]
        )

        engine.tick({"005930": 75000.0})  # 초기화 (warm=False)
        engine.tick({"005930": 75000.0})  # warm=True

        # 정확히 10% 하락
        drop_price = 75000.0 * (1 - 0.10)  # 67500
        signals = engine.tick({"005930": drop_price})

        assert len(signals) == 1
        sig = signals[0]
        assert isinstance(sig, SellSignal)
        assert sig.code == "005930"
        assert sig.name == "삼성전자"
        assert sig.current_price == drop_price
        assert sig.peak_price == 75000.0
        assert sig.drop_pct == pytest.approx(0.10)
        assert sig.threshold == 0.10

    def test_per_symbol_threshold_triggers_earlier(self):
        """Test 5: 종목별 threshold=0.05 — 5% 하락 시 SellSignal이 발생해야 한다."""
        engine, store = make_engine(
            symbols=[make_symbol("005930", "삼성전자", threshold=0.05)]
        )

        engine.tick({"005930": 100000.0})  # 초기화 (warm=False)
        engine.tick({"005930": 100000.0})  # warm=True

        # 5% 하락
        drop_price = 100000.0 * (1 - 0.05)  # 95000
        signals = engine.tick({"005930": drop_price})

        assert len(signals) == 1
        assert signals[0].threshold == 0.05
        assert signals[0].drop_pct == pytest.approx(0.05)

    def test_restart_restores_peak_from_state(self):
        """Test 6: 재시작 복원 — StateStore에서 로드한 고점으로 초기화."""
        # state.json에 이전 고점이 있는 상황 시뮬레이션
        saved_states = {
            "005930": SymbolState(code="005930", peak_price=90000.0, warm=True),
        }
        engine, store = make_engine(states=saved_states)

        # 엔진이 이전 고점(90000)을 복원해야 함
        assert engine.states["005930"].peak_price == 90000.0

    def test_first_tick_after_restart_no_sell_signal(self):
        """Test 7: 재시작 후 첫 tick — warm=False 상태에서 SellSignal이 없어야 한다."""
        # state.json에 warm=False 상태로 저장된 종목 (재시작 직후)
        saved_states = {
            "005930": SymbolState(code="005930", peak_price=90000.0, warm=False),
        }
        engine, store = make_engine(states=saved_states)

        # 고점(90000) 대비 20% 하락한 가격이라도 첫 tick에서는 신호 없어야 함
        signals = engine.tick({"005930": 72000.0})  # -20% from peak

        assert signals == []

    def test_second_tick_after_restart_triggers_sell_signal(self):
        """Test 8: 두 번째 tick부터 매도 신호 — warm-up 이후 threshold 이상 하락 시 SellSignal."""
        saved_states = {
            "005930": SymbolState(code="005930", peak_price=100000.0, warm=False),
        }
        engine, store = make_engine(states=saved_states)

        # 첫 tick: warm-up (신호 없음)
        engine.tick({"005930": 100000.0})

        # 두 번째 tick: 10% 하락 → SellSignal 발생
        signals = engine.tick({"005930": 90000.0})

        assert len(signals) == 1

    def test_unknown_symbol_in_state_is_ignored(self):
        """Test 9: config에 없는 종목은 state에서 무시되어야 한다."""
        # state.json에 config에 없는 종목 포함
        saved_states = {
            "005930": SymbolState(code="005930", peak_price=76000.0, warm=True),
            "999999": SymbolState(code="999999", peak_price=50000.0, warm=True),  # config에 없음
        }
        engine, store = make_engine(
            symbols=[make_symbol("005930", "삼성전자")],
            states=saved_states,
        )

        # config에 없는 종목은 엔진 state에 없어야 함
        assert "999999" not in engine.states
        assert "005930" in engine.states

    def test_new_symbol_not_in_state_initializes_on_first_tick(self):
        """Test 10: config에 신규 추가 종목 — state에 없으면 첫 가격으로 초기화."""
        # state에 없는 종목이 config에 있는 경우
        engine, store = make_engine(
            symbols=[make_symbol("000660", "SK하이닉스")],
            states={},  # 빈 state
        )

        signals = engine.tick({"000660": 185000.0})

        assert signals == []
        assert engine.states["000660"].peak_price == 185000.0
        assert engine.states["000660"].warm is False

    def test_peak_update_triggers_store_save(self):
        """Test 11: 고점 갱신 시 StateStore.save()가 호출되어야 한다."""
        engine, store = make_engine()

        # 첫 tick (초기화) — peak_updated=True이므로 save 호출됨
        store.save.reset_mock()
        engine.tick({"005930": 75000.0})

        assert store.save.called

    def test_no_peak_update_no_store_save(self):
        """Test 12: 고점 갱신이 없으면 StateStore.save()가 호출되지 않아야 한다."""
        engine, store = make_engine(
            states={"005930": SymbolState(code="005930", peak_price=80000.0, warm=True)}
        )

        store.save.reset_mock()

        # 가격이 고점보다 낮으나 threshold 미만 (고점 갱신 없음)
        engine.tick({"005930": 75000.0})  # 80000 대비 6.25% 하락

        assert not store.save.called

    def test_dry_run_sell_signal_has_dry_run_true(self):
        """Test 13: 드라이런 모드에서 SellSignal.dry_run=True이어야 한다."""
        engine, store = make_engine(
            symbols=[make_symbol("005930", "삼성전자", threshold=0.10)],
            dry_run=True,
        )

        engine.tick({"005930": 100000.0})  # 초기화 (warm=False)
        engine.tick({"005930": 100000.0})  # warm=True

        # 10% 하락 → SellSignal (dry_run=True)
        signals = engine.tick({"005930": 90000.0})

        assert len(signals) == 1
        assert signals[0].dry_run is True

    def test_live_mode_sell_signal_has_dry_run_false(self):
        """라이브 모드에서 SellSignal.dry_run=False이어야 한다."""
        engine, store = make_engine(
            symbols=[make_symbol("005930", "삼성전자", threshold=0.10)],
            dry_run=False,
        )

        engine.tick({"005930": 100000.0})  # 초기화 (warm=False)
        engine.tick({"005930": 100000.0})  # warm=True

        signals = engine.tick({"005930": 90000.0})

        assert len(signals) == 1
        assert signals[0].dry_run is False

    def test_warm_flag_set_true_after_first_tick(self):
        """첫 tick 이후 warm=True로 갱신되어야 한다."""
        engine, store = make_engine()

        engine.tick({"005930": 75000.0})

        assert engine.states["005930"].warm is False  # 첫 tick → warm=False (신규 등록)
        engine.tick({"005930": 75000.0})  # 두 번째 tick
        assert engine.states["005930"].warm is True

    def test_multiple_symbols_independent_tracking(self):
        """여러 종목이 각각 독립적으로 고점을 추적해야 한다."""
        engine, store = make_engine(
            symbols=[
                make_symbol("005930", "삼성전자", threshold=0.10),
                make_symbol("000660", "SK하이닉스", threshold=0.10),
            ]
        )

        # 두 종목 초기화
        engine.tick({"005930": 75000.0, "000660": 185000.0})
        engine.tick({"005930": 75000.0, "000660": 185000.0})  # warm=True

        # 삼성전자만 10% 이상 하락
        signals = engine.tick({"005930": 67000.0, "000660": 185000.0})

        assert len(signals) == 1
        assert signals[0].code == "005930"
