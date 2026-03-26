"""Tests for the Lark events API endpoint — URL verification, token validation, event handling."""

from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from config import settings
from main import app


@pytest.mark.asyncio
class TestLarkEventsAPI:
    async def test_health_check(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_url_verification_returns_challenge(self):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/api/lark/events",
                json={"type": "url_verification", "challenge": "test_challenge_123"},
            )
        assert resp.status_code == 200
        assert resp.json() == {"challenge": "test_challenge_123"}

    async def test_invalid_token_rejected(self):
        original = settings.lark_verification_token
        settings.lark_verification_token = "valid_token"

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/api/lark/events",
                    json={
                        "schema": "2.0",
                        "header": {
                            "event_type": "approval_instance",
                            "token": "wrong_token",
                        },
                        "event": {},
                    },
                )
            assert resp.json()["code"] == 401
        finally:
            settings.lark_verification_token = original

    async def test_approved_event_triggers_background_task(self):
        original_token = settings.lark_verification_token
        settings.lark_verification_token = ""  # disable token check for test

        try:
            with patch("api.lark_events._handle_approved", new_callable=AsyncMock) as mock_handle:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/lark/events",
                        json={
                            "schema": "2.0",
                            "header": {"event_type": "approval_instance", "token": ""},
                            "event": {
                                "status": "APPROVED",
                                "approval_code": "test_code",
                                "instance_id": "inst_001",
                            },
                        },
                    )
                assert resp.status_code == 200
                assert resp.json()["code"] == 0
        finally:
            settings.lark_verification_token = original_token

    async def test_non_approved_status_ignored(self):
        original_token = settings.lark_verification_token
        settings.lark_verification_token = ""

        try:
            with patch("api.lark_events._handle_approved", new_callable=AsyncMock) as mock_handle:
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    resp = await client.post(
                        "/api/lark/events",
                        json={
                            "schema": "2.0",
                            "header": {"event_type": "approval_instance", "token": ""},
                            "event": {
                                "status": "REJECTED",
                                "approval_code": "test_code",
                                "instance_id": "inst_002",
                            },
                        },
                    )
                assert resp.json()["code"] == 0
                mock_handle.assert_not_called()
        finally:
            settings.lark_verification_token = original_token
