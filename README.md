# AI Learning Copilot

面向**非计算机理工科背景、编程基础薄弱、希望转向 AI 应用开发**的初学者的自学平台。
目标不是把课程播放完，而是让学习者最终能**独立开发并展示一个简单的 AI 应用**。

> 当前处于 **Sprint 0（骨架与基础设施）**。前端是结构与演示数据，后端只有健康检查，
> 数据库只有迁移骨架——**尚未实现课程、判题、AI 对话等业务功能**，界面上未实现的入口一律标注「开发中」。

## 首版范围：路线 A

```
Python 基础 → 编程实践 → API → LLM → RAG/Agent 基础 → 简单 AI 项目
```

产品原则：教用户独立解决问题而不是直接给答案；学习评估尽量基于可验证数据；允许自由使用 AI 提示但必须记录提示依赖；**不把课程完成率等同于掌握程度**。

## 当前状态（诚实清单）

| 能力 | 状态 |
| --- | --- |
| 五个页面（今日 / 学习 / 练习 / 项目 / 进度）+ 导航 + 深浅色主题 | ✅ 可运行 |
| 前端读取后端与数据库状态 | ✅ 已打通（在线 / 数据库未连接 / 离线三态） |
| `GET /api/v1/health`、`GET /api/v1/ready` | ✅ 已实现并测试 |
| PostgreSQL 本地容器 + Alembic 空基线迁移 | ✅ 可用（业务表 0 张） |
| 课程内容、练习判题、AI 导师对话、登录、数据持久化 | ❌ 未实现（界面标注「开发中」） |
| 真实代码执行沙箱 | ❌ 未实现，且**不会**用普通 Docker 容器冒充安全沙箱 |

## 技术栈（本机实测版本）

| 层 | 技术 | 版本 |
| --- | --- | --- |
| 前端 | Next.js（App Router）/ React / TypeScript / Tailwind CSS 4 | 16.4.4 / 19.3.0 / 5.9.3 / 4.3.4 |
| 后端 | Python / FastAPI / Pydantic v2 / SQLAlchemy 2.x / Alembic | 3.12.15 / 0.162.0 / 2.14.2 / 2.1.6 / 1.20.1 |
| 数据库 | PostgreSQL（Docker，仅本机回环） | 17-alpine |
| 工具 | uv（后端依赖）、npm（前端依赖）、Pytest、ESLint | uv 0.13.5 / npm 11.20.0 |
| AI（预留） | DeepSeek API（Sprint 0 **不调用**，不产生费用） | 模型 id 见 `docs/ARCHITECTURE.md` |

## 目录结构

```
ai-learning-copilot/
├─ apps/
│  ├─ web/                 # Next.js 16 前端
│  │  └─ src/{app,components,lib}
│  └─ api/                 # FastAPI 后端（uv 管理）
│     ├─ app/{main.py,core,api/v1}
│     ├─ migrations/       # Alembic（当前只有空基线 0001）
│     └─ tests/
├─ infra/docker-compose.yml  # 仅 PostgreSQL，只绑定 127.0.0.1
├─ docs/                     # PRD / ARCHITECTURE / DATABASE / ROADMAP / DESIGN_SYSTEM
├─ .env.example              # 全部环境变量参考（三段：后端 / 前端 / 数据库）
└─ README.md
```

## 本地启动（Windows PowerShell）

以下命令均在 PowerShell 中逐行执行。**不要用 `&&` 串联**，Windows PowerShell 5.1 不支持。

### 0. 前置检查

```powershell
node -v          # 需要 20+（本机实测 26.13.0）
npm -v
uv --version     # 需要 uv 0.13+（本机实测 0.13.5）
uv python list   # 需要 cpython-3.12.x；若没有：uv python install 3.12
docker --version
docker compose version
```

### 1. 进入仓库

```powershell
cd "F:\ai自学产品\ai-learning-copilot"
```

### 2. 启动数据库（Docker）

```powershell
Copy-Item infra\.env.example infra\.env
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps      # 等待 STATUS 显示 (healthy)
```

数据库只在 `127.0.0.1:5432` 监听，不对局域网或公网开放；口令是本地开发默认值，**不要用于任何公开环境**。

### 3. 启动后端

```powershell
cd apps\api
Copy-Item .env.example .env      # DEEPSEEK_API_KEY 留空即可，非 AI 功能照常工作
uv sync
uv run alembic upgrade head      # 空基线迁移，不创建业务表
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

后端接口文档：<http://127.0.0.1:8000/docs>

### 4. 启动前端（新开一个 PowerShell 窗口）

```powershell
cd "F:\ai自学产品\ai-learning-copilot\apps\web"
Copy-Item .env.example .env.local
npm install
npm run dev
```

打开 <http://localhost:3000>。页面右下角/侧栏底部的「系统状态」应显示 **后端在线 · 数据库已连接**。

### 5. 确认前后端已打通

```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
curl.exe -s -w "`nHTTP=%{http_code}`n" http://127.0.0.1:8000/api/v1/ready
```

预期：`health` 返回 200 且 `status=ok`；`ready` 在数据库可用时返回 200 / `status=ready`，数据库不可用时返回 **503** 与 `status=not_ready`（服务本身不崩溃，这正是健康与就绪分离的意义）。

> PowerShell 里 `curl` 是 `Invoke-WebRequest` 的别名，请显式写 `curl.exe`。

## 常用命令

| 目的 | 命令 |
| --- | --- |
| 后端测试（不依赖数据库） | `cd apps\api` 然后 `uv run pytest -q` |
| 后端测试（需要数据库在线） | `uv run pytest -q -m integration` |
| 新增数据库迁移 | `uv run alembic revision --autogenerate -m "描述"` |
| 前端类型检查 | `cd apps\web` 然后 `npx tsc --noEmit` |
| 前端 lint | `npm run lint` |
| 前端生产构建 | `npm run build` |
| 前端生产运行 | `npm run start` |
| 停止数据库 | `docker compose -f infra/docker-compose.yml stop` |
| 停止并删除数据卷（会清空数据） | `docker compose -f infra/docker-compose.yml down -v` |

## 环境变量

根目录 `.env.example` 是完整参考，分三段分别复制到：

| 文件 | 对应位置 | 是否入库 |
| --- | --- | --- |
| `apps\api\.env` | 后端（数据库连接、CORS、DeepSeek） | 否（已 gitignore） |
| `apps\web\.env.local` | 前端（`NEXT_PUBLIC_API_BASE_URL`） | 否（已 gitignore） |
| `infra\.env` | Docker Compose（数据库端口/账号） | 否（已 gitignore） |

**任何真实密钥都不得写进仓库。** 缺少 `DEEPSEEK_API_KEY` 时服务照常启动，`/api/v1/health` 会返回 `ai_configured: false`。

## 已验证的检查（Sprint 0 实测记录）

| # | 检查 | 结果 |
| --- | --- | --- |
| 1 | 前端依赖安装 | ✅ `npm install` 成功，`package-lock.json` 已锁定 |
| 2 | TypeScript 类型检查 | ✅ `npx tsc --noEmit` 退出码 0 |
| 3 | ESLint | ✅ `npm run lint` 退出码 0 |
| 4 | 生产构建 | ✅ `npm run build` 成功，5 个页面静态预渲染 |
| 5 | 后端启动 | ✅ `uvicorn app.main:app` 正常监听 8000 |
| 6 | Pytest | ✅ 默认模式 11 passed；integration 模式 1 passed |
| 7 | PostgreSQL 容器 | ✅ healthy，仅绑定 127.0.0.1:5432 |
| 8 | 健康与就绪 | ✅ health 200 / ready 200；停库后 ready 503 且服务不崩 |
| 9 | 前后端通信 | ✅ 页面显示「后端在线 · 数据库已连接」，含真实延迟 |
| 10 | 页面渲染 | ✅ 五个页面浏览器实测无阻断错误，Console 无应用报错 |

## 文档

| 文档 | 内容 |
| --- | --- |
| [docs/PRD.md](docs/PRD.md) | 产品定位、痛点、MVP 范围、用户故事、可验证验收条件、指标 |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | 前后端架构、模块边界、数据流、DeepSeek 调用流程、错误与安全 |
| [docs/DATABASE.md](docs/DATABASE.md) | 数据模型设计（13 张表、ER 图、索引、迁移策略） |
| [docs/ROADMAP.md](docs/ROADMAP.md) | Sprint 0–7 的分步计划与每阶段验收条件 |
| [docs/DESIGN_SYSTEM.md](docs/DESIGN_SYSTEM.md) | 视觉风格、颜色/字体/布局令牌、组件与交互规范 |

## 已知限制

1. **DeepSeek 模型 id 待确认**：`deepseek-flash` / `deepseek-v4-pro` 为当前配置默认值，需在 Sprint 2 对照 DeepSeek 官方文档核实后再启用真实调用。
2. **本轮不调用任何 AI 接口**，不产生 Token 费用。
3. **不做代码执行**：普通 Docker 容器不等于安全沙箱，本轮不实现也不宣称具备该能力。
4. **单用户本地形态**：无登录、无鉴权，不要直接部署到公网。
5. 移动端（<768px）抽屉导航已有实现（`md:` 断点 + Escape 关闭），但本次验收未做窄屏视觉截图。

## 许可证

MIT（`LICENSE`）。**版权方与授权方式待最终确认**，确认后即可用于开源发布。

## 下一步

下一阶段（Sprint 1）计划见 [docs/ROADMAP.md](docs/ROADMAP.md)：用户能力诊断 → DeepSeek AI 导师 → 课程与练习 → 错题复习 → 项目实践。
