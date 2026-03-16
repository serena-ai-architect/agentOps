"""定时任务引擎 — 资源到期提醒 + 月度成本报表。

使用 APScheduler 在 FastAPI 进程内运行定时任务，
无需额外的 Redis/Celery 基础设施。
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_, select

from config import settings

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler():
    """启动定时任务调度器（在 FastAPI lifespan 中调用）。"""
    global _scheduler
    _scheduler = BackgroundScheduler(timezone="Asia/Shanghai")

    # 每日 09:00 检查资源到期
    _scheduler.add_job(
        _run_async(check_resource_expiry),
        CronTrigger(hour=9, minute=0),
        id="check_resource_expiry",
        name="资源到期检查",
    )

    # 每月 1 号 10:00 发送成本报表
    _scheduler.add_job(
        _run_async(send_monthly_cost_report),
        CronTrigger(day=settings.cost_report_day, hour=10, minute=0),
        id="send_monthly_cost_report",
        name="月度成本报表",
    )

    _scheduler.start()
    logger.info("Scheduler started with %d jobs", len(_scheduler.get_jobs()))


def stop_scheduler():
    """关闭调度器。"""
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")


def _run_async(coro_func):
    """将 async 函数包装为同步函数供 APScheduler 调用。"""
    def wrapper():
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(coro_func())
        except Exception as e:
            logger.exception("Scheduled task failed: %s", e)
        finally:
            loop.close()
    return wrapper


# ============================================================
# 定时任务 1: 资源到期检查
# ============================================================

async def check_resource_expiry():
    """扫描即将到期的云资源，按负责人分组发送飞书提醒。

    查询条件: expires_at 在今天到未来 N 天之间，且状态为 success。
    """
    from models.database import async_session
    from models.resource_record import ResourceRecord

    now = datetime.now(timezone.utc)
    deadline = now + timedelta(days=settings.expiry_warning_days)

    async with async_session() as db:
        stmt = select(ResourceRecord).where(
            and_(
                ResourceRecord.expires_at.isnot(None),
                ResourceRecord.expires_at <= deadline,
                ResourceRecord.expires_at > now,
                ResourceRecord.status == "success",
            )
        ).order_by(ResourceRecord.expires_at)

        result = await db.execute(stmt)
        records = result.scalars().all()

    if not records:
        logger.info("No resources expiring in the next %d days", settings.expiry_warning_days)
        return

    # 构造通知数据
    PROVIDER_NAMES = {"alibaba": "阿里云", "huawei": "华为云", "tencent": "腾讯云"}
    TYPE_NAMES = {
        "rds_mysql": "RDS MySQL", "rds_postgresql": "RDS PostgreSQL",
        "redis": "Redis", "ecs": "ECS", "oss": "OSS",
        "ascend_gpu": "昇腾 GPU", "slb": "SLB", "sae": "SAE",
    }

    resources = []
    for r in records:
        days_left = (r.expires_at - now).days
        resources.append({
            "name": r.resource_name,
            "type": TYPE_NAMES.get(r.resource_type, r.resource_type),
            "cloud": PROVIDER_NAMES.get(r.cloud_provider, r.cloud_provider),
            "owner": r.owner or "未知",
            "expires_in_days": max(days_left, 0),
        })

    from lark.notifier import notify_expiry_warning
    await notify_expiry_warning(resources)

    logger.info("Sent expiry warning for %d resources", len(resources))


# ============================================================
# 定时任务 2: 月度成本报表
# ============================================================

async def send_monthly_cost_report():
    """汇总上月云资源成本，发送飞书报表。

    数据来源:
    1. 本地资源台账 (resource_records) 的 monthly_cost_estimate
    2. 可选: 调阿里云 BSS API 查询实际账单 (更准确)
    """
    from models.database import async_session
    from models.resource_record import ResourceRecord

    # 计算上月时间范围
    now = datetime.now(timezone.utc)
    first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month_end = first_of_this_month - timedelta(seconds=1)
    last_month_start = last_month_end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    month_str = last_month_start.strftime("%Y-%m")

    async with async_session() as db:
        # 查询所有活跃资源 (status=success, 创建于上月之前或上月内)
        stmt = select(ResourceRecord).where(
            and_(
                ResourceRecord.status == "success",
                ResourceRecord.created_at <= first_of_this_month,
            )
        )
        result = await db.execute(stmt)
        records = result.scalars().all()

    if not records:
        logger.info("No active resources found for %s cost report", month_str)
        return

    PROVIDER_NAMES = {"alibaba": "阿里云", "huawei": "华为云", "tencent": "腾讯云"}
    TYPE_NAMES = {
        "rds_mysql": "RDS MySQL", "rds_postgresql": "RDS PostgreSQL",
        "redis": "Redis", "ecs": "ECS", "oss": "OSS",
        "ascend_gpu": "昇腾 GPU", "slb": "SLB", "sae": "SAE",
    }

    # 按云厂商汇总
    by_provider: dict[str, float] = {}
    # 按资源类型汇总
    by_type: dict[str, float] = {}

    for r in records:
        cost = r.monthly_cost_estimate or 0.0
        provider_name = PROVIDER_NAMES.get(r.cloud_provider, r.cloud_provider)
        type_name = TYPE_NAMES.get(r.resource_type, r.resource_type)

        by_provider[provider_name] = by_provider.get(provider_name, 0) + cost
        by_type[type_name] = by_type.get(type_name, 0) + cost

    total = sum(by_provider.values())

    # 尝试从阿里云 BSS API 获取更准确的账单数据
    try:
        bss_total = await _fetch_alibaba_bill(month_str)
        if bss_total is not None and bss_total > 0:
            # 用实际账单替换阿里云的估算值
            by_provider["阿里云"] = bss_total
            total = sum(by_provider.values())
    except Exception as e:
        logger.warning("Failed to fetch BSS bill, using estimates: %s", e)

    from lark.notifier import notify_cost_report
    await notify_cost_report(
        month=month_str,
        by_provider=by_provider,
        by_type=by_type,
        total=total,
    )

    logger.info("Sent monthly cost report for %s: total=%.0f", month_str, total)


async def _fetch_alibaba_bill(month: str) -> float | None:
    """从阿里云 BSS API 查询指定月份的实际账单总额。"""
    try:
        from alibabacloud_bssopenapi20171214.client import Client as BssClient
        from alibabacloud_bssopenapi20171214.models import QueryBillOverviewRequest

        from cloud.alibaba import get_ali_config

        config = get_ali_config()
        config.endpoint = "business.aliyuncs.com"
        client = BssClient(config)

        request = QueryBillOverviewRequest(billing_cycle=month)
        response = client.query_bill_overview(request)

        if response.body and response.body.data and response.body.data.items:
            total = sum(
                float(item.pretax_amount or 0)
                for item in response.body.data.items.item
            )
            return total
    except Exception as e:
        logger.warning("BSS QueryBillOverview failed: %s", e)

    return None
