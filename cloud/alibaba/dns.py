"""阿里云 DNS — 域名解析记录管理。

SDK: alibabacloud-alidns20150109
"""

import logging

from alibabacloud_alidns20150109.client import Client as DnsClient
from alibabacloud_alidns20150109.models import (
    AddDomainRecordRequest,
    DeleteDomainRecordRequest,
    DescribeDomainRecordsRequest,
)

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)


def _get_client() -> DnsClient:
    config = get_ali_config()
    config.endpoint = "alidns.cn-hangzhou.aliyuncs.com"
    return DnsClient(config)


async def add_dns_record(
    subdomain: str,
    record_type: str = "CNAME",
    value: str = "",
    ttl: int = 600,
) -> str:
    """添加 DNS 解析记录。

    Args:
        subdomain: 子域名，如 "order-service-test"（不含主域名）
        record_type: 记录类型 A/CNAME/TXT 等
        value: 记录值（IP 或 CNAME 目标）
        ttl: TTL 秒数

    Returns:
        record_id: DNS 记录 ID
    """
    client = _get_client()

    request = AddDomainRecordRequest(
        domain_name=settings.ali_domain_name,
        rr=subdomain,
        type=record_type,
        value=value,
        ttl=ttl,
    )

    response = client.add_domain_record(request)
    record_id = response.body.record_id
    logger.info("DNS record created: %s.%s → %s (id=%s)", subdomain, settings.ali_domain_name, value, record_id)
    return record_id


async def find_dns_record(subdomain: str) -> str | None:
    """查找 DNS 记录 ID。"""
    client = _get_client()

    request = DescribeDomainRecordsRequest(
        domain_name=settings.ali_domain_name,
        rr_key_word=subdomain,
    )

    response = client.describe_domain_records(request)
    records = response.body.domain_records.record if response.body.domain_records else []

    for record in records:
        if record.rr == subdomain:
            return record.record_id

    return None


async def delete_dns_record(record_id: str):
    """删除 DNS 记录。"""
    client = _get_client()

    request = DeleteDomainRecordRequest(record_id=record_id)
    client.delete_domain_record(request)
    logger.info("DNS record deleted: id=%s", record_id)
