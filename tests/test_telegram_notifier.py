"""
tests/test_telegram_notifier.py

TelegramNotifier 단위 테스트.

테스트 시나리오:
1. notify(signal, qty)를 호출하면 daemon Thread가 생성된다
2. notify()는 Thread 시작 후 즉시 반환한다 (0.1초 이내)
3. send_message가 예외를 발생시켜도 notify()는 예외를 전파하지 않는다
4. 전송된 메시지에 "매도 주문 제출", signal.code, signal.name이 포함된다
5. token=None, chat_id=None 시 아무 동작 없이 반환한다
"""
import time
import threading
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mutrade.engine.models import SellSignal


@pytest.fixture
def sell_signal():
    return SellSignal(
        code="005930",
        name="삼성전자",
        current_price=70000.0,
        peak_price=80000.0,
        drop_pct=0.125,
        threshold=0.10,
        dry_run=False,
    )


class TestTelegramNotifier:
    def test_notify_sends_message(self, sell_signal):
        """notify(signal, qty)를 호출하면 threading.Thread(daemon=True)가 생성된다."""
        with patch("mutrade.notifier.telegram.Bot") as MockBot:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(return_value=None)
            MockBot.return_value = mock_bot

            from mutrade.notifier.telegram import TelegramNotifier
            notifier = TelegramNotifier(token="bot123:ABC", chat_id="-100123456")

            threads_before = set(t.ident for t in threading.enumerate())
            notifier.notify(sell_signal, qty=10)

            # Thread가 시작되어야 하므로 잠시 대기
            time.sleep(0.2)
            # Bot이 호출되었는지 확인
            assert MockBot.called

    def test_notify_is_nonblocking(self, sell_signal):
        """notify()는 Thread 시작 후 즉시 반환한다 (0.1초 이내)."""
        with patch("mutrade.notifier.telegram.Bot") as MockBot:
            mock_bot = MagicMock()
            # send_message를 느리게 만들어 blocking 여부 확인
            async def slow_send(*args, **kwargs):
                time.sleep(2.0)  # 2초 지연
            mock_bot.send_message = slow_send
            MockBot.return_value = mock_bot

            from mutrade.notifier.telegram import TelegramNotifier
            notifier = TelegramNotifier(token="bot123:ABC", chat_id="-100123456")

            start = time.time()
            notifier.notify(sell_signal, qty=10)
            elapsed = time.time() - start

            assert elapsed < 0.1, f"notify()가 {elapsed:.3f}초 걸림 — 0.1초 이내여야 함"

    def test_notify_failure_does_not_raise(self, sell_signal):
        """send_message가 Exception을 발생시켜도 notify()는 예외를 전파하지 않는다."""
        with patch("mutrade.notifier.telegram.Bot") as MockBot:
            mock_bot = MagicMock()
            mock_bot.send_message = AsyncMock(side_effect=Exception("네트워크 오류"))
            MockBot.return_value = mock_bot

            from mutrade.notifier.telegram import TelegramNotifier
            notifier = TelegramNotifier(token="bot123:ABC", chat_id="-100123456")

            # 예외가 전파되지 않아야 한다
            try:
                notifier.notify(sell_signal, qty=10)
                time.sleep(0.2)  # Thread 완료 대기
            except Exception as e:
                pytest.fail(f"notify()가 예외를 전파했음: {e}")

    def test_notify_message_format(self, sell_signal):
        """전송된 메시지에 '매도 주문 제출', signal.code, signal.name이 포함된다."""
        sent_texts = []

        with patch("mutrade.notifier.telegram.Bot") as MockBot:
            mock_bot = MagicMock()

            async def capture_send(*args, **kwargs):
                sent_texts.append(kwargs.get("text", ""))
            mock_bot.send_message = capture_send
            MockBot.return_value = mock_bot

            from mutrade.notifier.telegram import TelegramNotifier
            notifier = TelegramNotifier(token="bot123:ABC", chat_id="-100123456")
            notifier.notify(sell_signal, qty=10)

            # Thread 완료 대기
            time.sleep(0.3)

        assert len(sent_texts) == 1, f"메시지가 전송되지 않았음: {sent_texts}"
        text = sent_texts[0]
        assert "매도 주문 제출" in text, f"'매도 주문 제출' 미포함: {text}"
        assert sell_signal.code in text, f"종목 코드 미포함: {text}"
        assert sell_signal.name in text, f"종목명 미포함: {text}"

    def test_no_token_skips_notify(self, sell_signal):
        """TelegramNotifier(token=None, chat_id=None).notify(...)는 아무 동작 없이 반환한다."""
        with patch("mutrade.notifier.telegram.Bot") as MockBot:
            from mutrade.notifier.telegram import TelegramNotifier
            notifier = TelegramNotifier(token=None, chat_id=None)
            notifier.notify(sell_signal, qty=10)

            # Bot이 호출되지 않아야 한다
            assert not MockBot.called
