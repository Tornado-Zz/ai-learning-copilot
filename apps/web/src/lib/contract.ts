export type AssessmentState =
  | "unassessed"
  | "assessed_below_threshold"
  | "established"
  | "requested_verification";

export type EvidenceStrength = "none" | "self_reported" | "assessed" | "verified";

export type TimezoneSource = "default" | "user_confirmed";

export type MeUser = {
  id: number | null;
  displayName: string;
  timezone: string;
  timezoneSource: TimezoneSource;
};

export type MeProfile = {
  studyDays: number[];
  dailyMinutes: number;
  weeklyMinutes: number;
};

export type SkillLevelRow = {
  code: string;
  nameZh: string;
  level: number;
  state: AssessmentState;
  evidenceKind: string | null;
  evidenceStrength: EvidenceStrength;
};

export type UsersMe = {
  user: MeUser;
  profile: MeProfile;
  skills: SkillLevelRow[];
};

export type SkillRow = {
  code: string;
  nameZh: string;
  level: string;
  orderIndex: number;
};

export type DomainScore = {
  skillCode: string;
  correct: number;
  total: number;
  rate: number;
  level: number;
  state: AssessmentState;
};

export type DiagnosticResult = {
  attemptId: number | null;
  ruleVersion: string;
  questionSetVersion: string | null;
  domains: DomainScore[];
};

export type PlanDay = { date: string; minutes: number };

export type HistoryItem = {
  attemptId: number | null;
  questionSetVersion: string;
  ruleVersion: string;
  submittedAt: string | null;
  totalCorrect: number | null;
  totalQuestions: number | null;
  domains: DomainScore[];
};

export type AttemptQuestion = {
  id: string;
  number: number;
  domainCode: string;
  kind: string;
  prompt: string;
  yourChoice: string | null;
  correctChoice: string | null;
  isCorrect: boolean | null;
};

export type AttemptDetail = {
  attemptId: number | null;
  submittedAt: string | null;
  questionSetVersion: string;
  ruleVersion: string;
  totalCorrect: number | null;
  totalQuestions: number | null;
  domains: DomainScore[];
  questions: AttemptQuestion[];
};

export type ApiErrorDetails = {
  code: string;
  message: string;
  details: unknown;
};

const ASSESSMENT_STATES: AssessmentState[] = [
  "unassessed",
  "assessed_below_threshold",
  "established",
  "requested_verification",
];

export function isAssessmentState(value: unknown): value is AssessmentState {
  return (
    typeof value === "string" &&
    (ASSESSMENT_STATES as string[]).indexOf(value) >= 0
  );
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
    if (typeof value === "string") {
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

function readNumberArray(
  record: Record<string, unknown>,
  keys: string[],
): number[] | null {
  for (const key of keys) {
    const value = asArray(record[key]);
    if (!value) {
      continue;
    }
    const numbers: number[] = [];
    for (const item of value) {
      if (typeof item === "number" && Number.isFinite(item)) {
        numbers.push(item);
      }
    }
    return numbers;
  }
  return null;
}

function clampLevel(value: number | null): number {
  if (value === null) {
    return 0;
  }
  return Math.min(4, Math.max(0, Math.round(value)));
}

function parseStrength(value: unknown): EvidenceStrength {
  if (value === "verified" || value === "assessed" || value === "self_reported") {
    return value;
  }
  return "none";
}

function parseSkillLevelRow(value: unknown): SkillLevelRow | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const code = readString(record, ["code", "skill_code"]);
  if (!code) {
    return null;
  }
  // 冻结契约 §6.1 用 state；调度任务书用 assessment_state。两个键都接受，值域仍只认四个枚举。
  const state = record.state ?? record.assessment_state;
  return {
    code,
    nameZh: readString(record, ["name_zh", "nameZh"]) ?? "",
    level: clampLevel(readNumber(record, ["level"])),
    state: isAssessmentState(state) ? state : "unassessed",
    evidenceKind: readString(record, ["evidence_kind", "evidenceKind"]),
    evidenceStrength: parseStrength(record.evidence_strength),
  };
}

function parseDomainScore(
  value: unknown,
  fallbackCode?: string,
): DomainScore | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const code = readString(record, ["skill_code", "skillCode", "code"]) ?? fallbackCode;
  if (!code) {
    return null;
  }
  const correct = readNumber(record, ["correct"]) ?? 0;
  const total = readNumber(record, ["total"]) ?? 0;
  const rate = readNumber(record, ["rate"]);
  const state = record.state ?? record.assessment_state;
  return {
    skillCode: code,
    correct,
    total,
    rate: rate === null ? (total > 0 ? correct / total : 0) : rate,
    level: clampLevel(readNumber(record, ["level"])),
    state: isAssessmentState(state) ? state : "unassessed",
  };
}

function parseDomainList(value: unknown): DomainScore[] {
  const list = asArray(value);
  if (list) {
    const parsed: DomainScore[] = [];
    for (const item of list) {
      const domain = parseDomainScore(item);
      if (domain) {
        parsed.push(domain);
      }
    }
    return parsed;
  }
  const map = asRecord(value);
  if (!map) {
    return [];
  }
  const parsed: DomainScore[] = [];
  for (const code of Object.keys(map)) {
    const domain = parseDomainScore(map[code], code);
    if (domain) {
      parsed.push(domain);
    }
  }
  return parsed;
}

export function parseUsersMe(body: unknown): UsersMe | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  const user = asRecord(record.user);
  const profile = asRecord(record.profile);
  if (!user && !profile) {
    return null;
  }
  const skills: SkillLevelRow[] = [];
  const rawSkills = asArray(record.skills);
  if (rawSkills) {
    for (const row of rawSkills) {
      const skill = parseSkillLevelRow(row);
      if (skill) {
        skills.push(skill);
      }
    }
  }
  const studyDays = profile ? readNumberArray(profile, ["study_days", "studyDays"]) : null;
  return {
    user: {
      id: user ? readNumber(user, ["id"]) : null,
      displayName: user ? readString(user, ["display_name", "displayName"]) ?? "" : "",
      timezone: user ? readString(user, ["timezone"]) ?? "Asia/Shanghai" : "Asia/Shanghai",
      timezoneSource:
        user && user.timezone_source === "user_confirmed" ? "user_confirmed" : "default",
    },
    profile: {
      studyDays: studyDays ?? [],
      dailyMinutes: profile ? readNumber(profile, ["daily_minutes", "dailyMinutes"]) ?? 60 : 60,
      weeklyMinutes: profile
        ? readNumber(profile, ["weekly_minutes", "weeklyMinutes"]) ??
          (studyDays ? studyDays.length : 0) * 60
        : 0,
    },
    skills,
  };
}

export function parseSkills(body: unknown): SkillRow[] | null {
  const record = asRecord(body);
  const list = record ? asArray(record.skills) : asArray(body);
  if (!list) {
    return null;
  }
  const rows: SkillRow[] = [];
  for (const item of list) {
    const row = asRecord(item);
    if (!row) {
      continue;
    }
    const code = readString(row, ["code", "skill_code"]);
    if (!code) {
      continue;
    }
    rows.push({
      code,
      nameZh: readString(row, ["name_zh", "nameZh"]) ?? "",
      level: readString(row, ["level"]) ?? "domain",
      orderIndex: readNumber(row, ["order_index", "orderIndex"]) ?? rows.length + 1,
    });
  }
  return rows;
}

export function parseDiagnosticResult(body: unknown): DiagnosticResult | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  const domains = parseDomainList(record.domains ?? record.domain_scores);
  if (domains.length === 0) {
    return null;
  }
  return {
    attemptId: readNumber(record, ["attempt_id", "attemptId", "id"]),
    ruleVersion: readString(record, ["rule_version", "ruleVersion"]) ?? "",
    questionSetVersion: readString(record, ["question_set_version", "questionSetVersion"]),
    domains,
  };
}

export function parseHistoryItem(value: unknown): HistoryItem | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    attemptId: readNumber(record, ["attempt_id", "attemptId", "id"]),
    questionSetVersion:
      readString(record, ["question_set_version", "questionSetVersion"]) ?? "—",
    ruleVersion: readString(record, ["rule_version", "ruleVersion"]) ?? "—",
    submittedAt: readString(record, [
      "submitted_at",
      "submittedAt",
      "created_at",
      "createdAt",
    ]),
    totalCorrect: readNumber(record, ["total_correct", "totalCorrect"]),
    totalQuestions: readNumber(record, ["total_questions", "totalQuestions"]),
    domains: parseDomainList(record.domains ?? record.domain_scores),
  };
}

export function parseHistory(body: unknown): HistoryItem[] | null {
  const list = asArray(body);
  const record = list ? null : asRecord(body);
  const container = list
    ? list
    : record
      ? asArray(record.attempts) ??
        asArray(record.items) ??
        asArray(record.history) ??
        asArray(record.list) ??
        asArray(record.data)
      : null;
  if (!container) {
    return null;
  }
  const items: HistoryItem[] = [];
  for (const entry of container) {
    const item = parseHistoryItem(entry);
    if (item) {
      items.push(item);
    }
  }
  return items;
}

function parseAttemptQuestion(value: unknown, fallbackNumber: number): AttemptQuestion | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = readString(record, ["id", "question_id", "questionId"]);
  if (!id) {
    return null;
  }
  // 真实响应模型 AttemptQuestionOut：selected 是用户所选（可为 null），correct 是正确选项字符串，
  // is_correct 才是布尔判定；缺失的字段一律留空，页面显示「—」而不是猜一个正确答案。
  const yourChoice = readString(record, ["selected", "your_choice", "user_choice", "selected_choice"]);
  const correctChoice = readString(record, ["correct", "correct_choice", "correct_answer"]);
  const explicit = readBoolean(record, ["is_correct"]);
  let isCorrect: boolean | null = explicit;
  if (isCorrect === null && yourChoice !== null && correctChoice !== null) {
    isCorrect = yourChoice.trim().toUpperCase() === correctChoice.trim().toUpperCase();
  }
  return {
    id,
    number: readNumber(record, ["order", "number"]) ?? fallbackNumber,
    domainCode: readString(record, ["domain_code", "domainCode", "domain"]) ?? "",
    kind: readString(record, ["type", "kind"]) ?? "",
    prompt: readString(record, ["prompt", "stem"]) ?? "",
    yourChoice,
    correctChoice,
    isCorrect,
  };
}

// GET /api/v1/diagnostics/attempts/{id}：只有已提交批次才有这个响应。
export function parseAttemptDetail(body: unknown): AttemptDetail | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  const rawQuestions =
    asArray(record.questions) ?? asArray(record.items) ?? asArray(record.details) ?? [];
  const questions: AttemptQuestion[] = [];
  const seen: string[] = [];
  for (let index = 0; index < rawQuestions.length; index += 1) {
    const question = parseAttemptQuestion(rawQuestions[index], index + 1);
    if (!question || seen.indexOf(question.id) >= 0) {
      continue;
    }
    seen.push(question.id);
    questions.push(question);
  }
  questions.sort((left, right) => left.number - right.number);
  const domains = parseDomainList(record.domains ?? record.domain_scores);
  if (domains.length === 0 && questions.length === 0) {
    return null;
  }
  return {
    attemptId: readNumber(record, ["attempt_id", "attemptId", "id"]),
    submittedAt: readString(record, ["submitted_at", "submittedAt", "created_at", "createdAt"]),
    questionSetVersion:
      readString(record, ["question_set_version", "questionSetVersion"]) ?? "—",
    ruleVersion: readString(record, ["rule_version", "ruleVersion"]) ?? "—",
    totalCorrect: readNumber(record, ["total_correct", "totalCorrect"]),
    totalQuestions: readNumber(record, ["total_questions", "totalQuestions"]),
    domains,
    questions,
  };
}

export function parseApiError(body: unknown): ApiErrorDetails | null {
  const record = asRecord(body);
  const error = record ? asRecord(record.error) : null;
  if (!record || !error) {
    return null;
  }
  const code = readString(error, ["code"]);
  const message = readString(error, ["message"]);
  if (!code && !message) {
    return null;
  }
  return {
    code: code ?? "INTERNAL_ERROR",
    message: message ?? "请求失败",
    details: error.details ?? null,
  };
}

export function readRequestId(body: unknown): string | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  return readString(record, ["request_id", "requestId"]);
}
