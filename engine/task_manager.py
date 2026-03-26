"""任务管理器 — 幂等提交 + 状态跟踪 + 执行。

核心逻辑：
- submit_task(): 幂等提交，重复的 idempotency_key 直接返回已有记录
- execute_task(): 执行任务并更新状态（pending → running → success/failed）
- get_task(): 查询任务状态

替换 background_tasks.add_task() 的裸调用，提供：
1. 飞书 webhook 重试去重（幂等）
2. 进程崩溃不丢任务（持久化）
3. 可查询任务进度（状态机）
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.task_record import TaskRecord

logger = logging.getLogger(__name__)


async def submit_task(
    db: AsyncSession,
    idempotency_key: str,
    task_type: str,
    input_data: dict,
) -> tuple[TaskRecord, bool]:
    """幂等提交任务。

    Returns:
        (task, is_new): task 记录 + 是否是新创建的。
        如果已存在相同 idempotency_key 的任务，直接返回 (existing, False)。
    """
    # 幂等检查：相同 key 不重复创建
    stmt = select(TaskRecord).where(TaskRecord.idempotency_key == idempotency_key)
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        logger.info(
            "Task already exists: key=%s state=%s (idempotent skip)",
            idempotency_key, existing.state,
        )
        return existing, False

    task = TaskRecord(
        idempotency_key=idempotency_key,
        task_type=task_type,
        state="pending",
        input_data=json.dumps(input_data, ensure_ascii=False),
    )
    db.add(task)
    await db.commit()
    await db.refresh(task)

    logger.info("Task created: id=%d key=%s type=%s", task.id, idempotency_key, task_type)
    return task, True


async def mark_running(db: AsyncSession, task: TaskRecord) -> None:
    """标记任务为执行中。"""
    task.state = "running"
    task.started_at = datetime.now(timezone.utc)
    await db.commit()


async def mark_success(db: AsyncSession, task: TaskRecord, output: dict | None = None) -> None:
    """标记任务为成功。"""
    task.state = "success"
    task.completed_at = datetime.now(timezone.utc)
    if output:
        task.output_data = json.dumps(output, ensure_ascii=False)
    await db.commit()


async def mark_failed(db: AsyncSession, task: TaskRecord, error: str) -> None:
    """标记任务为失败。"""
    task.state = "failed"
    task.completed_at = datetime.now(timezone.utc)
    task.error = error[:2000]
    task.retry_count += 1
    await db.commit()


async def get_task(db: AsyncSession, idempotency_key: str) -> TaskRecord | None:
    """按幂等键查询任务。"""
    stmt = select(TaskRecord).where(TaskRecord.idempotency_key == idempotency_key)
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_recent_tasks(db: AsyncSession, limit: int = 20) -> list[TaskRecord]:
    """查询最近的任务列表。"""
    stmt = select(TaskRecord).order_by(TaskRecord.created_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())
