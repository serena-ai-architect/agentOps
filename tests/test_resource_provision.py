"""Tests for resource provisioning workflow — cloud dispatch + DB records + notifications."""

from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio

from models.resource_record import ResourceRecord
from workflows.resource_provision import (
    PROVIDER_MAP,
    RESOURCE_TYPE_MAP,
    execute_resource_provision,
)


class TestProviderMapping:
    def test_alibaba_mapping(self):
        assert PROVIDER_MAP["阿里云"] == "alibaba"

    def test_huawei_mapping(self):
        assert PROVIDER_MAP["华为云"] == "huawei"

    def test_tencent_mapping(self):
        assert PROVIDER_MAP["腾讯云"] == "tencent"


class TestResourceTypeMapping:
    def test_rds_mysql(self):
        assert RESOURCE_TYPE_MAP["RDS MySQL"] == "rds_mysql"

    def test_redis(self):
        assert RESOURCE_TYPE_MAP["Redis"] == "redis"

    def test_gpu(self):
        assert RESOURCE_TYPE_MAP["GPU(昇腾)"] == "ascend_gpu"

    def test_all_types_have_values(self):
        for key, value in RESOURCE_TYPE_MAP.items():
            assert value, f"Empty mapping for {key}"


@pytest.mark.asyncio
class TestResourceProvisionWorkflow:
    async def test_alibaba_rds_creates_record_and_notifies(self, db, mock_notifier):
        mock_result = {
            "resource_id": "rm-test123",
            "connection_info": "Host: test.mysql.rds.aliyuncs.com\nPort: 3306\nPassword: secret",
            "cost_estimate": None,
        }

        with patch(
            "workflows.resource_provision._provision_alibaba",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await execute_resource_provision(
                db=db,
                lark_approval_id="approval_001",
                applicant="user_001",
                cloud_provider="阿里云",
                resource_type="RDS MySQL",
                spec="4核8G",
                purpose="订单数据库",
                project="order",
            )

        # Verify DB record
        from sqlalchemy import select

        result = await db.execute(select(ResourceRecord))
        record = result.scalar_one()
        assert record.cloud_provider == "alibaba"
        assert record.resource_type == "rds_mysql"
        assert record.resource_id == "rm-test123"
        assert record.status == "success"
        assert record.owner == "user_001"
        assert record.project == "order"

        # Verify notification sent
        mock_notifier["resource_created"].assert_called_once()

    async def test_huawei_gpu_dispatches_correctly(self, db, mock_notifier):
        mock_result = {
            "resource_id": "server-gpu-001",
            "connection_info": "实例 ID: server-gpu-001 (昇腾 GPU)",
            "cost_estimate": None,
        }

        with patch(
            "workflows.resource_provision._provision_huawei",
            new_callable=AsyncMock,
            return_value=mock_result,
        ):
            await execute_resource_provision(
                db=db,
                lark_approval_id="approval_002",
                applicant="user_002",
                cloud_provider="华为云",
                resource_type="GPU(昇腾)",
                spec="昇腾910B x1",
                purpose="模型训练",
                project="ai-training",
            )

        result = await db.execute(
            __import__("sqlalchemy").select(ResourceRecord).where(
                ResourceRecord.lark_approval_id == "approval_002"
            )
        )
        record = result.scalar_one()
        assert record.cloud_provider == "huawei"
        assert record.resource_type == "ascend_gpu"
        assert record.status == "success"

    async def test_missing_provider_raises(self, db, mock_notifier):
        with pytest.raises(ValueError, match="缺少必填字段"):
            await execute_resource_provision(
                db=db,
                lark_approval_id="approval_003",
                applicant="user_003",
                cloud_provider=None,
                resource_type="RDS MySQL",
                spec=None,
                purpose=None,
                project=None,
            )

    async def test_missing_resource_type_raises(self, db, mock_notifier):
        with pytest.raises(ValueError, match="缺少必填字段"):
            await execute_resource_provision(
                db=db,
                lark_approval_id="approval_004",
                applicant="user_004",
                cloud_provider="阿里云",
                resource_type=None,
                spec=None,
                purpose=None,
                project=None,
            )

    async def test_cloud_api_failure_records_error(self, db, mock_notifier):
        with patch(
            "workflows.resource_provision._provision_alibaba",
            new_callable=AsyncMock,
            side_effect=RuntimeError("API timeout"),
        ):
            with pytest.raises(RuntimeError, match="API timeout"):
                await execute_resource_provision(
                    db=db,
                    lark_approval_id="approval_005",
                    applicant="user_005",
                    cloud_provider="阿里云",
                    resource_type="ECS",
                    spec="2核4G",
                    purpose="测试",
                    project="test",
                )

        # Record should be marked as failed
        from sqlalchemy import select

        result = await db.execute(
            select(ResourceRecord).where(
                ResourceRecord.lark_approval_id == "approval_005"
            )
        )
        record = result.scalar_one()
        assert record.status == "failed"
        assert "API timeout" in record.error_message

        # Failure notification should have been sent
        mock_notifier["failure"].assert_called_once()

    async def test_unsupported_alibaba_resource_type_raises(self, db, mock_notifier):
        """An unrecognized resource type under a valid provider should fail."""
        with pytest.raises(Exception):
            await execute_resource_provision(
                db=db,
                lark_approval_id="approval_006",
                applicant="user_006",
                cloud_provider="阿里云",
                resource_type="RDS PostgreSQL",  # exists in map but not implemented
                spec=None,
                purpose=None,
                project="test",
            )
