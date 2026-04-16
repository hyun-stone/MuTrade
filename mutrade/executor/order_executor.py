"""
mutrade/executor/order_executor.py

매도 주문 실행기 — SellSignal을 KIS 시장가 매도 주문으로 전환.

핵심 흐름:
  1. SELL_PENDING 중복 확인 (EXEC-03)
  2. 매도 가능 수량 조회 — balance.stock(code).orderable (EXEC-02)
  3. 시장가 매도 주문 — account.sell(market="KRX", price=None) (EXEC-01)
  4. 체결 확인 — daily_orders().order(order) 폴링 (EXEC-04)
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

from loguru import logger
from pykis import PyKis, KisAPIError

from mutrade.engine.models import SellSignal

if TYPE_CHECKING:
    from mutrade.notifier.telegram import TelegramNotifier


class OrderExecutor:
    """KIS 시장가 매도 주문 실행기.

    SellSignal을 받아 수량 조회 → 주문 제출 → 체결 확인의 3단계를 처리.
    SELL_PENDING 플래그(내부 set)로 동일 종목 중복 주문 방지.
    """

    def __init__(
        self,
        kis: PyKis,
        dry_run: bool = False,
        notifier: "TelegramNotifier | None" = None,
    ):
        self._kis = kis
        self._dry_run = dry_run
        self._pending: set[str] = set()
        self._notifier = notifier

    def execute(self, signal: SellSignal) -> None:
        """SellSignal을 처리하여 KIS 매도 주문 제출 또는 dry-run 로그 출력.

        Args:
            signal: Phase 2 TrailingStopEngine이 생성한 매도 신호.
        """
        if signal.dry_run or self._dry_run:
            logger.info(
                "[DRY-RUN] 매도 주문 시뮬레이션: {} ({})",
                signal.code,
                signal.name,
            )
            return

        if signal.code in self._pending:
            logger.warning(
                "SELL_PENDING 중복 방지: {} — 이미 주문 진행 중",
                signal.code,
            )
            return

        self._pending.add(signal.code)
        try:
            self._submit_order(signal)
        except Exception as e:
            logger.error("주문 실패 {}: {}", signal.code, e)
            self._pending.discard(signal.code)

    def pending_codes(self) -> frozenset:
        """현재 SELL_PENDING 중인 종목 코드 집합. 스레드 안전 복사본."""
        return frozenset(self._pending)

    def _submit_order(self, signal: SellSignal) -> None:
        """잔고 조회 → 시장가 매도 주문 → 체결 확인.

        주문 불가(잔고 없음, orderable=0) 시 _pending 해제 후 반환.
        주문 성공 시 체결 확인(_confirm_fill) 호출.
        """
        acc = self._kis.account()
        balance = acc.balance("KR")
        stock = balance.stock(signal.code)

        if stock is None or stock.orderable <= 0:
            logger.warning(
                "매도 불가 {}: 잔고 없음 또는 orderable=0",
                signal.code,
            )
            self._pending.discard(signal.code)
            return

        qty = stock.orderable
        order = acc.sell(
            market="KRX",
            symbol=signal.code,
            price=None,
            qty=qty,
        )
        logger.warning(
            "[LIVE] 매도 주문 제출: {} ({}) qty={} 주문번호={}",
            signal.code,
            signal.name,
            qty,
            order.number,
        )
        # NOTIF-03: [TRADE] 마커로 거래 이력 기록 — grep "[TRADE]"로 추출 가능
        logger.info(
            "[TRADE] 매도 주문 제출: {} ({}) qty={} current_price={:,.0f} "
            "peak={:,.0f} drop={:.2%} threshold={:.1%} order={}",
            signal.code, signal.name, qty,
            signal.current_price, signal.peak_price,
            signal.drop_pct, signal.threshold,
            order.number,
        )
        # NOTIF-01: Telegram 알림 전송 (D-03: acc.sell() 직후, _confirm_fill() 전)
        if self._notifier is not None:
            self._notifier.notify(signal, qty)
        self._confirm_fill(acc, order, signal.code)

    def _confirm_fill(
        self,
        acc,
        order,
        symbol: str,
        max_attempts: int = 5,
        interval_sec: float = 3.0,
    ) -> None:
        """체결 여부를 daily_orders().order()로 폴링 확인.

        체결 확인 또는 타임아웃 후 반드시 _pending에서 symbol을 제거한다.

        Args:
            acc: KisAccount — daily_orders() 호출용.
            order: 주문 결과 (KisOrder) — daily.order()에 전달.
            symbol: 종목 코드 — _pending 해제 및 로그용.
            max_attempts: 최대 폴링 횟수 (기본 5회).
            interval_sec: 폴링 간격 초 (기본 3.0초).
        """
        for attempt in range(max_attempts):
            time.sleep(interval_sec)
            try:
                daily = acc.daily_orders()
                record = daily.order(order)
                if record is not None:
                    logger.info(
                        "체결 확인 {}: 체결수량={} 미체결수량={} 체결단가={}",
                        symbol,
                        record.executed_quantity,
                        record.pending_quantity,
                        record.price,
                    )
                    self._pending.discard(symbol)
                    return
            except KisAPIError as e:
                logger.warning(
                    "체결 확인 API 오류 (attempt {}): {}",
                    attempt + 1,
                    e,
                )

        logger.warning(
            "체결 확인 시간 초과: {} — SELL_PENDING 해제",
            symbol,
        )
        self._pending.discard(symbol)
