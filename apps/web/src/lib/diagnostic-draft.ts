import type { AnswerChoice } from "@/lib/questions";

export const DRAFT_STORAGE_KEY = "alc-diagnostic-draft-v1";

type DiagnosticDraft = {
  questionSetVersion: string;
  ruleVersion: string;
  answers: Record<string, AnswerChoice>;
  currentIndex: number;
  updatedAt: number;
};

function isChoice(value: unknown): value is AnswerChoice {
  return value === "A" || value === "B" || value === "C" || value === "D";
}

// 题号是否属于当前题面由调用方决定：草稿模块不再持有任何题库定义。
function parseAnswers(value: unknown): Record<string, AnswerChoice> {
  const answers: Record<string, AnswerChoice> = {};
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return answers;
  }
  const record = value as Record<string, unknown>;
  for (const key of Object.keys(record)) {
    const choice = record[key];
    if (isChoice(choice)) {
      answers[key] = choice;
    }
  }
  return answers;
}

function parseDraft(raw: string | null): DiagnosticDraft | null {
  if (!raw) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  const index =
    typeof record.currentIndex === "number" && Number.isFinite(record.currentIndex)
      ? Math.round(record.currentIndex)
      : 0;
  return {
    questionSetVersion:
      typeof record.questionSetVersion === "string" ? record.questionSetVersion : "",
    ruleVersion: typeof record.ruleVersion === "string" ? record.ruleVersion : "",
    answers: parseAnswers(record.answers),
    currentIndex: Math.max(0, index),
    updatedAt: typeof record.updatedAt === "number" ? record.updatedAt : 0,
  };
}

export function readDraft(): DiagnosticDraft | null {
  try {
    return parseDraft(window.localStorage.getItem(DRAFT_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function writeDraft(draft: DiagnosticDraft): boolean {
  try {
    window.localStorage.setItem(DRAFT_STORAGE_KEY, JSON.stringify(draft));
    return true;
  } catch {
    return false;
  }
}

export function clearDraft(): void {
  try {
    window.localStorage.removeItem(DRAFT_STORAGE_KEY);
  } catch {
    // 存储不可用（隐私模式）时草稿只在内存里，页面仍然可用。
  }
}

// 提交令牌与草稿绑定：同一次诊断的多次重试必须复用同一个 token，
// 否则后端会把网络重试当成新批次追加（契约 §POST /diagnostics 幂等语义）。
export const ATTEMPT_TOKEN_STORAGE_KEY = "alc-diagnostic-token-v1";

export type AttemptTokenRecord = {
  token: string;
  questionSetVersion: string;
  ruleVersion: string;
  boundAt: number;
};

// localStorage 不可用（隐私模式）时仍要保证页面内的重试复用同一 token，
// 因此额外保留一份内存副本；两个副本都不存在时才生成新 token。
let memoryToken: AttemptTokenRecord | null = null;

function createToken(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return "attempt-" + String(Date.now()) + "-" + String(Math.random()).slice(2, 10);
}

function parseTokenRecord(raw: string | null): AttemptTokenRecord | null {
  if (!raw) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  if (typeof record.token !== "string" || record.token === "") {
    return null;
  }
  return {
    token: record.token,
    questionSetVersion:
      typeof record.questionSetVersion === "string" ? record.questionSetVersion : "",
    ruleVersion: typeof record.ruleVersion === "string" ? record.ruleVersion : "",
    boundAt: typeof record.boundAt === "number" ? record.boundAt : 0,
  };
}

export function readAttemptToken(): AttemptTokenRecord | null {
  try {
    const stored = parseTokenRecord(window.localStorage.getItem(ATTEMPT_TOKEN_STORAGE_KEY));
    if (stored) {
      return stored;
    }
  } catch {
    // 存储不可用时退回内存副本。
  }
  return memoryToken;
}

// 版本一致才复用：题面或规则版本变化意味着这是另一次诊断，旧 token 必须作废。
export function ensureAttemptToken(
  questionSetVersion: string,
  ruleVersion: string,
): string {
  const existing = readAttemptToken();
  if (
    existing &&
    existing.questionSetVersion === questionSetVersion &&
    existing.ruleVersion === ruleVersion
  ) {
    return existing.token;
  }
  const record: AttemptTokenRecord = {
    token: createToken(),
    questionSetVersion,
    ruleVersion,
    boundAt: Date.now(),
  };
  memoryToken = record;
  try {
    window.localStorage.setItem(ATTEMPT_TOKEN_STORAGE_KEY, JSON.stringify(record));
  } catch {
    // 存储不可用时只保留内存副本，本次页面会话内的重试仍复用同一 token。
  }
  return record.token;
}

export function clearAttemptToken(): void {
  memoryToken = null;
  try {
    window.localStorage.removeItem(ATTEMPT_TOKEN_STORAGE_KEY);
  } catch {
    // 忽略存储不可用。
  }
}
