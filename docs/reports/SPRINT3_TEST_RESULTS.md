# SPRINT 3 测试结果

> 全部为调度者本轮实际执行；未采信子 agent 自述。执行时间 2026-11-04 00:2x (+08:00)。
> 本文件区分「我在本机执行通过」「只做静态审查」「未执行」三类。

## 1. 命令与退出码（本机执行）

| # | 命令 | 目录 | 退出码 | 结果 |
|---|---|---|---|---|
| 1 | `uv run pytest -q` | apps/api | **0** | `80 passed, 70 deselected in 10.70s` |
| 2 | `uv run pytest -m integration -q`（第 1 遍） | apps/api | **0** | `70 passed, 80 deselected in 12.65s` |
| 3 | `uv run pytest -m integration -q`（第 2 遍） | apps/api | **0** | `70 passed, 80 deselected in 12.47s` |
| 4 | `uv run alembic current` | apps/api | 0 | `0004_sprint3_exercises (head)` |
| 5 | `npx tsc --noEmit` | apps/web | **0** | 无输出 |
| 6 | `npm run lint` | apps/web | **0** | 无错误 |
| 7 | `npm run build` | apps/web | **0** | 路由表含 `○ /practice`、`◐ /practice/[id]` |
| 8 | `node apps/web/scripts/plan-rules-check.mjs` | apps/web | **0** | `18/18 PASS`（按钮可见性 + A3 预算语义 + 页面渲染） |

## 2. 阶段 A 的关键测试（按名字执行，逐条 PASSED）

```
tests/test_sprint3_stage_a_progress.py::test_a1_completing_a_lesson_settles_only_the_current_weeks_plan_item  PASSED
tests/test_sprint3_stage_a_progress.py::test_a2_concurrent_requests_never_regress                                PASSED
tests/test_sprint3_stage_a_progress.py::test_a2_completed_to_in_progress_is_422_with_zero_writes                  PASSED
tests/test_sprint3_stage_a_progress.py::test_a2_repeating_the_same_status_is_idempotent_200                      PASSED
============================== 4 passed in 0.45s ==============================
```

### 我自己的并发复验（跨连接真实 HTTP）

```
并发两条 PUT /api/v1/lessons/2/progress（in_progress 与 completed 同时发出）
  in_progress=200   completed=200
  库内最终状态: lesson 2 | completed | progress_pct=100 | completed_at 非空
  矛盾行（status<>'completed' 且 (completed_at 非空 或 pct=100)）计数: 0
  全部进度行: 1|completed|100 ; 2|completed|100
```

### A3 算法与文案一致性

```
后端 apps/api/app/services/study_plan.py:382   remaining = daily_minutes - history_minutes - used
前端 plan-rules.ts BUDGET_SCOPE_NOTE           历史终态分钟计入当日已分配预算；total<=daily 仅在生成时成立
grep '不再占用|恒 <= daily|恒<=daily'          全库 0 命中
```

## 3. 阶段 B 的 API 实测（真实 HTTP + 真实库）

```
# 静态规则通过
POST /api/v1/exercises/1/submissions  {"code_text": "<完整解答>"}
  201  judging_mode=static_rule  verification_strength=assessed
       evidence_label=已验证（静态规则）  is_passed=true    checks 13 项全通过

# 静态规则失败
POST /api/v1/exercises/1/submissions  {"code_text": "x = 1"}
  201  verification_strength=assessed  is_passed=false  checks 通过 5/13

# 自检（用户申报）
POST /api/v1/exercises/1/submissions  {"code_text": "print(1)", "self_reported_passed": true}
  201  judging_mode=self_check  verification_strength=self_reported
       evidence_label=未验证（自检）  is_passed=true

# 历史与 recent
GET /api/v1/exercises/1/submissions   total=4  attempt_no=[4,3,2,1]
GET /api/v1/submissions/recent        items=4  标签含 {已验证（静态规则）, 未验证（自检）}

# 详情端点不泄露答案键
GET /api/v1/exercises/1   required_patterns=0  forbidden_patterns=0  expected_output=0
                          visible_tests 3 条（含 name/expect 与 input/expected 双别名）

# 能力等级不受判题影响
判题前 user_skill_levels = 30 行 levels={0,2}；判题后 = 30 行 levels={0,2}
```

## 4. 浏览器端到端（生产构建 3000 + 真实后端 8000）

| 页面 | 观察 |
|---|---|
| `/practice` | 按课程分组渲染 10 道练习；显示难度（入门/基础/中等）、预计时长、最近提交状态与**证据徽章**；`/api/v1/exercises/*` 预取请求 **0 条**（修复前为 5 条 404） |
| `/practice/1` | 起始代码预填、可见自检 3 条（注明「系统不代为运行」）、编辑器可输入 |
| 提交（未勾选自检） | 结果卡：判定方式「静态规则对比（未运行代码）」、徽章「**已验证（静态规则）**」、**逐项检查可见** |
| 提交（勾选自检） | 结果卡：判定方式「用户自检申报（未验证）」、徽章「未验证（自检）」 |
| Console | 全流程 **0 条应用报错** |

## 5. 失败与修复记录（如实保留）

| 现象 | 原因 | 处置 |
|---|---|---|
| `/practice` Console 出现 5 条 404，Network 为 `/api/v1/exercises/1..5?_rsc=` | 练习卡片 `href` 用了接口地址构造器 | 前端新增 `practicePagePath()` 并替换两处 Link；复验 API 预取 0 条、页面预取 5 条全 200 |
| 难度徽标空白 | 后端 `difficulty` 为 `smallint`，前端按字符串读 | 前端新增 `readDifficulty` 映射 1..5 → 中文标签；复验 `1 → 入门` |
| 界面提交后永远是「未验证（自检）」且看不到 checks | 前端无条件发送 `self_reported_passed: false`，后端按「字段存在」分流 | 未勾选时不发送该字段；复验不勾选 → `static_rule` + 13 项检查 |
| `GET /exercises/1` 首次返回错误体 | **我自己的操作失误**：8000 端口被旧实例占用，新 uvicorn `bind` 失败（exit 3），curl 打到无该路由的旧服务 | 清端口重启后正常；非产品缺陷 |
| 并发测试的两个 session 在同一连接上互释 SAVEPOINT 报 `PendingRollbackError` | 测试设施问题（默认 `create_savepoint`） | 改为 `rollback_only` + 独立 session；另用真实跨连接 HTTP 独立复验 |

## 6. 数据保全

| 表 | 值 |
|---|---|
| tables（含 alembic_version） | 11 |
| users / user_profiles / skills | 1 / 1 / 6 |
| diagnostic_attempts / user_skill_levels | 5 / 30（`level>=3` = **0**） |
| lessons / learning_progress / study_plan_items | 5 / 2 / 5 |
| **exercises / submissions** | **10 / 12** |

无 `DROP` / `DELETE` / `TRUNCATE` / `downgrade`。`learning_progress` 的第 2 行由我的并发验收写入；12 条 `submissions` 均为验收产生的真实数据。

## 7. 未执行

| 项目 | 原因 |
|---|---|
| 移动端 <768px、跨浏览器、纯键盘全流程 | 本机仅 Chromium 且无法设置视口 |
| `alembic downgrade` | 主动禁止（不提供破坏路径） |
| DeepSeek 调用、执行用户代码 | 本轮明确禁止 |
| 练习加入周计划 | 明确延期（B4 未做） |