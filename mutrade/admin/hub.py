"""
mutrade/admin/hub.py

BotStateHub — APScheduler 스레드와 FastAPI asyncio 이벤트 루프 사이의 상태 브릿지.

설계 원칙:
- push_snapshot(): APScheduler 스레드에서 호출. loop.call_soon_threadsafe()로 asyncio.Queue에 삽입.
- get_snapshot(): asyncio 루프 또는 어느 스레드에서도 호출 가능. RLock으로 보호.
- stop_event: threading.Event — 스레드 안전 플래그. FastAPI → APScheduler 스레드 방향 제어.
"""
import asyncio
import threading
from typing import Optional


class BotStateHub:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._snapshot: dict = {}
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._change_queue: Optional[asyncio.Queue] = None
        self._stop_event = threading.Event()
        self._is_running: bool = False

    def attach_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """FastAPI lifespan startup에서 호출. asyncio 이벤트 루프와 Queue를 연결."""
        with self._lock:
            self._loop = loop
            self._change_queue = asyncio.Queue(maxsize=1)

    def push_snapshot(
        self,
        states: dict,
        prices: "dict[str, float] | None" = None,
        pending_codes: "frozenset[str] | None" = None,
    ) -> None:
        """
        APScheduler 스레드에서 호출. engine.states 딕셔너리를 직렬화하여 저장.
        attach_loop()가 호출된 경우 asyncio.Queue에도 push.

        Args:
            states: engine.states (SymbolState dict 또는 이미 직렬화된 dict)
            prices: 종목별 현재가 dict (scheduler.py에서 전달, 없으면 None)
            pending_codes: 현재 SELL_PENDING 중인 종목 코드 frozenset (없으면 None)
        """
        _prices = prices or {}
        _pending = pending_codes or frozenset()

        # SymbolState dataclass → plain dict 직렬화
        serialized: dict = {}
        for code, s in states.items():
            if hasattr(s, '__dataclass_fields__') or hasattr(s, 'peak_price'):
                peak = getattr(s, 'peak_price', 0.0)
                current = _prices.get(code, 0.0)
                # drop_pct: peak > 0 and current > 0 인 경우만 계산
                if peak > 0 and current > 0:
                    drop = round(((current - peak) / peak) * 100, 2)
                else:
                    drop = 0.0
                serialized[code] = {
                    "code": getattr(s, 'code', code),
                    "peak_price": peak,
                    "warm": getattr(s, 'warm', False),
                    "current_price": current,
                    "drop_pct": drop,
                    "sell_pending": code in _pending,
                }
            else:
                serialized[code] = s  # 이미 dict인 경우

        with self._lock:
            self._snapshot = serialized

        # asyncio.Queue에 삽입 (loop가 연결된 경우만)
        # call_soon_threadsafe: 스레드 안전 — asyncio 이벤트 루프 스레드에서 실행됨
        if self._loop is not None and self._change_queue is not None:
            try:
                self._loop.call_soon_threadsafe(
                    self._put_snapshot, dict(serialized)
                )
            except RuntimeError:
                # 루프가 닫힌 경우 (shutdown 중) — 무시
                pass

    def _put_snapshot(self, data: dict) -> None:
        """asyncio 이벤트 루프 스레드에서 실행 (call_soon_threadsafe 경유).

        INFRA-02: 큐가 full일 때 기존 항목을 드롭 후 새 항목 삽입.
        QueueFull 예외는 무시 (극히 드문 경합 방어).
        """
        assert self._change_queue is not None
        if self._change_queue.full():
            try:
                self._change_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
        try:
            self._change_queue.put_nowait(data)
        except asyncio.QueueFull:
            pass

    def get_snapshot(self) -> dict:
        """asyncio 루프에서 호출. 최신 스냅샷의 복사본 반환."""
        with self._lock:
            return dict(self._snapshot)

    async def wait_for_change(self) -> dict:
        """
        WebSocket 브로드캐스트 태스크에서 await.
        새 스냅샷이 push될 때까지 대기. asyncio 이벤트 루프에서만 호출 가능.
        attach_loop() 전에 호출되면 RuntimeError를 raise (개발 오용 방지).
        """
        if self._change_queue is None:
            raise RuntimeError(
                "BotStateHub.attach_loop()가 먼저 호출되어야 합니다."
            )
        return await self._change_queue.get()

    def request_stop(self) -> None:
        """FastAPI 엔드포인트에서 봇 폴링 중단 요청. threading.Event — 스레드 안전."""
        self._stop_event.set()

    def clear_stop(self) -> None:
        """중단 플래그 초기화. 봇 재시작 전 호출."""
        self._stop_event.clear()

    def is_stop_requested(self) -> bool:
        """APScheduler 스레드의 poll 루프에서 중단 요청 여부 확인."""
        return self._stop_event.is_set()

    def set_running(self, running: bool) -> None:
        """APScheduler 스레드가 세션 시작/종료 시 호출."""
        with self._lock:
            self._is_running = running

    def is_running(self) -> bool:
        """봇 실행 상태 조회. FastAPI 엔드포인트에서 호출."""
        with self._lock:
            return self._is_running
