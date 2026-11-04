# SPRINT 2 交付报告

- 上游依据：`Sprint1B_Independent_Review.md`（CONDITIONAL GO）+ 本轮任务书
- 本轮两个阶段：**A** Sprint 1B 问题修复；**B** Sprint 2 课程 / 进度 / 周计划
- 数据库：`0003_sprint2_lessons_and_plan` 已应用（head）
- 配套：`SPRINT2_TEST_RESULTS.md`、`SPRINT2_REVIEW.zip`

---

## 1. 阶段 A：Sprint 1B 三个 P1 的修复结果

| 编号 | 问题 | 处置 | 我的验证 |
|---|---|---|---|
| P1-01 | 幂等未闭环（前端每次新建 token；后端不校验载荷） | 前端 token 与草稿绑定（键 `alc-diagnostic-token-v1`，重试复用、成功/重开才换）；后端同 token 比对版本与规范化答案 | 同 token 同载荷 → 200 且零新行；**同 token 不同答案 → 409 `IDEMPOTENCY_CONFLICT`**；越权批次 404；`paper` 答案键 0 |
| P1-02 | `/learn` 仍是 TypeScript/React 假课程、未做诊断准入 | 重做为「未诊断 → 引导态 / 已诊断 → 六域真实等级」，删除全部假课程与演示百分比，新增真实课程区块 | 浏览器实见「状态只来自能力诊断」「不显示任何完成百分比」 |
| P1-03 | 结果无逐题依据 | 新增 `GET /api/v1/diagnostics/attempts/{id}`（只读已提交批次、答案仅此端点可见、题面从题库现取不落库）+ 前端逐题面板 | 实见「第 1 题 q01 / 你的选择 B / 正确答案 B / 正确」 |

文档同步：`README` 去 Sprint 0 残留；`SPRINT1A_CONTRACT` 新增 §6.8–6.11（paper / history / attempts / token 与 409）并修正 L0 示例；`DATABASE §4.16 C10` 改为「允许」；`ROADMAP` 删除占位 target、统一「课程自评 ≠ 域等级验证」、AC-S1-09 标延期、新增 Sprint 1 验收核对表（完成 16 / 延期 2 / 不适用 0）。

**阶段 A 闸门：通过（GO）。**

## 2. 阶段 B：Sprint 2 交付

### 数据库（迁移 0003）

| 表 | 列数 | 说明 |
|---|---|---|
| `lessons` | 16 | `code` 唯一、`stage`、`estimated_minutes`、`content_version`、`content jsonb`（含 `schema_version`） |
| `learning_progress` | 11 | `UNIQUE(user_id, lesson_id)`、`self_assessment` 上限 2（三层拦截）、`started_at`/`completed_at` + CHECK |
| `study_plan_items` | 12 | `dedupe_key` 唯一、`kind` 三值枚举（生成器只写 `lesson`）、`target_id` 服务层强校验 + DB 触发器双保险、`ck_spi_plan_date_in_week` |

迁移前后既有 5 表行数：`1/1/6/5/30` → `1/1/6/5/30`（**零变化**）。未 DROP / DELETE / 降级。

### 课程（5 节，均 `content_version=1`）

| code | 标题 | 时长 |
|---|---|---|
| `route_a.py.variables` | 变量与数据类型 | 20 |
| `route_a.py.control_flow` | 条件判断与循环 | 25 |
| `route_a.py.list_dict` | 列表与字典 | 30 |
| `route_a.py.functions` | 函数与参数 | 30 |
| `route_a.py.debugging` | 综合小练习与错误排查 | 30 |

每节含：学习目标、讲解、代码示例（含预期输出）、典型错误（错误写法/原因/改法）、自测问题 3 题、预计时长、内容版本。

### API（新增 6 条 + 1 处修复）

`GET /lessons`、`GET /lessons/{id}`、`PUT /lessons/{id}/progress`、`POST /study-plan/generate`、`GET /study-plan`、`PATCH /study-plan/items/{id}`；修复 `attempts[].questions[].type`。

### 前端

`/learn` 课程区块、`/learn/[id]` 详情（自测答案默认折叠、打开不写库、自评仅 L0–L2）、`/` 今日真实任务、`/plan` 真实计划与重新生成 + done/skipped 操作。保留六域等级区与三态组件，无演示数据。

## 3. 本轮发现并修复的问题

| # | 问题 | 严重度 | 发现方式 | 处置 |
|---|---|---|---|---|
| 1 | 后端 attempts 响应缺 `type`，UI 显示「题型未提供」 | 低 | 我用浏览器逐题面板发现 | 后端补 `questions[].type` |
| 2 | `done`/`skipped` 按钮无后端接口（404） | **高（功能缺口）** | 前端主动披露 + 我审阅任务书对照 | 后端新增 `PATCH /study-plan/items/{id}`（终态 409、跳过无失败副作用） |
| 3 | **课程详情页 `INVALID_RESPONSE`**：后端返回平铺结构，前端按契约要求 `{lesson:{...}}` 包装 | **高（阻断）** | 我在浏览器验收时发现 | 前端 owner 已不可达，**由我本人改 1 行** `asRecord(record.lesson) ?? record`，随后 `tsc/lint/build` 全 0 并浏览器复验 |
| 4 | 计划响应缺 `today` 字段，前端需自算今日 | 低 | 前端披露 | 后端补 `today`（按 `users.timezone`） |
| 5 | 档案/学习日变更后，属于上周的 `scheduled` 行会破坏 R2 | 中 | 后端自测发现 | generate 时把不属于本周的 scheduled 置为 `expired`（UPDATE 非 DELETE），不计入预算 |

## 4. 过程事故（如实记录）

| 事件 | 影响 | 处置 |
|---|---|---|
| 阶段 A 后端 agent **以失败终止且无回执** | 无代码损伤：其迁移、端点、测试均已落地 | 我独立复跑 `58 passed`、真实 HTTP 验幂等与详情端点、检查无遗留临时库/文件，确认状态可用；仅缺其自述报告 |
| 阶段 B 前端 agent 在收尾修复时 **不可达** | 课程详情页仍报 INVALID_RESPONSE | 由我改 1 行并自证（构建 + 浏览器），已在第 3 节披露 |
| 我首次幂等测试载荷非法（选项 `Z`、版本 `v9`）得到 422 | 一度误以为 409 未实现 | 改用合法但不同的答案后复测，确认 409 正常 |

## 5. 实际通过 / 未执行 / 失败

**实际通过**：迁移 0003 与数据保全、5 节课内容、课程读取与进度保存、打开不自动完成、自评不污染 `user_skill_levels`、计划五项不变量（只含真实 lesson / 不超支 / 非学习日为空 / 幂等 / done-skipped 不可改写）、时区 409、前端三条命令、浏览器学习流程。

**未执行**：移动端窄屏视觉验收、跨浏览器渲染、纯键盘操作全流程、`alembic downgrade`（主动禁止）、DeepSeek 与用户代码执行（明确禁止）。

**失败**：本轮结束时无已知失败项。

## 6. 遗留问题

| # | 遗留 | 严重度 | 建议 |
|---|---|---|---|
| 1 | `done`/`skipped` **不可逆**（规格要求 409，误点无回退） | 中 | S3 前决定是否加「撤销」或允许 done→scheduled |
| 2 | `time_spent_seconds` 按累计值解释，前端未上报 | 低 | 统一口径后再开放该字段 |
| 3 | `progress_pct` 细粒度增长依赖前端上报 | 低 | 与上一条一并处理 |
| 4 | 5 节课全部 `stage=1` | 计划内 | S3 起补后续阶段 |
| 5 | AC-S1-09（自评 L3/L4 申请入口）仍延期 | 中 | S3 实现 |
| 6 | AC-S1-17（C1–C17 逐条执行记录）仍缺 | 低 | 需要一份约束用例的逐条执行台账 |
| 7 | `daily_minutes=15` 时 20 分钟课程无法排期，进入 `unscheduled` 并给原因 | 设计取舍 | 可接受 |

## 7. 下轮建议（Sprint 3）

1. 决定 `done/skipped` 是否可撤销，并同步契约。
2. 实现练习（`exercises`/`submissions`）与 `static_rule` 判题；注意 static_rule 只产 `assessed`，**不得自动授 L3/L4**。
3. 补 AC-S1-09 的自评申请入口与 AC-S1-17 的约束台账。
4. 课程内容扩展到 stage 2–6，并引入内容版本治理。
5. 仍不接入 DeepSeek、不执行用户代码、不做登录与部署。