"""tests/test_client.py — create_kis_client() 단위 테스트"""
from unittest.mock import MagicMock, patch

from mutrade.kis.client import create_kis_client


def _make_settings(mock: bool) -> MagicMock:
    s = MagicMock()
    s.kis_mock = mock
    s.kis_id = "test_id"
    s.kis_account = "73345839"
    s.kis_appkey = "A" * 36
    s.kis_secretkey = "S" * 36
    s.kis_virtual_account = "12345678"
    s.kis_virtual_id = "virtual_id"
    s.kis_virtual_appkey = "V" * 36
    s.kis_virtual_secretkey = "VS" * 36
    return s


@patch("mutrade.kis.client.PyKis")
def test_mock_mode_uses_virtual_account(mock_pykis):
    """KIS_MOCK=true 시 account=kis_virtual_account 로 PyKis 초기화"""
    settings = _make_settings(mock=True)
    create_kis_client(settings)

    _, kwargs = mock_pykis.call_args
    assert kwargs["account"] == settings.kis_virtual_account


@patch("mutrade.kis.client.PyKis")
def test_real_mode_uses_real_account(mock_pykis):
    """KIS_MOCK=false 시 account=kis_account 로 PyKis 초기화"""
    settings = _make_settings(mock=False)
    create_kis_client(settings)

    _, kwargs = mock_pykis.call_args
    assert kwargs["account"] == settings.kis_account
