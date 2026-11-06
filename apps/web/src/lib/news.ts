// GET /api/v1/news, POST /api/v1/news/refresh, POST /api/v1/news/{id}/analyze
//
// 解析口径与其它 lib 一致：字段缺失就留空/跳行，整体不可解析返回 null（页面显示
// 读取失败），绝不补造条目。

export const NEWS_PATH = "/api/v1/news";
export const NEWS_REFRESH_PATH = "/api/v1/news/refresh";
export const NEWS_LIMIT = 20;

export type NewsItem = {
  id: string;
  sourceKey: string;
  sourceKind: string;
  title: string;
  url: string;
  excerpt: string;
  publishedAt: string | null;
  fetchedAt: string | null;
  aiStatus: string;
  aiSummary: string | null;
  aiKeyPoints: string[];
  aiModel: string | null;
  aiTokens: number | null;
  aiUpdatedAt: string | null;
};

export type NewsList = {
  items: NewsItem[];
  total: number;
  sources: string[];
  enabled: boolean;
};

export type NewsRefreshStat = {
  source: string;
  status: string;
  fetched: number | null;
  inserted: number | null;
  detail: string | null;
};

export type NewsRefresh = {
  sources: NewsRefreshStat[];
  itemsBefore: number;
  itemsAfter: number;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
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

function readStringArray(record: Record<string, unknown>, keys: string[]): string[] {
  for (const key of keys) {
    const value = asArray(record[key]);
    if (value) {
      return value.filter((entry): entry is string => typeof entry === "string");
    }
  }
  return [];
}

function parseItem(value: unknown): NewsItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = readId(record, ["id"]);
  const title = readText(record, ["title"]) ?? "";
  const url = readText(record, ["url"]) ?? "";
  if (id === null || (title === "" && url === "")) {
    return null;
  }
  return {
    id,
    sourceKey: readText(record, ["source_key", "sourceKey"]) ?? "",
    sourceKind: readText(record, ["source_kind", "sourceKind"]) ?? "",
    title,
    url,
    excerpt: readText(record, ["excerpt"]) ?? "",
    publishedAt: readText(record, ["published_at", "publishedAt"]),
    fetchedAt: readText(record, ["fetched_at", "fetchedAt"]),
    aiStatus: readText(record, ["ai_status", "aiStatus"]) ?? "pending",
    aiSummary: readText(record, ["ai_summary", "aiSummary"]),
    aiKeyPoints: readStringArray(record, ["ai_key_points", "aiKeyPoints"]),
    aiModel: readText(record, ["ai_model", "aiModel"]),
    aiTokens: readCount(record, ["ai_tokens", "aiTokens"]),
    aiUpdatedAt: readText(record, ["ai_updated_at", "aiUpdatedAt"]),
  };
}

export function parseNewsList(payload: unknown): NewsList | null {
  const record = asRecord(payload);
  const rawItems = record ? asArray(record.items) : null;
  if (!record || !rawItems) {
    return null;
  }
  const items: NewsItem[] = [];
  for (const entry of rawItems) {
    const parsed = parseItem(entry);
    if (parsed) {
      items.push(parsed);
    }
  }
  const total = readCount(record, ["total"]);
  return {
    items,
    total: total === null ? items.length : Math.round(total),
    sources: readStringArray(record, ["sources"]),
    enabled: record.enabled === true,
  };
}

export function parseNewsItem(payload: unknown): NewsItem | null {
  return parseItem(payload);
}

export function parseNewsRefresh(payload: unknown): NewsRefresh | null {
  const record = asRecord(payload);
  const rawSources = record ? asArray(record.sources) : null;
  if (!record || !rawSources) {
    return null;
  }
  const sources: NewsRefreshStat[] = [];
  for (const entry of rawSources) {
    const stat = asRecord(entry);
    if (!stat) {
      continue;
    }
    sources.push({
      source: readText(stat, ["source"]) ?? "",
      status: readText(stat, ["status"]) ?? "",
      fetched: readCount(stat, ["fetched"]),
      inserted: readCount(stat, ["inserted"]),
      detail: readText(stat, ["detail"]),
    });
  }
  return {
    sources,
    itemsBefore: Math.round(readCount(record, ["items_before", "itemsBefore"]) ?? 0),
    itemsAfter: Math.round(readCount(record, ["items_after", "itemsAfter"]) ?? 0),
  };
}

export function analyzePath(id: string): string {
  return NEWS_PATH + "/" + encodeURIComponent(id) + "/analyze";
}

export const NEWS_SOURCE_LABELS: Record<string, string> = {
  hn: "Hacker News",
  "arxiv-ai": "arXiv cs.AI",
  "gh-nextjs": "Next.js Releases",
};

export function newsSourceLabel(key: string): string {
  return NEWS_SOURCE_LABELS[key] ?? (key || "未知来源");
}

export function aiStatusLabel(status: string): string {
  if (status === "ok") {
    return "已提炼";
  }
  if (status === "error") {
    return "提炼失败";
  }
  if (status === "unavailable") {
    return "未配置模型";
  }
  return "待提炼";
}
