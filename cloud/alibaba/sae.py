"""阿里云 SAE — 无服务器应用引擎。

SDK: alibabacloud-sae20190506
"""

import logging

from alibabacloud_sae20190506.client import Client as SaeClient
from alibabacloud_sae20190506.models import CreateApplicationRequest

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)

SPEC_MAP = {
    "0.5核1G": (500, 1024),
    "1核2G": (1000, 2048),
    "2核4G": (2000, 4096),
    "4核8G": (4000, 8192),
}


def _get_client() -> SaeClient:
    config = get_ali_config()
    config.endpoint = f"sae.{settings.ali_region_id}.aliyuncs.com"
    return SaeClient(config)


async def create_sae_application(name: str, spec: str | None = None) -> dict:
    """创建 SAE 应用。"""
    cpu, memory = SPEC_MAP.get(spec, (1000, 2048)) if spec else (1000, 2048)

    client = _get_client()

    request = CreateApplicationRequest(
        app_name=name,
        namespace_id=settings.ali_region_id,
        package_type="Image",
        replicas=2,
        cpu=cpu,
        memory=memory,
        vpc_id=settings.ali_vpc_id,
        v_switch_id=settings.ali_vswitch_id,
        security_group_id=settings.ali_security_group_id,
    )

    response = client.create_application(request)
    app_id = response.body.data.app_id if response.body.data else "unknown"

    logger.info("SAE application created: id=%s name=%s", app_id, name)

    return {
        "resource_id": app_id,
        "connection_info": f"SAE App ID: {app_id}\n(镜像地址需在部署时指定)",
        "cost_estimate": None,
    }
