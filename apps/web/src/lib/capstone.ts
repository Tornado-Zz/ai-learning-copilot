import type { ApiFailure } from "@/lib/http";

// v0.1.3 · 结业作品提交（自评）
//
// 诚实性红线：这是单用户本地应用，不存在第三方评审者。唯一的结论来源是
// reviewer='self'（本人自评），所以本模块产出的文案只用「自评」，
// 不使用「审核 / 认证 / 评审专家」等暗示第三方背书的措辞。
//
// 前端只镜像冻结契约，不推断服务端状态：字段缺失一律解析为 null
// （渲染成「—」），不补 0、不补 false、不把「没返回」写成「未达标」。

export const CAPSTONE_SUBMISSIONS_PATH = "/api/v1/capstone/submissions";
export const CAPSTONE_LIST_LIMIT = 20;
export const DASH = "—";

export type CapstoneStatus = "draft" | "submitted" | "reviewed";
export type CapstoneVerdict = "pass" | "needs_work";

// 后端 self_checks 是 jsonb 数组，元素为字符串（app/schemas/capstone.py:
// `self_checks: list[str]`），所以一条记录 = 一条自检陈述。
// 勾选项写成固定清单 label 原文；共享备注作为一条带前缀的陈述追加在末尾。
export type SelfCheckEntry = {
  key: string;
  text: string;
  checked: boolean | null;
};

export type ReadinessRequirementSnapshot = {
  key: string;
  label: string | null;
  required: number | null;
  actual: number | null;
  met: boolean | null;
};

export type ReadinessSnapshot = {
  ready: boolean | null;
  requirements: ReadinessRequirementSnapshot[] | null;
  note: string | null;
};

export type CapstoneSubmission = {
  id: number;
  title: string | null;
  summary: string | null;
  repoUrl: string | null;
  runInstructions: string | null;
  selfChecks: SelfCheckEntry[] | null;
  readinessSnapshot: ReadinessSnapshot | null;
  status: CapstoneStatus | null;
  verdict: CapstoneVerdict | null;
  reviewer: string | null;
  reviewerNote: string | null;
  submittedAt: string | null;
  reviewedAt: string | null;
  createdAt: string | null;
  updatedAt: string | null;
};

export type CapstoneSubmissionList = {
  items: CapstoneSubmission[];
  total: number | null;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

function readNumber(source: Record<string, unknown> | null, key: string): number | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function readBoolean(source: Record<string, unknown> | null, key: string): boolean | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  return typeof value === "boolean" ? value : null;
}

function readText(source: Record<string, unknown> | null, key: string): string | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }
  return value;
}

function readStatus(value: unknown): CapstoneStatus | null {
  if (value === "draft" || value === "submitted" || value === "reviewed") {
    return value;
  }
  return null;
}

function readVerdict(value: unknown): CapstoneVerdict | null {
  if (value === "pass" || value === "needs_work") {
    return value;
  }
  return null;
}

// 契约是 list[str]；这里仍接受对象元素（checked/label 兼容旧形状），
// 元素为空字符串时跳过，不编造内容。
function parseSelfCheck(value: unknown, index: number): SelfCheckEntry | null {
  if (typeof value === "string") {
    const text = value.trim();
    if (text === "") {
      return null;
    }
    return { key: "item-" + String(index), text, checked: null };
  }
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const text =
    readText(record, "text") ?? readText(record, "label") ?? readText(record, "name");
  if (text === null) {
    return null;
  }
  return {
    key: readText(record, "key") ?? "item-" + String(index),
    text,
    checked: readBoolean(record, "checked"),
  };
}

function parseSelfChecks(value: unknown): SelfCheckEntry[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const rows: SelfCheckEntry[] = [];
  value.forEach((item, index) => {
    const row = parseSelfCheck(item, index);
    if (row) {
      rows.push(row);
    }
  });
  return rows;
}

function parseRequirementSnapshot(value: unknown): ReadinessRequirementSnapshot | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const key = readText(record, "key");
  if (key === null) {
    return null;
  }
  return {
    key,
    label: readText(record, "label"),
    required: readNumber(record, "required"),
    actual: readNumber(record, "actual"),
    met: readBoolean(record, "met"),
  };
}

function parseReadinessSnapshot(value: unknown): ReadinessSnapshot | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  let requirements: ReadinessRequirementSnapshot[] | null = null;
  if (Array.isArray(record.requirements)) {
    requirements = [];
    for (const item of record.requirements) {
      const row = parseRequirementSnapshot(item);
      if (row) {
        requirements.push(row);
      }
    }
  }
  return {
    ready: readBoolean(record, "ready"),
    requirements,
    note: readText(record, "note"),
  };
}

export function parseSubmission(value: unknown): CapstoneSubmission | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = readNumber(record, "id");
  if (id === null) {
    // 没有 id 的记录无法定位（也无法发起后续状态流转），不渲染也不编造。
    return null;
  }
  return {
    id,
    title: readText(record, "title"),
    summary: readText(record, "summary"),
    repoUrl: readText(record, "repo_url"),
    runInstructions: readText(record, "run_instructions"),
    selfChecks: parseSelfChecks(record.self_checks),
    readinessSnapshot: parseReadinessSnapshot(record.readiness_snapshot),
    status: readStatus(record.status),
    verdict: readVerdict(record.verdict),
    reviewer: readText(record, "reviewer"),
    reviewerNote: readText(record, "reviewer_note"),
    submittedAt: readText(record, "submitted_at"),
    reviewedAt: readText(record, "reviewed_at"),
    createdAt: readText(record, "created_at"),
    updatedAt: readText(record, "updated_at"),
  };
}

// 冻结契约写明 create 返回完整对象；detail 只写「详情」，未写包装形状，
// 因此这里同时接受裸对象与 {item|submission|data: {...}} 两种写法。
export function parseSubmissionEnvelope(body: unknown): CapstoneSubmission | null {
  const direct = parseSubmission(body);
  if (direct) {
    return direct;
  }
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  for (const key of ["item", "submission", "data"]) {
    const nested = parseSubmission(record[key]);
    if (nested) {
      return nested;
    }
  }
  return null;
}

export function parseSubmissionList(body: unknown): CapstoneSubmissionList | null {
  if (Array.isArray(body)) {
    return { items: parseSubmissionArray(body), total: null };
  }
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  const raw = record.items ?? record.data;
  if (!Array.isArray(raw)) {
    return null;
  }
  return { items: parseSubmissionArray(raw), total: readNumber(record, "total") };
}

function parseSubmissionArray(value: unknown[]): CapstoneSubmission[] {
  const rows: CapstoneSubmission[] = [];
  for (const item of value) {
    const row = parseSubmission(item);
    if (row) {
      rows.push(row);
    }
  }
  return rows;
}

// PATCH /submit /review 的响应体不在冻结契约里，只需要知道「服务端接受了」；
// 能解析出对象就用它，解析不出来也当成功（随后以 GET 详情为准）。
export type CapstoneMutationResult =
  | { kind: "submission"; submission: CapstoneSubmission }
  | { kind: "acknowledged" };

export function parseMutationResult(body: unknown): CapstoneMutationResult {
  const submission = parseSubmissionEnvelope(body);
  if (submission) {
    return { kind: "submission", submission };
  }
  return { kind: "acknowledged" };
}

export function capstoneListPath(limit: number = CAPSTONE_LIST_LIMIT): string {
  return CAPSTONE_SUBMISSIONS_PATH + "?limit=" + String(limit);
}

export function capstoneItemPath(id: number): string {
  return CAPSTONE_SUBMISSIONS_PATH + "/" + String(id);
}

export function capstoneSubmitPath(id: number): string {
  return capstoneItemPath(id) + "/submit";
}

export function capstoneReviewPath(id: number): string {
  return capstoneItemPath(id) + "/review";
}

// 固定的 4 项自评清单。label 原文写进 self_checks（list[str]），
// 因此记录自解释：勾选了哪几项、备注写了什么，都能从数组直接读回来。
export const SELF_CHECK_ITEMS: ReadonlyArray<{ key: string; label: string }> = [
  { key: "runs_locally", label: "我能按自己写的运行说明把作品在本地跑起来" },
  { key: "features_complete", label: "README 里承诺的功能都已实现，没有留半成品入口" },
  { key: "real_data_only", label: "没有伪造演示数据，页面上的数字都能追溯到真实记录" },
  { key: "limits_documented", label: "已知限制与未实现项都在文档里写清楚了" },
];

// 共享备注作为一条带前缀的陈述追加在数组末尾（list[str] 放不下结构化备注）。
export const SELF_CHECK_NOTE_PREFIX = "备注：";

export type SelfCheckDraft = {
  key: string;
  label: string;
  checked: boolean;
};

export type CapstoneSubmissionDraft = {
  title: string;
  summary: string;
  repoUrl: string;
  runInstructions: string;
  selfChecks: SelfCheckDraft[];
  selfNote: string;
};

export type CapstoneSubmissionBody = {
  title: string;
  summary: string;
  repo_url: string | null;
  run_instructions: string;
  self_checks: string[];
};

export function emptyDraft(): CapstoneSubmissionDraft {
  return {
    title: "",
    summary: "",
    repoUrl: "",
    runInstructions: "",
    selfChecks: SELF_CHECK_ITEMS.map((item) => ({
      key: item.key,
      label: item.label,
      checked: false,
    })),
    selfNote: "",
  };
}

// 把 self_checks 拆成「勾选项 label」与「共享备注」两部分：勾选项按固定清单的
// label 前缀匹配（文案以后改了也不会把历史记录误读成未勾选）。
export function splitSelfChecks(entries: SelfCheckEntry[] | null): {
  labels: string[];
  note: string | null;
} {
  const labels: string[] = [];
  let note: string | null = null;
  for (const entry of entries ?? []) {
    if (entry.text.startsWith(SELF_CHECK_NOTE_PREFIX) || entry.text.startsWith("备注:")) {
      const value = entry.text.replace(/^(备注：|备注:)/, "").trim();
      if (value !== "") {
        note = value;
      }
      continue;
    }
    labels.push(entry.text);
  }
  return { labels, note };
}

export function buildSelfChecks(draft: CapstoneSubmissionDraft): string[] {
  const checked = draft.selfChecks.filter((item) => item.checked).map((item) => item.label);
  const note = draft.selfNote.trim();
  if (note !== "") {
    checked.push(SELF_CHECK_NOTE_PREFIX + note);
  }
  return checked;
}

export function draftFromSubmission(submission: CapstoneSubmission): CapstoneSubmissionDraft {
  const { labels, note } = splitSelfChecks(submission.selfChecks);
  return {
    title: submission.title ?? "",
    summary: submission.summary ?? "",
    repoUrl: submission.repoUrl ?? "",
    runInstructions: submission.runInstructions ?? "",
    selfChecks: SELF_CHECK_ITEMS.map((item) => ({
      key: item.key,
      label: item.label,
      checked: labels.some((label) => label === item.label || label.startsWith(item.label)),
    })),
    selfNote: note ?? "",
  };
}

// repo_url 为空时提交 null（列本身 nullable）：空字符串会被后端当成
// 「不是 http(s) URL」的候选值，null 才是契约里「为空」的表达。
export function toSubmissionBody(draft: CapstoneSubmissionDraft): CapstoneSubmissionBody {
  const repoUrl = draft.repoUrl.trim();
  return {
    title: draft.title.trim(),
    summary: draft.summary.trim(),
    repo_url: repoUrl === "" ? null : repoUrl,
    run_instructions: draft.runInstructions.trim(),
    self_checks: buildSelfChecks(draft),
  };
}

export type CapstoneFieldErrors = {
  title: string | null;
  summary: string | null;
  repoUrl: string | null;
  runInstructions: string | null;
};

export const EMPTY_FIELD_ERRORS: CapstoneFieldErrors = {
  title: null,
  summary: null,
  repoUrl: null,
  runInstructions: null,
};

const HTTP_URL = /^https?:\/\/[^\s/]+[^\s]*$/i;

// 前端校验只镜像契约里已冻结的限制（title 1..120、summary/run_instructions 1..4000、
// repo_url 为空或 http(s)），不自造额外门槛（例如「必须勾选自评清单」只做提示）。
export function validateDraft(draft: CapstoneSubmissionDraft): CapstoneFieldErrors {
  const next: CapstoneFieldErrors = { ...EMPTY_FIELD_ERRORS };

  const title = draft.title.trim();
  if (title.length === 0) {
    next.title = "标题不能为空（1–120 个字符）。";
  } else if (title.length > 120) {
    next.title = "标题最多 120 个字符，当前 " + String(title.length) + " 个。";
  }

  const summary = draft.summary.trim();
  if (summary.length === 0) {
    next.summary = "作品简介不能为空（1–4000 个字符）。";
  } else if (summary.length > 4000) {
    next.summary = "作品简介最多 4000 个字符，当前 " + String(summary.length) + " 个。";
  }

  const runInstructions = draft.runInstructions.trim();
  if (runInstructions.length === 0) {
    next.runInstructions = "运行说明不能为空（1–4000 个字符）。";
  } else if (runInstructions.length > 4000) {
    next.runInstructions = "运行说明最多 4000 个字符，当前 " + String(runInstructions.length) + " 个。";
  }

  const repoUrl = draft.repoUrl.trim();
  if (repoUrl !== "" && !HTTP_URL.test(repoUrl)) {
    next.repoUrl = "仓库链接可以为空，或必须是 http:// / https:// 开头的地址。";
  }

  return next;
}

export function hasFieldErrors(errors: CapstoneFieldErrors): boolean {
  return (
    errors.title !== null ||
    errors.summary !== null ||
    errors.repoUrl !== null ||
    errors.runInstructions !== null
  );
}

export function statusLabel(status: CapstoneStatus | null): string {
  switch (status) {
    case "draft":
      return "草稿";
    case "submitted":
      return "已提交";
    case "reviewed":
      return "已自评";
    default:
      return DASH;
  }
}

export function verdictLabel(verdict: CapstoneVerdict | null): string {
  switch (verdict) {
    case "pass":
      return "通过";
    case "needs_work":
      return "需要改进";
    default:
      return DASH;
  }
}

export function reviewerLabel(reviewer: string | null): string {
  if (reviewer === null) {
    return DASH;
  }
  if (reviewer === "self") {
    return "self（本人自评）";
  }
  return reviewer;
}

export function capstoneFailureHint(failure: ApiFailure): string | null {
  switch (failure.code) {
    case "SELF_REVIEW_NOT_CONFIRMED":
      return "后端要求先勾选「我确认这是本人自评，不是第三方评审」，才会写入自评结论（400）。";
    case "CAPSTONE_INVALID_STATE":
      return "状态机限制：只有草稿可以修改，只有已提交的作品可以做自评（409）。请刷新后按当前状态操作。";
    case "VALIDATION_ERROR":
      return "字段超出冻结契约：标题 1–120、简介与运行说明 1–4000、仓库链接为空或 http(s)（422）。";
    case "NOT_FOUND":
      return "作品不存在、不属于当前用户，或该路由尚未注册（404）。";
    default:
      return failure.status === 404 ? "后端尚未注册该路由（404）。" : null;
  }
}
