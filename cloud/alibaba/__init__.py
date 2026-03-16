"""阿里云 API 客户端公共工具。"""

from alibabacloud_tea_openapi.models import Config

from config import settings


def get_ali_config(endpoint: str | None = None) -> Config:
    """获取阿里云 SDK 通用配置。"""
    config = Config(
        access_key_id=settings.ali_access_key_id,
        access_key_secret=settings.ali_access_key_secret,
        region_id=settings.ali_region_id,
    )
    if endpoint:
        config.endpoint = endpoint
    return config
