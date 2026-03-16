"""流程 2: 多云资源自动开通

完整流程:
1. 解析资源申请 (云厂商 + 资源类型 + 规格)
2. 调对应云厂商 API 创建资源
3. 记录资源台账
4. 飞书通知研发 (连接信息)
"""

import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from lark import notifier
from models.operation_log import OperationLog
from models.resource_record import ResourceRecord

logger = logging.getLogger(__name__)

# 云厂商名称映射
PROVIDER_MAP = {
    "阿里云": "alibaba",
    "华为云": "huawei",
    "腾讯云": "tencent",
}

# 资源类型映射
RESOURCE_TYPE_MAP = {
    "RDS MySQL": "rds_mysql",
    "RDS PostgreSQL": "rds_postgresql",
    "Redis": "redis",
    "ECS": "ecs",
    "OSS": "oss",
    "GPU(昇腾)": "ascend_gpu",
    "SLB": "slb",
    "SAE 应用": "sae",
}


async def execute_resource_provision(
    db: AsyncSession,
    lark_approval_id: str,
    applicant: str,
    cloud_provider: str | None,
    resource_type: str | None,
    spec: str | None,
    purpose: str | None,
    project: str | None,
    project_established: str | None = None,
    project_report: str | None = None,
):
    """执行云资源开通全流程。

    注意: 此流程由业务负责人在研发写代码之前提交，用于开通项目所需的云资源。
    """
    if not all([cloud_provider, resource_type]):
        raise ValueError(f"缺少必填字段: cloud_provider={cloud_provider}, "
                        f"resource_type={resource_type}")

    provider_code = PROVIDER_MAP.get(cloud_provider, "alibaba")
    type_code = RESOURCE_TYPE_MAP.get(resource_type, resource_type)
    is_established = project_established == "是"

    # 创建记录
    record = ResourceRecord(
        cloud_provider=provider_code,
        resource_type=type_code,
        resource_name=f"{project or 'unnamed'}-{type_code}",
        spec=spec,
        owner=applicant,
        project=project,
        project_established=is_established,
        project_report_url=project_report,
        lark_approval_id=lark_approval_id,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    try:
        # 根据云厂商分发
        if provider_code == "alibaba":
            result = await _provision_alibaba(type_code, spec, project)
        elif provider_code == "huawei":
            result = await _provision_huawei(type_code, spec, project)
        elif provider_code == "tencent":
            result = await _provision_tencent(type_code, spec, project)
        else:
            raise ValueError(f"不支持的云厂商: {cloud_provider}")

        # 更新记录
        record.resource_id = result.get("resource_id")
        record.connection_info = result.get("connection_info")
        record.monthly_cost_estimate = result.get("cost_estimate")
        record.status = "success"
        await db.commit()

        # 飞书通知
        await notifier.notify_resource_created(
            resource_type=resource_type,
            resource_name=record.resource_name,
            connection_info=result.get("connection_info", "详见控制台"),
            cost_estimate=result.get("cost_estimate"),
            applicant=applicant,
        )

        # 操作日志
        log = OperationLog(
            action="provision_resource",
            operator=applicant,
            lark_approval_id=lark_approval_id,
            request_data=json.dumps({
                "provider": provider_code,
                "type": type_code,
                "spec": spec,
            }),
            response_data=json.dumps(result),
            status="success",
        )
        db.add(log)
        await db.commit()

    except Exception as e:
        record.status = "failed"
        record.error_message = str(e)[:1000]
        await db.commit()

        log = OperationLog(
            action="provision_resource",
            operator=applicant,
            lark_approval_id=lark_approval_id,
            status="failed",
            error_message=str(e)[:1000],
        )
        db.add(log)
        await db.commit()

        await notifier.notify_failure("云资源开通失败", str(e), {
            "云厂商": cloud_provider,
            "资源类型": resource_type,
            "规格": spec or "",
        })
        raise


async def _provision_alibaba(resource_type: str, spec: str | None, project: str | None) -> dict:
    """阿里云资源开通。"""
    if resource_type == "rds_mysql":
        from cloud.alibaba.rds import create_rds_instance
        return await create_rds_instance(name=f"{project}-mysql", spec=spec)

    elif resource_type == "redis":
        from cloud.alibaba.redis import create_redis_instance
        return await create_redis_instance(name=f"{project}-redis", spec=spec)

    elif resource_type == "ecs":
        from cloud.alibaba.ecs import create_ecs_instance
        return await create_ecs_instance(name=f"{project}-ecs", spec=spec)

    elif resource_type == "oss":
        from cloud.alibaba.oss import create_oss_bucket
        return await create_oss_bucket(name=f"{project}-bucket")

    elif resource_type == "slb":
        from cloud.alibaba.slb import create_slb_instance
        return await create_slb_instance(name=f"{project}-slb")

    elif resource_type == "sae":
        from cloud.alibaba.sae import create_sae_application
        return await create_sae_application(name=f"{project}-app", spec=spec)

    else:
        raise ValueError(f"不支持的阿里云资源类型: {resource_type}")


async def _provision_huawei(resource_type: str, spec: str | None, project: str | None) -> dict:
    """华为云资源开通。"""
    if resource_type == "ascend_gpu":
        from cloud.huawei.ecs import create_ascend_instance
        return await create_ascend_instance(name=f"{project}-gpu", spec=spec)

    elif resource_type == "ecs":
        from cloud.huawei.ecs import create_ecs_instance
        return await create_ecs_instance(name=f"{project}-ecs", spec=spec)

    else:
        raise ValueError(f"不支持的华为云资源类型: {resource_type}")


async def _provision_tencent(resource_type: str, spec: str | None, project: str | None) -> dict:
    """腾讯云资源开通。"""
    if resource_type == "ecs":
        from cloud.tencent.cvm import create_cvm_instance
        return await create_cvm_instance(name=f"{project}-cvm", spec=spec)

    else:
        raise ValueError(f"不支持的腾讯云资源类型: {resource_type}")
