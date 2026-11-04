# Changelog

本项目的所有重要变更记录在此文件。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

## [0.1.12] — 2026-11-04

**产品第一次有了 AI 内容。** 此前 5 节课全是 Python 基础，而六个技能域里有 API 与 LLM——一个叫「AI 学习」的产品没有 AI 课程。

### Added

- 迁移 `0011_sprint7_ai_content`：两节已发布课程 + 四道练习（每课 2 道），**完全离线可学**，不要求网络或 API Key。
  - `route_a.api.json`「请求、响应与 JSON」（a3，25 分钟）：HTTP 方法与状态码、JSON 结构、用 `json.loads` 解析示例响应文本。
  - `route_a.llm.messages`「调用大模型的请求长什么样」（a4，30 分钟）：消息数组与三种角色、`temperature` / `max_tokens`、token 与计费、响应形状、按状态码排错。
- 课程正文与现有 5 节同款六块结构；`common_mistakes` 写成 mistake / why / fix 三段。

### Changed

- 版本号三处来源（`app-version.ts` / `package.json` / `pyproject.toml`）统一到 **0.1.12**。此前界面一直显示 `v0.1.3`——第 5 轮建立的单一来源常量之后从未更新。

### Fixed

- **文档一致性检查器自身的 bug**：`revision` 正则只认 `revision = "..."`，不认新迁移里的 `revision: str = "..."`，导致它把 head 报成旧版本。**检查器给出过期真值是最危险的失败方式**，已修正并加注释。
- 检查器新增「版本号三处必须一致」，并**刻意不检查**「N 节课程 / N 道练习」——这两个数字在文档里既是当前总量、也是 S7 目标（60 节）或规则（至少 6 道、一天最多 1 道），试加后产生 12 条误报。会喊狼的检查器比没有更糟，理由已写进脚本。

### Verified

- 判题双向自洽：starter 原样提交 **7/13 通过（判失败）**；参考解 **14/14 通过**，证据强度 `assessed`。
- 迁移幂等：`0010` 时 5 节 → 首次 head **7 节 / 14 练习** → 再次 head 仍是 **7 / 14**。
- `130 passed`（单元）/ `134 passed`（集成，新增 7 条内容测试）/ `ruff` 干净 / 全新数据库集成档同样 134 passed。
- `scripts/ci.ps1` 十一步全绿；浏览器确认 `/learn` 列出 7 节课、新课程页正常渲染、Console 0 报错、侧栏显示 `v0.1.12`。

## [0.1.11] — 2026-11-04

把依赖告警从「文档里的一句话」变成**可回归的基线**。

### Added

- `apps/web/scripts/audit-check.mjs`：用 npm 自己的语义把两类问题分开——
  - `npm audit --omit=dev` **运行时依赖必须为 0**（硬门禁）；
  - `npm audit` 全量告警数不得高于 `apps/web/security-baseline.json` 的 `dev.total`（当前 16）。
  - 离线时退出码 **2** 并明确打印「本次未做检查」——**不静默跳过**。
- `apps/web/security-baseline.json`：记录 16 个 dev-only 告警的范围、为什么不能用 `--force` 修、以及人工复核结论（逐个看 via 链，均不含 `next`/`react`/`react-dom`）。
- 接入 `scripts/ci.ps1` 的 security 步骤（容忍退出码 2 并给出可见警告），`CONTRIBUTING.md` 与 `SECURITY.md` 列出三个自查脚本。

### Fixed

- `audit-check.mjs` 首次运行报「审计不可用」。根因是 **Node 18.20 起（CVE-2024-27980 修复）默认拒绝执行 `.cmd`/`.bat`**，而 Windows 上 `npm` 就是 `npm.cmd`，`execFileSync` 直接 spawn 会 ENOENT。补 `shell: true` 后正常。这与之前 `Start-Process` 启动不了 `npm` 是同一类问题，只是报错方式不同。
- `scripts/ci.ps1` 里我一度写进中文注释（34 个非 ASCII 字符），会破坏 Windows PowerShell 5.1 的解析；已改回纯 ASCII 并加检测。

### Verified

- 基线匹配：`运行时依赖告警 0 / 全部 16 / 符合基线`，退出码 0。
- 基线调低到 15：打印「开发依赖告警由 15 增加到 16」并退出码 1；恢复后回到 0。
- 三个自查脚本一次性全跑通：文档一致性、依赖基线、死导出（377 个导出 0 个死代码）。

## [0.1.10] — 2026-11-04

把「文档一致性」从人工比对变成**可执行检查**。

### Added

- `scripts/docs-consistency-check.mjs`：零依赖，只读源码树（不需要服务或数据库），从四个来源推导真值并与文档里的数字声明比对——
  - 迁移 head：`revision` / `down_revision` 图里没有后继的那个；
  - 迁移版本数：`migrations/versions` 下的文件数；
  - 业务表数：`CREATE TABLE` 去重后的表名数；
  - 接口操作数：`@router.<verb>` 装饰器数量；
  - 页面路由数：`src/app` 下的 `page.tsx` 数量。
  不一致时按 `文件:行号` 逐条报出并退出码 1。
- 接入 `scripts/ci.ps1`（在 job 之前单独一步）与 `.github/workflows/ci.yml` 的 `web` job（只需要 Node）。

### Verified

- **双向验证**：把 README 的 `15 张业务表` 改成 `16` → 输出 `README.md:7 业务表数 文档写 16，实际 15`、退出码 1；改回 → `文档一致性：全部一致`、退出码 0。
- 工作流用 pyyaml 解析确认结构：`api` 8 步、`web` 7 步（含新增的 `Docs consistency`）。
- `scripts/ci.ps1` 十一步全绿：docs consistency → uv sync --locked → ruff → 迁移 → head 校验 → 130 单元 → 127 集成 → npm ci → tsc → lint → build。

## [0.1.9] — 2026-11-04

文档一致性总检：把 7 份文档与当前实现逐条对齐。**这一轮没有改任何代码**，只改说法。

### Fixed

- **`docs/DATABASE.md` 与实现严重不符**：设计稿里有 4 张**从未建过**的表（`exercise_test_cases`、`mistakes`、`review_tasks`、`projects`），而实际存在的 `review_items`、`capstone_submissions`、`knowledge_sources`、`knowledge_chunks` **完全没写**。新增第 0 节「实现现状（as-built）」：列出实际 15 张表与迁移 head，逐条说明那 4 张设计稿表**被什么替代**（自检用例进 `exercises.visible_tests`；错题本与复习合并为 `review_items`，且间隔是 1/3/7/14 天而**不是**设计稿写的 1/3/7/14/30 天；项目实践改为 `capstone_submissions`），并声明第 4 节仍是冻结设计基线。
- **README 停在 v0.1.1**：迁移写 `0007`（实际 `0010`）、`28 个端点`（实际 37 操作 / 34 路径）、`13 条页面路由`（实际 14）。
- **README 的质量门禁表会误导贡献者**：仍写着集成档「需要预置数据库、在全新数据库上会失败」。该说法自 hermetic 化之后已不成立，现改为「全新数据库同样全绿」。同步补上 CI 的 `ruff check` 步骤与 head 校验。
- `docs/API.md`、`docs/README.md`、`CONTRIBUTING.md`、`docs/PUBLISHING.md`、`docs/BUILD_PLAN.md` 各自的过期版本号、端点计数与提交/标签快照。

### 数据来源（本轮的每个数字都是量出来的）

- 表与迁移：`information_schema.tables` + `migrations/versions/` → 15 张表、10 个版本、head `0010`。
- 端点：`GET /openapi.json` → 34 paths / 37 operations。
- 页面：`find src/app -name page.tsx` → 14 条（Next 构建输出里的 17 含 `_not-found` 等内部条目）。

## [0.1.8] — 2026-11-04

开源发布前的依赖与元数据审计。

### Added

- `SECURITY.md`：安全边界（仅回环、无鉴权是设计取舍、不执行用户代码、Key 不入库不入日志、知识白名单）、依赖告警的**真实情况**、以及任何人都能自己复核的命令。

### Changed

- `apps/api/pyproject.toml`：描述从「Sprint 0 skeleton」改为真实职责，版本对齐 `0.1.7`。
- `apps/web/package.json`：包名 `web` → `ai-learning-copilot-web`，版本对齐 `0.1.7`，补 `license: MIT`；`package-lock.json` 同步重建。

### Fixed

- **`uv.lock` 因 pyproject 元数据变更而失效**：`uv sync --locked` 会直接报 `lockfile needs to be updated`，CI 必红。已执行 `uv lock`（只更新版本行），`uv lock --check` 与 `uv sync --locked` 恢复通过。

### 依赖审计结论（如实记录）

- `npm audit`：**16 个 moderate，全部在 ESLint 开发链**（`minimatch` 经 `eslint-config-next` 传递引入）。
- **运行时依赖干净**：`next` / `react` / `react-dom` / `tailwindcss` 均无告警；生产依赖只有 3 个。
- `npm audit fix`（非 `--force`）无法消除；`--force` 会升到 `eslint-config-next` 不接受的版本、反而破坏 lint。**选择等上游修复并在 `SECURITY.md` 记录，而不是强推。**

### Verified

- `scripts/ci.ps1` 十个步骤全绿，`npm run lint` 输出已显示新包名 `ai-learning-copilot-web@0.1.7`。
- `npm ci` 在新包名下正常工作；`tsc` / `eslint` / `next build` / 死导出检查全部干净。

## [0.1.7] — 2026-11-04

开源前的代码质量收尾：后端补 lint、前端清死代码、修掉工具链里两处会伤到使用者的坑。

### Added

- **后端 ruff**（`E,F,I,UP,B`；`E501` 与实际代码冲突故关闭，`B008` 是 FastAPI `Depends()` 误报）。进入 dev 组、CI 增加一步、`scripts/ci.ps1` 同步。
- **`apps/web/scripts/dead-exports-check.mjs`**：零依赖的死导出自查脚本，发现即退出码 1。已用它清掉 13 个死导出（含删除后级联暴露的 4 个）。

### Fixed

- **`ci.ps1` 在开发服务运行时必然失败**：`npm ci` 会先删 `node_modules`，而 `next start` 正持有 `node_modules/@next/swc-*.node`，`unlink` 报 EPERM，还会把**正在运行的前端一起弄坏**。脚本现在先检查 3000 / 8000 端口，被占用就退出并说明原因。
- 73 处 ruff 问题：64 处自动修复（`datetime.UTC`、过时 typing 导入、导入顺序、未使用导入），9 处手工修复——其中 8 处是此前把 helper 插在 import 语句中间造成的 `E402`。
- 一处测试用裸 `Exception` 断言，改为 `pydantic.ValidationError`。
- 前端产物：删除 `DisabledButton`、`SoonTag`、`IconArrowRight`、`IconCheck`、`isAssistanceLevel`、`parsePlanPreview`、`readLastResult`、`clearLastResult`、`stateTone`、`reviewResultPath` 及随之孤立的类型与常量。

### Verified

- `ci.ps1` 十个步骤全绿（ruff → uv sync --locked → 迁移 → head 校验 → 130 单元 → 127 集成 → npm ci → tsc → lint → build），并在「服务在跑」时正确拒绝执行。
- `next build` 无任何警告，17/17 页面生成；`tsc` / `eslint` 退出码 0；死导出 377 个中 0 个。
- 干净数据库与开发库上后端两档测试均全绿。

## [0.1.6] — 2026-11-04

工程化收尾：让「本地全绿」与「CI 全绿」成为同一件事。

### Added

- `scripts/ci.ps1`：与 `.github/workflows/ci.yml` **完全相同的 9 个步骤**（后端 `uv sync --locked` / 迁移 / head 校验 / 两档 pytest；前端 `npm ci` / `tsc` / `lint` / `build`），任何一步非 0 退出码都会被列出。推送前本地跑一次即可预知 CI 结果。
- `smoke.ps1` 增加环境泄漏提示：若 shell 里残留 `DATABASE_URL`（会覆盖 `.env`），会打印脱敏后的地址，避免出现「明明库是好的却 alembic 连不上」这种难以定位的失败。

### Changed

- `study_plan.generate_plan()` 改为接收显式 `user_id`（`users.get_user` + 路由解析）。此前它内部解析「唯一那个用户」，导致计划相关用例只能跑在真实用户身上、随真实学习数据漂移。新增 `test_study_plan_isolation.py` 用自建用户证明隔离：别的用户生成计划不会改动种子用户的任何行。

### Fixed

- 计划相关测试的断言改为「规则」而非「数据」：历史分钟按增量断言、练习数断言「不超过上限」而不是「必须达到 2」。
- `skill-card.tsx` 残留的未使用导入（ESLint 会报 warning）。
- `apps/web/package-lock.json` 的版本号停留在 0.1.0，已与 `package.json` 对齐到 0.1.3。
- `CONTRIBUTING.md` 一处被改岔的句子。

### Verified

- 全新克隆中执行 `scripts/ci.ps1`：9 步全部 `ok`，末尾输出 `CI-equivalent checks passed.`
- 干净数据库上：`130 passed`（单元）+ `127 passed`（集成）。

## [0.1.5] — 2026-11-04

以学习者身份完整走一遍首次使用流程（诊断 20 题 → 结果 → 计划 → 练习 → 复习 → 作品）时发现的界面缺陷。

### Fixed

- **结果页自相矛盾**：`LEVEL_NAMES[0]` 是「未评估」，任何 `level=0` 都会渲染成「L0 · 未评估」，于是「已测，未达 L1 门槛」旁边印着「未评估」。新增状态感知的 `levelLabelForState`：`level=0` 且 `assessed_below_threshold` 时显示「L0 · 已测未达标」。
- **结果页与档案口径易混**：未达门槛的域显示 L0，但「当前等级」仍保留此前已建立的等级（`assessment_state='established'` 才参与解析）。已在结果页显式说明「下面的等级是本次诊断的结论，不会降低你此前已建立的等级」。
- **产品界面残留开发阶段标签**：`/onboarding`、`/diagnostic`、`/result`、`/history` 上的「Sprint 1 · 第 N 步」全部改为「学习流程 · 第 N 步」。

### Verified

- 诊断全流程实测：20 题作答 → 提交 → `/result` 六域判定；六域正确率 25% / 0% 时均正确显示「已测未达标」，`L0 · 未评估` 出现次数为 0。
- 后端 `130 passed` / `125 passed`；前端 `tsc` / `lint` / `build` 全 0；三个页面浏览器 Console 无报错。
## [0.1.3] — 2026-11-04

补上「结业作品提交」，但**只做能诚实交付的部分**：本版本是单用户本地应用，没有第二个人能评审，所以评审一律是**本人自评**。

### Added

- `capstone_submissions` 表（迁移 `0009`）：`draft → submitted → reviewed` 单向状态机；提交时把四条达标要求的结果**快照存档**，事后可追溯。
- 6 个端点：创建草稿、列表、详情、改草稿（仅 draft）、提交、自评。
- `/projects` 页新增提交表单（标题 / 简介 / 仓库链接 / 运行说明 / 4 项自检清单）与状态展示。

### Changed

- 版本号收敛到单一来源 `apps/web/src/lib/app-version.ts`，界面不再出现三处不同的版本号；`apps/web/package.json` 同步到 0.1.3。

### Fixed

- **数据库约束的三值逻辑漏洞**（迁移 `0010`）：`ck_capstone_submissions_reviewed_complete` 原本写 `reviewer = 'self'`，当 `reviewer` 为 `NULL` 时整条 CHECK 求值为 `NULL`，PostgreSQL 视为通过——实测可以把「已评审但没有评审人」的行写进库。已改为显式 `reviewer IS NOT NULL AND reviewer = 'self'`。
- 列表排序用例依赖库内既有作品数，混入其它数据时位置断言会漂移；改为只对本用例创建的行断言相对顺序。
- 迁移链断言漏了 `0009 → 0010` 一环（批量改 head 常量时误改），已补 `CAPSTONE_REVISION` 常量与断言。

### Verified

- 真实接口序列：创建草稿 → 提交（快照 `ready=false`、四条要求齐全）→ 重复提交 409 `CAPSTONE_INVALID_STATE` → 未确认自评 400 `SELF_REVIEW_NOT_CONFIRMED` → 非法 verdict 422 → 确认自评 200（`reviewed / pass / self`）。
- 数据库层实测：`UPDATE ... SET reviewer = NULL` 与 `reviewer = 'human'` 均被约束拒绝。
- 默认档 `130 passed`；集成档 `125 passed`；**全新数据库**上 `125 passed`。
## [0.1.2] — 2026-11-04

补上「错题本与间隔复习」——`review_items` 此前恒为 0，周计划里 `kind='review'` 从不生成。新增一张表（迁移 `0008_review_items`），其余表零变化。

### Added

- `review_items` 表：`UNIQUE (user_id, exercise_id)`、`(user_id, next_review_on)` 索引、`status ∈ {pending, done}`；**行永不删除**，`done` 只是状态。
- 间隔调度：答错 → `streak=0`、1 天、明天；答对 → `3 → 7 → 14` 天，连续 3 次通过置 `done`；答对但无复习行时不建行。
- `GET /review/items`、`POST /review/items/{id}/result`、`GET /review/summary` 三个端点；「今天」按 `users.timezone`。
- `/review` 页面：复习概览四指标 + 「今天到期」与「全部待复习」两区块，每行显示连续通过次数、当前间隔、下次复习日期。
- 周计划新增 `kind='review'` 排程，并在导航与计划页显示「复习」徽章与「去复习 →」。

### Changed

- **排课顺序改为「课程 → 复习 → 新练习」**。原顺序（课程 → 练习 → 复习）实测导致 `review_items` 恒为 0：每天 30 分钟课 + 15 分钟练习正好用满 45 分钟额度，复习永远抢不到余量。改后到期复习优先占位，代价是当天可能没有新练习——这是刻意的取舍。
- 已排的复习行在每轮生成里原地重生，避免 `expire` 与下一次生成之间来回抖动。

### Verified

- 真实接口序列：答错 → 2026-11-05 → 答对 → 11-07 → 11-11 → 11-18 且 `done`；再次答错正确重置为明天。
- 真实生成：`review=1`（此前恒 0），11-04 为「30 分钟课 + 15 分钟复习」，原本那天的练习转为 `expired`，四天 `total` 仍全部 = 45。
- 默认档 `130 passed`；集成档 `110 passed` ×2；**全新数据库**上 `110 passed`，临时库用后即删。

### Known limitations

- **逾期复习不进周计划**：候选窗口是 `next_review_on ∈ [今天, 本周日]`，已逾期的错题只在 `/review` 页出现。
- `kind='review'` 的 `target_id` 只由服务层校验（迁移 0007 的触发器只覆盖 lesson/exercise，本轮未改迁移）。

## [0.1.1] — 2026-11-04

把所有「演示数据」占位换成由真实学习记录推导的页面。**没有任何新表、没有新迁移**。

### Added

- `GET /api/v1/progress/overview`：课程进度（含已完成分钟）、本周计划（完成 / 跳过 / 排期与分钟）、练习与证据分布（`static_rule` / `self_report` / `none`）、六域能力等级与均值、最近 7 天活动（缺失日期补 0）。
- `GET /api/v1/capstone/readiness`：四条结业要求（完成 5 节课程 / 通过 ≥6 道练习 / ≥3 个能力域达到 L2 / 完成 ≥5 个计划任务），`ready` 由四条判定全真推导；响应中的 `note` 明确声明作品提交与人工评审流程尚未实现。

### Changed

- `/progress` 重写：四张真实数据卡 + 7 天活动条形，删除全部 `DemoTag` 与「演示数据」文案。
- `/projects` 重写：展示四条要求的 `actual / required / met` 与总体状态，并原样显示后端 `note`；原「三个候选项目」演示列表移除。
- 前端解析遵循「缺失 ≠ 0」：字段缺失渲染「—」，分组缺失显示「后端未返回」，不补零、不估算；分母缺失时不渲染比例条。
- 导航摘要与页脚版本号更新为 v0.1.1 口径。

### Verified

- 端点数字与库内 SQL 逐项对账：`lessons 2 / 45 分钟`、`plan scheduled 6 / done 1 / skipped 1 / 20 / 135 分钟`、`submissions 12 / 去重练习 2 / 通过 1`、`by_evidence 7+5`、`平均等级 1.6 / 6 域`。
- 全新数据库上 `130 passed`（单元档）+ `95 passed`（集成档），临时库跑完已删除，`apps/web/src` 内 `DemoTag` 与「演示数据」命中 **0**。

## [0.1.0] — 2026-11-04

第一个可用版本。零基础学习者可以走完「能力诊断 → 课程学习 → 编程练习 → AI 导师 → 知识检索 → 周计划」这条闭环，全部数据落在本地 PostgreSQL。

数据库迁移：`0001` → `0007`（head `0007_sprint6_plan_exercise_targets`），14 张业务表；26 个 HTTP 端点，文档见 `docs/API.md`。

### Added

- **能力诊断**（Sprint 1B）：20 道固定题库（`GET /diagnostics/paper` 为唯一来源，前端不再内置题库），六域计分，作答明细可回看；**只授予 L0–L2，永不授予 L3/L4**。
- **用户档案**：时区、学习日、每日分钟；`study_days` 有唯一性触发器，`weekly_minutes` 为生成列。
- **课程与进度**（Sprint 2）：5 节 Python 课程（变量 / 条件循环 / 列表字典 / 函数 / 调试），进度单向（`not_started → in_progress → completed`），课程自评只写 `learning_progress`，绝不写 `user_skill_levels`。
- **周计划**（Sprint 2 + Sprint 6）：按学习日与每日预算排课，`scheduled → done|skipped` 终态只读；Sprint 6 起把**练习**一并排入（`kind='exercise'`，目标必须是真实 `exercises.id`，含数据库触发器校验），每日练习上限随能力等级变化。
- **练习与判题**（Sprint 3）：10 道练习（每节课 2 道），代码编辑器零依赖，判题只有两条通道——`static_rule`（静态规则，标「已验证（静态规则）」）与 `self_check`（自检，标「未验证（自检）」）；**服务端从不执行用户代码**，任何判定都不写 `user_skill_levels`。
- **AI 导师**（Sprint 4）：接入 DeepSeek（`POST /ai/tutor`），四档提示依赖（`none/hint/partial_code/full_answer`）；无 Key 时 `503 AI_UNAVAILABLE` 且**不发起任何上游请求**，超时 504、超配额 429；每次尝试都写一行 `ai_interactions` 台账，便于成本与失败追溯；密钥只从环境读取，永不入库、入日志、入响应。
- **知识检索**（Sprint 5）：白名单入库（仅 `docs.python.org` 与仓库内课程，服务端强制域名校验）、关键词打分检索、每条结果带 `fetched_at` 与过期标记；AI 回答带 `citations[]` 引用；入库端点默认关闭。
- **运维与开源就绪**：`scripts/start-dev.ps1`（一键起库 + 迁移 + API + Web）、`scripts/smoke.ps1`（17 项只读自检）、`docs/API.md`、`CONTRIBUTING.md`、`.github/workflows/ci.yml`、`docs/reports/` 历史报告归档。

### Changed

- 预算口径修正：历史终态（done/skipped）分钟**仍计入**当日已分配预算，`total_minutes <= daily_minutes` **只在生成那一刻成立**；事后调小每日额度会超限，界面必须提示而不是宣称恒成立。
- 进度写入改为**数据库层原子条件更新**（等级比较 + `GREATEST`/`COALESCE`），并发请求不再可能把 `completed` 回退成 `in_progress`。
- 课程完成同步**限定当周**（按用户时区的周一），不再误改历史周次或终态行。

### Fixed

- 并发写入导致的学习进度回退（应用层判断 → 数据库条件更新）。
- 完成课程时误标其他周次计划项为 done。
- 中文检索召回为 0：分词只按非字母数字切分，中文整句变成一个词；现改为 **CJK 二元组**，中文提问可正常召回。
- AI 引用重复：同一页面的多个命中块曾显示成多条相同来源；现按 URL 去重。
- 前端把接口地址当页面路由用（练习卡片曾链到 `/api/v1/exercises/{id}`，Next 预取产生 5 条 404）。
- 自检字段无条件发送，导致静态规则判题永远不执行（未勾选时必须不发送 `self_reported_passed`）。
- 干净库迁移回归用例使用固定探针库名，两个进程并发跑必互删；改为 `pid + uuid` 唯一库名。

## Sprint 1 准入审查（2026-11-03）

审查基线 `f06dab4`。本轮不开发业务功能，只做复验、口径修正与安全加固。

### Added

- `docs/DATABASE.md`：新增第 14 张表 `study_plan_items`（周计划任务），含唯一约束 `uq_study_plan_items_dedupe (user_id, dedupe_key)`，用于保证「同一周重复生成不产生重复任务」。
- `docs/DATABASE.md`：`user_skill_levels` 新增证据溯源五字段 `source`、`evidence_strength`、`verification_status`、`evidence_ref`、`evidence_count`，使能力等级可追溯来源。
- `docs/DATABASE.md`：`exercises` 新增 `kind`（`practice` / `transfer`），作为 L4「迁移应用」的判定依据。
- `docs/PRD.md`：六种提交情况唯一取值表、学习时间规则 R1–R6、Sprint 顺序表、新增验收条件 AC-31…AC-35。
- `docs/ROADMAP.md`：新增 §10.1「安全代码执行方案评估」（四方案 × 五维度），并补齐 `AC-S7-07/08/09`。
- `README.md`：新增本地监听约定（三端口仅回环）。
- `REVIEW_REPORT.md`、`TEST_RESULTS.md`、`CHANGELOG.md`：审查交付文档。

### Changed

- `docs/PRD.md`、`docs/ARCHITECTURE.md`、`docs/DATABASE.md`、`docs/ROADMAP.md`：能力等级口径统一为「初步诊断只授予 L1/L2；L3 需同域 ≥3 次不同题目且 `ai_assistance_level='none'` 且 `verification_status='verified'`；L4 需迁移任务且状态一律 `pending_review`」。
- 提示依赖收敛为 3 列可写（`is_passed`、`verification_status`、`ai_assistance_level`）+ 2 个 PostgreSQL 生成列（`used_ai`、`passed_with_ai`）；`has_prompt_dependency` 不再落库，改为 `EXISTS ai_interactions` 查询派生。
- `user_profiles`：`weekly_minutes` 改为生成列，新增 `study_days`、`daily_minutes`；`users.timezone` 明确为「今日/本周」唯一边界。
- Sprint 顺序重排：S1 用户档案与能力诊断 → S2 学习路线与课程 → S3 练习与判题 → S4 AI 导师与提示依赖 → S5 错题本与复习 → S6 项目与进度 → S7 打磨与开源。八个功能需求一条未删。
- 课程掌握度默认值由 L1 改为 **L0（未评估）**；仍允许自评 L0–L4，但必须标注「自评，未经验证」，且永不写入 `user_skill_levels`、不作技能域等级证据。
- `docs/ARCHITECTURE.md`：拓扑图与端口表统一为 `127.0.0.1:3000` / `127.0.0.1:8000` / `127.0.0.1:5432`；新增判题能力边界表与两条硬约束。

### Fixed

- **安全**：`apps/web/package.json` 的 `dev` 与 `start` 脚本增加 `-H 127.0.0.1`。修复前 Next.js 默认绑定 `0.0.0.0:3000` 与 `[::]:3000`，使**无认证**的本地前端暴露到局域网；修复后实测只监听 `127.0.0.1:3000`。
- 修复「用了 AI 却可记为完全独立完成」的数据漏洞：`ai_assistance_level` 与 `used_ai` 之间原本没有约束，现在由生成列表达式在数据库层保证一致。
- 修复 `docs/ARCHITECTURE.md` 中 api 监听 `0.0.0.0:8000` 的错误描述（与 uvicorn 默认值及自身端口表均矛盾）。
- 统一 `study_plan_items` 四个字段为 `NOT NULL`（PRD / ROADMAP 原为可空），否则 R1 求和与 R5 可解释性无法判定。

### Removed

- `submissions.has_prompt_dependency` 列（改为查询派生，避免与 `ai_interactions` 形成两个事实源）。
- 课程掌握度默认 L1 的假设（改为 L0 未评估）。

### 备注

- 本轮未修改任何业务代码（唯一代码改动为启动脚本参数）；未新增依赖；未执行 git 提交或推送；数据库业务表仍为 0 张。

## Sprint 0（2026-11-03）

初始骨架：

- 前端 Next.js 16 App Router + React 19 + TypeScript + Tailwind 4，五个页面（今日 / 学习 / 练习 / 项目 / 进度）、侧边导航、深浅色三态主题、系统状态组件。
- 后端 FastAPI + uv（Python 3.12），`GET /api/v1/health` 与 `GET /api/v1/ready`，请求日志中间件、CORS 白名单、Alembic 空基线迁移。
- 本地基础设施：`infra/docker-compose.yml` 提供 PostgreSQL 17（仅绑定 `127.0.0.1:5432`）。
- 文档五份（PRD / ARCHITECTURE / DATABASE / ROADMAP / DESIGN_SYSTEM）与 README。