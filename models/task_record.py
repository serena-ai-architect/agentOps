"""任务记录 — 幂等性 + 状态持久化 + 可重试。

解决的核心问题：
1. 飞书 webhook 超时会重发，同一个审批可能收到 2-3 次 → 幂等键去重
2. background_tasks 进程挂了任务就丢 → 任务持久化到数据库
3. 无法观测任务状态 → 完整的状态机（pending → running → success/failed）
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from models.database import Base


class TaskRecord(Base):
    """任务记录 — 每个自动化操作一条记录，幂等键唯一。"""

    __tablename__ = "task_records"

    id: Mapped[int] = mapped_column(primary_key=True)

    # 幂等键 = 飞书审批实例 ID（全局唯一），重复提交直接返回已有任务
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)

    # 任务类型：pipeline / provision / domain
    task_type: Mapped[str] = mapped_column(String(50), index=True)

    # 状态机：pending → running → success / failed
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)

    # 输入/输出
    input_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    output_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # 重试
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)

    # 时间
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
