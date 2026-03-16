"""流程 3: 域名替换（自动分配域名 → 已备案的正式域名）

完整流程:
1. 校验等保备案状态（未备案则拒绝）
2. 更新 DNS 记录 (删除旧记录 + 创建新记录)
3. 申请新域名的 SSL 证书
4. 更新流水线记录中的域名
5. 飞书通知研发
"""

import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from cloud.alibaba.dns import add_dns_record, delete_dns_record, find_dns_record
from cloud.alibaba.ssl import apply_ssl_certificate
from lark import notifier
from models.operation_log import OperationLog
from models.pipeline_record import PipelineRecord

logger = logging.getLogger(__name__)

ENV_MAP = {
    "测试环境": "test",
    "生产环境": "production",
}


async def execute_domain_change(
    db: AsyncSession,
    lark_approval_id: str,
    applicant: str,
    service_name: str | None,
    current_domain: str | None,
    formal_domain: str | None,
    environment: str | None,
    security_filing: str | None,
    security_filing_proof: str | None,
):
    """执行域名替换全流程。"""
    if not all([service_name, formal_domain]):
        raise ValueError(
            f"缺少必填字段: service_name={service_name}, formal_domain={formal_domain}"
        )

    # 校验等保备案
    if security_filing != "是":
        await notifier.notify_failure("域名变更被拒绝", "正式域名必须已完成等保备案", {
            "服务": service_name,
            "申请域名": formal_domain,
            "等保备案状态": security_filing or "未填写",
        })
        raise ValueError(f"域名 {formal_domain} 未完成等保备案，无法替换。请先完成等保备案后重新提交。")

    env_code = ENV_MAP.get(environment, "test")

    try:
        # Step 1: 查找当前 DNS 记录并删除
        if current_domain:
            # 支持 .test.hep.com.cn 和 .hep.com.cn 两种格式
            if ".test.hep.com.cn" in current_domain:
                subdomain = current_domain.replace(".test.hep.com.cn", "")
            else:
                subdomain = current_domain.replace(".hep.com.cn", "")
            record_id = await find_dns_record(subdomain)
            if record_id:
                logger.info("Deleting old DNS record for %s", current_domain)
                await delete_dns_record(record_id)

        # Step 2: 创建新 DNS 记录
        # 正式域名可能不在 hep.com.cn 下，需要处理
        new_subdomain = formal_domain.replace(".hep.com.cn", "")
        logger.info("Creating new DNS record for %s", formal_domain)
        await add_dns_record(
            subdomain=new_subdomain,
            record_type="CNAME",
            value=f"slb-{env_code}.hep.com.cn",
        )

        # Step 3: 申请 SSL 证书
        logger.info("Applying SSL certificate for %s", formal_domain)
        await apply_ssl_certificate(domain=formal_domain)

        # Step 4: 更新流水线记录
        stmt = select(PipelineRecord).where(
            PipelineRecord.service_name == service_name,
            PipelineRecord.environment == env_code,
        )
        result = await db.execute(stmt)
        pipeline = result.scalar_one_or_none()
        if pipeline:
            pipeline.final_domain = formal_domain
            await db.commit()

        # 飞书通知
        await notifier.notify_domain_changed(
            service_name=service_name,
            old_domain=current_domain or "(无)",
            new_domain=formal_domain,
        )

        # 操作日志
        log = OperationLog(
            action="change_domain",
            operator=applicant,
            lark_approval_id=lark_approval_id,
            request_data=json.dumps({
                "service_name": service_name,
                "old_domain": current_domain,
                "formal_domain": formal_domain,
                "environment": env_code,
                "security_filing": security_filing,
            }),
            status="success",
        )
        db.add(log)
        await db.commit()

    except Exception as e:
        log = OperationLog(
            action="change_domain",
            operator=applicant,
            lark_approval_id=lark_approval_id,
            status="failed",
            error_message=str(e)[:1000],
        )
        db.add(log)
        await db.commit()

        if "等保备案" not in str(e):
            await notifier.notify_failure("域名变更失败", str(e), {
                "服务": service_name,
                "新域名": formal_domain,
            })
        raise
