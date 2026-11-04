# AI Learning Copilot — 后续搭建规划（Sprint 4–7）

> 依据：当前仓库状态（Sprint 0–3 已完成：骨架 → 诊断 → 课程与周计划 → 练习系统）。
> 本规划回答三件事：**怎么跑通、怎么接入 API、怎么自主检索最新知识**。

## 0. 当前真实基线（本轮实测，不是回忆）

| 项 | 状态 |
|---|---|
| 迁移 | `0004_sprint3_exercises`（head），11 张表 |
| 后端 | FastAPI：health/ready、诊断、课程、周计划、练习判题 共 15+ 端点 |
| 前端 | Next.js 16：`/` `/learn` `/learn/[id]` `/onboarding` `/diagnostic` `/result` `/plan` `/history` `/practice` `/practice/[id]` |
| 数据 | lessons 5、exercises 10、submissions 12、user_skill_levels 30（L3+ = 0） |
| 测试 | 后端 80 常规 + 70 集成；前端 tsc/lint/build + 18 条规则断言 |
| **缺口** | DeepSeek 未接入（key 为空）、无知识检索、无任务规划引擎、无 AI 导师 |

## 1. 目标拆解（把一句话目标变成可验收的四步）

| 目标原文 | 拆成可验收能力 | 所属 Sprint |
|---|---|---|
| 确保项目可以跑通 | 一条命令起 DB/API/Web；健康检查全绿；10 条页面可访问 | S3 已完成，本轮补「一键启动 + 自检脚本」 |
| 能够接入 api | DeepSeek 客户端、超时/重试/降级、用量与费用记录、无 key 时不崩 | **S4** |
| 能够自主检索最新的知识 | 知识库入库（可刷新）+ 关键词检索 + 引用展示 + 新鲜度标记 | **S5** |
| 规划任务合理 | 周计划 + 任务优先级 + 学习节奏调整（基于掌握度与时间预算） | **S6** |
| 初学者自学 AI 项目 | 端到端学习闭环 + 可展示作品 + 开源就绪 | **S7** |

## 2. Sprint 4：DeepSeek AI 导师（第一个 API 接入点）

**目标**：用户在练习或课程页可以问 AI 导师；回答带提示依赖等级；无 key 时明确降级而不是崩。

| 项 | 设计 |
|---|---|
| 配置 | `DEEPSEEK_API_KEY` / `DEEPSEEK_BASE_URL` / `DEEPSEEK_MODEL`（默认 `deepseek-flash`）/ `DEEPSEEK_MODEL_COMPLEX`；全部从环境变量读，**不落库、不进日志** |
| 端点 | `POST /api/v1/ai/tutor`（非流式先行）、`GET /api/v1/ai/interactions`（历史） |
| 提示依赖 | 请求带 `assistance_level ∈ none/hint/partial_code/full_answer`；写入 `ai_interactions`；练习提交时沿用既有 `max()` 规则 |
| 失败处理 | 无 key → 503 `AI_UNAVAILABLE`；上游超时（默认 30s）→ 504；429 → 退避 1 次后 503；错误体统一 |
| 成本控制 | 每次记录 `prompt_tokens/completion_tokens/latency_ms`；单日 token 上限可配（默认 50k），超限 429 `AI_QUOTA_EXCEEDED` |
| 安全 | 只在服务端持有 key；不把用户代码发到上游之外；日志脱敏 |
| 测试 | 无 key 503、超时 504、正常 200（用**本地 stub 传输层**，不打真实网络）、用量上限 429、日志不含 key |

**验收**：无 key 时全站仍可用；配置 key 后 `POST /ai/tutor` 返回真实模型回答并写入 `ai_interactions`；token 用量可查。

## 3. Sprint 5：知识检索（"最新的知识"）

**关键取舍**：不引入向量库与嵌入模型（会带来新依赖与费用）。先用**关键词 + BM25 风格打分**，够用且可解释。

| 项 | 设计 |
|---|---|
| 表 | `knowledge_sources`（来源/版本/抓取时间/内容 hash）、`knowledge_chunks`（段落切片 + 关键词索引） |
| 入库 | `POST /api/v1/knowledge/ingest`（仅本地/管理员开关开启时可用）+ CLI 脚本；来源白名单（如官方文档页面、仓库内课程） |
| 检索 | `GET /api/v1/knowledge/search?q=` → 返回 chunk + 来源 + 抓取时间 + 相似度分 |
| 新鲜度 | 每条结果标注 `fetched_at` 与 `source_version`；过期阈值（默认 30 天）标「可能过期」 |
| 与 AI 结合 | AI 导师回答时先检索，命中则作为引用注入 prompt，并在响应里返回 `citations[]` |
| 测试 | 入库幂等（内容 hash 去重）、检索排序、过期标记、无结果空态、引用可追溯 |

**验收**：能回答「Python 3.13 有什么新特性」这类问题并给出**带来源与抓取时间**的引用；离线时检索仍可用。

## 4. Sprint 6：任务规划引擎

- 输入：六域等级、课程/练习完成度、`study_days`/`daily_minutes`、时区。
- 输出：本周计划（lesson + exercise 两类真实 target）、每日 rationale、超支保护。
- 与 S2 的区别：**加入练习**，并按掌握度调整配比（L0→课程为主，L2→练习为主）。
- 测试：预算、学习日、幂等、done/skipped 不可改写、等级驱动的配比变化。

## 5. Sprint 7：收尾与开源就绪

- 一键启动脚本、烟雾自检、示例 `.env`、贡献指南、CI（本地可跑）。
- 全量回归 + 浏览器端到端 + 文档一致性 sweep。

## 6. 需要你决定的两件事

1. **DeepSeek API Key**：当前 `.env` 里 `DEEPSEEK_API_KEY` 为空。我可以在**没有任何 key** 的情况下把接入代码、降级与 stub 测试全部做完并验证；但「真的调用一次模型」必须等你提供 key。
2. **知识来源白名单**：默认只抓官方文档与仓库内课程。若你希望加入特定站点（如某教程站），需要你指定，我不会擅自扩大抓取范围。

## 7. 本轮（Round 1）会做什么

1. 恢复 Docker/PostgreSQL，确认项目重新跑通（含一次全量测试）。
2. 产出本规划文档。
3. 开始 Sprint 4：DeepSeek 客户端 + 端点 + 降级 + stub 测试（不依赖真实 key）。
4. 补「一键启动 + 烟雾自检」脚本，降低跑通成本。