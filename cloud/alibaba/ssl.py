"""阿里云 CAS — SSL 证书管理。

SDK: alibabacloud-cas20200407
"""

import logging

from alibabacloud_cas20200407.client import Client as CasClient
from alibabacloud_cas20200407.models import CreateCertificateRequestRequest

from cloud.alibaba import get_ali_config

logger = logging.getLogger(__name__)


def _get_client() -> CasClient:
    config = get_ali_config()
    config.endpoint = "cas.aliyuncs.com"
    return CasClient(config)


async def apply_ssl_certificate(domain: str) -> str:
    """为域名申请免费 SSL 证书。

    阿里云提供每年 20 个免费 DV 证书。

    Returns:
        order_id: 证书订单 ID
    """
    client = _get_client()

    request = CreateCertificateRequestRequest(
        domain=domain,
        product_code="digicert-free-1-free",  # 免费 DV SSL
    )

    response = client.create_certificate_request(request)
    order_id = str(response.body.order_id) if response.body else "unknown"
    logger.info("SSL certificate requested for %s, order_id=%s", domain, order_id)
    return order_id
