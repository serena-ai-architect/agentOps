from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class PipelineRecord(Base):
    """流水线创建记录 — 每次通过飞书审批创建云效流水线的记录"""

    __tablename__ = "pipeline_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    service_name: Mapped[str] = mapped_column(String(255), index=True)
    gitee_repo: Mapped[str] = mapped_column(String(500))
    branch: Mapped[str] = mapped_column(String(100))
    language: Mapped[str] = mapped_column(String(50))  # java_maven, nodejs, python
    environment: Mapped[str] = mapped_column(String(20))  # test, production
    # 云效
    yunxiao_pipeline_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 域名
    temp_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    final_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # 飞书
    lark_approval_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    applicant: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 状态
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/success/failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
