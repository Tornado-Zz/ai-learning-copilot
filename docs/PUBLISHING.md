# 发布到 GitHub

> 本仓库当前状态：分支 `main`、30+ 个提交、标签 `v0.1.0` … `v0.1.8`（9 个）、工作区干净、**未配置 remote**。
> 下面两种方式任选其一；推荐方式 A——它不需要把任何凭据交给别人。

## 发布前自检（本机执行，全绿才推）

```powershell
cd apps\api
uv run pytest -q                  # 单元档：125 passed
uv run pytest -m integration -q   # 集成档：85 passed（已 hermetic，干净库同样全绿）

cd ..\web
npx tsc --noEmit                  # 0
npm run lint                      # 0
npm run build                     # 0

cd ..\..
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1   # 17 项 PASS
```

## 方式 A：你自己建仓库并推送（推荐）

1. 在 GitHub 上新建一个**空仓库**（不要勾选 README / .gitignore / license，避免与本地冲突）。
2. 在本仓库根目录执行：

```powershell
git remote add origin https://github.com/<你的账号>/<仓库名>.git
git push -u origin main
git push origin --tags          # 推送全部 9 个标签；也可只推某一个：git push origin v0.1.8
```

3. 推送后确认两件事：
   - GitHub 仓库首页能看到 9 个标签（`v0.1.0` … `v0.1.8`）；
   - **Actions 里 CI 两个 job（`api`、`web`）都是绿色**。CI 用真实 PostgreSQL 17 起库并跑两档测试，不依赖任何 secret。

> 若使用 SSH：`git remote add origin git@github.com:<账号>/<仓库名>.git`，其余相同。

## 方式 B：交给有 repo 权限的 token 代推

```powershell
git remote add origin https://<token>@github.com/<账号>/<仓库名>.git
git push -u origin main --tags
```

推完立刻在 GitHub 上**撤销该 token**。不建议长期使用这种方式。

## 推送前必须确认的三件事

### 1. 没有真实密钥进入版本库

- `apps/api/.env` 被 `.gitignore` 忽略，仓库里只有 `.env.example`（Key 留空）。
- 本次发布前已执行全历史扫描：`git log -p --all | grep -E 'sk-[a-f0-9]{20,}'` → **0 命中**。
- ⚠️ **开发期间用于联调的 DeepSeek Key 曾在会话中出现过，建议在发布前到平台轮换一次**，并把新 Key 只写进本机 `apps/api/.env`。

### 2. 数据库与数据不进仓库

PostgreSQL 数据在 Docker volume 里，`infra/docker-compose.yml` 只提供本地开发配置；仓库不含任何 `.sql` 备份或用户数据。

### 3. 已知边界要写清楚

`README.md` 与 `docs/API.md` 已如实声明：**单用户、无鉴权、服务端不执行用户代码、AI 与知识库入库默认关闭**。这些是 v0.1.0 的设计取舍，不是遗漏。

## 推送之后

- 仓库设置里把 `main` 设为默认分支并开启分支保护（要求 CI 通过才能合并）。
- 首次发布可在 Releases 里基于最新标签 `v0.1.8` 写发布说明；每个标签对应的内容都能在 `CHANGELOG.md` 的同版本段落里找到。