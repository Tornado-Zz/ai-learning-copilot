# 贡献指南（Contributing）

感谢你想改进 **AI Learning Copilot**。这是一个**单人本地开发**的 MVP：
没有鉴权、只监听回环地址、默认不连真实 AI 服务。改动遵循「小步、可复跑、不留假数据」。

- 产品与范围：[docs/PRD.md](docs/PRD.md) ｜ 架构：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 接口口径：[docs/API.md](docs/API.md)（26 个端点，实测清单）
- 数据模型：[docs/DATABASE.md](docs/DATABASE.md)

---

## 1. 环境要求

| 组件 | 版本 | 说明 |
| --- | --- | --- |
| Python | 3.12.x | 由 `uv` 管理，不要用系统 Python 直接装依赖 |
| uv | 0.13+ | 后端依赖与命令入口（`uv sync` / `uv run`） |
| Node.js | 20+（实测 26.13.0） | 前端 |
| npm | 10+（实测 11.20.0） | 前端依赖 |
| Docker | 任意近期版本 | 只用来跑 PostgreSQL 17（仅绑定 `127.0.0.1:5432`） |

> Windows 用户注意：**PowerShell 5.1 不支持 `&&`**，请逐行执行；`curl` 是 `Invoke-WebRequest` 的别名，要写 `curl.exe`。

---

## 2. 本地启动：两条命令

### 2.1 一次性准备（每个新克隆只做一次）

```powershell
cd <仓库根>
Copy-Item infra\.env.example infra\.env
Copy-Item apps\api\.env.example apps\api\.env
Copy-Item apps\web\.env.example apps\web\.env.local
```

三份 `.env` 都被 `.gitignore` 忽略。`DEEPSEEK_API_KEY` **保持空着**：非 AI 功能照常工作，AI 端点会按设计返回 503。

### 2.2 起服务 + 自检

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ci.ps1      # 本地跑一遍 CI 的全部命令
```

- 第一条：起 PostgreSQL → 等 healthy → `alembic upgrade head` → 起 API（`127.0.0.1:8000`）→ 构建并起 Web（`127.0.0.1:3000`）。**它会自动补齐 2.1 的 `.env`**（缺哪个就从对应 `.env.example` 复制），并在首次运行时执行 `npm ci` 与 `npm run build`——所以新克隆只需这一条命令→ 等到两者都能应答。
- 第二条：只读自检（数据库健康、迁移到 head、API 端点结构、页面是否 200），**不写任何业务数据**；全部 `PASS` 才算跑通。
- 第三条：**与 GitHub Actions 完全相同的 9 个步骤**（后端 5 步 + 前端 4 步），任何一步非 0 退出码都会列在末尾。推送前跑一次，就不会出现「推上去才发现 CI 红」。

手动启动的完整步骤（四步）见 [README.md](README.md#本地启动windows-powershell)。接口交互式文档：<http://127.0.0.1:8000/docs>。

---

## 3. 测试与检查命令

改动提交前，后端两档 + 前端三项都应通过。

| # | 目的 | 命令 | 需要数据库 |
| --- | --- | --- | --- |
| 1 | 后端单元档（默认，最快） | `cd apps\api` → `uv run pytest -q` | 否（默认 `-m 'not integration'`） |
| 2 | 后端集成档 | `cd apps\api` → `uv run pytest -q -m integration` | **是**（先起 `infra\docker-compose.yml`） |
| 3 | 前端类型检查 | `cd apps\web` → `npx tsc --noEmit` | 否 |
| 4 | 前端 lint | `cd apps\web` → `npm run lint` | 否 |
| 5 | 前端生产构建 | `cd apps\web` → `npm run build` | 否 |
| 6 | 迁移一致性 | `cd apps\api` → `uv run alembic current`（应为 head） | 是 |

约定：

- **单元档必须能在数据库停止的情况下全绿**——这是硬约束，不是建议。不要因为在 CI 里加个 service 就让单元档依赖数据库。
- **集成档目前依赖“已有开发数据”**：部分用例断言「库里已有 5 条诊断 / 12 条提交等历史行未丢失」，在全新数据库上会失败。它在你本机能过，是因为本机库里有历史数据；把它改造成自洽的用例是待办项（见 [README 已知限制](README.md#已知限制) 第 3 条）。
- 测试**不得发起真实网络请求**（AI 与知识抓取一律用假实现/桩）。
- 测试**不得删除数据**：不写 `DELETE` / `TRUNCATE` / `DROP`，不跑 `alembic downgrade`，不执行 `docker compose down -v`。集成档用事务回滚 + 自建用户隔离状态。
- 新增数据库迁移：`uv run alembic revision -m "描述"`，并在 PR 里说明「向前兼容 / 是否需要回填」。
- 新增环境变量：**四处 `.env.example`（根、`apps/api`、`apps/web`、`infra`）同步更新**，值只能是占位或本地默认值。

---

## 4. 提交信息约定（Conventional Commits）

```
<type>(<scope>): <subject>
```

- `type`：`feat` / `fix` / `docs` / `test` / `refactor` / `perf` / `build` / `ci` / `chore`
- `scope`：可选，取模块名：`api` / `web` / `db` / `docs` / `infra` / `ci`
- `subject`：祈使句、不加句号、中文或英文都行，控制在 50 字符内

示例：

```
feat(api): 增加知识库来源过期标记
fix(web): 修正 /plan 页在无计划时的空状态
docs(api): 补齐 /knowledge/ingest 的 403 说明
ci: 为 api job 增加 postgres service
```

规则：

- 一个提交只做一件事；格式调整与逻辑改动分开提交。
- 破坏兼容的改动在 `type` 后加 `!`（如 `feat(api)!: 调整诊断提交响应字段`），并在正文写清迁移方式。
- 正文里引用 issue：`Closes #12`。

---

## 5. Pull Request 检查清单

提交 PR 前自查，逐条打勾（在 PR 描述里贴这份清单）：

- [ ] `uv run pytest -q` 全绿（**数据库停止**状态下也一样）
- [ ] `uv run pytest -q -m integration` 全绿（数据库在线；未依赖任何真实网络）
- [ ] `npx tsc --noEmit` 退出码 0
- [ ] `npm run lint` 退出码 0
- [ ] `npm run build` 退出码 0
- [ ] `uv run alembic current` 为 head；新增迁移已在干净库上 `upgrade head` 验证过
- [ ] 接口有变化时，[docs/API.md](docs/API.md) 已同步（含错误码）
- [ ] 新增/修改的环境变量已同步到**四处** `.env.example`
- [ ] 行为变化已记入 [CHANGELOG.md](CHANGELOG.md)
- [ ] 没有提交任何密钥、令牌、真实用户数据、`.env` 文件
- [ ] 没有回退他人的未提交改动（工作树里别人的改动不属于你）
- [ ] CI（`.github/workflows/ci.yml`）两个 job 都是绿的

PR 描述请包含：**做了什么 / 为什么 / 怎么验证的（贴关键命令与输出）**。只写「已测试」不算证据。

---

## 6. 禁止事项（重要）

1. **绝不提交真实 Key**：`DEEPSEEK_API_KEY`、数据库口令、任何令牌都不许进仓库、issue、PR、截图。`.env.example` 里只能留空或占位值。万一误传，立刻作废该 Key 并说明。
2. **不擅自扩大知识抓取白名单**：`KNOWLEDGE_DOC_URLS` 只允许 `docs.python.org` 的文档页与仓库内 `repo://lesson/<code>`。新增外部域名需要单独评审（涉及机器人协议、版权与 SSRF 风险），不要顺手加进白名单或改掉 `BLOCKED_HOST` 判断。
3. **不执行用户代码**：判题是静态规则 + 自报输出比对。不要加 `exec` / `eval` / 子进程执行提交代码的路径，也不要用普通 Docker 容器冒充「安全沙箱」。
4. **不破坏数据**：不跑 `DROP` / `TRUNCATE` / `alembic downgrade` / `docker compose down -v`；迁移只向前。
5. **不改成公网可访问**：绑定地址保持 `127.0.0.1`，不要改成 `0.0.0.0`，不要在没有鉴权的情况下部署到公网（v0.1.0 没有任何鉴权）。
6. **不伪造证据**：报告与 PR 里的命令输出必须是实际跑出来的。没跑的写「未执行」，不要抄历史记录当成当前结果。
7. **不提交 `.env` 或业务数据库数据**：`infra/.env`、`apps/api/.env`、`apps/web/.env.local` 都在 `.gitignore` 里，别用 `git add -f` 绕过。

---

## 7. 许可证

提交即表示你同意以 [MIT](LICENSE) 许可发布你的贡献。
