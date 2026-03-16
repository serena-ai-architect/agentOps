from datetime import datetime

from sqlalchemy import DateTime, Float, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class ResourceRecord(Base):
    """云资源台账 — 记录所有通过自动化开通的云资源"""

    __tablename__ = "resource_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    cloud_provider: Mapped[str] = mapped_column(String(20), index=True)  # alibaba/huawei/tencent
    resource_type: Mapped[str] = mapped_column(String(50), index=True)  # rds/redis/ecs/gpu/oss
    resource_id: Mapped[str | None] = mapped_column(String(200), nullable=True)  # 云厂商返回的 ID
    resource_name: Mapped[str] = mapped_column(String(255))
    spec: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 规格描述
    connection_info: Mapped[str | None] = mapped_column(Text, nullable=True)  # 连接信息 (加密)
    monthly_cost_estimate: Mapped[float | None] = mapped_column(Float, nullable=True)
    # 归属
    owner: Mapped[str | None] = mapped_column(String(100), nullable=True)  # 业务负责人(申请人)
    project: Mapped[str | None] = mapped_column(String(255), nullable=True)  # 关联项目
    # 立项信息
    project_established: Mapped[bool] = mapped_column(default=False)  # 是否已立项
    project_report_url: Mapped[str | None] = mapped_column(Text, nullable=True)  # 立项签报链接
    # 飞书
    lark_approval_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 计费与到期
    billing_type: Mapped[str] = mapped_column(String(20), default="PostPaid")  # PostPaid/PrePaid
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
