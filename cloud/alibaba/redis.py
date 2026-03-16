"""阿里云 Redis — 缓存实例管理。

SDK: alibabacloud-r-kvstore20150101
"""

import logging
import secrets
import string

from alibabacloud_r_kvstore20150101.client import Client as RedisClient
from alibabacloud_r_kvstore20150101.models import CreateInstanceRequest

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)

SPEC_MAP = {
    "1G": "redis.master.small.default",
    "2G": "redis.master.mid.default",
    "4G": "redis.master.stand.default",
    "8G": "redis.master.large.default",
    "16G": "redis.master.2xlarge.default",
}


def _get_client() -> RedisClient:
    config = get_ali_config()
    config.endpoint = f"r-kvstore.{settings.ali_region_id}.aliyuncs.com"
    return RedisClient(config)


async def create_redis_instance(name: str, spec: str | None = None) -> dict:
    """创建 Redis 实例。"""
    instance_class = SPEC_MAP.get(spec, "redis.master.stand.default") if spec else "redis.master.stand.default"
    password = "".join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))

    client = _get_client()

    request = CreateInstanceRequest(
        instance_name=name,
        instance_class=instance_class,
        instance_type="Redis",
        engine_version="7.0",
        charge_type="PostPaid",
        vpc_id=settings.ali_vpc_id,
        v_switch_id=settings.ali_vswitch_id,
        zone_id=f"{settings.ali_region_id}-b",
        password=password,
    )

    response = client.create_instance(request)
    instance_id = response.body.instance_id
    connection = response.body.connection_domain or f"{instance_id}.redis.rds.aliyuncs.com"

    logger.info("Redis instance created: id=%s name=%s", instance_id, name)

    return {
        "resource_id": instance_id,
        "connection_info": f"Host: {connection}\nPort: 6379\nPassword: {password}",
        "cost_estimate": None,
    }
