# SPRINT 2 PATCH 测试结果

> 全部为调度者本轮实际执行；未采信子 agent 自述。执行时间 2026-11-03 23:3x (+08:00)。

## 1. 命令与退出码

| # | 命令 | 目录 | 退出码 | 结果 |
|---|---|---|---|---|
| 1 | `uv run pytest -q` | apps/api | **0** | `58 passed, 50 deselected in 10.70s` |
| 2 | `uv run pytest -m integration -q`（第 1 遍） | apps/api | **0** | `50 passed, 58 deselected in 9.34s` |
| 3 | `uv run pytest -m integration -q`（第 2 遍） | apps/api | **0** | `50 passed, 58 deselected in 9.43s` |
| 4 | `pytest -m integration -v`（三条关键用例） | apps/api | **0** | `3 passed in 0.55s`，逐条 PASSED（见第 2 节） |
| 5 | `node apps/web/scripts/plan-rules-check.mjs` | apps/web | **0** | `16/16 PASS`（按钮可见性 + 预算拆分） |
| 6 | `npx tsc --noEmit` | apps/web | **0** | 无输出 |
| 7 | `npm run lint` | apps/web | **0** | 无错误 |
| 8 | `npm run build` | apps/web | **0** | 构建成功，含静态与 Partial Prerender 路由 |
| 9 | `curl` 计划接口 | — | 0 | 200，见第 4 节 |

## 2. 三个可独立复现点的实测

| 复现点 | 用例 | 结果 |
|---|---|---|
| 周二首次生成是否还排周一 | `test_patch_03_first_generation_on_tuesday_creates_no_monday_scheduled_row` | **PASSED**（`today_override` 对照：周一生成时周一有 scheduled；周二生成后 `monday_scheduled=0`） |
| A→B→A 后 expired 是否死锁 | `test_patch_01_expired_item_is_resurrected_when_its_study_day_returns` | **PASSED**（id=151 同键 scheduled→expired→scheduled，复活不新增行） |
| 进度回退是否被拦且零写入 | `test_patch_07_progress_regression_is_422_with_zero_writes` | **PASSED**（三条回退路径均 422，行数据不变） |

## 3. 真实 HTTP（后端 8000 + 真实数据库）

```
PATCH /api/v1/study-plan/items/149  body={"status":"skipped"}
  -> HTTP 409  {"error":{"code":"PLAN_ITEM_LOCKED","message":"该计划项已是终态…","details":{"field":"status"...}}}

PUT /api/v1/lessons/1/progress  body={"status":"in_progress"}
  -> HTTP 422  {"error":{"code":"COURSE_PROGRESS_REGRESSION","message":"课程进度只允许前进…"}}

GET /api/v1/study-plan
  scheduled_items 3 | history_items 2 | items_total 5
  2026-11-02  sched 0  hist 45  total 45  <= daily 45
  2026-11-04  sched 30 hist 0   total 30  <= daily 45
  2026-11-06  sched 30 hist 0   total 30  <= daily 45
  2026-11-07  sched 30 hist 0   total 30  <= daily 45
```

## 4. 浏览器交互（生产构建 3000 + 真实后端）

| 页面 | 观察 |
|---|---|
| `/plan` | 终态（done/skipped）行**零按钮**，仅文案「已完成（终态只读）；计划完成不等于课程完成或能力等级。」「已跳过（终态只读）；不会顺延到次日，也不能撤销。」；scheduled 行仅「标记完成 / 跳过」；**全页无撤销** |
| `/plan` 预算 | 顶部「本周待执行 0 · 已完成/已跳过 2」；逐日「待执行 0 分钟 · 历史 45 分钟 · 合计 45 分钟 / 每天可用 45 分钟」 |
| `/learn/1`（已完成课程） | 无「开始学习」，仅「更新完成记录」；文案「课程自评不等于能力等级… 本页不提供 L3/L4 选项」「计划项被标成 done 不等于课程完成，也不等于能力等级」 |
| Console | 全程 0 条应用报错 |

## 5. 数据保全（测试与验证前后对比）

| 表 | 前 | 后 |
|---|---|---|
| users | 1 | 1 |
| user_profiles | 1 | 1 |
| skills | 6 | 6 |
| diagnostic_attempts | 5 | 5 |
| user_skill_levels | 30 | 30 |
| lessons | 5 | 5 |
| learning_progress | 1 | 1 |
| study_plan_items | 5 | 5（149 done、150 skipped、151/152/153 scheduled，id/日期/分钟/状态逐行一致） |

未执行 `DROP` / `DELETE` / `TRUNCATE` / `downgrade`；`alembic head` 仍为 `0003_sprint2_lessons_and_plan`。

## 6. 失败与修复记录

| 现象 | 原因 | 处置 |
|---|---|---|
| 本轮之前有 3 条既有集成用例失败 | 真实数据中 11-02 的 done/skipped 落在非学习日分支；PATCH 用例取到了终态行 | 后端修正用例选取与防御分支断言（未改产品语义） |
| 我首次逐条跑三条关键用例时用 `-q -v` 混用未打印 PASSED | 我的命令问题 | 去掉 `-q` 重跑，确认 `3 passed` 且逐条 PASSED |

## 7. 未执行

| 项目 | 原因 |
|---|---|
| 移动端窄屏 / 跨浏览器 / 纯键盘 | 本机仅 Chromium 且无法设置视口 |
| `alembic downgrade` | 主动禁止 |
| DeepSeek、用户代码执行、新增课程 | 本轮明确禁止 |
| 真实跨周边界的自然触发 | 已用 `today_override` 确定性覆盖，未等到自然跨周 |