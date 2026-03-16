"""流程 1: 创建云效流水线 + 分配临时域名

完整流程:
1. 在云效上创建 CI/CD 流水线 (关联 Gitee 仓库)
2. 分配临时域名 (如 order-service-test.hep.com.cn)
3. 创建 DNS 记录
4. 触发首次流水线运行
5. 飞书通知研发
"""

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from cloud.alibaba.dns import add_dns_record
from cloud.alibaba.yunxiao import create_pipeline, run_pipeline
from lark import notifier
from models.operation_log import OperationLog
from models.pipeline_record import PipelineRecord

logger = logging.getLogger(__name__)

# 语言类型到云效构建配置的映射
LANGUAGE_MAP = {
    "Java Maven": "java_maven",
    "Java Gradle": "java_gradle",
    "Node.js": "nodejs",
    "Python": "python",
}

ENV_MAP = {
    "测试环境": "test",
    "生产环境": "production",
}


async def execute_pipeline_setup(
    db: AsyncSession,
    lark_approval_id: str,
    applicant: str,
    service_name: str | None,
    gitee_repo: str | None,
    branch: str | None,
    language: str | None,
    environment: str | None,
):
    """执行流水线创建全流程。"""
    if not all([service_name, gitee_repo, branch, language]):
        raise ValueError(f"缺少必填字段: service_name={service_name}, "
                        f"gitee_repo={gitee_repo}, branch={branch}, language={language}")

    lang_code = LANGUAGE_MAP.get(language, "java_maven")
    env_code = ENV_MAP.get(environment, "test")

    # 自动分配域名: 测试环境=测试域名，生产环境=.hep.com.cn 正式域名
    short_id = uuid.uuid4().hex[:6]
    if env_code == "test":
        temp_domain = f"{service_name}-{short_id}.test.hep.com.cn"
    else:
        temp_domain = f"{short_id}.hep.com.cn"

    # 创建记录
    record = PipelineRecord(
        service_name=service_name,
        gitee_repo=gitee_repo,
        branch=branch,
        language=lang_code,
        environment=env_code,
        temp_domain=temp_domain,
        lark_approval_id=lark_approval_id,
        applicant=applicant,
        status="pending",
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    try:
        # Step 1: 在云效上创建流水线
        logger.info("Creating Yunxiao pipeline for %s (%s)", service_name, gitee_repo)
        pipeline_id = await create_pipeline(
            service_name=service_name,
            gitee_repo=gitee_repo,
            branch=branch,
            language=lang_code,
            environment=env_code,
        )
        record.yunxiao_pipeline_id = pipeline_id

        # Step 2: 创建 DNS 记录 (指向负载均衡 IP，需要根据实际环境配置)
        logger.info("Creating DNS record for %s", temp_domain)
        await add_dns_record(
            subdomain=temp_domain.replace(".hep.com.cn", ""),
            record_type="CNAME",
            value=f"slb-{env_code}.hep.com.cn",  # 指向对应环境的 SLB
        )

        # Step 3: 触发首次运行
        logger.info("Triggering first pipeline run for %s", pipeline_id)
        await run_pipeline(pipeline_id)

        # 更新状态
        record.status = "success"
        await db.commit()

        # Step 4: 飞书通知
        await notifier.notify_success("流水线创建成功", {
            "项目": service_name,
            "仓库": gitee_repo,
            "分支": branch,
            "语言": language,
            "环境": environment,
            "分配域名": temp_domain,
            "云效流水线 ID": pipeline_id,
        })

        # 记录操作日志
        log = OperationLog(
            action="create_pipeline",
            operator=applicant,
            lark_approval_id=lark_approval_id,
            request_data=json.dumps({
                "service_name": service_name,
                "gitee_repo": gitee_repo,
                "branch": branch,
                "language": lang_code,
            }),
            response_data=json.dumps({
                "pipeline_id": pipeline_id,
                "temp_domain": temp_domain,
            }),
            status="success",
        )
        db.add(log)
        await db.commit()

    except Exception as e:
        record.status = "failed"
        record.error_message = str(e)[:1000]
        await db.commit()

        # 记录失败日志
        log = OperationLog(
            action="create_pipeline",
            operator=applicant,
            lark_approval_id=lark_approval_id,
            status="failed",
            error_message=str(e)[:1000],
        )
        db.add(log)
        await db.commit()

        # 飞书通知失败
        await notifier.notify_failure("流水线创建失败", str(e), {
            "项目": service_name,
            "仓库": gitee_repo,
        })
        raise
