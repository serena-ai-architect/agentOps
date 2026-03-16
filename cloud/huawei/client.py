"""华为云认证基础客户端。"""

from huaweicloudsdkcore.auth.credentials import BasicCredentials

from config import settings


def get_hw_credentials() -> BasicCredentials:
    return BasicCredentials(
        ak=settings.hw_access_key,
        sk=settings.hw_secret_key,
        project_id=settings.hw_project_id,
    )
