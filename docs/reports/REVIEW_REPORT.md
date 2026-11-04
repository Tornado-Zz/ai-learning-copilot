# Sprint 1 准入审查报告

- 审查基线：`f06dab4`（Sprint 0 交付提交）
- 审查对象：`apps/web`、`apps/api`、`infra`、`docs` 五份文档、根配置
- 审查方式：重新执行命令 + 源码抽查 + 跨文档机械比对；不采信任何自述结论
- 详细测试记录见同目录 `TEST_RESULTS.md`，本轮改动见 `CHANGELOG.md`

---

## 一、Sprint 0 各项测试是否真实通过

**结论：真实通过。9 项检查在本轮全部重新执行，无一项引用历史结果。**

| # | 检查 | 退出码 / 结果 |
|---|---|---|
| 1 | 前端依赖安装 | `npm install` 成功，`package-lock.json` 存在 |
| 2 | TypeScript 类型检查 | `npx tsc --noEmit` → **0** |
| 3 | ESLint | `npm run lint` → **0**，0 error |
| 4 | Next.js 生产构建 | `npm run build` → **0**，6 条路由（含 `_not-found`）静态预渲染 |
| 5 | FastAPI 启动 | `uvicorn app.main:app` 监听 `127.0.0.1:8000` |
| 6 | Pytest 单元 | `uv run pytest -q` → **0**，`11 passed, 1 deselected` |
| 7 | Pytest 集成 | `uv run pytest -q -m integration` → **0**，`1 passed, 11 deselected` |
| 8 | PostgreSQL | 容器 `Up (healthy)`，仅 `127.0.0.1:5432`，`PostgreSQL 17.11` |
| 9 | health / ready | health **200**（六字段全、`ai_configured=false`）；ready **200**（`connected`，`latency_ms=5`） |
| 10 | Alembic | `0001 (head)`；业务表计数 **0** |
| 11 | 前后端通信 | 浏览器实测显示「后端在线 · 数据库已连接」 |
| 12 | Git / 密钥 | 基线后仅本轮 6 个文件改动；`sk-*` 与私钥头扫描 **0 命中** |

未发现失败项，因此本轮无失败信息可记录。已知的非失败告警有两类，均不属代码缺陷：

1. 后端未启动时浏览器 Console 出现 2 条 `net::ERR_CONNECTION_REFUSED` 网络层日志（应用代码 `console.` 调用计数为 0）。
2. `next start` 绑定地址问题（见第二节第 5 条）已修复，修复前会打印 `Network: http://<局域网 IP>:3000`。

## 二、本轮要求的五个主要问题是否全部解决

**结论：五个问题全部解决，且每条都有可复现的验证方式。**

| # | 问题 | 严重度 | 解决方式 | 验证 |
|---|---|---|---|---|
| 1 | 20 道初步诊断题直接产出 L0–L4，L3/L4 无实践证据 | 高 | 诊断只授予 **L1/L2**；L3 需同域 ≥3 次不同题目且 `ai_assistance_level='none'` 且 `verification_status='verified'`；L4 需迁移任务且一律 `pending_review`；新增 `source`/`evidence_strength`/`verification_status`/`evidence_ref`/`evidence_count` 五个溯源字段；无证据域写 L0 且 `unassessed`，禁止推测 | `grep -cE '20 题[^|]*L0–L4' docs/PRD.md` → **0**；`AC-S1-08/09/10` 为可判定断言 |
| 2 | `used_ai`/`assistance_level`/`passed_with_ai`/`is_passed`/`dependency_level` 在 PRD 与 ARCHITECTURE 间口径矛盾，且「用了 AI 却记为完全独立」可写入数据库 | 高 | 收敛为 **3 列可写**（`is_passed`/`verification_status`/`ai_assistance_level`）+ **2 个生成列**（`used_ai`、`passed_with_ai`）+ `has_prompt_dependency` 改为查询派生；六种情况取值表在四份文档中逐字一致 | 四份文档表格 `diff` → **ALL FOUR IDENTICAL**；生成列 `grep -F` 各 **1** 处；`has_prompt_dependency` 仅出现在移除语境 |
| 3 | 学习计划缺学习日、每日可用时长、时区，无法判定「不超支 / 不强制每天 / 可幂等重生成」 | 中 | `user_profiles` 新增 `study_days`（1–7 数组）、`daily_minutes`（15–480），`weekly_minutes` 改生成列；`users.timezone` 作为唯一边界；新增第 14 张表 `study_plan_items` 与唯一约束 `uq_study_plan_items_dedupe`；定义 R1–R6 六条可判定规则 | `AC-S1-11..17` 一一对应 R1–R6；本轮不含调度代码（符合要求） |
| 4 | 编程评测真实性边界不清，`self_check` 与「真实运行通过」被混同 | 中 | 明确 `self_check`＝用户自检、`static_rule`＝静态规则+文本比对、`manual`＝待人工；`run_output_text` 不构成代码运行证明；界面禁用「已通过自动测试 / 实时运行结果」；自检结果不得作为 L3/L4 证据；ROADMAP 新增 §10.1 安全代码执行方案评估（四方案 × 五维度） | ARCHITECTURE §3.2 能力边界三行表；ROADMAP `AC-S7-07/08/09`；本轮未安装、未实现任何沙箱 |
| 5 | 本地监听地址不统一，且无认证前端默认暴露到局域网 | 高（安全） | 实测 `next start` 默认绑 `0.0.0.0:3000` 与 `[::]:3000`；改为在 `apps/web/package.json` 的 `dev`/`start` 脚本加 `-H 127.0.0.1`；ARCHITECTURE 拓扑图与端口表统一三端口回环；README 增补监听约定 | 改后 `netstat` 仅 `127.0.0.1:3000`；`grep -c 0.0.0.0 docs/ARCHITECTURE.md` → **0** |

另有一项额外要求（Sprint 顺序）也已处理：S1 档案诊断 → S2 课程 → S3 练习 → S4 AI 导师 → S5 错题 → S6 项目 → S7 打磨，**8 个功能需求 8/8 有归属、一条未删**，旧编号残影清零。

## 三、是否还有文档与代码不一致

**结论：本轮口径层面已无矛盾；仍存在「设计态 vs 实现态」的差距，但这属于既定计划，不是矛盾。**

已消除的矛盾（本轮由审查方裁定后统一）：

| 冲突 | 处理 |
|---|---|
| `study_plan_items` 字段可空性：PRD / ROADMAP 可空 vs DATABASE NOT NULL | 统一 NOT NULL（否则 R1 求和、R5 可解释性无法判定） |
| 课程掌握度默认值：PRD 默认 L1 vs ROADMAP 默认 L0 | 统一默认 **L0（未评估）**；仍允许用户自评 L0–L4，但标注「自评，未经验证」且不写入 `user_skill_levels` |
| `exercises.kind` 是否存在：L4 判定依赖它，但原设计无此列 | 批准新增（`NOT NULL default 'practice' CHECK in ('practice','transfer')`） |
| ARCHITECTURE 拓扑图写 api 监听 `0.0.0.0:8000`，与端口表及 uvicorn 默认值矛盾 | 全部改为 127.0.0.1 |
| 六种情况取值表四份文档表述不一 | 逐字统一，`diff` 全部 SAME |

仍然存在、需要如实记录的不一致：

1. **设计态 vs 实现态（计划内）**：`docs/DATABASE.md` 的 14 张表全部是设计，数据库业务表为 **0 张**；文档中的 `/api/v1/users/me`、`/skills`、`/diagnostics`、`/study-plan` 均未实现，现有代码只有 health 与 ready。文档已标注这些是「待实现设计」，但读者若只看文档容易误认为已落地。
2. **表计数表述不同**：ARCHITECTURE 写「13 张，S1 起新增为第 14 张」，DATABASE 写「表数量为 14」。语义一致，字面不同。
3. **等级表列数不同**：PRD 为 6 列（含授予来源/证据强度），DATABASE 与 ROADMAP 为 3 列。逐条核对语义相同（只有六种情况表要求逐字一致）。
4. **ARCHITECTURE 缺 `study_plan_items` 数据流小节**，周计划生成流程仅见于 PRD / ROADMAP。
5. **`learning_progress` 无证据强度列**：「自评，未经验证」目前靠界面标注 + 「不写 `user_skill_levels`」约束，没有字段级保证。
6. **R1 / R2 无法用数据库约束表达**，只能服务层校验，正确性依赖代码而非数据库兜底。
7. **`docs/DATABASE.md` 4.14 节缺完整 `CREATE TABLE`**（为守行数预算裁剪），只有字段表 + 约束 + 索引。
8. **DeepSeek 模型 id 未核实**：`deepseek-flash` / `deepseek-v4-pro` 需在 S4（首次真实调用）前对照官方文档确认。
9. **移动端 <768px 无视觉验收**：代码层断点与抽屉逻辑已核（`md:flex` / `md:hidden` / Escape 关闭），但无窄屏截图证据。

## 四、当前遗留问题及严重程度

| # | 遗留问题 | 严重度 | 影响面 | 建议时点 |
|---|---|---|---|---|
| 1 | DATABASE 4.14 缺完整 DDL | 中 | S1 迁移 | S1 写 0002 迁移时补齐并逐项核对字段表 |
| 2 | R1/R2 仅服务层校验 | 中 | S1 计划生成正确性 | S1 在 `app/services/planning.py` 单点实现，其他模块只读 |
| 3 | 「自评」标注无字段保证 | 中 | 进度页可信度 | 落 `learning_progress` 前决定加列或纯界面约定 |
| 4 | ARCHITECTURE 缺计划生成数据流 | 低 | 可读性 | S1 结束时补一节 |
| 5 | 表计数与等级表字面不统一 | 低 | grep 检索 | 顺手统一或接受现状 |
| 6 | DeepSeek 模型 id 未核实 | 中（S4 前） | 真实调用 | S4 开工前确认，S1–S3 无 AI 调用不受影响 |
| 7 | 移动端无视觉验收 | 低 | 体验 | 有窄屏环境时补截图 |
| 8 | 本轮 6 个文件未提交 | 低 | 版本管理 | 建议 S1 开工前提交，见下 |

无「高」级别遗留问题。

## 五、是否允许启动 Sprint 1

# 判定：GO

理由：

1. Sprint 0 的 12 项检查在本轮全部重新执行通过，无回归；唯一代码改动（`package.json` 绑定回环）是安全加固，构建仍为 0。
2. 本轮要求的五个问题全部解决，且解决方式在四份文档中相互一致（关键契约逐字一致）。
3. 三处跨文档冲突由审查方裁定后统一，无悬空结论。
4. 遗留问题中没有「高」级别项，且没有一项阻断 S1 开工：DDL 缺失正是 S1 自身交付物；R1/R2 服务层校验是既定设计；模型 id 不影响 S1（S1 不调用 AI）。

随 S1 一并闭环的三个收尾动作（不构成准入门槛）：

1. 提交本轮改动（建议拆两个提交：`docs: align sprint 0 docs with capability-evidence and prompt-dependency rules` 与 `fix(web): bind dev/start to loopback`）。
2. S1 的 0002 迁移补齐 `study_plan_items` 完整 DDL。
3. 落地 `learning_progress` 前确定「自评」标注方式。

## 附：本轮修改文件

| 文件 | 变更 | 说明 |
|---|---|---|
| `apps/web/package.json` | +2/−2 | `dev`/`start` 加 `-H 127.0.0.1` |
| `docs/PRD.md` | +163/−47 → 612 行 | 诊断口径、等级表、六种情况表、R1–R6、Sprint 表、监听地址、AC-31..35 |
| `docs/DATABASE.md` | +228/−40 → 785 行 | 证据溯源五字段、3 列可写 + 2 生成列、`exercises.kind`、`study_plan_items`（第 14 张表） |
| `docs/ARCHITECTURE.md` | +97/−24 → 514 行 | 判题能力边界表、依赖计算口径、监听地址、安全节新增 4 条 |
| `docs/ROADMAP.md` | +296/−94 → 448 行 | S1–S7 重排、AC 重编号 75 条、§10.1 安全执行评估 |
| `README.md` | +4 | 本地监听约定 |

未修改：`apps/api/**`、`docs/DESIGN_SYSTEM.md`、`next.config.ts`、任何依赖。未执行 git 写操作，未推送 GitHub。