# 测试结果（Sprint 1 准入审查轮）

> 本文件记录的是**本次审查轮实际执行**的命令与结果，执行时间 2026-11-03 21:33 (+08:00)。
> 未引用 README 或任何历史记录中的测试结果。

## 1. 执行环境

| 组件 | 版本（本次实测） |
|---|---|
| Node.js | v26.13.0 |
| npm | 11.20.0 |
| uv | 0.13.5 (46776a95d 2026-10-21 x86_64-pc-windows-msvc) |
| Python（uv 托管） | 3.12.15 |
| Docker | 29.9.2, build a82e528 |
| Docker Compose | v5.6.1 |
| PostgreSQL（容器内） | PostgreSQL 17.11 on x86_64-pc-linux-musl |
| Next.js / React / TypeScript / Tailwind | 16.4.4 / 19.3.0 / 5.9.3 / 4.3.4 |
| FastAPI / SQLAlchemy / Pydantic / Alembic | 0.162.0 / 2.1.6 / 2.14.2 / 1.20.1 |

## 2. 执行记录

| # | 命令 | 工作目录 | 退出码 | 结果摘要 |
|---|---|---|---|---|
| 1 | `npx tsc --noEmit` | `apps/web` | **0** | 无输出，类型检查通过 |
| 2 | `npm run lint` | `apps/web` | **0** | `eslint` 无告警无错误 |
| 3 | `npm run build` | `apps/web` | **0** | `▲ Next.js 16.4.4 (Turbopack)`；`✓ Compiled successfully in 217ms`；`✓ Generating static pages using 9 workers (8/8) in 583ms` |
| 4 | `uv run pytest -q` | `apps/api` | **0** | `11 passed, 1 deselected in 6.32s` |
| 5 | `uv run pytest -q -m integration` | `apps/api` | **0** | `1 passed, 11 deselected in 0.28s` |
| 6 | `uv run pytest --collect-only -q` | `apps/api` | 0 | `11/12 tests collected (1 deselected)` |
| 7 | `uv run alembic current` | `apps/api` | 0 | `0001 (head)` |
| 8 | `docker compose -f infra/docker-compose.yml ps` | 仓库根 | 0 | `ai-learning-copilot-postgres`｜`Up About an hour (healthy)`｜`127.0.0.1:5432->5432/tcp` |
| 9 | `psql -U copilot -d copilot -tAc "select version()"` | 容器内 | 0 | `PostgreSQL 17.11 ...` |
| 10 | `psql ... "select count(*) from information_schema.tables where table_schema='public' and table_name<>'alembic_version'"` | 容器内 | 0 | `0`（无业务表，符合「本轮不建业务表」） |
| 11 | `curl http://127.0.0.1:8000/api/v1/health` | — | 0 | HTTP **200**：`{"status":"ok","service":"ai-learning-copilot-api","version":"0.1.0","environment":"local","timestamp":"2026-11-03T13:33:42.234786Z","ai_configured":false}` |
| 12 | `curl http://127.0.0.1:8000/api/v1/ready` | — | 0 | HTTP **200**：`{"status":"ready","checks":{"database":{"status":"connected","latency_ms":5,"detail":null}}}` |
| 13 | `git log --oneline` | 仓库根 | 0 | `f06dab4 chore: sprint 0 scaffold - docs, fastapi skeleton, next.js app shell` |
| 14 | `git status --porcelain -uall` | 仓库根 | 0 | 6 行（本轮修改的 6 个文件），无未跟踪垃圾文件 |
| 15 | 密钥扫描 `grep -rlE "sk-[A-Za-z0-9]{16,}|BEGIN (RSA|OPENSSH) PRIVATE KEY"` | 仓库根 | 0 | **0 命中** |

## 3. 测试数量

| 类别 | 数量 | 说明 |
|---|---|---|
| 后端测试用例总数 | 12 | `--collect-only` 收集结果 |
| 默认执行（单元） | 11 passed | 不依赖数据库，库未启动也应通过 |
| 默认排除 | 1 deselected | 标记为 `integration`，需真实数据库 |
| 集成执行 | 1 passed | 数据库在线时执行 |
| 前端静态检查 | 3 项 | tsc、eslint、production build |
| HTTP 契约检查 | 2 项 | health 200、ready 200 |
| 数据库检查 | 3 项 | 容器 healthy、版本、业务表计数 |

## 4. 失败信息

**本次执行没有任何命令返回非零退出码，也没有任何测试失败或错误。**

因此本文件不含失败堆栈。以下两类是已知的非失败现象，记录以免日后误判：

1. 后端未启动时，前端页面 Console 会出现 2 条 `Failed to load resource: net::ERR_CONNECTION_REFUSED`，属浏览器网络层日志；应用代码中 `console.` 调用计数为 0（`grep -rn "console\." apps/web/src | wc -l` → `0`）。
2. `/api/v1/ready` 在数据库停止时会返回 **503**（`status="not_ready"`、`detail="database probe timed out after 2s"`），这是设计行为而非失败；`/api/v1/health` 同时保持 200，服务不崩溃。该分支已在 Sprint 0 验收中实测。

## 5. 复现方式

```powershell
cd "F:\ai自学产品\ai-learning-copilot"

# 数据库
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps

# 前端
cd apps\web
npx tsc --noEmit
npm run lint
npm run build

# 后端
cd ..\api
uv run pytest -q
uv run pytest -q -m integration
uv run alembic current
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000
```

另开一个 PowerShell 窗口验证接口：

```powershell
curl.exe -s -w "`nHTTP=%{http_code}`n" http://127.0.0.1:8000/api/v1/health
curl.exe -s -w "`nHTTP=%{http_code}`n" http://127.0.0.1:8000/api/v1/ready
```

## 6. 本轮未执行的检查

| 项目 | 原因 |
|---|---|
| 真实 DeepSeek API 调用 | 本轮及 Sprint 0 均不调用，避免产生费用 |
| 用户代码执行 / 沙箱 | 明确禁止实现；`self_check` 与 `static_rule` 不代表代码真实运行 |
| 移动端 <768px 视觉验收 | 本机浏览器工具无法设置视口宽度，代码层断点与抽屉逻辑已核对但无截图 |
| 浏览器逐页截图（本轮） | 本轮无前端业务改动（仅改 `package.json` 启动脚本），未重复 Sprint 0 的逐页验收 |