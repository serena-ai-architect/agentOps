"""华为云 ECS — 含昇腾 GPU 实例管理。

SDK: huaweicloudsdkecs
"""

import logging
import secrets
import string

from huaweicloudsdkcore.exceptions import exceptions
from huaweicloudsdkecs.v2 import (
    CreateServersRequest,
    CreateServersRequestBody,
    EcsClient,
    PostPaidServer,
    PostPaidServerDataVolume,
    PostPaidServerNic,
    PostPaidServerRootVolume,
)
from huaweicloudsdkecs.v2.region.ecs_region import EcsRegion

from cloud.huawei.client import get_hw_credentials
from config import settings

logger = logging.getLogger(__name__)

# 昇腾 GPU 规格映射
ASCEND_SPEC_MAP = {
    "昇腾910B x1": "ai1s.xlarge.4",  # 示例规格，实际需查华为云文档
    "昇腾910B x2": "ai1s.2xlarge.4",
    "昇腾910C x1": "ai1s.xlarge.4",
}

ECS_SPEC_MAP = {
    "2核4G": "s6.large.2",
    "4核8G": "s6.xlarge.2",
    "8核16G": "s6.2xlarge.2",
}


def _get_client() -> EcsClient:
    credentials = get_hw_credentials()
    return (
        EcsClient.new_builder()
        .with_credentials(credentials)
        .with_region(EcsRegion.value_of(settings.hw_region))
        .build()
    )


async def create_ascend_instance(name: str, spec: str | None = None) -> dict:
    """创建昇腾 GPU 实例。"""
    flavor = ASCEND_SPEC_MAP.get(spec, "ai1s.xlarge.4") if spec else "ai1s.xlarge.4"
    return await _create_instance(name, flavor, is_gpu=True)


async def create_ecs_instance(name: str, spec: str | None = None) -> dict:
    """创建华为云普通 ECS 实例。"""
    flavor = ECS_SPEC_MAP.get(spec, "s6.large.2") if spec else "s6.large.2"
    return await _create_instance(name, flavor, is_gpu=False)


async def _create_instance(name: str, flavor: str, is_gpu: bool) -> dict:
    password = "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$") for _ in range(16))

    client = _get_client()

    server = PostPaidServer(
        name=name,
        flavor_ref=flavor,
        image_ref="",  # 需要填实际镜像 ID，如 Ubuntu 22.04
        root_volume=PostPaidServerRootVolume(volumetype="SSD", size=40),
        nics=[PostPaidServerNic(subnet_id="")],  # 需要填实际子网 ID
        admin_pass=password,
        count=1,
    )

    request = CreateServersRequest(body=CreateServersRequestBody(server=server))

    try:
        response = client.create_servers(request)
        server_ids = response.server_ids or []
        server_id = server_ids[0] if server_ids else "unknown"

        logger.info(
            "Huawei ECS created: id=%s name=%s flavor=%s gpu=%s",
            server_id, name, flavor, is_gpu,
        )

        gpu_info = " (昇腾 GPU)" if is_gpu else ""
        return {
            "resource_id": server_id,
            "connection_info": f"实例 ID: {server_id}{gpu_info}\n密码: {password}\n(IP 请在华为云控制台查看)",
            "cost_estimate": None,
        }

    except exceptions.ClientRequestException as e:
        raise RuntimeError(f"华为云 ECS 创建失败: {e.error_msg}") from e
