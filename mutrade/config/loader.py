"""
config.toml 로더

config.toml 파일을 파싱하여 타입이 명시된 데이터클래스로 반환한다.
Python 3.11+ 표준 라이브러리 tomllib 사용 (외부 의존성 없음).

스키마:
  [general]           — 전역 설정 (poll_interval, default_threshold, 시장 시간)
  [[symbols]]         — 모니터링 종목 목록 (code, name, threshold 선택적)
"""
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class SymbolConfig:
    """개별 종목 설정."""
    code: str           # 종목 코드 (예: "005930" — 삼성전자)
    name: str           # 종목명 (예: "삼성전자")
    threshold: float    # 트레일링 스탑 하락률 임계값 (예: 0.10 = 10%)


@dataclass(frozen=True)
class AppConfig:
    """애플리케이션 전역 설정."""
    poll_interval: float          # 가격 조회 간격 (초, 3~5 권장)
    default_threshold: float      # 종목별 기본 트레일링 스탑 임계값
    symbols: list[SymbolConfig]
    market_open_hour: int = 9
    market_open_minute: int = 0
    market_close_hour: int = 15
    market_close_minute: int = 20


def load_config(path: str | Path = "config.toml") -> AppConfig:
    """
    config.toml 을 파싱하여 AppConfig 를 반환한다.

    Args:
        path: config.toml 파일 경로 (기본값: "config.toml")

    Returns:
        AppConfig 인스턴스

    Raises:
        KeyError: [general] 섹션이 없을 때
        ValueError: [[symbols]] 가 비어 있을 때
        FileNotFoundError: 파일이 존재하지 않을 때
    """
    with open(path, "rb") as f:
        data = tomllib.load(f)

    general = data["general"]  # KeyError if missing
    default_threshold = general.get("default_threshold", 0.10)
    poll_interval = general.get("poll_interval", 3.0)

    raw_symbols = data.get("symbols", [])
    if not raw_symbols:
        raise ValueError("config.toml must contain at least one [[symbols]] entry")

    symbols = [
        SymbolConfig(
            code=s["code"],
            name=s["name"],
            threshold=s.get("threshold", default_threshold),
        )
        for s in raw_symbols
    ]

    return AppConfig(
        poll_interval=poll_interval,
        default_threshold=default_threshold,
        symbols=symbols,
        market_open_hour=general.get("market_open_hour", 9),
        market_open_minute=general.get("market_open_minute", 0),
        market_close_hour=general.get("market_close_hour", 15),
        market_close_minute=general.get("market_close_minute", 20),
    )
