"""
tests/test_state_store.py

TDD: StateStore 원자적 state.json 읽기/쓰기 테스트.

커버리지:
- save() 후 load() 시 동일한 dict[str, SymbolState] 반환
- state.json 없을 때 load()는 빈 dict 반환
- save()는 tempfile + os.replace 원자적 쓰기 사용
- save() 후 state.json 파일에 JSON이 정상 기록됨
"""
import json
import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from mutrade.engine.models import SymbolState
from mutrade.engine.state_store import StateStore


class TestStateStore:
    """StateStore 파일 읽기/쓰기 테스트."""

    def test_save_then_load_returns_same_states(self, tmp_path):
        """save() 후 load()하면 동일한 dict[str, SymbolState] 반환해야 한다."""
        path = tmp_path / "state.json"
        store = StateStore(path)

        states = {
            "005930": SymbolState(code="005930", peak_price=76000.0, warm=True),
            "000660": SymbolState(code="000660", peak_price=190000.0, warm=True),
        }

        store.save(states)
        loaded = store.load()

        assert len(loaded) == 2
        assert loaded["005930"].code == "005930"
        assert loaded["005930"].peak_price == 76000.0
        assert loaded["005930"].warm is True
        assert loaded["000660"].code == "000660"
        assert loaded["000660"].peak_price == 190000.0
        assert loaded["000660"].warm is True

    def test_load_returns_empty_dict_when_file_missing(self, tmp_path):
        """state.json 없을 때 load()는 빈 dict를 반환해야 한다."""
        path = tmp_path / "state.json"
        store = StateStore(path)

        result = store.load()

        assert result == {}

    def test_save_uses_atomic_write_with_os_replace(self, tmp_path):
        """save()는 tempfile + os.replace로 원자적 쓰기를 사용해야 한다."""
        import shutil
        path = tmp_path / "state.json"
        store = StateStore(path)

        states = {
            "005930": SymbolState(code="005930", peak_price=76000.0, warm=True),
        }

        # os.replace 대신 shutil.move를 참조로 저장하여 재귀를 방지
        with patch("mutrade.engine.state_store.os.replace", wraps=shutil.move) as mock_replace:
            store.save(states)

        mock_replace.assert_called_once()
        # dst(두 번째 인수)는 path 여야 함
        args = mock_replace.call_args.args
        assert str(args[1]) == str(path)

    def test_save_writes_valid_json_to_file(self, tmp_path):
        """save() 후 state.json 파일에 유효한 JSON이 기록되어야 한다."""
        path = tmp_path / "state.json"
        store = StateStore(path)

        states = {
            "005930": SymbolState(code="005930", peak_price=76000.0, warm=True),
        }

        store.save(states)

        assert path.exists()
        with open(path, "r") as f:
            data = json.load(f)

        assert "005930" in data
        assert data["005930"]["peak_price"] == 76000.0
        assert data["005930"]["warm"] is True

    def test_save_warm_false_preserved(self, tmp_path):
        """warm=False 상태도 정확히 저장/복원되어야 한다."""
        path = tmp_path / "state.json"
        store = StateStore(path)

        states = {
            "005930": SymbolState(code="005930", peak_price=50000.0, warm=False),
        }

        store.save(states)
        loaded = store.load()

        assert loaded["005930"].warm is False

    def test_load_handles_missing_warm_field_as_true(self, tmp_path):
        """warm 필드가 없는 구 버전 state.json은 warm=True로 읽어야 한다."""
        path = tmp_path / "state.json"
        # warm 필드 없이 직접 JSON 파일 생성
        data = {
            "005930": {"code": "005930", "peak_price": 76000.0}
        }
        with open(path, "w") as f:
            json.dump(data, f)

        store = StateStore(path)
        loaded = store.load()

        assert loaded["005930"].warm is True

    def test_save_creates_parent_directories(self, tmp_path):
        """parent 디렉토리가 없어도 save()가 디렉토리를 생성해야 한다."""
        path = tmp_path / "subdir" / "nested" / "state.json"
        store = StateStore(path)

        states = {
            "005930": SymbolState(code="005930", peak_price=76000.0, warm=True),
        }

        store.save(states)

        assert path.exists()
