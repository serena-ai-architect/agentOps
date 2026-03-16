"""阿里云 ECS — 云服务器管理。

SDK: alibabacloud-ecs20140526
"""

import logging
import secrets
import string

from alibabacloud_ecs20140526.client import Client as EcsClient
from alibabacloud_ecs20140526.models import RunInstancesRequest

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)

SPEC_MAP = {
    "1核1G": "ecs.t6-c1m1.large",
    "1核2G": "ecs.t6-c1m2.large",
    "2核4G": "ecs.c6.large",
    "4核8G": "ecs.c6.xlarge",
    "8核16G": "ecs.c6.2xlarge",
    "16核32G": "ecs.c6.4xlarge",
}


def _get_client() -> EcsClient:
    config = get_ali_config()
    config.endpoint = f"ecs.{settings.ali_region_id}.aliyuncs.com"
    return EcsClient(config)


async def create_ecs_instance(name: str, spec: str | None = None) -> dict:
    """创建 ECS 云服务器。"""
    instance_type = SPEC_MAP.get(spec, "ecs.c6.large") if spec else "ecs.c6.large"
    password = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$") for _ in range(16))

    client = _get_client()

    request = RunInstancesRequest(
        instance_name=name,
        instance_type=instance_type,
        image_id="aliyun_3_x64_20G_alibase_20240819.vhd",  # Alibaba Cloud Linux 3
        system_disk_category="cloud_essd",
        system_disk_size="40",
        internet_max_bandwidth_out=0,
        vpc_id=settings.ali_vpc_id,
        v_switch_id=settings.ali_vswitch_id,
        security_group_id=settings.ali_security_group_id,
        amount=1,
        instance_charge_type="PostPaid",
        password=password,
    )

    response = client.run_instances(request)
    instance_ids = response.body.instance_id_sets.instance_id_set
    instance_id = instance_ids[0] if instance_ids else "unknown"

    logger.info("ECS instance created: id=%s name=%s type=%s", instance_id, name, instance_type)

    return {
        "resource_id": instance_id,
        "connection_info": f"实例 ID: {instance_id}\nroot 密码: {password}\n(内网 IP 请在控制台查看)",
        "cost_estimate": None,
    }
