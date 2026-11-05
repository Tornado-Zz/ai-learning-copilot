// Sprint 5 冻结契约（知识检索）。前端只做三件事：把查询词交给后端、渲染命中的知识块、标注抓取时间与过期状态。
// 本页不提供「输入任意 URL 抓取」的入口：抓取白名单（docs.python.org 与仓库 lessons）只在服务端判定，前端不参与。

export const KNOWLEDGE_SEARCH_PATH = "/api/v1/knowledge/search";
// GET /api/v1/knowledge/sources：入库了哪些来源、各多少块、什么时候抓的、是否过期。
// 这个接口一直存在，但知识库页面此前只做检索、从不展示来源清单。
export const KNOWLEDGE_SOURCES_PATH = "/api/v1/knowledge/sources";

// 契约默认 limit=5；页面固定用同一个值，避免多出一次状态。
export const KNOWLEDGE_LIMIT = 5;
export const KNOWLEDGE_QUERY_MIN = 2;
export const KNOWLEDGE_STALE_DAYS_HINT = 30;

// 页面顶部固定说明：只读快照，不做实时抓取。页面与 AI 面板共用下面两条文案，避免两处漂移。
export const KNOWLEDGE_PAGE_NOTICE =
  "检索只读知识库快照，不联网实时抓取；每条结果都标注抓取时间。";
export const KNOWLEDGE_STALE_BADGE = "可能过期";
export const KNOWLEDGE_NO_CITATION = "本次回答未使用知识库引用";

export type KnowledgeHit = {
  chunkId: string | null;
  sourceId: string | null;
  title: string;
  url: string;
  fetchedAt: string | null;
  ageDays: number | null;
  stale: boolean;
  heading: string | null;
  snippet: string;
  score: number;
};

export type KnowledgeSource = {
  id: string;
  url: string;
  title: string;
  sourceType: string;
  fetchedAt: string | null;
  ageDays: number | null;
  stale: boolean;
  chunks: number | null;
};

export type KnowledgeSearchResult = {
  query: string;
  items: KnowledgeHit[];
  total: number;
};

// 与后端 q 的 min_length 同口径：只裁首尾空白后计数，不足 2 个字符直接在前端拦下。
export function validateKnowledgeQuery(text: string): string | null {
  const trimmed = text.trim();
  if (trimmed.length < KNOWLEDGE_QUERY_MIN) {
    return (
      "检索词至少 2 个字符，当前 " + String(trimmed.length) + " 个；后端同口径返回 422。"
    );
  }
  return null;
}

export function buildSearchPath(query: string, limit: number = KNOWLEDGE_LIMIT): string {
  return (
    KNOWLEDGE_SEARCH_PATH +
    "?q=" +
    encodeURIComponent(query.trim()) +
    "&limit=" +
    String(limit)
  );
}

// 来源域名：官方文档页直接显示 host；仓库课程用 repo://lesson/<code> 的形式，显示为「仓库课程」。
export function sourceDomain(url: string): string {
  const trimmed = url.trim();
  if (trimmed === "") {
    return "来源未知";
  }
  if (trimmed.toLowerCase().startsWith("repo://")) {
    return "仓库课程";
  }
  try {
    const parsed = new URL(trimmed);
    return parsed.hostname === "" ? "来源未知" : parsed.hostname;
  } catch {
    return "来源未知";
  }
}

export function ageDaysText(ageDays: number | null): string {
  if (ageDays === null) {
    return "后端未返回";
  }
  return String(ageDays) + " 天";
}

export function scoreText(score: number): string {
  if (!Number.isFinite(score)) {
    return "—";
  }
  return score.toFixed(2);
}

// stale 由后端按 KNOWLEDGE_STALE_DAYS（默认 30）给出；字段缺失时按同一阈值在本地补算，
// 这样徽章不会因为后端漏字段而永远不出现。
export function isStale(ageDays: number | null, stale: boolean | null): boolean {
  if (stale !== null) {
    return stale;
  }
  return ageDays !== null && ageDays > KNOWLEDGE_STALE_DAYS_HINT;
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

function readText(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
  }
  return null;
}

function readCount(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return value;
    }
  }
  return null;
}

function readBoolean(record: Record<string, unknown>, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") {
      return value;
    }
  }
  return null;
}

function readId(record: Record<string, unknown>, keys: string[]): string | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return null;
}

// 单条命中：标题是唯一硬要求（没有标题的行无法溯源，直接丢弃），url/snippet 缺失时降级渲染，
// 不编造内容，也不把缺字段当成整次检索失败。
function parseHit(value: unknown): KnowledgeHit | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const title = readText(record, ["title"]);
  if (title === null) {
    return null;
  }
  const ageDays = readCount(record, ["age_days", "ageDays"]);
  return {
    chunkId: readId(record, ["chunk_id", "chunkId", "id"]),
    sourceId: readId(record, ["source_id", "sourceId"]),
    title,
    url: readText(record, ["url"]) ?? "",
    fetchedAt: readText(record, ["fetched_at", "fetchedAt"]),
    ageDays,
    stale: isStale(ageDays, typeof record.stale === "boolean" ? record.stale : null),
    heading: readText(record, ["heading"]),
    snippet: readText(record, ["snippet", "content"]) ?? "",
    score: readCount(record, ["score"]) ?? 0,
  };
}

// GET /api/v1/knowledge/search 的 200 响应：{query, items[], total}。
// items 不是数组视为结构不符（返回 null → 页面显示契约错误态），单条坏数据只跳过该行。
export function parseKnowledgeSearch(payload: unknown): KnowledgeSearchResult | null {
  const record = asRecord(payload);
  if (!record) {
    return null;
  }
  const rawItems = asArray(record.items);
  if (!rawItems) {
    return null;
  }
  const items: KnowledgeHit[] = [];
  for (const entry of rawItems) {
    const parsed = parseHit(entry);
    if (parsed) {
      items.push(parsed);
    }
  }
  const total = readCount(record, ["total"]);
  return {
    query: readText(record, ["query"]) ?? "",
    items,
    total: total === null ? items.length : Math.round(total),
  };
}

// 单条来源：缺关键字段就跳过该行，整体不可解析时返回 null（页面显示读取失败，不编条目）。
function parseSource(value: unknown): KnowledgeSource | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const url = readText(record, ["url"]) ?? "";
  const title = readText(record, ["title"]) ?? "";
  if (url === '' && title === '') {
    return null;
  }
  return {
    id: readId(record, ["id"]) ?? "",
    url,
    title,
    sourceType: readText(record, ["source_type", "sourceType"]) ?? "",
    fetchedAt: readText(record, ["fetched_at", "fetchedAt"]),
    ageDays: readCount(record, ["age_days", "ageDays"]),
    stale: readBoolean(record, ["stale"]) ?? false,
    chunks: readCount(record, ["chunks"]),
  };
}

export function parseSourceList(payload: unknown): KnowledgeSource[] | null {
  const list = asArray(payload);
  const record = list ? null : asRecord(payload);
  const container = list
    ? list
    : record
      ? asArray(record.items) ?? asArray(record.sources) ?? asArray(record.data)
      : null;
  if (!container) {
    return null;
  }
  const items: KnowledgeSource[] = [];
  for (const entry of container) {
    const parsed = parseSource(entry);
    if (parsed) {
      items.push(parsed);
    }
  }
  return items;
}
