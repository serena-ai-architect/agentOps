"""Tests for scheduled tasks — resource expiry scanning + cost report aggregation."""

from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest

from models.resource_record import ResourceRecord


def _make_mock_session(db):
    """Create a mock async_session that yields the test db session."""

    @asynccontextmanager
    async def mock_session():
        yield db

    return mock_session


@pytest.mark.asyncio
class TestResourceExpiryScan:
    async def test_finds_expiring_resources(self, db, mock_notifier):
        now = datetime.now(timezone.utc)

        expiring = ResourceRecord(
            cloud_provider="alibaba",
            resource_type="rds_mysql",
            resource_id="rm-expiring",
            resource_name="order-mysql",
            owner="user_001",
            status="success",
            expires_at=now + timedelta(days=3),
        )
        safe = ResourceRecord(
            cloud_provider="alibaba",
            resource_type="redis",
            resource_id="r-safe",
            resource_name="cache-redis",
            owner="user_002",
            status="success",
            expires_at=now + timedelta(days=30),
        )
        expired = ResourceRecord(
            cloud_provider="huawei",
            resource_type="ecs",
            resource_id="ecs-expired",
            resource_name="old-server",
            owner="user_003",
            status="success",
            expires_at=now - timedelta(days=1),
        )
        failed = ResourceRecord(
            cloud_provider="alibaba",
            resource_type="ecs",
            resource_id="ecs-failed",
            resource_name="failed-server",
            owner="user_004",
            status="failed",
            expires_at=now + timedelta(days=2),
        )

        db.add_all([expiring, safe, expired, failed])
        await db.commit()

        with patch("models.database.async_session", _make_mock_session(db)):
            from scheduler import check_resource_expiry

            await check_resource_expiry()

        mock_notifier["expiry_warning"].assert_called_once()
        resources = mock_notifier["expiry_warning"].call_args.args[0]
        assert len(resources) == 1
        assert resources[0]["name"] == "order-mysql"

    async def test_no_expiring_resources_no_notification(self, db, mock_notifier):
        now = datetime.now(timezone.utc)

        safe = ResourceRecord(
            cloud_provider="alibaba",
            resource_type="ecs",
            resource_id="ecs-safe",
            resource_name="safe-server",
            owner="user_001",
            status="success",
            expires_at=now + timedelta(days=60),
        )
        db.add(safe)
        await db.commit()

        with patch("models.database.async_session", _make_mock_session(db)):
            from scheduler import check_resource_expiry

            await check_resource_expiry()

        mock_notifier["expiry_warning"].assert_not_called()


@pytest.mark.asyncio
class TestCostReportAggregation:
    async def test_aggregates_costs_by_provider_and_type(self, db, mock_notifier):
        now = datetime.now(timezone.utc)
        last_month = now - timedelta(days=35)

        resources = [
            ResourceRecord(
                cloud_provider="alibaba",
                resource_type="rds_mysql",
                resource_id="rm-001",
                resource_name="order-mysql",
                status="success",
                monthly_cost_estimate=2500.0,
                created_at=last_month,
            ),
            ResourceRecord(
                cloud_provider="alibaba",
                resource_type="redis",
                resource_id="r-001",
                resource_name="cache-redis",
                status="success",
                monthly_cost_estimate=800.0,
                created_at=last_month,
            ),
            ResourceRecord(
                cloud_provider="huawei",
                resource_type="ascend_gpu",
                resource_id="gpu-001",
                resource_name="train-gpu",
                status="success",
                monthly_cost_estimate=5000.0,
                created_at=last_month,
            ),
        ]
        db.add_all(resources)
        await db.commit()

        with (
            patch("models.database.async_session", _make_mock_session(db)),
            patch("scheduler._fetch_alibaba_bill", new_callable=AsyncMock, return_value=None),
        ):
            from scheduler import send_monthly_cost_report

            await send_monthly_cost_report()

        mock_notifier["cost_report"].assert_called_once()
        call_kwargs = mock_notifier["cost_report"].call_args.kwargs
        assert call_kwargs["total"] == 8300.0
        assert "阿里云" in call_kwargs["by_provider"]
        assert "华为云" in call_kwargs["by_provider"]
        assert call_kwargs["by_provider"]["阿里云"] == 3300.0
        assert call_kwargs["by_provider"]["华为云"] == 5000.0
