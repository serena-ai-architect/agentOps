"""阿里云 SLB — 负载均衡管理。

SDK: alibabacloud-slb20140515
"""

import logging

from alibabacloud_slb20140515.client import Client as SlbClient
from alibabacloud_slb20140515.models import CreateLoadBalancerRequest

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)


def _get_client() -> SlbClient:
    config = get_ali_config()
    config.endpoint = f"slb.{settings.ali_region_id}.aliyuncs.com"
    return SlbClient(config)


async def create_slb_instance(name: str) -> dict:
    """创建 SLB 负载均衡。"""
    client = _get_client()

    request = CreateLoadBalancerRequest(
        load_balancer_name=name,
        address_type="intranet",
        vpc_id=settings.ali_vpc_id,
        v_switch_id=settings.ali_vswitch_id,
        load_balancer_spec="slb.s1.small",
        pay_type="PayOnDemand",
    )

    response = client.create_load_balancer(request)
    lb_id = response.body.load_balancer_id
    address = response.body.address or ""

    logger.info("SLB created: id=%s name=%s address=%s", lb_id, name, address)

    return {
        "resource_id": lb_id,
        "connection_info": f"SLB ID: {lb_id}\n内网地址: {address}",
        "cost_estimate": None,
    }
