from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """AgentOps — AI-native DevOps platform configuration"""

    model_config = {"env_prefix": "AGENTOPS_", "env_file": ".env"}

    # --- App ---
    debug: bool = False

    # --- Scheduler ---
    expiry_warning_days: int = 7  # 资源到期前多少天开始提醒
    cost_report_day: int = 1  # 每月几号发送成本报表

    # --- Database ---
    database_url: str = "sqlite+aiosqlite:///./agentops.db"

    # --- Lark (飞书) ---
    lark_app_id: str = ""
    lark_app_secret: str = ""
    lark_verification_token: str = ""  # 事件订阅验证 token
    lark_encrypt_key: str = ""  # 事件加密 key
    # 机器人 webhook (用于通知)
    lark_webhook_notify: str = ""  # 通知群 webhook URL
    # 审批模板 approval_code (在飞书管理后台创建后获取)
    lark_approval_pipeline: str = ""  # "新项目部署申请" 模板 code
    lark_approval_resource: str = ""  # "云资源申请" 模板 code
    lark_approval_domain: str = ""  # "域名变更申请" 模板 code
    # 资源到期通知收件人 (飞书 user_id / open_id)
    lark_notify_cloud_admin: str = ""  # 公有云负责人
    lark_notify_it_director: str = ""  # 信息技术部主任杨京峰

    # --- Alibaba Cloud ---
    ali_access_key_id: str = ""
    ali_access_key_secret: str = ""
    ali_region_id: str = "cn-hangzhou"
    # 云效
    ali_devops_org_id: str = ""  # 云效组织 ID
    # ACR
    ali_acr_registry: str = ""  # e.g. registry.cn-hangzhou.aliyuncs.com
    ali_acr_namespace: str = "hep"
    # ACK
    ali_ack_cluster_id: str = ""
    # DNS
    ali_domain_name: str = "hep.com.cn"  # 主域名
    # VPC (资源开通需要)
    ali_vpc_id: str = ""
    ali_vswitch_id: str = ""
    ali_security_group_id: str = ""

    # --- Huawei Cloud ---
    hw_access_key: str = ""
    hw_secret_key: str = ""
    hw_region: str = "cn-north-4"
    hw_project_id: str = ""

    # --- Tencent Cloud ---
    tc_secret_id: str = ""
    tc_secret_key: str = ""
    tc_region: str = "ap-beijing"


settings = Settings()
