# HepOps — 运维自动化引擎

> 飞书审批驱动，多云资源自动开通，替代运维工程师的手动操作

## 解决什么问题

高等教育出版社现有流程：研发/业务负责人口头或邮件找运维 → 运维手动登录阿里云/华为云/腾讯云控制台 → 手动创建流水线、开通资源、配置域名 → 口头回复。

**痛点**：运维是瓶颈，响应慢，易出错，无台账。

**HepOps 做的事**：把运维的手动操作变成 API 调用，用飞书审批触发，全程自动，零人工介入。

## 三个核心流程

### 1. 云资源开通（写代码前）

```
业务负责人飞书提交"云资源申请" → 主管审批 → 自动调云 API 创建资源 → 飞书通知连接信息
```

支持：阿里云（RDS / Redis / ECS / OSS / SLB / SAE）、华为云（昇腾 GPU）、腾讯云（CVM）

### 2. 部署流水线创建

```
研发飞书提交"部署申请" → 主管审批 → 自动在云效创建 CI/CD 流水线 + 分配域名 → 飞书通知
```

之后研发每次 push 代码到 Gitee，云效自动构建部署。

### 3. 域名替换（需等保备案）

```
业务负责人飞书提交"域名变更申请" → 主管审批 → 校验等保备案 → 自动更新 DNS + SSL → 飞书通知
```

## 定时任务

- **每日 09:00** — 扫描即将到期的云资源，飞书通知业务负责人 + 公有云负责人 + 信息技术部主任
- **每月 1 号 10:00** — 汇总上月云资源成本，飞书推送报表

## 快速开始

### 1. 安装

```bash
cd hepops
pip install -e .
```

### 2. 配置

```bash
cp .env.example .env
```

编辑 `.env`，填入以下凭证：

| 配置项 | 说明 | 获取方式 |
|--------|------|---------|
| `HEPOPS_LARK_APP_ID` | 飞书应用 ID | 飞书开放平台 → 创建企业自建应用 |
| `HEPOPS_LARK_APP_SECRET` | 飞书应用密钥 | 同上 |
| `HEPOPS_LARK_WEBHOOK_NOTIFY` | 飞书群机器人 webhook | 飞书群 → 添加机器人 → 自定义机器人 |
| `HEPOPS_LARK_APPROVAL_PIPELINE` | 部署申请审批模板 code | 飞书管理后台 → 审批 → 创建模板 |
| `HEPOPS_LARK_APPROVAL_RESOURCE` | 云资源申请审批模板 code | 同上 |
| `HEPOPS_LARK_APPROVAL_DOMAIN` | 域名变更审批模板 code | 同上 |
| `HEPOPS_ALI_ACCESS_KEY_ID` | 阿里云 AK | 阿里云 → RAM → AccessKey |
| `HEPOPS_ALI_ACCESS_KEY_SECRET` | 阿里云 SK | 同上 |
| `HEPOPS_HW_ACCESS_KEY` | 华为云 AK | 华为云 → 我的凭证 |
| `HEPOPS_TC_SECRET_ID` | 腾讯云 SecretId | 腾讯云 → API 密钥管理 |

完整配置项见 [.env.example](.env.example)。

### 3. 启动

```bash
# 开发模式（自动重载）
python main.py

# 生产模式
uvicorn main:app --host 0.0.0.0 --port 8000

# Docker
docker build -t hepops .
docker run -p 8000:8000 --env-file .env hepops
```

### 4. 验证

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

## 飞书配置指南

### 第一步：创建企业自建应用

1. 登录 [飞书开放平台](https://open.feishu.cn)
2. 创建企业自建应用 → 获取 App ID 和 App Secret
3. 权限管理 → 开通：`approval:instance:read`（读取审批实例）、`im:message:send_as_bot`（机器人发消息）

### 第二步：创建 3 个审批模板

在飞书管理后台 → 审批管理 → 创建审批，按以下字段创建：

**模板 1：云资源申请**

| 字段名 | 类型 | 选项 |
|--------|------|------|
| 云厂商 | 单选 | 阿里云 / 华为云 / 腾讯云 |
| 资源类型 | 单选 | RDS MySQL / Redis / ECS / OSS / GPU(昇腾) |
| 规格 | 文本 | |
| 用途说明 | 多行文本 | |
| 关联项目 | 文本 | |
| 项目立项否 | 单选 | 是 / 否 |
| 立项签报截图/链接 | 附件 | |

**模板 2：新项目部署申请**

| 字段名 | 类型 | 选项 |
|--------|------|------|
| 项目名称 | 文本 | |
| Gitee 仓库地址 | 文本 | |
| 分支名 | 文本 | |
| 语言类型 | 单选 | Java Maven / Java Gradle / Node.js / Python |
| 部署环境 | 单选 | 测试环境 / 生产环境 |
| 备注 | 多行文本 | |

**模板 3：域名变更申请**

| 字段名 | 类型 | 选项 |
|--------|------|------|
| 服务名 | 文本 | |
| 当前域名 | 文本 | |
| 正式域名名称 | 文本 | |
| 环境 | 单选 | 测试环境 / 生产环境 |
| 是否已做过等保备案 | 单选 | 是 / 否 |
| 等保备案证明 | 附件 | |

创建后，每个模板会有一个 `approval_code`，填入 `.env` 对应配置项。

### 第三步：配置事件订阅

1. 飞书开放平台 → 应用 → 事件订阅
2. 请求地址填：`https://你的域名/api/lark/events`
3. 订阅事件：`approval_instance`（审批实例状态变更）
4. 获取 Verification Token 和 Encrypt Key，填入 `.env`

### 第四步：创建通知机器人

1. 在飞书群中添加自定义机器人
2. 获取 Webhook URL，填入 `HEPOPS_LARK_WEBHOOK_NOTIFY`

## 技术架构

```
飞书审批 → POST /api/lark/events → 工作流路由 → 云 API 调用 → 飞书通知
                                                    ↓
                                              SQLite 资源台账
```

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI |
| 数据库 | SQLite（可切 PostgreSQL） |
| 飞书 SDK | lark-oapi |
| 阿里云 | alibabacloud-devops / alidns / rds / ecs 等 |
| 华为云 | huaweicloudsdkecs |
| 腾讯云 | tencentcloud-sdk-python |
| 定时任务 | APScheduler |

## 项目结构

```
hepops/
├── main.py                     # FastAPI 入口
├── config.py                   # 配置管理
├── scheduler.py                # 定时任务（到期提醒 + 成本报表）
├── api/
│   └── lark_events.py          # 飞书事件回调（系统入口）
├── workflows/
│   ├── pipeline_setup.py       # 流程1: 创建云效流水线
│   ├── resource_provision.py   # 流程2: 多云资源开通
│   └── domain_change.py        # 流程3: 域名替换
├── cloud/
│   ├── alibaba/                # 阿里云 API（10个模块）
│   ├── huawei/                 # 华为云 API（GPU）
│   └── tencent/                # 腾讯云 API
├── lark/
│   ├── client.py               # 飞书 API 客户端
│   ├── approval_templates.py   # 审批表单字段定义
│   └── notifier.py             # 飞书通知
├── models/
│   ├── pipeline_record.py      # 流水线记录
│   ├── resource_record.py      # 资源台账
│   └── operation_log.py        # 操作审计日志
└── docs/
    └── workflow-diagrams.md    # Mermaid 流程图（6张）
```

## 流程图

详见 [docs/workflow-diagrams.md](docs/workflow-diagrams.md)，包含 6 张 Mermaid 流程图：

1. 现状 vs 自动化对比
2. 项目全生命周期
3. 云资源开通流程
4. 域名替换流程
5. 定时任务流程
6. 系统整体架构
