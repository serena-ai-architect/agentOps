from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class OperationLog(Base):
    """操作审计日志 — 记录所有自动化操作"""

    __tablename__ = "operation_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(50), index=True)
    # create_pipeline / provision_resource / change_domain
    operator: Mapped[str | None] = mapped_column(String(100), nullable=True)
    lark_approval_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    request_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    response_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    status: Mapped[str] = mapped_column(String(20))  # success / failed
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
