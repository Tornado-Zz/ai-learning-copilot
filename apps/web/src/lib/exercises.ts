import type { EvidenceStrength } from "@/lib/contract";

// Sprint 3 阶段 B 练习契约（冻结口径 B1/B2/B3）。
// 判题只做两件事：静态模式比对（static_rule）与用户自检申报（self_check），系统不执行任何提交的代码。
// 因此前端不解析、不推断任何运行结果：响应缺字段时解析返回 null（页面显示错误态）或留空，
// 绝不补默认题目、默认用例或默认判定结果。

export const EXERCISES_PATH = "/api/v1/exercises";

// 页面顶栏与结果卡反复引用同一句话，集中一处避免文案漂移。
export const EVIDENCE_DISCLAIMER =
  "静态规则通过不代表代码真实运行通过；自检结果属未验证证据。";

export function exercisesByLessonPath(lessonId: string | number): string {
  return EXERCISES_PATH + "?lesson_id=" + encodeURIComponent(String(lessonId));
}

// 接口地址：只用于 apiRequest（GET/POST），绝不能放进 <Link href>。
export function exercisePath(id: string | number): string {
  return EXERCISES_PATH + "/" + encodeURIComponent(String(id));
}

// 页面路由：给 <Link href> 用，指向练习详情页 /practice/{id}。
// 两者混用会让卡片链到 API 端点（点开是 JSON/404），Next 还会对 /api/... 发起 RSC 预取并拿到 404。
export function practicePagePath(id: string | number): string {
  return "/practice/" + encodeURIComponent(String(id));
}

export function exerciseSubmissionsPath(id: string | number): string {
  return exercisePath(id) + "/submissions";
}

export type LastSubmission = {
  // 后端缺 is_passed 时保持 null，页面显示「结果未知」，不猜成通过或未通过。
  isPassed: boolean | null;
  strength: EvidenceStrength;
  submittedAt: string | null;
};

export type ExerciseSummary = {
  id: string;
  lessonId: string;
  code: string;
  title: string;
  difficulty: string;
  estimatedMinutes: number;
  contentVersion: string;
  lastSubmission: LastSubmission | null;
};

export type VisibleTest = { input: string; expected: string };

export type ExerciseDetail = {
  id: string;
  title: string;
  prompt: string;
  starterCode: string;
  visibleTests: VisibleTest[];
  estimatedMinutes: number;
  difficulty: string;
};

export type SubmissionCheck = { name: string; passed: boolean; detail: string };

export type SubmissionRecord = {
  submissionId: string;
  submittedAt: string | null;
  isPassed: boolean | null;
  judgingMode: string;
  verificationMethod: string;
  verificationStrength: EvidenceStrength;
  evidenceLabel: string;
  checks: SubmissionCheck[];
};

export type SubmissionResult = SubmissionRecord;

export type ExerciseDetailPayload = {
  exercise: ExerciseDetail;
  history: SubmissionRecord[];
};

// 判定方式的中文说明。值域来自冻结契约的 verification_method，未知值原样显示而不是抹成默认。
const VERIFICATION_METHOD_LABELS: Record<string, string> = {
  static_rule: "静态规则对比（未运行代码）",
  self_report: "用户自检申报（未验证）",
};

export function verificationMethodLabel(method: string): string {
  if (!method) {
    return "后端未返回";
  }
  return VERIFICATION_METHOD_LABELS[method] ?? method;
}

export function submissionStateLabel(isPassed: boolean | null): string {
  if (isPassed === null) {
    return "结果未知";
  }
  return isPassed ? "通过" : "未通过";
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

function readText(
  record: Record<string, unknown>,
  keys: string[],
  fallback: string,
): string {
  return readString(record, keys) ?? fallback;
}

function readId(record: Record<string, unknown>, keys: string[]): string {
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

// 自检用例的 input/expected 可能是字符串或数字，统一转文本用于展示与对照，不做类型推断。
function readScalarText(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "string") {
      return value;
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
    if (typeof value === "boolean") {
      return value ? "true" : "false";
    }
  }
  return "";
}

function readStrength(record: Record<string, unknown>): EvidenceStrength {
  const value = readString(record, ["verification_strength", "verificationStrength"]);
  if (value === "assessed" || value === "self_reported" || value === "verified") {
    return value;
  }
  return "none";
}

// 后端 difficulty 是 smallint 1..5（与 /lessons 一致），不是文本；这里同时接受数字与数字字符串，
// 统一映射为中文标签。未知值返回空串，页面据此不渲染难度 Tag，而不是把数字直接当文案或猜测档位。
const DIFFICULTY_LABELS: Record<number, string> = {
  1: "入门",
  2: "基础",
  3: "中等",
  4: "进阶",
  5: "挑战",
};

function readDifficulty(record: Record<string, unknown>, keys: string[]): string {
  for (const key of keys) {
    const value = record[key];
    let level: number | null = null;
    if (typeof value === "number" && Number.isFinite(value)) {
      level = Math.round(value);
    } else if (typeof value === "string" && /^[1-5]$/.test(value.trim())) {
      level = Number(value.trim());
    }
    if (level !== null) {
      return DIFFICULTY_LABELS[level] ?? "";
    }
  }
  return "";
}

function readVisibleTests(value: unknown): VisibleTest[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const tests: VisibleTest[] = [];
  for (const entry of list) {
    const record = asRecord(entry);
    if (!record) {
      continue;
    }
    const input = readScalarText(record, ["input"]);
    const expected = readScalarText(record, ["expected"]);
    if (input === "" && expected === "") {
      continue;
    }
    tests.push({ input, expected });
  }
  return tests;
}

function readChecks(value: unknown): SubmissionCheck[] | null {
  const list = asArray(value);
  if (!list) {
    return null;
  }
  const checks: SubmissionCheck[] = [];
  for (const entry of list) {
    const record = asRecord(entry);
    if (!record) {
      continue;
    }
    const name = readString(record, ["name"]);
    const passed = readBoolean(record, ["passed"]);
    if (!name || passed === null) {
      continue;
    }
    checks.push({ name, passed, detail: readText(record, ["detail"], "") });
  }
  return checks;
}

function parseLastSubmission(value: unknown): LastSubmission | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    isPassed: readBoolean(record, ["is_passed", "isPassed", "passed"]),
    strength: readStrength(record),
    submittedAt: readString(record, ["submitted_at", "submittedAt", "created_at"]),
  };
}

function parseExerciseSummary(value: unknown): ExerciseSummary | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = readId(record, ["id"]);
  const title = readString(record, ["title"]);
  if (!id || !title) {
    return null;
  }
  return {
    id,
    lessonId: readId(record, ["lesson_id", "lessonId"]),
    code: readText(record, ["code"], ""),
    title,
    difficulty: readDifficulty(record, ["difficulty"]),
    estimatedMinutes: readNumber(record, ["estimated_minutes", "estimatedMinutes"]) ?? 0,
    contentVersion: readId(record, ["content_version", "contentVersion"]),
    lastSubmission: parseLastSubmission(record.last_submission ?? record.lastSubmission),
  };
}

export function parseExerciseList(body: unknown): ExerciseSummary[] | null {
  const record = asRecord(body);
  const list = record
    ? asArray(record.exercises) ?? asArray(record.items) ?? asArray(record.data)
    : asArray(body);
  if (!list) {
    return null;
  }
  const exercises: ExerciseSummary[] = [];
  for (const entry of list) {
    const exercise = parseExerciseSummary(entry);
    if (exercise) {
      exercises.push(exercise);
    }
  }
  return exercises;
}

// 单条提交记录：只有出现可识别字段时才计入历史，避免把空对象渲染成一行空白提交。
function hasSubmissionSignal(record: Record<string, unknown>): boolean {
  const keys = [
    "submission_id",
    "submissionId",
    "submitted_at",
    "submittedAt",
    "created_at",
    "is_passed",
    "isPassed",
    "passed",
    "verification_method",
    "verificationMethod",
    "verification_strength",
    "verificationStrength",
    "checks",
  ];
  for (const key of keys) {
    if (record[key] !== undefined) {
      return true;
    }
  }
  return false;
}

function parseSubmissionRecord(record: Record<string, unknown>): SubmissionRecord {
  return {
    submissionId: readId(record, ["submission_id", "submissionId", "id"]),
    submittedAt: readString(record, ["submitted_at", "submittedAt", "created_at", "createdAt"]),
    isPassed: readBoolean(record, ["is_passed", "isPassed", "passed"]),
    judgingMode: readText(record, ["judging_mode", "judgingMode"], ""),
    verificationMethod: readText(record, ["verification_method", "verificationMethod"], ""),
    verificationStrength: readStrength(record),
    evidenceLabel: readText(record, ["evidence_label", "evidenceLabel"], ""),
    checks: readChecks(record.checks) ?? [],
  };
}

export function parseSubmissionList(body: unknown): SubmissionRecord[] | null {
  const record = asRecord(body);
  const list = Array.isArray(body)
    ? body
    : record
      ? asArray(record.submissions) ??
        asArray(record.items) ??
        asArray(record.history) ??
        asArray(record.data)
      : null;
  if (!list) {
    return null;
  }
  const records: SubmissionRecord[] = [];
  for (const entry of list) {
    const item = asRecord(entry);
    if (!item || !hasSubmissionSignal(item)) {
      continue;
    }
    records.push(parseSubmissionRecord(item));
  }
  // 历史一律倒序：最近一次提交排在最前，页面不再二次排序。
  records.sort((left, right) => {
    const a = left.submittedAt ?? "";
    const b = right.submittedAt ?? "";
    if (a === b) {
      return 0;
    }
    return a < b ? 1 : -1;
  });
  return records;
}

export function parseSubmissionResult(body: unknown): SubmissionResult | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  // checks 是冻结响应里的必备字段：缺失说明契约不一致，直接判为不可渲染，由页面显示错误。
  const checks = readChecks(record.checks);
  if (!checks) {
    return null;
  }
  return { ...parseSubmissionRecord(record), checks };
}

export function parseExerciseDetail(body: unknown): ExerciseDetailPayload | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  // 冻结契约写的是 {exercise:{...}, history:[...]}；已实现的后端若直接平铺，这里退回顶层。
  const exercise = asRecord(record.exercise) ?? record;
  const title = readString(exercise, ["title"]);
  if (!title) {
    return null;
  }
  const history: SubmissionRecord[] = [];
  const rawHistory = asArray(record.history);
  if (rawHistory) {
    for (const entry of rawHistory) {
      const item = asRecord(entry);
      if (!item || !hasSubmissionSignal(item)) {
        continue;
      }
      history.push(parseSubmissionRecord(item));
    }
  }
  history.sort((left, right) => {
    const a = left.submittedAt ?? "";
    const b = right.submittedAt ?? "";
    if (a === b) {
      return 0;
    }
    return a < b ? 1 : -1;
  });
  return {
    exercise: {
      id: readId(exercise, ["id"]),
      title,
      prompt: readText(exercise, ["prompt"], ""),
      starterCode: readText(exercise, ["starter_code", "starterCode"], ""),
      visibleTests: readVisibleTests(exercise.visible_tests ?? exercise.visibleTests),
      estimatedMinutes: readNumber(exercise, ["estimated_minutes", "estimatedMinutes"]) ?? 0,
      difficulty: readDifficulty(exercise, ["difficulty"]),
    },
    history,
  };
}
