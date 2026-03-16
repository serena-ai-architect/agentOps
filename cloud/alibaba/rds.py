"""阿里云 RDS — 数据库实例管理。

SDK: alibabacloud-rds20140815
"""

import logging
import secrets
import string

from alibabacloud_rds20140815.client import Client as RdsClient
from alibabacloud_rds20140815.models import CreateDBInstanceRequest

from cloud.alibaba import get_ali_config
from config import settings

logger = logging.getLogger(__name__)

# 常用规格映射 (简化用户输入)
SPEC_MAP = {
    "1核1G": "rds.mysql.t1.small",
    "1核2G": "rds.mysql.s1.small",
    "2核4G": "rds.mysql.s2.large",
    "4核8G": "rds.mysql.s3.large",
    "8核16G": "rds.mysql.m1.medium",
    "16核32G": "rds.mysql.c1.large",
}


def _get_client() -> RdsClient:
    config = get_ali_config()
    config.endpoint = f"rds.{settings.ali_region_id}.aliyuncs.com"
    return RdsClient(config)


def _generate_password(length: int = 16) -> str:
    chars = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(chars) for _ in range(length))


async def create_rds_instance(
    name: str,
    spec: str | None = None,
    engine: str = "MySQL",
    engine_version: str = "8.0",
    storage_gb: int = 50,
) -> dict:
    """创建 RDS 数据库实例。

    Returns:
        {"resource_id": "rm-xxx", "connection_info": "...", "cost_estimate": 358.0}
    """
    instance_type = SPEC_MAP.get(spec, "rds.mysql.s2.large") if spec else "rds.mysql.s2.large"
    password = _generate_password()

    client = _get_client()

    request = CreateDBInstanceRequest(
        engine=engine,
        engine_version=engine_version,
        db_instance_class=instance_type,
        db_instance_storage=storage_gb,
        db_instance_net_type="Intranet",
        db_instance_description=name,
        security_iplist="10.0.0.0/8,172.16.0.0/12",
        pay_type="Postpaid",
        vpcid=settings.ali_vpc_id,
        v_switch_id=settings.ali_vswitch_id,
        zone_id=f"{settings.ali_region_id}-b",
    )

    response = client.create_dbinstance(request)
    instance_id = response.body.dbinstance_id
    connection_string = response.body.connection_string or f"{instance_id}.mysql.rds.aliyuncs.com"

    logger.info("RDS instance created: id=%s name=%s spec=%s", instance_id, name, instance_type)

    return {
        "resource_id": instance_id,
        "connection_info": f"Host: {connection_string}\nPort: 3306\nPassword: {password}",
        "cost_estimate": None,  # 可后续调 BSS API 查询
    }
