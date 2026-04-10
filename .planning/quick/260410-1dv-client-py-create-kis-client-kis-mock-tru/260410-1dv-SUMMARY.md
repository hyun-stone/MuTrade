---
plan: 260410-1dv
status: complete
completed: 2026-04-10
tests: 80 passed
---

# Summary: 260410-1dv — client.py KIS_MOCK account 파라미터 수정

## What Was Done

`mutrade/kis/client.py`의 `create_kis_client()` KIS_MOCK=true 분기에서
`account=settings.kis_account` (실전 계좌번호)를
`account=settings.kis_virtual_account` (모의투자 계좌번호)로 수정.

## Root Cause

pykis 2.1.6에서 `account` 파라미터가 primary_account로 설정되며,
모의투자 엔드포인트(VTTC*)는 실전 계좌번호를 거부 → `INVALID_CHECK_ACNO` 오류 발생.

## Changes

| File | Change |
|------|--------|
| `mutrade/kis/client.py` | mock 분기 `account=settings.kis_account` → `account=settings.kis_virtual_account` |
| `tests/test_client.py` | 신규 생성 — mock/real 모드 account 파라미터 분기 검증 2개 테스트 |

## Verification

- 80 tests passed (78 기존 + 2 신규)
- mock=True: `PyKis(account=kis_virtual_account)` 호출 확인
- mock=False: `PyKis(account=kis_account)` 호출 유지 확인
