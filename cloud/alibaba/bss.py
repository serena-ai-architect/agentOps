"""阿里云 BSS — 计费询价。

SDK: alibabacloud-bssopenapi20171214
"""

import logging

from alibabacloud_bssopenapi20171214.client import Client as BssClient
from alibabacloud_bssopenapi20171214.models import GetPayAsYouGoPriceRequest

from cloud.alibaba import get_ali_config

logger = logging.getLogger(__name__)


def _get_client() -> BssClient:
    config = get_ali_config()
    config.endpoint = "business.aliyuncs.com"
    return BssClient(config)


async def get_price_estimate(product_code: str, product_type: str, spec: str) -> float | None:
    """查询按量付费价格。

    Args:
        product_code: 产品代码，如 "rds", "kvstore", "ecs"
        product_type: 产品类型
        spec: 规格

    Returns:
        预估月费 (元) 或 None
    """
    try:
        client = _get_client()

        request = GetPayAsYouGoPriceRequest(
            product_code=product_code,
            product_type=product_type,
        )

        response = client.get_pay_as_you_go_price(request)
        if response.body and response.body.data:
            # 返回小时价格 × 24 × 30 = 月估价
            hourly_price = response.body.data.trade_price
            if hourly_price:
                return round(float(hourly_price) * 24 * 30, 2)
    except Exception as e:
        logger.warning("BSS price query failed: %s", e)

    return None
