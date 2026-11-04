# SPRINT 1B 测试结果

> 本文件记录 Sprint 1B **实际执行**的命令与结果。所有数字均为调度者亲自复跑所得，未引用子 agent 自述。

## 1. 环境

| 组件 | 版本 |
|---|---|
| Node.js / npm | v26.13.0 / 11.20.0 |
| uv / Python | 0.13.5 / 3.12.15 |
| Next.js / React / TypeScript | 16.4.4 / 19.3.0 / 5.9.3 |
| Pytest | 9.2.0 |
| PostgreSQL（容器） | 17.11，`127.0.0.1:5432` |
| Alembic head | `0002_sprint1a_identity_diagnostics` |

## 2. 命令与退出码

| # | 命令 | 目录 | 退出码 | 结果 |
|---|---|---|---|---|
| 1 | `npx tsc --noEmit` | apps/web | **0** | 无输出 |
| 2 | `npm run lint` | apps/web | **0** | eslint 无错误 |
| 3 | `npm run build` | apps/web | **0** | 11 条路由，含 5 条新路由 |
| 4 | `uv run pytest -q` | apps/api | **0** | `47 passed, 17 deselected` |
| 5 | `uv run pytest -m integration -q` | apps/api | **0** | `17 passed, 47 deselected`（连跑 3 遍均同） |
| 6 | `uv run pytest --collect-only -q` | apps/api | 0 | `47/64 tests collected` |
| 7 | `uv run alembic current` | apps/api | 0 | `0002_sprint1a_identity_diagnostics (head)` |
| 8 | `curl /api/v1/health` | — | 0 | 200 |
| 9 | `curl /api/v1/ready` | — | 0 | 200，`database.status=connected` |
| 10 | `curl /api/v1/diagnostics/paper` | — | 0 | 200，20 题，`answer` 命中数 **0** |
| 11 | `grep -rn 'console\.' src/` | apps/web | 0 | **0 条** |
| 12 | `grep -rn 'Sprint 0' src/` | apps/web | 0 | **0 条** |

## 3. 十五项必须测试的逐条结果

| # | 要求 | 验证方式（实际执行） | 结果 |
|---|---|---|---|
| 1 | 迁移升级成功 | `alembic upgrade head` → `alembic current` | ✅ `0002 (head)` |
| 2 | 五张业务表结构正确 | `information_schema` 查询 + `test_migrations::test_02` | ✅ 五表齐全 |
| 3 | skills 六条种子正确 | `psql` 直接查 `code, name_zh, order_index` | ✅ `route_a.a1…a6`，名称与顺序正确 |
| 4 | study_days 非法输入被拒 | `test_04`（DB 拒绝 `{}`/`{1,1}`/`{8}`/`{0}`）+ `test_04b`（API 422） | ✅ 全部被拒 |
| 5 | 20 题诊断正常提交 | 浏览器真实提交 | ✅ 批次 #93，1 attempt + 6 levels，`evidence_ref` 全为 `diag:93` |
| 6 | 评分与能力等级正确 | 浏览器答对 5/20 → 六域全 L0；API 全对 → 六域全 L2 | ✅ 25% / 0% 落 `assessed_below_threshold`；100%（4/4、3/3）落 L2 |
| 7 | 重复请求不产生重复提交 | 同 `attempt_token` 提交两次 | ✅ 同一 `attempt_id=94`，响应体相同，行数 `2/12` 不变 |
| 8 | 重新诊断保留历史 | 新 token 再提交 | ✅ 新增 `attempt=95`，`history` 倒序 3 条 |
| 9 | L0 状态正确 | 结果页文案 + `test_09` | ✅ 同页区分「L0 · 未评估」与「已测，未达 L1 门槛」 |
| 10 | 高层证据不被低层覆盖 | `test_10`（自建用户，先 tier2 practice 再 tier1 诊断） | ✅ 展示等级保持 tier2 |
| 11 | 提交失败事务完整回滚 | `test_11` / `test_11b` | ✅ attempts 与 levels 均无新增行 |
| 12 | 时区与学习日处理正确 | 浏览器改为 `{1,3,5,6}`/45 分钟并确认时区 → `users/me` | ✅ `user_confirmed`、`weekly_minutes=180`；预览 4 天全落在所选学习日 |
| 13 | 预览不写入数据库 | 调用前后行数对比 | ✅ `3/18` → `3/18`；`persisted=false` |
| 14 | 全部前端页面正常交互 | 浏览器端到端（第 5 节） | ✅ 5 条新路由全通，Console 0 条应用报错 |
| 15 | 原有测试无回归 | `tests/test_health.py`、`tests/test_ready.py` | ✅ 仍全绿（含在 47/17 内） |

## 4. 关键行为实测数据

```
=== 幂等与追加 ===
before       : 1/6            (attempts/levels)
1st  token A : 201 attempt=94 levels=[2] states=[established]
after 1st    : 2/12
2nd  token A : 201 attempt=94 identical=True
after 2nd    : 2/12           <- 未新增行
3rd  token B : 201 attempt=95
after 3rd    : 3/18           <- 追加历史

=== 预览零写入 ===
preview      : persisted=False days=4 | rows before/after: 3/18  3/18

=== 测试可重复性（修复后）===
BEFORE: 3/18/1/{1,3,5,6}45
集成档 第 1 遍 -> 17 passed, 47 deselected in 2.73s
集成档 第 2 遍 -> 17 passed, 47 deselected in 2.68s
集成档 第 3 遍 -> 17 passed, 47 deselected in 2.79s
常规档         -> 47 passed, 17 deselected in 10.54s
AFTER:  3/18/1/{1,3,5,6}45   <- 与测试前完全一致
```

## 5. 浏览器端到端记录（真实后端 8000 + 生产构建 3000）

| 步骤 | 结果 |
|---|---|
| `/onboarding` 加载 | 先显示骨架「正在读取学习档案」，随后预填已保存档案 |
| 填表 | 加选周六、分钟改 45、勾选时区确认 → 保存 200 → 自动跳 `/diagnostic` |
| 服务端核对 | `timezone_source=user_confirmed`、`study_days=[1,3,5,6]`、`daily_minutes=45`、`weekly_minutes=180` |
| `/diagnostic` 题面 | 首题为后端 `paper` 的 q01「执行 nums = [1, 2, 3, 4] 后，表达式 nums[1:3] 的结果是什么？」 |
| 草稿 | 答 2 题后刷新，回来仍「已答 2 / 20」 |
| 提交校验 | 未答完时按钮禁用并提示「还有 N 题未作答（第 … 题）」 |
| 提交 → `/result` | 批次 #93、规则版本 r1、六域「L0 · 未评估 / 已测，未达 L1 门槛 / 正确率 25%（1/4）」 |
| `/history` | 「共 3 个批次」；#95、#94「6 域已建立等级」，#93「0 域已建立 · 6 域未达门槛」 |
| 展开 #94 | 「L2 · 能跟做 / 已建立等级 / 该域正确率 100%（4/4 题），达到 L2 门槛（≥85%）」 |
| `/plan` | 「预览不落库」、`persisted false`、学习日「周一、周三、周五、周六」、每天 45、合计 180、日期 2026-11-02/04/06/07 全落在所选学习日 |
| 死链检查 | `/plan` 内链接仅指向 `/`、`/result`、`/onboarding`、`/history` |
| Console | 全程 **0 条应用报错** |

## 6. 失败记录（如实保留）

| 时间点 | 现象 | 原因 | 处置 |
|---|---|---|---|
| 首次执行 0002 | `value too long for type character varying(32)`，事务回滚，库仍 0001 | revision 名 34 字符超出 alembic 默认列宽 | 迁移首条语句扩宽至 64，重跑成功 |
| 端到端之后复跑集成档 | **9 failed, 9 passed**（`assert 24 == 6`、`user_confirmed == default`、`[1,3,5,6] == [1,3,5]`、`4 == 1`） | 用例依赖「空库 + 默认档案 + 单例用户」 | 改为自建独立用户 + 断言作用域化 + 基线复原；修复后连跑 3 遍全绿、数据零变化 |
| 前端首次 lint | 5 条 `react-hooks/set-state-in-effect` | effect 内直接 setState | 重构为异步之后再 setState，未关闭规则 |

## 7. 未执行的检查

| 项目 | 原因 |
|---|---|
| 移动端 <768px 视觉验收 | 本机浏览器工具无法设置视口宽度（已知限制） |
| 纯键盘 Tab 走完全部 20 题 | 本轮未逐键录制 |
| 跨浏览器（Safari / Firefox） | 本机仅 Chromium |
| `alembic downgrade` | 主动禁止（不提供破坏路径），未验证 |
| DeepSeek / 用户代码执行 | 本轮明确不接入、不执行 |