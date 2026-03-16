# HepOps 运维自动化 — 企业工作流程图

> 可直接粘贴到飞书文档 / Notion / 语雀 / mermaid.live 中渲染

---

## 图 1: 现状 vs 自动化对比

### 现状（人工运维）

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart LR
    subgraph 业务团队
        A1[业务负责人]
        A2[研发工程师]
    end

    subgraph 运维团队
        B[运维工程师 x2]
    end

    subgraph 云平台
        C[阿里云控制台]
        D[华为云控制台]
        E[腾讯云控制台]
    end

    A1 -->|口头申请云资源| B
    B -->|手动登录 手动开通| C
    B -->|手动开通 GPU| D
    B -->|手动开通资源| E
    B -->|口头回复连接信息| A1
    A2 -->|口头提交部署需求| B
    B -->|手动创建流水线| C
    B -->|口头回复域名| A2

    style B fill:#ff6b6b,color:#fff
```

**痛点**: 运维是瓶颈，研发等待时间长，人工操作易出错，无台账无法追溯

### 自动化后（零人工介入）

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart LR
    subgraph 业务团队
        A1[业务负责人]
        A2[研发工程师]
    end

    subgraph 飞书
        B[审批表单]
        C[主管审批]
        D[机器人通知]
    end

    subgraph HepOps
        E[事件接收]
        F[自动执行]
    end

    subgraph 云平台
        G[阿里云 API]
        H[华为云 API]
        I[腾讯云 API]
    end

    A1 -->|提交云资源申请| B
    A2 -->|提交部署申请| B
    B --> C
    C -->|审批通过 自动回调| E
    E --> F
    F --> G
    F --> H
    F --> I
    F -->|自动通知| D
    D --> A1
    D --> A2

    style F fill:#51cf66,color:#fff
```

**效果**: 自助、分钟级完成、全程可追溯、零运维人力

---

## 图 2: 项目全生命周期

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart TD
    A[项目立项] --> B["业务负责人在飞书提交云资源申请"]
    B --> C{主管审批}
    C -->|通过| D["自动开通云资源 RDS/Redis/ECS/GPU等"]
    D --> E["飞书通知业务负责人 资源已创建+连接信息"]

    E --> F[研发团队开始写代码]
    F --> G[研发 push 代码到 Gitee]
    G --> H[云效自动构建部署]
    H --> I[自动分配域名]

    I --> I1["测试环境 xxx-test.hep.com.cn"]
    I --> I2["生产环境 xxx.hep.com.cn"]

    I1 --> J["飞书通知研发 部署成功+域名"]
    I2 --> J

    J --> K{需要正式域名?}
    K -->|是| L["业务负责人提交域名变更申请 需等保备案"]
    K -->|否| M[使用自动分配的域名]
    L --> N{审批通过}
    N --> O[自动替换 DNS + SSL]
    O --> P["飞书通知 域名已更新"]

    style A fill:#868e96,color:#fff
    style B fill:#4c6ef5,color:#fff
    style F fill:#ffd43b,color:#333
    style G fill:#ffd43b,color:#333
    style L fill:#4c6ef5,color:#fff
    style D fill:#51cf66,color:#fff
    style H fill:#51cf66,color:#fff
    style O fill:#51cf66,color:#fff
```

### 关键角色分工

| 阶段 | 操作人 | 操作 |
|------|--------|------|
| 项目立项后 | **业务/项目负责人** | 飞书提交"云资源申请" |
| 资源就绪后 | **暂时还是RD --> 下一步会替换成LLM，砍掉外包RD** | RD 开始写代码 --> LLM vibe coding |
| 代码完成后 | **RD / LLM** | push 到 Gitee 分支，自动部署 + 分配域名 |
| 需要正式域名时 | **业务/项目负责人** | 飞书提交"域名变更申请"（需等保备案） |

---

## 图 3: 云资源开通流程（写代码前）

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart TD
    A["业务负责人在飞书提交云资源申请"] --> B{主管审批}
    B -->|拒绝| Z[飞书通知 审批被拒]
    B -->|通过| C[飞书回调 HepOps 后端]

    C --> D["解析表单: 云厂商+资源类型+规格+立项信息"]
    D --> E{云厂商路由}

    E -->|阿里云 70%| F[阿里云 API]
    E -->|华为云| G[华为云 API]
    E -->|腾讯云| H[腾讯云 API]

    F --> F1["RDS/Redis/ECS/OSS/SLB/SAE"]
    G --> G1["昇腾910B/C GPU ModelArts"]
    H --> H1["CVM云服务器 COS存储"]

    F1 --> I["记录资源台账 连接信息+费用+立项信息"]
    G1 --> I
    H1 --> I

    I --> J["飞书通知业务负责人 资源已创建+连接信息+预估月费"]

    style A fill:#4c6ef5,color:#fff
    style J fill:#51cf66,color:#fff
    style F fill:#ff922b,color:#fff
    style G fill:#e64980,color:#fff
    style H fill:#4c6ef5,color:#fff
```

### 审批表单字段

| 字段 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| 云厂商 | 单选 | 阿里云 / 华为云 / 腾讯云 | |
| 资源类型 | 单选 | RDS MySQL / Redis / OSS / GPU(昇腾/PPU) | |
| 规格 | 文本 | 4核8G / 昇腾910C x2 | |
| 用途说明 | 多行文本 | 订单服务数据库 | |
| 关联项目 | 文本 | order-service | |
| **项目立项否** | **单选** | **是 / 否** | **新增** |
| **立项签报截图/链接** | **附件/链接** | | **新增** |

---

## 图 4: 域名替换流程（需等保备案）

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart TD
    A["业务负责人在飞书提交域名变更申请"] --> B{主管审批}
    B -->|拒绝| Z[飞书通知 审批被拒]
    B -->|通过| C[飞书回调 HepOps 后端]

    C --> D{检查等保备案状态}
    D -->|未备案| E["飞书通知 域名变更被拒绝 请先完成等保备案"]
    D -->|已备案| F[删除旧 DNS 记录]

    F --> G[创建新 DNS 记录]
    G --> H[申请 SSL 证书]
    H --> I[更新流水线记录]
    I --> J["飞书通知 域名已更新为 xxx.hep.com.cn"]

    style A fill:#4c6ef5,color:#fff
    style E fill:#ff6b6b,color:#fff
    style J fill:#51cf66,color:#fff
    style D fill:#ffd43b,color:#333
```

### 审批表单字段

| 字段 | 类型 | 示例值 | 说明 |
|------|------|--------|------|
| 服务名 | 文本 | order-service | |
| 当前域名 | 文本 | order-test.hep.com.cn | 自动分配的域名 |
| **正式域名名称** | **文本** | **order.hep.com.cn** | **新增** |
| 环境 | 单选 | 测试环境 / 生产环境 | |
| **是否已做过等保备案** | **单选** | **是 / 否** | **新增，必须为"是"** |
| **等保备案证明** | **附件/链接** | | **新增** |

---

## 图 5: 定时任务 — 资源到期提醒 + 月度成本报表

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart TD
    subgraph 每日09点
        A[扫描资源台账] --> B{有资源7天内到期?}
        B -->|有| C[按负责人分组]
        C --> D["飞书群通知 到期预警列表"]
        C --> E["单聊通知: 业务负责人+公有云负责人+杨京峰主任"]
        B -->|无| F[无需提醒]
    end

    subgraph 每月1号10点
        G[查询上月资源台账] --> H["调BSS API查询各云实际账单"]
        H --> I[按云厂商+资源类型汇总]
        I --> J[飞书推送月度报表]
    end

    style D fill:#ffd43b,color:#333
    style E fill:#ff922b,color:#fff
    style J fill:#4c6ef5,color:#fff
```

---

## 图 6: 系统整体架构

```mermaid
%%{init: {'flowchart': {'useMaxWidth': false}} }%%
flowchart TB
    subgraph 用户层
        U1["业务负责人 申请资源/域名"]
        U2["研发工程师 部署/push代码"]
        M[主管]
    end

    subgraph 飞书
        LA["审批表单 x3"]
        LB[审批流转]
        LC["通知 群机器人+单聊"]
    end

    subgraph HepOps
        EA["事件接收 /api/lark/events"]
        EB[工作流路由]
        EC["流程1: 云资源开通"]
        ED["流程2: 部署流水线"]
        EE["流程3: 域名替换"]
        EF["定时任务 到期提醒+成本报表"]
        EG[资源台账+操作日志]
    end

    subgraph 云平台API
        CA["阿里云"]
        CB["华为云"]
        CC["腾讯云"]
    end

    subgraph 数据库
        DB[(SQLite)]
    end

    U1 -->|提交审批| LA
    U2 -->|提交审批| LA
    LA --> LB
    LB --> M
    M -->|通过| LB
    LB -->|webhook| EA
    EA --> EB
    EB --> EC
    EB --> ED
    EB --> EE

    EC --> CA
    EC --> CB
    EC --> CC
    ED --> CA
    EE --> CA

    EC --> EG
    ED --> EG
    EE --> EG
    EG --> DB

    EF -->|通知| LC
    EF --> DB

    EC -->|结果通知| LC
    ED -->|结果通知| LC
    EE -->|结果通知| LC
    LC --> U1
    LC --> U2

    style EA fill:#4c6ef5,color:#fff
    style EF fill:#ffd43b,color:#333
    style CA fill:#ff922b,color:#fff
    style CB fill:#e64980,color:#fff
    style CC fill:#4c6ef5,color:#fff
```

---

## 价值总结

| 维度 | 现状 (人工) | 自动化后 |
|------|------------|---------|
| **人力成本** | 2 名运维工程师 | 0 人（系统自动执行） |
| **响应速度** | 几小时到几天（等运维排期） | 分钟级（审批通过即执行） |
| **出错率** | 高（手动操作易遗漏配置） | 极低（标准化 API 调用） |
| **可追溯性** | 无（口头/邮件沟通） | 完整审计日志 + 飞书审批留痕 |
| **资源管理** | 无台账，不知道开了什么资源 | 自动台账 + 到期提醒(通知3类人) + 成本报表 |
| **合规性** | 无立项审核，无等保校验 | 资源申请需立项签报，域名变更需等保备案 |
| **研发体验** | 需要找运维、等排期 | 飞书一键提交，自助完成 |
