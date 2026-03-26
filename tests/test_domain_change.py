"""Tests for domain change workflow — security filing check + DNS + SSL + notification."""

from unittest.mock import AsyncMock, patch

import pytest

from models.pipeline_record import PipelineRecord
from workflows.domain_change import execute_domain_change


@pytest.mark.asyncio
class TestDomainChangeWorkflow:
    async def test_rejects_without_security_filing(self, db, mock_notifier):
        """Domain change must be rejected if security filing is not done."""
        with pytest.raises(ValueError, match="等保备案"):
            await execute_domain_change(
                db=db,
                lark_approval_id="approval_d001",
                applicant="user_001",
                service_name="order-service",
                current_domain="order-service-abc123.test.hep.com.cn",
                formal_domain="order.hep.com.cn",
                environment="测试环境",
                security_filing="否",
                security_filing_proof=None,
            )

        mock_notifier["failure"].assert_called_once()
        call_args = mock_notifier["failure"].call_args
        assert "等保备案" in call_args.args[1]

    async def test_rejects_missing_security_filing(self, db, mock_notifier):
        """Missing (None) security filing should also be rejected."""
        with pytest.raises(ValueError, match="等保备案"):
            await execute_domain_change(
                db=db,
                lark_approval_id="approval_d002",
                applicant="user_001",
                service_name="order-service",
                current_domain=None,
                formal_domain="order.hep.com.cn",
                environment="测试环境",
                security_filing=None,
                security_filing_proof=None,
            )

    async def test_successful_domain_change(self, db, mock_notifier):
        # Pre-create a pipeline record to update
        record = PipelineRecord(
            service_name="payment",
            gitee_repo="https://gitee.com/hep/payment",
            branch="main",
            language="java_maven",
            environment="test",
            temp_domain="payment-abc123.test.hep.com.cn",
            lark_approval_id="approval_original",
            applicant="user_001",
            status="success",
        )
        db.add(record)
        await db.commit()

        with (
            patch(
                "workflows.domain_change.find_dns_record",
                new_callable=AsyncMock,
                return_value="dns_record_001",
            ),
            patch("workflows.domain_change.delete_dns_record", new_callable=AsyncMock) as mock_delete,
            patch("workflows.domain_change.add_dns_record", new_callable=AsyncMock) as mock_add,
            patch(
                "workflows.domain_change.apply_ssl_certificate",
                new_callable=AsyncMock,
                return_value="order_ssl_001",
            ),
        ):
            await execute_domain_change(
                db=db,
                lark_approval_id="approval_d003",
                applicant="user_001",
                service_name="payment",
                current_domain="payment-abc123.test.hep.com.cn",
                formal_domain="payment.hep.com.cn",
                environment="测试环境",
                security_filing="是",
                security_filing_proof="https://example.com/proof.pdf",
            )

            # Old DNS record should be deleted
            mock_delete.assert_called_once_with("dns_record_001")

            # New DNS record should be created
            mock_add.assert_called_once()
            add_args = mock_add.call_args
            assert add_args.kwargs["subdomain"] == "payment"

        # Pipeline record should have final_domain updated
        from sqlalchemy import select

        result = await db.execute(
            select(PipelineRecord).where(PipelineRecord.service_name == "payment")
        )
        pipeline = result.scalar_one()
        assert pipeline.final_domain == "payment.hep.com.cn"

        # Domain change notification
        mock_notifier["domain_changed"].assert_called_once()

    async def test_missing_service_name_raises(self, db):
        with pytest.raises(ValueError, match="缺少必填字段"):
            await execute_domain_change(
                db=db,
                lark_approval_id="approval_d004",
                applicant="user_001",
                service_name=None,
                current_domain=None,
                formal_domain="test.hep.com.cn",
                environment="测试环境",
                security_filing="是",
                security_filing_proof=None,
            )

    async def test_no_old_dns_record_skips_deletion(self, db, mock_notifier):
        """If old DNS record doesn't exist, skip deletion and continue."""
        with (
            patch(
                "workflows.domain_change.find_dns_record",
                new_callable=AsyncMock,
                return_value=None,
            ),
            patch("workflows.domain_change.delete_dns_record", new_callable=AsyncMock) as mock_delete,
            patch("workflows.domain_change.add_dns_record", new_callable=AsyncMock),
            patch("workflows.domain_change.apply_ssl_certificate", new_callable=AsyncMock),
        ):
            await execute_domain_change(
                db=db,
                lark_approval_id="approval_d005",
                applicant="user_001",
                service_name="new-svc",
                current_domain="old.test.hep.com.cn",
                formal_domain="new-svc.hep.com.cn",
                environment="测试环境",
                security_filing="是",
                security_filing_proof="proof",
            )

            # delete should NOT be called since find returned None
            mock_delete.assert_not_called()
