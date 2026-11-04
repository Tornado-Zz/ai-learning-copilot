# API 参考（v0.1.0）

本文档描述 **v0.1.0 实际注册的 26 个端点**，与实际运行的 `GET /openapi.json`（26 个端点、70 个 schema）逐条核对过。
契约来源：[SPRINT1A_CONTRACT.md](SPRINT1A_CONTRACT.md) §6；实现来源：`apps/api/app/api/v1/routes/`。

- 基地址：`http://127.0.0.1:8000`
- 统一前缀：`/api/v1`（由 `API_V1_PREFIX` 决定，改它就会改所有路径）
- 交互式文档：服务启动后打开 <http://127.0.0.1:8000/docs>（Swagger UI）；机器可读的 `/openapi.json` 同源可取
- 内容类型：请求与响应均为 `application/json`（无文件上传端点）

---

## 1. 读前须知（v0.1.0 的真实边界）

1. **单用户本地 MVP，没有任何鉴权**。没有登录、没有 token、没有多租户：每个端点都作用于数据库里的**同一个种子用户**，`GET /users/me` 返回的就是它。数据库里一个用户都没有时，依赖用户的端点返回 404 `NOT_FOUND`（详情里带初始化提示）。
   **这是当前版本明确的设计取舍，不是遗漏**：v0.1.0 的目标是单人本地学习闭环，加鉴权会让「一条 `docker compose up` 就能跑通」这个前提失效。因此：**只监听 127.0.0.1，不要部署到公网，也不要绑定 0.0.0.0**。
2. **不执行用户代码**。练习判题只做静态规则匹配与自报输出比对（`POST /exercises/{id}/submissions` 不会运行任何提交的代码）。
3. **分页只有 `limit`，没有游标分页**（唯一例外是 `GET /diagnostics/history` 的 `cursor`）。`limit` 超出范围时返回 422 `VALIDATION_ERROR`，不会静默截断，也不会给出下一页指针。
4. **两个端点需要额外环境配置**，否则按设计拒绝服务（详见第 5 节）：`/ai/*` 需要 `DEEPSEEK_API_KEY`；`POST /knowledge/ingest` 需要 `KNOWLEDGE_INGEST_ENABLED=true`。

---

## 2. 统一错误体与 `request_id`

除 `GET /health` 与 `GET /ready` 外，**所有端点的错误响应使用同一个信封**（契约 §6.6）：

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "请求参数不合法",
    "details": {"field": "limit", "reason": "out_of_range", "min": 1, "max": 100, "value": 0}
  },
  "request_id": "0f3c1a2b9d8e"
}
```

- `error.code`：机器可读的错误码，见下表；`error.message`：面向用户的中文提示，**不含堆栈、不含内部路径**；`error.details`：结构化补充，恒为对象（无补充时为 `{}`）。
- `request_id`：**固定在顶层出现一次**（`error` 内不会重复），12 位小写十六进制，逐请求生成；同时作为 `X-Request-ID` 响应头返回，也写进后端日志行（`method=... status_code=... duration_ms=... request_id=...`）。排查问题时把 `request_id` 交给维护者即可对齐日志。**请求里自己带 `X-Request-ID` 不会被采信**——id 一律由服务端生成。
- `GET /health` 与 `GET /ready` 保留各自的响应体（就绪失败返回 503 + `{"status":"not_ready",...}`），不走上面的信封。

### 2.1 已出现的错误码

| `error.code` | HTTP | 出现位置 | 含义 |
| --- | --- | --- | --- |
| `VALIDATION_ERROR` | 422 | 所有端点 | 参数不合法（含 Pydantic 校验失败、`limit` 越界、业务校验如 `self_assessment > 2`） |
| `NOT_FOUND` | 404 | 所有带 id 的端点 | 资源不存在或未发布（**不泄露他人资源是否存在**） |
| `CONFLICT` | 409 | 通用 | 通用冲突 |
| `IDEMPOTENCY_CONFLICT` | 409 | `POST /diagnostics` | 同一个 `attempt_token` 被用于不同内容 |
| `PLAN_ITEM_LOCKED` | 409 | `PATCH /study-plan/items/{id}` | 计划项已是终态（`done`/`skipped`/`expired`），不允许再改写；**不提供撤销** |
| `COURSE_PROGRESS_REGRESSION` | 422 | `PUT /lessons/{id}/progress` | 进度回退（如 `completed → in_progress`），**零写入** |
| `DB_UNAVAILABLE` | 503 | 所有访问数据库的端点 | 数据库不可达，服务本身不崩溃 |
| `INTERNAL_ERROR` | 500 | 所有端点 | 未预期异常 |
| `AI_UNAVAILABLE` | 503 | `POST /ai/tutor` | 未配置 `DEEPSEEK_API_KEY`，**未发起任何上游请求** |
| `AI_TIMEOUT` | 504 | `POST /ai/tutor` | 上游超过 `AI_TIMEOUT_SECONDS`，已落库 `status='timeout'` |
| `AI_QUOTA_EXCEEDED` | 429 | `POST /ai/tutor` | 当日累计 token 已达 `AI_DAILY_TOKEN_LIMIT`，**未发起任何上游请求** |
| `AI_UPSTREAM_ERROR` | 502 | `POST /ai/tutor` | 上游可达但没有给出可用答案，已落库 `status='error'` |
| `INGEST_DISABLED` | 403 | `POST /knowledge/ingest` | `KNOWLEDGE_INGEST_ENABLED` 未开启，**未做任何数据库或网络操作** |

> 另外两个名字常被误当成顶层错误码，实际不是：
> - `SERVICE_UNAVAILABLE` 只是 503 的 HTTP 状态名（`GET /ready` 用它表达「就绪失败」），**不会出现在 `error.code` 里**；数据库类 503 的 `error.code` 一律是 `DB_UNAVAILABLE`。
> - `BLOCKED_HOST` / `INGEST_ERROR` 是 `POST /knowledge/ingest` **200 响应内逐条来源**的 `error_code`（某个 URL 被白名单拒绝或抓取失败），不是整个请求的错误码。

---

## 3. 端点总览（26 条）

| # | 方法 | 路径 | 说明 |
| --- | --- | --- | --- |
| 1 | GET | `/api/v1/health` | 存活探针，恒 200 |
| 2 | GET | `/api/v1/ready` | 就绪探针，数据库可用 200 / 不可用 503 |
| 3 | GET | `/api/v1/users/me` | 当前用户 + 学习档案 + 六域等级快照 |
| 4 | PUT | `/api/v1/users/me/profile` | 更新学习档案 |
| 5 | GET | `/api/v1/skills` | 六个技能域（只有 domain 级） |
| 6 | GET | `/api/v1/diagnostics/paper` | 20 题题面（不含答案键） |
| 7 | POST | `/api/v1/diagnostics` | 提交诊断，写批次 + 六域证据 |
| 8 | GET | `/api/v1/diagnostics/history` | 诊断批次历史（游标分页） |
| 9 | GET | `/api/v1/diagnostics/attempts/{attempt_id}` | 批次逐题明细（唯一返回答案键的接口） |
| 10 | GET | `/api/v1/study-plan/preview` | 本周计划预览（内存计算，不落库） |
| 11 | GET | `/api/v1/study-plan` | 本周已落库计划 |
| 12 | POST | `/api/v1/study-plan/generate` | 生成 / 刷新本周计划并落库 |
| 13 | PATCH | `/api/v1/study-plan/items/{item_id}` | 计划项标记 `done` / `skipped` |
| 14 | GET | `/api/v1/lessons` | 课程列表（含当前用户进度） |
| 15 | GET | `/api/v1/lessons/{lesson_id}` | 课程详情（正文五块） |
| 16 | PUT | `/api/v1/lessons/{lesson_id}/progress` | 写课程进度（只进不退） |
| 17 | GET | `/api/v1/exercises` | 练习列表（可按课程过滤） |
| 18 | GET | `/api/v1/exercises/{exercise_id}` | 练习详情（不含答案键） |
| 19 | POST | `/api/v1/exercises/{exercise_id}/submissions` | 提交练习并判题 |
| 20 | GET | `/api/v1/exercises/{exercise_id}/submissions` | 该题提交历史 |
| 21 | GET | `/api/v1/submissions/recent` | 跨题最近提交 |
| 22 | POST | `/api/v1/ai/tutor` | AI 导师问答（需 `DEEPSEEK_API_KEY`） |
| 23 | GET | `/api/v1/ai/interactions` | AI 互动历史（只有问题预览与用量） |
| 24 | GET | `/api/v1/knowledge/search` | 知识库关键词检索 |
| 25 | GET | `/api/v1/knowledge/sources` | 知识来源清单与新鲜度 |
| 26 | POST | `/api/v1/knowledge/ingest` | 知识入库（默认关闭） |

---

## 4. 逐端点说明

> 记号：成功列给状态码与**关键响应字段**（不是全部字段，完整 schema 见 `/docs`）；错误列只列该端点特异的状态码，所有端点都可能返回 422 `VALIDATION_ERROR`、503 `DB_UNAVAILABLE`、500 `INTERNAL_ERROR`（健康检查除外）。

### 4.1 健康与就绪

**1. `GET /health`** — 无参数。
成功 200：`status`(= `"ok"`)、`service`、`version`、`environment`(= `APP_ENV`)、`timestamp`、`ai_configured`（`DEEPSEEK_API_KEY` 非空才为 true）。**不查数据库**，恒 200。

**2. `GET /ready`** — 无参数。
成功 200：`status`(= `"ready"`)、`checks`。
失败 **503**：`{"status": "not_ready", "checks": {...}}`——**不走统一错误信封**，服务不崩溃。

### 4.2 学习档案（users / skills）

**3. `GET /users/me`** — 无参数。
成功 200：`user`、`profile`（`study_days` / `daily_minutes` / `timezone` / `timezone_confirmed`）、`skills`（六域快照；未建立等级的行 `level=0`、`evidence_kind=null`）。
错误：404 `NOT_FOUND`（数据库中没有任何用户）。

**4. `PUT /users/me/profile`** — 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `study_days` | `int[]` | 可学习的星期（1–7） |
| `daily_minutes` | `int` | 每日可用分钟数 |
| `timezone` | `string` | IANA 时区名 |
| `timezone_confirmed` | `bool` | 默认 `false`；`true` 时写 `users.timezone_source='user_confirmed'`，之后不会退回 `default` |

成功 200：同 `GET /users/me` 的结构。错误：422 `VALIDATION_ERROR`（字段缺失或越界）；404 `NOT_FOUND`。

**5. `GET /skills`** — 无参数。
成功 200：`skills[]`（只返回 `level='domain'` 的 6 个域）。

### 4.3 能力诊断（diagnostics）

**6. `GET /diagnostics/paper`** — 查询参数 `version`（默认 `v1`，当前只支持 v1）。
成功 200：`question_set_version`、`rule_version`、`total`(=20)、`questions[]`。**响应中不含任何答案键**（`answer` 命中数为 0）。

**7. `POST /diagnostics`** — 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `attempt_token` | `string \| null` | ≤64 字符。同一次诊断的网络重试复用同一 token（幂等）；省略则每次追加新批次 |
| `question_set_version` | `string` | 必须与题面返回的一致 |
| `rule_version` | `string` | 必须与题面返回的一致 |
| `answers` | `object` | `{题目id: {"choice": "A"}}`，20 题全答 |

成功 **201**：`attempt_id`、`rule_version`、`domains[]`（六域得分）。
成功 **200**（回放）：同一个 `attempt_token` + 完全相同的版本与答案 → 返回原批次，不新建行。
错误 **409 `IDEMPOTENCY_CONFLICT`**：同一 token 但版本或答案不同，`details` 里带原 `attempt_id` 与冲突字段；既不复用也不新建。**422 `VALIDATION_ERROR`**：题号越界、缺题、choice 非法。

**8. `GET /diagnostics/history`** — 查询参数 `limit`（默认 20，1–100）、`cursor`（上一页最后一条的 attempt id，正整数）。
成功 200：`items[]`、`next_cursor`、`has_more`。这是**唯一**支持游标分页的端点。错误：422 `VALIDATION_ERROR`（`limit` 越界 / `cursor` 非正整数）。

**9. `GET /diagnostics/attempts/{attempt_id}`** — 路径参数 `attempt_id ≥ 1`。
成功 200：`attempt_id`、`submitted_at`、`question_set_version`、`rule_version`、`total_correct`、`total_questions`、`domains[]`、`questions[]`（逐题 `selected` / `correct` / `is_correct` / `explanation`）。
**这是唯一返回答案键的接口**。错误：404 `NOT_FOUND`（批次不存在，或不属于当前用户——两种情况响应一致，不泄露存在性）。

### 4.4 周计划（study-plan）

**10. `GET /study-plan/preview`** — 无参数。
成功 200：`computed`、`persisted`（**恒为 `false`**）、`days[]`、`note`、`weekly_minutes`、`timezone`、`focus_stage`、`advice`、`stages[]`。纯内存计算，**不写任何计划行**。
错误：422 `VALIDATION_ERROR`（时区未确认）。

**11. `GET /study-plan`** — 无参数。
成功 200：`week_start`、`week_end`、`today`、`timezone`、`daily_minutes`、`study_days[]`、`weekly_planned_minutes`、`items_total`、`scheduled_items`、`history_items`、`expired_items`、`lesson_items`、`exercise_items`、`review_items`、`days[]`（每日给 `scheduled_minutes` / `history_minutes` / `total_minutes`）。**读取不生成计划**；恒有 `total_minutes <= daily_minutes`。
错误：422 `VALIDATION_ERROR`（时区未确认）。

**12. `POST /study-plan/generate`** — 无请求体。
成功 200：`generated`、`unscheduled[]`。同一周重复生成**行数不变**；`done`/`skipped` 行不被改写；已过去的日期不新增任务。
错误：422 `VALIDATION_ERROR`（时区未确认）。

**13. `PATCH /study-plan/items/{item_id}`** — 请求体 `{"status": "done" | "skipped"}`（只接受这两个值）；`item_id ≥ 1`。
成功 200：`week_start`、`plan_date`、`updated_at`。
错误：404 `NOT_FOUND`（不存在或不属于当前用户）；**409 `PLAN_ITEM_LOCKED`**（已是终态，**没有撤销**）；422 `VALIDATION_ERROR`（其它 status 值）。

### 4.5 课程与进度（lessons）

**14. `GET /lessons`** — 无参数。
成功 200：`items[]`（元数据 + 当前用户进度，不含正文）、`total`。

**15. `GET /lessons/{lesson_id}`** — `lesson_id ≥ 1`。
成功 200：`content`（正文五块结构）。**打开课程不写库**（不置 `in_progress`、不计时长）。
错误：404 `NOT_FOUND`（不存在或未发布）。

**16. `PUT /lessons/{lesson_id}/progress`** — 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `status` | `"not_started" \| "in_progress" \| "completed"` | 必填；只前进不后退 |
| `self_assessment` | `int \| null` | 0–2（自评 L0–L2）。**只写 `learning_progress`，永不写 `user_skill_levels`** |
| `time_spent_seconds` | `int \| null` | ≥ 0 |
| `progress_pct` | `int \| null` | 0–100；服务端只增不减，`completed` 时固定 100 |

成功 200：`lesson_id`、`status`、`plan_items_completed`、`self_assessment`、`progress_pct`、`time_spent_seconds`、`started_at`、`completed_at`、`updated_at`。`completed` 会在同一事务内把关联的 `scheduled` 计划项置 `done`。
错误：404 `NOT_FOUND`；**422 `COURSE_PROGRESS_REGRESSION`**（进度回退，零写入）；422 `VALIDATION_ERROR`（`self_assessment > 2` 等）。

### 4.6 练习与判题（exercises / submissions）

**17. `GET /exercises`** — 查询参数 `lesson_id`（可选，≥ 1）。
成功 200：`items[]`（含当前用户最近一次提交状态与通过数）、`total`。

**18. `GET /exercises/{exercise_id}`** — `exercise_id ≥ 1`。
成功 200：`prompt`、`starter_code`、`visible_tests[]`。**不含** `required_patterns` / `expected_output` 等答案键。
错误：404 `NOT_FOUND`（不存在或未发布）。

**19. `POST /exercises/{exercise_id}/submissions`** — 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code_text` | `string` | 1–20000 字符。**只做静态模式匹配，绝不执行** |
| `claimed_output` | `string \| null` | ≤20000 字符，与题库 `expected_output` 做归一化文本比对 |
| `self_reported_passed` | `bool \| null` | 自报本地跑通；填了就走自检，并标记为未验证 |

成功 **201**：`submission_id`、`judging_mode`、`verification_method`、`verification_strength`、`evidence_label`、`is_passed`、`checks[]`。**不写 `user_skill_levels`**（自评不自动升级）。
错误：404 `NOT_FOUND`；409 `CONFLICT`（同一题的提交序号并发冲突，重试即可）；422 `VALIDATION_ERROR`（`code_text` 为空或超长）。

**20. `GET /exercises/{exercise_id}/submissions`** — 无参数。
成功 200：`items[]`（新到旧，含判定方式与证据标签）、`total`（全部尝试数）。错误：404 `NOT_FOUND`。

**21. `GET /submissions/recent`** — 查询参数 `limit`（默认 20，1–50）。
成功 200：`items[]`（跨题、新到旧）、`total`。错误：422 `VALIDATION_ERROR`（`limit` 越界）。
> 路径注意：这个端点**不在** `/exercises` 命名空间下，见第 6 节「已知的不一致」。

### 4.7 AI 导师（ai）— 需要 `DEEPSEEK_API_KEY`

**22. `POST /ai/tutor`** — 请求体：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `question` | `string` | 1–2000 字 |
| `assistance_level` | `"none" \| "hint" \| "partial_code" \| "full_answer"` | 帮助程度；这个枚举也是 `ai_interactions` 里唯一允许的取值 |
| `context` | `object \| null` | 只带 `lesson_id` / `exercise_id`（均 ≥ 1），**不带任何代码文本** |

成功 200：`interaction_id`、`answer`、`model`、`assistance_level`、`usage`、`latency_ms`、`citations[]`（知识库引用；没检索到就是空数组，**不阻断回答**）。
错误：**503 `AI_UNAVAILABLE`**（未配置 Key，未发起上游请求）；**429 `AI_QUOTA_EXCEEDED`**（当日 token 已用完）；**504 `AI_TIMEOUT`**；**502 `AI_UPSTREAM_ERROR`**；404 `NOT_FOUND`（`context` 里的课程 / 练习 id 不存在）；422 `VALIDATION_ERROR`。
> 每一次调用（含失败）都会在 `ai_interactions` 写一行用量记录，因此「没拿到答案」也计入当日 token 预算。

**23. `GET /ai/interactions`** — 查询参数 `limit`（默认 20，1–50）。
成功 200：`items[]`（新到旧，只有问题预览与用量，**不含回答全文**）、`total`。错误：422 `VALIDATION_ERROR`。

### 4.8 知识库（knowledge）

**24. `GET /knowledge/search`** — 查询参数 `q`（2–200 字符，必填）、`limit`（默认 5，1–50）。
成功 200：`query`、`items[]`、`total`。评分规则：`score = 命中词数 / 查询词数`，heading 与标题命中额外加分。
错误：422 `VALIDATION_ERROR`（`q` 缺失、为空或少于 2 字符；`limit` 越界）。

**25. `GET /knowledge/sources`** — 查询参数 `limit`（默认 50，1–200）。
成功 200：`items[]`（每个来源的入库时间、`age_days`、`stale`、块数）、`total`。`stale` 由 `KNOWLEDGE_STALE_DAYS` 决定。错误：422 `VALIDATION_ERROR`。

**26. `POST /knowledge/ingest`** — 请求体可选：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `urls` | `string[] \| null` | 省略则入库默认白名单与仓库内全部课程；最多 20 条，单条 ≤2048 字符。只接受 `docs.python.org` 页面与 `repo://lesson/<code>` |

成功 200：`results[]`（逐条来源的状态与 `error_code`）、`sources_total`、`chunks_total`。幂等：内容未变则跳过；单个来源失败不影响其他来源（**200 响应内**标 `error_code=BLOCKED_HOST` / `INGEST_ERROR`）。
错误：**403 `INGEST_DISABLED`**（`KNOWLEDGE_INGEST_ENABLED` 未开启，未做任何数据库或网络操作）；422 `VALIDATION_ERROR`（`urls` 为空串、超长或超过 20 条）。

---

## 5. 需要环境配置的端点

| 端点 | 需要 | 缺失时的行为 |
| --- | --- | --- |
| `POST /ai/tutor` | `DEEPSEEK_API_KEY` 非空 | 503 `AI_UNAVAILABLE`，`details.reason="not_configured"`，**不发起任何上游请求、不产生费用**；其余端点照常工作，`/health` 的 `ai_configured` 为 `false` |
| `POST /knowledge/ingest` | `KNOWLEDGE_INGEST_ENABLED=true` | 403 `INGEST_DISABLED`，**未做任何数据库或网络操作**（入库是写路径，默认必须关闭） |
| `GET /knowledge/search`、`/knowledge/sources` | 无 | 知识库为空时返回空列表，不报错 |
| `POST /ai/tutor` 的 `citations` | 知识库已有内容（可选） | 检索不到就是空数组，回答照常返回 |

相关变量默认值见 [apps/api/.env.example](../apps/api/.env.example) 与 [.env.example](../.env.example)；**任何真实 Key 都不得提交到仓库**。

---

## 6. 已知限制与不一致（如实记录，未偷偷改实现）

1. **`GET /submissions/recent` 不在 `/exercises` 命名空间下**：其余提交类端点都在 `/exercises/{id}/submissions`，只有它挂在 `/submissions/recent`。这是 Sprint 3 落地时的选择（跨题查询不属于某一节练习），但与其他路径风格不一致。**当前版本不改**（改路径会破坏已有前端调用），如需收敛请作为单独变更 + 版本说明。
2. **分页只有 `limit`**：除 `GET /diagnostics/history` 的 `cursor` 外，其余列表端点没有游标 / 偏移分页。数据量变大时会出现「只能看最近 N 条」的问题，属已知技术债。
3. **单用户、无鉴权**：见第 1 节。所有端点共享同一个用户；不存在「按用户隔离」的能力。
4. **不执行用户代码**：练习判题是静态规则 + 自报输出比对，不能证明代码真的跑通。
5. **`GET /ready` 与 `GET /health` 不走统一错误体**：它们返回各自的结构（就绪失败是 503 + `status=not_ready`），这是刻意保留的运维语义。
6. **逐题解析恒为 `null`**：`GET /diagnostics/attempts/{id}` 的 `questions[].explanation` 后端恒返回 `null`（题库暂无解析字段）。

---

## 7. 相关文档

- 冻结契约（错误码与状态码的原始出处）：[SPRINT1A_CONTRACT.md](SPRINT1A_CONTRACT.md) §6
- 架构与模块边界：[ARCHITECTURE.md](ARCHITECTURE.md)
- 数据模型：[DATABASE.md](DATABASE.md)
- 本地启动与测试命令：[../CONTRIBUTING.md](../CONTRIBUTING.md)
