# AI Learning Copilot 架构设计文档

**文档版本**：v1.0（Sprint 0 基线）
**适用范围**：本地开发形态 + 首版演进路线
**上游文档**：PRD.md（做什么）、DATABASE.md（数据模型）、ROADMAP.md（何时做）、DESIGN_SYSTEM.md（怎么呈现）

本文档只描述结构与契约，不描述产品动机。所有端口、路径、字段名与 Sprint 0 权威决策表一致；文档与实现冲突时先改决策表，再同步两侧。

## 1. 系统总览与本地拓扑

### 1.1 组成

| 单元 | 技术 | 职责 | 目录 |
|---|---|---|---|
| web | Next.js 16（App Router）+ React 19 + TypeScript + Tailwind CSS 4 | 页面渲染、请求编排、状态展示 | apps/web |
| api | Python 3.12 + FastAPI + Pydantic v2（uv 管理依赖） | 业务接口、校验、数据访问 | apps/api |
| db | PostgreSQL + SQLAlchemy 2.x（asyncpg 异步驱动）+ Alembic | 持久化与迁移 | 由 infra/docker-compose.yml 提供 |
| infra | Docker Compose | 本地依赖编排 | infra |
| docs | Markdown | 设计与契约基线 | docs |

### 1.2 本地开发拓扑

```text
               浏览器（开发者本机）
                       |
                       | HTTP  http://localhost:3000
                       v
        +----------------------------------+
        | web   Next.js 16 (dev server)    |
        |       React 19 + Tailwind CSS 4  |
        |       监听 0.0.0.0:3000           |
        +----------------------------------+
                       |
                       | 浏览器直接 fetch  http://localhost:8000/api/v1/*
                       | JSON（未来 AI 对话使用 SSE）
                       v
        +----------------------------------+
        | api   FastAPI + uvicorn          |
        |       Python 3.12 / Pydantic v2  |
        |       监听 0.0.0.0:8000          |
        +----------------------------------+
                       |
                       | SQLAlchemy 2.x async + asyncpg
                       v
        +----------------------------------+
        | db    PostgreSQL                 |
        |       仅绑定 127.0.0.1:5432      |
        |       不对公网暴露               |
        +----------------------------------+

        未来：api --HTTPS--> DeepSeek API
        本轮不发起任何 DeepSeek 调用（见第 5.8 节）
```

说明：浏览器直接访问 api，不经 web 反向代理。这样本地排错简单，但也意味着 api 的 CORS 必须是白名单而不是通配符。

### 1.3 端口与访问矩阵

| 服务 | 端口 | 绑定地址 | 谁访问 | 默认白名单 |
|---|---|---|---|---|
| web | 3000 | 本机 | 开发者浏览器 | 不适用 |
| api | 8000 | 本机 | 浏览器 fetch、curl、测试 | 允许来源 http://localhost:3000 与 http://127.0.0.1:3000 |
| postgres | 5432 | 仅 127.0.0.1 | api 进程 | 不对外 |

### 1.4 启动方式（Windows PowerShell，逐行执行，不使用 && 串联）

```powershell
#1) 启动数据库
cd "F:/ai自学产品/ai-learning-copilot"
docker compose -f infra/docker-compose.yml up -d

#2) 启动后端
cd "F:/ai自学产品/ai-learning-copilot/apps/api"
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000

#3) 启动前端（新窗口）
cd "F:/ai自学产品/ai-learning-copilot/apps/web"
npm install
npm run dev
```

### 1.5 配置项约定

| 变量 | 用途 | 默认值 | 是否必需 |
|---|---|---|---|
| DEEPSEEK_API_KEY | DeepSeek 访问密钥，仅后端读取 | 无 | 否（缺失时 ai_configured=false，服务照常启动） |
| DEEPSEEK_MODEL | 默认对话模型 | deepseek-flash | 否 |
| DEEPSEEK_MODEL_COMPLEX | 复杂任务预留模型 | deepseek-v4-pro | 否 |
| DATABASE_URL | 异步数据库连接串（postgresql+asyncpg） | 本地 compose 的连接串 | 是 |
| CORS_ORIGINS | 允许的跨域来源列表 | http://localhost:3000,http://127.0.0.1:3000 | 否 |
| ENVIRONMENT | 运行环境标识，写入 health 响应 | local | 否 |
| APP_VERSION | 版本号，写入 health 响应 | 0.1.0 | 否 |
| LOG_LEVEL | 日志级别 | INFO | 否 |

约定：除 DEEPSEEK_API_KEY 由权威决策表确定外，上表其余变量名属于本文档约定。S1 开始前与 apps/api/app/core/config.py 对齐一次；若实现已使用不同名称，以代码为准并回写本表，不允许文档与代码长期并存两种写法。

## 2. 模块边界

### 2.1 前端三层

```text
apps/web/src/
  app/
    (Today)/page.tsx      页面层：路由 /        今日待办、诊断入口
    learn/page.tsx        页面层：路由 /learn   课程阅读、掌握度标记
    practice/page.tsx     页面层：路由 /practice 练习、提交、判题结果
    projects/page.tsx     页面层：路由 /projects 项目模板与清单
    progress/page.tsx     页面层：路由 /progress 掌握度与完成率
    layout.tsx            根布局：侧边导航、字体、主题
  components/             组件层：可复用 UI，不含请求逻辑
  lib/                    请求层：fetch 封装、类型定义、错误归一化
```

职责与禁令：

- 页面层可以做：组合组件、调用 lib 的请求函数、持有页面级状态、渲染 loading 与 error 态。
- 页面层不可以做：直接拼接 fetch URL、手写超时与重试、在组件内计算统计口径。
- 组件层可以做：接收 props、渲染、处理纯 UI 交互。
- 组件层不可以做：发起网络请求、读写 localStorage 之外的持久化、引用页面级状态。
- 请求层可以做：统一 baseURL、超时、错误归一化、类型映射。
- 请求层不可以做：把后端错误码翻译成业务决策（例如"是否允许重试提交"由页面决定）、缓存业务状态。

### 2.2 后端三层

```text
apps/api/
  app/main.py                    应用装配：CORS、路由注册、异常处理、日志初始化
  app/core/config.py             配置与校验：环境变量读取、默认值、密钥判定
  app/core/db.py                 数据库：异步引擎、会话依赖、连通性探测
  app/core/logging.py            日志：结构化字段、脱敏、request_id
  app/api/v1/routes/health.py    路由：健康与就绪
  app/api/v1/routes/*.py         路由：后续按资源划分
  tests/                         测试：单元 + 接口
  migrations/                    Alembic 迁移
```

职责与禁令：

- 路由层只做 HTTP 映射、入参校验（Pydantic v2）、调用下层、组装响应；不写 SQL，不做长度超过 20 行的业务分支。
- 业务逻辑从 S1 起进入 app/services/（当前不存在，属于计划结构）；服务层可以调用 core/db 的会话，不直接依赖 FastAPI 的 Request。
- 数据访问统一经 app/core/db.py 提供的会话；禁止在路由内创建引擎或自行拼接连接串。
- 健康检查与就绪检查必须分离：health 不访问数据库，ready 只执行 SELECT 1。

### 2.3 越界判定表

| 行为 | 判定 | 原因 |
|---|---|---|
| 组件里直接 fetch | 越界，必须移到 lib | 请求层要保持单一入口，才能统一超时与错误 |
| 路由里写 select 语句 | 越界，移到服务层或 db 层 | 便于测试与复用，避免 SQL 散落 |
| health 里查询业务表 | 越界 | 健康与就绪分离，health 不应因业务表而失败 |
| 前端读取 DEEPSEEK_API_KEY | 越界且违规 | 密钥只存在于后端进程环境 |
| 前端直连 5432 | 越界且违规 | 数据库只绑定 127.0.0.1 且只允许 api 访问 |
| 页面里内联颜色值 | 越界 | 颜色只能来自 DESIGN_SYSTEM.md 的令牌 |
| 在 api 里渲染 HTML | 越界 | api 只返回 JSON |

## 3. 数据流

### 3.1 流一：页面读取系统状态（已实现）

用途：今日页顶部显示"数据服务正常/异常"和"AI 导师已配置/未配置"，让用户在学之前先知道环境是否健康。

```text
浏览器 (Today 页)
  1. GET /api/v1/health
     api: 读配置（不访问数据库）
     200 { status:"ok", service:"ai-learning-copilot-api", version, environment,
           timestamp, ai_configured:false }
  2. GET /api/v1/ready
     api: SELECT 1
     200 { status:"ready", checks:{ database:{ status:"connected", latency_ms:3 } } }
     或 503 { status:"not_ready",
              checks:{ database:{ status:"disconnected", detail:"..." } } }
  3. 页面渲染两个状态徽标；ready 失败时显示错误态与重试按钮
```

写入点：无。该流程是只读的，不产生任何数据行。

### 3.2 流二：未来练习提交与判题（S4 实现，本轮不实现）

关键约束：不执行用户代码，判定来源为 self_check、static_rule、manual。

```text
浏览器 (practice 页)
  1. GET /api/v1/exercises/{id}
     返回题目、起始代码、可见自检用例（隐藏用例不下发）
  2. 用户在本地运行代码，把运行输出粘贴回页面
  3. POST /api/v1/submissions
     body: { exercise_id, code_text, run_output_text, used_ai, ai_assistance_level }
     api 校验：code_text <= 20000 字符、run_output_text 非空、exercise 存在
  4. 判题（不执行代码）：
       a. static_rule：检查必须出现与禁止出现的语法结构；输出与期望值比对
       b. self_check：展示自检用例与实际输出的差异，由用户确认是否通过
       c. manual：无人值守判定，标记待人工或后续复盘
  5. 写库（单事务）：
       submissions 一行（含用于本行的 judging_mode 快照与 passed_with_ai）
       未通过 -> mistakes 一行 + review_tasks 一行（scheduled_for = now + 1 天）
  6. 返回判定结果与是否借助 AI 通过
```

写入点：submissions、mistakes、review_tasks。三者在同一事务内写入，任一失败整体回滚。

### 3.3 流三：未来 AI 导师对话（S2 实现，本轮不实现、不调用 DeepSeek）

```text
浏览器 (practice 或 learn 页)
  1. 用户选择提示依赖等级（none / hint / partial_code / full_answer）
  2. POST /api/v1/ai/tutor（Accept: text/event-stream）
     api 校验：问题长度、上下文 id 归属、等级取值
  3. 写 ai_interactions 一行，status='pending'，dependency_level=用户所选等级
     拿到 interaction_id
  4. api 调用 DeepSeek（流式），并转发事件：
       event: delta  -> { text }
       event: done   -> { interaction_id, tokens, latency_ms }
       event: error  -> { error_code, message }
  5. 结束（成功或失败）回写 ai_interactions：status、prompt_tokens、completion_tokens、
     latency_ms、response_text（脱敏后）、error_code
  6. 用户提交练习时：把相关 interaction 关联 submission_id，
     并按 dependency_level 计算 submissions.used_ai / passed_with_ai
```

写入点：ai_interactions（创建与收尾各一次）、submissions（提交时回填提示依赖字段）。

### 3.4 流四：未来复习任务生成（S5 实现）

触发：练习判题未通过，或用户手动加入错题。
处理：写 mistakes 一行（error_type、note_md），按 1/3/7/14/30 天规则生成 review_tasks 一行。
写入点：mistakes、review_tasks。规则细节见 DATABASE.md 第 4.11 与 4.12 节。

## 4. 接口约定

### 4.1 已实现契约（不可单方面修改）

`GET /api/v1/health`

| 字段 | 类型 | 说明 |
|---|---|---|
| status | string | 固定 ok |
| service | string | 固定 ai-learning-copilot-api |
| version | string | 应用版本号 |
| environment | string | 运行环境标识 |
| timestamp | string | ISO 8601 时间 |
| ai_configured | boolean | DEEPSEEK_API_KEY 是否已配置 |

返回 HTTP 200。未配置密钥不是错误，服务必须照常启动。

`GET /api/v1/ready`

| 情况 | 状态码 | 响应要点 |
|---|---|---|
| 数据库可用 | 200 | status=ready；checks.database.status=connected；含 latency_ms |
| 数据库不可用 | 503 | status=not_ready；checks.database.status=disconnected；含 detail |

就绪检查只执行 SELECT 1，不访问业务表。健康与就绪分离是硬约束：数据库不可用时 health 仍返回 200。

### 4.2 规划中的通用约定（S1 起生效）

- 列表响应统一为 `{ "items": [...], "next_cursor": "string|null", "has_more": false }`。
- 分页默认 limit=20，上限 100，超限返回 422。
- 请求与响应字段一律 snake_case；时间一律 ISO 8601 UTC 带 Z。
- 未实现的能力不注册路由：宁可 404，也不返回占位数据。

## 5. DeepSeek API 调用流程

本轮（Sprint 0）不发起任何 DeepSeek 请求，只固定调用契约与失败处理，避免后续实现各自发明参数。

### 5.1 调用参数

| 参数 | 取值 | 说明 |
|---|---|---|
| provider | deepseek | 供应商标识，写入 ai_interactions.provider |
| model | DEEPSEEK_MODEL，默认 deepseek-flash | 普通辅导对话 |
| model（复杂） | DEEPSEEK_MODEL_COMPLEX，默认 deepseek-v4-pro | 仅诊断总结、架构讲解类任务使用 |
| stream | true | 前端按 token 增量渲染 |
| temperature | 0.3 | 辅导场景需要稳定，不接受 1.0 以上的自由发挥 |
| max_tokens | 1024 | 单次回答上限，防止长回答挤占学习时间 |
| 请求头 | Authorization: Bearer <key> | 密钥只在后端内存中出现 |

### 5.2 超时、重试与退避

| 阶段 | 上限 | 超时后的行为 |
|---|---|---|
| 建立连接 | 5s | 计为可重试失败 |
| 首 token | 10s | 计为可重试失败（若已产生 token 则不可重试） |
| 整体（含流式传输） | 60s | 终止流，返回 error 事件，记 status='failed' |

重试规则：

- 最多 2 次重试，即最多 3 次尝试（1 次原始 + 2 次重试），计数按单次用户请求计算，不跨请求累积。
- 可重试：连接错误、超时（未产生任何 token）、HTTP 429、HTTP 5xx。
- 不可重试：HTTP 400、401、403、404 与内容审核拒绝；这些直接进入降级。
- 退避：第 1 次重试等待 0.5s，第 2 次等待 1.5s，各加正负 20% 抖动；不退避到 5s 以上，避免用户干等。

### 5.3 流式协议

- 服务端以 text/event-stream 输出，事件类型固定三类：delta、done、error。
- delta 只带文本增量，不带元数据；元数据只在 done 中下发一次。
- 客户端断开连接时，服务端停止向上游读取并回写 status='cancelled'，不记为失败。
- 不允许把上游原始错误体直接透传给前端，必须映射为本文档第 6.2 节的错误码。

### 5.4 失败降级阶梯

1. 重试（按 5.2 规则）。
2. 仍然失败：返回 error 事件，前端在对话区显示"AI 导师暂不可用"，并展示本地引导要点（来自练习的 hints，不来自模型）。
3. 降级不影响主线：练习可提交、复习可完成、诊断可进行。
4. 降级事件必须落库：ai_interactions.status='failed' 与 error_code 必填，便于统计真实可用性。

### 5.5 密钥管理

- DEEPSEEK_API_KEY 只从后端进程环境读取，只出现在请求头，不写入数据库、不写入日志、不下发前端。
- health 响应只暴露布尔值 ai_configured，不暴露密钥任何片段（含后四位）。
- 任何日志中出现密钥形态的字符串都按缺陷处理。

### 5.6 提示依赖记录的写入点

提示依赖是本产品的核心数据，写入点固定为三处，不允许在别处补写：

| 序号 | 写入点 | 触发时机 | 写入内容 |
|---|---|---|---|
| 1 | ai_interactions 创建 | 调用 DeepSeek 之前 | status='pending'、dependency_level=用户所选等级、context 类型与 id |
| 2 | ai_interactions 收尾 | 流结束、失败或被取消 | status、tokens、latency_ms、脱敏后的 prompt 与 response、error_code |
| 3 | submissions 回填 | 练习提交时 | used_ai、ai_assistance_level、has_prompt_dependency、passed_with_ai |

一致性规则：submissions.passed_with_ai 为真，当且仅当 is_passed 为真且 used_ai 为真；dependency_level='full_answer' 的调用必须使该次提交的 passed_with_ai 为真。若两者不一致，以 ai_interactions 为事实源，修复写入逻辑而不修改历史数据。

### 5.7 本轮不调用

- S0 不实现 /api/v1/ai/* 路由。
- S0 不在任何代码路径中导入 DeepSeek SDK。
- S0 不因缺少 DEEPSEEK_API_KEY 而启动失败；health 的 ai_configured=false 即为此契约的证据。

## 6. 错误处理方案

### 6.1 统一错误响应体（S1 起生效）

```json
{
  "error": {
    "code": "AI_TIMEOUT",
    "message": "AI 导师响应超时，请稍后重试",
    "request_id": "0f3c1a2b9d8e",
    "details": { "retry_after_ms": 1500 }
  }
}
```

- message 面向用户，中文，不含堆栈与内部路径。
- request_id 与日志中的 request_id 一致，便于把用户反馈对到日志。
- details 可选，只在有结构化补充信息时出现。
- 兼容说明：S0 已实现的 `/api/v1/ready` 在数据库不可用时返回的是 readiness 结构（status 与 checks），不属于错误响应体。S1 引入统一错误体时，不为 ready 增加 error 包裹，保持该接口现状；只有新的业务接口使用统一错误体。

### 6.2 错误码与状态码约定

| code | HTTP | 使用场景 |
|---|---|---|
| VALIDATION_ERROR | 422 | 请求体或参数不合法（Pydantic 校验失败） |
| NOT_FOUND | 404 | 资源不存在 |
| CONFLICT | 409 | 状态冲突（例如重复提交同一练习的进行中记录） |
| AI_UNAVAILABLE | 503 | DeepSeek 不可用或未配置 |
| AI_TIMEOUT | 504 | 上游超时 |
| RATE_LIMITED | 429 | 触发上游限流 |
| DB_UNAVAILABLE | 503 | 数据库不可用（业务接口） |
| INTERNAL_ERROR | 500 | 未分类的服务端错误 |

约束：4xx 不重试；5xx 由前端提供一次显式重试按钮，不自动重试写操作。

### 6.3 前端错误边界与降级

- 5 个页面路由段各自有 error 边界，单页异常不导致整站白屏。
- 边界内展示三件事：发生了什么（中文）、可以做什么（重试或返回今日页）、request_id（便于对照日志）。
- 请求层超时默认 10s，AI 对话使用 60s 并支持手动停止。
- 未拿到数据时不渲染 0 值图表；显示空状态或错误态。

### 6.4 日志字段

```json
{
  "ts": "2025-01-01T00:00:00Z",
  "level": "ERROR",
  "service": "ai-learning-copilot-api",
  "environment": "local",
  "event": "ai.request.failed",
  "request_id": "0f3c1a2b9d8e",
  "method": "POST",
  "path": "/api/v1/ai/tutor",
  "status_code": 504,
  "duration_ms": 60012,
  "error_code": "AI_TIMEOUT",
  "provider": "deepseek",
  "model": "deepseek-flash",
  "prompt_chars": 812,
  "prompt_sha256_12": "9a1c4f0b7e22"
}
```

- 不记录：密钥、Authorization 头、完整提示词与完整响应原文、邮箱等可识别信息。
- 需要排查时记录长度与哈希前缀（12 位），可配合数据库脱敏记录定位。
- 每个请求一个 request_id，贯穿 api 日志与前端错误提示。

## 7. 安全设计原则

1. 密钥只存后端环境：不入库、不入前端包、不入日志；健康接口只返回布尔值。
2. CORS 用白名单：默认 http://localhost:3000 与 http://127.0.0.1:3000，通过环境变量可扩展；禁止使用通配符配合凭据。
3. 输入校验前置：所有入参经 Pydantic v2 校验，并设置长度上限（提示 4000 字符、代码 20000 字符、标题 200 字符），超限返回 422。
4. SQL 注入防护：只使用 SQLAlchemy 表达式与参数绑定；禁止字符串拼接 SQL；禁止把用户输入作为表名或列名。
5. 日志脱敏：见第 6.4 节；任何密钥形态字符串出现即视为缺陷。
6. 数据库不暴露：compose 中端口映射固定为 127.0.0.1:5432；不允许改成 0.0.0.0。
7. 不把 Docker 容器当安全沙箱：容器不是隔离执行环境，因此本产品在首版不执行用户代码；即使将来引入执行能力，必须使用专用隔离方案（独立容器加资源限额、只读文件系统、无网络），而不是复用 api 容器。
8. 依赖可信：不引入来源不明的包；锁文件入库；不在运行时执行动态下载的脚本。

## 8. 后续扩展策略

### 8.1 加一个功能模块（以模块为例的标准动作）

1. 在 PRD.md 第 5 节补该模块的输入、输出、验收要点。
2. 在 DATABASE.md 定表与索引，并标注属于哪个 Sprint 的迁移。
3. 后端：app/api/v1/routes 加路由文件 → app/services 加服务 → 复用 core/db 会话。
4. 前端：lib 加请求函数与类型 → components 加组件 → 页面层组装。
5. 测试：后端加接口测试（含失败分支），前端加 ESLint 与交互走查。
6. 文档：ARCHITECTURE.md 第 3 节补数据流，ROADMAP.md 补验收条件。

以上 6 步缺一步视为未完成，不允许"先合代码后补文档"。

### 8.2 更换或新增模型供应商

- 定义统一的模型调用接口（本设计中的 AIClient 协议）：chat(messages, model, stream) 与 count_tokens(text)，返回值含 tokens、latency。
- 供应商差异只出现在适配器内部：鉴权头、流式事件格式、错误码映射。
- ai_interactions.provider 与 model 已有字段承载供应商切换，不需要改表。
- 迁移顺序：先并行接入新供应商并置灰开关，验证通过后再切换默认值，保留 1 个 Sprint 的双写观察期。

### 8.3 加异步任务

- S5 的复习任务可先同步生成（单用户数据量小）。
- 需要异步时按此顺序升级：FastAPI BackgroundTasks（无额外依赖）→ 引入 worker 与队列 → 引入定时调度。
- 异步任务必须幂等：以 (user_id, entity_type, entity_id, scheduled_for) 做唯一约束或先查后写。
- 异步任务失败必须落库可见，不允许静默丢失。

### 8.4 可观测性

- 已是基线：结构化 JSON 日志、request_id、health 与 ready 分离。
- S7 起再加：请求耗时直方图、AI 调用成功率与 p95 延迟、错误码分布；仅在本地或受控环境暴露，不对外网开放。
- 不上第三方 SaaS 监控；首版不引入分布式追踪。

## 9. 当前实现状态与差距

| 项 | 状态 | 说明 |
|---|---|---|
| GET /api/v1/health | 已实现 | 六字段响应，密钥缺失时 ai_configured=false |
| GET /api/v1/ready | 已实现 | 200 与 503 两条路径，含 latency_ms 与 detail |
| CORS 白名单 | 已实现 | 默认两个 localhost 来源 |
| Alembic 骨架 + 空基线迁移 | 已实现 | 尚未创建任何业务表 |
| 业务表（13 张） | 未实现 | DATABASE.md 是设计文档，不是已建表说明 |
| 五个页面 | S0 范围：路由骨架与布局 | 页面功能按模块 1–8 在 S1–S6 补齐；未实现入口标注开发中 |
| AI 导师调用链 | 未实现 | 本轮明确不调用 DeepSeek |
| 认证与多用户 | 未实现且非目标 | 单用户本地形态 |
| 对外部署 | 未实现且非目标 | 只在本地开发环境运行 |

本表区分"S0 承诺范围"与"S1 起补齐的功能"，不声明任何运行时验证结论；实现证据以仓库与本地命令输出为准。

## 10. 待确认事项

- 待确认：infra/docker-compose.yml 是否把 web 与 api 也容器化。当前文档约定 compose 至少提供 postgres，web 与 api 在宿主机运行；若改为容器化，需要在本文件第 1.2 与 1.3 节同步端口与拓扑。
- 待确认：统一错误响应体在 S1 落地时，是否需要为历史接口保留 detail 兼容字段。默认不为 ready 加 error 包裹（见第 6.1 节）。
- 待确认：DeepSeek 模型的默认值与复杂任务模型是否与实际可用型号一致，需在 S2 接入前用真实密钥验证一次，并把结论写回本文件第 5.1 节与 PRD.md 第 5.5 节。
