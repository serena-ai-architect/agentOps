"""飞书机器人通知 — 向群聊发送操作结果通知。

使用自定义机器人 webhook 发送消息，支持富文本格式。
"""

import hashlib
import hmac
import logging
import time
from base64 import b64encode

import httpx

from config import settings

logger = logging.getLogger(__name__)


async def notify_success(title: str, details: dict[str, str]):
    """发送操作成功通知。

    Args:
        title: 通知标题，如 "流水线创建成功"
        details: 详情字典，如 {"服务名": "order-service", "域名": "xxx.hep.com.cn"}
    """
    lines = [[{"tag": "text", "text": f"{k}: {v}"}] for k, v in details.items()]

    await _send_rich_text(
        title=f"\u2705 {title}",
        content_lines=lines,
    )


async def notify_failure(title: str, error: str, details: dict[str, str] | None = None):
    """发送操作失败通知。"""
    lines = [[{"tag": "text", "text": f"\u274c 错误: {error[:300]}"}]]
    if details:
        lines.extend([[{"tag": "text", "text": f"{k}: {v}"}] for k, v in details.items()])

    await _send_rich_text(
        title=f"\u274c {title}",
        content_lines=lines,
    )


async def notify_resource_created(
    resource_type: str,
    resource_name: str,
    connection_info: str,
    cost_estimate: float | None = None,
    applicant: str | None = None,
):
    """发送云资源创建成功通知。"""
    details = {
        "资源类型": resource_type,
        "资源名称": resource_name,
        "连接信息": connection_info,
    }
    if cost_estimate:
        details["预估月费"] = f"{cost_estimate:.0f} 元/月"
    if applicant:
        details["申请人"] = applicant

    await notify_success("云资源开通成功", details)


async def notify_domain_changed(
    service_name: str,
    old_domain: str,
    new_domain: str,
):
    """发送域名变更成功通知。"""
    await notify_success("域名变更成功", {
        "服务": service_name,
        "旧域名": old_domain,
        "新域名": new_domain,
    })


async def notify_expiry_warning(resources: list[dict]):
    """发送资源到期预警通知。

    通知对象: 业务负责人(owner) + 公有云负责人 + 信息技术部主任杨京峰
    同时发送到群 webhook (全员可见) 和单聊消息 (定向通知负责人)。

    Args:
        resources: [{"name": "order-mysql", "type": "RDS", "owner": "张三",
                      "expires_in_days": 3, "cloud": "阿里云"}, ...]
    """
    lines = [[{"tag": "text", "text": f"以下 {len(resources)} 个云资源即将到期，请及时处理:"}]]
    lines.append([{"tag": "text", "text": ""}])

    for r in resources:
        lines.append([{
            "tag": "text",
            "text": f"  {r['cloud']} | {r['type']} | {r['name']} | "
                    f"{r['expires_in_days']}天后到期 | 负责人: {r.get('owner', '未知')}",
        }])

    # 1. 发送到通知群 (所有人可见)
    await _send_rich_text(title="\u26a0\ufe0f 云资源到期预警", content_lines=lines)

    # 2. 单聊通知: 公有云负责人 + 信息技术部主任杨京峰
    fixed_recipients = []
    if settings.lark_notify_cloud_admin:
        fixed_recipients.append(settings.lark_notify_cloud_admin)
    if settings.lark_notify_it_director:
        fixed_recipients.append(settings.lark_notify_it_director)

    # 3. 单聊通知: 各资源的业务负责人 (owner)
    owners = {r["owner"] for r in resources if r.get("owner") and r["owner"] != "未知"}

    all_recipients = set(fixed_recipients) | owners
    for user_id in all_recipients:
        await _send_direct_message(
            user_id=user_id,
            title="\u26a0\ufe0f 云资源到期预警",
            content_lines=lines,
        )


async def notify_cost_report(
    month: str,
    by_provider: dict[str, float],
    by_type: dict[str, float],
    total: float,
):
    """发送月度成本汇总报表。

    Args:
        month: 月份，如 "2026-02"
        by_provider: {"阿里云": 12580, "华为云": 8900, "腾讯云": 1200}
        by_type: {"RDS": 4200, "Redis": 2100, "ECS": 6280, "GPU": 8900}
        total: 总费用
    """
    lines = [[{"tag": "text", "text": f"{month} 云资源成本汇总"}]]
    lines.append([{"tag": "text", "text": ""}])

    lines.append([{"tag": "text", "text": "--- 按云厂商 ---"}])
    for provider, cost in sorted(by_provider.items(), key=lambda x: -x[1]):
        lines.append([{"tag": "text", "text": f"  {provider}: {cost:,.0f} 元"}])

    lines.append([{"tag": "text", "text": ""}])
    lines.append([{"tag": "text", "text": "--- 按资源类型 ---"}])
    for rtype, cost in sorted(by_type.items(), key=lambda x: -x[1]):
        lines.append([{"tag": "text", "text": f"  {rtype}: {cost:,.0f} 元"}])

    lines.append([{"tag": "text", "text": ""}])
    lines.append([{"tag": "text", "text": f"月度总计: {total:,.0f} 元"}])

    await _send_rich_text(title=f"\U0001f4ca {month} 月度云资源成本报表", content_lines=lines)


async def _send_rich_text(title: str, content_lines: list[list[dict]]):
    """发送飞书富文本消息。"""
    webhook_url = settings.lark_webhook_notify
    if not webhook_url:
        logger.warning("Lark webhook URL not configured, skipping notification")
        return

    payload = {
        "msg_type": "post",
        "content": {
            "post": {
                "zh_cn": {
                    "title": title,
                    "content": content_lines,
                }
            }
        },
    }

    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(webhook_url, json=payload)
        if resp.status_code != 200:
            logger.error("Lark notification failed: %s %s", resp.status_code, resp.text)
        else:
            result = resp.json()
            if result.get("code") != 0:
                logger.error("Lark notification error: %s", result)


async def _send_direct_message(user_id: str, title: str, content_lines: list[list[dict]]):
    """通过飞书 API 向指定用户发送单聊消息。

    用于资源到期提醒等需要定向通知特定人的场景。
    使用 lark-oapi SDK 发送消息。
    """
    try:
        import json

        import lark_oapi as lark
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        client = (
            lark.Client.builder()
            .app_id(settings.lark_app_id)
            .app_secret(settings.lark_app_secret)
            .build()
        )

        content = {
            "zh_cn": {
                "title": title,
                "content": content_lines,
            }
        }

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("open_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(user_id)
                .msg_type("post")
                .content(json.dumps(content))
                .build()
            )
            .build()
        )

        response = client.im.v1.message.create(request)
        if not response.success():
            logger.error(
                "Failed to send direct message to %s: code=%s msg=%s",
                user_id, response.code, response.msg,
            )
    except Exception as e:
        logger.error("Failed to send direct message to %s: %s", user_id, e)
