"""腾讯云认证基础。"""

from tencentcloud.common.credential import Credential

from config import settings


def get_tc_credential() -> Credential:
    return Credential(settings.tc_secret_id, settings.tc_secret_key)
