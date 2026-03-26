"""Tests for Lark approval form parsing — extract_form_value()."""

import pytest

from lark.client import extract_form_value


# --- Fixtures: sample form data ---

SAMPLE_FORM = [
    {"id": "widget_001", "name": "项目名称", "type": "input", "value": "order-service"},
    {"id": "widget_002", "name": "Gitee 仓库地址", "type": "input", "value": "https://gitee.com/hep/order-service"},
    {"id": "widget_003", "name": "分支名", "type": "input", "value": "main"},
    {"id": "widget_004", "name": "语言类型", "type": "radioV2", "value": '"Java Maven"'},
    {"id": "widget_005", "name": "部署环境", "type": "radioV2", "value": '"测试环境"'},
    {"id": "widget_006", "name": "备注", "type": "textarea", "value": ""},
]

RESOURCE_FORM = [
    {"id": "widget_010", "name": "云厂商", "type": "radioV2", "value": '"阿里云"'},
    {"id": "widget_011", "name": "资源类型", "type": "radioV2", "value": '"RDS MySQL"'},
    {"id": "widget_012", "name": "规格", "type": "radioV2", "value": '"4核8G"'},
    {"id": "widget_013", "name": "用途说明", "type": "textarea", "value": "订单服务数据库"},
    {"id": "widget_014", "name": "关联项目", "type": "input", "value": "order"},
    {"id": "widget_015", "name": "项目立项否", "type": "radioV2", "value": '"是"'},
]


class TestExtractFormValue:
    def test_extract_plain_text(self):
        result = extract_form_value(SAMPLE_FORM, "项目名称")
        assert result == "order-service"

    def test_extract_url(self):
        result = extract_form_value(SAMPLE_FORM, "Gitee 仓库地址")
        assert result == "https://gitee.com/hep/order-service"

    def test_extract_radio_value_unquoted(self):
        """Radio (select) values come as JSON-quoted strings like '"Java Maven"'."""
        result = extract_form_value(SAMPLE_FORM, "语言类型")
        assert result == "Java Maven"

    def test_extract_radio_value_chinese(self):
        result = extract_form_value(SAMPLE_FORM, "部署环境")
        assert result == "测试环境"

    def test_extract_empty_value(self):
        result = extract_form_value(SAMPLE_FORM, "备注")
        assert result == ""

    def test_extract_nonexistent_field(self):
        result = extract_form_value(SAMPLE_FORM, "不存在的字段")
        assert result is None

    def test_extract_empty_form(self):
        result = extract_form_value([], "项目名称")
        assert result is None

    def test_extract_resource_provider(self):
        result = extract_form_value(RESOURCE_FORM, "云厂商")
        assert result == "阿里云"

    def test_extract_resource_type(self):
        result = extract_form_value(RESOURCE_FORM, "资源类型")
        assert result == "RDS MySQL"

    def test_extract_boolean_radio(self):
        result = extract_form_value(RESOURCE_FORM, "项目立项否")
        assert result == "是"

    def test_malformed_json_string_returned_as_is(self):
        """If a value starts with " but isn't valid JSON, return as-is."""
        form = [{"name": "test", "value": '"unclosed'}]
        result = extract_form_value(form, "test")
        assert result == '"unclosed'
