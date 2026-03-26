"""Tests for workflow routing — approval code → correct workflow dispatch."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from config import settings


@pytest.fixture
def approval_codes():
    """Set up approval codes for routing tests."""
    original = (
        settings.lark_approval_pipeline,
        settings.lark_approval_resource,
        settings.lark_approval_domain,
    )
    settings.lark_approval_pipeline = "PIPELINE_CODE"
    settings.lark_approval_resource = "RESOURCE_CODE"
    settings.lark_approval_domain = "DOMAIN_CODE"
    yield
    (
        settings.lark_approval_pipeline,
        settings.lark_approval_resource,
        settings.lark_approval_domain,
    ) = original


MOCK_FORM = [
    {"name": "项目名称", "value": "test-svc"},
    {"name": "Gitee 仓库地址", "value": "https://gitee.com/hep/test"},
    {"name": "分支名", "value": "main"},
    {"name": "语言类型", "value": '"Java Maven"'},
    {"name": "部署环境", "value": '"测试环境"'},
]

MOCK_RESOURCE_FORM = [
    {"name": "云厂商", "value": '"阿里云"'},
    {"name": "资源类型", "value": '"RDS MySQL"'},
    {"name": "规格", "value": '"4核8G"'},
    {"name": "用途说明", "value": "数据库"},
    {"name": "关联项目", "value": "test"},
    {"name": "项目立项否", "value": '"是"'},
    {"name": "立项签报截图/链接", "value": ""},
]

MOCK_DOMAIN_FORM = [
    {"name": "服务名", "value": "test-svc"},
    {"name": "当前域名", "value": "test-svc-abc123.test.hep.com.cn"},
    {"name": "正式域名名称", "value": "order.hep.com.cn"},
    {"name": "环境", "value": '"测试环境"'},
    {"name": "是否已做过等保备案", "value": '"是"'},
    {"name": "等保备案证明", "value": "https://example.com/proof"},
]


@pytest.mark.asyncio
class TestWorkflowRouting:
    async def test_pipeline_code_dispatches_to_pipeline_setup(self, approval_codes):
        with (
            patch("api.lark_events.get_approval_instance", new_callable=AsyncMock) as mock_get,
            patch("api.lark_events._dispatch_pipeline_setup", new_callable=AsyncMock) as mock_dispatch,
        ):
            mock_get.return_value = {
                "approval_code": "PIPELINE_CODE",
                "status": "APPROVED",
                "form": MOCK_FORM,
                "applicant_id": "user_001",
            }

            from api.lark_events import _handle_approved

            await _handle_approved("instance_001", "PIPELINE_CODE")

            mock_dispatch.assert_called_once_with("instance_001", MOCK_FORM, "user_001")

    async def test_resource_code_dispatches_to_resource_provision(self, approval_codes):
        with (
            patch("api.lark_events.get_approval_instance", new_callable=AsyncMock) as mock_get,
            patch("api.lark_events._dispatch_resource_provision", new_callable=AsyncMock) as mock_dispatch,
        ):
            mock_get.return_value = {
                "approval_code": "RESOURCE_CODE",
                "status": "APPROVED",
                "form": MOCK_RESOURCE_FORM,
                "applicant_id": "user_002",
            }

            from api.lark_events import _handle_approved

            await _handle_approved("instance_002", "RESOURCE_CODE")

            mock_dispatch.assert_called_once_with("instance_002", MOCK_RESOURCE_FORM, "user_002")

    async def test_domain_code_dispatches_to_domain_change(self, approval_codes):
        with (
            patch("api.lark_events.get_approval_instance", new_callable=AsyncMock) as mock_get,
            patch("api.lark_events._dispatch_domain_change", new_callable=AsyncMock) as mock_dispatch,
        ):
            mock_get.return_value = {
                "approval_code": "DOMAIN_CODE",
                "status": "APPROVED",
                "form": MOCK_DOMAIN_FORM,
                "applicant_id": "user_003",
            }

            from api.lark_events import _handle_approved

            await _handle_approved("instance_003", "DOMAIN_CODE")

            mock_dispatch.assert_called_once_with("instance_003", MOCK_DOMAIN_FORM, "user_003")

    async def test_unknown_approval_code_is_ignored(self, approval_codes):
        with (
            patch("api.lark_events.get_approval_instance", new_callable=AsyncMock) as mock_get,
            patch("api.lark_events._dispatch_pipeline_setup", new_callable=AsyncMock) as p,
            patch("api.lark_events._dispatch_resource_provision", new_callable=AsyncMock) as r,
            patch("api.lark_events._dispatch_domain_change", new_callable=AsyncMock) as d,
        ):
            mock_get.return_value = {
                "approval_code": "UNKNOWN_CODE",
                "status": "APPROVED",
                "form": [],
                "applicant_id": "user_004",
            }

            from api.lark_events import _handle_approved

            await _handle_approved("instance_004", "UNKNOWN_CODE")

            p.assert_not_called()
            r.assert_not_called()
            d.assert_not_called()
