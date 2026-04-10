"""
mutrade/notifier/telegram_listener.py

Telegram /status 명령 수신 리스너.

사용자가 Telegram 봇에 /status를 보내면 TrailingStopEngine의 현재 states를
순회하여 종목별 현재가(KIS API 조회), 고점, 하락률을 포맷된 메시지로 응답한다.

token/chat_id가 None이면 start() 호출 시 즉시 반환 (no-op). 스레드 미생성.

보안:
- T-quick-01: chat_id 검증 — 설정된 chat_id와 다른 사용자 요청은 무시
- T-04-01: bot 토큰을 절대 로그에 출력하지 않음
"""
import asyncio
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from loguru import logger

KST = ZoneInfo("Asia/Seoul")


def _build_status_message(
    states: dict,
    prices: dict,
    symbols: dict,
    dry_run: bool,
    kis_mock: bool,
) -> str:
    """종목별 현재가, 고점, 하락률을 포맷한 상태 메시지를 반환한다.

    순수 함수 — 외부 I/O 없음. 테스트 용이.

    Args:
        states: {code: SymbolState} — 엔진 상태 복사본
        prices: {code: float} — 현재가 dict (조회 실패 종목은 키 없음)
        symbols: {code: SymbolConfig} — 종목 설정
        dry_run: DRY_RUN 모드 여부
        kis_mock: 모의투자 모드 여부

    Returns:
        포맷된 상태 메시지 문자열
    """
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")
    lines = [f"📊 MuTrade 모니터링 현황 ({now_str})"]
    lines.append("")

    if not states:
        lines.append("모니터링 종목 없음")
    else:
        for code, state in states.items():
            sym = symbols.get(code)
            name = sym.name if sym else code

            current = prices.get(code)
            if current is None:
                lines.append(f"• {code} {name} / 현재가: 조회실패 | 고점: {state.peak_price:,.0f}원")
            else:
                peak = state.peak_price
                if peak > 0:
                    drop_pct = (peak - current) / peak * 100
                else:
                    drop_pct = 0.0
                lines.append(
                    f"• {code} {name} / "
                    f"현재가: {current:,.0f}원 | "
                    f"고점: {peak:,.0f}원 | "
                    f"하락률: -{drop_pct:.1f}%"
                )

    lines.append("")
    dry_run_label = "ON" if dry_run else "OFF"
    kis_mock_label = "ON" if kis_mock else "OFF"
    lines.append(f"DRY_RUN: {dry_run_label} | 모의투자: {kis_mock_label}")

    return "\n".join(lines)


class TelegramListener:
    """Telegram /status 명령 수신 리스너.

    daemon Thread에서 python-telegram-bot ApplicationBuilder를 실행하여
    /status 명령을 수신하고 응답한다.
    token/chat_id 미설정 시 start()가 no-op으로 스레드를 생성하지 않는다.
    """

    def __init__(self, token: str | None, chat_id: str | None) -> None:
        # T-04-01: 토큰을 repr/로그에 노출하지 않도록 repr=False 불가 (dataclass 아님)
        # — 절대 self._token을 logger에 출력하지 않을 것
        self._token = token
        self._chat_id = chat_id
        self._thread: threading.Thread | None = None
        self._app = None

    def start(
        self,
        engine,
        kis,
        symbols: dict,
        dry_run: bool,
        kis_mock: bool,
    ) -> None:
        """리스너를 daemon Thread에서 시작한다.

        token/chat_id 중 하나라도 없으면 즉시 반환 (no-op).

        Args:
            engine: TrailingStopEngine 인스턴스 (states 조회용)
            kis: PyKis 클라이언트 (현재가 조회용)
            symbols: {code: SymbolConfig} 딕셔너리
            dry_run: DRY_RUN 모드 여부
            kis_mock: 모의투자 모드 여부
        """
        if not self._token or not self._chat_id:
            return  # no-op

        self._engine = engine
        self._kis = kis
        self._symbols = symbols
        self._dry_run = dry_run
        self._kis_mock = kis_mock

        self._thread = threading.Thread(
            target=self._run_polling,
            daemon=True,
            name="TelegramListener",
        )
        self._thread.start()
        logger.debug("TelegramListener daemon thread started.")

    def _run_polling(self) -> None:
        """새 asyncio 이벤트 루프에서 Telegram Application polling을 실행한다."""
        try:
            from telegram.ext import ApplicationBuilder, CommandHandler

            async def run():
                app = ApplicationBuilder().token(self._token).build()
                self._app = app
                app.add_handler(CommandHandler("status", self._handle_status))
                await app.initialize()
                await app.start()
                await app.updater.start_polling()
                # polling은 stop() 호출 또는 프로세스 종료까지 지속
                # daemon thread이므로 메인 프로세스 종료 시 자동 정리
                while True:
                    await asyncio.sleep(3600)

            asyncio.run(run())
        except Exception as e:
            # T-04-01: self._token 절대 로깅 금지
            logger.error("TelegramListener polling 오류: {}", e)

    async def _handle_status(self, update, context) -> None:
        """Telegram /status 명령 핸들러.

        T-quick-01: chat_id 검증 — 설정된 chat_id 이외 사용자 요청은 무시.
        """
        effective_chat_id = str(update.effective_chat.id)
        if effective_chat_id != str(self._chat_id):
            logger.warning(
                "TelegramListener: 허가되지 않은 chat_id={} 의 /status 요청 무시.",
                effective_chat_id,
            )
            return

        # 현재 엔진 states 스냅샷
        states = self._engine.states if self._engine else {}

        # 각 종목 현재가 조회
        prices: dict[str, float] = {}
        for code in states:
            try:
                quote = self._kis.stock(code).quote()
                prices[code] = float(quote.price)
            except Exception as e:
                logger.warning("현재가 조회 실패 {}: {}", code, e)
                # prices에 키 없음 → _build_status_message에서 "조회실패" 표시

        msg = _build_status_message(
            states=states,
            prices=prices,
            symbols=self._symbols,
            dry_run=self._dry_run,
            kis_mock=self._kis_mock,
        )

        await update.message.reply_text(msg)

    def stop(self) -> None:
        """리스너를 정지한다 (best-effort). 로그만 남기고 예외는 무시."""
        if self._app is not None:
            try:
                # ApplicationBuilder app은 async stop 필요 — best-effort 시도
                asyncio.run(self._app.stop())
            except Exception as e:
                logger.debug("TelegramListener stop 중 무시된 오류: {}", e)
