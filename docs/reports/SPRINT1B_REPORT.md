# SPRINT 1B 交付报告

- 本轮目标：实现真实可运行的用户学习档案、能力诊断、六维能力画像与学习路线预览
- 执行依据：`docs/SPRINT1A_CONTRACT.md` 与 PRD / DATABASE / ARCHITECTURE / ROADMAP（Sprint 1A 冻结口径）
- 数据库：`0002_sprint1a_identity_diagnostics` 已执行，当前 head
- 配套测试记录：`SPRINT1B_TEST_RESULTS.md`

---

## 1. 交付概览

| 项 | 数量 |
|---|---|
| 新增文件 | **45**（后端 25 / 前端 20） |
| 修改文件 | 9（后端 3 / 前端 6） |
| 迁移脚本 | 1 个，199 行 |
| 新增代码行数 | 后端约 3159 行（含测试）、前端约 3301 行 |
| 后端测试 | 64 条（常规档 47 / 集成档 17） |
| 新增依赖 | **0** |

## 2. 数据库迁移结果

`alembic upgrade head` → `0002_sprint1a_identity_diagnostics (head)`。

| 表 | 内容 |
|---|---|
| `users` | 1 行种子（学习者 / Asia/Shanghai / `timezone_source=default`） |
| `user_profiles` | 1 行种子（`{1,3,5}` / 60 分钟 / `weekly_minutes` 生成列 180） |
| `skills` | **6 行**：`route_a.a1` Python 基础、`a2` 编程实践、`a3` API、`a4` LLM、`a5` RAG 与 Agent 基础、`a6` 简单 AI 项目 |
| `diagnostic_attempts` | 空表；含 `attempt_token` 唯一约束、JSONB `answers` / `domain_scores`、题集与规则版本 |
| `user_skill_levels` | 空表；`evidence_kind` / `verification_method` / 生成列 `evidence_strength` / `assessment_state` 四态 |

约束与机制：`study_days` 三条 CHECK + 去重触发器 `trg_user_profiles_study_days_unique`；`weekly_minutes` 生成列；`ck_usk_*` 交叉约束；迁移**无 DROP / DELETE / TRUNCATE**，`downgrade()` 主动抛错（不提供破坏路径）。

一处必要的基础设施调整：本迁移 revision 名 34 字符，超出 alembic 默认 `alembic_version.version_num varchar(32)`，首次 upgrade 报 `value too long`（事务化 DDL 整体回滚，库仍停在 0001）。已在迁移首条语句把该列扩为 `varchar(64)`（只动 alembic 自身账本，非业务表）后成功，契约要求的 revision 名保持不变。

## 3. 后端实现

| # | 能力 | 端点 |
|---|---|---|
| 1 | 档案读取 | `GET /api/v1/users/me`（user + profile + 六域快照） |
| 2 | 档案保存 | `PUT /api/v1/users/me/profile`（study_days / daily_minutes / timezone + `timezone_confirmed`，非法 422 统一体） |
| 3 | 技能域清单 | `GET /api/v1/skills` |
| 4 | 版本化题面 | `GET /api/v1/diagnostics/paper?version=v1`（**不含答案键**） |
| 5 | 诊断提交 | `POST /api/v1/diagnostics`（单事务 1 attempt + 6 levels，`evidence_ref='diag:<id>'`） |
| 6 | 历史批次 | `GET /api/v1/diagnostics/history` |
| 7 | 路线预览 | `GET /api/v1/study-plan/preview`（内存计算 `persisted=false`；时区未确认 409） |

评分：确定性、版本化（`question_set_version=v1` / `rule_version=r1`），20 题 = 12 单选 + 5 代码阅读 + 3 改错，六域 4/4/3/3/3/3；阈值 ≥85%→L2、≥60%→L1、<60%→L0 + `assessed_below_threshold`。**永不产生 L3/L4**。

当前等级：逐字实现契约 §3.3 的 `tier 3~0 + DISTINCT ON + 回退`，弱证据不覆盖强证据。

`health` / `ready` 行为与字段一字未改。

## 4. 前端实现

| 路由 | 内容 |
|---|---|
| `/onboarding` | 学习日七选多（1–7、不重复）、每天 15–480 分钟、时区下拉 + **独立确认勾选**，内联校验 |
| `/diagnostic` | 从后端 `paper` 拉题面；逐题作答、进度、上一题、跳到首题、未答完禁止提交；**localStorage 草稿 `alc-diagnostic-draft-v1`**，刷新恢复；题面版本变化即丢稿并提示 |
| `/result` | 六维卡片：level、assessment_state、correct/total/rate、**判定依据一句话**；区分未评估 / 已测未达阈值 / 已建立等级 |
| `/plan` | 阶段级建议 + 「预览不落库」+ `persisted:false`；链接只指向已实现路由 |
| `/history` | 批次列表（时间、题集版本、规则版本、六域摘要），点击展开明细 |

导航新增「学习流程」分组；系统状态组件与深浅色三态主题保留；加载/错误/空三态统一由 `components/states.tsx` 复用；首屏不读浏览器存储（诊断页骨架 + `useSyncExternalStore`），无水合警告。

## 5. 实际测试结果（摘要，明细见 TEST_RESULTS）

| 类别 | 结果 |
|---|---|
| 前端 tsc / lint / build | **0 / 0 / 0** |
| 后端常规档 | **47 passed**，17 deselected |
| 后端集成档 | **17 passed**，连跑 3 遍全绿 |
| 测试前后数据库 | `3/18/1/{1,3,5,6}45` → 完全不变 |
| 浏览器端到端 | 档案保存 → 拉题面 → 20 题 → 草稿恢复 → 提交 → 六维结果 → 预览 → 历史，Console 0 条应用报错 |

## 6. 发现与修复的问题

| # | 问题 | 严重度 | 发现方式 | 处置 |
|---|---|---|---|---|
| 1 | **前后端各有一份 20 题题库**，题干与答案键可能不一致，用户答题、后端按另一套判分 | **高（静默算错）** | 后端报告主动披露 + 前端承认用契约桩联调 | 新增 `GET /diagnostics/paper` 作为唯一来源（不含答案键），前端删除本地题库改为拉取，失败只显示错误不降级 |
| 2 | **集成测试不可重复执行**：依赖「空库 + 默认档案 + 单例用户」，真实使用后 9 条失败 | **高（回归防线失效）** | 我跑完端到端后复跑测试发现 `9 failed` | 测试自建独立用户、断言作用域化、档案用例「基线→写入→断言→复原」；我三次连跑验证 + 前后快照一致 |
| 3 | 历史页文案称「重复提交同一份答案会产生新批次」，与幂等实现相反 | 中（用户可见错误） | 我读页面文案发现 | 改为「同一 attempt_token 的重试不重复产生批次；重新诊断会新增批次」 |
| 4 | 界面标识仍写「Sprint 0 · 预览版」 | 低 | 截图发现 | 统一改为 Sprint 1B（`grep` 命中 0） |
| 5 | alembic revision 名超长导致首次迁移失败 | 中 | 后端首次 upgrade 报错 | 迁移内扩宽 `alembic_version.version_num` 至 64 |
| 6 | `attempt_token` 幂等需求与冻结契约「每次提交新增批次」冲突 | 中 | 派工前预判 | 纯增量加列 + 唯一约束；语义切分为「重试幂等 / 新 token 追加」，已在报告中标记为契约外增量 |

## 7. 遗留问题

| # | 遗留 | 严重度 | 影响 | 建议 |
|---|---|---|---|---|
| 1 | 契约 §6.1 示例把 L0 域写成 `evidence_kind='diagnostic'`，与 §3.3 SQL / DATABASE §4.4 的 `NULL` 回退冲突；实现按 SQL（返回 `null`） | 中 | 阅读者误解 | 下一次文档修订修正示例 |
| 2 | `DATABASE §4.16 C10` 表述错误（称 level=0 + static_rule 应被拒，实际约束与诊断流程允许） | 低 | 文档自相矛盾 | 文档修订时改正 |
| 3 | 单用户三端点（`users/me`、`profile`、`preview`）无法指定 `user_id`，测试只能用「基线 + 复原 + 事务回滚」保证可重复 | 低 | 未来多用户需改契约 | 引入登录时再统一 |
| 4 | `attempt_token`、`/diagnostics/paper`、`/diagnostics/history` 属契约外增量，尚未回写 `SPRINT1A_CONTRACT.md` | 中 | 契约与实现有偏差 | 下轮把三者补进契约 §6 |
| 5 | 移动端 <768px、纯键盘操作、跨浏览器渲染未做视觉/交互验收 | 低 | 体验 | 有窄屏环境时补 |
| 6 | 题面与答案键只在后端一处，前端无离线答题能力 | 设计取舍 | 后端不可用则无法诊断 | 可接受；如需离线需本地缓存题面 |
| 7 | `learning_progress` 与课程进度仍属 S2 | 计划内 | 无课程进度 | S2 实现 |

无「高」级别遗留问题。

## 8. 下轮开发建议（Sprint 2）

1. **先补契约**：把 `attempt_token`、`/diagnostics/paper`、`/diagnostics/history` 三个已实现但契约外的接口回写进 `SPRINT1A_CONTRACT.md`，避免后续实现者按旧契约开发。
2. **S2 主线**：`study_plan_items` 建表 + R1–R6 时间规则 + 最小课程（3–5 节）+ 规则化周计划生成（不调用 AI）。落地前先决定「同层是否允许降级」。
3. **版本治理**：题集已版本化（v1/r1），S2 引入课程后应同样给课程内容版本号，便于追溯「等级不可比」。
4. **可观测性**：`request_id` 已贯穿后端响应与前端提示，S2 增加慢请求日志与 p95 统计。
5. **不建议**在 S2 做：登录、DeepSeek 调用、代码执行沙箱——均属后续 Sprint。

## 9. 本轮明确未做

未接入 DeepSeek；未执行用户代码；未实现 AI 导师；未创建 `study_plan_items`；未引入登录注册；未新增依赖；未推送 GitHub；未部署；未跳过任何失败测试。