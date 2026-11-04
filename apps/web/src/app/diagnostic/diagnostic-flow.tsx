"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Alert, ErrorPanel, LoadingPanel } from "@/components/states";
import { Button, ChoiceOption } from "@/components/form";
import { Card, CardBody, CardHeader, Meter, Tag } from "@/components/ui";
import { DiagnosticWizardProvider, useDiagnosticWizard } from "@/components/diagnostic/wizard";
import { DIAGNOSTIC_PAPER_PATH } from "@/lib/api";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseDiagnosticResult, parseSkills } from "@/lib/contract";
import type { DiagnosticResult, SkillRow } from "@/lib/contract";
import {
  ATTEMPT_TOKEN_STORAGE_KEY,
  DRAFT_STORAGE_KEY,
  clearAttemptToken,
  clearDraft,
  ensureAttemptToken,
} from "@/lib/diagnostic-draft";
import { writeLastResult } from "@/lib/diagnostic-result";
import { formatDateTime, domainName } from "@/lib/labels";
import { DOMAINS, KIND_LABELS, parseDiagnosticPaper } from "@/lib/questions";
import type { AnswerChoice, DiagnosticPaper } from "@/lib/questions";

function describeUnanswered(numbers: number[]): string {
  const head = numbers.slice(0, 6).map((value) => "第 " + String(value) + " 题");
  if (numbers.length > head.length) {
    return head.join("、") + " 等";
  }
  return head.join("、");
}

type SkillsState = {
  status: "checking" | "ready" | "unavailable";
  failure: ApiFailure | null;
};

type PaperState =
  | { status: "loading" }
  | { status: "ready"; paper: DiagnosticPaper }
  | { status: "failed"; failure: ApiFailure };

export function DiagnosticFlow() {
  const [paperState, setPaperState] = useState<PaperState>({ status: "loading" });
  const [paperToken, setPaperToken] = useState(0);

  const retryPaper = useCallback(() => {
    setPaperState({ status: "loading" });
    setPaperToken((value) => value + 1);
  }, []);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<DiagnosticPaper>(DIAGNOSTIC_PAPER_PATH, {
        parse: parseDiagnosticPaper,
      });
      if (!active) {
        return;
      }
      if (result.ok) {
        setPaperState({ status: "ready", paper: result.data });
        return;
      }
      setPaperState({ status: "failed", failure: result.failure });
    })();
    return () => {
      active = false;
    };
  }, [paperToken]);

  if (paperState.status === "loading") {
    return (
      <LoadingPanel
        title="正在从后端加载题面"
        description="题目与选项由后端题库提供，加载完成后才渲染答题界面。"
        rows={4}
      />
    );
  }

  if (paperState.status === "failed") {
    return (
      <ErrorPanel
        failure={paperState.failure}
        title="题面加载失败"
        onRetry={retryPaper}
        extra={
          <p>
            题面只从 GET /api/v1/diagnostics/paper 获取，页面不保留本地题库副本，因此没有可降级的题目。
            确认后端可用后点击重试。
          </p>
        }
      />
    );
  }

  return (
    <DiagnosticWizardProvider paper={paperState.paper}>
      <DiagnosticBody />
    </DiagnosticWizardProvider>
  );
}

function DiagnosticBody() {
  const router = useRouter();
  const wizard = useDiagnosticWizard();
  const paper = wizard.paper;
  const questions = paper.questions;
  const [skillsState, setSkillsState] = useState<SkillsState>({
    status: "checking",
    failure: null,
  });
  const [skillsToken, setSkillsToken] = useState(0);
  const [submitting, setSubmitting] = useState(false);
  const [submitFailure, setSubmitFailure] = useState<ApiFailure | null>(null);
  const [confirmReset, setConfirmReset] = useState(false);
  // 只在本次页面会话内记住已绑定的 token，用于展示；复用判定由 localStorage 记录决定。
  const [attemptToken, setAttemptToken] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<SkillRow[]>("/api/v1/skills", { parse: parseSkills });
      if (!active) {
        return;
      }
      if (result.ok) {
        setSkillsState({ status: "ready", failure: null });
        return;
      }
      setSkillsState({ status: "unavailable", failure: result.failure });
    })();
    return () => {
      active = false;
    };
  }, [skillsToken]);

  const submit = useCallback(async () => {
    if (submitting || !wizard.isComplete) {
      return;
    }
    setSubmitting(true);
    setSubmitFailure(null);
    const answers: Record<string, { choice: AnswerChoice }> = {};
    for (const question of paper.questions) {
      const choice = wizard.answers[question.id];
      if (choice) {
        answers[question.id] = { choice };
      }
    }
    // 首次提交生成并持久化；失败重试沿用同一个 token，后端据此返回原批次而不是追加新批次。
    // 题面/规则版本变化时 ensureAttemptToken 会自动换新 token，旧批次的幂等记录不会被误命中。
    const token = ensureAttemptToken(paper.questionSetVersion, paper.ruleVersion);
    setAttemptToken(token);
    const result = await apiRequest<DiagnosticResult>("/api/v1/diagnostics", {
      method: "POST",
      body: {
        attempt_token: token,
        question_set_version: paper.questionSetVersion,
        rule_version: paper.ruleVersion,
        answers,
      },
      parse: parseDiagnosticResult,
    });
    setSubmitting(false);
    if (!result.ok) {
      setSubmitFailure(result.failure);
      return;
    }
    writeLastResult({ ...result.data, questionSetVersion: paper.questionSetVersion });
    // 提交成功即结束这次诊断：草稿与 token 一起清除，下一次从新 token 开始。
    clearDraft();
    clearAttemptToken();
    setAttemptToken(null);
    router.push("/result");
  }, [submitting, wizard.isComplete, wizard.answers, paper, router]);

  if (!wizard.hydrated) {
    return (
      <LoadingPanel
        title="正在恢复本机草稿"
        description="题面已就绪，正在读取本机作答进度，读取完成后才渲染答题卡，避免水合不一致。"
        rows={3}
      />
    );
  }

  const question = wizard.current;
  const selected = wizard.answers[question.id] ?? null;
  const progressPercent =
    paper.total > 0 ? Math.round((wizard.answeredCount / paper.total) * 100) : 0;
  const savedLabel = wizard.savedAt ? formatDateTime(new Date(wizard.savedAt).toISOString()) : "—";

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        {skillsState.status === "unavailable" ? (
          <Alert
            tone="warning"
            title="服务未就绪：无法确认诊断接口"
            action={
              <Button
                variant="secondary"
                onClick={() => {
                  setSkillsState({ status: "checking", failure: null });
                  setSkillsToken((value) => value + 1);
                }}
              >
                重新检测
              </Button>
            }
          >
            <p>
              预检请求 GET /api/v1/skills 失败（{skillsState.failure ? skillsState.failure.code : "UNKNOWN"}）。
              你可以继续作答并保存草稿；提交时会重新请求 POST /api/v1/diagnostics。
            </p>
          </Alert>
        ) : null}

        {wizard.versionDiscarded ? (
          <Alert tone="warning" title="题面版本已变化，旧草稿已丢弃">
            <p>
              后端返回的 question_set_version 是{" "}
              <span className="font-mono">{paper.questionSetVersion || "（未提供）"}</span>
              ，与本机草稿记录的版本不一致，草稿键{" "}
              <span className="font-mono">{DRAFT_STORAGE_KEY}</span> 中的作答已丢弃，请重新作答。
            </p>
          </Alert>
        ) : null}

        {wizard.restored ? (
          <Alert tone="accent" title="已从本机草稿恢复作答">
            <p>
              草稿键名 <span className="font-mono">{DRAFT_STORAGE_KEY}</span>，已恢复{" "}
              {String(wizard.answeredCount)} 题答案。
            </p>
          </Alert>
        ) : null}

        <Card>
          <CardHeader
            title={"第 " + String(wizard.index + 1) + " / " + String(paper.total) + " 题"}
            description={"题集版本 " + paper.questionSetVersion + " · 规则版本 " + paper.ruleVersion}
            action={<Tag tone="accent">{KIND_LABELS[question.kind]}</Tag>}
          />
          <CardBody className="space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Tag>{domainName(question.domain)}</Tag>
              <Tag>题目编号 {question.id}</Tag>
              <Tag>{selected ? "本题已作答" : "本题未作答"}</Tag>
            </div>

            <p
              id="diagnostic-stem"
              className="whitespace-pre-wrap break-words text-[15px] leading-relaxed font-medium text-fg"
            >
              {question.prompt}
            </p>

            <div
              role="radiogroup"
              aria-labelledby="diagnostic-stem"
              aria-describedby="diagnostic-choice-hint"
              className="space-y-2"
            >
              {question.options.map((option) => (
                <ChoiceOption
                  key={option.key}
                  id={"option-" + question.id + "-" + option.key}
                  name={"question-" + question.id}
                  value={option.key}
                  checked={selected === option.key}
                  onChange={() => wizard.answer(question.id, option.key)}
                  label={
                    <span className="flex gap-2">
                      <span className="font-mono text-[12px] text-muted">{option.key}</span>
                      <span className="min-w-0 flex-1">{option.text}</span>
                    </span>
                  }
                />
              ))}
            </div>
            <p id="diagnostic-choice-hint" className="text-[11px] leading-relaxed text-muted">
              选择后立即写入本机草稿；题面来自后端题库，正误由后端按规则版本判定，页面不做本地判分。
            </p>

            <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
              <Button
                variant="secondary"
                onClick={wizard.previous}
                disabled={wizard.index === 0}
                aria-label="回到上一题"
              >
                上一题
              </Button>
              <Button
                variant="secondary"
                onClick={wizard.next}
                disabled={wizard.index === questions.length - 1}
                aria-label="进入下一题"
              >
                下一题
              </Button>
              {wizard.isComplete ? null : (
                <Button variant="quiet" onClick={wizard.goToFirstUnanswered}>
                  跳到第一个未作答题
                </Button>
              )}
              <span className="ml-auto text-[11px] text-muted">已答 {String(wizard.answeredCount)} / {String(paper.total)}</span>
            </div>
          </CardBody>
        </Card>

        {submitFailure ? (
          <ErrorPanel
            failure={submitFailure}
            title="诊断提交失败"
            onRetry={() => void submit()}
            extra={
              <>
                <p>
                  答案仍保存在本机草稿中，修复接口后可再次提交，不会丢失。重试复用同一个
                  attempt_token，服务端会命中幂等，不会把重试写成新批次。
                </p>
                {submitFailure.code === "IDEMPOTENCY_CONFLICT" ? (
                  <div className="mt-2 space-y-2">
                    <p>
                      该 token 已在服务端绑定另一批答案或另一个版本（HTTP 409）。要把当前答案作为新批次提交，
                      需要先解绑 token，下一次提交会生成新 token。
                    </p>
                    <Button
                      variant="secondary"
                      onClick={() => {
                        clearAttemptToken();
                        setAttemptToken(null);
                      }}
                    >
                      解绑令牌（下次提交生成新 token）
                    </Button>
                  </div>
                ) : null}
              </>
            }
          />
        ) : null}

        <div className="flex flex-wrap items-center gap-3">
          <Button
            variant="primary"
            onClick={() => void submit()}
            disabled={!wizard.isComplete || submitting}
          >
            {submitting ? "正在提交…" : "提交诊断"}
          </Button>
          {wizard.isComplete ? (
            <span className="text-[11px] text-muted">{String(paper.total)} 题已全部作答，可以提交。</span>
          ) : (
            <span className="text-[11px] leading-relaxed text-danger-text" role="status">
              还有 {String(wizard.unansweredNumbers.length)} 题未作答（
              {describeUnanswered(wizard.unansweredNumbers)}），答完 {String(paper.total)} 题后才能提交。
            </span>
          )}
        </div>
      </div>

      <aside className="space-y-6">
        <Card>
          <CardHeader title="作答进度" description="每答一题都会刷新本机草稿。" />
          <CardBody className="space-y-3">
            <div className="flex items-center justify-between text-[11px] text-muted">
              <span>已完成</span>
              <span className="font-mono text-fg">{progressPercent}%</span>
            </div>
            <Meter value={progressPercent} label="作答进度" />
            <dl className="space-y-1 pt-2 text-[11px]">
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">草稿位置</dt>
                <dd className="font-mono text-fg">localStorage</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">草稿键名</dt>
                <dd className="font-mono text-fg">{DRAFT_STORAGE_KEY}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">最近保存</dt>
                <dd className="font-mono text-fg">{savedLabel}</dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">提交令牌</dt>
                <dd className="font-mono text-fg">
                  {attemptToken === null ? "未生成" : attemptToken.slice(0, 8) + "…（重试复用）"}
                </dd>
              </div>
              <div className="flex items-center justify-between gap-3">
                <dt className="text-muted">令牌键名</dt>
                <dd className="font-mono text-fg">{ATTEMPT_TOKEN_STORAGE_KEY}</dd>
              </div>
            </dl>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="题目导航" description="已作答的题目使用强调色边框。" />
          <CardBody>
            <div className="grid grid-cols-5 gap-1.5">
              {questions.map((item, index) => {
                const answered = Boolean(wizard.answers[item.id]);
                const active = index === wizard.index;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => wizard.goto(index)}
                    aria-current={active ? "step" : undefined}
                    aria-label={"第 " + String(item.number) + " 题，" + (answered ? "已作答" : "未作答")}
                    className={
                      "rounded-control border px-0 py-1.5 font-mono text-[11px] transition-colors " +
                      (active
                        ? "border-accent bg-accent-soft text-accent"
                        : answered
                          ? "border-line-strong bg-surface text-fg hover:bg-elevated"
                          : "border-line bg-canvas text-muted hover:bg-elevated")
                    }
                  >
                    {item.number}
                  </button>
                );
              })}
            </div>
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="覆盖的技能域" description="题数按后端题面里的 domain_code 统计。" />
          <CardBody className="space-y-1.5">
            {DOMAINS.map((domain) => {
              const total = questions.filter((item) => item.domain === domain.code).length;
              const done = questions.filter(
                (item) => item.domain === domain.code && wizard.answers[item.id],
              ).length;
              return (
                <div key={domain.code} className="flex items-center justify-between gap-3 text-[11px]">
                  <span className="min-w-0 truncate text-muted">{domain.nameZh}</span>
                  <span className="shrink-0 font-mono text-fg">
                    {String(done)} / {String(total)}
                  </span>
                </div>
              );
            })}
          </CardBody>
        </Card>

        <div className="flex flex-wrap items-center gap-2">
          {confirmReset ? (
            <>
              <Button
                variant="danger"
                onClick={() => {
                  wizard.reset();
                  clearDraft();
                  clearAttemptToken();
                  setAttemptToken(null);
                  setConfirmReset(false);
                  setSubmitFailure(null);
                }}
              >
                确认清空草稿
              </Button>
              <Button variant="quiet" onClick={() => setConfirmReset(false)}>
                取消
              </Button>
            </>
          ) : (
            <Button variant="quiet" onClick={() => setConfirmReset(true)}>
              清空草稿并重新开始
            </Button>
          )}
        </div>
      </aside>
    </div>
  );
}
