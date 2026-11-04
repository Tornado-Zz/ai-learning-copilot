# 安全说明

> 适用范围：v0.1.x（单用户、本地回环运行的 MVP）。这不是一个已部署到公网的服务。

## 报告问题

发现安全问题请在仓库开 Issue，标题加 `[security]`，**不要**在公开 Issue 里贴可利用细节或真实密钥。
本项目没有独立的私密披露渠道，因此更倾向于「先修再公开细节」。

## 设计上已经做到的边界

| 边界 | 现状 |
| --- | --- |
| 网络暴露面 | 三个端口（3000 / 8000 / 5432）**只监听 `127.0.0.1`**，不绑定 `0.0.0.0` |
| 鉴权 | **没有**。所有端点作用于同一个种子用户，这是 v0.1.x 的设计取舍；因此不要把它部署到可被他人访问的主机 |
| 用户代码 | **从不执行**。判题只做文本层面的静态规则匹配与自报输出比对 |
| API Key | 只从环境变量读取；不写入数据库、不写日志、不出现在任何响应里；异常信息做脱敏 |
| 知识抓取 | 域名白名单（仅 `docs.python.org` + 仓库内课程），入库端点默认关闭 |
| 出站内容 | AI 请求只带问题文本与课程/练习**标题**，不带用户提交的代码全文 |

## 依赖告警（如实记录）

`cd apps/web && npm audit` 目前报告 **16 个 moderate**，**全部位于 ESLint 及其插件的开发依赖链**（`minimatch` 的传递告警，经 `eslint-config-next` 引入）：

- 受影响的包：`eslint`、`eslint-config-next`、`@typescript-eslint/*`、`@next/eslint-plugin-next`、`eslint-plugin-import`、`eslint-plugin-jsx-a11y`、`eslint-plugin-react`、`@eslint/*`。
- **运行时依赖干净**：`next`、`react`、`react-dom`、`tailwindcss` 均无告警；生产依赖只有 3 个。
- 这些包只在本地 `npm run lint` / 构建时使用，不会进入产物，也不接收用户输入。
- `npm audit fix`（非 `--force`）无法消除；`--force` 会升级到与 `eslint-config-next` 不兼容的版本，反而破坏 lint。**因此选择等上游修复，而不是强行降级/升级。**

后端 `uv.lock` 目前没有已知告警。

### 这条基线是**可执行**的

```powershell
cd apps\web
node scripts/audit-check.mjs
```

- 运行时依赖（`npm audit --omit=dev`）**必须为 0** —— 硬门禁。
- 开发依赖告警数不得高于 `security-baseline.json` 里的 `dev.total`（当前 **16**）。新增告警会让脚本退出码 1，逼你复核后再更新基线。
- 离线时退出码 2，并明确打印「本次未做检查」——**不会静默跳过**。

这把「16 个告警」从一句口头说明变成了可回归的基线：如果哪天运行时依赖出了漏洞，CI 之外的这一步会立刻拦住。

## 你可以自己复核

```powershell
# 依赖告警
cd apps\web; npm audit

# 仓库里没有真实密钥（应为 0）
git log -p --all | Select-String -Pattern 'sk-[a-f0-9]{20,}'

# 端口只监听回环
netstat -ano | findstr 'LISTENING' | findstr ':3000 :8000 :5432'

# 系统自检
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1
```

## 发布前必做

1. 若曾把 `DEEPSEEK_API_KEY` 贴进任何聊天、截图或 Issue，**先去平台轮换**，再填本机 `apps/api/.env`。
2. 确认 `git log -p --all` 的密钥扫描为 0。
3. 确认 `.env` 类文件仍在 `.gitignore` 中（仓库里只有 `.env.example`，Key 留空）。