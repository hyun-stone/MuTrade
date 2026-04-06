"""
config.toml 로더 테스트

테스트 시나리오:
1. [general] 과 [[symbols]] 가 있는 유효한 TOML → AppConfig + SymbolConfig 리스트 파싱
2. 커스텀 threshold 없는 종목 → [general].default_threshold (0.10) 적용
3. 커스텀 threshold 있는 종목 → 해당 값 적용
4. [[symbols]] 비어 있음 → ValueError 발생
5. [general] 섹션 없음 → KeyError 또는 ValueError 발생
"""
import pytest
import textwrap
from pathlib import Path

from mutrade.config.loader import load_config, AppConfig, SymbolConfig


def write_toml(tmp_path: Path, content: str) -> Path:
    """임시 TOML 파일을 작성하고 경로를 반환한다."""
    p = tmp_path / "config.toml"
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def test_valid_config_parses_into_appconfig(tmp_path):
    """유효한 TOML이 AppConfig와 SymbolConfig 리스트로 파싱되어야 한다."""
    toml = """
        [general]
        poll_interval = 3.0
        default_threshold = 0.10

        [[symbols]]
        code = "005930"
        name = "삼성전자"

        [[symbols]]
        code = "000660"
        name = "SK하이닉스"
        threshold = 0.08
    """
    path = write_toml(tmp_path, toml)
    cfg = load_config(path)

    assert isinstance(cfg, AppConfig)
    assert len(cfg.symbols) == 2
    assert isinstance(cfg.symbols[0], SymbolConfig)
    assert cfg.poll_interval == 3.0
    assert cfg.default_threshold == 0.10


def test_symbol_without_threshold_uses_default(tmp_path):
    """threshold 없는 종목은 default_threshold (0.10) 을 사용해야 한다."""
    toml = """
        [general]
        poll_interval = 3.0
        default_threshold = 0.10

        [[symbols]]
        code = "005930"
        name = "삼성전자"
    """
    path = write_toml(tmp_path, toml)
    cfg = load_config(path)

    samsung = cfg.symbols[0]
    assert samsung.code == "005930"
    assert samsung.threshold == 0.10


def test_symbol_with_custom_threshold_uses_its_own_value(tmp_path):
    """커스텀 threshold가 있는 종목은 해당 값을 사용해야 한다."""
    toml = """
        [general]
        poll_interval = 3.0
        default_threshold = 0.10

        [[symbols]]
        code = "000660"
        name = "SK하이닉스"
        threshold = 0.08
    """
    path = write_toml(tmp_path, toml)
    cfg = load_config(path)

    sk = cfg.symbols[0]
    assert sk.threshold == 0.08


def test_empty_symbols_raises_value_error(tmp_path):
    """[[symbols]] 가 비어 있으면 ValueError가 발생해야 한다."""
    toml = """
        [general]
        poll_interval = 3.0
        default_threshold = 0.10
    """
    path = write_toml(tmp_path, toml)

    with pytest.raises(ValueError, match="at least one"):
        load_config(path)


def test_missing_general_section_raises_error(tmp_path):
    """[general] 섹션이 없으면 KeyError 또는 ValueError가 발생해야 한다."""
    toml = """
        [[symbols]]
        code = "005930"
        name = "삼성전자"
    """
    path = write_toml(tmp_path, toml)

    with pytest.raises((KeyError, ValueError)):
        load_config(path)
