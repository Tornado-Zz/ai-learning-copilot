import type { ApiFailure } from "@/lib/http";

// Sprint 4 冻结契约（DeepSeek AI 导师面板）。
// 前端只做三件事：把「问题 + 提示依赖等级 + 课程/练习 id」交给后端、渲染回答、渲染最近交互。
// 密钥只存在于服务端环境变量：前端不读取、不拼接、不发送、不展示任何 key；
// 请求体不含用户代码全文——题目名与学习目标由后端按 context 里的 id 解析。

export const AI_TUTOR_PATH = "/api/v1/ai/tutor";
export const AI_INTERACTIONS_PATH = "/api/v1/ai/interactions";

// 后端 AI_TIMEOUT_SECONDS 默认 30s；客户端多留 5s，让服务端的 504 AI_TIMEOUT 先到达，
// 而不是被浏览器先 abort 成「服务未就绪」。
export const AI_TUTOR_TIMEOUT_MS = 35000;

// 区块内只展示最近 5 条交互（接口本身支持 limit，这里同时再裁一次，防止后端忽略 limit）。
export const AI_HISTORY_VISIBLE = 5;
export const AI_HISTORY_QUERY = "?limit=5";

// 回答区的固定提示：AI 回答不是学习证据，且 hint 及以上会降低提示依赖等级。
export const AI_EVIDENCE_NOTICE =
  "AI 回答不是学习证据；使用 hint 及以上会降低本次练习的提示依赖等级";

// 产物文案按冻结契约写死，不在页面里二次改写。
export const AI_UNAVAILABLE_NOTICE = "未配置 DEEPSEEK_API_KEY，AI 导师暂不可用";
export const AI_UNAVAILABLE_HINT =
  "配置方式：在服务端环境变量（.env）中填写 DEEPSEEK_API_KEY 后重启后端；本页不会、也无法接收或保存密钥。";

export const AI_QUESTION_MIN = 1;
export const AI_QUESTION_MAX = 2000;

export type AssistanceLevel = "none" | "hint" | "partial_code" | "full_answer";

export const DEFAULT_ASSISTANCE_LEVEL: AssistanceLevel = "hint";

export type AssistanceLevelOption = {
  value: AssistanceLevel;
  label: string;
  description: string;
};

// 四个等级的固定文案映射；选择器、回答区、历史三处共用，避免文案漂移。
export const ASSISTANCE_LEVEL_OPTIONS: AssistanceLevelOption[] = [
  {
    value: "none",
    label: "none · 不给提示",
    description: "只解释概念与判断方向，不点出本题该怎么改。",
  },
  {
    value: "hint",
    label: "hint · 提示",
    description: "指出卡住的位置与下一步，不给可粘贴的代码（默认等级）。",
  },
  {
    value: "partial_code",
    label: "partial_code · 部分代码",
    description: "给出片段或骨架，关键行留空由你自己补全。",
  },
  {
    value: "full_answer",
    label: "full_answer · 完整答案",
    description: "给出可直接抄写的完整实现，对本练习的证据价值最低。",
  },
];

export function assistanceLevelLabel(level: string): string {
  for (const option of ASSISTANCE_LEVEL_OPTIONS) {
    if (option.value === level) {
      return option.label;
    }
  }
  return level ? level + " · 未知等级" : "未返回等级";
}

export function assistanceLevelRisk(level: string): string {
  if (level === "none") {
    return "none：只讲思路，不降低提示依赖等级。";
  }
  return "询问即记录：本次交互按「" + assistanceLevelLabel(level) + "」落库，会降低本次练习的提示依赖等级。";
}

export type AiUsage = {
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
};

// Sprint 5：citations[] 由后端给出 {title, url, fetched_at, stale}。
// 检索是纯 DB 操作，后端检索失败时会降级成空数组，因此这里只负责渲染，不推断失败原因。
export type AiCitation = {
  title: string;
  url: string;
  fetchedAt: string | null;
  stale: boolean;
};

export type AiTutorAnswer = {
  interactionId: string | null;
  answer: string;
  model: string;
  assistanceLevel: string;
  usage: AiUsage;
  latencyMs: number | null;
  citations: AiCitation[];
};

export type AiInteractionRecord = {
  interactionId: string | null;
  createdAt: string | null;
  assistanceLevel: string;
  model: string;
  totalTokens: number | null;
  status: string;
};

// ai_interactions.status 的值域（冻结契约）。失败状态在界面上用中性色，不用红色告警色。
const AI_STATUS_LABELS: Record<string, string> = {
  ok: "成功",
  error: "失败",
  timeout: "超时",
  unavailable: "未配置",
  quota: "超额",
};

export function aiStatusLabel(status: string): string {
  return AI_STATUS_LABELS[status] ?? (status ? status : "未知");
}

export function aiStatusIsOk(status: string): boolean {
  return status === "ok";
}

export type TutorRequestBody = {
  question: string;
  assistance_level: AssistanceLevel;
  context?: { lesson_id?: number; exercise_id?: number };
};

// 后端课程/练习 id 是 int（schemas/lessons.py、schemas/exercises.py），路由参数是字符串。
// 只在纯数字时转成 number 放进 context；否则整个 context 字段不发，避免用假 id 触发 422。
export function numericId(value: string | number | null | undefined): number | null {
  if (typeof value === "number") {
    return Number.isInteger(value) && value > 0 ? value : null;
  }
  if (typeof value !== "string") {
    return null;
  }
  const trimmed = value.trim();
  if (!/^[0-9]+$/.test(trimmed)) {
    return null;
  }
  const parsed = Number.parseInt(trimmed, 10);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
}

// 请求体只由这三个字段构成：question、assistance_level、context（id）。
// 任何代码/编辑器内容都进不来——组件不读取、也不持有编辑器里的代码。
export function buildTutorBody(
  question: string,
  level: AssistanceLevel,
  ids: { lessonId?: string | number | null; exerciseId?: string | number | null },
): TutorRequestBody {
  const body: TutorRequestBody = { question, assistance_level: level };
  const context: { lesson_id?: number; exercise_id?: number } = {};
  const lessonId = numericId(ids.lessonId);
  const exerciseId = numericId(ids.exerciseId);
  if (lessonId !== null) {
    context.lesson_id = lessonId;
  }
  if (exerciseId !== null) {
    context.exercise_id = exerciseId;
  }
  if (context.lesson_id !== undefined || context.exercise_id !== undefined) {
    body.context = context;
  }
  return body;
}

export function validateQuestion(text: string): string | null {
  // 只裁首尾空白后计数，与服务端 1..2000 的口径一致；正文里的换行原样保留。
  const trimmed = text.trim();
  if (trimmed.length < AI_QUESTION_MIN) {
    return "问题不能为空：先写下你卡住的具体位置。";
  }
  if (trimmed.length > AI_QUESTION_MAX) {
    return "问题不能超过 2000 字，当前 " + String(trimmed.length) + " 字。";
  }
  return null;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function asArray(value: unknown): unknown[] | null {
  return Array.isArray(value) ? value : null;
}

function readString(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }
  return null;
}

function readNumber(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function readTokenCount(record: Record<string, unknown>, keys: string[]): number | null {
  const value = readNumber(record, keys);
  if (value === null || value < 0) {
    return null;
  }
  return Math.round(value);
}

// 单条引用：object 形式按 {title, url, fetched_at, stale} 读；没有标题的行直接丢弃。
// 兼容旧版后端返回的纯字符串引用（没有链接，只作为标题展示），不在前端编造 url 或抓取时间。
function parseCitation(value: unknown): AiCitation | null {
  if (typeof value === "string") {
    const title = value.trim();
    return title.length > 0 ? { title, url: "", fetchedAt: null, stale: false } : null;
  }
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const title = readString(record, ["title", "heading"]);
  if (title === null) {
    return null;
  }
  return {
    title,
    url: readString(record, ["url"]) ?? "",
    fetchedAt: readString(record, ["fetched_at", "fetchedAt"]),
    stale: record.stale === true,
  };
}

// POST /api/v1/ai/tutor 的 200 响应。answer 为空视为结构不符（返回 null），页面显示契约错误态，
// 不伪造回答；usage 缺字段时按 0 显示并在界面上注明「后端未返回」。
export function parseTutorAnswer(payload: unknown): AiTutorAnswer | null {
  const record = asRecord(payload);
  if (!record) {
    return null;
  }
  const answer = readString(record, ["answer"]);
  if (answer === null) {
    return null;
  }
  const usageRecord = asRecord(record.usage);
  const promptTokens = usageRecord ? readTokenCount(usageRecord, ["prompt_tokens", "promptTokens"]) : null;
  const completionTokens = usageRecord
    ? readTokenCount(usageRecord, ["completion_tokens", "completionTokens"])
    : null;
  const totalTokens = usageRecord
    ? readTokenCount(usageRecord, ["total_tokens", "totalTokens"])
    : null;
  const citations: AiCitation[] = [];
  const rawCitations = asArray(record.citations);
  if (rawCitations) {
    for (const item of rawCitations) {
      const citation = parseCitation(item);
      if (citation) {
        citations.push(citation);
      }
    }
  }
  const rawId = record.interaction_id ?? record.interactionId ?? record.id;
  return {
    interactionId:
      typeof rawId === "string" || typeof rawId === "number" ? String(rawId) : null,
    answer,
    model: readString(record, ["model"]) ?? "",
    assistanceLevel:
      readString(record, ["assistance_level", "assistanceLevel"]) ?? DEFAULT_ASSISTANCE_LEVEL,
    usage: {
      promptTokens: promptTokens ?? 0,
      completionTokens: completionTokens ?? 0,
      totalTokens: totalTokens ?? (promptTokens ?? 0) + (completionTokens ?? 0),
    },
    latencyMs: readNumber(record, ["latency_ms", "latencyMs"]),
    citations,
  };
}

function parseInteraction(value: unknown): AiInteractionRecord | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const status = readString(record, ["status"]);
  if (status === null) {
    return null;
  }
  const rawId = record.id ?? record.interaction_id ?? record.interactionId;
  const promptTokens = readTokenCount(record, ["prompt_tokens", "promptTokens"]);
  const completionTokens = readTokenCount(record, ["completion_tokens", "completionTokens"]);
  return {
    interactionId:
      typeof rawId === "string" || typeof rawId === "number" ? String(rawId) : null,
    createdAt: readString(record, ["created_at", "createdAt", "at"]),
    assistanceLevel:
      readString(record, ["assistance_level", "assistanceLevel"]) ?? DEFAULT_ASSISTANCE_LEVEL,
    model: readString(record, ["model"]) ?? "",
    totalTokens:
      readTokenCount(record, ["total_tokens", "totalTokens"]) ??
      (promptTokens === null && completionTokens === null
        ? null
        : (promptTokens ?? 0) + (completionTokens ?? 0)),
    status,
  };
}

// GET /api/v1/ai/interactions：接受裸数组或 {items|interactions|data:[...]} 包装；
// 单条结构不符则跳过该行，整体不可解析时返回 null（页面显示读取失败，不填充假记录）。
export function parseInteractionList(payload: unknown): AiInteractionRecord[] | null {
  const list = asArray(payload);
  const record = list ? null : asRecord(payload);
  const container = list
    ? list
    : record
      ? asArray(record.items) ??
        asArray(record.interactions) ??
        asArray(record.data) ??
        asArray(record.list)
      : null;
  if (!container) {
    return null;
  }
  const items: AiInteractionRecord[] = [];
  for (const entry of container) {
    const parsed = parseInteraction(entry);
    if (parsed) {
      items.push(parsed);
    }
  }
  return items;
}

export type QuotaDetail = {
  usedTokens: number | null;
  limitTokens: number | null;
};

// 团队契约只规定 429 的错误码，未冻结 details 结构；因此三处都读一遍（details.details、
// details 本体、顶层 error.details），读不到就返回 null，由界面写「后端未返回」而不是编数字。
export function readQuotaDetail(failure: ApiFailure): QuotaDetail {
  const sources: Array<Record<string, unknown> | null> = [asRecord(failure.details)];
  const outer = asRecord(failure.details);
  if (outer) {
    sources.push(asRecord(outer.details));
    sources.push(asRecord(outer.usage));
  }
  let usedTokens: number | null = null;
  let limitTokens: number | null = null;
  for (const source of sources) {
    if (!source) {
      continue;
    }
    usedTokens =
      usedTokens ??
      readTokenCount(source, [
        "used_tokens",
        "usedTokens",
        "today_tokens",
        "tokens_used",
        "used",
      ]);
    limitTokens =
      limitTokens ??
      readTokenCount(source, [
        "limit_tokens",
        "limitTokens",
        "daily_token_limit",
        "token_limit",
        "limit",
      ]);
  }
  return { usedTokens, limitTokens };
}

export type TutorFailureKind =
  | "unavailable"
  | "timeout"
  | "quota"
  | "validation"
  | "not_ready"
  | "other";

// 先按冻结契约的 error.code 判定，再退回 HTTP 状态码。
// 503 在契约里唯一对应 AI_UNAVAILABLE；但 DB_UNAVAILABLE（后端连不上库）不能冒充「未配置 key」，
// 因此那种情况落到 other，只显示通用重试文案。
export function classifyTutorFailure(failure: ApiFailure): TutorFailureKind {
  const code = failure.code;
  if (code === "AI_UNAVAILABLE") {
    return "unavailable";
  }
  if (code === "AI_TIMEOUT") {
    return "timeout";
  }
  if (code === "AI_QUOTA_EXCEEDED") {
    return "quota";
  }
  if (code === "VALIDATION_ERROR") {
    return "validation";
  }
  if (code === "NOT_FOUND") {
    return "not_ready";
  }
  if (code === "SERVICE_UNAVAILABLE" || code === "DB_UNAVAILABLE") {
    // 连不上后端或数据库不可用：与「未配置 key」无关，不能套用那条固定文案。
    return "other";
  }
  if (failure.status === 504) {
    return "timeout";
  }
  if (failure.status === 503) {
    return "unavailable";
  }
  if (failure.status === 429) {
    return "quota";
  }
  if (failure.status === 422) {
    return "validation";
  }
  if (failure.status === 404) {
    return "not_ready";
  }
  return "other";
}

// 只有契约里确认为「未配置 key」的 503 才展示配置引导；其余 503 只说服务不可用。
export function isKeyMissingFailure(failure: ApiFailure): boolean {
  return failure.code === "AI_UNAVAILABLE" || (failure.code === "HTTP_503" && failure.status === 503);
}

export function tokenText(value: number | null): string {
  if (value === null) {
    return "后端未返回";
  }
  return String(value) + " tokens";
}
