"""飞书事件回调 — 整个自动化系统的入口。

飞书会在以下场景 POST 到此端点:
1. 事件订阅验证 (url_verification) — 首次配置时的握手
2. 审批实例状态变更 (approval_instance) — 审批通过/拒绝时

当审批通过时，根据审批模板 code 路由到对应的 workflow 执行自动化操作。
"""

import hashlib
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Request
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from lark.client import extract_form_value, get_approval_instance
from models.database import async_session

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/events")
async def handle_lark_event(request: Request, background_tasks: BackgroundTasks):
    """接收飞书事件回调。

    飞书事件订阅文档:
    https://open.feishu.cn/document/ukTMukTMukTM/uUTNz4SN1MjL1UzM
    """
    body = await request.json()

    # --- 1. 事件订阅验证 (首次配置时飞书发送 challenge) ---
    if body.get("type") == "url_verification":
        challenge = body.get("challenge", "")
        logger.info("Lark URL verification: challenge=%s", challenge)
        return {"challenge": challenge}

    # --- 2. 事件回调 v2.0 格式 ---
    schema = body.get("schema")
    header = body.get("header", {})
    event = body.get("event", {})

    event_type = header.get("event_type", "")
    token = header.get("token", "")

    # 验证 token
    if settings.lark_verification_token and token != settings.lark_verification_token:
        logger.warning("Invalid verification token: %s", token)
        return {"code": 401, "msg": "invalid token"}

    logger.info("Lark event received: type=%s", event_type)

    # --- 3. 审批实例状态变更 ---
    if event_type == "approval_instance":
        status = event.get("status", "")
        approval_code = event.get("approval_code", "")
        instance_id = event.get("instance_id", "")

        logger.info(
            "Approval event: code=%s instance=%s status=%s",
            approval_code, instance_id, status,
        )

        # 只处理审批通过的事件
        if status == "APPROVED":
            background_tasks.add_task(_handle_approved, instance_id, approval_code)

    return {"code": 0, "msg": "ok"}


async def _handle_approved(instance_id: str, approval_code: str):
    """处理审批通过事件 — 查询表单数据，路由到对应 workflow。"""
    try:
        # 查询审批实例详情 (获取表单数据)
        instance = await get_approval_instance(instance_id)
        form = instance["form"]
        applicant_id = instance["applicant_id"]

        logger.info(
            "Processing approved instance=%s code=%s applicant=%s",
            instance_id, approval_code, applicant_id,
        )

        # 根据审批模板 code 路由
        if approval_code == settings.lark_approval_pipeline:
            await _dispatch_pipeline_setup(instance_id, form, applicant_id)
        elif approval_code == settings.lark_approval_resource:
            await _dispatch_resource_provision(instance_id, form, applicant_id)
        elif approval_code == settings.lark_approval_domain:
            await _dispatch_domain_change(instance_id, form, applicant_id)
        else:
            logger.warning("Unknown approval code: %s, ignoring", approval_code)

    except Exception as e:
        logger.exception("Failed to handle approved instance %s: %s", instance_id, e)
        # 发送失败通知
        from lark.notifier import notify_failure

        await notify_failure("自动化执行失败", str(e), {"审批单号": instance_id})


async def _dispatch_pipeline_setup(instance_id: str, form: list, applicant_id: str):
    """分发到流程1: 创建云效流水线。"""
    from lark.approval_templates import PipelineApproval
    from workflows.pipeline_setup import execute_pipeline_setup

    data = {
        "service_name": extract_form_value(form, PipelineApproval.SERVICE_NAME),
        "gitee_repo": extract_form_value(form, PipelineApproval.GITEE_REPO),
        "branch": extract_form_value(form, PipelineApproval.BRANCH),
        "language": extract_form_value(form, PipelineApproval.LANGUAGE),
        "environment": extract_form_value(form, PipelineApproval.ENVIRONMENT),
    }

    async with async_session() as db:
        await execute_pipeline_setup(
            db=db,
            lark_approval_id=instance_id,
            applicant=applicant_id,
            **data,
        )


async def _dispatch_resource_provision(instance_id: str, form: list, applicant_id: str):
    """分发到流程2: 云资源开通（由业务负责人在写代码前提交）。"""
    from lark.approval_templates import ResourceApproval
    from workflows.resource_provision import execute_resource_provision

    data = {
        "cloud_provider": extract_form_value(form, ResourceApproval.CLOUD_PROVIDER),
        "resource_type": extract_form_value(form, ResourceApproval.RESOURCE_TYPE),
        "spec": extract_form_value(form, ResourceApproval.SPEC),
        "purpose": extract_form_value(form, ResourceApproval.PURPOSE),
        "project": extract_form_value(form, ResourceApproval.PROJECT),
        "project_established": extract_form_value(form, ResourceApproval.PROJECT_ESTABLISHED),
        "project_report": extract_form_value(form, ResourceApproval.PROJECT_REPORT),
    }

    async with async_session() as db:
        await execute_resource_provision(
            db=db,
            lark_approval_id=instance_id,
            applicant=applicant_id,
            **data,
        )


async def _dispatch_domain_change(instance_id: str, form: list, applicant_id: str):
    """分发到流程3: 域名替换（需要等保备案）。"""
    from lark.approval_templates import DomainApproval
    from workflows.domain_change import execute_domain_change

    data = {
        "service_name": extract_form_value(form, DomainApproval.SERVICE_NAME),
        "current_domain": extract_form_value(form, DomainApproval.CURRENT_DOMAIN),
        "formal_domain": extract_form_value(form, DomainApproval.FORMAL_DOMAIN),
        "environment": extract_form_value(form, DomainApproval.ENVIRONMENT),
        "security_filing": extract_form_value(form, DomainApproval.SECURITY_FILING),
        "security_filing_proof": extract_form_value(form, DomainApproval.SECURITY_FILING_PROOF),
    }

    async with async_session() as db:
        await execute_domain_change(
            db=db,
            lark_approval_id=instance_id,
            applicant=applicant_id,
            **data,
        )
