# Changelog

本项目的所有重要变更记录在此文件。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号遵循语义化版本。

## [Unreleased]

## [0.1.23] — 2026-11-04

把**只有对话里才知道的事**写进仓库：`CONTRIBUTING.md` 新增第 7 节「踩过的坑」，12 条，每条都真的在本仓库发生过。

### 为什么要写

这些问题不会出现在任何设计文档里，但每个新贡献者都会撞上，而且**症状与根因往往差得很远**——改完前端只看旧界面、`npm ci` 报 EPERM、CI 因锁文件失效必红、测试随星期几变红。这些知识原先只存在于开发者的记忆里，会随会话消失。

### 收录内容

1. **改了前端却看到旧界面**：`next start` 提供的是构建产物；（这一条曾浪费一整轮）
2. **服务在跑时不要安装依赖或构建**：`npm ci` 删 `node_modules` 时被 `next start` 占用 → EPERM，还会弄坏正在跑的前端；
3. **`npm` 在 Windows 是 `npm.cmd`**：Node ≥18.20 拒绝 spawn `.cmd`（需 `shell: true`），`Start-Process 'npm'` 静默无操作；
4. **PowerShell 5.1 脚本必须纯 ASCII**：无 BOM 脚本按 ANSI 读，中文注释会解析失败；
5. **改 `pyproject.toml` 就要 `uv lock`**：否则 `uv sync --locked` 让 CI 必红；
6. **版本号有四处**：第四处（`app/__init__.py`）曾落后 17 个版本；
7. **测试别依赖共享用户的历史**：用 `create_isolated_learner()`；
8. **写死「周几」的测试会随日历漂移**：更糟的是越过目标日后**空过**，用 `calendar_today()` / `future_weekdays()` 或显式 skip；
9. **生成列不能直接 INSERT**（`evidence_strength`）；
10. **迁移落地瞬间 `alembic current` 不打印 `(head)`**：这是正确行为；
11. **路径含中文时 `URL.pathname` 会被百分号编码**；`git commit -m` 带引号会被吃掉 → 用 `-F`；
12. **Docker Desktop 会自己停**：集成测试大面积 `ConnectionRefusedError` 时先看 Docker，别改测试。

### Verified

- 文档一致性检查通过；README 文档索引已指向新内容。

## [0.1.22] — 2026-11-04

系统排查**时间脆弱性**：上一轮发现「写死周三」的用例会随日期变红，这轮把同类隐患一次清掉。

### Fixed

- **`tests/test_sprint2_patch_lessons.py`**：`study_days=[5]`（周五）且走 HTTP 用真实时钟——周六就会红。改为从今天推算。
- **`tests/test_sprint2_patch_study_plan.py`** 里剩余三处硬编码天数：
  - 两处场景（「周二首次生成」「周末首次生成」）需要特定星期，越过该星期后断言会**恒真**——测试不再检验任何东西。比红更危险的是**空过**，因此改为显式 `pytest.skip` 并说明原因；
  - 一处改为使用上轮引入的日期推算 helper。
- **共享 helper 提到 `tests/conftest.py`**：`calendar_today()` / `future_weekdays()`，供所有走真实时钟的计划用例复用（此前散落在一个测试文件里）。

### 排查结论（不是所有「写死日期」都有问题）

- `test_progress_aggregates.py` 的固定日期测的是**纯函数**（`activity_window`），不依赖今天，安全；
- `test_study_plan_generate.py` 的三处 `study_days=[2,3,4]` 走**服务层 + `today_override`**，不受真实时钟影响，安全；
- 真正危险的是**走 HTTP 且写死星期**的组合，本轮已全部处理。

### Verified

- 产品库：`164 passed`（单元）/ `142 passed, 1 skipped`（集成）；**全新数据库结果完全相同**；`ruff` 干净。
- 那个 skip 是诚实的：本周的周二已过，「周二首次生成」场景无法复现——保留红或让它空过都更糟。

## [0.1.21] — 2026-11-04

堵住一个**可以清空错题本**的诚信漏洞，并修掉一组会随星期几变红的测试。

### Fixed

- **自检申报的「通过」不再推进错题本**。此前 `self_reported_passed=true`（勾选「我已在本地运行并通过」）与静态规则通过一样推进 streak——勾三次就能把一道错题标记为完成，而系统从未验证过。错题本的意义正是把答错的题**重新考一次**。
  - 自检**失败**仍然照常重置：谎报失败对自己没好处，拦它只会误伤；
  - 练习页明确写出这条规则，避免学习者「勾了没反应」的困惑。
- **`tests/test_sprint2_patch_study_plan.py` 的 3 个用例硬编码了 `study_days=[3]`（周三）**：一旦运行日越过周三，排课器不会给过去的日子排东西，用例整片变红。实测：2026-11-04（周三）全绿，2026-11-05（周四）3 红。改为从「今天」推算学习日，本周放不下时 `pytest.skip` 并说明原因。
- 顺带修正 `test_sprint3_exercises.py` 的间隔机制用例：它们原先借**自检口径**造「通过」（docstring 写着「自检口径最省事」），与本轮新规则冲突。改用真正的静态规则通过，并断言 `verification_strength == 'assessed'`——间隔机制不该依赖判题路径。

### Verified

- 新增 `tests/test_review_evidence_gate.py`（3 条）：自检通过不推进、静态通过仍推进、自检失败仍重置。
- 产品库 `164 passed`（单元）/ `143 passed`（集成）；**全新数据库同样 164 / 143**；`ruff` 干净。
- 排除了误判：把本轮改动 stash 后，那 3 个日期用例同样红——证明与本轮改动无关，是既有缺陷。

## [0.1.20] — 2026-11-04

让「通过」不再过分乐观：**语法不合法的代码不能算通过**。

### 问题

静态规则只做文本比对，因此少一个右括号照样命中「定义了函数」那条规则。实测提交

```python
def error_kind(traceback_text):
    return "x"
def error_line(traceback_text):
    return [-1] int( strip(line) print(error_kind
```

6/7 条规则命中，旧逻辑会判**通过**——而这段代码根本跑不起来。

### Added

- `judging.syntax_error()`：用 `ast.parse` 检查语法，**只解析、不执行**（模块内依旧没有 `eval` / `exec` / `subprocess`，与「服务端绝不执行用户代码」的红线不冲突）。
- 判题的检查项新增第 0 项 `syntax`：语法错时报「代码无法解析：第 N 行附近 xxx」，并直接判失败；汇总文案也点明原因是语法。
- 病态输入（超深嵌套、超长表达式）由 `RecursionError` / `MemoryError` / `ValueError` 兜底，**绝不 500**。

### Verified

- 新增 6 条用例：合法代码无错、非法代码报行号、两种病态输入不抛异常、**规则全中 + 语法错 = 判失败**、语法门禁不误伤正确答案。
- 真实提交：6/7 规则命中但语法坏 → `is_passed=False`，首项即 `syntax` 失败。
- `164 passed`（单元，+6）/ `140 passed`（集成）/ `ruff` 干净。
- 22 道题的 20 份历史「已通过」提交语法**全部合法**——这次收紧没有追溯推翻任何既有判定。

### 已知边界

语法合法 ≠ 逻辑正确。`def error_kind(t): return 1` 语法没问题、规则也可能命中，判题仍然只能说「静态规则通过，未经验证」。

## [0.1.19] — 2026-11-04

修掉一个**让全部 22 道练习形同虚设**的判题漏洞。

### 问题

静态规则直接在原始文本上做正则匹配，注释也参与匹配。于是只提交一行

```python
# def error_kind(t) def error_line(t) [-1] int( strip( print( error_kind
```

就能拿到 **13/13 通过**——每道题都能用同一招作弊。docstring 同理。

### Fixed

- 新增 `judging.code_for_matching()`：匹配前把**注释**与**语句位置的字符串（docstring）**抹成空格。
  - 用 `tokenize` 按 token 位置精确抹除，而不是正则硬删；
  - **括号内的字符串一律保留**（用括号深度判断）：`{"role": "system"}`、`print("line")` 这类是数据，抹掉会让键名规则反过来判错；
  - `tokenize` 失败时（学习者常提交写了一半的代码）退回保守的行级剥离，**绝不抛异常**。
- 修复后实测：只写注释 → `is_passed=False`；只写 docstring → `False`；完整正确答案仍 **13/13 通过**（无回归）。

### Verified

- 新增 9 条用例（`tests/test_judging_strips_comments.py`）：注释/docstring 被抹、函数体保留、表达式内字符串保留（含多行字典）、坏代码不抛异常、端到端「只写注释判失败」与「真代码仍通过」。
- `158 passed`（单元，+9）/ `140 passed`（集成，**说明没有一道题依赖注释匹配**）/ `ruff` 干净。

### 已知残留（如实记录）

字符串常量里的文本仍参与匹配——把要求塞进字符串依然能骗过静态规则，只是不再是一行注释就能做到。要彻底解决只能引入真正的代码执行，而那与「服务端绝不执行用户代码」的红线冲突，故不做。

### 顺带修正

- README 第 32 行仍写「14 道练习」（实际 22 道），是内容扩充后的漏改。

## [0.1.18] — 2026-11-04

让判题失败时**说人话**：此前学习者只看到「第 4 项必须出现的写法没有出现」，而题面根本没有编号，没人知道「第 4 项」是什么。

### Added

- 迁移 `0014_sprint10_requirement_labels`：`exercises` 新增 `requirement_labels`（jsonb 数组），为**全部 22 道题、124 条判题规则**逐条写中文标签，与 `required_patterns` **一一对应、顺序相同、条数相等**。
- `GET /exercises/{id}` 返回 `requirements`（要求清单）。它复述题面要求，不是答案键；`required_patterns` / `forbidden_patterns` / `expected_output` 仍绝不外泄。
- 练习详情页新增「本题要求」编号清单：判题前就能看到 1..N 条要求，失败时后端按同一编号引用。

### Changed

- 判题失败文案：`第 4 项「用负一索引取报错的最后一行」没有出现`。标签缺失时回退到旧文案，不报错。

### Fixed

- **`tests/test_health.py` 把版本号写死成 `0.1.0`**：这既是每次发版都要改测试的负担，也掩盖了「运行时版本与包版本不一致」——那正是一个存在过 17 个版本的 bug。改为只断言 `body["version"] == __version__`。

### Verified

- 22/22 道题 `len(requirement_labels) == len(required_patterns)`，**0 条不匹配**。
- 真实失败提交：`第 3 项「用负一索引取报错的最后一行」没有出现`（starter 代码实测）。
- 详情响应含 `requirements`（7 条）且**答案键零泄露**。
- 浏览器：`/practice/25` 渲染「本题要求」清单，Console 0 报错。
- `149 passed`（单元）/ `140 passed`（集成）/ `ruff` 干净。

## [0.1.17] — 2026-11-04

给仓库补上**真实截图**，并修掉一个界面长期显示错误版本的 bug。

### Added

- `docs/images/` 下 6 张真实运行截图（1280×800，Chromium，未修图）：今日概览、学习路线、周计划、课程正文、练习页（含复习横幅）、诊断历史。README 由「截图占位」改为图片表格。
- `docs/images/VERSION` 版本戳：截图属于哪个版本一目了然。

### Fixed

- **界面「服务版本」一直显示 `0.1.0`**：`apps/api/app/__init__.py` 里的 `__version__` 从未跟随发布更新，而它同时是 `GET /health` 的 `version` 字段与 OpenAPI 的 `info.version`。已改为 `0.1.17`，重启后 `health version = 0.1.17`、`openapi info.version = 0.1.17`。
- 版本一致性检查从 **3 处扩到 4 处**（新增后端运行时版本）。此前它只比对 `app-version.ts` / `package.json` / `pyproject.toml`，所以第 4 处漂移了 17 个版本都没被发现。

### 关于「截图会过期」的处理

README 原本写「刻意不放截图，避免过期截图冒充当前界面」。这个顾虑是对的，但零截图的仓库几乎没人会 clone。现在改为：**放截图，同时让过期可被发现**——

- `docs-consistency-check.mjs` 读取 `docs/images/VERSION` 与当前版本比对，不一致时打印 `NOTE` 提醒重新截图；
- 只提示、不判失败：重新截图是发布动作，不该拦住每一次代码提交。

### Verified

- 4 处版本号实测一致；`health` 与 `openapi` 都报 `0.1.17`。
- 截图过期提示双向验证：把 `VERSION` 改成 `0.1.10` → 打印 NOTE；改回 → 无提示。
- `.gitattributes` 已有 `*.jpg binary`，`git check-attr text` 确认图片不做换行转换。

## [0.1.16] — 2026-11-04

打通「错题 → 复习 → 练习」的界面闭环：练习页此前不知道自己是不是一道复习题。

### Added

- **`GET /exercises/{id}` 新增 `review` 字段**（无复习项时为 `null`）：`status` / `due` / `streak` / `interval_days` / `next_review_on` / `last_result` / `last_reviewed_at`。
- 练习详情页新增复习横幅：到期时提示「今天就是它的复习日」，未到期时显示「下次复习 YYYY-MM-DD · 当前间隔 N 天 · 连续答对 N 次」，并链接到错题本。

### 设计要点

- `due` 与错题本列表**复用同一个时区口径**（`review.local_today` + `users.timezone`），没有第二套时钟，也不用 UTC 直接比较。
- 查询用同一条 SQL 的 `LEFT JOIN LATERAL ... ORDER BY ri.id DESC LIMIT 1`，不增加往返；唯一约束保证至多一行。
- `status='done'` 仍返回 `review` 块（`due=false`），**只有「没有行」才是 `null`**——不凭猜测造空对象。前端只在 `status='pending'` 时渲染横幅，已完成的复习不会显示成待复习。
- `POST /exercises/{id}/submissions` 的响应、练习列表、迁移与依赖均未改动。

### Verified

- 真实接口：`exercises/2` 返回 pending 行（streak 0 / 间隔 1 天 / 下次 11-05，`due=false` 与 `local_today=11-04` 一致）；`exercises/1` 返回 `review: null`。
- 4 条新集成用例：有行、无行、**跨用户隔离**、`due` 的两条日期边界（今天 / 明天）全部通过。
- 浏览器：打开 `/practice/23` 渲染「这道题在错题本里 / 连续答对 1 次 / 下次复习 2026-11-07 / 当前间隔 3 天」，Console 0 报错。
- `134 passed`（单元）/ `140 passed`（集成）/ `ruff` 干净 / 文档一致性「全部一致」。

## [0.1.15] — 2026-11-04

补上 README 长期承认的一个缺口：**诊断只给分数、不给解析**。

### Added

- 20 道诊断题**全部带解析**（每题 60–80 字），结构统一为「正确答案为什么对（机制/规则）+ 最主要的那一个错项错在哪」，例如：
  - `q01`：切片是左闭右开，起始索引保留、结束索引不包含，所以 `[1:3]` 是 `[2, 3]`；错选 C 的人把右边界当成包含。
  - `q08`：`inner` 里对 `count` 有赋值，Python 就视为局部变量，未赋值先 `+=` 只能抛 `UnboundLocalError`；选 A 的人漏了作用域规则。
- 批次明细页新增「解析」块，逐题显示；提交后才能看到。

### 防泄题与版本

- **发卷接口 `GET /diagnostics/paper` 不含 `explanation` 键**（`paper_questions()` 是逐字段白名单投影），实测响应体既无该键也无任何一条解析原文。
- `question_set_version` / `rule_version` **保持 `v1` / `r1`**：解析不参与评分，升版本会让历史批次的版本语义漂移。
- 契约字段形状不变（仍是 9 个字段），只是取值从 `null` 变成文本。

### Verified

- 20/20 题解析非空、最短 67 字、互不重复、不是抄选项原文。
- 发卷无该键；批次 #2685 明细 20 题解析与题库逐字一致。
- 浏览器实测：打开任一批次，页面渲染 **20 个解析块**，Console 0 报错。
- `134 passed`（单元，新增 5 条解析用例）/ `136 passed`（集成）/ `ruff` 干净 / 文档一致性「全部一致」。
- 同步订正三处已过时的说法：README 能力表与已知限制、`docs/API.md` 第 6 条、`docs/SPRINT1A_CONTRACT.md` 的字段说明。

## [0.1.14] — 2026-11-04

补齐 a2「编程实践」——六个技能域**全部有对应课程**。

### Added

- 迁移 `0013_sprint9_practice_content`：两节已发布课程 + 四道练习，全部离线。
  - `route_a.practice.decompose`「把一段需求拆成几个函数」（a2，30 分钟）：先写「输入→输出」一句话、按动词拆函数、每个函数只做一件事、靠参数与返回值连接而不是全局变量。
  - `route_a.practice.debug`「读懂报错，自己定位」（a2，30 分钟）：Traceback 从最后一行往前读、TypeError / KeyError / IndexError 的典型成因、print 与二分定位、改完怎么验证没改坏别处。
- 课程总数 **11 节**、练习 **22 道**；六域覆盖 a1×5、a2×2、a3/a4/a5/a6 各 1。

### Changed

- 课程列表按 `(stage, order_index)` 排序，因此 a2 两节课（order_index 10/11、stage 2）在界面里落在 a1 之后、a3 之前——播种顺序与展示顺序不同，`test_lessons_api` 把两种顺序分别钉死，而不是放宽断言。

### Verified

- 判题抽验：a2 新题 starter 原样提交 **7/13 判失败**，参考解 **13/13 判通过**（`assessed`）。
- 离线自洽：全库课程与练习的 `prompt`/`starter_code`/`visible_tests` 中 **URL、`api_key`、`sk-` 命中 0**；网络库名称只出现在题面的「禁止使用」说明里。
- 迁移幂等：stamp 回 0012 再 upgrade，两次快照一致（9/18 → 11/22 只增 2 节 4 道）。
- `130 passed`（单元）/ `135 passed`（集成，连跑两遍）/ **全新数据库同样 130 / 135** / 计划用例 12 passed（上一轮的 R10 修复未回退）/ `ruff` 干净 / 文档一致性「全部一致」。
- 浏览器：`/learn` 按 a1→a2→a3→a4→a5→a6 顺序列出 11 节课，Console 0 报错。

## [0.1.13] — 2026-11-04

补齐最后两个技能域的课程，并修掉一个计划排课的真实口径问题。

### Added

- 迁移 `0012_sprint8_rag_agent`：两节已发布课程 + 四道练习（每课 2 道），**完全离线**。
  - `route_a.rag.retrieval`「检索增强：让回答有出处」（a5，30 分钟）：什么是 RAG、为什么切块、用关键词重合度给候选块打分、把命中原文塞进 prompt 并让回答带引用。
  - `route_a.agent.tool`「第一次让模型用工具」（a6，30 分钟）：工具声明的 name/description/参数 schema、模型返回「要调用什么」而不是答案、程序执行后回填、为什么工具必须由程序执行。
- 至此六域里有五域有对应课程（a1 五节、a3/a4/a5/a6 各一节），共 **9 节课 / 18 道练习**。

### Fixed

- **R10「一节课一天一个练习」被实际违反**：此前只把 `scheduled` 行排除在候选之外，学习者跳过某课练习后，下一次重生成会给**同一节课同一天**再排一道新的。现在终态（done/skipped）行同样占满该位——只顾 `done/skipped` 而不把 `scheduled` 算作占位是刻意的：`scheduled` 行必须被重新发出以保持幂等，若也算占位会让它被 `expire` 掉，计划里的练习凭空消失（实测会导致 5 个计划用例失败）。
- **两个计划用例的数据依赖**：`test_sprint6_04` 与 `test_sprint6_07` 跑在种子用户身上，随真实学习历史漂移。改用 `conftest.create_isolated_learner()` 自建用户；`04` 的额度断言也改为按真实最短课时长推导，不再写死 40 分钟。

### Verified

- 新增针对性用例 `test_r10_a_skipped_exercise_does_not_reopen_the_same_lesson_slot`：跳过某课练习后重生成，该课该日必须只有 1 行。
- 判题双向自洽（实测 4 道新题）：starter 原样提交全部 `is_passed=False`，参考解全部 `is_passed=True`。
- 迁移幂等：stamp 回 0011 再 upgrade，两次快照完全一致（9 节课 / 18 道练习）。
- 产品库 `130 passed` + `135 passed`；**全新数据库**同样 `130 / 135`；`ruff` 干净；文档一致性「全部一致」。

## [0.1.12] — 2026-11-04

**产品第一次有了 AI 内容。** 此前 5 节课全是 Python 基础，而六个技能域里有 API 与 LLM——一个叫「AI 学习」的产品没有 AI 课程。

### Added

- 迁移 `0011_sprint7_ai_content`：两节已发布课程 + 四道练习（每课 2 道），**完全离线可学**，不要求网络或 API Key。
  - `route_a.api.json`「请求、响应与 JSON」（a3，25 分钟）：HTTP 方法与状态码、JSON 结构、用 `json.loads` 解析示例响应文本。
  - `route_a.llm.messages`「调用大模型的请求长什么样」（a4，30 分钟）：消息数组与三种角色、`temperature` / `max_tokens`、token 与计费、响应形状、按状态码排错。
- 课程正文与现有 5 节同款六块结构；`common_mistakes` 写成 mistake / why / fix 三段。

### Changed

- 版本号三处来源（`app-version.ts` / `package.json` / `pyproject.toml`）统一到 **0.1.12**。此前界面一直显示 `v0.1.3`——第 5 轮建立的单一来源常量之后从未更新。

### Fixed

- **文档一致性检查器自身的 bug**：`revision` 正则只认 `revision = "..."`，不认新迁移里的 `revision: str = "..."`，导致它把 head 报成旧版本。**检查器给出过期真值是最危险的失败方式**，已修正并加注释。
- 检查器新增「版本号三处必须一致」，并**刻意不检查**「N 节课程 / N 道练习」——这两个数字在文档里既是当前总量、也是 S7 目标（60 节）或规则（至少 6 道、一天最多 1 道），试加后产生 12 条误报。会喊狼的检查器比没有更糟，理由已写进脚本。

### Verified

- 判题双向自洽：starter 原样提交 **7/13 通过（判失败）**；参考解 **14/14 通过**，证据强度 `assessed`。
- 迁移幂等：`0010` 时 5 节 → 首次 head **7 节 / 14 练习** → 再次 head 仍是 **7 / 14**。
- `130 passed`（单元）/ `134 passed`（集成，新增 7 条内容测试）/ `ruff` 干净 / 全新数据库集成档同样 134 passed。
- `scripts/ci.ps1` 十一步全绿；浏览器确认 `/learn` 列出 7 节课、新课程页正常渲染、Console 0 报错、侧栏显示 `v0.1.12`。

## [0.1.11] — 2026-11-04

把依赖告警从「文档里的一句话」变成**可回归的基线**。

### Added

- `apps/web/scripts/audit-check.mjs`：用 npm 自己的语义把两类问题分开——
  - `npm audit --omit=dev` **运行时依赖必须为 0**（硬门禁）；
  - `npm audit` 全量告警数不得高于 `apps/web/security-baseline.json` 的 `dev.total`（当前 16）。
  - 离线时退出码 **2** 并明确打印「本次未做检查」——**不静默跳过**。
- `apps/web/security-baseline.json`：记录 16 个 dev-only 告警的范围、为什么不能用 `--force` 修、以及人工复核结论（逐个看 via 链，均不含 `next`/`react`/`react-dom`）。
- 接入 `scripts/ci.ps1` 的 security 步骤（容忍退出码 2 并给出可见警告），`CONTRIBUTING.md` 与 `SECURITY.md` 列出三个自查脚本。

### Fixed

- `audit-check.mjs` 首次运行报「审计不可用」。根因是 **Node 18.20 起（CVE-2024-27980 修复）默认拒绝执行 `.cmd`/`.bat`**，而 Windows 上 `npm` 就是 `npm.cmd`，`execFileSync` 直接 spawn 会 ENOENT。补 `shell: true` 后正常。这与之前 `Start-Process` 启动不了 `npm` 是同一类问题，只是报错方式不同。
- `scripts/ci.ps1` 里我一度写进中文注释（34 个非 ASCII 字符），会破坏 Windows PowerShell 5.1 的解析；已改回纯 ASCII 并加检测。

### Verified

- 基线匹配：`运行时依赖告警 0 / 全部 16 / 符合基线`，退出码 0。
- 基线调低到 15：打印「开发依赖告警由 15 增加到 16」并退出码 1；恢复后回到 0。
- 三个自查脚本一次性全跑通：文档一致性、依赖基线、死导出（377 个导出 0 个死代码）。

## [0.1.10] — 2026-11-04

把「文档一致性」从人工比对变成**可执行检查**。

### Added

- `scripts/docs-consistency-check.mjs`：零依赖，只读源码树（不需要服务或数据库），从四个来源推导真值并与文档里的数字声明比对——
  - 迁移 head：`revision` / `down_revision` 图里没有后继的那个；
  - 迁移版本数：`migrations/versions` 下的文件数；
  - 业务表数：`CREATE TABLE` 去重后的表名数；
  - 接口操作数：`@router.<verb>` 装饰器数量；
  - 页面路由数：`src/app` 下的 `page.tsx` 数量。
  不一致时按 `文件:行号` 逐条报出并退出码 1。
- 接入 `scripts/ci.ps1`（在 job 之前单独一步）与 `.github/workflows/ci.yml` 的 `web` job（只需要 Node）。

### Verified

- **双向验证**：把 README 的 `15 张业务表` 改成 `16` → 输出 `README.md:7 业务表数 文档写 16，实际 15`、退出码 1；改回 → `文档一致性：全部一致`、退出码 0。
- 工作流用 pyyaml 解析确认结构：`api` 8 步、`web` 7 步（含新增的 `Docs consistency`）。
- `scripts/ci.ps1` 十一步全绿：docs consistency → uv sync --locked → ruff → 迁移 → head 校验 → 130 单元 → 127 集成 → npm ci → tsc → lint → build。

## [0.1.9] — 2026-11-04

文档一致性总检：把 7 份文档与当前实现逐条对齐。**这一轮没有改任何代码**，只改说法。

### Fixed

- **`docs/DATABASE.md` 与实现严重不符**：设计稿里有 4 张**从未建过**的表（`exercise_test_cases`、`mistakes`、`review_tasks`、`projects`），而实际存在的 `review_items`、`capstone_submissions`、`knowledge_sources`、`knowledge_chunks` **完全没写**。新增第 0 节「实现现状（as-built）」：列出实际 15 张表与迁移 head，逐条说明那 4 张设计稿表**被什么替代**（自检用例进 `exercises.visible_tests`；错题本与复习合并为 `review_items`，且间隔是 1/3/7/14 天而**不是**设计稿写的 1/3/7/14/30 天；项目实践改为 `capstone_submissions`），并声明第 4 节仍是冻结设计基线。
- **README 停在 v0.1.1**：迁移写 `0007`（实际 `0010`）、`28 个端点`（实际 37 操作 / 34 路径）、`13 条页面路由`（实际 14）。
- **README 的质量门禁表会误导贡献者**：仍写着集成档「需要预置数据库、在全新数据库上会失败」。该说法自 hermetic 化之后已不成立，现改为「全新数据库同样全绿」。同步补上 CI 的 `ruff check` 步骤与 head 校验。
- `docs/API.md`、`docs/README.md`、`CONTRIBUTING.md`、`docs/PUBLISHING.md`、`docs/BUILD_PLAN.md` 各自的过期版本号、端点计数与提交/标签快照。

### 数据来源（本轮的每个数字都是量出来的）

- 表与迁移：`information_schema.tables` + `migrations/versions/` → 15 张表、10 个版本、head `0010`。
- 端点：`GET /openapi.json` → 34 paths / 37 operations。
- 页面：`find src/app -name page.tsx` → 14 条（Next 构建输出里的 17 含 `_not-found` 等内部条目）。

## [0.1.8] — 2026-11-04

开源发布前的依赖与元数据审计。

### Added

- `SECURITY.md`：安全边界（仅回环、无鉴权是设计取舍、不执行用户代码、Key 不入库不入日志、知识白名单）、依赖告警的**真实情况**、以及任何人都能自己复核的命令。

### Changed

- `apps/api/pyproject.toml`：描述从「Sprint 0 skeleton」改为真实职责，版本对齐 `0.1.7`。
- `apps/web/package.json`：包名 `web` → `ai-learning-copilot-web`，版本对齐 `0.1.7`，补 `license: MIT`；`package-lock.json` 同步重建。

### Fixed

- **`uv.lock` 因 pyproject 元数据变更而失效**：`uv sync --locked` 会直接报 `lockfile needs to be updated`，CI 必红。已执行 `uv lock`（只更新版本行），`uv lock --check` 与 `uv sync --locked` 恢复通过。

### 依赖审计结论（如实记录）

- `npm audit`：**16 个 moderate，全部在 ESLint 开发链**（`minimatch` 经 `eslint-config-next` 传递引入）。
- **运行时依赖干净**：`next` / `react` / `react-dom` / `tailwindcss` 均无告警；生产依赖只有 3 个。
- `npm audit fix`（非 `--force`）无法消除；`--force` 会升到 `eslint-config-next` 不接受的版本、反而破坏 lint。**选择等上游修复并在 `SECURITY.md` 记录，而不是强推。**

### Verified

- `scripts/ci.ps1` 十个步骤全绿，`npm run lint` 输出已显示新包名 `ai-learning-copilot-web@0.1.7`。
- `npm ci` 在新包名下正常工作；`tsc` / `eslint` / `next build` / 死导出检查全部干净。

## [0.1.7] — 2026-11-04

开源前的代码质量收尾：后端补 lint、前端清死代码、修掉工具链里两处会伤到使用者的坑。

### Added

- **后端 ruff**（`E,F,I,UP,B`；`E501` 与实际代码冲突故关闭，`B008` 是 FastAPI `Depends()` 误报）。进入 dev 组、CI 增加一步、`scripts/ci.ps1` 同步。
- **`apps/web/scripts/dead-exports-check.mjs`**：零依赖的死导出自查脚本，发现即退出码 1。已用它清掉 13 个死导出（含删除后级联暴露的 4 个）。

### Fixed

- **`ci.ps1` 在开发服务运行时必然失败**：`npm ci` 会先删 `node_modules`，而 `next start` 正持有 `node_modules/@next/swc-*.node`，`unlink` 报 EPERM，还会把**正在运行的前端一起弄坏**。脚本现在先检查 3000 / 8000 端口，被占用就退出并说明原因。
- 73 处 ruff 问题：64 处自动修复（`datetime.UTC`、过时 typing 导入、导入顺序、未使用导入），9 处手工修复——其中 8 处是此前把 helper 插在 import 语句中间造成的 `E402`。
- 一处测试用裸 `Exception` 断言，改为 `pydantic.ValidationError`。
- 前端产物：删除 `DisabledButton`、`SoonTag`、`IconArrowRight`、`IconCheck`、`isAssistanceLevel`、`parsePlanPreview`、`readLastResult`、`clearLastResult`、`stateTone`、`reviewResultPath` 及随之孤立的类型与常量。

### Verified

- `ci.ps1` 十个步骤全绿（ruff → uv sync --locked → 迁移 → head 校验 → 130 单元 → 127 集成 → npm ci → tsc → lint → build），并在「服务在跑」时正确拒绝执行。
- `next build` 无任何警告，17/17 页面生成；`tsc` / `eslint` 退出码 0；死导出 377 个中 0 个。
- 干净数据库与开发库上后端两档测试均全绿。

## [0.1.6] — 2026-11-04

工程化收尾：让「本地全绿」与「CI 全绿」成为同一件事。

### Added

- `scripts/ci.ps1`：与 `.github/workflows/ci.yml` **完全相同的 9 个步骤**（后端 `uv sync --locked` / 迁移 / head 校验 / 两档 pytest；前端 `npm ci` / `tsc` / `lint` / `build`），任何一步非 0 退出码都会被列出。推送前本地跑一次即可预知 CI 结果。
- `smoke.ps1` 增加环境泄漏提示：若 shell 里残留 `DATABASE_URL`（会覆盖 `.env`），会打印脱敏后的地址，避免出现「明明库是好的却 alembic 连不上」这种难以定位的失败。

### Changed

- `study_plan.generate_plan()` 改为接收显式 `user_id`（`users.get_user` + 路由解析）。此前它内部解析「唯一那个用户」，导致计划相关用例只能跑在真实用户身上、随真实学习数据漂移。新增 `test_study_plan_isolation.py` 用自建用户证明隔离：别的用户生成计划不会改动种子用户的任何行。

### Fixed

- 计划相关测试的断言改为「规则」而非「数据」：历史分钟按增量断言、练习数断言「不超过上限」而不是「必须达到 2」。
- `skill-card.tsx` 残留的未使用导入（ESLint 会报 warning）。
- `apps/web/package-lock.json` 的版本号停留在 0.1.0，已与 `package.json` 对齐到 0.1.3。
- `CONTRIBUTING.md` 一处被改岔的句子。

### Verified

- 全新克隆中执行 `scripts/ci.ps1`：9 步全部 `ok`，末尾输出 `CI-equivalent checks passed.`
- 干净数据库上：`130 passed`（单元）+ `127 passed`（集成）。

## [0.1.5] — 2026-11-04

以学习者身份完整走一遍首次使用流程（诊断 20 题 → 结果 → 计划 → 练习 → 复习 → 作品）时发现的界面缺陷。

### Fixed

- **结果页自相矛盾**：`LEVEL_NAMES[0]` 是「未评估」，任何 `level=0` 都会渲染成「L0 · 未评估」，于是「已测，未达 L1 门槛」旁边印着「未评估」。新增状态感知的 `levelLabelForState`：`level=0` 且 `assessed_below_threshold` 时显示「L0 · 已测未达标」。
- **结果页与档案口径易混**：未达门槛的域显示 L0，但「当前等级」仍保留此前已建立的等级（`assessment_state='established'` 才参与解析）。已在结果页显式说明「下面的等级是本次诊断的结论，不会降低你此前已建立的等级」。
- **产品界面残留开发阶段标签**：`/onboarding`、`/diagnostic`、`/result`、`/history` 上的「Sprint 1 · 第 N 步」全部改为「学习流程 · 第 N 步」。

### Verified

- 诊断全流程实测：20 题作答 → 提交 → `/result` 六域判定；六域正确率 25% / 0% 时均正确显示「已测未达标」，`L0 · 未评估` 出现次数为 0。
- 后端 `130 passed` / `125 passed`；前端 `tsc` / `lint` / `build` 全 0；三个页面浏览器 Console 无报错。
## [0.1.3] — 2026-11-04

补上「结业作品提交」，但**只做能诚实交付的部分**：本版本是单用户本地应用，没有第二个人能评审，所以评审一律是**本人自评**。

### Added

- `capstone_submissions` 表（迁移 `0009`）：`draft → submitted → reviewed` 单向状态机；提交时把四条达标要求的结果**快照存档**，事后可追溯。
- 6 个端点：创建草稿、列表、详情、改草稿（仅 draft）、提交、自评。
- `/projects` 页新增提交表单（标题 / 简介 / 仓库链接 / 运行说明 / 4 项自检清单）与状态展示。

### Changed

- 版本号收敛到单一来源 `apps/web/src/lib/app-version.ts`，界面不再出现三处不同的版本号；`apps/web/package.json` 同步到 0.1.3。

### Fixed

- **数据库约束的三值逻辑漏洞**（迁移 `0010`）：`ck_capstone_submissions_reviewed_complete` 原本写 `reviewer = 'self'`，当 `reviewer` 为 `NULL` 时整条 CHECK 求值为 `NULL`，PostgreSQL 视为通过——实测可以把「已评审但没有评审人」的行写进库。已改为显式 `reviewer IS NOT NULL AND reviewer = 'self'`。
- 列表排序用例依赖库内既有作品数，混入其它数据时位置断言会漂移；改为只对本用例创建的行断言相对顺序。
- 迁移链断言漏了 `0009 → 0010` 一环（批量改 head 常量时误改），已补 `CAPSTONE_REVISION` 常量与断言。

### Verified

- 真实接口序列：创建草稿 → 提交（快照 `ready=false`、四条要求齐全）→ 重复提交 409 `CAPSTONE_INVALID_STATE` → 未确认自评 400 `SELF_REVIEW_NOT_CONFIRMED` → 非法 verdict 422 → 确认自评 200（`reviewed / pass / self`）。
- 数据库层实测：`UPDATE ... SET reviewer = NULL` 与 `reviewer = 'human'` 均被约束拒绝。
- 默认档 `130 passed`；集成档 `125 passed`；**全新数据库**上 `125 passed`。
## [0.1.2] — 2026-11-04

补上「错题本与间隔复习」——`review_items` 此前恒为 0，周计划里 `kind='review'` 从不生成。新增一张表（迁移 `0008_review_items`），其余表零变化。

### Added

- `review_items` 表：`UNIQUE (user_id, exercise_id)`、`(user_id, next_review_on)` 索引、`status ∈ {pending, done}`；**行永不删除**，`done` 只是状态。
- 间隔调度：答错 → `streak=0`、1 天、明天；答对 → `3 → 7 → 14` 天，连续 3 次通过置 `done`；答对但无复习行时不建行。
- `GET /review/items`、`POST /review/items/{id}/result`、`GET /review/summary` 三个端点；「今天」按 `users.timezone`。
- `/review` 页面：复习概览四指标 + 「今天到期」与「全部待复习」两区块，每行显示连续通过次数、当前间隔、下次复习日期。
- 周计划新增 `kind='review'` 排程，并在导航与计划页显示「复习」徽章与「去复习 →」。

### Changed

- **排课顺序改为「课程 → 复习 → 新练习」**。原顺序（课程 → 练习 → 复习）实测导致 `review_items` 恒为 0：每天 30 分钟课 + 15 分钟练习正好用满 45 分钟额度，复习永远抢不到余量。改后到期复习优先占位，代价是当天可能没有新练习——这是刻意的取舍。
- 已排的复习行在每轮生成里原地重生，避免 `expire` 与下一次生成之间来回抖动。

### Verified

- 真实接口序列：答错 → 2026-11-05 → 答对 → 11-07 → 11-11 → 11-18 且 `done`；再次答错正确重置为明天。
- 真实生成：`review=1`（此前恒 0），11-04 为「30 分钟课 + 15 分钟复习」，原本那天的练习转为 `expired`，四天 `total` 仍全部 = 45。
- 默认档 `130 passed`；集成档 `110 passed` ×2；**全新数据库**上 `110 passed`，临时库用后即删。

### Known limitations

- **逾期复习不进周计划**：候选窗口是 `next_review_on ∈ [今天, 本周日]`，已逾期的错题只在 `/review` 页出现。
- `kind='review'` 的 `target_id` 只由服务层校验（迁移 0007 的触发器只覆盖 lesson/exercise，本轮未改迁移）。

## [0.1.1] — 2026-11-04

把所有「演示数据」占位换成由真实学习记录推导的页面。**没有任何新表、没有新迁移**。

### Added

- `GET /api/v1/progress/overview`：课程进度（含已完成分钟）、本周计划（完成 / 跳过 / 排期与分钟）、练习与证据分布（`static_rule` / `self_report` / `none`）、六域能力等级与均值、最近 7 天活动（缺失日期补 0）。
- `GET /api/v1/capstone/readiness`：四条结业要求（完成 5 节课程 / 通过 ≥6 道练习 / ≥3 个能力域达到 L2 / 完成 ≥5 个计划任务），`ready` 由四条判定全真推导；响应中的 `note` 明确声明作品提交与人工评审流程尚未实现。

### Changed

- `/progress` 重写：四张真实数据卡 + 7 天活动条形，删除全部 `DemoTag` 与「演示数据」文案。
- `/projects` 重写：展示四条要求的 `actual / required / met` 与总体状态，并原样显示后端 `note`；原「三个候选项目」演示列表移除。
- 前端解析遵循「缺失 ≠ 0」：字段缺失渲染「—」，分组缺失显示「后端未返回」，不补零、不估算；分母缺失时不渲染比例条。
- 导航摘要与页脚版本号更新为 v0.1.1 口径。

### Verified

- 端点数字与库内 SQL 逐项对账：`lessons 2 / 45 分钟`、`plan scheduled 6 / done 1 / skipped 1 / 20 / 135 分钟`、`submissions 12 / 去重练习 2 / 通过 1`、`by_evidence 7+5`、`平均等级 1.6 / 6 域`。
- 全新数据库上 `130 passed`（单元档）+ `95 passed`（集成档），临时库跑完已删除，`apps/web/src` 内 `DemoTag` 与「演示数据」命中 **0**。

## [0.1.0] — 2026-11-04

第一个可用版本。零基础学习者可以走完「能力诊断 → 课程学习 → 编程练习 → AI 导师 → 知识检索 → 周计划」这条闭环，全部数据落在本地 PostgreSQL。

数据库迁移：`0001` → `0007`（head `0007_sprint6_plan_exercise_targets`），14 张业务表；26 个 HTTP 端点，文档见 `docs/API.md`。

### Added

- **能力诊断**（Sprint 1B）：20 道固定题库（`GET /diagnostics/paper` 为唯一来源，前端不再内置题库），六域计分，作答明细可回看；**只授予 L0–L2，永不授予 L3/L4**。
- **用户档案**：时区、学习日、每日分钟；`study_days` 有唯一性触发器，`weekly_minutes` 为生成列。
- **课程与进度**（Sprint 2）：5 节 Python 课程（变量 / 条件循环 / 列表字典 / 函数 / 调试），进度单向（`not_started → in_progress → completed`），课程自评只写 `learning_progress`，绝不写 `user_skill_levels`。
- **周计划**（Sprint 2 + Sprint 6）：按学习日与每日预算排课，`scheduled → done|skipped` 终态只读；Sprint 6 起把**练习**一并排入（`kind='exercise'`，目标必须是真实 `exercises.id`，含数据库触发器校验），每日练习上限随能力等级变化。
- **练习与判题**（Sprint 3）：10 道练习（每节课 2 道），代码编辑器零依赖，判题只有两条通道——`static_rule`（静态规则，标「已验证（静态规则）」）与 `self_check`（自检，标「未验证（自检）」）；**服务端从不执行用户代码**，任何判定都不写 `user_skill_levels`。
- **AI 导师**（Sprint 4）：接入 DeepSeek（`POST /ai/tutor`），四档提示依赖（`none/hint/partial_code/full_answer`）；无 Key 时 `503 AI_UNAVAILABLE` 且**不发起任何上游请求**，超时 504、超配额 429；每次尝试都写一行 `ai_interactions` 台账，便于成本与失败追溯；密钥只从环境读取，永不入库、入日志、入响应。
- **知识检索**（Sprint 5）：白名单入库（仅 `docs.python.org` 与仓库内课程，服务端强制域名校验）、关键词打分检索、每条结果带 `fetched_at` 与过期标记；AI 回答带 `citations[]` 引用；入库端点默认关闭。
- **运维与开源就绪**：`scripts/start-dev.ps1`（一键起库 + 迁移 + API + Web）、`scripts/smoke.ps1`（17 项只读自检）、`docs/API.md`、`CONTRIBUTING.md`、`.github/workflows/ci.yml`、`docs/reports/` 历史报告归档。

### Changed

- 预算口径修正：历史终态（done/skipped）分钟**仍计入**当日已分配预算，`total_minutes <= daily_minutes` **只在生成那一刻成立**；事后调小每日额度会超限，界面必须提示而不是宣称恒成立。
- 进度写入改为**数据库层原子条件更新**（等级比较 + `GREATEST`/`COALESCE`），并发请求不再可能把 `completed` 回退成 `in_progress`。
- 课程完成同步**限定当周**（按用户时区的周一），不再误改历史周次或终态行。

### Fixed

- 并发写入导致的学习进度回退（应用层判断 → 数据库条件更新）。
- 完成课程时误标其他周次计划项为 done。
- 中文检索召回为 0：分词只按非字母数字切分，中文整句变成一个词；现改为 **CJK 二元组**，中文提问可正常召回。
- AI 引用重复：同一页面的多个命中块曾显示成多条相同来源；现按 URL 去重。
- 前端把接口地址当页面路由用（练习卡片曾链到 `/api/v1/exercises/{id}`，Next 预取产生 5 条 404）。
- 自检字段无条件发送，导致静态规则判题永远不执行（未勾选时必须不发送 `self_reported_passed`）。
- 干净库迁移回归用例使用固定探针库名，两个进程并发跑必互删；改为 `pid + uuid` 唯一库名。

## Sprint 1 准入审查（2026-11-03）

审查基线 `f06dab4`。本轮不开发业务功能，只做复验、口径修正与安全加固。

### Added

- `docs/DATABASE.md`：新增第 14 张表 `study_plan_items`（周计划任务），含唯一约束 `uq_study_plan_items_dedupe (user_id, dedupe_key)`，用于保证「同一周重复生成不产生重复任务」。
- `docs/DATABASE.md`：`user_skill_levels` 新增证据溯源五字段 `source`、`evidence_strength`、`verification_status`、`evidence_ref`、`evidence_count`，使能力等级可追溯来源。
- `docs/DATABASE.md`：`exercises` 新增 `kind`（`practice` / `transfer`），作为 L4「迁移应用」的判定依据。
- `docs/PRD.md`：六种提交情况唯一取值表、学习时间规则 R1–R6、Sprint 顺序表、新增验收条件 AC-31…AC-35。
- `docs/ROADMAP.md`：新增 §10.1「安全代码执行方案评估」（四方案 × 五维度），并补齐 `AC-S7-07/08/09`。
- `README.md`：新增本地监听约定（三端口仅回环）。
- `REVIEW_REPORT.md`、`TEST_RESULTS.md`、`CHANGELOG.md`：审查交付文档。

### Changed

- `docs/PRD.md`、`docs/ARCHITECTURE.md`、`docs/DATABASE.md`、`docs/ROADMAP.md`：能力等级口径统一为「初步诊断只授予 L1/L2；L3 需同域 ≥3 次不同题目且 `ai_assistance_level='none'` 且 `verification_status='verified'`；L4 需迁移任务且状态一律 `pending_review`」。
- 提示依赖收敛为 3 列可写（`is_passed`、`verification_status`、`ai_assistance_level`）+ 2 个 PostgreSQL 生成列（`used_ai`、`passed_with_ai`）；`has_prompt_dependency` 不再落库，改为 `EXISTS ai_interactions` 查询派生。
- `user_profiles`：`weekly_minutes` 改为生成列，新增 `study_days`、`daily_minutes`；`users.timezone` 明确为「今日/本周」唯一边界。
- Sprint 顺序重排：S1 用户档案与能力诊断 → S2 学习路线与课程 → S3 练习与判题 → S4 AI 导师与提示依赖 → S5 错题本与复习 → S6 项目与进度 → S7 打磨与开源。八个功能需求一条未删。
- 课程掌握度默认值由 L1 改为 **L0（未评估）**；仍允许自评 L0–L4，但必须标注「自评，未经验证」，且永不写入 `user_skill_levels`、不作技能域等级证据。
- `docs/ARCHITECTURE.md`：拓扑图与端口表统一为 `127.0.0.1:3000` / `127.0.0.1:8000` / `127.0.0.1:5432`；新增判题能力边界表与两条硬约束。

### Fixed

- **安全**：`apps/web/package.json` 的 `dev` 与 `start` 脚本增加 `-H 127.0.0.1`。修复前 Next.js 默认绑定 `0.0.0.0:3000` 与 `[::]:3000`，使**无认证**的本地前端暴露到局域网；修复后实测只监听 `127.0.0.1:3000`。
- 修复「用了 AI 却可记为完全独立完成」的数据漏洞：`ai_assistance_level` 与 `used_ai` 之间原本没有约束，现在由生成列表达式在数据库层保证一致。
- 修复 `docs/ARCHITECTURE.md` 中 api 监听 `0.0.0.0:8000` 的错误描述（与 uvicorn 默认值及自身端口表均矛盾）。
- 统一 `study_plan_items` 四个字段为 `NOT NULL`（PRD / ROADMAP 原为可空），否则 R1 求和与 R5 可解释性无法判定。

### Removed

- `submissions.has_prompt_dependency` 列（改为查询派生，避免与 `ai_interactions` 形成两个事实源）。
- 课程掌握度默认 L1 的假设（改为 L0 未评估）。

### 备注

- 本轮未修改任何业务代码（唯一代码改动为启动脚本参数）；未新增依赖；未执行 git 提交或推送；数据库业务表仍为 0 张。

## Sprint 0（2026-11-03）

初始骨架：

- 前端 Next.js 16 App Router + React 19 + TypeScript + Tailwind 4，五个页面（今日 / 学习 / 练习 / 项目 / 进度）、侧边导航、深浅色三态主题、系统状态组件。
- 后端 FastAPI + uv（Python 3.12），`GET /api/v1/health` 与 `GET /api/v1/ready`，请求日志中间件、CORS 白名单、Alembic 空基线迁移。
- 本地基础设施：`infra/docker-compose.yml` 提供 PostgreSQL 17（仅绑定 `127.0.0.1:5432`）。
- 文档五份（PRD / ARCHITECTURE / DATABASE / ROADMAP / DESIGN_SYSTEM）与 README。