export type QuestionKind = "single_choice" | "code_reading" | "fix_error";

export type AnswerChoice = "A" | "B" | "C" | "D";

export type QuestionOption = { key: AnswerChoice; text: string };

export type Question = {
  id: string;
  number: number;
  domain: string;
  kind: QuestionKind;
  prompt: string;
  options: QuestionOption[];
};

export type DiagnosticPaper = {
  questionSetVersion: string;
  ruleVersion: string;
  total: number;
  questions: Question[];
};

export type DomainMeta = {
  code: string;
  nameZh: string;
  orderIndex: number;
  summary: string;
};

export const DOMAINS: DomainMeta[] = [
  {
    code: "route_a.a1",
    nameZh: "Python 基础",
    orderIndex: 1,
    summary: "变量、容器、控制流与函数",
  },
  {
    code: "route_a.a2",
    nameZh: "编程实践",
    orderIndex: 2,
    summary: "工具链、调试、异常与代码组织",
  },
  {
    code: "route_a.a3",
    nameZh: "API",
    orderIndex: 3,
    summary: "HTTP 语义、状态码与接口契约",
  },
  {
    code: "route_a.a4",
    nameZh: "LLM",
    orderIndex: 4,
    summary: "模型调用参数、提示词与输出约束",
  },
  {
    code: "route_a.a5",
    nameZh: "RAG 与 Agent 基础",
    orderIndex: 5,
    summary: "检索切片、排序与工具调用",
  },
  {
    code: "route_a.a6",
    nameZh: "简单 AI 项目",
    orderIndex: 6,
    summary: "配置管理、上线检查与可运维性",
  },
];

export const KIND_LABELS: Record<QuestionKind, string> = {
  single_choice: "单选",
  code_reading: "代码阅读",
  fix_error: "改错",
};

const ANSWER_CHOICES: string[] = ["A", "B", "C", "D"];

function isAnswerChoice(value: unknown): value is AnswerChoice {
  return typeof value === "string" && ANSWER_CHOICES.indexOf(value) >= 0;
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
    if (typeof value === "string" && value.trim() !== "") {
      return value;
    }
  }
  return null;
}

function readInteger(record: Record<string, unknown>, keys: string[]): number | null {
  for (const key of keys) {
    const value = record[key];
    if (typeof value === "number" && Number.isFinite(value)) {
      return Math.round(value);
    }
    if (typeof value === "string" && value.trim() !== "") {
      const parsed = Number(value);
      if (Number.isFinite(parsed)) {
        return Math.round(parsed);
      }
    }
  }
  return null;
}

// 后端题型写着 bug_fix，早期页面写着 fix_error；两种拼写都归一成同一枚举，缺失或未知题型按单选展示。
function parseKind(value: unknown): QuestionKind {
  if (value === "code_reading") {
    return "code_reading";
  }
  if (value === "bug_fix" || value === "fix_error") {
    return "fix_error";
  }
  return "single_choice";
}

function parseOptions(value: unknown): QuestionOption[] {
  const list = asArray(value);
  if (!list) {
    return [];
  }
  const options: QuestionOption[] = [];
  for (const item of list) {
    const record = asRecord(item);
    if (!record) {
      continue;
    }
    const key = record.key;
    const text = readString(record, ["text"]);
    if (!isAnswerChoice(key) || !text) {
      continue;
    }
    options.push({ key, text });
  }
  return options;
}

function parseQuestion(value: unknown, fallbackNumber: number): Question | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const id = readString(record, ["id"]);
  const prompt = readString(record, ["prompt", "stem"]);
  const options = parseOptions(record.options);
  if (!id || !prompt || options.length === 0) {
    return null;
  }
  return {
    id,
    number: readInteger(record, ["order", "number"]) ?? fallbackNumber,
    domain: readString(record, ["domain_code", "domain"]) ?? "",
    kind: parseKind(record.type ?? record.kind),
    prompt,
    options,
  };
}

// 只读取白名单字段：即使响应里混入 answer / correct 之类的键，也不会进入前端状态。
export function parseDiagnosticPaper(body: unknown): DiagnosticPaper | null {
  const record = asRecord(body);
  const rawQuestions = record ? asArray(record.questions) : null;
  if (!record || !rawQuestions) {
    return null;
  }
  const questions: Question[] = [];
  const seen: string[] = [];
  for (let index = 0; index < rawQuestions.length; index += 1) {
    const question = parseQuestion(rawQuestions[index], index + 1);
    if (!question || seen.indexOf(question.id) >= 0) {
      continue;
    }
    seen.push(question.id);
    questions.push(question);
  }
  if (questions.length === 0) {
    return null;
  }
  questions.sort((left, right) => left.number - right.number);
  const declaredTotal = readInteger(record, ["total"]);
  if (declaredTotal !== null && declaredTotal !== questions.length) {
    return null;
  }
  return {
    questionSetVersion: readString(record, ["question_set_version", "questionSetVersion"]) ?? "",
    ruleVersion: readString(record, ["rule_version", "ruleVersion"]) ?? "",
    total: questions.length,
    questions,
  };
}
