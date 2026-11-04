# Changelog

本项目的所有重要变更记录在此文件。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

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