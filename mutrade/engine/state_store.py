"""
mutrade/engine/state_store.py

state.json 원자적 읽기/쓰기.

tempfile.mkstemp() + os.replace() 패턴으로 전원 차단에도 안전한 원자적 쓰기를 보장한다.

state.json 포맷:
{
  "005930": {"code": "005930", "peak_price": 76000.0, "warm": true},
  "000660": {"code": "000660", "peak_price": 190000.0, "warm": true}
}
"""
import json
import os
import tempfile
from pathlib import Path

from mutrade.engine.models import SymbolState


class StateStore:
    """종목별 고점 상태를 state.json에 원자적으로 저장/복원한다."""

    def __init__(self, path: str | Path = "state.json"):
        self._path = Path(path)

    def load(self) -> dict[str, SymbolState]:
        """
        state.json에서 고점 상태를 로드한다.

        Returns:
            종목 코드 → SymbolState dict.
            파일이 없으면 빈 dict 반환.
        """
        if not self._path.exists():
            return {}
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return {
            code: SymbolState(
                code=code,
                peak_price=v["peak_price"],
                warm=v.get("warm", True),  # 구버전 호환: warm 필드 없으면 True
            )
            for code, v in data.items()
        }

    def save(self, states: dict[str, SymbolState]) -> None:
        """
        고점 상태를 state.json에 원자적으로 저장한다.

        tempfile.mkstemp() → JSON 쓰기 → os.replace() 순으로
        전원 차단에도 파일 손상이 없는 원자적 교체를 보장한다.

        Args:
            states: 저장할 종목 코드 → SymbolState dict
        """
        data = {
            code: {
                "code": s.code,
                "peak_price": s.peak_price,
                "warm": s.warm,
            }
            for code, s in states.items()
        }

        # parent 디렉토리 생성 (없는 경우)
        self._path.parent.mkdir(parents=True, exist_ok=True)

        # 원자적 쓰기: tempfile → JSON → os.replace
        fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, suffix=".tmp"
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            os.replace(tmp_path, self._path)
        except BaseException:
            # 실패 시 임시 파일 정리
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise
