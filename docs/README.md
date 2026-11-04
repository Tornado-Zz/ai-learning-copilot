# 文档索引

本目录是本项目的**设计与过程记录**集合。产品代码在 `apps/`，仓库入口见根目录 [README.md](../README.md)。

## 1. 设计与契约（当前有效，随时可读）

| 文档 | 内容 | 什么时候读 |
| --- | --- | --- |
| [GETTING_STARTED.md](GETTING_STARTED.md) | 第一次使用：从空数据库到交出第一个作品，每步的预期结果与耗时 | 第一次跑起来之后，想知道接下来点什么 |
| [PRD.md](PRD.md) | 产品定位、痛点、MVP 范围、用户故事、可验证验收条件、指标 | 想知道「为什么做这个产品」 |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 前后端架构、模块边界、数据流、DeepSeek 调用流程、错误码与安全 | 想知道「系统怎么拼起来的」 |
| [DATABASE.md](DATABASE.md) | 数据模型设计、ER 图、索引、约束清单、迁移策略 | 想改表结构之前 |
| [ROADMAP.md](ROADMAP.md) | 各 Sprint 的分步计划与逐条验收条件 | 想知道「下一步做什么」 |
| [DESIGN_SYSTEM.md](DESIGN_SYSTEM.md) | 视觉风格、颜色/字体/布局令牌、组件与交互规范 | 改前端界面前 |
| [SPRINT1A_CONTRACT.md](SPRINT1A_CONTRACT.md) | Sprint 1A 冻结契约：等级证据分层、L0 两态、JSONB 形态、API 契约 | 查接口口径与错误码来源 |
| [BUILD_PLAN.md](BUILD_PLAN.md) | 建设计划（阶段划分与交付定义） | 想知道「整体节奏」 |
| [API.md](API.md) | **v0.1.0 全部 26 个端点的实测清单**、统一错误体、`request_id` 说明 | 调接口时 |

## 2. 过程记录（reports/，历史存档，不再修订）

`docs/reports/` 下是各阶段的交付报告与测试记录。它们是**当时那一刻的实测快照**：
命令与数字只对当时的工作树与数据库 head 成立，**不要拿它们当当前状态的说明**。
当前状态以根目录 [README.md](../README.md) 与 [API.md](API.md) 为准。

| 报告 | 阶段 | 记录了什么 |
| --- | --- | --- |
| [reports/REVIEW_REPORT.md](reports/REVIEW_REPORT.md) | Sprint 1 准入审查（基线 `f06dab4`） | 以重新执行命令 + 源码抽查方式对 Sprint 0 交付做准入判定 |
| [reports/TEST_RESULTS.md](reports/TEST_RESULTS.md) | Sprint 1 准入审查轮 | 该审查轮实际执行的命令与原始输出；配套上一行 |
| [reports/SPRINT1A_DECISIONS.md](reports/SPRINT1A_DECISIONS.md) | Sprint 1A 契约冻结 | 本轮全部决策与逐条理由；只改文档，不写业务代码、不执行迁移 |
| [reports/SPRINT1A_TEST_RESULTS.md](reports/SPRINT1A_TEST_RESULTS.md) | Sprint 1A 契约冻结 | 约束测试清单的执行记录与文档校对命令 |
| [reports/SPRINT1B_REPORT.md](reports/SPRINT1B_REPORT.md) | Sprint 1B 身份与诊断 | 学习档案、20 题诊断、六维能力画像、学习路线预览的实现交付说明（迁移 `0002`） |
| [reports/SPRINT1B_TEST_RESULTS.md](reports/SPRINT1B_TEST_RESULTS.md) | Sprint 1B | 该轮实际执行的命令与结果；前端路由树、Pytest 两档数字的原始出处 |
| [reports/SPRINT2_REPORT.md](reports/SPRINT2_REPORT.md) | Sprint 2 计划与课程 | 阶段 A（Sprint 1B 问题修复）+ 阶段 B（课程 / 进度 / 周计划）交付说明（迁移 `0003`） |
| [reports/SPRINT2_TEST_RESULTS.md](reports/SPRINT2_TEST_RESULTS.md) | Sprint 2 | 该轮实测记录，数据库 head 为 `0003_sprint2_lessons_and_plan` |
| [reports/SPRINT2_PATCH_REPORT.md](reports/SPRINT2_PATCH_REPORT.md) | Sprint 2 复审补丁 | P1-01~P1-05 + P2-01 的定点修复说明 |
| [reports/SPRINT2_PATCH_TEST_RESULTS.md](reports/SPRINT2_PATCH_TEST_RESULTS.md) | Sprint 2 复审补丁 | 该补丁轮的实测命令与退出码 |
| [reports/SPRINT3_REPORT.md](reports/SPRINT3_REPORT.md) | Sprint 3 练习与判题 | 阶段 A（复审修复）+ 阶段 B（最小编程练习系统，静态规则判题、不执行用户代码）（迁移 `0004`） |
| [reports/SPRINT3_TEST_RESULTS.md](reports/SPRINT3_TEST_RESULTS.md) | Sprint 3 | 该轮实测记录，区分「本机执行通过 / 只做静态审查 / 未执行」三类 |

> Sprint 4（AI 导师）与 Sprint 5（知识库）没有单独的过程报告文件，
> 变更摘要记录在根目录 [CHANGELOG.md](../CHANGELOG.md)，接口口径以 [API.md](API.md) 为准。

## 3. 约定

- `docs/reports/` 只增不改：报告是历史证据，发现问题请在新报告或 `CHANGELOG.md` 里记录，不要回改旧报告里的数字。
- 报告里出现的绝对路径（如 `F:\ai自学产品\...`）是当时那台开发机的路径，跨机器阅读时请自行替换为你的仓库根。
- 冻结契约（`SPRINT1A_CONTRACT.md`）与实现不一致时，以**实现 + API.md**为准，并在 `CHANGELOG.md` 记一笔差异。
