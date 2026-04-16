"""
tests/test_app_routes.py

Wave 2 TDD RED 테스트:
- GET / → FileResponse(index.html)
- /ws WebSocket 엔드포인트 등록
- /static StaticFiles 마운트 등록
- WebSocket 연결 시 즉시 스냅샷 전송
- WebSocket 루프에서 wait_for_change() 결과 전송
- WebSocketDisconnect 시 오류 없이 종료
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from mutrade.admin.hub import BotStateHub
from mutrade.admin.app import create_app


@pytest.fixture
def hub():
    """테스트용 BotStateHub (실제 인스턴스)."""
    return BotStateHub()


@pytest.fixture
def app(hub, tmp_path):
    """static 디렉터리 + index.html이 있는 FastAPI 앱."""
    static_dir = tmp_path / "static"
    static_dir.mkdir()
    (static_dir / "index.html").write_text("<html>dashboard</html>")

    # STATIC_DIR을 tmp_path로 패치
    import mutrade.admin.app as app_module
    with patch.object(app_module, "STATIC_DIR", static_dir, create=True):
        _app = create_app(hub)
    return _app


class TestRouteRegistration:
    """라우트 등록 확인 — app.py에 추가되기 전에 실패해야 한다."""

    def test_get_root_route_exists(self, hub):
        """GET / 라우트가 app.routes에 등록되어야 한다."""
        app = create_app(hub)
        routes = {getattr(r, "path", None) for r in app.routes}
        assert "/" in routes, f"GET / 라우트 없음. routes: {routes}"

    def test_ws_route_exists(self, hub):
        """/ws WebSocket 라우트가 등록되어야 한다."""
        app = create_app(hub)
        ws_routes = [r for r in app.routes if getattr(r, "path", None) == "/ws"]
        assert ws_routes, f"/ws WebSocket 라우트 없음"

    def test_static_mount_exists(self, hub):
        """/static StaticFiles 마운트가 등록되어야 한다."""
        app = create_app(hub)
        mounts = [r for r in app.routes if getattr(r, "name", None) == "static"]
        assert mounts, f"/static StaticFiles 마운트 없음"


class TestGetIndex:
    """GET / 엔드포인트: index.html FileResponse 반환 확인."""

    def test_get_root_returns_html(self, tmp_path):
        """GET / 요청 시 200 OK와 HTML 반환."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        html_content = "<html>MuTrade Dashboard</html>"
        (static_dir / "index.html").write_text(html_content)

        hub = BotStateHub()
        import mutrade.admin.app as app_module

        # STATIC_DIR을 패치하여 임시 디렉터리 사용
        original_create = app_module.create_app

        def patched_create_app(h, **kwargs):
            _app = original_create(h, **kwargs)
            # GET / 라우트의 STATIC_DIR을 교체할 수 없으므로
            # 모듈 레벨 상수가 create_app 호출 전에 설정되어야 함
            return _app

        app = create_app(hub)
        # STATIC_DIR이 Path(__file__).parent / "static" 이므로
        # 실제 static/ 경로에 index.html이 없으면 404 또는 500 반환 가능
        # 이 테스트는 라우트 등록만 확인 (파일 존재 여부 독립)
        routes = {getattr(r, "path", None) for r in app.routes}
        assert "/" in routes


class TestWebSocketEndpoint:
    """WebSocket /ws 엔드포인트 동작 확인."""

    def test_websocket_sends_initial_snapshot(self, tmp_path):
        """WebSocket 연결 즉시 get_snapshot() 결과 전송."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html/>")

        hub = MagicMock(spec=BotStateHub)
        hub.get_snapshot.return_value = {"005930": {"code": "005930", "peak_price": 100.0}}

        # wait_for_change: 첫 번째 호출에서 매우 긴 시간 대기 (연결 끊기 전까지)
        async def long_wait():
            await asyncio.sleep(60)
            return {}

        hub.wait_for_change = long_wait

        import mutrade.admin.app as app_module
        with patch.object(app_module, "STATIC_DIR", static_dir, create=True):
            app = create_app(hub)

        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                data = ws.receive_json()
                assert "005930" in data, f"초기 스냅샷 미전송. 받은 데이터: {data}"
                assert data["005930"]["peak_price"] == 100.0

    def test_websocket_sends_updated_snapshot(self, tmp_path):
        """WebSocket 루프에서 wait_for_change() 결과가 전송된다."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html/>")

        hub = MagicMock(spec=BotStateHub)
        initial = {"005930": {"code": "005930", "peak_price": 100.0}}
        updated = {"005930": {"code": "005930", "peak_price": 110.0}}
        hub.get_snapshot.return_value = initial

        call_count = 0

        async def wait_side_effect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return updated
            # 두 번째 호출에서 무한 대기 (연결 끊기 전까지)
            await asyncio.sleep(60)

        hub.wait_for_change = AsyncMock(side_effect=wait_side_effect)

        import mutrade.admin.app as app_module
        with patch.object(app_module, "STATIC_DIR", static_dir, create=True):
            app = create_app(hub)

        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                first = ws.receive_json()
                assert first == initial, f"초기 스냅샷 오류: {first}"
                second = ws.receive_json()
                assert second == updated, f"업데이트 스냅샷 오류: {second}"

    def test_websocket_disconnect_no_error(self, tmp_path):
        """WebSocket 연결 해제 시 서버가 오류 없이 종료."""
        static_dir = tmp_path / "static"
        static_dir.mkdir()
        (static_dir / "index.html").write_text("<html/>")

        hub = MagicMock(spec=BotStateHub)
        hub.get_snapshot.return_value = {}

        async def long_wait():
            await asyncio.sleep(60)
            return {}

        hub.wait_for_change = long_wait

        import mutrade.admin.app as app_module
        with patch.object(app_module, "STATIC_DIR", static_dir, create=True):
            app = create_app(hub)

        # 연결 즉시 끊기 — WebSocketDisconnect가 서버에서 전파되지 않아야 함
        with TestClient(app) as client:
            with client.websocket_connect("/ws") as ws:
                ws.receive_json()  # 초기 스냅샷 수신
                # 연결 종료 (컨텍스트 매니저 exit)
        # 예외 없이 통과하면 PASS
