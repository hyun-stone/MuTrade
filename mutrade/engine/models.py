"""
mutrade/engine/models.py

트레일링 스탑 엔진 데이터 모델.

SymbolState: 종목별 고점 추적 상태 (mutable).
SellSignal: 매도 신호 (immutable).
"""
from dataclasses import dataclass, field


@dataclass
class SymbolState:
    """종목별 트레일링 스탑 추적 상태."""

    code: str          # 종목 코드 (예: "005930")
    peak_price: float  # 고점 (high-water mark)
    warm: bool = False # 첫 tick 이후 True (warm-up 완료 플래그)


@dataclass(frozen=True)
class SellSignal:
    """매도 신호 — 고점 대비 threshold 이상 하락 시 발생."""

    code: str               # 종목 코드
    name: str               # 종목명
    current_price: float    # 현재가
    peak_price: float       # 고점
    drop_pct: float         # 하락률 (0.10 = 10%)
    threshold: float        # 적용된 임계값
    dry_run: bool           # 드라이런 여부 (True이면 실제 주문 없음)
