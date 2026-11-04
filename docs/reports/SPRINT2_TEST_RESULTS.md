# SPRINT 2 测试结果

> 本文件只记录**实际执行**的命令与结果。所有数字由调度者复跑所得，未采信子 agent 自述。
> 时间：2026-11-03 23:0x (+08:00)；数据库 `0003_sprint2_lessons_and_plan (head)`。

## 1. 环境

| 组件 | 版本 |
|---|---|
| Node.js / npm | v26.13.0 / 11.20.0 |
| uv / Python | 0.13.5 / 3.12.15 |
| Next.js / React / TypeScript | 16.4.4 / 19.3.0 / 5.9.3 |
| Pytest | 9.2.0 |
| PostgreSQL | 17.11（`127.0.0.1:5432`） |

## 2. 命令与退出码

| # | 命令 | 目录 | 退出码 | 结果 |
|---|---|---|---|---|
| 1 | `npx tsc --noEmit` | apps/web | **0** | 无输出 |
| 2 | `npm run lint` | apps/web | **0** | 无错误 |
| 3 | `npm run build` | apps/web | **0** | 路由表含 `/learn` ○ 与 `/learn/[id]` ◐ |
| 4 | `uv run pytest -q` | apps/api | **0** | `58 passed, 41 deselected` |
| 5 | `uv run pytest -m integration -q` | apps/api | **0** | `41 passed, 58 deselected`（第二遍同） |
| 6 | `uv run pytest --collect-only -q` | apps/api | 0 | `58/99 tests collected` |
| 7 | `uv run alembic current` | apps/api | 0 | `0003_sprint2_lessons_and_plan (head)` |
| 8 | `curl /api/v1/lessons` | — | 0 | 200，5 节 |
| 9 | `curl /api/v1/study-plan` | — | 0 | 200，`items_total=5`、`exercise_items=0`、`review_items=0` |

## 3. 阶段 A 回归（修复后复验）

| 场景 | 结果 |
|---|---|
| 新 token 提交 | 201，新批次，行数 +1 attempt / +6 levels |
| 同 token 同载荷 | **200**，同一 `attempt_id`，响应体一致，**零新行** |
| 同 token 不同答案（合法选项） | **409 `IDEMPOTENCY_CONFLICT`**，零新行 |
| 同 token 不支持版本 `r2` | 422（校验阶段拒绝，未进入比对；「受支持的另一个版本」才走 409，由单测覆盖） |
| 越权/不存在批次 | 404 `NOT_FOUND` |
| `paper` 答案键泄漏 | **0** |
| 逐题详情 | 200，20 题，`selected`/`correct`/`is_correct` 可用 |
| `/learn` 未诊断引导 | 代码路径存在；当前库六域均为 L2，实测走「真实等级」分支 |

## 4. 阶段 B 核心断言（真实 HTTP + SQL）

```
plan          : 200 items=5 | lesson=5 exercise=0 review=0
per-day       : 2026-11-02:45  11-04:30  11-06:30  11-07:30  <= daily_minutes=45  -> True
weekdays      : [1,3,5,6] subset of study_days [1,3,5,6]                         -> True
rationale     : 每项均非空                                                          -> True
regen x2      : 200/200 | rows 5 -> 5 -> 5（行数不变，幂等）                          -> True
done 保持     : 重生成后 status=done 的行未被改写                                     -> True
done->skipped : 409 PLAN_ITEM_LOCKED                                                -> True
scheduled->skipped : 200（跳过不写失败记录；库内无 mistakes 表）                      -> True
不存在 id     : 404 NOT_FOUND                                                       -> True
时区未确认    : GET 409 / POST 409 CONFLICT（零写入）                                -> True
```

迁移前后既有 5 表行数：`users 1/1`、`user_profiles 1/1`、`skills 6/6`、`diagnostic_attempts 5/5`、`user_skill_levels 30/30`。

## 5. 浏览器端到端（生产构建 3000 + 真实后端 8000）

| 步骤 | 结果 |
|---|---|
| `/learn` | 显示 5 节课（标题/时长/code），同时保留六域真实等级 |
| `/learn/1` 打开 | 渲染目标、讲解、代码示例（等宽+块内横滚）、典型错误；**打开后 `learning_progress` 仍为 0 行** |
| 自测问题 | 默认折叠（按钮「显示参考答案」），点击后变「收起参考答案」 |
| 标记完成 | 写库成功：`lesson=1 / completed / progress_pct=100`；`user_skill_levels` 仍 30 行、**L3+ = 0** |
| `/plan` | 显示 2026-11-02–08、135 分钟、5 项、每日分组与理由展开 |
| 标记完成计划项 | 库内 `done=1`，页面显示「已完成」；重生成后仍为 done |
| `/` 今日 | 显示「今天没有安排任务」——**正确**：2026-11-03 是周二，不在学习日 `[1,3,5,6]` 内 |
| Console | 全程 0 条应用报错 |

## 6. 失败与修复记录（如实保留）

| 现象 | 原因 | 处置 |
|---|---|---|
| `/learn/1` 显示 `INVALID_RESPONSE` | 后端返回平铺结构，前端按契约要求 `{lesson:{...}}` 包装 | **调度者本人**改 1 行 `asRecord(record.lesson) ?? record`（前端 owner 不可达），随后 tsc/lint/build 全 0 并浏览器复验 |
| 首次幂等测试得 422 而非 409 | 我的载荷用了非法选项 `Z` 与不支持版本 `v9`，在校验阶段被拒 | 改用合法但不同的答案复测，得到 409 |
| 计划项状态点击 404 | 后端缺 `PATCH /study-plan/items/{id}` | 后端补实现（终态 409、跳过无失败副作用） |
| 逐题面板显示「题型未提供」 | attempts 响应缺 `type` | 后端补 `questions[].type` |

## 7. 未执行的检查

| 项目 | 原因 |
|---|---|
| 移动端 <768px / 跨浏览器 / 纯键盘 | 本机仅 Chromium 且无法设置视口 |
| `alembic downgrade` | 主动禁止（不提供破坏路径） |
| DeepSeek 调用 / 用户代码执行 | 本轮明确禁止 |
| 跨时区自然移位 | 当前时刻上海与纽约同属 2026-11-02 一周，已由固定时刻确定性单测覆盖 |