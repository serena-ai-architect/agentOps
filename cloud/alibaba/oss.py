"""阿里云 OSS — 对象存储管理。

SDK: oss2
"""

import logging

import oss2

from config import settings

logger = logging.getLogger(__name__)


async def create_oss_bucket(name: str) -> dict:
    """创建 OSS Bucket。"""
    auth = oss2.Auth(settings.ali_access_key_id, settings.ali_access_key_secret)
    endpoint = f"https://oss-{settings.ali_region_id}.aliyuncs.com"

    bucket = oss2.Bucket(auth, endpoint, name)
    bucket.create_bucket(oss2.BUCKET_ACL_PRIVATE)

    logger.info("OSS bucket created: %s", name)

    return {
        "resource_id": name,
        "connection_info": (
            f"Bucket: {name}\n"
            f"Endpoint: oss-{settings.ali_region_id}.aliyuncs.com\n"
            f"内网: oss-{settings.ali_region_id}-internal.aliyuncs.com"
        ),
        "cost_estimate": None,
    }
