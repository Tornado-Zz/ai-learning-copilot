# SPRINT 1A 测试结果

> 本文件记录 Sprint 1A（契约冻结轮）**实际执行**的命令与结果，执行时间 2026-11-03 21:5x (+08:00)。
> 本轮只改文档，未改任何业务代码、未执行数据库迁移。

## 1. 执行环境

| 组件 | 版本 |
|---|---|
| Node.js / npm | v26.13.0 / 11.20.0 |
| uv / Python（uv 托管） | 0.13.5 / 3.12.15 |
| Next.js / React / TypeScript | 16.4.4 / 19.3.0 / 5.9.3 |
| Pytest | 9.2.0 |
| PostgreSQL（容器，本轮未使用） | 17.11 |

## 2. 代码侧测试与 lint（本轮未改代码，重跑以证明无回归）

| # | 命令 | 工作目录 | 退出码 | 结果 |
|---|---|---|---|---|
| 1 | `npx tsc --noEmit` | `apps/web` | **0** | 无输出，类型检查通过 |
| 2 | `npm run lint` | `apps/web` | **0** | eslint 无错误无告警 |
| 3 | `npm run build` | `apps/web` | **0** | 构建成功，11 行路由树输出 |
| 4 | `uv run pytest -q` | `apps/api` | **0** | `11 passed, 1 deselected in 6.25s` |
| 5 | `uv run pytest -q -m integration` | `apps/api` | **0** | `1 passed, 11 deselected in 0.21s` |

无任何失败用例，因此本文件不含失败堆栈。

## 3. 文档契约一致性校验（本轮的主要交付凭证）

| 校验项 | 方法 | 结果 |
|---|---|---|
| 六种情况表 v2 五方一致 | 抽取表头 + 8 行，逐行 `tr -d ' '` 后 `diff` | **PRD == DATABASE == ARCHITECTURE == ROADMAP == CONTRACT，全部 SAME** |
| A.6 第 4 行逐字 | `sed` 取 PRD:253 与 CONTRACT 对应行，`diff` | **byte-identical** |
| 旧口径残影 | `grep -c 'verification_status'` | 仅出现在「该列已删除」说明中；`'unverified'` 计数 **0** |
| 占位符 | `grep -c 'TODO\|TBD'` 六份文档 | **全部 0** |
| 表数量口径 | `grep -c '15 张'` / `只创建 5 张` | DATABASE 4 / 2，ROADMAP 1，ARCHITECTURE 1（措辞不同、语义一致） |
| 迁移名一致 | `grep -c '0002_sprint1a_identity_diagnostics'` | ARCHITECTURE 1、DATABASE 2、ROADMAP 1、CONTRACT 2 |
| 版本行 | 人工核对 | PRD / ROADMAP / DATABASE / ARCHITECTURE 均为 v1.1 或 v1.2（标注不一致，不影响契约；见 DECISIONS §5） |

## 4. 文档规模

| 文件 | 行数 | 本轮变化 |
|---|---|---|
| `docs/PRD.md` | 673 | 612 → 673 |
| `docs/DATABASE.md` | 962 | 785 → 962 |
| `docs/ARCHITECTURE.md` | 634 | 514 → 634 |
| `docs/ROADMAP.md` | 479 | 448 → 479 |
| `docs/SPRINT1A_CONTRACT.md` | 424 | 新建 |
| `docs/DESIGN_SYSTEM.md` | 437 | 未改 |

## 5. 工作树状态

```
git status --porcelain -uall
 M README.md                     (上一轮：监听地址说明)
 M apps/web/package.json         (上一轮：-H 127.0.0.1 安全加固，本轮未动)
 M docs/ARCHITECTURE.md          (本轮)
 M docs/DATABASE.md              (本轮)
 M docs/PRD.md                   (本轮)
 M docs/ROADMAP.md               (本轮)
?? CHANGELOG.md                  (上一轮审查交付)
?? REVIEW_REPORT.md              (上一轮审查交付)
?? TEST_RESULTS.md               (上一轮审查交付)
?? docs/SPRINT1A_CONTRACT.md     (本轮新建)
```

本轮**没有**修改 `apps/api/**`、`apps/web/src/**`、`infra/**`，也没有新增依赖。

## 6. 本轮未执行的检查（及原因）

| 项目 | 原因 |
|---|---|
| `alembic upgrade head` 执行 0002 新迁移 | 复审明确要求「不执行有破坏性的数据库变更」；0002 仅为草案 |
| 业务表 DDL 与约束测试实跑 | 同上；约束测试清单（21 条）已冻结为 S1 实施时的验收项 |
| DeepSeek 真实调用 | 本轮及 Sprint 1 均不调用，避免产生费用 |
| 前端页面浏览器验收 | 本轮无前端改动，未重复 Sprint 0 的逐页截图 |
| 移动端 <768px 视觉验收 | 本机浏览器工具无法设置视口宽度（沿用已知限制） |

## 7. 结论

- 代码侧：**0 失败**，lint / 类型检查 / 构建 / 两档测试全部通过，无回归。
- 文档侧：**五份文档口径一致**，两张逐字表（六种情况表 v2、A.6 取值例子）在 PRD / DATABASE / ARCHITECTURE / ROADMAP / CONTRACT 之间零差异。
- 未执行任何破坏性数据库操作，未推送 GitHub，未开始 Sprint 1B。