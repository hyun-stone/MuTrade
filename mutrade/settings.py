"""
Settings — pydantic-settings 기반 환경변수 검증 클래스

.env 파일 또는 환경변수에서 KIS API 자격증명을 로드하고
시작 시 누락 필드를 ValidationError로 잡아준다.

D-03 결정: KIS_MOCK=true/false 로 모의투자 / 실계좌 전환.
모의투자 모드에서는 별도의 가상 계좌 자격증명이 필수다.
"""
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # 실전 계좌 자격증명 (항상 필수)
    kis_id: str = Field(..., alias="KIS_ID")
    kis_account: str = Field(..., alias="KIS_ACCOUNT")
    kis_appkey: str = Field(..., alias="KIS_APPKEY")
    kis_secretkey: str = Field(..., alias="KIS_SECRETKEY")

    # 가상 계좌 자격증명 (KIS_MOCK=true 일 때 필수)
    kis_virtual_id: str | None = Field(None, alias="KIS_VIRTUAL_ID")
    kis_virtual_account: str | None = Field(None, alias="KIS_VIRTUAL_ACCOUNT")
    kis_virtual_appkey: str | None = Field(None, alias="KIS_VIRTUAL_APPKEY")
    kis_virtual_secretkey: str | None = Field(None, alias="KIS_VIRTUAL_SECRETKEY")

    # 모의투자 모드 토글 (D-03)
    kis_mock: bool = Field(False, alias="KIS_MOCK")

    @model_validator(mode="after")
    def validate_virtual_credentials(self) -> "Settings":
        """KIS_MOCK=true 일 때 가상 계좌 자격증명이 모두 존재하는지 검증."""
        if self.kis_mock:
            missing = []
            if not self.kis_virtual_id:
                missing.append("KIS_VIRTUAL_ID")
            if not self.kis_virtual_account:
                missing.append("KIS_VIRTUAL_ACCOUNT")
            if not self.kis_virtual_appkey:
                missing.append("KIS_VIRTUAL_APPKEY")
            if not self.kis_virtual_secretkey:
                missing.append("KIS_VIRTUAL_SECRETKEY")
            if missing:
                raise ValueError(
                    f"KIS_MOCK=true requires virtual credentials: {', '.join(missing)}"
                )
        return self
