# AI Learning Copilot Sprint 1A 可执行契约
**文档版本**：v2.0（Sprint 1A 冻结口径）
**契约性质**：可执行契约。字段、取值、SQL、DDL 与验收映射以本文档为准；PRD.md、ARCHITECTURE.md、DATABASE.md、ROADMAP.md 与本文件冲突时，先改本文件的冻结口径，再同步那四份，不允许只改一侧。
**读者**：Sprint 1B 实现者（后端、前端、数据库）、复核者
**上游文档**：PRD.md（做什么）、DATABASE.md（数据模型）、ARCHITECTURE.md（分层与接口）、ROADMAP.md（排期与验收）、DESIGN_SYSTEM.md（怎么呈现）

Sprint 1A 只冻结契约，不写业务代码，不执行迁移。术语唯一口径是六个词：evidence_kind、verification_method、verification_strength、assessment_state、tier、timezone_source；不使用"来源""判题来源""证据等级"等近义词。本文档每条断言都能用一条 SQL 或一次请求判定；出现"参见其他文档才能确定"的内容一律视为缺陷。
## 1. 范围与不变量
### 1.1 Sprint 1 的对外成果（固定四步）
| 步 | 成果 | 落库证据 |
|---|---|---|
| 1 | 填学习档案：study_days、daily_minutes、timezone 显式确认 | user_profiles 1 行；users.timezone_source='user_confirmed' |
| 2 | 完成 20 题诊断（单选 12、代码阅读 5、改错 3） | diagnostic_attempts 1 行，answers 含 20 个键 |
| 3 | 看到按证据分级的六域结果 | user_skill_levels 6 行，evidence_kind='diagnostic' |
| 4 | 看到技能阶段级学习建议（advice，规则化生成，不调 AI） | 由 6 行等级与 study_days 推导，不落库 |

"计划预览"是内存计算、不落库：可展示"本周 3 天 / 每天 60 分钟 / 建议投入阶段 1"这类推导，但不得产生带 target_id 的行（详见 §6.5）。
### 1.2 Sprint 1 不做什么
| 不做项 | 判定方式 |
|---|---|
| 不创建 study_plan_items，不写入任何计划行 | §7 的 CREATE TABLE 清单只有 5 张表；`select to_regclass('public.study_plan_items')` 返回 NULL |
| 不调用 AI | 后端无 DeepSeek 导入；未配置密钥时 `POST /api/v1/diagnostics` 仍返回 201 |
| 不执行用户代码 | 无执行器依赖；verification_method='runtime_test' 在 S1 不可达 |
| 不引入登录 | 无密码、会话、令牌字段与路由；users 只由种子写入 1 行 |
| 不建 lessons、exercises、submissions、mistakes、review_tasks、projects、ai_interactions、learning_progress | 同 CREATE TABLE 清单（§7.3） |
| 不做周计划落库与幂等 UPSERT 实现 | 只有 `GET /api/v1/study-plan/preview`，响应恒含 `persisted:false` |
| 不改已实现的 /api/v1/health 与 /api/v1/ready | 两个路由的响应结构不变 |

> **Sprint 2 状态更新**：上表是 Sprint 1 的范围声明。Sprint 2 起 study_plan_items / lessons / learning_progress 已建表并落地，周计划落库、计划项状态机、课程进度与课程完成同步改按 §6.12–§6.14 的冻结口径执行；仍成立的三条是：不调用 AI、不执行用户代码、不引入登录。
### 1.3 不变量
| 编号 | 断言 | 违反判定 |
|---|---|---|
| I1 | 展示等级只来自 assessment_state='established' 的行，按 §3.3 SQL 每域取一条 | 查询结果里出现 state='requested_verification' 的行被当作等级 |
| I2 | 某域无 established 行时展示 level=0，state 取该域最新一行的 state，无行则 'unassessed' | 无证据域显示 L1 以上，或显示"能力弱" |
| I3 | 同一 tier 内取最新（可升可降）；低 tier 永不覆盖高 tier | 展示等级来自 tier 更低的较新行 |
| I4 | evidence_strength='none' 只允许出现在 level=0 的行 | 存在 level>=1 且 evidence_strength='none' 的行 |
| I5 | Sprint 1–3 期间任何域都不得自动出现 L3 或 L4；L3/L4 只以 requested_verification 存在 | `select count(*) from user_skill_levels where level>=3 and assessment_state<>'requested_verification'` 不为 0 |
| I6 | 诊断得分通过不等于代码能力经过验证：诊断行的 evidence_strength 只能是 'assessed' | 存在 evidence_kind='diagnostic' 且 evidence_strength='verified' 的行 |
| I7 | 所有"今天/本周"只用 users.timezone 计算；timezone_source='default' 时不得展示今日/本周推导 | 未确认时区就渲染"今日/本周"数据 |
| I8 | 诊断批次追加式：同一份答案重复提交产生新的 diagnostic_attempts 行，不覆盖旧行 | 第二次提交后旧行的 created_at 或 level 变化 |
## 2. 实体与字段
S1 只有 5 张表。"生成列"一列写"是"表示该列由表达式算出、不可直接写入。
### 2.1 users
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigint | PK, identity | 主键 |
| display_name | varchar(80) | NOT NULL | 显示名 |
| timezone | varchar(64) | NOT NULL, default 'Asia/Shanghai' | "今天/本周"的唯一边界来源 |
| timezone_source | varchar(16) | NOT NULL, default 'default', CHECK in ('default','user_confirmed') | 时区是否经用户显式确认 |
| locale | varchar(16) | NOT NULL, default 'zh-CN' | 界面语言 |
| created_at / updated_at | timestamptz | NOT NULL, default now() | 时间戳 |
### 2.2 user_profiles
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| user_id | bigint | PK, FK → users(id) CASCADE | 与 users 一对一 |
| target_track | varchar(32) | NOT NULL, default 'route_a', CHECK in ('route_a') | 首版只支持路线 A |
| study_days | smallint[] | NOT NULL, default '{1,3,5}'；三条 CHECK + 1 个触发器（§2.6） | 学习日，1=周一…7=周日，允许 1–7 天 |
| daily_minutes | smallint | NOT NULL, default 60, CHECK 15–480 | 单个学习日可投入分钟数 |
| weekly_minutes | smallint | 生成列（是）：cardinality(study_days) * daily_minutes STORED | 周容量，唯一算法 |
| onboarding_completed_at | timestamptz | NULL | 档案与诊断完成时间 |
| created_at / updated_at | timestamptz | NOT NULL, default now() | 时间戳 |
### 2.3 skills
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigint | PK, identity | 主键 |
| code | varchar(64) | NOT NULL, UNIQUE | 稳定标识，如 route_a.a1 |
| name_zh | varchar(80) | NOT NULL | 中文名（A1–A6 共 6 行） |
| level | varchar(16) | NOT NULL, default 'domain', CHECK in ('domain','topic') | 首版只有 domain |
| route_code | varchar(32) | NOT NULL, default 'route_a' | 所属路线 |
| order_index | smallint | NOT NULL | 展示顺序，1–6 |
| description | text | NULL | 达标标准 |
### 2.4 diagnostic_attempts
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigint | PK, identity | 批次主键，即 evidence_ref 中的 attempt_id |
| user_id | bigint | NOT NULL, FK → users(id) CASCADE | 归属用户 |
| question_set_version | varchar(16) | NOT NULL | 题集版本，如 v1 |
| rule_version | varchar(16) | NOT NULL | 评分规则版本，如 r1 |
| answers | jsonb | NOT NULL | 20 题作答快照（§4.1） |
| domain_scores | jsonb | NOT NULL | 6 域得分快照（§4.2） |
| total_correct | smallint | NOT NULL, CHECK >= 0 | 总对题数 |
| total_questions | smallint | NOT NULL, CHECK > 0 | 总题数，S1 恒为 20 |
| submitted_at | timestamptz | NOT NULL, default now() | 提交时间 |
| created_at | timestamptz | NOT NULL, default now() | 落库时间 |
### 2.5 user_skill_levels
| 字段 | 类型 | 约束 | 说明 |
|---|---|---|---|
| id | bigint | PK, identity | 主键 |
| user_id | bigint | NOT NULL, FK → users(id) CASCADE | 归属用户 |
| skill_id | bigint | NOT NULL, FK → skills(id) RESTRICT | 技能域 |
| level | smallint | NOT NULL, CHECK 0–4 | 本行主张的等级 |
| evidence_kind | varchar(16) | NOT NULL, CHECK in ('self_assessment','diagnostic','practice','transfer') | 证据来源（原 source 列改名） |
| verification_method | varchar(16) | NOT NULL, CHECK in ('none','self_report','static_rule','runtime_test','manual_review') | 本行证据是怎么来的 |
| evidence_strength | varchar(16) | 生成列（是）：CASE WHEN verification_method IN ('runtime_test','manual_review') THEN 'verified' WHEN verification_method='static_rule' THEN 'assessed' WHEN verification_method='self_report' THEN 'self_reported' ELSE 'none' END STORED | 证据强度，不可直写 |
| assessment_state | varchar(24) | NOT NULL, CHECK in ('unassessed','assessed_below_threshold','established','requested_verification') | 本行的状态（§3.2） |
| evidence_ref | varchar(200) | NULL | diag:<attempt_id> 或 sub:<submission_id>（§4.3） |
| evidence_count | smallint | NOT NULL, default 0, CHECK >= 0 | 支撑该行的题数或练习数 |
| created_at / updated_at | timestamptz | NOT NULL, default now() | created_at 参与 §3.3 排序 |

- 索引：`ix_user_skill_levels_user_skill`（user_id, skill_id, created_at DESC）；不建 (user_id, skill_id) 唯一约束——本表是追加式历史表；交叉约束：`ck_usk_strength_none_level0 CHECK (evidence_strength <> 'none' OR level = 0)`；`ck_usk_state_level CHECK ((assessment_state IN ('unassessed','assessed_below_threshold','requested_verification') AND level = 0) OR (assessment_state = 'established' AND level BETWEEN 1 AND 4))`。
### 2.6 study_days 的三条数据库约束与去重
| 编号 | 约束 | 表达形式 | 覆盖场景 |
|---|---|---|---|
| C1 | 非空且不超过 7 | CHECK (cardinality(study_days) BETWEEN 1 AND 7) | {} 与 8 天以上 |
| C2 | 元素取值 1–7 | CHECK (study_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]) | {0}、{8} |
| C3 | 非空 | CHECK (study_days IS NOT NULL) | 已隐含于列级 NOT NULL，不重复写 |

- 去重 CHECK 表达不了：改由 BEFORE INSERT OR UPDATE 触发器 `trg_user_profiles_study_days_unique` 检查元素不重复并 raise exception，服务层同时校验，两层缺一层即缺陷；daily_minutes 仍为 CHECK 15–480，weekly_minutes 保持生成列 cardinality(study_days) * daily_minutes，上限由 7 × 480 = 3360 自然封顶。
## 3. 等级状态机
### 3.1 tier 定义（数字越大越强）
| tier | 条件 | evidence_strength | Sprint 1 可达 |
|---|---|---|---|
| 3 | verification_method in ('runtime_test','manual_review') | verified | 否 |
| 2 | evidence_kind in ('practice','transfer') 且 verification_method='static_rule' | assessed | 否（S1 无 submissions） |
| 1 | evidence_kind='diagnostic' | assessed | 是 |
| 0 | evidence_kind='self_assessment'，以及未命中 3/2/1 的其它组合 | self_reported 或 none | 是 |

- tier 不落列，由 §3.3 的 CASE 表达式计算；evidence_kind='practice' 且 verification_method='self_report' 的行不满足 tier 2（要求 static_rule）也不满足 tier 1，按 ELSE 0 处理：弱于诊断，永不覆盖诊断；tier 只决定排序，不直接决定 level，level 由写入端按 §3.2 与阈值算好后落库。
### 3.2 assessment_state 四态
| assessment_state | 含义 | level | evidence_strength | 界面文案（唯一） |
|---|---|---|---|---|
| unassessed | 该域从无任何评估记录 | 0 | none | 尚未评估 |
| assessed_below_threshold | 参加过诊断但该域正确率 < 60% | 0 | none | 已测，未达 L1 门槛 |
| established | 达到该等级的证据充分 | 1–4 | assessed 或 verified | 按等级名展示（L0–L4 见 PRD 5.1） |
| requested_verification | 用户申请 L3/L4，或有待核验的更高等级主张 | 0 | none 或 self_reported | 待验证申请 |

- 阈值：诊断该域正确率 >= 60% 授 L1，>= 85% 授 L2，diagnostic 最高只到 L2；L0 的两种含义必须分开：unassessed 是"尚未评估"，assessed_below_threshold 是"已测，未达 L1 门槛"；两者都不得显示为"能力弱"。
- 自评（evidence_kind='self_assessment'）不产生等级：该行恒为 level=0，用户主张 L3/L4 时 state='requested_verification'；硬规则：诊断得分通过只证明客观题答对，不等于代码能力经过验证；诊断行的 evidence_strength 只能是 'assessed'，不得写 'verified'（I6）。
- diagnostic 行的 verification_method 恒为 'static_rule'，含义是"机器按评分规则判定"，不是代码静态检查；tier 1 由 evidence_kind='diagnostic' 决定，与该方法名无关。
### 3.3 当前等级解析 SQL（唯一口径，逐字引用）
```sql
-- 传入 :user_id；恒返回 6 行（domain 级技能），无记录的域 level=0、state='unassessed'
WITH ev AS (
  SELECT l.id, l.skill_id, l.level, l.assessment_state, l.evidence_kind, l.evidence_strength, l.evidence_ref, l.created_at,
         CASE WHEN l.verification_method IN ('runtime_test','manual_review') THEN 3
              WHEN l.evidence_kind IN ('practice','transfer') AND l.verification_method = 'static_rule' THEN 2
              WHEN l.evidence_kind = 'diagnostic' THEN 1 ELSE 0 END AS tier
  FROM user_skill_levels l
  WHERE l.user_id = :user_id AND l.assessment_state = 'established'
), cur AS (
  SELECT DISTINCT ON (skill_id) skill_id, level, assessment_state, evidence_kind, evidence_strength, evidence_ref, tier
  FROM ev ORDER BY skill_id, tier DESC, created_at DESC, id DESC
), latest_any AS (
  SELECT DISTINCT ON (l.skill_id) l.skill_id, l.assessment_state
  FROM user_skill_levels l WHERE l.user_id = :user_id
  ORDER BY l.skill_id, l.created_at DESC, l.id DESC
)
SELECT s.code AS skill_code, COALESCE(cur.level, 0) AS level,
       COALESCE(cur.assessment_state, latest_any.assessment_state, 'unassessed') AS assessment_state,
       cur.evidence_kind, COALESCE(cur.evidence_strength, 'none') AS evidence_strength, cur.evidence_ref
FROM skills s LEFT JOIN cur ON cur.skill_id = s.id LEFT JOIN latest_any ON latest_any.skill_id = s.id
WHERE s.level = 'domain' ORDER BY s.order_index;
```

此 SQL 是唯一口径：后端 app/services 照此实现，前端只渲染接口返回的 level 与 state，不得重算；其他文档引用时必须逐字复制，改动只能改 §3.3 一处并同步四份文档。
### 3.4 七个取值例子（逐字）
| # | 事件序列 | 当前展示 | 依据 |
|---|---|---|---|
| 1 | 只做过一次诊断，该域正确率 40% | level 0，state=assessed_below_threshold | 有诊断记录但未达 L1 阈值 60% |
| 2 | 诊断正确率 70% | level 1，state=established，evidence_kind=diagnostic | tier 1 |
| 3 | 先诊断 70%，后又诊断 90% | level 2 | tier 1 内取最新（同层可升） |
| 4 | 再抢先做诊断 55% | level 1（较原 L2 降级） | diagnostic 同层内以最新一次为准，因此允许降级 |
| 5 | 已有诊断 L2（tier 1），一次 static_rule 练习通过 | level 2，evidence_kind=practice | tier 2 > tier 1，弱层不覆盖强层 |
| 6 | 用户自评 L4 | 展示等级不变；新增 1 行 level=0、state=requested_verification | self_assessment 不产生等级 |
| 7 | 未来某次 runtime_test 通过并累计 3 次不同题目 | level 3，evidence_strength=verified | tier 3；Sprint 1 不可达 |

注：第 4 行示例用于说明「同层取最新」会降级——若你希望同层也不降级，需在 S2 前另行决策，本轮按「同层取最新」。
### 3.5 口径冲突与 v1→v2 差异登记（实现必须按此执行）
1. §3.4 第 4 行已按 PRD.md 第 253 行对齐：diagnostic 在同一 tier 内以最新一次为准，因此允许降级（55% < 60% 时该行 state 落 assessed_below_threshold，展示等级按 §3.3 SQL 与 I2 回退）；排序口径仍为 (tier DESC, created_at DESC, id DESC)。
2. v1→v2 差异 A：user_skill_levels 原 source 列改名为 evidence_kind；原 verification_status 与 evidence_strength 两列合并为 verification_method + 生成列 evidence_strength（取值 none/self_reported/assessed/verified）。 v1→v2 差异 B：原"用户自评授予 L1/L2"与"自评最多到 L2"作废；v2 规定 self_assessment 不产生等级（§3.2、§3.4 第 6 行），用户主张 L3/L4 只落 level=0、state='requested_verification' 的行。
3. v1→v2 差异 C：submissions 的 verification_status 删除，由 verification_method + 生成列 verification_strength 取代（S3 落地，本契约只冻结表头形态，见 §5）。
## 4. JSONB 形态
### 4.1 diagnostic_attempts.answers
```json
{
  "q01": {"choice": "B"},
  "q02": {"choice": "A"},
  "q03": {"choice": "C"}
}
```

- 真实 payload 含 q01–q20 共 20 个键，此处只举 3 题，q04–q20 省略，结构相同；键名固定为 q + 两位题号；值结构恒为 `{"choice":"A|B|C|D"}`，不存题干、不存正误、不存用时。 正误由 rule_version 对应的规则重算：规则不变时同一份 answers 必须复现同一组 domain_scores。
### 4.2 diagnostic_attempts.domain_scores
```json
{
  "route_a.a1": {"correct": 3, "total": 4, "rate": 0.75, "level": 1, "state": "established"},
  "route_a.a2": {"correct": 1, "total": 4, "rate": 0.25, "level": 0, "state": "assessed_below_threshold"},
  "route_a.a3": {"correct": 4, "total": 4, "rate": 1.0,  "level": 2, "state": "established"}
}
```

- 键是 skills.code，真实 payload 恰好 6 个键，此处只举 3 个，route_a.a4–a6 省略。
- rate = correct / total，保留两位小数；level 只允许 0、1、2；state 只允许 'established' 与 'assessed_below_threshold'（诊断不产生 unassessed 与 requested_verification）；六域 total 相加必须等于 total_questions（S1 为 20）。
### 4.3 evidence_ref 格式
| evidence_kind | evidence_ref 形态 | 六行是否共用 |
|---|---|---|
| diagnostic | diag:<attempt_id> | 是：同一次诊断的 6 行共用同一 ref |
| practice / transfer | sub:<submission_id> | 否：每行一条提交（S2 起可达） |
| self_assessment | NULL（不得写 diag: 或 sub:） | 不适用 |

diagnostic 行的 evidence_count = 该域 total（题数），因此 6 行 evidence_count 之和等于 total_questions。
## 5. 六种情况表 v2 与"为什么 static_rule 不是验证"
六种情况唯一取值表 v2（PRD.md、DATABASE.md、ARCHITECTURE.md、ROADMAP.md、本文档五份逐字一致）：

| # | 情况 | is_passed | verification_method | verification_strength（生成列） | ai_assistance_level | used_ai（生成列） | passed_with_ai（生成列） | 可作 L3 证据 |
|---|---|---|---|---|---|---|---|---|
| 1 | 完全独立通过（静态规则） | true | static_rule | assessed | 'none' | false | false | 否 |
| 2 | 使用 hint 后通过 | true | static_rule | assessed | 'hint' | true | true | 否 |
| 3 | 使用 partial_code 后通过 | true | static_rule | assessed | 'partial_code' | true | true | 否 |
| 4 | 使用 full_answer 后通过 | true | static_rule | assessed | 'full_answer' | true | true | 否 |
| 5 | 练习未通过 | false | static_rule 或 self_report | assessed 或 self_reported | 任意 | 按等级 | false | 否 |
| 6 | 无法验证的自检结果 | NULL | none | none | 任意 | 按等级 | false | 否 |
| 7 | 真实执行通过（未来） | true | runtime_test 或 manual_review | verified | 任意 | 按等级 | 视等级 | 是（且需 none） |

submissions 可写列只有 is_passed、verification_method、ai_assistance_level 三列；verification_strength、used_ai、passed_with_ai 为生成列，原 verification_status 列删除（S3 落地，本表即字段冻结形态）。
| judging_mode（提交时声明） | 落库 verification_method | verification_strength（生成列） |
|---|---|---|
| self_check | self_report | self_reported |
| static_rule | static_rule | assessed |
| manual | none（人工复核后改为 manual_review） | none（复核后 verified） |
**为什么不把 static_rule 当验证**：

1. static_rule 只比对答案与结构，不执行代码，"能跑通"没有被证明；它只能产出 verification_strength='assessed'，永远不是 'verified'，因此不能构成 tier 3 证据。
2. L3 授予条件（契约保留，Sprint 1 不可达）：tier 3 证据（runtime_test 或 manual_review）且 >= 3 次不同题目且 ai_assistance_level='none'；L4 再要求已满足 L3 且 >= 1 次 transfer；落库一律 assessment_state='requested_verification'，pending_review 不是 assessment_state 的枚举值，只是界面文案。
3. MVP 等级上限：Sprint 1–3 期间任何域都不得自动出现 L3 或 L4，L3/L4 只能以 requested_verification（用户申请）存在（I5）。
4. 若允许 static_rule 授予 L3/L4，passed_with_ai=false 的记录会被读成"独立完成"，且直接违反结论页固定文案"这是学习起点评估，不是能力认证"。
## 6. API 契约（Sprint 1A 的 8 个端点已落地 + Sprint 2 增补 §6.12–§6.14）
统一约定：字段 snake_case；时间 ISO 8601 UTC 带 Z；未实现能力不注册路由（宁可 404，也不返回占位数据）；除 health 与 ready 外，所有业务接口使用 §6.6 的统一错误体。
### 6.1 GET /api/v1/users/me → 200
```json
{
  "user": {"id": 1, "display_name": "学习者", "timezone": "Asia/Shanghai", "timezone_source": "user_confirmed"},
  "profile": {"study_days": [1, 3, 5], "daily_minutes": 60, "weekly_minutes": 180},
  "skills": [{"code": "route_a.a1", "name_zh": "Python 基础", "level": 1, "state": "established", "evidence_kind": "diagnostic", "evidence_strength": "assessed"},
            {"code": "route_a.a2", "name_zh": "编程实践", "level": 0, "state": "assessed_below_threshold", "evidence_kind": null, "evidence_strength": "none"}]}
```

- skills 恒 6 行（此处只举 2 行），顺序按 skills.order_index；level 与 state 由 §3.3 SQL 计算；timezone_source='default' 时前端必须要求用户确认时区，确认前不得展示"今日/本周"推导（I7）。
- **L0 行的 evidence_kind 是 `null`**：§3.3 SQL 只在 `cur`（established 行）上取 evidence_kind，某域没有 established 行时该字段为 `null`，`evidence_strength` 由 COALESCE 兜底为 `'none'`、state 取 `assessed_below_threshold` 或 `unassessed`。库内该行确实写了 `evidence_kind='diagnostic'`（诊断来源），但**接口按 SQL 返回 null**，前端不得据库内值反推等级，也不得把 null 渲染成"没有诊断过"。
### 6.2 PUT /api/v1/users/me/profile → 200
```json
{"study_days": [1, 3, 5], "daily_minutes": 60, "timezone": "Asia/Shanghai", "timezone_confirmed": true}
```

- 成功返回与 §6.1 完全相同的结构与状态码 200；校验失败返回 422（§6.7）；timezone_confirmed=true 时写 users.timezone_source='user_confirmed'，false 或缺省时保持 'default'，且不得清除已确认状态（只前进不回退）。
### 6.3 POST /api/v1/diagnostics → 201
```json
{"question_set_version": "v1", "rule_version": "r1", "answers": {"q01": {"choice": "B"}, "q02": {"choice": "A"}}}
```

```json
{
  "attempt_id": 12,
  "rule_version": "r1",
  "domains": [{"skill_code": "route_a.a1", "correct": 3, "total": 4, "rate": 0.75, "level": 1, "state": "established"},
             {"skill_code": "route_a.a2", "correct": 1, "total": 4, "rate": 0.25, "level": 0, "state": "assessed_below_threshold"}]}
```

- 请求 answers 含 20 个键（此处只举 2 题），domains 恒 6 行（此处只举 2 行）；同一事务写 diagnostic_attempts 1 行与 user_skill_levels 6 行，6 行的 evidence_ref 全等于 diag:<attempt_id>（§4.3）。
- 同一份答案换**新的** attempt_token 再次提交返回 201 且生成新的 attempt_id：追加，不覆盖（I8）；同 token 的语义见 §6.11（同内容回放 200、版本或答案不同 409）；写成功前不得返回 attempt_id。请求体可带 `attempt_token`（1–64 字符，缺省由服务端生成）。
### 6.4 GET /api/v1/skills → 200
```json
{"skills": [{"code": "route_a.a1", "name_zh": "Python 基础", "level": "domain", "order_index": 1}]}
```

恒 6 行（此处只举 1 行），只返回 domain 级技能，不含 topic；本行的 level 是技能树层级（'domain'=域），与 §6.1 中 users/me.skills[].level（用户能力等级 0–4）不是同一字段，实现不得串用。
### 6.5 GET /api/v1/study-plan/preview → 200
```json
{"computed": true, "persisted": false,
 "days": [{"date": "2025-01-06", "minutes": 60}, {"date": "2025-01-08", "minutes": 60}],
 "note": "Sprint 2 才落库"}
```

- 内存计算，不写任何表：persisted 恒为 false，响应不得含 target_id、plan_id 等落库标识；days 的 date 必须落在 study_days 内（非学习日不分配任何计划项，S2 的 R2 引用本条），按 users.timezone 计算"本周"，weekly_minutes 可由 days 的 minutes 求和复核（3 天 × 60 = 180）。
### 6.6 统一错误体
```json
{"error": {"code": "VALIDATION_ERROR", "message": "study_days 不允许重复元素", "details": {"field": "study_days", "value": [1, 1]}},
 "request_id": "0f3c1a2b9d8e"}
```

- request_id 固定在顶层，error 内不再出现第二次；message 面向用户、中文、不含堆栈与内部路径；错误码沿用 ARCHITECTURE.md 6.2：VALIDATION_ERROR/422、NOT_FOUND/404、CONFLICT/409、DB_UNAVAILABLE/503、INTERNAL_ERROR/500。
- Sprint 2 增补两个业务错误码：`PLAN_ITEM_LOCKED`/409（计划项已是终态或 expired，不允许再改写，见 §6.13）与 `COURSE_PROGRESS_REGRESSION`/422（课程进度回退，见 §6.14）。两者仍走统一错误体，request_id 同样在顶层。
### 6.7 五个 422 / 409 示例
| 输入 | HTTP | error.code | details |
|---|---|---|---|
| PUT profile：study_days=[1,1] | 422 | VALIDATION_ERROR | {"field":"study_days","reason":"duplicate_element"} |
| PUT profile：daily_minutes=10 | 422 | VALIDATION_ERROR | {"field":"daily_minutes","reason":"out_of_range","min":15,"max":480} |
| POST diagnostics：answers 缺 q20 或多出 q21 | 422 | VALIDATION_ERROR | {"field":"answers","reason":"question_set_mismatch","expected":20} |
| PUT /lessons/{id}/progress：completed → in_progress | 422 | COURSE_PROGRESS_REGRESSION | {"field":"status","from":"completed","to":"in_progress"} |
| PATCH /study-plan/items/{id}：对 done 行再置 done | 409 | PLAN_ITEM_LOCKED | {"field":"status","current":"done","allowed":["done","skipped"]} |
### 6.8 GET /api/v1/diagnostics/paper → 200
```json
{"question_set_version": "v1", "rule_version": "r1", "total": 20,
 "questions": [{"id": "q01", "order": 1, "type": "single_choice", "domain_code": "route_a.a1", "prompt": "……",
                "options": [{"key": "A", "text": "……"}, {"key": "B", "text": "……"}]}]}
```

- 题集的唯一来源是后端（`app/services/question_set.py`）：questions 恒 20 条，按 order 升序，每题带 domain_code 供结果页按域分组。
- **响应不得出现任何答案键**（correct / answer / answer_key / solution 一律禁止）：题面会被浏览器缓存与复制，答案只能走 §6.10 的已提交批次。
- 查询参数 version 缺省 `v1`；不支持的值返回 422，统一错误体 `details={"field":"version","reason":"unsupported_version","supported":["v1"]}`。
- 题面里连 `correct` / `explanation` 这类键都不许出现：`test_diagnostics_paper.py::test_paper_never_carries_a_correct_or_explanation_field` 逐键断言。
- 实现状态：已落地（`apps/api/app/api/v1/routes/diagnostics.py::read_paper`）。

### 6.9 GET /api/v1/diagnostics/history → 200
```json
{"items": [{"attempt_id": 12, "submitted_at": "2025-01-06T02:30:00Z",
            "question_set_version": "v1", "rule_version": "r1", "total_correct": 14, "total_questions": 20,
            "domains": [{"skill_code": "route_a.a1", "correct": 3, "total": 4, "rate": 0.75, "level": 1, "state": "established"}]}],
 "next_cursor": "9", "has_more": true}
```

- 追加式历史，按 id 倒序（最新在前）；items 行的 domains 与 §6.3 响应的 domains 完全同构（恒 6 行）。
- 分页：`limit` 缺省 20、范围 1–100（越界 422，`details={"field":"limit","reason":"out_of_range","min":1,"max":100}`）；`cursor` 是上一页最后一条的 attempt_id（非正整数 422，`details={"field":"cursor","reason":"invalid_cursor"}`）；`has_more=false` 时 `next_cursor` 为 `null`。
- 无任何批次时返回 `{"items":[],"next_cursor":null,"has_more":false}`，不返回 404。
- 实现状态：已落地（`read_history`，服务层 `list_history`）。

### 6.10 GET /api/v1/diagnostics/attempts/{id} → 200（逐题明细；答案只在提交后可见）
```json
{"attempt_id": 12, "submitted_at": "2025-01-06T02:30:00Z",
 "question_set_version": "v1", "rule_version": "r1", "total_correct": 14, "total_questions": 20,
 "domains": [{"skill_code": "route_a.a1", "correct": 3, "total": 4, "rate": 0.75, "level": 1, "state": "established"}],
 "questions": [{"id": "q01", "order": 1, "domain_code": "route_a.a1", "prompt": "……",
                "options": [{"key": "A", "text": "……"}, {"key": "B", "text": "……"}],
                "selected": "B", "correct": "B", "is_correct": true, "explanation": null}]}
```

- 顶层固定 8 个字段：`attempt_id / submitted_at / question_set_version / rule_version / total_correct / total_questions / domains / questions`；`domains` 与 §6.3 同构（恒 6 行）。`test_diagnostics_detail.py::test_detail_returns_per_question_verdicts_from_the_live_question_set` 用 `set(body)` 逐键断言了这 8 个键。
- `questions[]` 每行固定 9 个字段：`id / order / domain_code / prompt / options[]（key、text）/ selected / correct / is_correct / explanation`；恒 20 行，`order` 为 1–20 且与题集顺序一致。`selected` 取自该批次落库的 answers（未作答为 `null`），`correct` 是答案键，`is_correct` 为两者是否相等，`explanation` **字段始终存在**（不省略键）。起草契约为 `null`（题库当时无解析字段）；v0.1.15 起 20 题全部返回解析文本，而发卷接口仍不含该键——**字段形状不变，只是取值有内容**，评分口径（`v1` / `r1`）未变。
- **题面在请求时从题库投影，数据库只存答案**：本接口不读题库副本也不回写；`test_diagnostics_detail.py::test_detail_marks_wrong_choices_and_the_database_stores_answers_only` 同时断言逐题对错与「库里只有 answers」。
- **答案可见性约束（I9）**：`correct` / `is_correct` / `explanation` 只能由本接口、针对**已落库的批次**返回；§6.8 的题面接口永不返回它们；任何"未提交也能拿到答案"的路径（把答案塞进 paper、前端内置答案表、按 id 猜答案的独立接口）都判定为契约违规。
- 批次只追加不改写（I8），因此同一 `attempt_id` 反复读取必须返回相同内容。
- 错误：批次不存在或不属于当前用户 → 404 NOT_FOUND，message「诊断批次不存在，或不属于当前用户」，统一错误体，不得返回空对象（`test_diagnostics_detail.py::test_another_users_batch_is_404_and_never_leaks_verdicts`）。
- 前端读取要求（已对齐）：解析器读 `selected` / `correct` / `is_correct`（`apps/web/src/lib/contract.ts::parseAttemptQuestion` 首选这三个键，旧拼写只作兼容兜底）；`explanation` 恒为 null 且界面不展示，缺字段时显示「—」而不是猜一个正确答案。
- 实现状态：已落地（`routes/diagnostics.py::read_attempt` → `services/diagnostics.py::attempt_detail`）。

### 6.11 attempt_token 与幂等 / 409 语义
- 请求体可选字段 `attempt_token`（1–64 字符非空字符串；缺省或空白由服务端生成 uuid4 hex，即"缺省 = 每次新增批次"）。超长或空串 → 422，`details={"field":"attempt_token","reason":"invalid_token","max_length":64}`。
- 三条语义（同一 (user_id, attempt_token) 至多对应一个批次，`uq_diagnostic_attempts_token` 兜底）：
  1. **新 token** → **201** 并新增一次批次：1 行 `diagnostic_attempts` + 6 行 `user_skill_levels`（§6.3）。
  2. **同 token + 同 question_set_version / rule_version + 同 answers** → **200 回放**：返回**原 attempt_id** 与原 domains，不新增任何行（浏览器重试、双击提交不产生重复数据）。answers 比对先归一化（键小写去空格、choice 大写、丢弃题集外的键与空 choice，`normalize_answers`），因此键序与大小写噪声不算"不同内容"。
  3. **同 token + 版本或 answers 不同** → **409 IDEMPOTENCY_CONFLICT**，统一错误体 `{"error":{"code":"IDEMPOTENCY_CONFLICT","message":…,"details":{"attempt_id":<原批次>,"conflicts":["question_set_version"|"rule_version"|"answers"]}},"request_id":…}`；既不得静默回放旧批次，也不得新建批次，更不得覆盖旧行。
- 事务：写库失败必须整笔回滚（attempts 与 levels 都不留行），回滚后同 token 可重新提交并成功；并发同 token 由唯一约束兜底，落败方转为回放，**不得 500**。
- 实现状态：已落地；用例 `test_diagnostics_idempotency.py::test_identical_retry_replays_200_and_appends_no_rows`、`::test_same_token_with_different_answers_is_409`、`::test_same_token_with_a_different_stored_version_is_409`、`::test_concurrent_same_token_never_500_and_keeps_one_batch`。

### 6.12 GET /api/v1/study-plan → 200（Sprint 2 增补：预算三分口径）
```json
{ "week_start": "2025-01-06", "week_end": "2025-01-12", "today": "2025-01-08",
  "timezone": "Asia/Shanghai", "daily_minutes": 60, "study_days": [1, 3, 5],
  "weekly_planned_minutes": 90, "scheduled_items": 2, "history_items": 1,
  "days": [ { "plan_date": "2025-01-08", "weekday": 3,
              "scheduled_minutes": 45, "history_minutes": 15, "total_minutes": 60,
              "items": [ { "id": 11, "kind": "lesson", "target_id": 3, "planned_minutes": 45,
                           "status": "scheduled", "rationale": "L2 + 周三可用 60 分钟 -> 1 节课 45 分钟",
                           "dedupe_key": "2025-01-06:3:lesson:3" } ] } ],
  "expired_items": 0, "lesson_items": 2, "exercise_items": 0, "review_items": 0 }
```

- 三个分钟字段必须逐日同时给出（缺一即视为缺陷）：`scheduled_minutes` = 该 plan_date 上 status='scheduled' 行的 planned_minutes 之和（待执行）；`history_minutes` = status in ('done','skipped') 之和（历史，不可再执行）；`total_minutes` = scheduled_minutes + history_minutes（expired 行不计入任何一项）。历史终态（done/skipped）的分钟仍计入该日**已分配预算**，故 `total_minutes <= daily_minutes` 只在生成那一刻成立：用户事后调小 daily_minutes 时该日 total 可能超新额度，必须显示超限提示，不得宣称无条件恒成立。
- 顶层 `scheduled_items` / `history_items` 分别是本周待执行行数与历史（done+skipped）行数；前端**必须分开展示**，不得把 history_minutes 混进「待执行」。
- 预算口径与生成一致：生成时某日新排课额度 = daily_minutes − 历史终态分钟，只为 scheduled 分配剩余额度，因此 `total_minutes <= daily_minutes` 在生成那一刻成立（R1 由此可复核）；事后调小 daily_minutes 不重算历史、不改写既有行，该日 total 超新额度是须展示超限提示的合法状态。
- `today` 按 users.timezone 计算，前端判断「今天」只认该字段，不按浏览器时区自行推导；`week_start` / `week_end` 同样是用户本地日历的日期。
- 只读：读取路径不生成、不写入任何行；kind 恒为 'lesson'（exercise_items 与 review_items 恒为 0），每行 target_id 指向 lessons 中 status='published' 的真实课程。
- `expired_items` 是已作废行数，不进任何预算；expired 行只能由 §6.13 所述的生成路径复活为 scheduled，没有手工复活入口。

### 6.13 PATCH /api/v1/study-plan/items/{item_id} → 200（计划项状态机）
请求体只有 `{"status": "done"}` 或 `{"status": "skipped"}` 两种合法形态。

| 当前 status | 目标 status | 结果 |
|---|---|---|
| scheduled | done | 200，写库，updated_at 前进 |
| scheduled | skipped | 200，写库，updated_at 前进 |
| done | done / skipped | 409 PLAN_ITEM_LOCKED，不写库 |
| skipped | done / skipped | 409 PLAN_ITEM_LOCKED，不写库 |
| expired | 任意 | 409 PLAN_ITEM_LOCKED，不写库 |
| 任意 | scheduled 或其它值 | 422 VALIDATION_ERROR，details={"field":"status","allowed":["done","skipped"]} |

body 校验先于状态校验：终态行收到非法 body 仍返回 422，不返回 409；合法 body 命中终态行才返回 409。
| 不存在或不属于当前用户 | — | 404 NOT_FOUND |

- **done / skipped 是终态**：任何路径（PATCH、重生成、受控复活、课程完成同步）都不得改写其 status 与 updated_at，也不得删除历史行。
- **不存在撤销语义**：接口没有 done→scheduled 或 skipped→scheduled 的入口，也没有撤销参数；前端必须移除撤销按钮，终态行只读展示，不得渲染点击后只会得到 409 的按钮。
- 受控复活：`POST /api/v1/study-plan/generate` 可在同一 dedupe_key 上把 expired 行改回 scheduled，前提是该键属于本周目标集合；`EXPIRE_STALE_ITEMS` 的 keep 集合必须与目标集合一致，不得保留 expired 键。
- 幂等与历史：同一输入重复生成不改变 (user_id, week_start) 维度的行数；done/skipped 行的 status 与 updated_at 逐字不变。

### 6.14 PUT /api/v1/lessons/{id}/progress → 200（进度只前进 + 完成同步计划项）
请求体：`{"status": "in_progress" | "completed", "progress_pct": 0–100, "self_assessment": 0–2}`；self_assessment > 2 → 422。

| 当前 status | 目标 status | 结果 |
|---|---|---|
| 无行 | in_progress | 200，建行 |
| 无行 / not_started | completed | 200，建行，progress_pct=100，completed_at 首次写入 |
| not_started | in_progress | 200 |
| in_progress | completed | 200，progress_pct=100 |
| in_progress | not_started | 422 COURSE_PROGRESS_REGRESSION，不写库 |
| completed | not_started / in_progress | 422 COURSE_PROGRESS_REGRESSION，不写库 |
| 任意（含相同状态重复提交） | 与当前相同 | 200 幂等，不报错，completed_at 不变 |

- 只允许前进：not_started → in_progress → completed。回退请求整笔不写库（status、progress_pct、updated_at、completed_at 全部不变）。
- progress_pct 只增不减；status='completed' 时固定 100；completed_at 只在首次完成时写入，之后不回退、不清空。
- **并发不倒退（数据库层原子条件更新）**：写入走单条 UPSERT，`ON CONFLICT DO UPDATE` 的 `WHERE` 要求新等级 ≥ 旧等级（not_started=0 < in_progress=1 < completed=2），并同时 `progress_pct = GREATEST(旧,新)`、`completed_at = COALESCE(旧,新)`。
- 并发两个请求时最终状态不得倒退；`WHERE` 不成立即整笔零写入（status/progress_pct/completed_at 全不变），服务层重新读取当前行后返回 422 `COURSE_PROGRESS_REGRESSION`。
- **完成同步（同一事务）**：当且仅当 status='completed' 时，把 study_plan_items 中 target_id=lesson_id、status='scheduled' 且 week_start = 当周周一（按 users.timezone 本地日历计算）的行置为 done；status in ('done','skipped','expired') 的行不动，不新增行、不删除行。响应返回时计划项已是 done。
- **计划项 done ≠ 课程掌握**：界面必须同时展示课程真实完成状态（learning_progress.status）与计划项状态，并注明「计划完成不等于课程完成或能力等级」。
- 没有自动计时：打开课程（`GET /lessons/{id}`）不写库，不改变 progress_pct 与 time_spent_seconds；time_spent_seconds 的节流上报延期至 Sprint 3，本轮后端不接受该字段写入。
- 自评 self_assessment 只写 learning_progress.mastery_level，上限 L2，永不写入 user_skill_levels（见 ROADMAP AC-S2-04）。

## 7. 迁移草案：0002_sprint1a_identity_diagnostics（只定稿，不执行）
### 7.1 范围
| 项 | 取值 |
|---|---|
| revision | 0002_sprint1a_identity_diagnostics |
| depends_on | 0001（S0 空基线） |
| up 内容 | 5 张表 + 1 个触发器函数 + 1 行 users 种子 + 1 行 user_profiles 种子 + 6 行 skills 种子 |
| down 内容 / 执行时机 | 不提供（本契约不允许破坏性语句）；Sprint 1B 实现阶段执行，Sprint 1A 本轮不执行任何 alembic 命令 |
### 7.2 DDL 清单（伪 DDL，字段与约束即最终形态）
```sql
-- 5 张表；字段与约束即最终形态（每行一个对象，行内可多列）
CREATE TABLE users (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  display_name varchar(80) NOT NULL, timezone varchar(64) NOT NULL DEFAULT 'Asia/Shanghai',
  timezone_source varchar(16) NOT NULL DEFAULT 'default'
    CONSTRAINT ck_users_timezone_source CHECK (timezone_source IN ('default','user_confirmed')),
  locale varchar(16) NOT NULL DEFAULT 'zh-CN',
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE user_profiles (user_id bigint PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  target_track varchar(32) NOT NULL DEFAULT 'route_a' CHECK (target_track IN ('route_a')),
  study_days smallint[] NOT NULL DEFAULT '{1,3,5}',
  daily_minutes smallint NOT NULL DEFAULT 60 CONSTRAINT ck_up_daily_minutes CHECK (daily_minutes BETWEEN 15 AND 480),
  weekly_minutes smallint GENERATED ALWAYS AS (cardinality(study_days) * daily_minutes) STORED,
  onboarding_completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_up_study_days_card CHECK (cardinality(study_days) BETWEEN 1 AND 7),
  CONSTRAINT ck_up_study_days_vals CHECK (study_days <@ ARRAY[1,2,3,4,5,6,7]::smallint[]));
CREATE FUNCTION fn_up_study_days_unique() RETURNS trigger AS $$
BEGIN
  IF cardinality(NEW.study_days) <> (SELECT count(DISTINCT d) FROM unnest(NEW.study_days) AS d) THEN
    RAISE EXCEPTION 'study_days 不允许重复元素: %', NEW.study_days USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END $$ LANGUAGE plpgsql;
CREATE TRIGGER trg_user_profiles_study_days_unique BEFORE INSERT OR UPDATE ON user_profiles
  FOR EACH ROW EXECUTE FUNCTION fn_up_study_days_unique();

CREATE TABLE skills (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  code varchar(64) NOT NULL UNIQUE, name_zh varchar(80) NOT NULL,
  level varchar(16) NOT NULL DEFAULT 'domain' CONSTRAINT ck_skills_level CHECK (level IN ('domain','topic')),
  route_code varchar(32) NOT NULL DEFAULT 'route_a', order_index smallint NOT NULL, description text NULL,
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE diagnostic_attempts (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  question_set_version varchar(16) NOT NULL, rule_version varchar(16) NOT NULL,
  answers jsonb NOT NULL, domain_scores jsonb NOT NULL,
  total_correct smallint NOT NULL CONSTRAINT ck_da_total_correct CHECK (total_correct >= 0),
  total_questions smallint NOT NULL CONSTRAINT ck_da_total_questions CHECK (total_questions > 0),
  submitted_at timestamptz NOT NULL DEFAULT now(), created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE user_skill_levels (id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id bigint NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  skill_id bigint NOT NULL REFERENCES skills(id) ON DELETE RESTRICT,
  level smallint NOT NULL CONSTRAINT ck_usk_level CHECK (level BETWEEN 0 AND 4),
  evidence_kind varchar(16) NOT NULL CONSTRAINT ck_usk_evidence_kind
    CHECK (evidence_kind IN ('self_assessment','diagnostic','practice','transfer')),
  verification_method varchar(16) NOT NULL CONSTRAINT ck_usk_verification_method
    CHECK (verification_method IN ('none','self_report','static_rule','runtime_test','manual_review')),
  evidence_strength varchar(16) GENERATED ALWAYS AS (CASE
    WHEN verification_method IN ('runtime_test','manual_review') THEN 'verified'
    WHEN verification_method = 'static_rule' THEN 'assessed'
    WHEN verification_method = 'self_report' THEN 'self_reported' ELSE 'none' END) STORED,
  assessment_state varchar(24) NOT NULL CONSTRAINT ck_usk_assessment_state
    CHECK (assessment_state IN ('unassessed','assessed_below_threshold','established','requested_verification')),
  evidence_ref varchar(200) NULL,
  evidence_count smallint NOT NULL DEFAULT 0 CONSTRAINT ck_usk_evidence_count CHECK (evidence_count >= 0),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT ck_usk_strength_none_level0 CHECK (evidence_strength <> 'none' OR level = 0),
  CONSTRAINT ck_usk_state_level CHECK ((assessment_state IN ('unassessed','assessed_below_threshold','requested_verification') AND level = 0)
    OR (assessment_state = 'established' AND level BETWEEN 1 AND 4)));
CREATE INDEX ix_user_skill_levels_user_skill ON user_skill_levels (user_id, skill_id, created_at DESC);

-- 种子：1 用户 + 1 档案 + 6 技能域
INSERT INTO users (display_name, timezone) VALUES ('学习者', 'Asia/Shanghai');
INSERT INTO user_profiles (user_id, study_days, daily_minutes) VALUES (1, '{1,3,5}', 60);
INSERT INTO skills (code, name_zh, level, route_code, order_index) VALUES
  ('route_a.a1', 'Python 基础', 'domain', 'route_a', 1), ('route_a.a2', '编程实践', 'domain', 'route_a', 2),
  ('route_a.a3', 'API', 'domain', 'route_a', 3), ('route_a.a4', 'LLM', 'domain', 'route_a', 4),
  ('route_a.a5', 'RAG 与 Agent 基础', 'domain', 'route_a', 5), ('route_a.a6', '简单 AI 项目', 'domain', 'route_a', 6);
```
### 7.3 明确不建的表
study_plan_items（S2 建表）、lessons、exercises、submissions、mistakes、review_tasks、projects、ai_interactions、learning_progress。DATABASE.md 保留这些表的设计，但必须标注落地 Sprint；Sprint 1 的迁移不得出现它们的 CREATE TABLE。
### 7.4 声明
本契约与 0002 迁移不允许出现任何删除类语句：DROP TABLE、DELETE FROM、docker compose down -v 一律禁止；Sprint 1 的库只能通过 CREATE 与 INSERT 变更。除本条禁令外，全文不得再出现这两个关键字。
## 8. 约束测试清单
每条都必须能由一条 SQL、一次 HTTP 请求或一次界面操作判定。"拒绝"指事务回滚且返回非 2xx 或数据库错误码 23514 / 428C9。

| 编号 | 检查对象 | 输入 | 期望 |
|---|---|---|---|
| T01 | study_days | study_days='{}' | 拒绝（ck_up_study_days_card） |
| T02 | study_days | study_days='{1,1}' | 拒绝（trg_user_profiles_study_days_unique，23514） |
| T03 | study_days | study_days='{8}' | 拒绝（ck_up_study_days_vals） |
| T04 | study_days | study_days='{0}' | 拒绝（ck_up_study_days_vals） |
| T05 | study_days | study_days='{1,2,3,4,5,6,7}', daily_minutes=60 | 通过，weekly_minutes=420 |
| T06 | study_days | study_days='{1,3,5}', daily_minutes=60 | 通过，weekly_minutes=180 |
| T07 | daily_minutes | daily_minutes=10 | 拒绝（ck_up_daily_minutes） |
| T08 | daily_minutes | daily_minutes=481 | 拒绝（ck_up_daily_minutes） |
| T09 | 生成列 | update user_profiles set weekly_minutes=1000 | 拒绝（428C9），该行 weekly_minutes 不变 |
| T10 | 生成列 | insert user_skill_levels 显式给 evidence_strength='verified' | 拒绝（428C9）；不给该列时自动按 verification_method 计算 |
| T11 | level/state | level=2, verification_method='none'（evidence_strength='none'） | 拒绝（ck_usk_strength_none_level0） |
| T12 | level/state | assessment_state='established', level=0 | 拒绝（ck_usk_state_level） |
| T13 | level/state | assessment_state='requested_verification', level=3 | 拒绝（ck_usk_state_level） |
| T14 | level/state | assessment_state='unassessed', level=1 | 拒绝（ck_usk_state_level） |
| T15 | 诊断批次 | POST /api/v1/diagnostics（20 题完整答案） | 201；user_skill_levels 新增 6 行，6 行 evidence_ref 全等于 diag:<attempt_id>，evidence_kind='diagnostic'，level ∈ {0,1,2} |
| T16 | 追加式 | 同一份 answers 再提交一次 | 201 且 attempt_id 更大；diagnostic_attempts 新增 1 行（共 2 行）；user_skill_levels 共 12 行，最早 6 行的 created_at 与 level 不变 |
| T17 | 批次计数 | total_questions=0 / total_correct=-1 | 均拒绝（ck_da_total_questions / ck_da_total_correct） |
| T18 | 状态机 | 域内先写 established(level=2, tier1)，再写 requested_verification(level=0, 自评 L4) | §3.3 SQL 该域仍返回 level=2、state='established'；requested_verification 行不参与展示 |
| T19 | 时区确认 | users.timezone_source='default' | 前端档案页要求先确认时区，确认前今日/本周区块不渲染数据 |
| T20 | 越界题号 | POST /api/v1/diagnostics 提交 q21 | 422，error.code='VALIDATION_ERROR'，request_id 与后端日志一致 |
| T21 | 不落库 | GET /api/v1/study-plan/preview | 200 且 persisted=false；随后 `select count(*) from pg_class where relname='study_plan_items'` 为 0 |
## 9. 验收案例映射
PRD 的 Sprint 1 AC（AC-09、AC-31）与 ROADMAP 的 AC-S1-01 至 AC-S1-18 逐条落到"实际数据或行为"，不落占位；每行都能用一条 SQL、一次请求或一次界面操作判定。

| 验收编号 | 断言要点 | 对应的实际数据或行为 |
|---|---|---|
| PRD AC-09 | 首次诊断 1 个 attempt、6 行 ref 同值；重提追加不复写旧行 | `select count(*) from diagnostic_attempts` = 1；6 行 `evidence_ref` 全等于 'diag:<attempt_id>' 且该 id 存在；再提交后 attempt 2 行、user_skill_levels 12 行，旧行 created_at 不变 |
| PRD AC-31 | 诊断不自动授予 L3/L4；established 行 evidence_strength 只出现 'assessed' | `select count(*) from user_skill_levels where level>=3` = 0；established 行 level ∈ {1,2}、evidence_strength='assessed'；`where evidence_strength='verified'` = 0 |
| AC-S1-01 | 3 秒内 6 条，含 skill_code、level、evidence_kind、evidence_strength、assessment_state | POST 响应 domains 长度 6 且五项字段齐全；库内 user_skill_levels 新增 6 行（§8 T15） |
| AC-S1-02 | 刷新续答；清浏览器存储归零且不产生服务端数据 | 未提交时 diagnostic_attempts = 0 行；清 localStorage 后 answers 为空且服务端无新行 |
| AC-S1-03 | 同一份答案两次 → 12 行，最早 6 行内容不变 | §8 T16：user_skill_levels 共 12 行，旧 6 行 created_at 与 level 不变；"两次"按**两个不同 attempt_token** 计，同 token 重放按 §6.11 第 2 条不新增任何行 |
| AC-S1-04 | 未完成诊断访问 /learn 只发 health 与 ready | 网络面板只有 health、ready，以及一次判定诊断状态所必需的 `GET /api/v1/users/me`；无 /api/v1/lessons 等课程数据请求 |
| AC-S1-05 | 空库 alembic upgrade head 成功，skills 6 行全为 domain | 迁移 0002 后 `select count(*), count(distinct level) from skills` = (6, 1) 且该 level='domain' |
| AC-S1-06 | 越界题号 422、统一错误体、request_id 可对日志 | §8 T20 与 §6.7 第 3 行：error.code='VALIDATION_ERROR'，顶层 request_id 与后端日志一致 |
| AC-S1-07 | 无密钥仍可完成诊断，后端无 DeepSeek 调用 | 未设 DEEPSEEK_API_KEY 时 POST /api/v1/diagnostics 仍 201；`grep -r deepseek apps/api` 无业务导入 |
| AC-S1-08 | 全对时最高 L2，无 level>=3 且 established 的行，结论页含固定文案 | `select count(*) from user_skill_levels where level>=3 and assessment_state='established'` = 0；页面含"这是学习起点评估，不是能力认证" |
| AC-S1-09 | 自评 L3/L4 不改展示等级，只新增 1 行 level=0 的申请行 | §8 T18：新增 1 行 evidence_kind='self_assessment'、assessment_state='requested_verification'、level=0；§3.3 SQL 结果不变 |
| AC-S1-10 | L0 两态可区分且界面文案不同 | 空库调用 §6.1：6 行 state='unassessed'；诊断正确率 < 60% 的域 level=0、state='assessed_below_threshold'、evidence_ref='diag:<id>'；文案"尚未评估"/"已测，未达 L1 门槛"（§3.2） |
| AC-S1-11 | 批次可追溯：1 行 attempt 四字段非空、total_questions=20、total_correct 与 domain_scores 一致、6 行 ref 同值 | `select total_correct, (select sum((v->>'correct')::int) from jsonb_each(domain_scores) v) from diagnostic_attempts` 两列相等；6 行 evidence_ref 相同（§8 T15） |
| AC-S1-12 | 重复诊断追加、attempt_id 不同、展示按 tier 取最新 | §8 T16：diagnostic_attempts 2 行且 id 不同、最早行不变；§3.3 SQL 按 (tier DESC, created_at DESC, id DESC) 返回 |
| AC-S1-13 | timezone 确认前不展示今日/本周，确认后写 user_confirmed | §8 T19：PUT 带 timezone_confirmed=true 后 `select timezone_source from users` = 'user_confirmed'；确认前今日/本周区块不渲染数据 |
| AC-S1-14 | study_days 四条拒绝、两条通过、daily_minutes 两条拒绝、weekly_minutes 不可写 | §8 T01–T09：{}、{1,1}（触发器）、{8}、{0} 拒绝；{1,2,3,4,5,6,7} 与 {1,3,5} 通过；10 与 481 拒绝；直写 weekly_minutes 报 428C9 |
| AC-S1-15 | 计划预览不落库 | §8 T21：200 且 persisted=false；`select to_regclass('public.study_plan_items')` 返回 NULL |
| AC-S1-16 | L3/L4 不可自动授予，只能以 requested_verification 存在 | `select count(*) from user_skill_levels where assessment_state='established' and level>=3` = 0；level>=3 的行 state 全为 'requested_verification' |
| AC-S1-17 | 约束测试清单为 S1 可验收交付，逐条记录通过/拒绝与实际输出 | 本文档 §8 的 T01–T21 给出"输入 → 期望"；执行记录写入 SPRINT1A_TEST_RESULTS.md，须含 evidence_strength='none' 只允许在 level=0 行的用例（T11） |
| AC-S1-18 | 解析唯一口径：每域取 tier 最新、requested_verification 不参与、弱层不覆盖强层 | §3.3 SQL + §8 T18：先写 tier 2 的 practice(level=2)、后写 tier 1 诊断时，展示仍为 level=2、evidence_kind='practice' |
**S2 冻结项（幂等：本契约登记口径，S2 实现）**
- 重生成在单个事务内完成：读现有行 → 计算目标集合 → 按 dedupe_key UPSERT → 不删除 status in ('done','skipped') 的行；不变量：(user_id, week_start) 维度的 count(*) 在同输入重生成前后不变，done/skipped 行的 status 与 updated_at 不得被改写。
- 验收用例 1：同一输入重生成两次，该维度行数不变。用例 2：完成 1 项后重生成，该项保持 done。用例 3：跳过 1 项后重生成，该项保持 skipped。

