---
phase: 01-foundation-and-kis-api-connectivity
plan: "01"
subsystem: infra
tags: [python-kis, pydantic-settings, exchange-calendars, tomllib, pytest]

# Dependency graph
requires: []
provides:
  - "설치 가능한 Python 패키지 (pyproject.toml, setuptools)"
  - "pydantic-settings 기반 Settings 클래스 — .env 검증 + KIS_MOCK 모드 지원"
  - "tomllib 기반 config.toml 로더 — AppConfig/SymbolConfig 타입 데이터클래스"
  - "exchange_calendars XKRX 캘린더 기반 KRX 거래일 판정 함수"
  - "pytest 테스트 인프라 (12개 테스트 통과)"
affects:
  - "02-kis-client-and-price-feed"
  - "03-trailing-stop-engine"
  - "04-order-execution"

# Tech tracking
tech-stack:
  added:
    - "python-kis 2.1.6"
    - "pydantic-settings 2.13.1"
    - "python-dotenv 1.2.2"
    - "loguru 0.7.3"
    - "APScheduler 3.11.2"
    - "exchange-calendars 4.13.2"
    - "httpx 0.28.1"
    - "pytest + pytest-mock (dev)"
  patterns:
    - "pydantic-settings BaseSettings: 환경변수 → 타입화된 Python 객체"
    - "frozen dataclass: 불변 설정 객체 (AppConfig, SymbolConfig)"
    - "tomllib + dataclass: TOML 파일 → 타입 안전 설정"
    - "exchange_calendars 모듈 수준 캘린더 싱글톤 패턴"

key-files:
  created:
    - "pyproject.toml"
    - ".gitignore"
    - ".env.example"
    - "config.toml"
    - "logs/.gitkeep"
    - "mutrade/__init__.py"
    - "mutrade/settings.py"
    - "mutrade/config/__init__.py"
    - "mutrade/config/loader.py"
    - "mutrade/monitor/__init__.py"
    - "mutrade/monitor/holiday.py"
    - "tests/__init__.py"
    - "tests/test_settings.py"
    - "tests/test_config.py"
    - "tests/test_holiday.py"
  modified: []

key-decisions:
  - "python-kis 4.x 표기는 버전 체계 오류 — 실제 최신 버전 2.1.6 사용 (PyPI 확인)"
  - "setuptools.backends.legacy:build 대신 setuptools.build_meta 사용 (pip 호환성)"
  - "exchange_calendars로 KRX 공휴일 오프라인 판정 (httpx + KIS API 보다 신뢰성 높음)"
  - "Python 3.11 Homebrew 설치 — 로컬 3.9.6 대신 tomllib stdlib 지원 버전"

patterns-established:
  - "Settings(_env_file=None) 패턴: 테스트 시 .env 파일 없이 환경변수로만 로드"
  - "monkeypatch.setenv + monkeypatch.delenv: 환경변수 격리 테스트"
  - "tmp_path + write_text: 임시 TOML 파일 기반 config 테스트"
  - "frozen dataclass: 설정 객체는 불변으로 유지"

requirements-completed: [CONF-02, CONF-03, CONF-04]

# Metrics
duration: 5min
completed: "2026-04-06"
---

# Phase 1 Plan 1: Foundation and KIS API Connectivity Summary

**Python 3.11 패키지 스캐폴드 + pydantic-settings 환경변수 검증 + tomllib config.toml 로더 + exchange_calendars KRX 거래일 판정, 12개 테스트 통과**

## Performance

- **Duration:** 5 min
- **Started:** 2026-04-06T15:08:31Z
- **Completed:** 2026-04-06T15:13:29Z
- **Tasks:** 2
- **Files modified:** 15

## Accomplishments

- pydantic-settings BaseSettings로 .env 자격증명 타입 검증 — KIS_MOCK=true 시 가상 계좌 필드 존재 여부 자동 검증
- Python 3.11+ tomllib(stdlib)로 config.toml 파싱 — per-symbol threshold 및 기본값 fallback 지원
- exchange_calendars XKRX 캘린더로 KRX 공휴일/주말 오프라인 판정 — 외부 API 의존 없음
- pytest 테스트 인프라 구축 (12개 테스트: settings 4, config 5, holiday 3)

## Task Commits

각 태스크는 원자적으로 커밋됨:

1. **Task 1: Project skeleton, dependencies, Settings, .env validation** — `bd908dd` (feat)
2. **Task 2: config.toml loader and KRX holiday check** — `54452ea` (feat)

## Files Created/Modified

- `pyproject.toml` — 프로젝트 메타데이터, 의존성 (python-kis 2.1.6 등), pytest 설정
- `.gitignore` — .env, __pycache__, logs/*.log 등 제외
- `.env.example` — KIS API 자격증명 템플릿 (실전 + 가상 계좌)
- `config.toml` — 샘플 설정 (삼성전자, SK하이닉스, 기본 threshold 0.10)
- `mutrade/settings.py` — pydantic-settings BaseSettings, model_validator 기반 mock 모드 검증
- `mutrade/config/loader.py` — tomllib 파서, AppConfig/SymbolConfig frozen dataclass
- `mutrade/monitor/holiday.py` — exchange_calendars XKRX, is_krx_trading_day()
- `tests/test_settings.py` — 4개 Settings 테스트
- `tests/test_config.py` — 5개 config 로더 테스트
- `tests/test_holiday.py` — 3개 KRX 거래일 테스트

## Decisions Made

- **python-kis 버전:** CLAUDE.md의 "4.x" 표기는 버전 체계 오류로 확인. 실제 PyPI 최신 버전 2.1.6 사용.
- **빌드 백엔드:** `setuptools.backends.legacy:build` 가 pip 11+ 에서 동작하지 않음 → `setuptools.build_meta` 로 변경.
- **KRX 공휴일 판정:** exchange_calendars XKRX 오프라인 방식 채택 (httpx + KIS API 보다 외부 장애에 독립적).
- **Python 버전:** tomllib (stdlib) 사용을 위해 Homebrew Python 3.11.15 설치.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Build backend 수정**
- **Found during:** Task 1 (pip install -e ".[dev]")
- **Issue:** `setuptools.backends.legacy:build` 가 pip BackendUnavailable 오류 발생
- **Fix:** `setuptools.build_meta` 로 변경
- **Files modified:** `pyproject.toml`
- **Verification:** `pip install -e ".[dev]"` 성공
- **Committed in:** `bd908dd` (Task 1 커밋에 포함)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** 빌드 백엔드 수정은 pip 호환성을 위해 필수. 범위 변경 없음.

## Issues Encountered

- Python 3.9.6 (시스템 기본값)은 tomllib, python-kis 요구사항 미충족 → Homebrew Python 3.11.15 설치로 해결.

## User Setup Required

실제 실행 전 아래 설정 필요:
1. `.env.example` 을 `.env` 로 복사
2. KIS Developers 포털에서 발급한 실전/모의 계좌 AppKey, SecretKey 입력
3. `pip3.11 install -e ".[dev]"` 실행

## Next Phase Readiness

- Plan 02 (KIS 클라이언트 + 가격 피드)에서 `mutrade.settings.Settings` 와 `mutrade.config.loader.load_config` 를 임포트하여 바로 사용 가능
- `mutrade.monitor.holiday.is_krx_trading_day()` 는 APScheduler 스케줄링 판단에 사용 가능
- 테스트 인프라 준비 완료 — Plan 02 TDD 테스트 추가 가능

## Self-Check: PASSED

- FOUND: 모든 15개 파일 존재 확인
- FOUND: 커밋 bd908dd (Task 1), 54452ea (Task 2) 확인
- PASSED: `pytest tests/ -x -q` — 12 passed

---
*Phase: 01-foundation-and-kis-api-connectivity*
*Completed: 2026-04-06*
