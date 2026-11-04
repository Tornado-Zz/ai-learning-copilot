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

## 已知的体验摩擦（未修，记录在案）

1. **草稿提交需要两步**：草稿行只有「编辑草稿」，要提交得先进编辑态再点「提交」。功能正确，但比直接提供「提交」按钮多一次点击。
2. **逾期复习不进周计划**：`next_review_on < 今天` 的错题只出现在 `/review`，不会被重新排进本周（已冻结的口径）。
3. **作品提交与自评都在同一页**，长列表下需要滚动；v0.2 若加导航可拆成独立详情页。