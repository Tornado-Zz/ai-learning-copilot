import { weekdayLabel } from "@/lib/labels";
import type { PlanItemStatus } from "@/lib/plan-rules";

// Sprint 2 课程与周计划契约。所有字段都来自后端响应，解析失败一律返回 null，
// 由页面显示错误态——绝不用本地默认值伪造课程内容或任务。

export const LESSONS_PATH = "/api/v1/lessons";
export const STUDY_PLAN_PATH = "/api/v1/study-plan";
export const STUDY_PLAN_GENERATE_PATH = "/api/v1/study-plan/generate";

export function lessonPath(id: string | number): string {
  return LESSONS_PATH + "/" + encodeURIComponent(String(id));
}

export function lessonProgressPath(id: string | number): string {
  return lessonPath(id) + "/progress";
}

// 任务状态更新接口不在本次调度契约内，按最保守的 REST 形态实现：
// 后端未提供时调用得到 404，页面显示错误并保持接口返回的真实状态。
export function studyPlanItemPath(id: number): string {
  return "/api/v1/study-plan/items/" + encodeURIComponent(String(id));
}

export type LessonStatus = "not_started" | "in_progress" | "completed";

// 计划项状态机的唯一来源在 lib/plan-rules（纯规则、可被 node 脚本断言），这里只做转发。
export type { PlanItemStatus };

export type LessonProgress = {
  status: LessonStatus;
  selfAssessment: number | null;
  progressPct: number;
};

export type LessonSummary = {
  id: number;
  code: string;
  title: string;
  summary: string;
  stage: string;
  orderIndex: number;
  estimatedMinutes: number;
  contentVersion: string;
  progress: LessonProgress;
};

export type LessonSection = { heading: string; body: string };
export type LessonExample = { title: string; code: string; note: string };
export type LessonCommonError = { wrong: string; why: string; fix: string };
export type LessonSelfCheck = { question: string; answerHint: string };

export type LessonDetail = LessonSummary & {
  objectives: string[];
  sections: LessonSection[];
  examples: LessonExample[];
  commonErrors: LessonCommonError[];
  selfCheck: LessonSelfCheck[];
};

// S6：kind 现在有 lesson / exercise 两种真实取值，target_id 指向 lessons.id 或 exercises.id。
// 后端优先给出 target_title / target_href；缺字段时前端只按 kind + target_id 推导站内路由，
// 不猜标题、不构造后端没有的链接。
export type PlanItem = {
  id: number;
  kind: string;
  targetId: number | null;
  lessonId: number | null;
  lessonTitle: string;
  targetTitle: string;
  targetHref: string | null;
  plannedMinutes: number;
  status: PlanItemStatus;
  rationale: string;
};

// 契约 S5：days[] 分别给出 scheduled_minutes（待执行）与 history_minutes（done+skipped）。
// null 表示响应里没有该字段，由 resolveDayBudget 按行状态汇总同一口径。
export type PlanDay = {
  date: string;
  weekday: number | null;
  plannedMinutes: number;
  scheduledMinutes: number | null;
  historyMinutes: number | null;
  totalMinutes: number | null;
  items: PlanItem[];
};

export type StudyPlan = {
  weekStart: string;
  weekEnd: string | null;
  today: string | null;
  persisted: boolean | null;
  dailyMinutes: number | null;
  scheduledItems: number | null;
  historyItems: number | null;
  days: PlanDay[];
};

export const LESSON_STATUS_LABELS: Record<LessonStatus, string> = {
  not_started: "未开始",
  in_progress: "学习中",
  completed: "已完成",
};

// S6 起 lesson / exercise；v0.1.2 起周计划第三遍会排 kind='review'（target_id = exercises.id）。
// 未知 kind 原样显示，不抹成「课程」。
export const PLAN_ITEM_KIND_LABELS: Record<string, string> = {
  lesson: "课程",
  exercise: "练习",
  review: "复习",
};

export function planItemKindLabel(kind: string): string {
  return PLAN_ITEM_KIND_LABELS[kind] ?? kind;
}

// 只接受站内路由：后端若给出 API 端点（/api/...）、协议相对地址或绝对地址，一律丢弃后按 kind 推导，
// 否则 Next 会对 /api/... 发起 RSC 预取并拿到 404。
function planItemRouteHref(value: string | null): string | null {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/api/")) {
    return null;
  }
  return value;
}

// 后端未提供 target_href 时的推导：lesson -> /learn/{lesson_id}，exercise -> /practice/{exercise_id}。
function planItemHrefFallback(
  kind: string,
  lessonId: number | null,
  targetId: number | null,
): string | null {
  if (kind === "lesson" && lessonId !== null) {
    return "/learn/" + String(lessonId);
  }
  if (kind === "exercise" && targetId !== null) {
    return "/practice/" + String(targetId);
  }
  return null;
}

export const PLAN_ITEM_STATUS_LABELS: Record<PlanItemStatus, string> = {
  scheduled: "待完成",
  done: "已完成",
  skipped: "已跳过",
  expired: "已过期",
};

// 自评只开放 0–2：L3/L4 需要实践证据，不得由课程页自评产生。
export const SELF_ASSESSMENT_OPTIONS: Array<{ value: 0 | 1 | 2; label: string }> = [
  { value: 0, label: "L0 · 还没掌握" },
  { value: 1, label: "L1 · 大致看懂" },
  { value: 2, label: "L2 · 能自己写出来" },
];

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

function readText(record: Record<string, unknown>, keys: string[], fallback: string): string {
  return readString(record, keys) ?? fallback;
}

// stage / content_version 在不同响应里是数字或字符串，统一按文本渲染。
function readIdLike(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string" && value.length > 0) {
      return value;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return "";
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

function readLessonStatus(value: unknown): LessonStatus {
  if (value === "in_progress" || value === "completed" || value === "not_started") {
    return value;
  }
  return "not_started";
}

function readPlanItemStatus(value: unknown): PlanItemStatus {
  if (value === "done" || value === "skipped" || value === "expired" || value === "scheduled") {
    return value;
  }
  return "scheduled";
}

export function parseLessonProgress(value: unknown): LessonProgress {
  const record = asRecord(value);
  if (!record) {
    return { status: "not_started", selfAssessment: null, progressPct: 0 };
  }
  const pct = readNumber(record, ["progress_pct", "progressPct"]);
  const self = readNumber(record, ["self_assessment", "selfAssessment"]);
  return {
    status: readLessonStatus(record.status),
    selfAssessment: self === null ? null : Math.max(0, Math.min(4, Math.round(self))),
    progressPct: pct === null ? 0 : Math.max(0, Math.min(100, Math.round(pct))),
  };
}

export function parseLessonSummary(value: unknown): LessonSummary | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = readNumber(record, ["id"]);
  const title = readString(record, ["title"]);
  if (id === null || !title) {
    return null;
  }
  return {
    id,
    code: readText(record, ["code", "slug"], ""),
    title,
    summary: readText(record, ["summary"], ""),
    stage: readIdLike(record, ["stage"]),
    orderIndex: readNumber(record, ["order_index", "orderIndex"]) ?? 0,
    estimatedMinutes: readNumber(record, ["estimated_minutes", "estimatedMinutes"]) ?? 0,
    contentVersion: readIdLike(record, ["content_version", "contentVersion"]),
    progress: parseLessonProgress(record.progress),
  };
}

export function parseLessons(body: unknown): LessonSummary[] | null {
  const record = asRecord(body);
  // 已实现的后端返回 {items, total}；冻结契约写的是 {lessons}。两种都接受。
  const list = record
    ? asArray(record.lessons) ?? asArray(record.items) ?? asArray(record.data)
    : asArray(body);
  if (!list) {
    return null;
  }
  const lessons: LessonSummary[] = [];
  for (const entry of list) {
    const lesson = parseLessonSummary(entry);
    if (lesson) {
      lessons.push(lesson);
    }
  }
  return lessons;
}

function readStringList(value: unknown): string[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const result: string[] = [];
  for (const entry of list) {
    if (typeof entry === "string" && entry.length > 0) {
      result.push(entry);
      continue;
    }
    const record = asRecord(entry);
    const text = record ? readString(record, ["text", "objective", "title", "body"]) : null;
    if (text) {
      result.push(text);
    }
  }
  return result;
}

function readSections(value: unknown): LessonSection[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const sections: LessonSection[] = [];
  for (const entry of list) {
    const record = asRecord(entry);
    if (!record) {
      continue;
    }
    const heading = readText(record, ["heading", "title"], "");
    const body = readText(record, ["body", "content", "body_text"], "");
    if (!heading && !body) {
      continue;
    }
    sections.push({ heading, body });
  }
  return sections;
}

function readExamples(value: unknown): LessonExample[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const examples: LessonExample[] = [];
  for (const entry of list) {
    const record = asRecord(entry);
    if (!record) {
      continue;
    }
    const code = readText(record, ["code", "code_text", "snippet"], "");
    const title = readText(record, ["title"], "");
    const notes = readStringList(record.notes);
    const output = readText(record, ["output"], "");
    let note = readText(record, ["note", "description"], "");
    if (!note && notes.length > 0) {
      note = notes.join("；");
    }
    if (output) {
      note = (note ? note + " " : "") + "预期输出：" + output;
    }
    if (!code && !title) {
      continue;
    }
    examples.push({ title, code, note });
  }
  return examples;
}

function readCommonErrors(value: unknown): LessonCommonError[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const errors: LessonCommonError[] = [];
  for (const entry of list) {
    const record = asRecord(entry);
    if (!record) {
      continue;
    }
    const wrong = readText(record, ["wrong", "wrong_code", "mistake"], "");
    const why = readText(record, ["why", "reason"], "");
    const fix = readText(record, ["fix", "correction"], "");
    if (!wrong && !why && !fix) {
      continue;
    }
    errors.push({ wrong, why, fix });
  }
  return errors;
}

function readSelfCheck(value: unknown): LessonSelfCheck[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const checks: LessonSelfCheck[] = [];
  for (const entry of list) {
    const record = asRecord(entry);
    if (!record) {
      continue;
    }
    const question = readText(record, ["question", "prompt"], "");
    const answerHint = readText(record, ["answer_hint", "answerHint", "hint", "answer"], "");
    if (!question) {
      continue;
    }
    checks.push({ question, answerHint });
  }
  return checks;
}

export function parseLessonDetail(body: unknown): LessonDetail | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  // 后端实际返回平铺结构（字段在顶层，含 content 与 progress）；冻结契约曾写作 {lesson:{...}}。
  // 两种形态都接受：优先取 lesson 包装，缺失时退回顶层，避免把真实响应判成非法。
  const lesson = asRecord(record.lesson) ?? record;
  const summary = parseLessonSummary(lesson);
  if (!summary) {
    return null;
  }
  const content = asRecord(lesson.content) ?? lesson;
  const progress = record.progress
    ? parseLessonProgress(record.progress)
    : parseLessonProgress(lesson.progress);
  // 冻结契约是 objectives / sections / examples[] / common_errors；
  // 已实现的后端是 goal / explanation[] / example{} / common_mistakes。两种形态都归一化到同一套字段。
  const objectives = readStringList(content.objectives);
  const goal = readText(content, ["goal"], "");
  if (objectives.length === 0 && goal) {
    objectives.push(goal);
  }

  let sections = readSections(content.sections);
  if (sections.length === 0) {
    const paragraphs = readStringList(content.explanation);
    if (paragraphs.length > 0) {
      sections = [{ heading: "", body: paragraphs.join("\n\n") }];
    }
  }

  let examples = readExamples(content.examples);
  if (examples.length === 0 && content.example !== undefined && content.example !== null) {
    examples = readExamples([content.example]);
  }

  return {
    ...summary,
    progress,
    objectives,
    sections,
    examples,
    commonErrors: readCommonErrors(
      content.common_errors ?? content.commonErrors ?? content.common_mistakes ?? content.commonMistakes,
    ),
    selfCheck: readSelfCheck(content.self_check ?? content.selfCheck),
  };
}

function readPlanItems(value: unknown, dayIndex: number): PlanItem[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const items: PlanItem[] = [];
  for (let index = 0; index < list.length; index += 1) {
    const record = asRecord(list[index]);
    if (!record) {
      continue;
    }
    const id = readNumber(record, ["id"]);
    const kind = readText(record, ["kind"], "lesson");
    const lesson = asRecord(record.lesson);
    // kind='lesson' 时课程 id 在 target_id（多态引用）；其他 kind 的 target_id 指练习，不能当课程链接。
    const targetId = readNumber(record, ["target_id", "targetId"]);
    const lessonId =
      kind === "lesson"
        ? (lesson ? readNumber(lesson, ["id"]) : null) ??
          readNumber(record, ["lesson_id", "lessonId"]) ??
          targetId
        : null;
    const lessonTitle = lesson
      ? readText(lesson, ["title"], "")
      : readText(record, ["lesson_title", "lessonTitle"], "");
    // S6：target_title / target_href 由后端按 kind 给出；缺失时只做 lesson 标题与站内路由的推导。
    const targetTitle =
      readString(record, ["target_title", "targetTitle"]) ?? lessonTitle;
    const targetHref =
      planItemRouteHref(readString(record, ["target_href", "targetHref"])) ??
      planItemHrefFallback(kind, lessonId, targetId);
    items.push({
      // 后端未返回 id 时用负数占位：内容照实展示，但状态操作按钮禁用，避免向错误目标写数据。
      id: id === null ? -(dayIndex * 1000 + index + 1) : id,
      kind,
      targetId,
      lessonId,
      lessonTitle,
      targetTitle,
      targetHref,
      plannedMinutes: readNumber(record, ["planned_minutes", "plannedMinutes"]) ?? 0,
      status: readPlanItemStatus(record.status),
      rationale: readText(record, ["rationale"], ""),
    });
  }
  return items;
}

export function parseStudyPlan(body: unknown): StudyPlan | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  // week_start 是「本周」的唯一来源，缺它无法渲染任何日期分组。
  const weekStart = readString(record, ["week_start", "weekStart"]);
  if (!weekStart) {
    return null;
  }
  const rawDays = asArray(record.days);
  if (!rawDays) {
    return null;
  }
  const days: PlanDay[] = [];
  for (const entry of rawDays) {
    const record2 = asRecord(entry);
    if (!record2) {
      continue;
    }
    const date = readString(record2, ["date", "plan_date", "planDate"]);
    if (!date) {
      continue;
    }
    const items = readPlanItems(record2.items, days.length);
    let planned = readNumber(record2, ["planned_minutes", "plannedMinutes"]);
    if (planned === null) {
      planned = 0;
      for (const item of items) {
        planned += item.plannedMinutes;
      }
    }
    days.push({
      date,
      weekday: readNumber(record2, ["weekday"]),
      plannedMinutes: planned,
      scheduledMinutes: readNumber(record2, ["scheduled_minutes", "scheduledMinutes"]),
      historyMinutes: readNumber(record2, ["history_minutes", "historyMinutes"]),
      totalMinutes: readNumber(record2, ["total_minutes", "totalMinutes"]),
      items,
    });
  }
  days.sort((left, right) => (left.date < right.date ? -1 : left.date > right.date ? 1 : 0));
  return {
    weekStart,
    weekEnd: readString(record, ["week_end", "weekEnd"]),
    today: readString(record, ["today", "current_date", "currentDate"]),
    persisted: readBoolean(record, ["persisted"]),
    dailyMinutes: readNumber(record, ["daily_minutes", "dailyMinutes"]),
    scheduledItems: readNumber(record, ["scheduled_items", "scheduledItems"]),
    historyItems: readNumber(record, ["history_items", "historyItems"]),
    days,
  };
}

// 写接口（PUT/PATCH/POST）只要 HTTP 2xx 就算成功，响应体结构不参与渲染。
export function parseAck(): true {
  return true;
}

// 时区已确认为 user_confirmed 后，用用户时区算「今天」的本地日期。
// 这是唯一可以在前端做的日期推导：不做服务器时区推导，也不猜测。
export function localDateISO(timeZone: string): string | null {
  try {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    let year = "";
    let month = "";
    let day = "";
    for (const part of parts) {
      if (part.type === "year") {
        year = part.value;
      } else if (part.type === "month") {
        month = part.value;
      } else if (part.type === "day") {
        day = part.value;
      }
    }
    if (year.length !== 4 || month.length !== 2 || day.length !== 2) {
      return null;
    }
    return year + "-" + month + "-" + day;
  } catch {
    return null;
  }
}

export function weekdayOfDate(date: string): string {
  const parsed = new Date(date + "T00:00:00Z");
  if (Number.isNaN(parsed.getTime())) {
    return "";
  }
  const weekday = parsed.getUTCDay();
  return weekdayLabel(weekday === 0 ? 7 : weekday);
}

export function formatMinutes(minutes: number): string {
  return String(Math.max(0, Math.round(minutes))) + " 分钟";
}

// 标题只认后端给出的真实内容（target_title / lesson_title）；都没有时退回「类型 + 目标 id」，
// 既不编造标题，也不把另一门课的名字顶上来。
export function planItemTitle(item: PlanItem): string {
  if (item.targetTitle) {
    return item.targetTitle;
  }
  if (item.kind === "lesson") {
    return "课程 " + String(item.lessonId === null ? item.id : item.lessonId);
  }
  if (item.targetId !== null) {
    return planItemKindLabel(item.kind) + " " + String(item.targetId);
  }
  return item.kind + " · " + String(item.id);
}
