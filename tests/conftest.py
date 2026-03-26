"""Shared fixtures for AgentOps tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def db():
    """In-memory SQLite database for testing."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def mock_notifier():
    """Mock all Lark notification functions."""
    with (
        patch("lark.notifier.notify_success", new_callable=AsyncMock) as success,
        patch("lark.notifier.notify_failure", new_callable=AsyncMock) as failure,
        patch("lark.notifier.notify_resource_created", new_callable=AsyncMock) as resource,
        patch("lark.notifier.notify_domain_changed", new_callable=AsyncMock) as domain,
        patch("lark.notifier.notify_expiry_warning", new_callable=AsyncMock) as expiry,
        patch("lark.notifier.notify_cost_report", new_callable=AsyncMock) as cost,
    ):
        yield {
            "success": success,
            "failure": failure,
            "resource_created": resource,
            "domain_changed": domain,
            "expiry_warning": expiry,
            "cost_report": cost,
        }
