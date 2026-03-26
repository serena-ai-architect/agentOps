"""Tests for the task manager — idempotency, state tracking, lifecycle."""

import pytest

from engine.task_manager import (
    get_task,
    list_recent_tasks,
    mark_failed,
    mark_running,
    mark_success,
    submit_task,
)
from models.task_record import TaskRecord


@pytest.mark.asyncio
class TestSubmitTask:
    async def test_new_task_created(self, db):
        task, is_new = await submit_task(
            db=db,
            idempotency_key="inst_001",
            task_type="provision",
            input_data={"provider": "alibaba", "type": "rds_mysql"},
        )
        assert is_new is True
        assert task.idempotency_key == "inst_001"
        assert task.task_type == "provision"
        assert task.state == "pending"
        assert task.id is not None

    async def test_duplicate_key_returns_existing(self, db):
        task1, is_new1 = await submit_task(
            db=db,
            idempotency_key="inst_dup",
            task_type="pipeline",
            input_data={"service": "test"},
        )
        task2, is_new2 = await submit_task(
            db=db,
            idempotency_key="inst_dup",
            task_type="pipeline",
            input_data={"service": "test"},
        )
        assert is_new1 is True
        assert is_new2 is False
        assert task1.id == task2.id

    async def test_different_keys_create_separate_tasks(self, db):
        t1, _ = await submit_task(db=db, idempotency_key="a", task_type="provision", input_data={})
        t2, _ = await submit_task(db=db, idempotency_key="b", task_type="provision", input_data={})
        assert t1.id != t2.id


@pytest.mark.asyncio
class TestTaskLifecycle:
    async def test_pending_to_running(self, db):
        task, _ = await submit_task(
            db=db, idempotency_key="lc_001", task_type="provision", input_data={}
        )
        assert task.state == "pending"
        assert task.started_at is None

        await mark_running(db, task)
        assert task.state == "running"
        assert task.started_at is not None

    async def test_running_to_success(self, db):
        task, _ = await submit_task(
            db=db, idempotency_key="lc_002", task_type="domain", input_data={}
        )
        await mark_running(db, task)
        await mark_success(db, task, output={"domain": "order.hep.com.cn"})

        assert task.state == "success"
        assert task.completed_at is not None
        assert "order.hep.com.cn" in task.output_data

    async def test_running_to_failed(self, db):
        task, _ = await submit_task(
            db=db, idempotency_key="lc_003", task_type="pipeline", input_data={}
        )
        await mark_running(db, task)
        await mark_failed(db, task, error="Yunxiao API timeout")

        assert task.state == "failed"
        assert task.completed_at is not None
        assert "Yunxiao API timeout" in task.error
        assert task.retry_count == 1

    async def test_multiple_failures_increment_retry(self, db):
        task, _ = await submit_task(
            db=db, idempotency_key="lc_004", task_type="provision", input_data={}
        )
        await mark_running(db, task)
        await mark_failed(db, task, error="error 1")
        assert task.retry_count == 1

        task.state = "running"  # simulate retry
        await mark_failed(db, task, error="error 2")
        assert task.retry_count == 2


@pytest.mark.asyncio
class TestTaskQueries:
    async def test_get_task_by_key(self, db):
        await submit_task(db=db, idempotency_key="q_001", task_type="provision", input_data={})
        found = await get_task(db, "q_001")
        assert found is not None
        assert found.task_type == "provision"

    async def test_get_nonexistent_returns_none(self, db):
        found = await get_task(db, "nonexistent_key")
        assert found is None

    async def test_list_recent_tasks(self, db):
        for i in range(5):
            await submit_task(
                db=db,
                idempotency_key=f"list_{i}",
                task_type="provision",
                input_data={"i": i},
            )
        tasks = await list_recent_tasks(db, limit=3)
        assert len(tasks) == 3
