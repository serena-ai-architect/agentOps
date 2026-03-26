"""任务状态查询 API — 可观测性入口。"""

from fastapi import APIRouter

from engine.task_manager import get_task, list_recent_tasks
from models.database import async_session

router = APIRouter()


@router.get("/tasks")
async def list_tasks(limit: int = 20):
    """查询最近的任务列表。"""
    async with async_session() as db:
        tasks = await list_recent_tasks(db, limit=limit)
    return [
        {
            "id": t.id,
            "idempotency_key": t.idempotency_key,
            "task_type": t.task_type,
            "state": t.state,
            "retry_count": t.retry_count,
            "error": t.error,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in tasks
    ]


@router.get("/tasks/{idempotency_key}")
async def get_task_status(idempotency_key: str):
    """按幂等键查询单个任务状态。"""
    async with async_session() as db:
        task = await get_task(db, idempotency_key)
    if not task:
        return {"code": 404, "msg": "task not found"}
    return {
        "id": task.id,
        "idempotency_key": task.idempotency_key,
        "task_type": task.task_type,
        "state": task.state,
        "input_data": task.input_data,
        "output_data": task.output_data,
        "error": task.error,
        "retry_count": task.retry_count,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
    }
