---
phase: 01-foundation-and-kis-api-connectivity
plan: 02
subsystem: api
tags: [python-kis, pykis, apscheduler, loguru, exchange-calendars, rate-limiting, polling]

# Dependency graph
requires:
  - phase: 01-01-foundation-skeleton
    provides: "Settings, AppConfig/SymbolConfig, is_krx_trading_day — all consumed here"

provides:
  - "create_kis_client(): real/virtual mode PyKis 팩토리"
  - "poll_prices(): 15 req/s 레이트 리밋, KisAPIError 처리, 장 마감 시간 체크"
  - "create_poll_session() + start_scheduler(): APScheduler BlockingScheduler Mon-Fri KRX 거래일 폴링"
  - "mutrade/main.py: 봇 엔트리포인트 — settings, config, KIS client, scheduler 와이어링"

affects: [02-trailing-stop-engine, 03-order-execution]

# Tech tracking
tech-stack:
  added:
    - "python-kis 2.1.6 (PyKis, KisAPIError)"
    - "APScheduler 3.11.2 (BlockingScheduler, CronTrigger)"
    - "loguru 0.7.3 (console + file rotation)"
  patterns:
    - "KisAPIError는 rt_cd/msg_cd/msg1 속성 사용 (code/error_code/message 아님)"
    - "PyKis 가상계좌는 virtual=True 파라미터 아닌 virtual_id/virtual_appkey/virtual_secretkey kwargs"
    - "poll_prices(): 에러 종목 omit 패턴 — dict에 추가 안 함, price=0 전파 없음"
    - "datetime.now/time.sleep을 모듈 수준에서 임포트해 patch 가능하게 구성"

key-files:
  created:
    - mutrade/kis/__init__.py
    - mutrade/kis/client.py
    - mutrade/kis/price_feed.py
    - mutrade/monitor/scheduler.py
    - mutrade/main.py
    - tests/test_price_feed.py
    - tests/test_scheduler.py
  modified: []

key-decisions:
  - "PyKis 2.1.6의 실제 API는 virtual=True 파라미터 없음 — virtual_id/virtual_appkey/virtual_secretkey를 동시에 전달하면 가상 모드 활성화"
  - "KisAPIError 속성은 rt_cd/msg_cd/msg1 (속성 접근 시 getattr() 사용해 __new__ 생성 mock과도 호환)"
  - "poll_prices는 에러 종목을 결과 dict에서 omit — price=0 절대 전파 안 함"
  - "scheduler.py에서 datetime/time을 직접 임포트해 테스트에서 patch 가능하도록 설계"

patterns-established:
  - "KIS API 에러 처리 패턴: except KisAPIError → log → skip (no price=0)"
  - "레이트 리밋 패턴: time.sleep(MIN_INTERVAL) after each request"
  - "시장 마감 체크 패턴: now.hour*60+now.minute >= close_hour*60+close_minute"
  - "TDD 패턴: 테스트 먼저 작성 → ModuleNotFoundError 확인 → 구현 → green"

requirements-completed: [CONF-01, FEED-01, FEED-02, FEED-03, FEED-04]

# Metrics
duration: 4min
completed: 2026-04-07
---

# Phase 1 Plan 2: KIS API Client and Market-Hours Polling Summary

**PyKis 2.1.6 클라이언트 팩토리, 15 req/s 레이트 리밋 가격 폴링 루프(KisAPIError 방어 포함), APScheduler Mon-Fri KRX 거래일 스케줄러, loguru 봇 엔트리포인트 구현 완료 — 전체 테스트 23개 통과**

## Performance

- **Duration:** 4분
- **Started:** 2026-04-07T00:18:12Z
- **Completed:** 2026-04-07T00:22:00Z
- **Tasks:** 2 완료
- **Files modified:** 7 파일 생성

## Accomplishments

- `mutrade/kis/client.py`: `create_kis_client()` — KIS_MOCK 환경변수로 실전/가상계좌 자동 전환, keep_token=True 토큰 자동 갱신
- `mutrade/kis/price_feed.py`: `poll_prices()` — 15 req/s 레이트 리밋(MIN_INTERVAL=0.0667s), KisAPIError 발생 시 price=0 없이 해당 종목 제외, 장 마감 시간 즉시 중단
- `mutrade/monitor/scheduler.py`: `start_scheduler()` / `create_poll_session()` — APScheduler BlockingScheduler, Mon-Fri CronTrigger, is_krx_trading_day 공휴일 체크, 15:20 KST 루프 종료
- `mutrade/main.py`: 봇 엔트리포인트 — loguru 콘솔(INFO)+파일(DEBUG, 10MB 로테이션), 모든 컴포넌트 와이어링
- `tests/test_price_feed.py` + `tests/test_scheduler.py`: 11개 신규 테스트 (기존 12개 포함 전체 23개 green)

## Task Commits

각 태스크는 개별 커밋:

1. **Task 1: KIS client factory and price feed** - `bd433df` (feat)
2. **Task 2: APScheduler scheduling and main.py** - `3a0fba8` (feat)

## Files Created/Modified

- `mutrade/kis/__init__.py` — kis 패키지 초기화 (빈 파일)
- `mutrade/kis/client.py` — `create_kis_client()` 팩토리
- `mutrade/kis/price_feed.py` — `poll_prices()` 레이트 리밋 가격 피드
- `mutrade/monitor/scheduler.py` — `create_poll_session()` + `start_scheduler()`
- `mutrade/main.py` — 봇 엔트리포인트
- `tests/test_price_feed.py` — 7개 테스트
- `tests/test_scheduler.py` — 4개 테스트

## Decisions Made

- PyKis 2.1.6은 `virtual=True` 파라미터 없음 — `virtual_id`/`virtual_appkey`/`virtual_secretkey` 동시 전달로 가상 모드 활성화
- KisAPIError 로깅 시 `getattr(e, 'rt_cd', None)` 패턴 사용 — `__new__`로 생성된 테스트 mock에서도 안전하게 속성 접근 가능
- `datetime`과 `time`을 각 모듈에서 직접 임포트해 테스트 시 `patch("mutrade.kis.price_feed.datetime")` 방식으로 쉽게 교체 가능

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] PyKis virtual=True 파라미터 없음**
- **Found during:** Task 1 (KIS client factory)
- **Issue:** 플랜 코드가 `PyKis(virtual=True, ...)` 를 사용하지만 pykis 2.1.6에는 `virtual` 파라미터 없음
- **Fix:** `virtual_id`, `virtual_appkey`, `virtual_secretkey` kwargs를 전달하는 방식으로 변경 (pykis 실제 API에 맞춤)
- **Files modified:** `mutrade/kis/client.py`
- **Verification:** `test_mock_mode_uses_virtual_credentials` 테스트 통과
- **Committed in:** bd433df

**2. [Rule 1 - Bug] KisAPIError 로깅 속성 불일치**
- **Found during:** Task 1 (price feed 구현)
- **Issue:** 플랜 코드가 `e.rt_cd`, `e.msg_cd`, `e.msg1`를 직접 속성 접근하지만, `KisAPIError.__new__`로 생성된 mock에서 `code` 프로퍼티가 `self.rt_cd`를 요구해 AttributeError 발생
- **Fix:** `getattr(e, 'rt_cd', None)` 패턴으로 변경해 실제 KisAPIError와 mock 모두 안전하게 처리
- **Files modified:** `mutrade/kis/price_feed.py`
- **Verification:** `test_skips_symbol_on_kis_api_error` 테스트 통과
- **Committed in:** bd433df

---

**Total deviations:** 2 auto-fixed (Rule 1 - 라이브러리 실제 API와 플랜 코드 불일치 수정)
**Impact on plan:** 모두 pykis 2.1.6 실제 API에 맞춘 필수 수정. 기능 범위 변경 없음.

## Issues Encountered

- KisAPIError 테스트 mock 생성 시 `__new__`로 생성하면 `rt_cd` 속성이 없어 프로퍼티 접근 실패 → FakeKisAPIError 서브클래스로 해결

## User Setup Required

None - 이 플랜은 소스 코드 구현만 포함. 실행을 위한 `.env` 파일 설정은 01-01-SUMMARY에서 문서화됨.

## Next Phase Readiness

Phase 1 완료 조건 충족:
- KIS OAuth 클라이언트 초기화 + 토큰 자동 갱신
- 레이트 리밋 가격 피드 (KisAPIError 방어)
- APScheduler KRX 거래일 스케줄링
- main.py 엔트리포인트

Phase 2 (트레일링 스탑 엔진) 준비 상태:
- `poll_prices()` 반환 `dict[str, float]`를 트레일링 스탑 엔진에서 소비 가능
- `create_poll_session()` 내부에서 Phase 2 엔진 호출 위치 확보 (주석 "Phase 2 에서 트레일링 스탑 엔진이 prices 를 소비한다")

---
*Phase: 01-foundation-and-kis-api-connectivity*
*Completed: 2026-04-07*
