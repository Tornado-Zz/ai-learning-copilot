# 贡献指南（Contributing）

感谢你想改进 **AI Learning Copilot**。这是一个**单人本地开发**的 MVP：
没有鉴权、只监听回环地址、默认不连真实 AI 服务。改动遵循「小步、可复跑、不留假数据」。

- 产品与范围：[docs/PRD.md](docs/PRD.md) ｜ 架构：[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- 接口口径：[docs/API.md](docs/API.md)（37 个操作 / 34 条路径，实测清单）
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

cd apps\web
node scripts/dead-exports-check.mjs   # 死导出自查（0 = 干净；发现即退出码 1）
node scripts/audit-check.mjs          # 依赖基线（运行时必须 0；离线时退出码 2 并明说未检查）

cd ..\..
node scripts/docs-consistency-check.mjs   # 文档里的端点/表/迁移声明与源码是否一致
```

- 第一条：起 PostgreSQL → 等 healthy → `alembic upgrade head` → 起 API（`127.0.0.1:8000`）→ 构建并起 Web（`127.0.0.1:3000`）。**它会自动补齐 2.1 的 `.env`**（缺哪个就从对应 `.env.example` 复制），并在首次运行时执行 `npm ci` 与 `npm run build`——所以新克隆只需这一条命令，等到 API 与 Web 都能应答即可。
- 第二条：只读自检（数据库健康、迁移到 head、API 端点结构、页面是否 200），**不写任何业务数据**；全部 `PASS` 才算跑通。
- 第三条：**与 GitHub Actions 完全相同的 10 个步骤**（后端 6 步含 `ruff check`，前端 4 步），任何一步非 0 退出码都会列在末尾。推送前跑一次，就不会出现「推上去才发现 CI 红」。运行前请先停掉开发服务：`npm ci` 会重建 `node_modules`，而 `next start` 正持有 `next-swc` 文件；脚本检测到 3000 端口被占用时会直接退出并说明原因。

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
5. **不改成公网可访问**：绑定地址保持 `127.0.0.1`，不要改成 `0.0.0.0`，不要在没有鉴权的情况下部署到公网（v0.1.x 全部版本都没有鉴权）。
6. **不伪造证据**：报告与 PR 里的命令输出必须是实际跑出来的。没跑的写「未执行」，不要抄历史记录当成当前结果。
7. **不提交 `.env` 或业务数据库数据**：`infra/.env`、`apps/api/.env`、`apps/web/.env.local` 都在 `.gitignore` 里，别用 `git add -f` 绕过。

---

## 7. 踩过的坑（真实发生过，别重复）

这一节不是理论清单：每一条都在这个仓库里**真的发生过**，有的还发生了不止一次。踩之前先读，能省掉半小时。

### 7.1 前端：改了代码却看到旧界面

`next start` 提供的是**构建产物**，不是源码。改完 `apps/web/src/**` 而不重新构建，浏览器里永远是旧界面——你会以为是逻辑 bug，实际只是没构建。**曾经为此浪费过一整轮。**

```powershell
# 正确顺序：先停，再构建，再起
Get-NetTCPConnection -LocalPort 3000 | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force }
cd apps\web; npm run build; npm run start
```

截图时尤其注意：侧栏版本号与「服务版本」两处都应为当前版本，否则说明前后端有一边是旧的。

### 7.2 服务在跑时不要安装依赖或构建

`npm ci` 会先删 `node_modules`，而 `next start` 正持有 `node_modules/@next/swc-*.node`，`unlink` 报 **EPERM**，还会把正在跑的前端一起弄坏。在 `next start` 运行时跑 `npm run build` 也会让 `.next` 混入新旧 chunk。

`scripts/ci.ps1` 已经会在 3000/8000 被占用时拒绝执行——**不要绕过它自己直接跑 npm**（那样发生过一次，把 `node_modules` 弄坏后重新装了 675 个包）。

### 7.3 Windows：`npm` 是 `npm.cmd`，不能直接 spawn

- Node 18.20 起（CVE-2024-27980）**默认拒绝**执行 `.cmd`/`.bat`，`execFileSync('npm', …)` 会 ENOENT。要传 `shell: true`。
- `Start-Process -FilePath 'npm'` 在 PowerShell 里**静默什么都不做**。要用 `cmd.exe /c npm run start`。

两种表现不同，根因是同一个。

### 7.4 PowerShell 5.1 脚本必须是纯 ASCII

Windows PowerShell 5.1 会把**无 BOM** 的脚本按 ANSI 读。`.ps1` 里写中文注释会解析失败，报错还很难懂。`scripts/*.ps1` 一律 ASCII，中文字符串放到打印时也会乱码——要输出中文请用 Node 或 Python 脚本。

### 7.5 改了 `pyproject.toml` 就要 `uv lock`

CI 跑 `uv sync --locked`；只要 `pyproject.toml` 变了（哪怕只是版本号或 description），锁文件就失效，**CI 必红**。改完立刻：

```powershell
cd apps\api; uv lock; uv lock --check; uv sync --locked
```

### 7.6 版本号有四处，改一处等于没改

`app-version.ts`（界面）、`package.json`、`pyproject.toml`、`app/__init__.py`（`GET /health` 的 `version` 与 OpenAPI `info.version`）。第四处曾**落后 17 个版本**而无人察觉，界面一直显示旧服务版本。`scripts/docs-consistency-check.mjs` 会断言四处一致。

### 7.7 测试别依赖「共享用户的历史」

种子用户带着真实学习记录（完成的课程、终态计划行、到期复习、提交）。直接断言「今天应该排出 2 道练习」会随使用漂移，某天突然红。两类正确写法：

- 需要自带数据 → `tests/conftest.py` 的 `create_isolated_learner()`；
- 需要固定日期 → 走服务层并传 `today_override=`，别走 HTTP（HTTP 用真实时钟）。

### 7.8 写死「周几」的测试会随日历漂移

`study_days=[3]`（周三）在周四跑就排不出东西。更糟的是**空过**：场景要求「周二还没到」，周二过了之后断言恒真，测试通过但什么都没检验。用 `conftest` 的 `calendar_today()` / `future_weekdays()`，场景无法复现时显式 `pytest.skip` 并写明原因。

### 7.9 生成列不能直接 INSERT

`user_skill_levels.evidence_strength` 是**生成列**，插入时会报错；构造测试数据时只写可写列，并用 `verification_method='static_rule'` 满足 `ck_usk_strength_none_level0`。

### 7.10 迁移落地瞬间，`alembic current` 不再打印 `(head)`

迁移文件已存在但库里还没 upgrade 时，冒烟检查的「迁移到 head」一项会失败——这是**正确行为**，先 `alembic upgrade head` 再复跑。

### 7.11 路径与 shell 的两个小陷阱

- 本仓库路径含中文，Node 里取 `new URL(...).pathname` 会得到 `%E8%87%AA…`，**读不到目录**——用 `fileURLToPath()`。
- `git commit -m "多行带引号的消息"` 在 PowerShell 里容易把引号吃掉，用 `git commit -F 文件`。

### 7.12 Docker Desktop 会自己停

集成测试突然大面积 `ConnectionRefusedError` 或 `docker API … not found`，先看 Docker 是否还活着：

```powershell
docker info; docker compose -f infra\docker-compose.yml up -d
```

这不是代码问题，别去改测试。

---

## 8. 许可证

提交即表示你同意以 [MIT](LICENSE) 许可发布你的贡献。
