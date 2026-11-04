# SPRINT 1A 决策记录（契约冻结）

- 上游依据：`Sprint1_Independent_Review.md`（结论 **CONDITIONAL GO：只做 1A，不冻结/不执行 Sprint 1 业务迁移**）
- 本轮范围：只修文档契约，**不写业务代码、不执行迁移、不推送 GitHub**
- 仓库基线：`f06dab4`（工作树另有上一轮审查的未提交改动，本轮未回退）
- 配套测试证据：`SPRINT1A_TEST_RESULTS.md`

---

## 1. 两条由项目负责人拍板的决策

| 决策 | 选项 | 结论 |
|---|---|---|
| Sprint 1 是否保留周计划生成 | A 不落库预览（推荐）/ C 以 skills 为 target / B 提前建课程种子 | **A**：S1 不创建 `study_plan_items`、不写计划行；R1–R6 与对应验收整体移入 S2 |
| 当前能力等级取值规则 | A 证据分层优先、同层取最新 / B 单调只升不降 / C 双值并列展示 | **A**：tier 3 > tier 2 > tier 1 > tier 0，同层取最新；`requested_verification` 永不作为展示等级 |

## 2. 八项复审问题的裁定与落位

| # | 问题 | 严重度 | 裁定 | 落位 | 验证方式 |
|---|---|---|---|---|---|
| 1 | 当前等级被「最新一条」覆盖，弱证据可盖掉强证据 | P0 | 改为**证据分层**：tier 3 = `verification_method in (runtime_test, manual_review)`；tier 2 = `evidence_kind in (practice, transfer)` 且 `static_rule`；tier 1 = `diagnostic`；tier 0 = `self_assessment`。只取 `assessment_state='established'`，按 `(tier DESC, created_at DESC, id DESC)` 每域取一条 | DATABASE §4.4（SQL 272–298）、PRD §5.1（222–258）、ARCHITECTURE §3.5、ROADMAP §4、CONTRACT §3 | 五份文档 SQL 与规则一致；七行取值例子表在 PRD/CONTRACT 逐字相同 |
| 2 | L0 与证据强度互斥（`evidence_strength NOT NULL` 只有两值，无法表达「无」） | P0 | `assessment_state` 四态：`unassessed` / `assessed_below_threshold` / `established` / `requested_verification`；`evidence_strength` 为生成列，允许 `none` 但**仅限 level=0**；诊断只能得 `assessed` | DATABASE §4.4、PRD §5.1（L0 两态表）、CONTRACT §2、§3 | 交叉 CHECK 写入约束清单（C 系列） |
| 3 | S1 生成指向不存在课程/练习的 `target_id` | P0 | **S1 不建 `study_plan_items`、不写计划行**；计划预览改为内存计算、`persisted=false`；表设计与 R1–R6 移入 S2 | ROADMAP §4/§5、PRD §5.2、DATABASE §4.14、ARCHITECTURE §3.7、CONTRACT §7 | ROADMAP S1 节内 `study_plan_items` 命中全为否定式声明；AC-S1-15「预览不落库」 |
| 4 | `static_rule` 被当作真实验证，可自动授 L3/L4 | P0 | 新增 `verification_method`（none/self_report/static_rule/runtime_test/manual_review）+ 生成列 `verification_strength`；`static_rule` 只产 `assessed`；**MVP 等级上限 L2**，L3/L4 仅可作 `requested_verification` | DATABASE §4.8（映射表 446–457）、ARCHITECTURE §3.2、PRD §5.4、CONTRACT §5 | 六种情况表 v2（7 行）五份逐字一致；`'unverified'` 计数 0 |
| 5 | `study_days` 未禁重复，空数组可绕过 CHECK | P1 | 放宽到 1–7 天；三条 CHECK（非空 / 值∈1..7 / 长度≤7）+ `BEFORE INSERT OR UPDATE` 去重触发器 `trg_user_profiles_study_days_unique`；8 条用例（`{}`、`{1,1}`、`{8}`、`{0}` 拒；`{1,3,5}`、`{1..7}` 通过；`daily_minutes` 10/481 拒） | DATABASE §4.2 + §4.16 C1–C8、CONTRACT §8 | 约束测试清单 C1–C8 |
| 6 | `evidence_ref` 声称指向诊断批次，但无该批次记录 | P1 | 新增第 15 张表 `diagnostic_attempts`（单表 + JSONB `answers` / `domain_scores` + `question_set_version` + `rule_version`）；`evidence_ref` 统一 `diag:<attempt_id>`；重复提交追加新批次 | DATABASE §4.15、PRD §5.1、ARCHITECTURE §3.6、CONTRACT §4 | AC-S1-11 批次可追溯；AC-S1-12 重复诊断追加 |
| 7 | `uq_study_plan_items_dedupe` 不足以保证重生成幂等 | P1 | 冻结为**单事务**：读现有行 → 计算目标集 → 按 `dedupe_key` UPSERT → 不删除 `done`/`skipped` 行；三条不变量（行数不变、done 保持、skipped 保持且 `updated_at` 不改写）+ 三个验收用例 | DATABASE §4.14、ARCHITECTURE §3.7、ROADMAP §5（AC-S2-06 ①②③）、CONTRACT §7 | S2 实施时验收；本轮仅冻结契约 |
| 8 | 时区依赖服务器默认值，学习时间边界不清 | P1 | `users.timezone_source`（`default` / `user_confirmed`）；未确认前禁止展示「今日/本周」推导；非学习日不分配任何计划项；所有日期计算只用 `users.timezone` | DATABASE §4.1、PRD §5.2、ARCHITECTURE §7、CONTRACT §2 | AC-S1-13 时区确认；R2 引用「非学习日不分配」 |

## 3. 契约 v2 的六条硬规则（供 Sprint 1B 直接实现）

1. **等级解析唯一口径**：只读 `assessment_state='established'` 的行，`DISTINCT ON (skill_id) ... ORDER BY skill_id, tier DESC, created_at DESC, id DESC`；无 established 行时回退 level=0 并显示该域最新非 established 状态。
2. **评分不等于验证**：诊断（客观题、机器评分）只能产出 `evidence_strength='assessed'`；`static_rule` 同理。`verified` 只能来自 `runtime_test` 或 `manual_review`，Sprint 1–3 不可达。
3. **六种情况表 v2**（7 行）：完全独立通过 / hint / partial_code / full_answer / 未通过 / 无法验证的自检 / 未来真实执行通过。前六种均不可作 L3 证据，第七种才可。
4. **`judging_mode` 与 `verification_method` 不是同一件事**：前者是「提交时声明的判定方式」，后者是「服务端最终记录的证据方式」。映射：`self_check→self_report`、`static_rule→static_rule`、`manual→none`（人工复核通过后改写为 `manual_review`）。
5. **S1 迁移只建 5 张表**：`users`、`user_profiles`、`skills`（6 行种子）、`diagnostic_attempts`、`user_skill_levels`；迁移名 `0002_sprint1a_identity_diagnostics`；**不建** `study_plan_items` 等其余 10 张表；禁止 `DROP` / `DELETE` / `down -v`。
6. **计划预览不落库**：`GET /api/v1/study-plan/preview` 返回 `computed=true, persisted=false`，数据库不得出现任何计划行。

## 4. 过程偏差（如实记录）

| # | 偏差 | 影响 | 处置 |
|---|---|---|---|
| 1 | PRD 负责人因 `read` 在 ~52KB 处截断而整文件回写，导致 §9 尾部 + §10 + §11 一度丢失 | 一度 616 行 | 其自行回填；**我逐节复核：11 个 H2 齐全、§9 表格、§10 十三行、§11 四条、文件尾正常，无残留损伤** |
| 2 | ARCHITECTURE 负责人落盘写操作 4 次，超出给定上限 3 次 | 无内容影响 | 自检发现并修复；记入本表 |
| 3 | ARCHITECTURE 插入新小节时误覆盖 §7 第 12 条（安全代码执行方案评估） | 条目短暂丢失 | 已按原文逐字恢复，现编号 10–15 连续 |
| 4 | CONTRACT 负责人报告「ARCHITECTURE 6.1 把 request_id 放在 error 内」 | 误报（读到旧版本） | 我实测当前 §6.1 已是顶层 `request_id`，已撤回该主张，未改动 ARCHITECTURE |
| 5 | ARCHITECTURE 负责人报告「A.6 第 5 行 tier 表述相反」 | 误读 | 原文「tier 2 > tier 1，弱层不覆盖强层」正确，未改 |

此外，我自己在契约 v2 初稿中写错了 A.6 第 4 行（同时写「level 2 不变」与「实际 level 1」），已由 PRD 与 CONTRACT 两处统一为 `level 1（较原 L2 降级）`，并做 byte 级比对确认一致。

## 5. 仍未解决的决策（不阻塞 Sprint 1B）

| # | 待决事项 | 当前处置 | 建议时点 |
|---|---|---|---|
| 1 | 同一 tier 内是否允许**降级**（现按「同层取最新」允许） | 已按允许执行，并在文档登记 | S2 计划功能开工前定稿 |
| 2 | `judging_mode` 是否最终与 `verification_method` 合并为一套枚举 | 暂保留两列 + 唯一映射表 | S3 练习判题实现时 |
| 3 | L4 的复核状态何时能转 `confirmed` | 现统一为界面 `pending_review`、不落库；落库为 `requested_verification` 申请行 | 引入真实执行验证之后 |
| 4 | `diagnostic_attempts` 与未来审计日志表的关系（是否合并） | 暂独立 | S5 复习功能前 |
| 5 | 文档版本行不统一（PRD/ROADMAP v1.2，DATABASE/ARCHITECTURE v1.1） | 不影响契约内容 | 下次统一改写时一并处理 |

### 已知措辞读法（不改，但需按此理解）

- PRD:367 与 ROADMAP:244 中的「…transfer，状态一律 `pending_review`，不自动 confirmed」，指的是 **L4 的复核结论状态**，不是往 `assessment_state` 写值；落库形态以 DATABASE §4.4 与 PRD:203 / ROADMAP:115 为准。

## 6. 本轮交付物

| 文件 | 行数 | 说明 |
|---|---|---|
| `docs/SPRINT1A_CONTRACT.md` | 424 | **新建**：九节可执行契约（字段、状态机、JSONB 形态、六种情况表、API、迁移草案、21 条约束测试、验收映射 20 行） |
| `docs/PRD.md` | 673 | 诊断与等级口径、S1 成果、六种情况表 v2、G2 指标改 L2、影子规则 |
| `docs/DATABASE.md` | 962 | 15 张表、`diagnostic_attempts`、等级解析 SQL、映射表、`study_days` 触发器、约束测试 C1–C17、迁移草案 |
| `docs/ARCHITECTURE.md` | 634 | 等级解析、诊断单事务、幂等三不变量、5 个 API 示例、监听与时区规则 |
| `docs/ROADMAP.md` | 479 | S1 收窄、S2 承接计划与 R1–R6、AC-S1-01..18 重排 |
| `SPRINT1A_DECISIONS.md` | 本文件 | 决策记录 |
| `SPRINT1A_TEST_RESULTS.md` | — | 实际命令、退出码、一致性比对结果 |

未修改：`apps/**`（源码零改动）、`infra/**`、`docs/DESIGN_SYSTEM.md`、任何依赖与锁文件。未执行 alembic 迁移、未创建业务表、未推送 GitHub。

## 7. 退出标准核对

| 复审要求的退出标准 | 达成情况 |
|---|---|
| 跨文档合同一致 | ✅ 六种情况表 v2 五份 `SAME`；A.6 第 4 行 PRD/CONTRACT `byte-identical`；映射表与枚举值一致 |
| 每个状态/字段有可合法存储的示例 | ✅ CONTRACT §2 字段表、§3 状态机、§4 JSONB 形态（9 段 JSON 均可解析） |
| 明确当前技能等级查询方案 | ✅ DATABASE §4.4 可执行 SQL + CONTRACT §3.3 逐字 |
| 每个验收项对应实际数据而非占位 | ✅ CONTRACT §9 覆盖 AC-S1-01..18 与 PRD AC-09/AC-31，共 20 行，无占位 |

## 8. 下一步

Sprint 1A 到此冻结。**Sprint 1B 启动的前置条件**：本记录第 5 节第 1 条（同层是否降级）若不改，可直接开工；如需改为「同层不降级」，须先回写 DATABASE §4.4 SQL 与 PRD A.6 表，再开工。

Sprint 1B 不得做的事（本轮已冻结）：写 `study_plan_items`、调用 DeepSeek、执行用户代码、引入登录、创建 0002 以外的表。