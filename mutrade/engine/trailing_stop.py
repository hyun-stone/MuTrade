"""
mutrade/engine/trailing_stop.py

트레일링 스탑 엔진 — 고점 추적 및 매도 신호 발생.

tick(prices) 호출마다:
1. 신규 종목: 첫 가격을 고점으로 설정 (warm=False)
2. warm=False 종목: warm-up — 안전장치로 매도 신호 없음, warm=True로 전환
3. warm=True 종목: 고점 갱신 및 하락률 계산, threshold 이상이면 SellSignal 반환

상태 저장: 고점이 갱신된 경우에만 StateStore.save() 호출 (매 tick마다 쓰지 않음).
"""
from loguru import logger

from mutrade.config.loader import SymbolConfig
from mutrade.engine.models import SellSignal, SymbolState
from mutrade.engine.state_store import StateStore


class TrailingStopEngine:
    """
    종목별 고점(high-water mark) 추적 및 트레일링 스탑 매도 신호 발생.

    Usage:
        store = StateStore("state.json")
        engine = TrailingStopEngine(symbols=config.symbols, store=store)
        signals = engine.tick(prices)  # prices: {code: float}
    """

    def __init__(
        self,
        symbols: list[SymbolConfig],
        store: StateStore,
        dry_run: bool = False,
    ):
        """
        Args:
            symbols: 모니터링 종목 목록 (config.toml에서 로드한 SymbolConfig)
            store: 고점 상태 저장소 (StateStore 인스턴스 또는 mock)
            dry_run: True이면 SellSignal.dry_run=True (실제 주문 없음)
        """
        self._symbols: dict[str, SymbolConfig] = {s.code: s for s in symbols}
        self._store = store
        self._dry_run = dry_run

        # state.json에서 로드 후 config 기준 필터링 (D-02)
        # config에 없는 종목은 무시, config에 있는 종목만 복원
        loaded = store.load()
        self._states: dict[str, SymbolState] = {
            code: loaded[code]
            for code in self._symbols
            if code in loaded
        }

    def tick(self, prices: dict[str, float]) -> list[SellSignal]:
        """
        가격 dict을 받아 트레일링 스탑 로직을 실행하고 매도 신호 목록을 반환한다.

        Args:
            prices: 종목 코드 → 현재가 dict (poll_prices()의 반환값)

        Returns:
            매도 신호 목록. threshold 이상 하락한 종목에 대해 SellSignal 발생.
            첫 tick(warm=False) 종목은 절대 포함되지 않음.
        """
        signals: list[SellSignal] = []
        peak_updated = False

        for code, price in prices.items():
            # config에 없는 종목은 건너뜀
            if code not in self._symbols:
                continue
            sym = self._symbols[code]

            if code not in self._states:
                # 신규 종목: 첫 가격을 고점으로 설정 (D-01)
                self._states[code] = SymbolState(
                    code=code, peak_price=price, warm=False
                )
                peak_updated = True
                logger.info(
                    "신규 종목 {} ({}): 초기 고점={:,.0f}",
                    code, sym.name, price,
                )
                continue

            state = self._states[code]

            if not state.warm:
                # warm-up 단계: 첫 tick 안전장치
                # 가격이 고점보다 높으면 고점 갱신
                if price > state.peak_price:
                    state.peak_price = price
                    peak_updated = True
                state.warm = True
                logger.debug(
                    "{} ({}) warm-up 완료: peak={:,.0f}",
                    code, sym.name, state.peak_price,
                )
                continue

            # warm=True: 정상 추적 모드
            # 고점 갱신 (신고점)
            if price > state.peak_price:
                state.peak_price = price
                peak_updated = True
                logger.debug(
                    "{} ({}) 새 고점: {:,.0f}",
                    code, sym.name, price,
                )

            # 하락률 계산
            if state.peak_price > 0:
                drop_pct = (state.peak_price - price) / state.peak_price
            else:
                drop_pct = 0.0

            # threshold 이상 하락 시 매도 신호 발생
            if drop_pct >= sym.threshold:
                signal = SellSignal(
                    code=code,
                    name=sym.name,
                    current_price=price,
                    peak_price=state.peak_price,
                    drop_pct=drop_pct,
                    threshold=sym.threshold,
                    dry_run=self._dry_run,
                )
                signals.append(signal)
                logger.warning(
                    "[{}] 매도 신호: {} ({}) 현재가={:,.0f} 고점={:,.0f} "
                    "하락률={:.1%} 임계값={:.1%}",
                    "DRY-RUN" if self._dry_run else "LIVE",
                    code, sym.name, price,
                    state.peak_price, drop_pct, sym.threshold,
                )

        # 고점이 갱신된 경우에만 저장 (상태 저장 빈도 제한)
        if peak_updated:
            self._store.save(self._states)

        return signals

    @property
    def states(self) -> dict[str, SymbolState]:
        """현재 종목별 상태 복사본 반환 (읽기 전용 뷰)."""
        return dict(self._states)
