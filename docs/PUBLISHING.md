# 发布到 GitHub

> **本仓库当前状态**：分支 `main`、**70 个提交**、标签 `v0.1.0` … `v0.1.36`（**37 个**）、工作区干净、**未配置 remote**。
> 下面两种方式任选其一；推荐方式 A——它不需要把任何凭据交给别人。

## 发布前自检（本机执行，全绿才推）

```powershell
# 一条命令跑完与 GitHub Actions 相同的 12 步（前后端 + 文档一致性 + 依赖基线）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\ci.ps1

# 另需开发服务在跑时才能做的一项：
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1   # 18 项 PASS
```

当前基线（数字对不上时，先查是不是有人改了内容忘了同步）：

| 检查 | 期望 |
| --- | --- |
| 单元档 | `166 passed` |
| 集成档（hermetic） | `149 passed, 1 skipped` |
| `tsc` / `eslint` / `next build` | 全部退出码 0 |
| `ruff check app tests migrations` | All checks passed |
| 文档一致性 | 全部一致（head `0016_sprint11_return_rule`，16 个迁移） |
| 依赖基线 | 运行时 0 告警；开发依赖 16 条（均为 ESLint 链，见 `SECURITY.md`） |

## 先看这一条：本机只能走 SSH，不能走 HTTPS

实测（2026-11-05，本机）：

| 通道 | 结果 |
| --- | --- |
| `https://github.com` （443） | **超时不可达**（21 秒后失败，无任何提示） |
| `ssh github.com`（22） | **可达**（握手成功，只是还没有密钥） |
| `ssh ssh.github.com`（443） | 可达 |
| `https://api.github.com` | 可达（200） |

结论：**在这台机器上用 `https://` 的地址推送一定失败**。要用 SSH 地址：

```
git@github.com:<你的账号>/<仓库名>.git
```

本机目前**没有 SSH 密钥**（`~/.ssh` 下只有 known_hosts）。首次推送前先做一次：

```powershell
ssh-keygen -t ed25519 -C "852604336@qq.com"     # 一路回车即可
Get-Content $HOME\.ssh\id_ed25519.pub          # 复制这一整行
```

把复制到的公钥贴进 GitHub → Settings → SSH and GPG keys → New SSH key，然后用 `ssh -T git@github.com` 验证（出现 `Hi <账号>! You've successfully authenticated` 即成功）。

`scripts/publish.ps1` 会**先探测这两条通道**：如果给的是 https 地址而 https 不可达，它会直接拒绝运行并打印应使用的 SSH 地址，不会让你等 20 秒再看到一句没头没尾的失败。

## 方式 A：你自己建仓库并推送（推荐）

1. 在 GitHub 上新建一个**空仓库**（不要勾选 README / .gitignore / license，避免与本地冲突）。
2. 在本仓库根目录执行：

```powershell
# 一条命令：先自检，再配置 origin 并推送 main 与全部标签（从不 force push）
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\publish.ps1 `
  -RepoUrl https://github.com/<你的账号>/<仓库名>.git
```

脚本会依次：工作区是否干净 → **扫描全部历史的密钥**（命中即中止）→ 文档一致性 → 单元测试 → 配置 origin → 推送。加 `-SkipTests` 可跳过测试。

想手动执行等价命令：

```powershell
git remote add origin https://github.com/<你的账号>/<仓库名>.git
git push -u origin main
git push origin --tags          # 推送全部 37 个标签
```

3. 推送后确认三件事：
   - 仓库首页能看到 **37 个标签**（`v0.1.0` … `v0.1.36`）；
   - **Actions 里两个 job（`api`、`web`）都是绿色**——CI 用真实 PostgreSQL 17 起库、跑两档测试，全程不引用任何 secret；
   - README 首页的**六张截图能正常显示**（图片在 `docs/images/`，用的是相对路径）。

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
- 每次发布前执行全历史扫描：`git log -p --all | grep -E 'sk-[a-f0-9]{20,}'` → 应为 **0 命中**。
- ⚠️ **开发期间用于联调的 DeepSeek Key 曾在会话中出现过，建议在发布前到平台轮换一次**，并把新 Key 只写进本机 `apps/api/.env`。

### 2. 数据库与数据不进仓库

PostgreSQL 数据在 Docker volume 里，`infra/docker-compose.yml` 只提供本地开发配置；仓库不含任何 `.sql` 备份或用户数据。

### 3. 已知边界要写清楚

`README.md`、`docs/API.md`、`docs/UX_NOTES.md` 已如实声明：**单用户、无鉴权、服务端不执行用户代码（但会做语法解析）、AI 与知识库入库默认关闭、静态规则可被字符串常量绕过**。这些是 v0.1.x 的设计取舍，不是遗漏。

## 推送之后

- 仓库设置里把 `main` 设为默认分支，并开启分支保护（要求 CI 通过才能合并）。
- 首次发布在 Releases 里基于最新标签 `v0.1.36` 写说明；每个版本的内容都在 `CHANGELOG.md` 的同版本段落里。
- 若 CI 首次运行有意外失败：本机 `scripts/ci.ps1` 跑的是**同一批命令**，先在本地复现能省很多来回。