"""
mutrade/kis/client.py

PyKis 클라이언트 팩토리.

D-03 결정: KIS_MOCK=true/false 로 모의투자 / 실계좌 전환.
- kis_mock=False: 실전 계좌 자격증명만 사용
- kis_mock=True: 실전 + 가상 계좌 자격증명 모두 전달 (WebSocket 폴링에서
  virtual_appkey 존재 여부로 가상/실전 모드 판별)

keep_token=True: 24시간 만료되는 KIS OAuth 토큰을 파일에 캐시,
재시작 없이 자동 갱신한다.
"""
from pykis import PyKis
from loguru import logger

from mutrade.settings import Settings


def create_kis_client(settings: Settings) -> PyKis:
    """
    Settings 를 받아 PyKis 클라이언트를 생성한다.

    Args:
        settings: 환경변수에서 로드된 Settings 인스턴스

    Returns:
        초기화된 PyKis 인스턴스
    """
    if settings.kis_mock:
        logger.info("Initializing PyKis in VIRTUAL (mock) mode")
        return PyKis(
            id=settings.kis_id,
            account=settings.kis_account,
            appkey=settings.kis_appkey,
            secretkey=settings.kis_secretkey,
            virtual_id=settings.kis_virtual_id,
            virtual_appkey=settings.kis_virtual_appkey,
            virtual_secretkey=settings.kis_virtual_secretkey,
            keep_token=True,
        )
    else:
        logger.info("Initializing PyKis in REAL mode")
        return PyKis(
            id=settings.kis_id,
            account=settings.kis_account,
            appkey=settings.kis_appkey,
            secretkey=settings.kis_secretkey,
            keep_token=True,
        )
