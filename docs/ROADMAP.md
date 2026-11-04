# AI Learning Copilot 路线图

**文档版本**：v1.3（Sprint 2 Patch：AC-S2-02/03/04 与实现对齐，新增 AC-S2-14 至 AC-S2-19）
**覆盖范围**：S0（本次）至 S7（首版完成）
**统一口径**：契约 v2（Sprint 1A 冻结），与 PRD.md、ARCHITECTURE.md、DATABASE.md、SPRINT1A_CONTRACT.md 逐字一致
**上游文档**：PRD.md（做什么）、ARCHITECTURE.md（怎么分层）、DATABASE.md（表在哪个 Sprint 落地）、DESIGN_SYSTEM.md（界面基线）

本文档只排期与定验收，不重复功能描述。术语统一使用：路线 A、能力诊断、AI 导师、提示依赖、开发中。

## 1. 路线原则

1. 小步迭代：每个 Sprint 为 2 周，结束当天必须能演示，且每一条验收条件都能用命令或界面操作判定。
2. 一次只推进一个可演示切片：不做"半个模块"，一个 Sprint 内不并行开两个未完成模块。
3. 契约先行：接口、表、错误码先在文档定稿再写代码；改动契约必须先改文档。
4. 可验证数据优先：每个 Sprint 交付的功能必须产生可查询的数据行，不做只存在于前端的假状态。
5. 每个 Sprint 必带三件事：一次 Alembic 迁移、后端接口测试、前端 lint 通过。
6. 文档同 Sprint 同步：PRD、ARCHITECTURE、DATABASE、ROADMAP、DESIGN_SYSTEM 与本 Sprint 的代码在同一批变更里更新。
7. 顺序原则：课程与练习先行，AI 导师后置。练习表在 S3 就落 ai_assistance_level 字段（此时唯一可达值为 'none'），S4 才开放 hint、partial_code、full_answer 三级；理由是提示依赖记录必须产生于真实提交，先有提交表再开放求助等级，AI 模块才不会没有数据可落。
8. 闭环优先于数量：小规模完整学习闭环（课程 -> 练习 -> 记录进度 -> 生成下一次周计划）优先于内容数量，任何 Sprint 不以内容条数作为完成前提。
9. 安全默认：本地无认证版本一律只监听回环地址，不对局域网或公网开放。

### 1.1 版本号规则

| 阶段 | 版本号 | 说明 |
|---|---|---|
| S0 | 0.1.0 | 骨架与契约 |
| S1 | 0.2.0 | 每次 Sprint 结束递增次版本号 |
| S2 | 0.3.0 | 同上 |
| S3 | 0.4.0 | 同上 |
| S4 | 0.5.0 | 同上 |
| S5 | 0.6.0 | 同上 |
| S6 | 0.7.0 | 同上 |
| S7 | 0.8.0 | 首版功能完成 |
| 开源发布 | 1.0.0 | 首版通过 S7 全部验收并完成开源准备 |

版本号写入 health 响应的 version 字段（见 ARCHITECTURE.md 第 4.1 节），发布时同步更新 apps/web/package.json 与后端配置。

### 1.2 Sprint 完成的统一标准（DoD）

一个 Sprint 只有同时满足以下 6 条才算完成：

1. 本 Sprint 的验收条件全部通过，且每条都有命令输出或截图记录。
2. 后端新增接口有测试，覆盖成功与至少一条失败分支。
3. 前端 npm run lint 0 error，TypeScript 0 error。
4. 新增表的迁移能在空库上从零 upgrade head 成功。
5. 相关文档（PRD 第 5 节、ARCHITECTURE 第 3 节、DATABASE 第 4 节、本文件）已同步。
6. 界面上未完成入口都标注"开发中"，符合 DESIGN_SYSTEM.md 第 7.3 节。

## 2. S0（本次）已完成范围

本节记录 S0 的范围与验收方式。实现证据以仓库和本地命令输出为准，本文档不声明运行时验证结果。

| 交付项 | 范围 | 验收方式 |
|---|---|---|
| 仓库骨架 | apps/web、apps/api、infra、docs 四个目录，结构见 ARCHITECTURE.md 第 2 节 | 目录树比对 |
| 五页骨架 | 路由 /（今日）、/learn、/practice、/projects、/progress，含空态与"开发中"标注 | 逐个访问返回 200 且不白屏 |
| 健康检查 | GET /api/v1/health 返回 status、service、version、environment、timestamp、ai_configured | curl 比对六个字段 |
| 就绪检查 | GET /api/v1/ready：数据库可用 200（ready、connected、latency_ms）；不可用 503（not_ready、disconnected、detail） | 停库前后各请求一次 |
| CORS 白名单 | 默认只允许 http://localhost:3000 与 http://127.0.0.1:3000 | 从白名单外来源发起请求被拒 |
| 本地编排 | infra/docker-compose.yml 提供 PostgreSQL，端口映射仅 127.0.0.1:5432 | docker compose ps 与端口检查 |
| 迁移骨架 | Alembic 骨架 + 空基线迁移，不创建业务表 | alembic upgrade head 成功且迁移表只有基线一条 |
| 基线文档 | docs 下 5 份文档：PRD、ARCHITECTURE、DATABASE、ROADMAP、DESIGN_SYSTEM | 文件清单与标题层级检查 |
| 密钥约束 | 仓库无任何真实 API Key；未配置 DEEPSEEK_API_KEY 时服务照常启动 | 全局搜索与无密钥启动验证 |

S0 明确不含：业务表、真实业务接口、AI 调用、认证、部署。

### 2.1 S0 之后的监听地址修正

- 实测：apps/web 的 next start 默认绑定 0.0.0.0:3000 与 [::]:3000（局域网可达）；uvicorn 默认绑定 127.0.0.1。
- 修复：apps/web/package.json 的 dev 与 start 脚本都显式加 -H 127.0.0.1（dev: next dev -H 127.0.0.1；start: next start -H 127.0.0.1）。
- 文档统一：web 127.0.0.1:3000、api 127.0.0.1:8000、postgres 127.0.0.1:5432；拓扑图不得再写 0.0.0.0。
- 安全原则：本地无认证版本一律只监听回环地址，不对局域网或公网开放。

## 3. 里程碑总览

| Sprint | 周次 | 主题 | 可演示成果 | 版本 |
|---|---|---|---|---|
| S0 | 已完成 | 骨架与契约 | 五页骨架、health 与 ready、迁移骨架、5 份文档 | 0.1.0 |
| S1 | 第 1–2 周 | 用户档案与能力诊断（Sprint 1A，不含学习路线） | 完成 20 题诊断，看到按证据分级的 6 个技能域等级（只授 L1/L2），并看到技能阶段级学习建议与不落库的计划预览 | 0.2.0 |
| S2 | 第 3–4 周 | 学习路线与课程（最小课程） | 3–5 节最小课程可读，study_plan_items 落库并按 R1–R6 幂等重生成，跑通"课程 -> 进度 -> 周计划"闭环 | 0.3.0 |
| S3 | 第 5–6 周 | 练习与判题 | 提交 5–10 道练习，看到 verification_method、verification_strength 派生值与 passed_with_ai | 0.4.0 |
| S4 | 第 7–8 周 | AI 导师与提示依赖记录 | 与 AI 导师对话，四级提示依赖开放，每次求助被记录为 dependency_level | 0.5.0 |
| S5 | 第 9–10 周 | 错题本与间隔复习 | 错题按 1/3/7/14/30 天回到今日页并可完成 | 0.6.0 |
| S6 | 第 11–12 周 | 项目实践与进度可视化 | 完成 1 个项目清单，进度页看到按证据来源分列的掌握度与通过率 | 0.7.0 |
| S7 | 第 13–14 周 | 打磨、可观测性与开源准备 | 隐私导出删除、可访问性达标、CI 通过、安全代码执行方案评估文档 | 0.8.0 |

八个功能需求全部有归属，一条不删（PRD 模块编号 1–8 不随 Sprint 编号变化）：

1. 能力诊断（模块 1）-> S1：20 题诊断，只授予 L1 与 L2，结论写明"这是学习起点评估，不是能力认证"。
2. 个性化学习路线（模块 2）-> S1 + S2：S1 交付技能阶段级学习建议与不落库的计划预览（不写任何计划行），S2 建 study_plan_items 并交付满足 R1–R6 的规则化周计划与幂等重生成。
3. 编程知识学习（模块 3）-> S2：3–5 节最小课程 + 进度与掌握度记录。
4. 在线代码练习（模块 4）-> S3：5–10 道练习 + static_rule 判题 + 三列可写/三生成列（verification_strength、used_ai、passed_with_ai）。
5. AI 导师（模块 5）-> S4：流式调用链 + 四级提示依赖开放 + has_prompt_dependency 查询派生。
6. 错题本与定时复习（模块 6）-> S5：1/3/7/14/30 阶梯复习回到今日页可完成。
7. GitHub 项目实践（模块 7）-> S6：3 个项目模板与清单校验。
8. 学习进度可视化（模块 8）-> S6：4 个区块 + 掌握度按证据来源分列。

## 4. S1：用户档案与能力诊断

**目标**：建立单用户学习档案，跑通能力诊断闭环，产出 6 个技能域的按证据分级结果（诊断只授 L1 与 L2），让用户看到"真实起点"而不是自我感觉；同时落学习时间档案并按等级输出技能阶段级学习建议，使"每周可投入多少时间"成为可查询的数据。Sprint 1A 的对外成果固定为四步：填学习档案 -> 完成 20 题诊断 -> 看到按证据分级的六域结果 -> 看到技能阶段级学习建议（advice）。

**功能范围**：

- 单用户初始化：种子写入 users 1 行与 user_profiles 1 行，不做注册、登录、找回密码。
- 能力诊断 20 题（单选 12、代码阅读 5、改错 3），可中断续答，未提交的作答只存浏览器。
- 评分规则化：按题号与得分映射到 6 个技能域的等级，不调用 AI。初步诊断只能授予 L1 与 L2，永不授予 L3/L4；诊断输出必须写明"这是学习起点评估，不是能力认证"。
- 等级定义（全局唯一口径）：

| 等级 | 定义 | 授予来源 |
|---|---|---|
| L0 未评估 | 该域从无任何评估记录（unassessed），或参加过诊断但该域正确率 < 60%（assessed_below_threshold）。系统默认值，不得推测 | 无证据来源，level=0 且 evidence_strength='none' |
| L1 认识概念 | 能选出正确选项，不能独立写代码 | 诊断该域正确率 >= 60%（tier 1，evidence_kind='diagnostic'） |
| L2 能跟做 | 能照着示例改出可运行代码 | 同 tier 1 内更新的诊断 >= 85%；或 tier 2 的 static_rule 练习通过（evidence_kind='practice'） |
| L3 能独立完成 | 该域 >= 3 次不同题目的真实执行通过 | 需 tier 3 证据（verification_method in ('runtime_test','manual_review')）且每次 ai_assistance_level='none'；Sprint 1–3 不可达 |
| L4 能迁移应用 | 已满足 L3，且 >= 1 次 exercise.kind='transfer' 的迁移任务通过（同样 none 且 tier 3） | 界面状态恒为 pending_review（不落库）；落库为 1 行 level=0 且 assessment_state='requested_verification'，等级停在已建立的 L3；MVP 无代码执行证据，不自动 confirmed |

- 四种证据来源必须分开记录（self_assessment 用户自评 / diagnostic 初步诊断 / practice 练习 / transfer 迁移）。user_skill_levels 为追加式历史（不设唯一约束），字段定稿：level smallint NOT NULL CHECK 0–4；evidence_kind varchar(16) NOT NULL CHECK in ('self_assessment','diagnostic','practice','transfer')（原 source 列改名）；verification_method varchar(16) NOT NULL CHECK in ('none','self_report','static_rule','runtime_test','manual_review')；evidence_strength varchar(16) GENERATED ALWAYS AS (CASE WHEN verification_method IN ('runtime_test','manual_review') THEN 'verified' WHEN verification_method='static_rule' THEN 'assessed' WHEN verification_method='self_report' THEN 'self_reported' ELSE 'none' END) STORED；assessment_state varchar(24) NOT NULL CHECK in ('unassessed','assessed_below_threshold','established','requested_verification')；evidence_ref varchar(200) NULL（诊断写 'diag:<attempt_id>'，练习写 'sub:<submission_id>'）；evidence_count smallint NOT NULL default 0；created_at、updated_at。
- 证据分层（tier，数字越大越强）：tier 3 = verification_method in ('runtime_test','manual_review')；tier 2 = evidence_kind in ('practice','transfer') 且 verification_method='static_rule'；tier 1 = evidence_kind='diagnostic'；tier 0 = evidence_kind='self_assessment'。
- 当前等级解析规则（唯一口径）：只取 assessment_state='established' 的行，按 (tier DESC, created_at DESC, id DESC) 每域取第一条；requested_verification 行永不参与、永不作为展示等级。可执行 SQL：

```sql
SELECT DISTINCT ON (skill_id)
       skill_id, level, evidence_kind, evidence_strength, assessment_state
FROM  (SELECT *, CASE
         WHEN verification_method IN ('runtime_test','manual_review') THEN 3
         WHEN evidence_kind IN ('practice','transfer') AND verification_method = 'static_rule' THEN 2
         WHEN evidence_kind = 'diagnostic' THEN 1
         ELSE 0 END AS tier
       FROM user_skill_levels
       WHERE user_id = :user_id AND assessment_state = 'established') t
ORDER BY skill_id, tier DESC, created_at DESC, id DESC;
```

- 回退：某域无 established 行时展示 level=0，并取该域最新一条非 established 行的 state（unassessed / assessed_below_threshold / requested_verification）；完全无记录则为 unassessed。同层可升可降（同一 tier 内取最新），弱层永不覆盖强层。
- 硬规则：L0 有两态且界面文案必须不同——unassessed 显示"尚未评估"，assessed_below_threshold 显示"已测，未达 L1 门槛"；两者都不得显示为"能力弱"，也不得用相邻域、平均分或问卷观感推测；assessed_below_threshold 的 evidence_ref 指向该诊断批次。
- 硬规则：evidence_strength='none' 只允许出现在 level=0 的行上（用 CHECK 表达）；诊断得分通过（>= 60% / >= 85%）只证明客观题答对，不等于代码能力经过验证，evidence_strength 只能是 'assessed'，不得写 'verified'。
- 诊断结果：每个域显示等级、证据来源、依据题目、下一步建议；未完成诊断时访问 /learn 显示引导态，不展示课程。
- 用户自评只能到 L2；用户自选 L3/L4 时不写等级，只新增 1 行 evidence_kind='self_assessment'、level=0、assessment_state='requested_verification' 的申请记录，并提示需要实践证据。Sprint 1–3 期间任何域都不得自动出现 L3 或 L4，L3/L4 只能以 requested_verification（用户申请）存在。
- 学习时间档案：user_profiles.study_days smallint[] NOT NULL DEFAULT '{1,3,5}'，允许 1–7 天（取消 5 天上限）；约束三条：CHECK (cardinality(study_days) BETWEEN 1 AND 7)、CHECK (study_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[])、NOT NULL（非空）；元素去重 CHECK 无法表达，改由 BEFORE INSERT OR UPDATE 触发器 trg_user_profiles_study_days_unique 检查并 raise exception，服务层同时校验。daily_minutes smallint NOT NULL default 60（CHECK 15–480）；weekly_minutes 保持生成列 = cardinality(study_days) * daily_minutes（上限 7x480=3360）。
- 时区边界：users.timezone varchar(64) NOT NULL default 'Asia/Shanghai' 保留，新增 timezone_source varchar(16) NOT NULL default 'default' CHECK in ('default','user_confirmed')；timezone_source='default' 时前端必须在档案页要求用户显式确认，未确认前不得展示"今日/本周"相关推导，确认后写 'user_confirmed'。所有"今天/本周"计算只用 users.timezone，禁止使用服务器时区。
- 技能阶段级学习建议（advice）：按六域等级与 study_days/daily_minutes 输出每域下一阶段建议（阶段名、建议投入、依据等级与证据），只读、不落库。
- 计划预览（内存计算、不落库）：可展示"本周 3 天 / 每天 60 分钟 / 建议投入阶段 1"这类推导，但不得产生带 target_id 的行。Sprint 1 不创建 study_plan_items 表、不写入任何计划行；该表设计保留在 DATABASE.md 并标注"S2 建表"，R1–R6 六条时间规则与对应验收整体移入 Sprint 2。

**技术变更**：

- 数据库：迁移 0002_sprint1a_identity_diagnostics，只创建 5 张表 users、user_profiles、skills、diagnostic_attempts、user_skill_levels，并写入 6 行 skills 种子；不创建 study_plan_items（S2 建表）、lessons、exercises、submissions、mistakes、review_tasks、projects、ai_interactions、learning_progress。禁止任何 DROP / DELETE / down -v。
- 后端：新增 app/services 层（本 Sprint 首次引入）；路由 GET /api/v1/users/me、PUT /api/v1/users/me/profile、GET /api/v1/skills、POST /api/v1/diagnostics、GET /api/v1/study-plan/preview；统一错误响应体 {error:{code,message,details}, request_id} 在本 Sprint 落地（见 ARCHITECTURE.md 第 6.1 节）；app/services/skill_level.py 实现当前等级解析（唯一实现位置），app/services/advice.py 输出阶段级建议与不落库预览（不调用 AI，不写计划行）。
- 前端：(Today) 页接入诊断流程；lib/ 建立请求层与类型定义；新增表单、单选组、等级徽标组件；档案页学习时间设置（study_days 与 daily_minutes）与 timezone 显式确认；技能阶段级建议与计划预览区，标注"预览，Sprint 2 才落库"。

**本 Sprint 交付项（Sprint 1A 结束必须存在）**：

- docs/SPRINT1A_CONTRACT.md：契约 v2 冻结口径（能力等级证据分层、L0 两态、六种情况表 v2、诊断批次、幂等规则、时区边界、迁移草案、示例 API）。
- docs/reports/SPRINT1A_DECISIONS.md：本轮全部决策与逐条理由。
- docs/reports/SPRINT1A_TEST_RESULTS.md：约束测试清单的执行记录（用例清单见 DATABASE.md 第 4.2 节 user_profiles，逐条给出期望与实际输出）。

**验收条件**：

- **AC-S1-01** 提交诊断后 3 秒内返回 6 条记录，每条含 skill_code、level（0–4）、evidence_kind、evidence_strength、assessment_state；数据库中 user_skill_levels 新增行数等于 6。
- **AC-S1-02** 答到第 10 题刷新页面，前 10 题作答仍在；浏览器清除存储后归零，且不产生服务端数据。
- **AC-S1-03** 用同一份答案连续提交两次，user_skill_levels 新增 12 行而非 6 行，最早 6 行内容不变（验证追加式历史）。
- **AC-S1-04** 未完成诊断直接访问 /learn，页面显示引导且不发起课程数据请求（网络面板只有 health 与 ready）。
- **AC-S1-05** 空库执行 alembic upgrade head 成功，skills 表恰好 6 行且 level 全为 domain。
- **AC-S1-06** 提交越界题号返回 422，响应体符合统一错误体结构，request_id 与后端日志一致。
- **AC-S1-07** 断网或未配置密钥时诊断仍可完成；后端无任何 DeepSeek 调用（代码搜索无相关导入）。
- **AC-S1-08** 20 题全部答对时 6 个域最高只到 L2，user_skill_levels 无任何 level >= 3 且 assessment_state='established' 的行；结论页含原文"这是学习起点评估，不是能力认证"。
- **AC-S1-09** 自评选择 L3 或 L4 时展示等级不变，只新增 1 行 evidence_kind='self_assessment'、level=0、assessment_state='requested_verification' 的记录，并提示需要实践证据。**（当前状态：延期至 Sprint 3——提交源码中不存在该交互入口，见本节验收核对表与已知限制）**
- **AC-S1-10** L0 两态可区分：无任何记录的域 level=0 且 assessment_state='unassessed'；诊断正确率 < 60% 的域 level=0 且 assessment_state='assessed_below_threshold'、evidence_ref 指向该批次；两态界面文案分别为"尚未评估"与"已测，未达 L1 门槛"，均不出现"能力弱"。
- **AC-S1-11** 诊断批次可追溯：一次提交恰好新增 1 行 diagnostic_attempts（question_set_version、rule_version、answers、domain_scores 非空，total_questions=20、total_correct 与 domain_scores 一致），本次写入的 6 行 user_skill_levels 的 evidence_ref 都等于 'diag:<attempt_id>'。
- **AC-S1-12** 重复诊断追加：同一份答案连续提交两次，diagnostic_attempts 新增 2 行且 attempt_id 不同、最早行内容不变；user_skill_levels 新增 12 行（不覆盖），展示等级按解析规则在 tier DESC 内取最新。
- **AC-S1-13** timezone 确认：新建用户 timezone_source='default'，档案页在确认前不展示"今日/本周"推导；PUT /api/v1/users/me/profile 带 timezone_confirmed=true 后 timezone_source='user_confirmed'。
- **AC-S1-14** study_days 约束与去重：{}、{1,1}、{8}、{0} 均被拒绝（{1,1} 由触发器 trg_user_profiles_study_days_unique 拒绝）；{1,2,3,4,5,6,7} 与 {1,3,5} 通过；daily_minutes=10 与 481 被拒绝；weekly_minutes 为生成列，直接写入被拒绝。
- **AC-S1-15** 计划预览不落库：GET /api/v1/study-plan/preview 返回 computed=true、persisted=false 与 days、note，且数据库不存在 study_plan_items 表（to_regclass('study_plan_items') 为 NULL）。
- **AC-S1-16** L3/L4 不可自动授予：任意诊断与 static_rule 组合下 user_skill_levels 不存在 assessment_state='established' 且 level >= 3 的行；L3/L4 只能以 assessment_state='requested_verification' 存在。
- **AC-S1-17** 约束测试清单为 S1 可验收交付：docs/reports/SPRINT1A_TEST_RESULTS.md 逐条记录 DATABASE.md 第 4.2 节的约束用例（通过/拒绝 + 实际输出），含 evidence_strength='none' 只允许出现在 level=0 行上的 CHECK 用例。
- **AC-S1-18** 等级解析唯一口径：只取 established 行按 (tier DESC, created_at DESC, id DESC) 每域取第一条；requested_verification 行不参与展示；弱层不覆盖强层（已有 tier 2 的 practice 行时，新提交的 tier 1 诊断不改变展示等级与 evidence_kind）。

**Sprint 1 验收核对表（逐条状态与证据，禁止虚报通过）**

状态只有三种：**完成**（有测试名或可重跑命令作为证据）/ **延期**（本轮未交付，明确归属后续 Sprint 或记为待办）/ **不适用**（口径已被取代）。证据可以是 pytest 用例名或一条可复制执行的命令；「已完成」不得只靠自述。

| 验收编号 | 状态 | 证据（测试名或命令） |
|---|---|---|
| AC-S1-01 | 完成 | `test_diagnostics_api.py::test_05_submit_writes_one_attempt_and_six_evidence_rows`、`::test_06_domain_levels_follow_thresholds`（响应 6 个域，库内新增 6 行） |
| AC-S1-02 | 完成（人工证据） | `apps/web/src/lib/diagnostic-draft.ts`（localStorage 草稿读写 + `ensureAttemptToken`）；浏览器「答 2 题后刷新仍为已答 2/20」记录见 SPRINT1B_TEST_RESULTS.md 第 5 节；无自动化用例 |
| AC-S1-03 | 完成（口径更新） | `test_diagnostics_api.py::test_08_new_token_appends_history_without_rewriting`（新 token 追加 6 行、旧行不动）；同 token 同内容 200 回放且零新增见 `test_diagnostics_idempotency.py::test_identical_retry_replays_200_and_appends_no_rows`。原「同答案两次 → 12 行」按两个不同 attempt_token 计（SPRINT1A_CONTRACT.md §6.11） |
| AC-S1-04 | 完成（人工证据） | `apps/web/src/app/learn/learn-view.tsx`：六域全部非 established → 引导态，已诊断 → 显示真实等级与状态文案。与 AC 原文的偏差已登记：本页除 health/ready 外还需一次 `GET /api/v1/users/me`（判定诊断状态所必需），其余不请求任何课程/题面数据。前端无测试运行器，证据为源码 + 浏览器可复核步骤 |
| AC-S1-05 | 完成 | `test_migrations.py::test_01_alembic_upgrade_head_succeeds_and_reports_head`、`::test_03_skills_seed_is_exactly_six_domains` |
| AC-S1-06 | 完成（证据有缺口） | 校验实现 `app/services/diagnostics.py::_validate_answers`（`question_set_mismatch` + 422）；统一错误体用例 `test_api_errors.py::test_body_shape_errors_use_the_same_envelope`；**缺**「越界题号」专门用例，已列入本节风险 |
| AC-S1-07 | 完成 | `grep -rn 'deepseek\|openai' apps/api/app --include=*.py` → 仅 `app/core/config.py` 的 5 处配置项，无客户端与网络调用 |
| AC-S1-08 | 完成 | `test_scoring.py::test_level_for_never_returns_l3_or_l4`、`::test_score_answers_is_deterministic_and_caps_at_l2`；固定文案 `apps/web/src/app/result/page.tsx:15` |
| AC-S1-09 | **延期至 Sprint 3** | `grep -rn requested_verification apps/web/src` 只命中读取侧（`skill-card.tsx`、`plan-view.tsx`、`labels.ts`、`contract.ts`），提交源码中没有自评 L3/L4 的交互入口，也没有写入申请行的调用；不得声称该条通过 |
| AC-S1-10 | 完成 | `test_diagnostics_api.py::test_09_two_kinds_of_l0_are_distinguishable`；文案 `apps/web/src/lib/labels.ts:29-30`（「尚未评估」/「已测，未达 L1 门槛」） |
| AC-S1-11 | 完成 | `test_diagnostics_api.py::test_05_…`：1 行批次 + 6 行 `evidence_ref='diag:<attempt_id>'`，`total_questions=20`、`total_correct` 与 `domain_scores` 一致 |
| AC-S1-12 | 完成 | `test_diagnostics_api.py::test_08_new_token_appends_history_without_rewriting`、`::test_10_higher_tier_evidence_is_not_overwritten`；同 token 换内容不新建批次见 `test_diagnostics_idempotency.py::test_same_token_with_different_answers_is_409` |
| AC-S1-13 | 完成 | `test_profile_constraints.py::test_12_timezone_confirmation_and_study_days_semantics`；`test_study_plan_preview.py::test_13_preview_covers_both_timezone_states_and_persists_nothing` |
| AC-S1-14 | 完成 | `test_profile_constraints.py::test_04_study_days_rejected_by_database_constraints`、`::test_04b_study_days_rejected_by_api_with_422` |
| AC-S1-15 | 完成 | `test_study_plan_preview.py::test_13_…`（含 `to_regclass('public.study_plan_items')` 为 NULL）；`test_migrations.py:163` 断言该表不在表清单内 |
| AC-S1-16 | 完成 | `test_scoring.py::test_level_for_never_returns_l3_or_l4`、`::test_score_answers_is_deterministic_and_caps_at_l2`、`test_diagnostics_api.py::test_06_domain_levels_follow_thresholds` |
| AC-S1-17 | **延期** | docs/reports/SPRINT1A_TEST_RESULTS.md 没有 C1–C17 的逐条「输入 → 期望 → 实际输出」记录（其第 6 节自述「约束测试清单…已冻结为 S1 实施时的验收项」）；现有自动化仅覆盖子集（C1–C8 见 `test_profile_constraints.py`），C9–C17 缺逐条执行记录 |
| AC-S1-18 | 完成 | `test_diagnostics_api.py::test_10_higher_tier_evidence_is_not_overwritten`；解析实现唯一位置 `apps/api/app/services/levels.py` |

**统计：完成 16 条（其中 AC-S1-02、AC-S1-04 为人工证据，AC-S1-03 口径更新，AC-S1-06 证据有缺口）、延期 2 条（AC-S1-09、AC-S1-17）、不适用 0 条。合计 18 条。**
**结论：Sprint 1 未全部通过验收**——任何对外材料不得写「AC-S1-01..18 全部通过」。两条延期的归属：AC-S1-09 延期至 Sprint 3（自评 L3/L4 申请入口在提交源码中不存在）；AC-S1-17 待补 C9–C17 的逐条「输入 → 期望 → 实际输出」约束执行记录。

**风险与前置依赖**：

- 前置：DATABASE.md 第 4.1 节的 users 字段定稿；若 email 字段在实施中被移除，需要一次迁移并回写文档。
- 风险：20 题覆盖 6 个域可能不足，评分规则主观。缓解：评分规则写成可复核的映射表，S1 结束前用 5 名目标用户内测，必要时调整题量并同步 PRD.md 第 5.1 节。
- 风险：诊断结果与后续路线强绑定，若规则变更会导致已有等级不可比。缓解：规则表带版本号，写入等级时保存规则版本。
- 风险：S1 只做建议与预览，用户可能误以为计划已生成。缓解：预览接口固定返回 persisted=false 并在界面标注"Sprint 2 才落库"；study_plan_items 不在 0002 迁移内，验收用 to_regclass 确认其不存在。
- 风险：static_rule 通过与真实运行结果被混为一谈，导致等级虚高。缓解：提交入库即带 verification_method 与派生 verification_strength，界面只写"静态规则检查通过"，Sprint 1–3 期间任何域都不得自动出现 L3/L4。

## 5. S2：学习路线与课程内容（最小课程）

**目标**：把诊断结果变成可执行的每周计划，并交付最小课程集（3–5 节），跑通"看课程 -> 记录进度 -> 生成下一次周计划"的可演示闭环；本轮数量让位于闭环完整性，不要求一次做 60 节课。

**功能范围**：

- 建表与承接：study_plan_items 在本 Sprint 建表（表设计见 DATABASE.md 第 4.14 节；S1 只保留设计、不建表、不写行）；六条时间规则 R1–R6 自 S1 整体移入本 Sprint，验收一并移入。
  - R1 时间不超支：同一 plan_date 的 sum(planned_minutes) <= user_profiles.daily_minutes。
  - R2 不强制每天：一周内 distinct(plan_date) 数 <= cardinality(study_days)，且每个 plan_date 必须属于 study_days；非学习日不分配任何计划项（见第 4 节时区边界条）。候选日期恒为 study_days ∩ [today_local, week_end]（today_local 按 users.timezone 计算）：**不得给已过去的日期新增 scheduled 任务**；已过去日期上的 done/skipped 历史行保持原样、不参与本次排期。
  - R3 跳过学习日：某日任务置 skipped 后不自动顺延到次日；跳过不写 mistakes、不计失败；skipped 与 done 同为终态，任何路径都不得改回 scheduled。
  - R4 幂等：同一 (user_id, week_start) 重复生成记录数不变（uq_study_plan_items_dedupe）；只允许更新 status='scheduled' 的行；**done / skipped 是终态**，任何路径（重生成、受控复活、课程完成同步）都不得改写其 status 与 updated_at；不得删除历史行。`expired` 行可在同一 dedupe_key 上受控复活为 scheduled，但**仅允许由「重新生成」触发**，且 `EXPIRE_STALE_ITEMS` 的 keep 集合必须与本周目标集合一致，不得保留 expired 键。
  - R5 可解释：每条任务必须有 rationale（例："L2 + 周一可用 60 分钟 -> 1 节课 25 分钟 + 1 道练习 20 分钟"），UI 可展开。
  - R6 时区：week_start 与 plan_date 按 users.timezone 以用户本地日历计算并落库为 date；前端不判断"今天"。
- 规则化周计划生成（不调用 AI）：按等级、study_days、daily_minutes 排出每周学习单元，写入 study_plan_items；重生成必须在单个事务内完成：读现有行 -> 计算目标集合 -> 按 dedupe_key UPSERT -> 不删除 done/skipped 行。不变量：(user_id, week_start) 维度的 count(*) 在重生成前后不变（同一输入）；done/skipped 行的 status 与 updated_at 不得被改写。
- **计划项状态机（唯一口径，Sprint 2 Patch）**：合法迁移只有 `scheduled → done`、`scheduled → skipped`；`expired → scheduled` 仅允许由「重新生成」触发（受控复活）；**`done` / `skipped` 是终态**，任何路径都不得改写（含重生成、复活、课程完成同步），也不得删除历史行。`PATCH /study-plan/items/{id}` 只接受 `done` / `skipped`（其它取值 422），对终态或 `expired` 行返回 409 `PLAN_ITEM_LOCKED`；**不存在「撤销」语义**，前端必须移除撤销按钮；终态行在 UI 上只读展示，不得呈现会失败的操作按钮。
- 今日待办**只调度真实 lesson**：Sprint 2 仅生成 kind='lesson' 的计划项，每项 target_id 必须指向 lessons 表中 status='published' 的真实课程，数量 0–3；**exercise 与 review 的任务数为 0**——不生成任何假 target、不写 study_plan_items 行、不消耗学习时长（planned_minutes 只计 lesson），S3 与 S5 各自接上真实内容后再开放对应类别。禁止任何"占位项/演示项"进入统计与 UI。
- 课程页：markdown 渲染、代码高亮与复制、自测问答折叠、掌握度标记（自评上限 L2）。**打开课程不写 learning_progress**：写入只由用户显式操作触发（开始学习 → in_progress、标记完成 → completed），"打开"不等于"完成"。停留时长自动累计与节流上报**未实现，延期至 Sprint 3**。
- **课程自评 ≠ 域等级验证（统一口径）**：课程自评取值**上限 L0–L2**（界面不提供 L3/L4 选项，服务端对 `self_assessment > 2` 返回 422），只写 learning_progress.mastery_level，界面标注"自评，未经验证"；它**永不写入 user_skill_levels**（既不写 established 等级，也不写 requested_verification 申请行）、**不得授予 L3/L4**、不作为任何域等级的展示依据；技能域等级的唯一来源仍是第 4 节的证据分层与解析 SQL。用户自评 L3/L4 的申请入口随 AC-S1-09 延期至 Sprint 3，S2 不提供该入口。
- 内容与导航：交付 3–5 节最小课程（路线 A 的 A1 阶段起步内容，每节 8–12 分钟），其余阶段标"开发中"；侧边导航五项（今日、学习、练习、项目、进度）可用。

**技术变更**：

- 数据库：迁移 0003_sprint2_lessons_and_plan，创建 study_plan_items、lessons、learning_progress；写入 3–5 行课程种子；study_plan_items 的生成只指向真实 lesson 的 target_id（S2 不写 exercise/review 行，这两类的 target 列保持 NULL 且不产生计划行）。
- 后端：路由 /api/v1/lessons、/api/v1/today；app/services/planning.py 增加周计划重生成入口（只覆盖 status='scheduled' 的行：done/skipped 不动，expired 仅在目标集合内受控复活）；learning_progress 前进式写入（not_started → in_progress → completed，回退 422 COURSE_PROGRESS_REGRESSION），课程 completed 在同一事务内把关联 scheduled 计划项置 done；停留计时与节流上报延期 Sprint 3。
- 前端：/learn 页面与课程组件；侧边导航与布局（240px 导航、1200px 内容区）；骨架屏组件；计划项按 status 渲染（终态只读、无撤销按钮），预算按 scheduled_minutes / history_minutes 分开展示。

**验收条件**：

- **AC-S2-01** 生成周计划后，今日待办只有 lesson 类、0–3 项且每项 target_id 指向已发布课程；exercise 与 review 的任务数为 0（`SELECT count(*) FROM study_plan_items WHERE kind IN ('exercise','review')` = 0）且不占用学习时长；同一 plan_date 的 sum(planned_minutes) <= daily_minutes（R1），且 plan_date 都落在 study_days 内（R2）。
- **AC-S2-02** 打开一节课程**不写入**：`GET /lessons/{id}` 前后 learning_progress 的行数、status、progress_pct、updated_at 全部不变；**打开不等于完成**，打开路径不得产生 status='in_progress' 或 status='completed' 的行，写入只发生在用户显式调用 `PUT /lessons/{id}/progress` 时。
- **AC-S2-03**（**未实现，延期至 Sprint 3，不计入 S2 已验收**）停留时长自动累计与节流上报本轮不做：原口径「课程页停留 60 秒，learning_progress.time_spent_seconds 增加 45 到 60 秒」不适用；前端不上报、后端不接受 time_spent_seconds 写入，该列保持 0 或历史值不变，界面也不展示停留时长。S2 验收只核对本条被标注为未实现，不得计为已通过。
- **AC-S2-04** 掌握度自评默认 L0（未评估），取值**上限 L0–L2**：界面不提供 L3/L4 选项，服务端对 `self_assessment > 2` 返回 422；learning_progress.mastery_level 记录自评值并标注"自评，未经验证"；该值只写 learning_progress，**永不写入 user_skill_levels 的任何行（含申请行）**，不作为技能域等级，也不授予 L3/L4（申请入口随 AC-S1-09 延期至 Sprint 3）。
- **AC-S2-05** 空库升级后 lessons 表 status='published' 的行数在 3 到 5 之间，且每行 estimated_minutes 在 1 到 240 之间。
- **AC-S2-06** 幂等三用例（R4 与不变量）：① 同一输入连续生成两次，该 (user_id, week_start) 维度的 study_plan_items count(*) 不变；② 把 1 项置 done 后重生成，该行 status 仍为 'done' 且 updated_at 未被改写；③ 把 1 项置 skipped 后重生成，该行 status 仍为 'skipped' 且 updated_at 未被改写。
- **AC-S2-07** 把某日任务置 skipped 后不顺延到次日、不写 mistakes、不计失败（R3）；连续跳过 3 天后今日页只出现一条可解释提示，不合并两天、不追加当日时长。
- **AC-S2-08** 每条任务 rationale 非空、含等级与当日可用时长，UI 可展开（R5）。
- **AC-S2-09** 把 users.timezone 改为 America/New_York 后重新生成，week_start 与 plan_date 按用户本地日历变化并落库为 date（R6）。
- **AC-S2-10** 周计划生成路径不调用 AI：生成前后 ai_interactions 行数不增加，后端代码搜索无 DeepSeek 调用导入。
- **AC-S2-11** S2 段闭环可演示：今日页打开 1 节课 -> learning_progress 写入进度 -> 重新生成周计划并把下一节课排进新的 plan_date，三步在同一次演示内完成；S3 的练习提交接入后构成完整闭环（课程 -> 练习 -> 记录进度 -> 生成下一次周计划）。
- **AC-S2-12** 练习提交路径的字段契约在本 Sprint 定稿并写入 DATABASE.md：submissions 只有 is_passed、verification_method、ai_assistance_level 三列可写，verification_strength、used_ai、passed_with_ai 为生成列（见第 6 节六种情况表 v2）；S2 内 ai_assistance_level 可达值只有 'none'。
- **AC-S2-13** 约束回归（用例与 S1 同一批，见 DATABASE.md 第 4.2 节 user_profiles）：{}、{1,1}、{8}、{0} 与 daily_minutes=10、481 均被拒绝；{1,2,3,4,5,6,7} 与 {1,3,5} 通过；weekly_minutes 为生成列，直接写入被拒绝。
- **AC-S2-14** 计划项终态不可改写、且不存在撤销：对 `scheduled` 行 PATCH `done` 与 `skipped` 各返回 200 且 updated_at 前进；对同一 `done` / `skipped` 行再次 PATCH 任意目标 status 返回 **409 `PLAN_ITEM_LOCKED`** 且库内 status/updated_at 不变；PATCH body 传 `scheduled` 或其它值返回 422（**先校验 body 再校验状态**：终态行收到非法 body 仍是 422）；重生成与课程完成同步之后，该行 status 与 updated_at 仍不变，`select count(*)` 不减（无删除）。前端代码中「撤销」按钮与撤销请求为 0 处，终态行只读、不渲染可点击的标记操作。
- **AC-S2-15** `expired` 只能受控复活：把一行置为 `expired` 后重新生成，若其 dedupe_key 属于本周目标集合，则同一行（同 id、同 dedupe_key）回到 `scheduled`，行数不变；若不属于目标集合，则保持 `expired`；`select count(*) from study_plan_items where status='expired' and (user_id, week_start, dedupe_key) in (本周目标集合)` 为 0（`EXPIRE_STALE_ITEMS` 的 keep 集合与目标集合一致，不保留 expired 键）；PATCH 无法把任何行写成 `scheduled`（422/409），复活路径只有生成。
- **AC-S2-16** 周中生成不排过去日期：把 `users.timezone` 定到 today_local 为本周中间某天（例如周三）后调用生成，`select count(*) from study_plan_items where status='scheduled' and plan_date < today_local` 为 0；新生成的 scheduled 行只落在 study_days ∩ [today_local, week_end]；已过去日期上的 `done` / `skipped` 历史行 status 与 updated_at 不变，且不参与本次排期（不因缺口而补排）。
- **AC-S2-17** 课程完成同步计划项 done（同一事务）：`PUT /lessons/{id}/progress` 且 `status='completed'` 返回 200 后，`study_plan_items` 中 `target_id=lesson_id` 且原 `status='scheduled'` 的行全部为 `done`，与进度响应在同一事务内可见；同一课程的 `done` / `skipped` / `expired` 行 status 与 updated_at 不变，不新增、不删除行；UI 同时展示课程真实完成状态（learning_progress.status）与计划项状态，并注明「计划完成不等于课程完成或能力等级」。
- **AC-S2-18** 课程进度只前进：`not_started → in_progress → completed` 均 200；相同状态重复提交幂等 200 且 completed_at 不变；`completed → not_started`、`completed → in_progress`、`in_progress → not_started` 一律 **422 `COURSE_PROGRESS_REGRESSION`**，同一请求前后库内 status、progress_pct、updated_at、completed_at 完全不变（无写入）；progress_pct 单调不减，status='completed' 时恒为 100，completed_at 只在首次完成写入且之后不回退不清空。
- **AC-S2-19** 预算口径历史与待执行分离：`GET /api/v1/study-plan` 的每个 `days[]` 元素同时给出 `scheduled_minutes`、`history_minutes`、`total_minutes`，顶层给出 `scheduled_items` 与 `history_items`；断言 `scheduled_minutes` = 该日 scheduled 行 planned_minutes 之和、`history_minutes` = 该日 done+skipped 之和、`total_minutes = scheduled_minutes + history_minutes` 且 `total_minutes <= daily_minutes`（expired 不计入任何一项）；前端两个数字分开展示，历史量不进入「待执行」。

**风险与前置依赖**：

- 前置：S1 的技能域、按证据分级的等级与时间档案（含 timezone_source 确认）；study_plan_items 表与 R1–R6 在本 Sprint 建立并实现。
- 风险：内容产能是最大风险（旧排期把两周内容工作量估为数十节课程）。缓解：本轮最小交付定为 3–5 节，每节配 1 个课程内自测（不生成 exercise 计划项、不占学习时长）；数量扩展在闭环通过后按 PRD 排期，不占用验收条件。
- 风险：掌握度由用户自选，可能虚高。缓解：自评上限 L2，只写 learning_progress 并标注"自评，未经验证"，永不进入 user_skill_levels、不授予 L3/L4（见"课程自评 ≠ 域等级验证"）；进度页分开展示掌握度与练习证据数（PRD.md 模块 8 验收要点）。
- 风险：周计划与复习任务争抢同一日预算，且时区导致"今日"错位。缓解：预算只在 app/services/planning.py 一处校验，S5 的复习项也写 study_plan_items 的 kind='review'；日期一律按 users.timezone 计算。
- 风险：停留计时延期 Sprint 3，用户可能误以为时长已累计。缓解：AC-S2-03 明确标注未实现，界面不展示停留时长、不出现自动计时文案，打开课程不写库；补实现前不得把它计为已验收。

## 6. S3：练习与判题

**目标**：打通练习提交与判题（不执行用户代码），把"是否真的跑过、是否借助 AI 通过"变成可查询的数据；本 Sprint 的 ai_assistance_level 唯一可达值为 'none'，hint、partial_code、full_answer 三级在 S4 开放。

**功能范围**：

- 练习页：题目、起始代码、自检用例展示（隐藏用例不下发）、代码编辑区、运行输出粘贴区。
- 判题三种来源：self_check、static_rule、manual；界面文案禁止"已通过自动测试""实时运行结果"，统一用"静态规则检查通过""自检记录"，未实际执行的代码不得宣称通过真实自动测试。self_check 只代表用户自检结论，系统无法验证代码是否真的运行；static_rule 只代表静态规则检查（必须/禁止出现的语法结构 + 输出文本比对），不等于代码真实运行通过；用户粘贴的 run_output_text 不构成"代码确实运行过"的证明。
- submissions 只有三列可写：is_passed、verification_method、ai_assistance_level；verification_strength、used_ai、passed_with_ai 为 PostgreSQL 生成列：verification_strength GENERATED ALWAYS AS (CASE WHEN verification_method IN ('runtime_test','manual_review') THEN 'verified' WHEN verification_method='static_rule' THEN 'assessed' WHEN verification_method='self_report' THEN 'self_reported' ELSE 'none' END) STORED；used_ai GENERATED ALWAYS AS (ai_assistance_level <> 'none') STORED；passed_with_ai GENERATED ALWAYS AS (is_passed IS TRUE AND ai_assistance_level <> 'none') STORED。has_prompt_dependency 不落库，改为查询派生（EXISTS ai_interactions），S4 落地。
- is_passed boolean NULL：只表示可判定的结论。static_rule 判定通过=true；判定失败或用户确认未通过=false；无法判定=NULL。
- verification_method varchar(16) NOT NULL default 'none'，取值与判定来源严格对应：'static_rule' = judging_mode='static_rule'（静态规则检查：必须/禁止出现的语法结构 + 输出文本比对）；'self_report' = judging_mode='self_check' 且用户确认了自检结论（系统无法验证代码是否真的运行）；'none' = judging_mode='manual'，或自检未提供可核对的运行输出/未确认；'runtime_test' 与 'manual_review' 需真实执行或人工复核，Sprint 1–3 不产生。原 verification_status 列删除，由 verification_method 与派生列 verification_strength 取代；static_rule 只能产出 verification_strength='assessed'，不得授予 L3/L4。
- ai_assistance_level varchar(16) NOT NULL default 'none'，CHECK in ('none','hint','partial_code','full_answer')；写入值 = max(用户自报等级, 本次关联 ai_interactions 的 dependency_level)，按 none < hint < partial_code < full_answer 取最大。S3 尚无 ai_interactions，本 Sprint 唯一可达值为 'none'。
- 等级授予（契约保留，Sprint 1–3 不可达）：L3 = 该域 >= 3 次不同题目的真实执行通过，每次 ai_assistance_level='none' 且 verification_method in ('runtime_test','manual_review')（tier 3）；L4 = 满足 L3 且 >= 1 次 exercise.kind='transfer' 通过（同样 none 且 tier 3），状态一律 pending_review，不自动 confirmed。MVP 明确的等级上限：Sprint 1–3 期间任何域都不得自动出现 L3 或 L4，L3/L4 只能以 requested_verification 存在；static_rule 与 self_report 证据一律不计入 L3/L4。
- 提交历史：最近 10 次，每次显示判定来源与是否借助 AI 通过；未通过时同事务生成 mistakes 与 review_tasks（1 天后到期），S5 再展示。
- 内容：交付 5–10 道练习，其中至少 1 道 kind='transfer'。

六种情况表 v2（与 PRD、ARCHITECTURE、DATABASE、SPRINT1A_CONTRACT 逐字一致，提交路径按此表落值）：

| # | 情况 | is_passed | verification_method | verification_strength（生成列） | ai_assistance_level | used_ai（生成列） | passed_with_ai（生成列） | 可作 L3 证据 |
|---|---|---|---|---|---|---|---|---|
| 1 | 完全独立通过（静态规则） | true | static_rule | assessed | 'none' | false | false | 否 |
| 2 | 使用 hint 后通过 | true | static_rule | assessed | 'hint' | true | true | 否 |
| 3 | 使用 partial_code 后通过 | true | static_rule | assessed | 'partial_code' | true | true | 否 |
| 4 | 使用 full_answer 后通过 | true | static_rule | assessed | 'full_answer' | true | true | 否 |
| 5 | 练习未通过 | false | static_rule 或 self_report | assessed 或 self_reported | 任意 | 按等级 | false | 否 |
| 6 | 无法验证的自检结果 | NULL | none | none | 任意 | 按等级 | false | 否 |
| 7 | 真实执行通过（未来） | true | runtime_test 或 manual_review | verified | 任意 | 按等级 | 视等级 | 是（且需 none） |

两条硬约束：static_rule 只能产出 verification_strength='assessed'，不得授予 L3/L4；verification_strength<>'verified' 的记录不得计为"已验证通过"，也不得计入任何掌握度或 L3 证据；MVP（Sprint 1–3）期间任何域都不得自动出现 L3 或 L4，L3/L4 只能以 requested_verification（用户申请）存在。

**技术变更**：

- 数据库：迁移 add practice tables，创建 exercises、exercise_test_cases、submissions（三列可写 + 三生成列）；不落 has_prompt_dependency 与 verification_status 列；ai_interactions.submission_id 外键在 S4 迁移中追加。
- 后端：app/services/judging.py（纯函数，不执行代码，不使用 subprocess）；提交接口；verification_method 与 ai_assistance_level 的派生写入；等级授予服务（L3/L4 判定，唯一实现位置，Sprint 1–3 恒返回不授予）。
- 前端：/practice 页面；代码编辑组件；提交校验（运行输出为空时禁用）；判定来源与 AI 依赖的展示（文案按本节禁止表述清单）。

**验收条件**：

- **AC-S3-01** 运行输出为空时前端提交按钮禁用并显示原因；绕过前端直接请求返回 422 且错误码 VALIDATION_ERROR。
- **AC-S3-02** 每次成功提交，submissions 行数恰好加 1，judging_mode 取值为 self_check、static_rule、manual 之一。
- **AC-S3-03** verification_strength 派生正确：verification_method='static_rule' 落 'assessed'；'self_report' 落 'self_reported'；'none' 落 'none'（三种提交各 1 行，逐行比对）。
- **AC-S3-04** is_passed 三值正确：static_rule 判定通过落 true；用户确认未通过落 false；无法验证落 NULL 且 verification_method='none'。
- **AC-S3-05** 六种情况表第 1 行：ai_assistance_level='none' 且 is_passed=true 时 used_ai=false、passed_with_ai=false；第 5 行：is_passed=false 时 passed_with_ai 恒为 false。
- **AC-S3-06** 用了 AI 的记录 passed_with_ai=true：手工写入 ai_assistance_level='hint' 且 is_passed=true 的提交（第 2 行），查询得 used_ai=true、passed_with_ai=true。
- **AC-S3-07** used_ai 与 passed_with_ai 为生成列：直接写入两列被数据库拒绝；不存在 ai_assistance_level<>'none' 且 is_passed=true 且 passed_with_ai=false 的行。
- **AC-S3-08** verification_strength<>'verified' 的记录不计入掌握度与 L3 证据：该域有 3 行 assessed 通过时等级仍停在 L2。
- **AC-S3-09** L3 不可达：同一道题通过 3 次时该域最高仍为 L2；换 3 道不同题各通过 1 次且每次 ai_assistance_level='none' 时等级仍为 L2，user_skill_levels 无 level >= 3 的 established 行（static_rule 只产 assessed）。
- **AC-S3-10** L4 不可达：用户申请 L4 只新增 assessment_state='requested_verification' 的记录，不写 level >= 4 的 established 行，不自动 confirmed。
- **AC-S3-11** 判题代码不导入 subprocess、os.system、exec、eval，也不执行 code_text（代码审查加静态搜索双重确认）。
- **AC-S3-12** 提交超过 20000 字符的代码返回 422，且不写库。
- **AC-S3-13** 判题未通过时，同一次事务内新增 1 条 mistakes 与 1 条 review_tasks，后者 interval_days=1 且 scheduled_for 约等于当前时间加 1 天；人为让 mistakes 插入失败时 submissions 一起回滚。
- **AC-S3-14** 空库升级后 exercises 表 status='published' 的行数在 5 到 10 之间，其中 kind='transfer' 至少 1 行；页面文案与构建产物搜索"已通过自动测试""实时运行结果"0 命中。

**风险与前置依赖**：

- 前置：S2 的课程与技能域、S2 定稿的 submissions 字段契约；DATABASE.md 第 4.8 节约束定稿。
- 风险：static_rule 误判会伤害信任。缓解：规则以"必须出现某结构"为主，禁止关键字为辅，命中即给出具体原因；误判时可人工改判（judging_mode 记录为 manual）。
- 风险：用户粘贴的运行输出无法验证真伪，且事务边界写错会让错题与提交不一致。缓解：界面提示"运行输出由你本人提供"，把"不宣称判题结果等于真实运行结果"写进已知局限；验收时人为让 mistakes 插入失败，确认 submissions 一起回滚。
- 风险：生成列让 submissions 只有三列可写，历史代码若仍写 used_ai 会直接报错。缓解：迁移与代码在同一批变更内更新，验收时用直接写列的方式验证拒绝。

## 7. S4：DeepSeek AI 导师与提示依赖记录

**目标**：打通 AI 导师调用链（含流式、超时、重试、降级），并让每一次求助成为可统计的提示依赖记录。这是本产品与"直接问 ChatGPT"的核心差异。顺序上练习先行：S3 已在 submissions 落下 ai_assistance_level 字段（唯一可达值 'none'），本 Sprint 才开放 hint、partial_code、full_answer 三级，让求助等级有真实提交可落。

**功能范围**：

- /api/v1/ai/tutor 流式接口，默认提示依赖等级为 hint。
- 四级提示依赖选择（none、hint、partial_code、full_answer），full_answer 需显式确认；ai_interactions.dependency_level 使用与 submissions 同一枚举、同一排序，NOT NULL。
- 每次调用写 ai_interactions（创建 pending、收尾回写状态与 token 与延迟），并通过 submission_id 关联本次提交。
- 提交时 ai_assistance_level 写入 = max(用户自报等级, 本次关联 ai_interactions 的 dependency_level)，按 none < hint < partial_code < full_answer 取最大。
- has_prompt_dependency 为查询派生（EXISTS ai_interactions），不落库。
- 失败降级：重试 2 次后返回错误，前端展示本地引导要点（来自 exercises.hints，不来自模型）。
- 前端对话组件：流式渲染、手动停止、错误态、未配置密钥时的明确提示。

**技术变更**：

- 数据库：迁移 add ai interactions，创建 ai_interactions（含 dependency_level 与 submission_id 外键）；不改 submissions 的列结构，三列可写与三生成列在 S3 已定稿。
- 后端：新增 app/services/ai_client.py（供应商适配器）与鉴权配置读取；日志增加 provider、model、prompt_chars、prompt_sha256_12 字段；提交事务内的依赖等级回填。
- 前端：新增对话组件与 SSE 解析工具；lib/ 增加流式请求封装。
- 配置：DEEPSEEK_MODEL 默认 deepseek-flash，DEEPSEEK_MODEL_COMPLEX 预留 deepseek-v4-pro；密钥只从环境变量读取。

**验收条件**：

- **AC-S4-01** 配置密钥后提问，10 秒内收到首个 delta 事件；整体 60 秒内结束或超时。
- **AC-S4-02** 每次调用恰好新增 1 行 ai_interactions；结束后 status 从 pending 变为 succeeded 或 failed 或 cancelled，且成功行含 prompt_tokens、completion_tokens、latency_ms；dependency_level 非空。
- **AC-S4-03** 移除 DEEPSEEK_API_KEY 后重启，health 返回 ai_configured=false，调用返回 503 且错误码 AI_UNAVAILABLE，练习与其他页面不受影响。
- **AC-S4-04** 上游连续返回 5xx 时，日志中同一 request_id 的尝试次数不超过 3（1 次原始 + 2 次重试），两次退避分别约 0.5s 与 1.5s。
- **AC-S4-05** hint 等级的回答至少包含 1 个问句或明确的下一步动作；单独输出完整代码的响应在审查中判为不通过。
- **AC-S4-06** 前端中途断开连接，该次记录 status='cancelled'，且不计入失败率。
- **AC-S4-07** 日志、数据库、前端构建产物中均不含密钥明文（三处搜索无命中）。
- **AC-S4-08** 四级等级落值取最大：用户自报 'hint' 而本次关联 ai_interactions 的 dependency_level='full_answer' 时，提交落 'full_answer'，verification_method 仍为 static_rule、verification_strength='assessed'，used_ai 与 passed_with_ai 随之为 true（六种情况表 v2 第 4 行）。
- **AC-S4-09** has_prompt_dependency 为查询派生：存在关联 ai_interactions 的提交接口返回 true，无关联返回 false，submissions 表不存在该列。
- **AC-S4-10** 使用 hint 或以上等级通过、verification_strength='assessed' 的记录不计入 L3 证据（六种情况表 v2 第 2–4 行）：某域有 3 次 hint 通过时等级仍为 L2，且不存在 level >= 3 的 established 行。

**风险与前置依赖**：

- 前置：S3 的 submissions 与 exercises；ARCHITECTURE.md 第 5 节的超时与重试参数定稿。
- 风险：DeepSeek 模型的默认名与复杂任务模型是否可用需要在接入前用真实密钥验证，若型号变化必须同步 ARCHITECTURE.md 第 5.1 节与 PRD.md 第 5.5 节。
- 风险：无密钥环境无法端到端测试，且流式响应的跨域与超时易与 ready 混淆。缓解：单元测试用本地 mock SSE 服务，验收时再用真实密钥跑一次并记录输出；AI 请求使用独立超时（60s），不复用默认 10s。
- 风险：提示依赖由用户自报，存在少报可能。缓解：dependency_level 与 submission 的 ai_assistance_level 双向校验（取最大值），少报时在进度页以"未声明的 AI 使用"提示，但不阻断。

## 8. S5：错题本与间隔复习

**目标**：让错题按固定间隔回到用户面前，把"学过就忘"变成可追踪的复习任务。

**功能范围**：

- 错题本页签：按技能域与状态筛选，已 resolved 默认折叠。
- 复习任务：1、3、7、14、30 天阶梯；失败回到 1 天；连续 3 次通过置为 resolved。
- 今日页复习区：只显示当日到期任务，可一键回到原练习；复习项同时写入 study_plan_items 的 kind='review'，受 R1 同日预算约束。
- 复习结果必填：通过或未通过；跳过则标记 skipped 并在 1 天后重来；跳过不写 mistakes、不计失败（R3）。

**技术变更**：

- 数据库：迁移 add mistakes and review tasks，创建 mistakes、review_tasks。
- 后端：app/services/review.py（间隔推进算法，唯一实现位置）；今日页聚合接口增加复习区。
- 前端：今日页复习区；错题本列表与筛选组件；空状态组件。

**验收条件**：

- **AC-S5-01** 连续完成 4 次复习均通过，review_tasks 的 interval_days 依次为 3、7、14、30（首次任务为 1）。
- **AC-S5-02** 任意一次复习选择未通过，下次任务的 scheduled_for 等于当前时间加 1 天，repetition_no 重置为 1。
- **AC-S5-03** 连续 3 次通过后 mistakes.status='resolved' 且 resolved_at 非空，之后不再生成该错题的新任务。
- **AC-S5-04** 用户时区为 Asia/Shanghai 时，scheduled_for 为次日 00:10 的任务不出现在今天的复习区。
- **AC-S5-05** 点击跳过，任务 status='skipped'；1 天后重新出现在复习区，且不顺延到次日的 plan_date、不写 mistakes、不计失败。
- **AC-S5-06** 复习区在无到期任务时显示空状态与下次到期时间，不显示 0 条与 0% 进度条。

**风险与前置依赖**：

- 前置：S3 生成 mistakes 与首个 review_tasks。
- 风险：时区与跨日边界是最常见缺陷。缓解：复习判定统一在服务层用 users.timezone 计算，前端不判断"今天"。
- 风险：间隔算法在两处实现导致漂移。缓解：只允许 app/services/review.py 实现，前端只展示。
- 风险：错题积压导致今日页过长。缓解：复习区最多展示 5 项，超出显示"还有 N 项"并在专属页处理。

## 9. S6：项目实践与进度可视化

**目标**：让用户产出一个可展示的 AI 应用，并在一个页面看到真实掌握度，而不是完成率幻觉。

**功能范围**：

- 3 个项目模板：命令行工具、RAG 知识库问答、简单 Agent 助手，各含不少于 6 条验收清单与不少于 3 个里程碑。
- 项目记录：仓库地址、演示地址、清单勾选、状态流转（planned、in_progress、blocked、done）。
- 进度页 4 个区块：掌握度分布、练习通过率与趋势、复习完成率、项目状态；每块标注统计区间与数据来源，掌握度按证据来源（self_assessment、diagnostic、practice、transfer）分列，level=0 的域显示"未评估"。
- 完成判定：清单全部通过才能置为 done。

**技术变更**：

- 数据库：迁移 add projects，创建 projects。
- 后端：聚合查询服务（4 至 6 条聚合查询并发，超时 3s）；项目状态校验接口；掌握度的证据溯源来自 user_skill_levels 的追加式历史。
- 前端：/projects 与 /progress 页面；徽标、表格、状态卡组件；不引入重量级图表库（首屏 JS 保持 250KB gzip 以内）。

**验收条件**：

- **AC-S6-01** 验收清单存在未通过项时尝试置为 done，后端返回 409 CONFLICT 且状态不变。
- **AC-S6-02** repo_url 或 demo_url 非 https 时保存返回 422，并指出具体字段。
- **AC-S6-03** 进度页 4 个区块各自显示统计区间与数据来源；无数据时显示"暂无数据"。
- **AC-S6-04** 进度页每个数字都能用文档给出的 SQL 复现，误差为 0（同一时间点）。
- **AC-S6-05** 掌握度与完成率分属不同区块，页面文案不出现"完成率=已掌握"的表述。
- **AC-S6-06** submissions 达到 1 万行时，进度页接口 p95 不超过 300ms。
- **AC-S6-07** 掌握度按证据来源分列：自评、诊断、实践、迁移四类各显示条数；level=0 的域显示"未评估"，不显示 0 分、"能力弱"或推荐等级。

**风险与前置依赖**：

- 前置：S1 至 S5 的数据积累；S1 的技能域定义与证据溯源字段。
- 风险：聚合查询随数据增长变慢。缓解：使用 submissions 的冗余列与索引，避免每次 JOIN ai_interactions。
- 风险：图表库体积超标。缓解：优先用 CSS 与内联 SVG 实现条形与分布，不引入图表库；若必须引入，需先证明首屏 JS 仍在 250KB gzip 以内。
- 风险：项目验收清单靠自报。缓解：verified_checks 记录每项校验时间与依据，进度页显示"自报通过"字样，不宣称第三方验证。

## 10. S7：打磨、可观测性与开源准备

**目标**：把首版从"能跑"提升到"可交付、可维护、可开源"，补齐隐私相关能力，并给出安全代码执行的方案评估（只评估，不实现）。

**功能范围**：

- 隐私：数据导出（JSON）与删除（仅删 AI 文本或删除全部数据两条路径）。
- 稳定性：5 个路由段全部有错误边界；axios/fetch 层统一超时；请求失败给 request_id。
- 可访问性：键盘走查全部页面，焦点环可见，axe 无 serious 级问题，对比度达标（已知例外见 DESIGN_SYSTEM.md）。
- 可观测性：结构化日志字段补全（provider、model、latency、dependency_level）；AI 调用成功率与 p95 延迟统计（仅本地端点）。
- CI：lint、pytest、空库迁移重放三项必过。
- 开源准备与安全评估：示例数据清理、无密钥提交、多行命令不依赖 shell 串联（Windows 兼容）；安全代码执行方案评估只产出评估文档，不安装、不实现任何沙箱（见 10.1）。

**技术变更**：

- 后端：隐私导出删除接口；指标端点（本地）；日志字段补全。
- 前端：全局错误边界与错误页组件；可访问性修复；加载骨架与空状态统一。
- 仓库：CI 配置；贡献说明与文档索引（由文档负责人交付，本 Sprint 只列依赖）；安全代码执行方案评估文档（docs 下新增，只含评估结论）。

**验收条件**：

- **AC-S7-01** 在 5 个路由段各注入一个抛错组件，页面显示错误态而不是白屏，且错误态包含 request_id。
- **AC-S7-02** axe 扫描 5 个页面 0 serious；Tab 键可到达全部交互元素且焦点环可见（截图对比）。
- **AC-S7-03** 导出 JSON 含 6 类数据（submissions、learning_progress、mistakes、review_tasks、projects、ai_interactions），且不含未脱敏文本与密钥。
- **AC-S7-04** 删除 AI 记录后 prompt_text 与 response_text 为空、redacted_at 非空，tokens 与 latency 统计字段保留。
- **AC-S7-05** CI 在空库执行 alembic upgrade head 成功；pytest 覆盖率不低于 70%；ESLint 0 error。
- **AC-S7-06** Lighthouse 移动端性能分不低于 90，首页首屏 JS 不超过 250KB gzip。
- **AC-S7-07** 安全代码执行方案评估文档存在（见 10.1），含四种方案对比与五个评估维度，且依赖清单无变更。

**风险与前置依赖**：

- 前置：S1 至 S6 全部完成；隐私接口路径在 S7 前定稿（见 DATABASE.md 第 9 节）。
- 风险：隐私功能与单用户形态的取舍。缓解：默认提供"仅删 AI 文本"的轻量路径，全量删除需二次确认。
- 风险：CI 依赖 Docker 服务在托管环境不可用。缓解：CI 用服务容器或本地 compose，二者选一并写入贡献说明。

### 10.1 安全代码执行方案评估

**目标**：在不引入任何运行时代码执行的前提下，给出首版之后接入真实执行的选型依据。**本轮不安装、不实现任何沙箱**，不新增依赖，不改 judging.py 的纯函数边界。

| 方案 | 隔离强度 | 资源限额能力 | 成本 | 运维复杂度 | 与现有 static_rule 的兼容路径 |
|---|---|---|---|---|---|
| 自建隔离容器 + 资源/网络限额 | 进程级隔离，依赖内核与限额配置 | CPU/内存/时长/网络可限额 | 中（复用现有 Docker 环境） | 高（镜像、限额、清理） | static_rule 先判，容器执行作为第二判据，judging_mode 扩一个枚举值 |
| gVisor 或 Firecracker 微虚机 | 强，内核或虚拟化层隔离 | 可限额，粒度细 | 高（宿主机能力要求） | 很高 | 同上，执行结果作为 verification_strength='verified'（verification_method='runtime_test'）的新来源 |
| 第三方判题 API | 由供应商承担 | 由供应商限额与计费 | 按调用计费，外部依赖 | 低 | 提交后异步回填 is_passed 与 verification_method，需新增状态流转 |
| WASM 沙箱（如 Pyodide） | 语言级沙箱，能力强但需裁剪标准库 | 内存与时长可限额，网络天然不可用 | 低 | 中（前端体积与加载时间） | 可复用现有输出文本比对，兼容度最高 |

**产出物**：安全代码执行方案评估文档（docs 下新增一份），四种方案逐一覆盖隔离强度、资源限额能力、成本、运维复杂度、与现有 static_rule 的兼容路径五个维度，并给出首版之后的推荐顺序与回滚路径。

**验收条件**：

- **AC-S7-08** 评估文档存在，四种方案与五个维度两两覆盖无空格；文档显式写明"本轮不安装、不实现任何沙箱"。
- **AC-S7-09** apps/api 与 apps/web 的依赖清单无变更，仓库内不存在沙箱相关依赖、镜像或运行配置（搜索 0 命中）。

## 11. 明确延后的事项

| 事项 | 延后原因 | 触发条件 | 预计阶段 |
|---|---|---|---|
| 真实代码执行沙箱（实现） | 安全边界与运维成本远超首版；本版只做方案评估（见 10.1） | 10.1 的评估文档通过并选定方案 | 首版之后 |
| 多用户认证体系 | 首版单用户本地使用 | 需要多人共用或对外开放 | 首版之后 |
| 对外部署 | 首版只在本地开发环境运行 | 首版通过 S7 验收 | 首版之后 |
| 智能推荐 | 单用户冷启动无数据意义 | 单实例交互超 10 万条且内容库超 500 节 | 不确定 |
| 前沿 AI 新闻与论文分析 | 与学习闭环无关，维护成本高 | 用户调研 30% 以上主动要求 | 不确定 |
| 移动端 App | 学习场景以桌面为主 | 移动端访问占比超过 40% | 不确定 |
| 支付与订阅 | 首版不收费 | 决定商业化 | 不确定 |
| 仓库与演示地址真实可访问性校验 | 涉及外部请求与凭据管理 | 定稿凭据方案 | S6 之后 |
| 异步任务队列 | 单用户数据量下同步足够 | 出现超过 3s 的同步请求 | S5 之后按需 |
| 内容多语言 | 首版只服务中文用户 | 出现非中文用户群 | 不确定 |
| 教材版本与规则版本 UI | 先内部记录版本号即可 | 规则变更影响已有等级可比性时 | S3 之后 |

延后不等于否决。任何一项进入范围，必须先更新 PRD.md 第 3.2 节、本文件与本 Sprint 的验收条件，再动代码。

## 12. 待确认事项

- 待确认：每个学习日时长是否允许逐日不同。当前 weekly_minutes = cardinality(study_days) * daily_minutes，逐日不同需要把 daily_minutes 换成按日记录；若确定要做，需先增表并重写 R1。
- 待确认：同层证据取最新会导致降级（诊断 70% 后再诊断 55%，等级从 2 回落到 1，见契约 A.6 第 4 行示例）。本轮按「同层取最新」执行；若改为同层不降级，需在 S2 前决策。
- 待确认：L4 的 pending_review 何时能转 confirmed。当前 MVP 没有可信的代码执行证据（verification_method 无法达到 'runtime_test'/'manual_review'），等待安全代码执行方案落地并有真实执行记录后再定。
- 待确认：每个 Sprint 2 周的节奏在内容生产上是否可行（S2 为 3–5 节课、S3 为 5–10 道练习，之后才扩展到 60 节与 150 道题）；若不可行，优先压缩内容数量而不是压缩验收条件。
- 待确认：static_rule 规则集由谁维护与版本化，规则变更后已有的 assessed 证据是否需要重算展示等级（static_rule 只产 assessed，不影响 L3/L4）。S3 前定稿。
- 待确认：has_prompt_dependency 的派生查询在数据量增长后是否需要索引或物化视图。S4 验收时测量 p95 后再定。
- 待确认：CI 的托管方式（自建 runner 或托管服务）。S7 前定稿，不阻塞前面 Sprint。
