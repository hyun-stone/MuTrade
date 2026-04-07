"""
mutrade/notifier/telegram.py

Telegram 알림 전송기.

BlockingScheduler 단일 스레드를 차단하지 않기 위해
daemon Thread 내에서 asyncio.run()으로 Bot.send_message를 실행한다.
token/chat_id가 None이면 모든 notify() 호출을 무시한다 (D-01).

보안 주의: Bot 객체(token 포함)를 절대 로그에 출력하지 않는다 (T-04-01).
"""
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger
from telegram import Bot

from mutrade.engine.models import SellSignal

KST = ZoneInfo("Asia/Seoul")


class TelegramNotifier:
    """Telegram 알림 전송기.

    BlockingScheduler 단일 스레드를 차단하지 않기 위해
    daemon Thread 내에서 asyncio.run()으로 Bot.send_message를 실행한다.
    token/chat_id가 None이면 모든 notify() 호출을 무시한다 (D-01).
    """

    def __init__(self, token: str | None, chat_id: str | None) -> None:
        self._token = token
        self._chat_id = chat_id

    def notify(self, signal: SellSignal, qty: int) -> None:
        """매도 주문 제출 직후 Telegram 알림을 비동기 전송한다.

        daemon Thread에서 실행 — 메인 스레드 차단 없음 (NOTIF-02, D-02).
        전송 실패 시 logger.error()로 기록 후 무시 (D-02).
        token/chat_id 미설정 시 즉시 반환 (D-01).

        Args:
            signal: 매도 신호 (SellSignal 필드 전체 활용).
            qty: 실제 주문 수량.
        """
        if not self._token or not self._chat_id:
            return

        now_kst = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
        # D-04: 정확한 메시지 형식
        text = (
            f"🚨 매도 주문 제출\n"
            f"종목: {signal.name} ({signal.code})\n"
            f"수량: {qty}주 / 현재가: {signal.current_price:,.0f}원\n"
            f"고점: {signal.peak_price:,.0f}원 / 하락률: {signal.drop_pct:.2%}\n"
            f"임계값: {signal.threshold:.1%}\n"
            f"시간: {now_kst}"
        )

        def _send():
            try:
                bot = Bot(token=self._token)
                asyncio.run(bot.send_message(chat_id=self._chat_id, text=text))
            except Exception as e:
                # T-04-01: 토큰이 포함된 bot 객체 자체는 절대 로깅하지 않음 — e만 기록
                logger.error("Telegram 알림 전송 실패: {}", e)

        thread = threading.Thread(target=_send, daemon=True)
        thread.start()
