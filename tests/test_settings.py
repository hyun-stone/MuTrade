"""
Settings 클래스 테스트

테스트 시나리오:
1. 모든 필수 필드 존재 시 Settings 로드 성공
2. KIS_APPKEY 누락 시 ValidationError 발생
3. KIS_MOCK=true 에서 KIS_VIRTUAL_APPKEY 누락 시 ValidationError 발생
4. KIS_MOCK=false 에서는 가상 계좌 필드 불필요
"""
import os
import pytest
from pydantic import ValidationError


def _base_env():
    """실전 계좌 필수 필드만 포함한 최소 환경변수 딕셔너리."""
    return {
        "KIS_ID": "testuser",
        "KIS_ACCOUNT": "12345678-01",
        "KIS_APPKEY": "PStest123",
        "KIS_SECRETKEY": "RRtest456",
    }


def test_settings_loads_from_env(monkeypatch, tmp_path):
    """모든 필수 필드가 있을 때 Settings가 정상 로드되어야 한다."""
    env = _base_env()
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # .env 파일 없이도 환경변수에서 로드
    monkeypatch.setenv("KIS_MOCK", "false")

    from mutrade.settings import Settings

    s = Settings(_env_file=None)
    assert s.kis_appkey == "PStest123"
    assert s.kis_id == "testuser"
    assert s.kis_mock is False


def test_missing_appkey_raises_validation_error(monkeypatch):
    """KIS_APPKEY가 없으면 ValidationError가 발생해야 한다."""
    env = _base_env()
    env.pop("KIS_APPKEY")
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # 기존 환경변수 제거
    monkeypatch.delenv("KIS_APPKEY", raising=False)

    from mutrade.settings import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    # 오류 메시지에 필드 이름 포함 여부 확인
    errors = exc_info.value.errors()
    field_names = [e.get("loc", ("",))[0] for e in errors]
    assert any("kis_appkey" in str(n).lower() for n in field_names), (
        f"Expected 'kis_appkey' in error field names, got: {field_names}"
    )


def test_mock_mode_requires_virtual_appkey(monkeypatch):
    """KIS_MOCK=true 일 때 KIS_VIRTUAL_APPKEY 누락 시 ValidationError가 발생해야 한다."""
    env = _base_env()
    env["KIS_MOCK"] = "true"
    env["KIS_VIRTUAL_ID"] = "virtualuser"
    env["KIS_VIRTUAL_ACCOUNT"] = "99999999-01"
    # KIS_VIRTUAL_APPKEY 는 의도적으로 누락
    env["KIS_VIRTUAL_SECRETKEY"] = "VRtest789"
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("KIS_VIRTUAL_APPKEY", raising=False)

    from mutrade.settings import Settings

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    error_str = str(exc_info.value)
    assert "KIS_VIRTUAL_APPKEY" in error_str, (
        f"Expected 'KIS_VIRTUAL_APPKEY' in error message, got: {error_str}"
    )


def test_real_mode_does_not_require_virtual_fields(monkeypatch):
    """KIS_MOCK=false 일 때 가상 계좌 필드가 없어도 Settings가 로드되어야 한다."""
    env = _base_env()
    env["KIS_MOCK"] = "false"
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    # 가상 계좌 환경변수 제거
    for key in ["KIS_VIRTUAL_ID", "KIS_VIRTUAL_ACCOUNT", "KIS_VIRTUAL_APPKEY", "KIS_VIRTUAL_SECRETKEY"]:
        monkeypatch.delenv(key, raising=False)

    from mutrade.settings import Settings

    s = Settings(_env_file=None)
    assert s.kis_mock is False
    assert s.kis_virtual_appkey is None
