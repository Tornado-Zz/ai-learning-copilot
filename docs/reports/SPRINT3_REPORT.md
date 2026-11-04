# SPRINT 3 交付报告

- 上游：`SPRINT2_PATCH_INDEPENDENT_REVIEW.md`（GO + 三项定点修复）
- 结构：**阶段 A** 修复复审 A/B/C；**阶段 B** 最小编程练习系统
- 数据库：`0004_sprint3_exercises`（head）
- 配套：`SPRINT3_TEST_RESULTS.md`、`SPRINT3_REVIEW.zip`

---

## 阶段 A：三项定点修复

| 项 | 结论 | 代码位置 | 证据 |
|---|---|---|---|
| **A** 完成课程误改旧周计划 | **PASS** | `apps/api/app/services/lessons.py:136`（`AND week_start = :current_week_start`）；周一由 `users.timezone` 经 `study_plan._week_start` 算出（`:309-321`） | `test_a1_completing_a_lesson_settles_only_the_current_weeks_plan_item` **PASSED**：本周行变 done、上周/下周仍 scheduled |
| **B** 并发进度回退 | **PASS** | `lessons.py:99-120`：等级比较写在 **`ON CONFLICT DO UPDATE` 的 `WHERE`**（completed=2>in_progress=1>not_started=0），`progress_pct=GREATEST`、`completed_at=COALESCE`；`RETURNING` 空 → 回读 + 422 | 3 条测试 PASSED；**我另用两条真实并发 HTTP**（跨连接）同时发 in_progress/completed → 终态 `completed/100/completed_at`，`status<>'completed' 且 (completed_at 非空 或 pct=100)` 的行数为 **0** |
| **C** 预算文案与算法矛盾 | **PASS** | 后端 `study_plan.py:382`（`remaining = daily_minutes - history_minutes - used`）；前端 `plan-rules.ts` 的 `BUDGET_SCOPE_NOTE` + `budgetOverLimitNote`；文档 `恒 <= daily` 全库归零 | `plan-rules-check.mjs` **18/18 PASS**（含语义断言，不是关键字）；`grep '不再占用\|恒 <= daily'` = **0** |

阶段 A 闸门通过后才进入阶段 B。

## 阶段 B：最小编程练习系统

| 项 | 结论 | 说明 |
|---|---|---|
| 10 道练习（每课 2 道） | **PASS** | `lesson_id` 全部指向真实存在的 5 节课程（SQL 连接查询无孤儿行）；每题含目标、起始代码、≥2 个可见自检、必含/禁止模式、预计时长、内容版本 |
| 代码编辑器 | **PASS** | 零新增依赖：`textarea` + 等宽字体 + CSS 行号列（`scrollTop` 同步、`wrap=off`）+ Tab 插 2 空格；无 monaco/codemirror |
| 静态规则判题 | **PASS** | `app/services/judging.py` 纯文本，无 `subprocess/eval/exec/importlib`（AST 测试证明）；通过案例 13 项检查全绿 |
| 自检判题 | **PASS** | `self_reported` → 徽章「未验证（自检）」，永不为 `verified`（DB 生成列 + `ck_submissions_strength_never_verified` 兜底） |
| 提交历史 | **PASS** | 该题历史 `attempt_no` 4/3/2/1 倒序；`/submissions/recent` 跨题倒序且两种证据标签并存 |
| 证据分级 | **PASS** | 界面三态徽章：已验证（静态规则）/ 未验证（自检）/ 未提交；详情端点零答案键泄露 |
| 不授 L3/L4 | **PASS** | 判题前后 `user_skill_levels` 均 30 行、`level>=3` 计数 **0**；判题代码路径不写该表 |
| 练习进入周计划 | **NOT DONE（明确延期）** | `study_plan_items.kind` 仍只有 `lesson`；页面明示「练习本轮尚未加入周计划」，不声称闭环 |

## 本轮我在真实浏览器里发现并修复的三个缺陷

这三个都**不会**被 `tsc`/`lint`/`build`/后端单测发现，只有端到端才能暴露：

| # | 缺陷 | 后果 | 处置 |
|---|---|---|---|
| 1 | `difficulty` 后端是 `smallint`，前端用 `readText` 读字符串 | 难度徽标**永远空白** | 前端新增 `readDifficulty` 映射 `1..5 → 入门/基础/中等/进阶/挑战`；复验 `1 → 入门` |
| 2 | 练习卡片 `href` 用了**接口地址** `exercisePath()` | 点练习跳到 `/api/v1/exercises/{id}` → 404，且 Next 预取产生 5 条 404 | 新增 `practicePagePath()` 与 `exercisePath()` 明确分工，两处 Link 改用它；复验 API 预取 **0 条**、页面路由预取 5 条全 200 |
| 3 | 前端**无条件**发送 `self_reported_passed: false` | 后端按「字段存在即自检」分流 → **静态规则从界面永不执行**，用户看不到 checks | 未勾选时不发送该字段；复验不勾选得「已验证（静态规则）」+ 逐项检查，勾选得「未验证（自检）」 |

## 我自己的一次误判（如实记录）

首次验证 `GET /exercises/1` 时返回错误体，我一度怀疑端点有 bug；实际是我启动的 uvicorn 因 8000 端口被旧实例占用而 `bind` 失败（exit 3），我的 curl 打到了**没有该路由的旧服务**。清端口重启后正常。记为过程事实，不计入缺陷。

## 数据保全

| 表 | 状态 |
|---|---|
| users / user_profiles / skills / diagnostic_attempts / user_skill_levels | 1 / 1 / 6 / 5 / **30（level>=3 = 0）** |
| lessons | 5 |
| learning_progress | 2（lesson 1、2 completed；lesson 2 为我并发验收所写） |
| study_plan_items | 5（149 done / 150 skipped / 151-153 scheduled，未改） |
| exercises / submissions | 10 / 12（均为验收产生的真实数据） |

无 `DROP` / `DELETE` / `TRUNCATE` / `downgrade`；`0004` 仅 CREATE/INSERT。

## 遗留

| # | 遗留 | 严重度 | 说明 |
|---|---|---|---|
| 1 | 练习未进入周计划 | 中 | 明确延期；`kind` 仍只有 `lesson` |
| 2 | 静态规则可被「只堆字样」通过 | 中 | 判题固有上限；已在代码注释、判题说明与页面三处声明「静态规则通过 ≠ 代码可运行」 |
| 3 | 判题不回显模式正文，反馈颗粒度受限 | 低 | 防刷答案键的代价；学生只能看到「第 N 项必需写法未出现」 |
| 4 | 提交历史不含 `checks` | 低 | 历史行只渲染时间/方式/结果/徽章；如需展开需后端补字段 |
| 5 | `visible_tests` 存在 `name/expect` 与 `input/expected` 双别名 | 低 | 后端为兼容前端补的别名；建议后续收敛为单一口径 |
| 6 | 移动端窄屏、跨浏览器、纯键盘未验 | 低 | 本机仅 Chromium 且无法设视口 |
| 7 | AC-S1-09 / AC-S1-17 仍延期 | 中 | 未在本轮范围 |

## 下一轮建议

1. 把练习加入周计划（`kind='exercise'`，`target_id` 必须指向真实 `exercises.id`），并补「练习任务不占课程预算」的规则。
2. 收敛 `visible_tests` 字段口径，去掉双别名。
3. 静态规则反馈可给出「哪一类写法缺失」的更细提示，但仍不得回显答案正文。
4. 仍不接 DeepSeek、不执行用户代码、不做登录与部署。