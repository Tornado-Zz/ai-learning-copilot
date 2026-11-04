# 学习者路径验收清单（QA Checklist）

> 用途：每次发版前按此清单在浏览器里走一遍**真实用户路径**，而不是只看接口返回 200。
> 最近一次完整执行：2026-11-04（v0.1.5），全部通过。每一步都记录了当时的实际观察结果。

## 0. 前置

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\start-dev.ps1
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\smoke.ps1   # 17 项 PASS
```

打开 `http://127.0.0.1:3000`，浏览器 Console 全程应无 error。

## 1. 建档 `/onboarding`

| 检查点 | 期望 |
| --- | --- |
| 页头步骤 | 「学习流程 · 第 1 步」（不是内部 Sprint 编号） |
| 保存档案 | 200 后跳转，刷新后值仍在 |

## 2. 诊断 `/diagnostic` → `/result`

| 检查点 | 期望 |
| --- | --- |
| 20 题作答 | 每答一题，题号导航从「未作答」变「已作答」 |
| 中途刷新 | 草稿自动保存，回来仍在同一题、已答项保留 |
| 提交 | 跳 `/result`，六域各给出等级 + 评估状态 + 正确率 |
| 未达门槛的域 | 显示「L0 · **已测未达标**」+「已测，未达 L1 门槛」，**不得**出现「L0 · 未评估」 |
| 口径说明 | 页面明写「本次诊断结论，不会降低此前已建立的等级」 |

> 实测：正确率 25% / 0% 的域全部正确显示「已测未达标」；`L0 · 未评估` 出现 0 次。

## 3. 周计划 `/plan`

| 检查点 | 期望 |
| --- | --- |
| 每项 | kind 徽章（课程/练习/复习）+ 标题可点 + 分钟 + rationale |
| 预算 | 每日 `total_minutes ≤ daily_minutes`，页头显示三分栏 |
| 重新生成 | 二次点击后行数不增加（幂等），done/skipped 不被改写 |

## 4. 课程 `/learn` → `/learn/{id}`

| 检查点 | 期望 |
| --- | --- |
| 打开课程 | **不写** `learning_progress`（只是浏览不算进度） |
| 开始学习 | 写 `in_progress`，计划项**保持** `scheduled` |
| 标记完成 | 写 `completed` + `progress_pct=100` + `completed_at`，**同事务**把该课本周计划项置 `done` |
| 幂等 | 重复点击不倒退、不重复写 |

> 实测：lesson 3 从 none → in_progress → completed，计划项同步变 done，界面说明「计划项 done ≠ 课程完成 ≠ 能力等级」。

## 5. 练习 `/practice` → `/practice/{id}`

| 检查点 | 期望 |
| --- | --- |
| 不勾自检提交 | 走 `static_rule`，徽章「已验证（静态规则）」，展示逐项 checks |
| 勾选自检提交 | 走 `self_check`，徽章「未验证（自检）」 |
| 答错 | 自动创建 `review_items` 行，`next_review_on` = 明天 |
| 历史 | 该题历史倒序，`attempt_no` 递增 |

## 6. 错题本 `/review`

| 检查点 | 期望 |
| --- | --- |
| 概览 | 待复习 / 今日到期 / 已完成 / 下次到期 四项 |
| 到期列表 | 只含 `next_review_on <= 今天` 的行；今天的条目在此出现 |
| 行内容 | 练习题名（可点）+ 连续通过次数 + 当前间隔 + 下次复习日期 |

## 7. 结业作品 `/projects`

| 检查点 | 期望 |
| --- | --- |
| 达标判定 | 四条要求显示 actual/required/met，`note` 原样展示 |
| 保存草稿 | 201/200 后行状态 `draft`，自检项按勾选保存 |
| 提交 | 先 PATCH 再 `POST /submit`，状态 `submitted` 且 `readiness_snapshot` 非空 |
| 自评未勾确认 | **不发起请求**，状态保持 `submitted` |
| 自评勾确认 | `POST /review` 200，状态 `reviewed`、`verdict` 有值、`reviewer='self'` |

> 实测：未勾确认时无任何 POST，库内仍是 `submitted`；勾选后 `reviewed / pass / self`。

## 8. 数据一致性抽查（任选其一）

```sql
-- 课程完成与计划项同步
select l.id, p.status, s.status from lessons l
  left join learning_progress p on p.lesson_id = l.id
  left join study_plan_items s on s.kind='lesson' and s.target_id = l.id;

-- 复习项与提交结果一致
select exercise_id, streak, interval_days, next_review_on, status from review_items;

-- 已自评作品必须带 reviewer='self'
select id, status, verdict, reviewer, reviewed_at from capstone_submissions;
```

## 9. 空数据库上的新用户路径（v0.1.7 实测）

把 API 指向一个**全新迁移的数据库**（`tz_source=default`、零进度），按新用户视角走一遍。
这一步不能省：种子用户的学习历史会掩盖「第一次使用」才会暴露的问题。

| 阶段 | 期望 | 实测（2026-11-04） |
| --- | --- | --- |
| 首次打开 `/` | 明确提示「需要先确认时区」+ 去档案页入口，不展示任何按周/按天的推导 | 一致；Console 0 报错 |
| 后端闸门 | `/study-plan`、`/study-plan/preview` 返回 409 `CONFLICT`（`reason=timezone_not_confirmed`），其余端点 200 | 一致 |
| 建档 | 不勾「我确认我的时区是…」时拒绝保存并说明原因；勾选后 `users.timezone_source` 变 `user_confirmed` | 一致 |
| 诊断（全部答对） | 六域各 100% → **一律 L2**（≥85% 授 L2，且诊断永不授 L3/L4），状态 `established` | 6 × `L2 · 能跟做 · 已建立等级` |
| 诊断（多数答错） | 未达 60% 的域显示「L0 · 已测未达标」，且**不降低**此前已建立的等级 | 见第 2 节 |
| 首次生成计划 | 当日总额度内排课；L2 时 rationale 写「每日练习上限 2」；过去的日期不补排 | 11-02 为 0 项；11-04 为 20+25+15=60 |
| 完成一节课 | `learning_progress=completed/100`，本周对应计划项**同事务**变 `done` | 一致 |
| 结业要求联动 | `lessons_completed` 与 `plan_items_done` 立即反映，`domains_at_l2=6` 达标 | 1/5、1/5、6/3 met |

复现方式：

```powershell
docker exec ai-learning-copilot-postgres psql -U copilot -d postgres -c 'CREATE DATABASE copilot_fresh'
# 用 DATABASE_URL 指向 copilot_fresh 起 API（uvicorn 读环境变量）
# 走完路径后：DROP DATABASE copilot_fresh WITH (FORCE)
```

> 注意：用完务必删掉临时库，并且**不要在持久 shell 里留下 `DATABASE_URL`**（`smoke.ps1` 会提示）。

## 已知的体验摩擦（未修，记录在案）

1. **草稿提交需要两步**：草稿行只有「编辑草稿」，要提交得先进编辑态再点「提交」。功能正确，但比直接提供「提交」按钮多一次点击。
2. **逾期复习不进周计划**：`next_review_on < 今天` 的错题只出现在 `/review`，不会被重新排进本周（已冻结的口径）。
3. **作品提交与自评都在同一页**，长列表下需要滚动；v0.2 若加导航可拆成独立详情页。