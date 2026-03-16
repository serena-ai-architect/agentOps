"""飞书审批模板字段定义 — 定义各模板的表单字段名称，用于解析审批数据。

这些字段名需要和飞书管理后台创建的审批模板保持一致。
"""


class PipelineApproval:
    """新项目部署申请 — 审批模板字段"""

    SERVICE_NAME = "项目名称"
    GITEE_REPO = "Gitee 仓库地址"
    BRANCH = "分支名"
    LANGUAGE = "语言类型"  # Java Maven / Java Gradle / Node.js / Python
    ENVIRONMENT = "部署环境"  # 测试环境 / 生产环境
    NOTES = "备注"


class ResourceApproval:
    """云资源申请 — 审批模板字段（由业务负责人在写代码前提交）"""

    CLOUD_PROVIDER = "云厂商"  # 阿里云 / 华为云 / 腾讯云
    RESOURCE_TYPE = "资源类型"  # RDS MySQL / Redis / ECS / OSS / GPU(昇腾) / ...
    SPEC = "规格"  # 如 "4核8G", "4G Redis", "昇腾910B x2"
    PURPOSE = "用途说明"
    PROJECT = "关联项目"
    PROJECT_ESTABLISHED = "项目立项否"  # 单选: 是 / 否
    PROJECT_REPORT = "立项签报截图/链接"  # 附件或链接


class DomainApproval:
    """域名变更申请 — 用于将自动分配的域名替换为已备案的正式域名"""

    SERVICE_NAME = "服务名"
    CURRENT_DOMAIN = "当前域名"
    FORMAL_DOMAIN = "正式域名名称"  # 已申请的正式域名
    ENVIRONMENT = "环境"  # 测试环境 / 生产环境
    SECURITY_FILING = "是否已做过等保备案"  # 单选: 是 / 否
    SECURITY_FILING_PROOF = "等保备案证明"  # 附件或链接
