"""Tests for pipeline setup workflow — CI/CD creation + domain + notification."""

from unittest.mock import AsyncMock, patch

import pytest

from models.pipeline_record import PipelineRecord
from workflows.pipeline_setup import ENV_MAP, LANGUAGE_MAP, execute_pipeline_setup


class TestLanguageMapping:
    def test_java_maven(self):
        assert LANGUAGE_MAP["Java Maven"] == "java_maven"

    def test_java_gradle(self):
        assert LANGUAGE_MAP["Java Gradle"] == "java_gradle"

    def test_nodejs(self):
        assert LANGUAGE_MAP["Node.js"] == "nodejs"

    def test_python(self):
        assert LANGUAGE_MAP["Python"] == "python"


class TestEnvMapping:
    def test_test_env(self):
        assert ENV_MAP["测试环境"] == "test"

    def test_prod_env(self):
        assert ENV_MAP["生产环境"] == "production"


@pytest.mark.asyncio
class TestPipelineSetupWorkflow:
    async def test_successful_pipeline_creation(self, db, mock_notifier):
        with (
            patch(
                "workflows.pipeline_setup.create_pipeline",
                new_callable=AsyncMock,
                return_value="pipeline_12345",
            ),
            patch(
                "workflows.pipeline_setup.add_dns_record",
                new_callable=AsyncMock,
                return_value="record_001",
            ),
            patch(
                "workflows.pipeline_setup.run_pipeline",
                new_callable=AsyncMock,
                return_value="run_001",
            ),
        ):
            await execute_pipeline_setup(
                db=db,
                lark_approval_id="approval_p001",
                applicant="user_001",
                service_name="order-service",
                gitee_repo="https://gitee.com/hep/order-service",
                branch="main",
                language="Java Maven",
                environment="测试环境",
            )

        # Verify DB record
        from sqlalchemy import select

        result = await db.execute(select(PipelineRecord))
        record = result.scalar_one()
        assert record.service_name == "order-service"
        assert record.language == "java_maven"
        assert record.environment == "test"
        assert record.yunxiao_pipeline_id == "pipeline_12345"
        assert record.status == "success"
        assert ".test.hep.com.cn" in record.temp_domain

        # Verify success notification
        mock_notifier["success"].assert_called_once()
        call_args = mock_notifier["success"].call_args
        assert "流水线创建成功" in call_args.args[0]

    async def test_test_env_gets_test_domain(self, db, mock_notifier):
        with (
            patch("workflows.pipeline_setup.create_pipeline", new_callable=AsyncMock, return_value="p1"),
            patch("workflows.pipeline_setup.add_dns_record", new_callable=AsyncMock),
            patch("workflows.pipeline_setup.run_pipeline", new_callable=AsyncMock),
        ):
            await execute_pipeline_setup(
                db=db,
                lark_approval_id="approval_p002",
                applicant="user_001",
                service_name="payment",
                gitee_repo="https://gitee.com/hep/payment",
                branch="main",
                language="Node.js",
                environment="测试环境",
            )

        from sqlalchemy import select

        result = await db.execute(
            select(PipelineRecord).where(PipelineRecord.service_name == "payment")
        )
        record = result.scalar_one()
        assert ".test.hep.com.cn" in record.temp_domain
        assert record.temp_domain.startswith("payment-")

    async def test_prod_env_gets_prod_domain(self, db, mock_notifier):
        with (
            patch("workflows.pipeline_setup.create_pipeline", new_callable=AsyncMock, return_value="p2"),
            patch("workflows.pipeline_setup.add_dns_record", new_callable=AsyncMock),
            patch("workflows.pipeline_setup.run_pipeline", new_callable=AsyncMock),
        ):
            await execute_pipeline_setup(
                db=db,
                lark_approval_id="approval_p003",
                applicant="user_001",
                service_name="analytics",
                gitee_repo="https://gitee.com/hep/analytics",
                branch="release",
                language="Python",
                environment="生产环境",
            )

        from sqlalchemy import select

        result = await db.execute(
            select(PipelineRecord).where(PipelineRecord.service_name == "analytics")
        )
        record = result.scalar_one()
        assert record.temp_domain.endswith(".hep.com.cn")
        assert ".test." not in record.temp_domain

    async def test_missing_fields_raises(self, db):
        with pytest.raises(ValueError, match="缺少必填字段"):
            await execute_pipeline_setup(
                db=db,
                lark_approval_id="approval_p004",
                applicant="user_001",
                service_name=None,
                gitee_repo="https://gitee.com/hep/test",
                branch="main",
                language="Python",
                environment="测试环境",
            )

    async def test_pipeline_failure_records_error(self, db, mock_notifier):
        with patch(
            "workflows.pipeline_setup.create_pipeline",
            new_callable=AsyncMock,
            side_effect=RuntimeError("Yunxiao API error"),
        ):
            with pytest.raises(RuntimeError, match="Yunxiao API error"):
                await execute_pipeline_setup(
                    db=db,
                    lark_approval_id="approval_p005",
                    applicant="user_001",
                    service_name="failing-svc",
                    gitee_repo="https://gitee.com/hep/fail",
                    branch="main",
                    language="Python",
                    environment="测试环境",
                )

        from sqlalchemy import select

        result = await db.execute(
            select(PipelineRecord).where(PipelineRecord.service_name == "failing-svc")
        )
        record = result.scalar_one()
        assert record.status == "failed"
        assert "Yunxiao API error" in record.error_message

        mock_notifier["failure"].assert_called_once()
