// v0.1.2 错题本与间隔复习的前端契约（冻结口径 B1 / B2 / B3）。
// 诚实性口径：后端缺哪个字段就留 null，页面显示「—」，不补 0、不按 streak 反推间隔天数。
// 调度只在服务端发生（POST /exercises/{id}/submissions 判题成功后同事务写入 review_items），
// 本页只读，不发起任何写请求，也不向前端重复一份间隔算法。

export const REVIEW_ITEMS_PATH = "/api/v1/review/items";
export const REVIEW_SUMMARY_PATH = "/api/v1/review/summary";

// 默认分页：契约的 GET /review/items?due=1&limit=20。
export const REVIEW_PAGE_LIMIT = 20;

// due=1 时只返回 status='pending' AND next_review_on <= 今天；不带 due 时返回全部行。
export function reviewItemsPath(options: { due?: boolean; limit?: number }): string {
  const query: string[] = [];
  if (options.due === true) {
    query.push("due=1");
  }
  if (options.limit !== undefined) {
    query.push("limit=" + String(options.limit));
  }
  return query.length === 0 ? REVIEW_ITEMS_PATH : REVIEW_ITEMS_PATH + "?" + query.join("&");
}

export type ReviewItem = {
  id: number;
  exerciseId: number | null;
  exerciseTitle: string | null;
  lessonId: number | null;
  streak: number | null;
  intervalDays: number | null;
  nextReviewOn: string | null;
  status: string | null;
  due: boolean | null;
  lastResult: string | null;
};

export type ReviewItemPage = {
  items: ReviewItem[];
  total: number | null;
  dueTotal: number | null;
};

export type ReviewSummary = {
  pending: number | null;
  dueToday: number | null;
  done: number | null;
  nextDueOn: string | null;
};

export const REVIEW_STATUS_LABELS: Record<string, string> = {
  pending: "待复习",
  done: "已完成",
};

export const REVIEW_LAST_RESULT_LABELS: Record<string, string> = {
  passed: "上次通过",
  failed: "上次未通过",
};

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

function readBoolean(record: Record<string, unknown>, keys: string[]): boolean | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "boolean") {
      return value;
    }
  }
  return null;
}

function parseReviewItem(value: unknown): ReviewItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  // id 是复习项的唯一标识，缺它无法渲染成一行（也无法 POST result），该类行视为非法响应。
  const id = readNumber(record, ["id"]);
  if (id === null) {
    return null;
  }
  return {
    id,
    exerciseId: readNumber(record, ["exercise_id", "exerciseId"]),
    exerciseTitle: readString(record, ["exercise_title", "exerciseTitle"]),
    lessonId: readNumber(record, ["lesson_id", "lessonId"]),
    streak: readNumber(record, ["streak"]),
    intervalDays: readNumber(record, ["interval_days", "intervalDays"]),
    nextReviewOn: readString(record, ["next_review_on", "nextReviewOn"]),
    status: readString(record, ["status"]),
    due: readBoolean(record, ["due"]),
    lastResult: readString(record, ["last_result", "lastResult"]),
  };
}

// 行序沿用后端默认的 next_review_on ASC, id ASC：前端不再排序，避免把缺日期的行排到别处。
export function parseReviewItems(body: unknown): ReviewItemPage | null {
  const record = asRecord(body);
  const list = record ? asArray(record.items) : asArray(body);
  if (!list) {
    return null;
  }
  const items: ReviewItem[] = [];
  for (const entry of list) {
    const item = parseReviewItem(entry);
    if (item) {
      items.push(item);
    }
  }
  return {
    items,
    total: record ? readNumber(record, ["total"]) : null,
    dueTotal: record ? readNumber(record, ["due_total", "dueTotal"]) : null,
  };
}

// 无数据时后端返回 pending / due_today / done 全 0 且 next_due_on = null；缺字段仍留 null 显示「—」。
export function parseReviewSummary(body: unknown): ReviewSummary | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  return {
    pending: readNumber(record, ["pending"]),
    dueToday: readNumber(record, ["due_today", "dueToday"]),
    done: readNumber(record, ["done"]),
    nextDueOn: readString(record, ["next_due_on", "nextDueOn"]),
  };
}

// 未知取值原样显示，不抹成已知状态。
export function reviewStatusLabel(status: string | null): string {
  if (status === null) {
    return "—";
  }
  return REVIEW_STATUS_LABELS[status] ?? status;
}

export function reviewLastResultLabel(value: string | null): string {
  if (value === null) {
    return "—";
  }
  return REVIEW_LAST_RESULT_LABELS[value] ?? value;
}

export function reviewCountText(value: number | null): string {
  return value === null ? "—" : String(value);
}

export function reviewDaysText(value: number | null): string {
  return value === null ? "—" : String(value) + " 天";
}
