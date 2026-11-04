"use client";

import { useCallback, useEffect, useState } from "react";
import { Button, ChoiceOption, fieldClass } from "@/components/form";
import { Alert, SkeletonLines } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { formatDateTime } from "@/lib/labels";
import {
  AI_EVIDENCE_NOTICE,
  AI_HISTORY_QUERY,
  AI_HISTORY_VISIBLE,
  AI_INTERACTIONS_PATH,
  AI_QUESTION_MAX,
  AI_TUTOR_PATH,
  AI_TUTOR_TIMEOUT_MS,
  AI_UNAVAILABLE_HINT,
  AI_UNAVAILABLE_NOTICE,
  ASSISTANCE_LEVEL_OPTIONS,
  DEFAULT_ASSISTANCE_LEVEL,
  aiStatusIsOk,
  aiStatusLabel,
  assistanceLevelLabel,
  assistanceLevelRisk,
  buildTutorBody,
  classifyTutorFailure,
  isKeyMissingFailure,
  parseInteractionList,
  parseTutorAnswer,
  readQuotaDetail,
  tokenText,
  validateQuestion,
} from "@/lib/ai-tutor";
import type { AiInteractionRecord, AiTutorAnswer, AssistanceLevel } from "@/lib/ai-tutor";
import {
  KNOWLEDGE_NO_CITATION,
  KNOWLEDGE_STALE_BADGE,
  sourceDomain,
} from "@/lib/knowledge";

// AI 导师区块。三处硬边界写死在结构里：
// 1) 请求体只有 question / assistance_level / context（id），本组件从不读取编辑器里的代码；
// 2) 密钥只在服务端，前端不读取、不拼接、不展示，界面上也不提供任何填 key 的输入；
// 3) 每个失败态都把后端 error.code 原样展示，不在前端改写成语义更强的结论。

type AnswerState =
  | { status: "idle" }
  | { status: "pending" }
  | { status: "ok"; answer: AiTutorAnswer }
  | { status: "failed"; failure: ApiFailure };

type HistoryState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; items: AiInteractionRecord[] };

export function AiTutorPanel({
  lessonId = null,
  exerciseId = null,
}: {
  lessonId?: string | null;
  exerciseId?: string | null;
}) {
  const [expanded, setExpanded] = useState(false);
  const [question, setQuestion] = useState("");
  const [level, setLevel] = useState<AssistanceLevel>(DEFAULT_ASSISTANCE_LEVEL);
  const [submitting, setSubmitting] = useState(false);
  const [validation, setValidation] = useState<string | null>(null);
  const [answer, setAnswer] = useState<AnswerState>({ status: "idle" });
  const [history, setHistory] = useState<HistoryState>({ status: "idle" });
  const [historyToken, setHistoryToken] = useState(0);

  // 历史只在这一区块展开后读取：折叠状态下页面不会为一个可选区块发请求。
  // loading 态由展开按钮（事件回调）置位，effect 内只写请求结果，避免同步 setState 触发级联渲染。
  useEffect(() => {
    if (!expanded) {
      return;
    }
    let active = true;
    void (async () => {
      const result = await apiRequest<AiInteractionRecord[]>(
        AI_INTERACTIONS_PATH + AI_HISTORY_QUERY,
        { parse: parseInteractionList },
      );
      if (!active) {
        return;
      }
      if (!result.ok) {
        setHistory({ status: "error", failure: result.failure });
        return;
      }
      setHistory({ status: "ready", items: result.data.slice(0, AI_HISTORY_VISIBLE) });
    })();
    return () => {
      active = false;
    };
  }, [expanded, historyToken]);

  const submit = useCallback(async () => {
    if (submitting) {
      return;
    }
    const invalid = validateQuestion(question);
    if (invalid !== null) {
      setValidation(invalid);
      return;
    }
    setValidation(null);
    setSubmitting(true);
    setAnswer({ status: "pending" });
    const response = await apiRequest<AiTutorAnswer>(AI_TUTOR_PATH, {
      method: "POST",
      body: buildTutorBody(question, level, { lessonId, exerciseId }),
      parse: parseTutorAnswer,
      timeoutMs: AI_TUTOR_TIMEOUT_MS,
    });
    setSubmitting(false);
    if (!response.ok) {
      setAnswer({ status: "failed", failure: response.failure });
    } else {
      setAnswer({ status: "ok", answer: response.data });
    }
    // 失败也会落一行 ai_interactions，所以无论成败都重读历史。
    setHistoryToken((value) => value + 1);
  }, [exerciseId, lessonId, level, question, submitting]);

  const panelId = "ai-tutor-panel";
  const questionId = "ai-tutor-question";
  const questionErrorId = "ai-tutor-question-error";
  const questionHintId = "ai-tutor-question-hint";
  const canSubmit = !submitting && question.trim().length > 0;

  function renderFailure(failure: ApiFailure) {
    switch (classifyTutorFailure(failure)) {
      case "unavailable":
        return (
          <Alert tone="muted" title={AI_UNAVAILABLE_NOTICE}>
            {isKeyMissingFailure(failure) ? (
              <p>{AI_UNAVAILABLE_HINT}</p>
            ) : (
              <p>
                后端返回 503（<span className="font-mono">{failure.code}</span>），本轮无法确认是否为未配置 key；
                请以后端日志为准。
              </p>
            )}
            <p>按契约此状态不发起任何上游请求，也不会消耗今日 token 额度。</p>
          </Alert>
        );
      case "timeout":
        return (
          <Alert
            tone="warning"
            title="AI_TIMEOUT · 上游超时"
            action={
              <Button variant="secondary" onClick={() => void submit()} disabled={submitting}>
                重试
              </Button>
            }
          >
            <p>DeepSeek 在 AI_TIMEOUT_SECONDS（默认 30 秒）内没有返回；问题文本仍在输入框里，可直接重试。</p>
            <p className="font-mono text-[10px]">
              {failure.code} / {failure.message}
            </p>
          </Alert>
        );
      case "quota": {
        const quota = readQuotaDetail(failure);
        return (
          <Alert tone="warning" title="AI_QUOTA_EXCEEDED · 今日 token 已超上限">
            <p>
              今日已用 {tokenText(quota.usedTokens)}；今日上限 {tokenText(quota.limitTokens)}
              （AI_DAILY_TOKEN_LIMIT，默认 50000）。
            </p>
            <p>按契约此状态不发起上游请求；额度按自然日重置，明天再试或调高该上限。</p>
          </Alert>
        );
      }
      case "validation":
        return (
          <Alert tone="warning" title="问题未通过参数校验（422）">
            <p>问题长度需在 1–2000 字之间，且只允许冻结契约里的四个提示依赖等级。</p>
            <p className="font-mono text-[10px]">
              {failure.code} / {failure.message}
            </p>
          </Alert>
        );
      case "not_ready":
        return (
          <Alert
            tone="muted"
            title="AI 导师接口尚未注册（404）"
            action={
              <Button variant="secondary" onClick={() => void submit()} disabled={submitting}>
                重试
              </Button>
            }
          >
            <p>
              本轮前端按冻结契约实现；<span className="font-mono">{AI_TUTOR_PATH}</span> 上线后本区块即可用。
            </p>
          </Alert>
        );
      default:
        return (
          <Alert
            tone="danger"
            title="AI 导师请求失败"
            action={
              <Button variant="secondary" onClick={() => void submit()} disabled={submitting}>
                重试
              </Button>
            }
          >
            <p>
              {failure.message}
              <span className="ml-2 font-mono">{failure.code}</span>
            </p>
            {failure.requestId ? (
              <p className="font-mono text-[10px]">request_id {failure.requestId}</p>
            ) : null}
          </Alert>
        );
    }
  }

  return (
    <Card>
      <CardHeader
        title="AI 导师"
        description="向 DeepSeek 提问当前课程或练习；回答只是参考，不写进度、不改能力等级。"
        action={<Tag tone="accent">{assistanceLevelLabel(level)}</Tag>}
      />
      <CardBody className="space-y-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <p className="min-w-0 max-w-xl text-[11px] leading-relaxed text-muted">
            默认折叠：展开不会自动提问，也不会发送任何内容。发送的只有你写的问句、提示依赖等级与
            {lessonId !== null ? "课程编号" : "练习编号"}
            ；
            {lessonId !== null
              ? "本页没有代码编辑器，也没有可发送的代码。"
              : "编辑器里的代码全文不会随请求发出。"}
          </p>
          <Button
            variant="secondary"
            aria-expanded={expanded}
            aria-controls={panelId}
            onClick={() => {
              const next = !expanded;
              setExpanded(next);
              if (next && history.status !== "ready") {
                setHistory({ status: "loading" });
              }
            }}
          >
            {expanded ? "收起 AI 导师" : "展开 AI 导师"}
          </Button>
        </div>

        <div id={panelId} hidden={!expanded} className="space-y-4">
          <fieldset className="space-y-2">
            <legend className="text-[12px] font-medium text-fg">提示依赖等级</legend>
            <p className="text-[11px] leading-relaxed text-muted">
              等级随请求发给后端并落库；等级越高，本次练习的提示依赖记录越弱。
            </p>
            <div className="grid gap-2 sm:grid-cols-2">
              {ASSISTANCE_LEVEL_OPTIONS.map((option) => (
                <ChoiceOption
                  key={option.value}
                  id={"ai-tutor-level-" + option.value}
                  name="ai-tutor-level"
                  value={option.value}
                  checked={level === option.value}
                  onChange={() => setLevel(option.value)}
                  label={
                    <span className="block">
                      <span className="block font-medium">{option.label}</span>
                      <span className="mt-0.5 block text-[11px] leading-relaxed text-muted">
                        {option.description}
                      </span>
                    </span>
                  }
                />
              ))}
            </div>
          </fieldset>

          <div className="space-y-1.5">
            <label htmlFor={questionId} className="block text-[12px] font-medium text-fg">
              你的问题（1–2000 字）
            </label>
            <p id={questionHintId} className="text-[11px] leading-relaxed text-muted">
              只写问题；不要粘贴完整代码或任何密钥。当前 {question.length} / {AI_QUESTION_MAX} 字。
            </p>
            <textarea
              id={questionId}
              rows={4}
              maxLength={AI_QUESTION_MAX}
              value={question}
              onChange={(event) => {
                setQuestion(event.target.value);
                if (validation !== null) {
                  setValidation(null);
                }
              }}
              aria-invalid={validation !== null ? true : undefined}
              aria-describedby={validation !== null ? questionErrorId : questionHintId}
              placeholder="例如：为什么我的循环在最后一项会被多算一次？"
              className={fieldClass(validation !== null) + " text-[13px] leading-5"}
            />
            {validation !== null ? (
              <p id={questionErrorId} role="alert" className="text-[11px] leading-relaxed text-danger-text">
                {validation}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="primary"
              onClick={() => void submit()}
              disabled={!canSubmit}
              aria-disabled={!canSubmit}
            >
              {submitting ? "正在询问 AI 导师…" : "向 AI 导师提问"}
            </Button>
            <span className="text-[11px] leading-relaxed text-muted">
              {submitting
                ? "等待后端返回，单次最长 30 秒；返回前按钮保持禁用，避免重复计费。"
                : question.trim().length === 0
                  ? "问题为空时不能提交：先写下你卡住的具体位置。"
                  : assistanceLevelRisk(level)}
            </span>
          </div>

          <div aria-live="polite" className="space-y-3">
            <div className="rounded-control border border-line bg-surface px-3 py-2.5">
              <p className="text-[11px] leading-relaxed text-fg">{AI_EVIDENCE_NOTICE}</p>

              {answer.status === "idle" ? (
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  还没有提问。提问后这里显示回答、assistance_level 与 usage.total_tokens。
                </p>
              ) : null}

              {answer.status === "pending" ? (
                <div aria-busy="true" className="mt-2 space-y-2">
                  <SkeletonLines rows={3} />
                </div>
              ) : null}

              {answer.status === "ok" ? (
                <div className="mt-2 space-y-2">
                  <p className="whitespace-pre-line text-[13px] leading-relaxed text-fg">
                    {answer.answer.answer}
                  </p>
                  <div className="space-y-1.5 border-t border-line pt-2">
                    <p className="text-[11px] font-medium text-fg">知识库引用</p>
                    {answer.answer.citations.length === 0 ? (
                      <p className="text-[11px] leading-relaxed text-muted">{KNOWLEDGE_NO_CITATION}</p>
                    ) : (
                      <ul className="space-y-2">
                        {answer.answer.citations.map((citation, index) => (
                          <li
                            key={(citation.url || citation.title) + "-" + String(index)}
                            className="text-[11px] leading-relaxed"
                          >
                            <div className="flex flex-wrap items-center gap-2">
                              {citation.url ? (
                                <a
                                  href={citation.url}
                                  target="_blank"
                                  rel="noreferrer noopener"
                                  className="font-medium text-fg underline-offset-4 hover:text-accent hover:underline"
                                >
                                  {citation.title}
                                </a>
                              ) : (
                                <span className="font-medium text-fg">{citation.title}</span>
                              )}
                              <Tag>{citation.url ? sourceDomain(citation.url) : "无链接"}</Tag>
                              {citation.stale ? <Tag tone="warning">{KNOWLEDGE_STALE_BADGE}</Tag> : null}
                            </div>
                            <p className="mt-0.5 font-mono text-[10px] text-muted">
                              抓取 {formatDateTime(citation.fetchedAt)}
                            </p>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                  <dl className="space-y-1 border-t border-line pt-2 text-[11px] text-muted">
                    <div className="flex items-center justify-between gap-3">
                      <dt>assistance_level</dt>
                      <dd className="text-right text-fg">
                        {assistanceLevelLabel(answer.answer.assistanceLevel)}
                        <span className="ml-1 font-mono">({answer.answer.assistanceLevel})</span>
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>usage.total_tokens</dt>
                      <dd className="font-mono text-fg">{String(answer.answer.usage.totalTokens)}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>prompt / completion</dt>
                      <dd className="font-mono text-fg">
                        {String(answer.answer.usage.promptTokens)} / {String(answer.answer.usage.completionTokens)}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>model</dt>
                      <dd className="font-mono text-fg">{answer.answer.model || "后端未返回"}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>latency_ms</dt>
                      <dd className="font-mono text-fg">
                        {answer.answer.latencyMs === null ? "后端未返回" : String(answer.answer.latencyMs)}
                      </dd>
                    </div>
                  </dl>
                </div>
              ) : null}

              {answer.status === "failed" ? (
                <p className="mt-2 text-[11px] leading-relaxed text-muted">
                  本次没有回答；失败的降级说明见下方，历史里会留下一条非 ok 记录。
                </p>
              ) : null}
            </div>

            {answer.status === "failed" ? renderFailure(answer.failure) : null}
          </div>

          <div className="space-y-2 border-t border-line pt-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-[12px] font-medium text-fg">最近交互</p>
              <Tag>{history.status === "ready" ? String(history.items.length) + " / 5 条" : "最多 5 条"}</Tag>
            </div>

            {history.status === "loading" ? (
              <div aria-busy="true">
                <SkeletonLines rows={2} />
              </div>
            ) : null}

            {history.status === "error" ? (
              <Alert
                tone="muted"
                title="最近交互读取失败"
                action={
                  <Button
                    variant="secondary"
                    onClick={() => {
                      setHistory({ status: "loading" });
                      setHistoryToken((value) => value + 1);
                    }}
                  >
                    重试
                  </Button>
                }
              >
                <p>
                  {history.failure.message}
                  <span className="ml-2 font-mono">{history.failure.code}</span>
                </p>
                <p>历史读取失败不影响提问；失败的调用同样会落库，重试后可见。</p>
              </Alert>
            ) : null}

            {history.status === "ready" && history.items.length === 0 ? (
              <p className="text-[11px] leading-relaxed text-muted">
                还没有交互记录。每次提问（含失败）都会落一行 ai_interactions。
              </p>
            ) : null}

            {history.status === "ready" && history.items.length > 0 ? (
              <ul className="divide-y divide-line">
                {history.items.map((item, index) => (
                  <li
                    key={(item.interactionId ?? "row") + "-" + String(index)}
                    className="flex flex-wrap items-center justify-between gap-2 py-2 text-[11px] first:pt-0 last:pb-0"
                  >
                    <span className="font-mono tabular-nums text-muted">
                      {formatDateTime(item.createdAt)}
                    </span>
                    <span className="text-muted">{assistanceLevelLabel(item.assistanceLevel)}</span>
                    <span className="font-mono tabular-nums text-muted">
                      {item.totalTokens === null ? "—" : String(item.totalTokens) + " tokens"}
                    </span>
                    <span
                      className={
                        aiStatusIsOk(item.status)
                          ? "font-medium text-fg"
                          : "text-muted"
                      }
                    >
                      {aiStatusLabel(item.status)}
                    </span>
                  </li>
                ))}
              </ul>
            ) : null}

            <p className="text-[11px] leading-relaxed text-muted">
              失败状态（超时 / 未配置 / 超额）用中性色标注，不当作学习证据，也不影响课程与练习的判定。
            </p>
          </div>
        </div>
      </CardBody>
    </Card>
  );
}
