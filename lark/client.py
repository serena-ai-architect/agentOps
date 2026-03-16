"""飞书 API 客户端 — 审批实例查询 + 表单数据提取。

飞书事件回调只告诉我们"某个审批实例状态变了"，
我们需要通过 API 查询审批实例的完整信息（表单数据、审批人等）。
"""

import json
import logging

import lark_oapi as lark
from lark_oapi.api.approval.v4 import GetApprovalInstanceRequest

from config import settings

logger = logging.getLogger(__name__)

# 全局 Lark 客户端
_client: lark.Client | None = None


def get_lark_client() -> lark.Client:
    global _client
    if _client is None:
        _client = (
            lark.Client.builder()
            .app_id(settings.lark_app_id)
            .app_secret(settings.lark_app_secret)
            .log_level(lark.LogLevel.DEBUG if settings.debug else lark.LogLevel.INFO)
            .build()
        )
    return _client


async def get_approval_instance(instance_id: str) -> dict:
    """查询审批实例详情，返回表单数据和审批状态。

    Returns:
        {
            "approval_code": "xxx",     # 审批模板 code
            "status": "APPROVED",       # PENDING/APPROVED/REJECTED/CANCELED
            "form": [...],              # 表单字段列表
            "applicant_id": "xxx",      # 申请人 user_id
        }
    """
    client = get_lark_client()

    request = (
        GetApprovalInstanceRequest.builder()
        .instance_id(instance_id)
        .build()
    )

    response = client.approval.v4.approval_instance.get(request)

    if not response.success():
        raise RuntimeError(
            f"Failed to get approval instance {instance_id}: "
            f"code={response.code}, msg={response.msg}"
        )

    data = response.data
    return {
        "approval_code": data.approval_code,
        "status": data.status,
        "form": json.loads(data.form) if data.form else [],
        "applicant_id": data.user_id,
    }


def extract_form_value(form_fields: list[dict], field_name: str) -> str | None:
    """从飞书审批表单字段列表中提取指定字段的值。

    飞书表单数据格式:
    [
        {"id": "widget_xxx", "name": "项目名称", "type": "input", "value": "order-service"},
        {"id": "widget_yyy", "name": "Gitee 仓库地址", "type": "input", "value": "https://..."},
        ...
    ]
    """
    for field in form_fields:
        if field.get("name") == field_name:
            value = field.get("value", "")
            # 单选类型的值是 JSON 字符串，如 '"Java Maven"'
            if isinstance(value, str) and value.startswith('"'):
                try:
                    return json.loads(value)
                except json.JSONDecodeError:
                    pass
            return value
    return None
