# AgentOps 架构设计 — 并发 + 云

> 任何人都能做一个 12306，但能做到并发只有专业程序员。
> 面向 AI 设计：AI Agent 能安全地并发操作多朵云。

---

## 核心矛盾

| 维度 | 现状（玩具） | 目标（生产） |
|------|-------------|-------------|
| 并发 | `background_tasks.add_task()` 裸跑 | 有锁、有队列、有幂等、有限流 |
| 云 | 三朵云各写各的 client | 统一抽象、一键切换、自动 failover |
| 数据安全 | 无备份、无冗余 | 跨云备份、定期快照、可恢复 |
| AI 可操作性 | 面向人的 webhook | 面向 AI 的状态机 + 幂等 API |

---

## 第一根柱子：并发

### 问题拆解

```
并发
├── 幂等性      → 同一个请求执行多次 = 执行一次（飞书 webhook 必然重试）
├── 资源锁      → 同一个项目同时申请两个 Redis，只能创建一个
├── 任务队列    → 不再 fire-and-forget，任务持久化 + 可重试 + 可观测
├── 速率限制    → 云 API QPS 限制，必须排队
└── 数据库      → SQLite → PostgreSQL（并发写 + 事务隔离）
```

### 1.1 幂等性（Idempotency）

**12306 的教训**：用户点了两次"购买"，不能出两张票。

AgentOps 的等价问题：飞书 webhook 超时会重发，同一个 `instance_id` 可能收到 2-3 次。

```python
# 幂等键 = 飞书审批实例 ID（全局唯一）
# 方案：数据库唯一约束 + 状态检查

class TaskRecord(Base):
    """任务记录 — 每个幂等操作一条记录"""
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(200), unique=True, index=True  # 飞书 instance_id
    )
    task_type: Mapped[str]          # provision / pipeline / domain / backup / migrate
    state: Mapped[str]              # pending → running → success / failed / cancelled
    input_data: Mapped[str]         # JSON — 完整的请求参数
    output_data: Mapped[str | None] # JSON — 执行结果
    error: Mapped[str | None]
    retry_count: Mapped[int] = mapped_column(default=0)
    max_retries: Mapped[int] = mapped_column(default=3)
    locked_by: Mapped[str | None]   # worker ID（谁在执行）
    locked_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

```python
# 入口逻辑
async def submit_task(idempotency_key: str, task_type: str, input_data: dict) -> TaskRecord:
    """提交任务 — 幂等。重复提交直接返回已有任务。"""
    existing = await db.get_by_key(idempotency_key)
    if existing:
        return existing  # 幂等：直接返回，不重复执行

    task = TaskRecord(
        idempotency_key=idempotency_key,
        task_type=task_type,
        state="pending",
        input_data=json.dumps(input_data),
    )
    db.add(task)
    await db.commit()
    return task
```

### 1.2 资源锁（Distributed Locking）

**问题**：两个 AI Agent 同时帮 order-service 开 Redis，会创建两个实例。

```python
# 锁键 = 项目名 + 资源类型
# 方案：数据库行级锁（PostgreSQL Advisory Lock）

class ResourceLock:
    """基于 PostgreSQL Advisory Lock 的分布式锁"""

    @staticmethod
    def lock_key(project: str, resource_type: str) -> int:
        """生成锁 ID — 基于项目名+资源类型的哈希"""
        raw = f"{project}:{resource_type}"
        return int(hashlib.sha256(raw.encode()).hexdigest()[:15], 16)

    async def acquire(self, db: AsyncSession, project: str, resource_type: str) -> bool:
        """尝试获取锁，非阻塞。返回 True/False。"""
        key = self.lock_key(project, resource_type)
        result = await db.execute(text(f"SELECT pg_try_advisory_lock({key})"))
        return result.scalar()

    async def release(self, db: AsyncSession, project: str, resource_type: str):
        key = self.lock_key(project, resource_type)
        await db.execute(text(f"SELECT pg_advisory_unlock({key})"))
```

```python
# 使用
async def execute_resource_provision(...):
    lock = ResourceLock()
    if not await lock.acquire(db, project, resource_type):
        raise ConflictError(f"{project} 的 {resource_type} 正在创建中，请勿重复提交")
    try:
        result = await _provision(...)
    finally:
        await lock.release(db, project, resource_type)
```

### 1.3 任务队列（Task Queue）

**现状**：`background_tasks.add_task()` — 进程挂了任务就丢了，无法重试，无法观测。

**目标架构**：

```
飞书 webhook → FastAPI → 写入任务表（pending）→ 立即返回 200
                                    ↓
                            TaskWorker 轮询（或被通知）
                                    ↓
                          取任务 → 加锁 → 执行 → 更新状态
                                    ↓
                           成功 → 通知飞书    失败 → 重试/告警
```

```python
class TaskWorker:
    """任务消费者 — 从数据库取 pending 任务执行。

    为什么不用 Celery/Redis？
    - AgentOps 的并发量级是 10-100/天，不是 10000/秒
    - 数据库队列足够，且减少基础设施依赖
    - 任务状态天然持久化，重启不丢失
    """

    def __init__(self, worker_id: str, concurrency: int = 5):
        self.worker_id = worker_id
        self.semaphore = asyncio.Semaphore(concurrency)  # 最大并发数
        self.running = False

    async def run(self):
        """主循环 — 持续拉取并执行任务。"""
        self.running = True
        while self.running:
            tasks = await self._fetch_pending_tasks(limit=self.semaphore._value)
            if not tasks:
                await asyncio.sleep(1)  # 无任务时等 1 秒
                continue

            # 并发执行（受 semaphore 限制）
            await asyncio.gather(*[
                self._execute_with_semaphore(task) for task in tasks
            ])

    async def _fetch_pending_tasks(self, limit: int) -> list[TaskRecord]:
        """原子地获取并锁定待执行任务。

        SELECT ... WHERE state = 'pending' AND locked_by IS NULL
        FOR UPDATE SKIP LOCKED  ← 关键：跳过已被其他 worker 锁定的行
        LIMIT N
        """
        async with async_session() as db:
            stmt = (
                select(TaskRecord)
                .where(TaskRecord.state == "pending", TaskRecord.locked_by.is_(None))
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
            result = await db.execute(stmt)
            tasks = result.scalars().all()

            for task in tasks:
                task.state = "running"
                task.locked_by = self.worker_id
                task.locked_at = datetime.now(UTC)

            await db.commit()
            return tasks

    async def _execute_with_semaphore(self, task: TaskRecord):
        async with self.semaphore:
            await self._execute(task)
```

### 1.4 速率限制（Rate Limiting）

**问题**：阿里云 API 大多限制 20-50 QPS，华为云更低。10 个任务并发打过去 → 全部 429。

```python
class CloudRateLimiter:
    """令牌桶限流器 — 按云厂商分别限速。"""

    def __init__(self):
        self._limiters: dict[str, TokenBucket] = {
            "alibaba": TokenBucket(rate=20, capacity=20),   # 20 QPS
            "huawei": TokenBucket(rate=10, capacity=10),     # 10 QPS
            "tencent": TokenBucket(rate=15, capacity=15),    # 15 QPS
        }

    async def acquire(self, provider: str):
        """等待直到获得令牌。"""
        limiter = self._limiters.get(provider)
        if limiter:
            await limiter.wait()


class TokenBucket:
    """异步令牌桶"""

    def __init__(self, rate: float, capacity: int):
        self.rate = rate          # 每秒补充的令牌数
        self.capacity = capacity  # 桶容量
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def wait(self):
        while True:
            async with self._lock:
                self._refill()
                if self.tokens >= 1:
                    self.tokens -= 1
                    return
            await asyncio.sleep(1 / self.rate)  # 等一个令牌的时间

    def _refill(self):
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_refill = now
```

### 1.5 数据库升级

```
SQLite（现状）          →    PostgreSQL（目标）
─────────────────────       ─────────────────────
单文件，开发方便              并发写入无锁冲突
并发写入互斥                  Advisory Lock = 分布式锁
无 SKIP LOCKED               FOR UPDATE SKIP LOCKED
无行级锁                      MVCC 事务隔离
```

`config.py` 变更：
```python
# 现状
database_url: str = "sqlite+aiosqlite:///./agentops.db"

# 目标 — 开发仍可用 SQLite，生产用 PostgreSQL
database_url: str = "postgresql+asyncpg://agentops:***@localhost:5432/agentops"
```

### 并发架构总图

```
                    ┌─────────────────────────┐
                    │        飞书 Webhook       │
                    │    (可能重发 2-3 次)       │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │     FastAPI Endpoint     │
                    │                         │
                    │  1. 幂等检查             │
                    │     (idempotency_key)    │
                    │  2. 写入 tasks 表        │
                    │     (state=pending)      │
                    │  3. 返回 200             │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │      TaskWorker(s)       │
                    │                         │
                    │  SELECT ... FOR UPDATE   │
                    │  SKIP LOCKED             │
                    │                         │
                    │  ┌──┐ ┌──┐ ┌──┐ ┌──┐   │
                    │  │T1│ │T2│ │T3│ │T4│   │  ← semaphore 控制并发数
                    │  └──┘ └──┘ └──┘ └──┘   │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │    CloudRateLimiter      │
                    │                         │
                    │  alibaba: 20 QPS ████░  │
                    │  huawei:  10 QPS ██░░░  │
                    │  tencent: 15 QPS ███░░  │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │      ResourceLock        │
                    │                         │
                    │  pg_advisory_lock(key)   │
                    │  同项目同资源 = 互斥      │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │     Cloud API 调用       │
                    │                         │
                    │  创建资源 / 备份 / 迁移   │
                    └───────────┬─────────────┘
                                │
                    ┌───────────▼─────────────┐
                    │     更新 tasks 表        │
                    │  state=success/failed    │
                    │  → 飞书通知结果           │
                    └─────────────────────────┘
```

---

## 第二根柱子：云

### 问题拆解

```
云
├── 抽象层      → 统一接口，屏蔽三朵云的 API 差异
├── 切换        → 资源可以从 A 云迁到 B 云（数据 + DNS + 连接串）
├── 备份        → 关键数据跨云冗余，不依赖单一云厂商的备份
├── failover    → A 云 API 挂了，自动降级到 B 云
└── 可观测      → AI Agent 能查到每朵云的健康状态和资源清单
```

### 2.1 云抽象层（Cloud Abstraction Layer）

**当前代码的问题**：

```python
# resource_provision.py — 每加一种资源就要改三个 if-elif 分支
if provider_code == "alibaba":
    result = await _provision_alibaba(type_code, spec, project)
elif provider_code == "huawei":
    result = await _provision_huawei(type_code, spec, project)
elif provider_code == "tencent":
    result = await _provision_tencent(type_code, spec, project)
```

**目标设计 — Provider 接口**：

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class CloudProvider(str, Enum):
    ALIBABA = "alibaba"
    HUAWEI = "huawei"
    TENCENT = "tencent"


@dataclass
class CloudResource:
    """统一资源描述 — 屏蔽云差异。"""
    provider: CloudProvider
    resource_type: str         # rds_mysql / redis / ecs / oss / ...
    resource_id: str           # 云厂商返回的实例 ID
    name: str
    region: str
    spec: str                  # 规格描述
    connection_info: dict      # {"host": "...", "port": 3306, "password": "..."}
    status: str                # running / stopped / creating / error
    monthly_cost: float | None
    metadata: dict             # 云厂商特有信息


@dataclass
class BackupRecord:
    """统一备份描述。"""
    backup_id: str
    source: CloudResource
    backup_type: str           # snapshot / logical / physical
    storage_location: str      # 备份存储位置（可能是另一朵云的 OSS）
    size_bytes: int
    created_at: datetime
    expires_at: datetime | None


class CloudProviderInterface(ABC):
    """云厂商统一接口 — 所有云必须实现这些方法。

    为什么用接口而不是 adapter？
    - 接口强制每朵云实现完整能力，不会遗漏
    - AI Agent 只需要知道这一组接口，不需要了解具体云的 API
    """

    @abstractmethod
    async def create_resource(self, resource_type: str, name: str,
                              spec: str, **kwargs) -> CloudResource:
        """创建资源。"""

    @abstractmethod
    async def delete_resource(self, resource_id: str, resource_type: str) -> bool:
        """删除资源。"""

    @abstractmethod
    async def get_resource(self, resource_id: str, resource_type: str) -> CloudResource:
        """查询资源状态。"""

    @abstractmethod
    async def list_resources(self, resource_type: str | None = None) -> list[CloudResource]:
        """列出所有资源。"""

    # --- 备份 ---
    @abstractmethod
    async def create_backup(self, resource_id: str, resource_type: str) -> BackupRecord:
        """创建备份/快照。"""

    @abstractmethod
    async def restore_backup(self, backup_id: str, target_name: str) -> CloudResource:
        """从备份恢复。"""

    @abstractmethod
    async def list_backups(self, resource_id: str) -> list[BackupRecord]:
        """列出资源的所有备份。"""

    # --- 数据导出（用于跨云迁移）---
    @abstractmethod
    async def export_data(self, resource_id: str, resource_type: str,
                          target_oss_url: str) -> str:
        """导出数据到对象存储（用于跨云迁移）。返回导出任务 ID。"""

    @abstractmethod
    async def import_data(self, resource_id: str, resource_type: str,
                          source_oss_url: str) -> str:
        """从对象存储导入数据。返回导入任务 ID。"""

    # --- 健康检查 ---
    @abstractmethod
    async def health_check(self) -> dict:
        """检查该云厂商 API 是否可用。返回 {"healthy": bool, "latency_ms": int, ...}"""
```

### 2.2 Provider 注册中心

```python
class CloudRegistry:
    """云厂商注册中心 — 统一入口。

    AI Agent 不需要知道用的是哪朵云，只需要说"帮我开一个 Redis"。
    注册中心根据策略自动选择最合适的云。
    """

    def __init__(self):
        self._providers: dict[CloudProvider, CloudProviderInterface] = {}
        self._health_cache: dict[CloudProvider, dict] = {}

    def register(self, provider: CloudProvider, impl: CloudProviderInterface):
        self._providers[provider] = impl

    def get(self, provider: CloudProvider) -> CloudProviderInterface:
        return self._providers[provider]

    async def select_best_provider(
        self,
        resource_type: str,
        preferences: dict | None = None,
    ) -> CloudProvider:
        """智能选云 — AI Agent 可以不指定云厂商，系统自动选。

        决策因素：
        1. 该云是否支持该资源类型
        2. 该云当前是否健康
        3. 成本偏好
        4. 合规要求（如数据必须在境内）
        5. 已有资源的亲和性（同项目尽量在同一朵云，减少跨云网络开销）
        """
        candidates = []
        for provider, impl in self._providers.items():
            health = await self._get_health(provider)
            if not health.get("healthy"):
                continue
            # 检查是否支持该资源类型
            if resource_type in self._get_supported_types(provider):
                candidates.append((provider, health))

        if not candidates:
            raise NoHealthyProviderError(f"没有可用的云厂商支持 {resource_type}")

        # 默认优先阿里云（70% 业务在阿里云），可通过 preferences 覆盖
        preferred = preferences.get("provider") if preferences else None
        if preferred:
            preferred_enum = CloudProvider(preferred)
            if any(c[0] == preferred_enum for c in candidates):
                return preferred_enum

        # 按延迟排序
        candidates.sort(key=lambda c: c[1].get("latency_ms", 9999))
        return candidates[0][0]

    # 资源类型支持矩阵
    CAPABILITY_MATRIX = {
        CloudProvider.ALIBABA: [
            "rds_mysql", "rds_postgresql", "redis", "ecs", "oss", "slb", "sae",
        ],
        CloudProvider.HUAWEI: [
            "rds_mysql", "redis", "ecs", "ascend_gpu",
        ],
        CloudProvider.TENCENT: [
            "rds_mysql", "redis", "ecs", "cos",
        ],
    }
```

### 2.3 云切换 — 迁移工作流

```
迁移不是"删了重建"，是一个状态机：

    ┌─────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌─────────┐
    │ 准备阶段  │ →  │ 数据同步  │ →  │ 验证阶段  │ →  │ 切换阶段  │ →  │ 清理阶段 │
    │          │    │          │    │          │    │          │    │         │
    │ 在目标云  │    │ 源 → 目标 │    │ 数据一致性│    │ DNS 切换  │    │ 删除源  │
    │ 创建空实例│    │ 全量+增量 │    │ 连通性测试│    │ 连接串更新│    │ 资源    │
    └─────────┘    └──────────┘    └──────────┘    └──────────┘    └─────────┘
        ↑               ↑              ↑               ↑              ↑
        任何阶段失败都可以回滚，源资源始终保留到最后确认
```

```python
class MigrationState(str, Enum):
    """迁移状态机 — 每一步都可审计、可回滚。"""
    CREATED = "created"                # 迁移任务已创建
    PREPARING = "preparing"            # 在目标云创建空实例
    PREPARED = "prepared"              # 目标实例就绪
    SYNCING = "syncing"                # 数据同步中（全量）
    SYNCED = "synced"                  # 全量同步完成
    INCREMENTAL_SYNC = "incr_sync"     # 增量同步中
    VALIDATING = "validating"          # 验证数据一致性
    VALIDATED = "validated"            # 验证通过
    SWITCHING = "switching"            # DNS/连接串切换中
    SWITCHED = "switched"              # 切换完成
    CLEANING = "cleaning"              # 清理旧资源
    COMPLETED = "completed"            # 迁移完成
    FAILED = "failed"                  # 失败（可查看 error 字段）
    ROLLED_BACK = "rolled_back"        # 已回滚


class MigrationRecord(Base):
    """迁移记录 — 完整跟踪一次云切换"""
    __tablename__ = "migrations"

    id: Mapped[int] = mapped_column(primary_key=True)
    # 源
    source_provider: Mapped[str]
    source_resource_id: Mapped[str]
    source_resource_type: Mapped[str]
    # 目标
    target_provider: Mapped[str]
    target_resource_id: Mapped[str | None]
    # 状态机
    state: Mapped[str] = mapped_column(default=MigrationState.CREATED)
    state_history: Mapped[str]  # JSON array: [{"state": "...", "at": "...", "detail": "..."}]
    # 数据
    data_sync_task_id: Mapped[str | None]
    validation_result: Mapped[str | None]  # JSON
    # 回滚
    rollback_available: Mapped[bool] = mapped_column(default=True)
    rollback_deadline: Mapped[datetime | None]  # 过了这个时间源资源被清理
```

### 2.4 备份策略

**原则**：备份不能和数据在同一朵云。阿里云 region 级故障 → 如果备份也在阿里云，等于没备份。

```
备份层次：

    Level 0: 云厂商自带备份（RDS 自动备份、Redis AOF）
             → 防误删、防逻辑错误
             → 无法防云厂商级故障

    Level 1: 跨 region 备份（同云不同地域）
             → 防单 region 故障
             → 无法防云厂商整体故障（罕见但发生过）

    Level 2: 跨云备份（阿里云数据备份到华为云/腾讯云 OSS）
             → 最高安全等级
             → 成本最高
```

```python
@dataclass
class BackupPolicy:
    """备份策略 — 按资源类型和重要性配置。"""
    resource_type: str
    level: int                  # 0 / 1 / 2
    frequency: str              # "daily" / "hourly" / "weekly"
    retention_days: int         # 保留天数
    cross_cloud_target: CloudProvider | None  # Level 2 时备份到哪朵云
    cross_region_target: str | None           # Level 1 时备份到哪个 region


# 默认策略
DEFAULT_BACKUP_POLICIES = {
    "rds_mysql": BackupPolicy(
        resource_type="rds_mysql",
        level=2,                          # 数据库 = 最高等级
        frequency="daily",
        retention_days=30,
        cross_cloud_target=CloudProvider.HUAWEI,  # 阿里云 MySQL → 备份到华为云 OBS
        cross_region_target="cn-shanghai",
    ),
    "redis": BackupPolicy(
        resource_type="redis",
        level=1,                          # 缓存 = 中等（可重建）
        frequency="daily",
        retention_days=7,
        cross_cloud_target=None,
        cross_region_target="cn-shanghai",
    ),
    "ecs": BackupPolicy(
        resource_type="ecs",
        level=1,
        frequency="weekly",
        retention_days=14,
        cross_cloud_target=None,
        cross_region_target="cn-shanghai",
    ),
    "oss": BackupPolicy(
        resource_type="oss",
        level=2,                          # 对象存储 = 最高等级
        frequency="daily",
        retention_days=90,
        cross_cloud_target=CloudProvider.TENCENT,  # 阿里云 OSS → 腾讯云 COS
        cross_region_target=None,
    ),
}
```

### 跨云备份流程

```
                        ┌──────────────────┐
                        │  BackupScheduler  │
                        │  (定时触发)        │
                        └────────┬─────────┘
                                 │
                    ┌────────────▼────────────┐
                    │  查询 backup_policies    │
                    │  匹配需要备份的资源       │
                    └────────────┬────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                   ▼
     ┌────────────────┐ ┌────────────────┐ ┌────────────────┐
     │ Level 0        │ │ Level 1        │ │ Level 2        │
     │ 云厂商自带快照  │ │ 导出 → 跨region│ │ 导出 → 跨云    │
     │ (调 backup API)│ │ 上传到同云OSS  │ │ 上传到另一云OSS │
     └───────┬────────┘ └───────┬────────┘ └───────┬────────┘
             │                  │                   │
             └──────────────────┼───────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  记录 backup_records   │
                    │  → 飞书通知备份完成     │
                    │  → 检查过期备份并清理   │
                    └───────────────────────┘
```

### 2.5 健康检查 + Failover

```python
class CloudHealthMonitor:
    """持续监测各云厂商 API 健康状态。

    AI Agent 决策的依据：哪朵云现在能用？
    """

    def __init__(self, registry: CloudRegistry, check_interval: int = 60):
        self.registry = registry
        self.check_interval = check_interval
        self._status: dict[CloudProvider, HealthStatus] = {}

    async def run(self):
        """持续健康检查循环。"""
        while True:
            for provider in CloudProvider:
                try:
                    impl = self.registry.get(provider)
                    result = await asyncio.wait_for(
                        impl.health_check(),
                        timeout=10,
                    )
                    self._status[provider] = HealthStatus(
                        provider=provider,
                        healthy=result["healthy"],
                        latency_ms=result["latency_ms"],
                        last_check=datetime.now(UTC),
                        consecutive_failures=0,
                    )
                except Exception as e:
                    current = self._status.get(provider)
                    failures = (current.consecutive_failures + 1) if current else 1
                    self._status[provider] = HealthStatus(
                        provider=provider,
                        healthy=False,
                        latency_ms=-1,
                        last_check=datetime.now(UTC),
                        consecutive_failures=failures,
                        error=str(e),
                    )
                    # 连续 3 次失败 → 告警
                    if failures == 3:
                        await self._alert_unhealthy(provider, str(e))

            await asyncio.sleep(self.check_interval)

    def get_healthy_providers(self) -> list[CloudProvider]:
        """返回当前健康的云厂商列表。"""
        return [p for p, s in self._status.items() if s.healthy]
```

---

## 面向 AI 的设计原则

上面两根柱子解决的是"系统怎么不崩"，但还有一个维度：**AI Agent 怎么安全地操作这个系统**。

### 为什么 AI 需要特殊设计？

```
人类操作                              AI Agent 操作
──────────                           ──────────────
看到报错会停下来想                     可能无限重试
一次只做一件事                         可能同时做 10 件事
有直觉判断风险                         需要明确的规则判断风险
忘了也能问同事                         需要完整的状态可查询
```

### 原则 1：所有操作都是幂等的

AI Agent 可能因为超时/错误而重试同一个操作。如果操作不幂等，重试就会造成重复。

```python
# 坏：AI 调两次 = 创建两个 Redis
POST /api/resources  {"type": "redis", "project": "order-service"}

# 好：AI 调两次 = 同一个 Redis
POST /api/resources  {"idempotency_key": "order-service-redis-20260319", ...}
```

### 原则 2：所有操作都有清晰的状态机

AI Agent 需要知道"现在到哪一步了"，不能只有"成功/失败"。

```python
# 坏：
{"status": "failed"}  # AI 不知道失败在哪一步，不知道能不能重试

# 好：
{
    "state": "syncing",
    "state_history": [
        {"state": "created", "at": "10:00", "detail": "迁移任务创建"},
        {"state": "preparing", "at": "10:01", "detail": "在华为云创建空 RDS"},
        {"state": "prepared", "at": "10:05", "detail": "华为云 RDS 就绪"},
        {"state": "syncing", "at": "10:06", "detail": "全量同步开始，预计 30 分钟"},
    ],
    "can_retry": true,
    "can_rollback": true,
}
```

### 原则 3：暴露能力矩阵，而不是让 AI 猜

```python
# AI 问：华为云能开 Redis 吗？
GET /api/capabilities

{
    "alibaba": {
        "healthy": true,
        "resources": ["rds_mysql", "redis", "ecs", "oss", "slb", "sae"],
        "backup_support": ["rds_mysql", "redis", "ecs", "oss"],
        "migration_targets": ["huawei", "tencent"],
    },
    "huawei": {
        "healthy": true,
        "resources": ["rds_mysql", "redis", "ecs", "ascend_gpu"],
        "backup_support": ["rds_mysql", "ecs"],
        "migration_targets": ["alibaba"],
    },
    ...
}
```

### 原则 4：AI 能触发的操作 = 人能触发的操作

不给 AI 开后门，也不给 AI 加限制。AI 和人走同一条路径：

```
AI Agent / 人类
      │
      ▼
  submit_task()          ← 同一个入口
      │
      ▼
  幂等检查 → 资源锁 → 速率限制 → 执行    ← 同一套保障
      │
      ▼
  状态机更新 → 通知       ← 同一套反馈
```

---

## 新增代码结构

```
agentops/
├── cloud/
│   ├── interface.py              # ★ CloudProviderInterface + CloudResource + BackupRecord
│   ├── registry.py               # ★ CloudRegistry + select_best_provider
│   ├── health.py                 # ★ CloudHealthMonitor
│   ├── rate_limiter.py           # ★ CloudRateLimiter + TokenBucket
│   ├── alibaba/
│   │   ├── provider.py           # ★ AlibabaProvider(CloudProviderInterface)
│   │   ├── backup.py             # ★ 阿里云备份实现
│   │   └── (现有 rds.py / redis.py / ... 保留，被 provider.py 内部调用)
│   ├── huawei/
│   │   ├── provider.py           # ★ HuaweiProvider(CloudProviderInterface)
│   │   ├── backup.py             # ★
│   │   └── ...
│   └── tencent/
│       ├── provider.py           # ★ TencentProvider(CloudProviderInterface)
│       ├── backup.py             # ★
│       └── ...
├── engine/
│   ├── task.py                   # ★ TaskRecord 模型 + submit_task()
│   ├── worker.py                 # ★ TaskWorker
│   ├── lock.py                   # ★ ResourceLock
│   └── idempotency.py            # ★ 幂等检查
├── workflows/
│   ├── resource_provision.py     # 重构：通过 CloudRegistry 调用
│   ├── cloud_migration.py        # ★ 迁移工作流（状态机）
│   ├── backup.py                 # ★ 备份调度
│   └── ...
├── models/
│   ├── task_record.py            # ★ 任务表
│   ├── migration_record.py       # ★ 迁移记录表
│   ├── backup_record.py          # ★ 备份记录表
│   └── ...
└── api/
    ├── capabilities.py           # ★ GET /api/capabilities（AI 可查询能力矩阵）
    └── tasks.py                  # ★ 任务状态查询 API
```

---

## 实施顺序

**不能一起做，有依赖关系：**

```
第一步：地基
├── PostgreSQL 迁移（没有 pg 就没有行锁和 SKIP LOCKED）
├── TaskRecord 模型 + TaskWorker（替换 background_tasks）
└── 幂等检查

第二步：并发控制
├── ResourceLock
├── CloudRateLimiter
└── 重构 lark_events.py → 全部走 submit_task()

第三步：云抽象
├── CloudProviderInterface
├── CloudRegistry
├── 三朵云的 Provider 实现（包装现有代码）
└── 重构 resource_provision.py → 通过 Registry 调用

第四步：备份
├── BackupPolicy + BackupScheduler
├── 各云的 backup.py 实现
└── 跨云备份流程

第五步：迁移
├── MigrationRecord + 状态机
├── 迁移工作流
└── DNS/连接串切换

第六步：AI 可观测
├── /api/capabilities
├── /api/tasks
├── CloudHealthMonitor
└── 对接 Phase 2 AI 对话式操作
```

---

## 关键设计决策

| 决策点 | 选择 | 为什么 |
|--------|------|--------|
| 任务队列 | 数据库队列（不用 Celery/Redis） | AgentOps 量级是 10-100/天，不需要重型 MQ。数据库队列 = 零额外基础设施 + 天然持久化 |
| 分布式锁 | PostgreSQL Advisory Lock | 已经有 PG，不需要额外引入 Redis/etcd |
| 云抽象 | 接口 + 注册中心 | 比 if-elif 分支干净，新增云只需实现接口 + 注册 |
| 跨云备份 | 导出到对象存储 + 上传到目标云 | 通用方案，不依赖特定云的跨云功能 |
| 迁移 | 细粒度状态机 + 随时可回滚 | 迁移是高风险操作，必须可暂停、可回滚、可审计 |
| AI 设计 | 幂等 + 状态机 + 能力矩阵 | AI Agent 的三个刚需：安全重试、知道进度、知道能力边界 |
