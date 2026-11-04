# SPRINT 2 PATCH 报告

- 上游：`SPRINT2_Independent_Review.md` 第四节（Sprint 2 Patch）
- 范围：P1-01 至 P1-05 + P2-01；P2-02 文档同步；P2-03 记录为后续项
- 未做：新增课程、DeepSeek、用户代码执行、登录、部署、Sprint 3、任何 git 写操作
- 配套：`SPRINT2_PATCH_TEST_RESULTS.md`、`SPRINT2_PATCH_REVIEW.zip`

---

## 逐项结论

| 编号 | 结论 | 关键代码位置 | 测试 / 证据 |
|---|---|---|---|
| **P1-01** 计划页失效按钮 | **PASS** | `apps/web/src/lib/plan-rules.ts:23`（planItemActions）、`apps/web/src/app/plan/plan-view.tsx:157`（守卫）、`:290-313`（动作渲染）、`apps/web/src/components/plan-item.tsx:24,47`（终态只读文案） | `node apps/web/scripts/plan-rules-check.mjs` → **16/16 PASS**；浏览器实见终态行零按钮、scheduled 行仅「标记完成/跳过」、全页无撤销 |
| **P1-02** expired 死锁 | **PASS** | `apps/api/app/services/study_plan.py`（UPSERT 的 `WHERE status IN (scheduled, expired)`；`EXPIRE_STALE_ITEMS` 的 keep 集合 = 本次目标键集） | `test_patch_01_expired_item_is_resurrected_when_its_study_day_returns` **PASSED**（id=151 同键 scheduled→expired→scheduled，行数 A=7/B=10/A'=10） |
| **P1-03** 周中首次生成排过去日期 | **PASS** | `apps/api/app/services/study_plan.py`（candidate_dates = study_days ∩ [today_local, week_end]；today_override 仅测试注入） | `test_patch_03_first_generation_on_tuesday_creates_no_monday_scheduled_row` **PASSED**（对照：today=周一时周一有 scheduled；today=2026-11-03 后 monday_scheduled=0）；`test_patch_04`（周末）同样 PASSED |
| **P1-04** 课程完成与计划项脱节 | **PASS** | `apps/api/app/services/lessons.py`（MARK_PLAN_ITEMS_DONE 同事务）；前端 `lesson-detail-view.tsx`（展示真实 learning_progress 并注明三者不同） | `test_patch_05`（课程完成 → 计划项 done，plan_items_completed=1）+ `test_patch_06`（计划项 done 不会把课程标成完成）双双 PASSED；浏览器文案「计划项被标成 done 不等于课程完成，也不等于能力等级」 |
| **P1-05** 进度可回退 | **PASS** | `apps/api/app/services/lessons.py`（前进守卫在任何 SQL 之前）、`app/core/errors.py:COURSE_PROGRESS_REGRESSION` | `test_patch_07_progress_regression_is_422_with_zero_writes` **PASSED**；真实 HTTP `PUT /lessons/1/progress` 带 status=in_progress → **422 COURSE_PROGRESS_REGRESSION** |
| **P2-01** 历史终态污染预算 | **PASS** | `apps/api/app/services/study_plan.py`（某日额度 = daily_minutes − done+skipped）、`app/schemas/study_plan.py`（三分钟字段 + 顶层两计数）、前端 `plan-view.tsx:238-270,358-399,441-456` | `test_patch_02`（预算 30→60→30 不超支、目标课程不丢）、`test_patch_09`（scheduled 30 + history 30 = 60 ≤ 60）PASSED；真实 GET：scheduled_items 3 / history_items 2，逐日 total ≤ daily |
| **P2-02** 文档与实现口径冲突 | **PASS** | `docs/ROADMAP.md`（AC-S2-02/03/04 改写 + 新增 AC-S2-14..19）、`docs/SPRINT1A_CONTRACT.md`（§6.12-6.14）、`docs/PRD.md`（6 处）、`docs/DATABASE.md`（§4.9 与 §4.14）、`README.md` | AC-S2-03 明确标「未实现，延期至 Sprint 3，不计入已验收」；PRD 中「停留」仅剩延期说明；DATABASE §4.14:721-725 三条硬约束 |
| **P2-03** 个性化程度有限 | **NOT FIXED（按指令记录为后续项）** | — | 本轮不设计推荐规则；建议 Sprint 3 只做低成本差异化 |

## P2-01 的边界（如实记录）

`total_minutes <= daily_minutes` 在**生成时**必然成立。若用户先把任务标记 done、之后又调小 daily_minutes，历史终态行按「终态不可改写」保留，该日 total 可能超过新预算。这是两条冻结规则相交时的取舍，未做静默回退。

## 需要说明的三处过程事实

1. `docs/DATABASE.md §4.14` 由文档 agent 第 3 次运行补齐（我前后两次投递才被处理），三行硬约束落在 `:721-725`。
2. 后端额外修复了 **3 条此前就已失败的既有用例**（真实数据中 11-02 的 done/skipped 落在非学习日、PATCH 用例取到终态行），未修改产品语义。
3. 后端为确定性复现增加了 `generate_plan(today_override=...)`，仅测试注入，生产路径不传。

## 数据保全

全部测试与真实 HTTP 验证前后：`users 1/1`、`user_profiles 1/1`、`skills 6/6`、`diagnostic_attempts 5/5`、`user_skill_levels 30/30`、`lessons 5/5`、`learning_progress 1/1`、`study_plan_items 5/5`。
`study_plan_items` 五行逐行 id / plan_date / planned_minutes / status 与开始时一致（149 done、150 skipped、151/152/153 scheduled）。未执行 DROP / DELETE / TRUNCATE / downgrade。

## 遗留

| # | 遗留 | 严重度 | 说明 |
|---|---|---|---|
| 1 | 本周已 settled 的课程不重排（跨周才回到候选） | 中 | 为避免同一课程出现第二条可执行行；需产品确认 |
| 2 | 先 settled 再调小预算，历史行会让该日 total 超新预算 | 低 | 两条冻结规则相交时的既定取舍 |
| 3 | done/skipped 不可逆 | 中 | 按 P1-01 修复方向：仅移除失效按钮并用文案提示，未开放撤销 API |
| 4 | 计划页不能逐行显示课程真实完成状态（载荷不含） | 低 | 现用行内链接 + 文案区分；如需直出需 API 增字段 |
| 5 | AC-S1-09 与 AC-S1-17 仍延期 | 中 | 未在本轮范围 |