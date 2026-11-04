"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button, fieldClass } from "@/components/form";
import { CodeTextarea } from "@/components/code-editor";
import { EvidenceBadge, evidenceKind } from "@/components/evidence-badge";
import { Alert, EmptyState, ErrorPanel, LoadingPanel, SkeletonLines } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { AiTutorPanel } from "@/components/ai-tutor-panel";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { formatMinutes } from "@/lib/learning";
import { formatDateTime } from "@/lib/labels";
import {
  EVIDENCE_DISCLAIMER,
  exercisePath,
  exerciseSubmissionsPath,
  parseExerciseDetail,
  parseSubmissionList,
  parseSubmissionResult,
  submissionStateLabel,
  verificationMethodLabel,
} from "@/lib/exercises";
import type {
  ExerciseDetail,
  ExerciseDetailPayload,
  SubmissionRecord,
  SubmissionResult,
} from "@/lib/exercises";

// 判定只做静态模式比对与自检申报，因此本页没有任何执行入口：
// 提交的代码只作为文本发给后端，前端不 eval、不 new Function、不发起任何运行请求。

type DetailState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; exercise: ExerciseDetail };

type HistoryState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; items: SubmissionRecord[]; fromDetail: boolean };

export function ExerciseView({ exerciseId }: { exerciseId: string }) {
  const [detail, setDetail] = useState<DetailState>({ status: "loading" });
  const [history, setHistory] = useState<HistoryState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);
  const [code, setCode] = useState("");
  const [claimedOutput, setClaimedOutput] = useState("");
  const [selfReportedPassed, setSelfReportedPassed] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<SubmissionResult | null>(null);
  const [submitFailure, setSubmitFailure] = useState<ApiFailure | null>(null);
  const initializedFor = useRef<string | null>(null);

  useEffect(() => {
    let active = true;
    void (async () => {
      // 题目与历史并发读取；历史接口失败不会挡住作答。
      const [detailResult, historyResult] = await Promise.all([
        apiRequest<ExerciseDetailPayload>(exercisePath(exerciseId), {
          parse: parseExerciseDetail,
        }),
        apiRequest<SubmissionRecord[]>(exerciseSubmissionsPath(exerciseId), {
          parse: parseSubmissionList,
        }),
      ]);
      if (!active) {
        return;
      }
      if (!detailResult.ok) {
        setDetail({ status: "error", failure: detailResult.failure });
      } else {
        const payload = detailResult.data;
        setDetail({ status: "ready", exercise: payload.exercise });
        // 起始代码只在首次拿到该题时预填：重试、刷新历史与提交后重读都不会覆盖已修改的代码。
        if (initializedFor.current !== exerciseId) {
          initializedFor.current = exerciseId;
          setCode(payload.exercise.starterCode);
        }
      }
      if (historyResult.ok) {
        setHistory({ status: "ready", items: historyResult.data, fromDetail: false });
      } else if (detailResult.ok && detailResult.data.history.length > 0) {
        // 历史接口未就绪时用详情响应自带的 history 兜底，并在卡片上注明来源。
        setHistory({ status: "ready", items: detailResult.data.history, fromDetail: true });
      } else {
        setHistory({ status: "error", failure: historyResult.failure });
      }
    })();
    return () => {
      active = false;
    };
  }, [exerciseId, reloadToken]);

  const reload = useCallback(() => {
    setDetail((current) => (current.status === "error" ? { status: "loading" } : current));
    setHistory({ status: "loading" });
    setReloadToken((value) => value + 1);
  }, []);

  const submit = useCallback(async () => {
    if (submitting || code.trim().length === 0) {
      return;
    }
    setSubmitting(true);
    setSubmitFailure(null);
    const body: {
      code_text: string;
      claimed_output?: string;
      self_reported_passed?: boolean;
    } = { code_text: code };
    if (claimedOutput.trim().length > 0) {
      body.claimed_output = claimedOutput;
    }
    // 后端按「字段是否存在」分流：self_reported_passed is None -> static_rule；字段存在（true 或 false）->
    // self_check。因此未勾选时必须完全不发送该字段，发 false 也会把判题切到自检，静态规则将永不执行。
    if (selfReportedPassed) {
      body.self_reported_passed = true;
    }
    const response = await apiRequest<SubmissionResult>(exerciseSubmissionsPath(exerciseId), {
      method: "POST",
      body,
      parse: parseSubmissionResult,
    });
    setSubmitting(false);
    if (!response.ok) {
      setSubmitFailure(response.failure);
    } else {
      setResult(response.data);
    }
    // 无论成败都重读历史：提交可能已落库（例如响应被判为不符合契约），界面以服务端记录为准。
    setReloadToken((value) => value + 1);
  }, [claimedOutput, code, exerciseId, selfReportedPassed, submitting]);

  if (detail.status === "loading") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">练习详情</h1>
        <LoadingPanel
          title="正在读取题目"
          description="GET /api/v1/exercises/{id}；判题不执行代码，本页也不会运行任何提交内容。"
          rows={5}
        />
      </div>
    );
  }

  if (detail.status === "error") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">练习详情</h1>
        <ErrorPanel
          failure={detail.failure}
          title="题目加载失败"
          onRetry={reload}
          extra={<p>拿不到题目内容时不显示编辑器与用例，避免给出无法判定的占位题。</p>}
        />
        <Link
          href="/practice"
          className="inline-block rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          返回练习列表
        </Link>
      </div>
    );
  }

  const exercise = detail.exercise;
  const canSubmit = !submitting && code.trim().length > 0;
  const disabledReason = submitting
    ? "正在提交，请稍候；请求返回前按钮保持禁用，避免重复提交。"
    : code.trim().length === 0
      ? "代码为空时不能提交：先在上面的编辑器里写入你的实现。"
      : "提交后由后端按静态规则比对代码文本；勾选自检时改按你的申报记录（未验证）。系统不会运行代码。";

  return (
    <div className="space-y-6">
      <header className="border-b border-line pb-6">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/practice"
            className="rounded-control text-[12px] font-medium text-muted hover:text-fg"
          >
            练习
          </Link>
          <span aria-hidden="true" className="text-[12px] text-muted">/</span>
          {exercise.difficulty ? <Tag>{exercise.difficulty}</Tag> : null}
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">{exercise.title}</h1>
        <p className="mt-2 flex flex-wrap gap-x-4 font-mono text-[11px] tabular-nums text-muted">
          <span>预计 {formatMinutes(exercise.estimatedMinutes)}</span>
          <span>可见用例 {exercise.visibleTests.length} 条</span>
          {exercise.id ? <span>题目编号 {exercise.id}</span> : null}
        </p>
      </header>

      {exercise.review !== null && exercise.review.status === "pending" ? (
        <Alert
          tone={exercise.review.due ? "warning" : "accent"}
          title={exercise.review.due ? "这是一道到期复习题" : "这道题在错题本里"}
        >
          <p>
            {exercise.review.due
              ? "今天就是它的复习日。"
              : "还没到复习日，随时可以提前重做。"}
            连续答对 {String(exercise.review.streak)} 次；
            {exercise.review.due
              ? "再答对一次即推进到下一间隔。"
              : "下次复习 " + exercise.review.nextReviewOn + "。"}
            {exercise.review.intervalDays > 0
              ? "当前间隔 " + String(exercise.review.intervalDays) + " 天。"
              : null}
          </p>
          <p className="mt-1 text-muted">
            错题连续通过 3 次后转为完成，不再占用周计划额度。
            <Link href="/review" className="ml-1 underline hover:text-fg">
              查看全部错题
            </Link>
          </p>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader
              title="题目与目标"
              description="题面来自后端内容，本页不改写题干、不提供参考答案。"
            />
            <CardBody className="space-y-3">
              {exercise.prompt ? (
                <p className="whitespace-pre-line text-[13px] leading-relaxed text-fg">
                  {exercise.prompt}
                </p>
              ) : (
                <Alert tone="warning" title="后端未返回题目说明">
                  <p>prompt 为空；本页不填充占位题干，请等待题目内容发布。</p>
                </Alert>
              )}
              <p className="text-[11px] leading-relaxed text-muted">
                下方编辑器已预填该题的起始代码，可以直接修改；起始代码只是骨架，不含答案。
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="代码编辑器"
              description="等宽字体 + 行号侧栏；Tab 插入两个空格缩进。编辑器只收集文本，前端不会执行它。"
            />
            <CardBody className="space-y-2">
              <label htmlFor="exercise-code" className="block text-[12px] font-medium text-fg">
                你的代码
              </label>
              <CodeTextarea
                id="exercise-code"
                value={code}
                onChange={setCode}
                describedBy="exercise-code-hint"
                rows={16}
              />
              <p id="exercise-code-hint" className="text-[11px] leading-relaxed text-muted">
                行号随滚动同步，Tab 键插入缩进而不是跳走。当前字符数 {code.length}。
                系统不会运行这段代码，运行期错误与超时不会在这里暴露——请在本地自行验证。
              </p>
            </CardBody>
          </Card>

          <Card>
            <CardHeader
              title="可见自检用例"
              description="输入与期望输出来自题目内容，用于本地自检；系统不代为运行。"
            />
            <CardBody className="space-y-3">
              {exercise.visibleTests.length === 0 ? (
                <Alert tone="warning" title="后端未返回可见用例">
                  <p>visible_tests 为空；本页不编造用例。</p>
                </Alert>
              ) : (
                <ul className="divide-y divide-line">
                  {exercise.visibleTests.map((test, index) => (
                    <li
                      key={index}
                      className="grid gap-2 py-3 first:pt-0 last:pb-0 sm:grid-cols-2"
                    >
                      <div className="min-w-0">
                        <p className="text-[11px] text-muted">用例 {index + 1} · 输入</p>
                        <pre
                          tabIndex={0}
                          aria-label={"用例 " + String(index + 1) + " 输入"}
                          className="mt-1 overflow-x-auto rounded-control border border-line bg-surface px-2.5 py-2"
                        >
                          <code className="font-mono text-[13px] leading-5 whitespace-pre text-fg">
                            {test.input === "" ? "（空）" : test.input}
                          </code>
                        </pre>
                      </div>
                      <div className="min-w-0">
                        <p className="text-[11px] text-muted">期望输出</p>
                        <pre
                          tabIndex={0}
                          aria-label={"用例 " + String(index + 1) + " 期望输出"}
                          className="mt-1 overflow-x-auto rounded-control border border-line bg-surface px-2.5 py-2"
                        >
                          <code className="font-mono text-[13px] leading-5 whitespace-pre text-fg">
                            {test.expected === "" ? "（空）" : test.expected}
                          </code>
                        </pre>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </CardBody>
          </Card>
        </div>

        <aside className="space-y-6">
          <Card>
            <CardHeader title="提交与自检" action={<Tag>{selfReportedPassed ? "含自检申报" : "仅静态规则"}</Tag>} />
            <CardBody className="space-y-4">
              <div className="space-y-1.5">
                <label
                  htmlFor="claimed-output"
                  className="block text-[12px] font-medium text-fg"
                >
                  我已在本地运行，输出为…（可选）
                </label>
                <p id="claimed-output-hint" className="text-[11px] leading-relaxed text-muted">
                  原样粘贴本地输出；后端只做字符串比对，不会执行代码。
                </p>
                <textarea
                  id="claimed-output"
                  rows={4}
                  value={claimedOutput}
                  aria-describedby="claimed-output-hint"
                  onChange={(event) => setClaimedOutput(event.target.value)}
                  className={fieldClass(false) + " font-mono text-[13px] leading-5"}
                />
              </div>

              <label
                htmlFor="self-reported-passed"
                className="flex cursor-pointer items-start gap-2.5 rounded-control border border-line bg-surface px-3 py-2.5 text-[12px] text-fg"
              >
                <input
                  id="self-reported-passed"
                  type="checkbox"
                  checked={selfReportedPassed}
                  onChange={(event) => setSelfReportedPassed(event.target.checked)}
                  className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]"
                />
                <span className="min-w-0 flex-1 leading-relaxed">
                  我已在本地运行并通过（<span className="font-mono">self_reported_passed</span>）
                </span>
              </label>

              <p className="text-[11px] leading-relaxed text-muted">
                勾选后本次提交按自检记录：这类结果永远是「未验证（自检）」，不会变成已验证，也不会改变能力等级；
                不勾选则只做静态规则判题（不发送自检字段）。
              </p>

              {submitFailure ? (
                <Alert tone="danger" title="提交失败">
                  <p>
                    {submitFailure.message}
                    <span className="ml-2 font-mono text-[11px]">{submitFailure.code}</span>
                  </p>
                  <p>提交结果未知时不要假设已通过；下方历史会在重试后按服务端记录刷新。</p>
                </Alert>
              ) : null}

              <div className="flex flex-wrap items-center gap-2">
                <Button
                  variant="primary"
                  onClick={() => void submit()}
                  disabled={!canSubmit}
                  aria-disabled={!canSubmit}
                >
                  {submitting ? "正在提交…" : "提交判定"}
                </Button>
              </div>
              <p className="text-[11px] leading-relaxed text-muted">{disabledReason}</p>
            </CardBody>
          </Card>

          <div aria-live="polite">
            {result ? (
              <Card>
                <CardHeader
                  title="判定结果"
                  description="判定方式与证据强度来自后端响应；本页不写等级、不表示能力提升。"
                  action={<EvidenceBadge kind={evidenceKind(result.verificationStrength, true)} />}
                />
                <CardBody className="space-y-3">
                  <p
                    className={
                      result.isPassed === true
                        ? "text-[13px] font-medium text-success-text"
                        : result.isPassed === false
                          ? "text-[13px] font-medium text-danger-text"
                          : "text-[13px] font-medium text-fg"
                    }
                  >
                    {submissionStateLabel(result.isPassed)}
                  </p>
                  <dl className="space-y-1 border-t border-line pt-2 text-[11px] text-muted">
                    <div className="flex items-center justify-between gap-3">
                      <dt>判定方式</dt>
                      <dd className="text-right text-fg">
                        {verificationMethodLabel(result.verificationMethod)}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>verification_method</dt>
                      <dd className="font-mono text-fg">{result.verificationMethod || "—"}</dd>
                    </div>
                    <div className="flex items-center justify-between gap-3">
                      <dt>verification_strength</dt>
                      <dd className="font-mono text-fg">{result.verificationStrength}</dd>
                    </div>
                    {result.judgingMode ? (
                      <div className="flex items-center justify-between gap-3">
                        <dt>judging_mode</dt>
                        <dd className="font-mono text-fg">{result.judgingMode}</dd>
                      </div>
                    ) : null}
                    {result.submissionId ? (
                      <div className="flex items-center justify-between gap-3">
                        <dt>提交编号</dt>
                        <dd className="font-mono text-fg">{result.submissionId}</dd>
                      </div>
                    ) : null}
                  </dl>

                  <div>
                    <p className="text-[11px] font-medium text-fg">检查项</p>
                    {result.checks.length === 0 ? (
                      <p className="mt-1 text-[11px] leading-relaxed text-muted">
                        后端返回的 checks 为空，本次没有可展示的检查项。
                      </p>
                    ) : (
                      <ul className="mt-1.5 space-y-1.5">
                        {result.checks.map((check, index) => (
                          <li
                            key={index}
                            className="rounded-control border border-line bg-surface px-2.5 py-2"
                          >
                            <div className="flex items-center justify-between gap-2">
                              <span className="min-w-0 font-mono text-[12px] text-fg">
                                {check.name}
                              </span>
                              <span
                                className={
                                  check.passed
                                    ? "shrink-0 text-[11px] font-medium text-success-text"
                                    : "shrink-0 text-[11px] font-medium text-danger-text"
                                }
                              >
                                {check.passed ? "通过" : "未通过"}
                              </span>
                            </div>
                            {check.detail ? (
                              <p className="mt-1 text-[11px] leading-relaxed text-muted">
                                {check.detail}
                              </p>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>

                  <p className="rounded-control border border-line bg-elevated px-3 py-2 text-[11px] leading-relaxed text-fg">
                    {EVIDENCE_DISCLAIMER}
                  </p>
                </CardBody>
              </Card>
            ) : (
              <Card>
                <CardHeader title="判定结果" />
                <CardBody>
                  <p className="text-[11px] leading-relaxed text-muted">
                    还没有提交。提交后这里显示通过情况、判定方式与证据标签。
                  </p>
                </CardBody>
              </Card>
            )}
          </div>

          <Card>
            <CardHeader title="判定说明" />
            <CardBody className="space-y-2 text-[11px] leading-relaxed text-muted">
              <p>静态规则：按必须出现 / 禁止出现的模式比对代码文本，可再比对申报的输出文本。</p>
              <p>自检：你在本地运行后自行申报，系统原样记录，不做复核。</p>
              <p>系统不执行任何提交的代码，因此「静态规则通过」不等于「代码能运行」。</p>
            </CardBody>
          </Card>
        </aside>
      </div>

      {/* AI 导师：可选区块，默认折叠；展开前不发任何请求。
          请求体只有问句 + 提示依赖等级 + 练习编号，编辑器里的代码不会随请求发出。 */}
      <AiTutorPanel exerciseId={exerciseId} />

      <Card>
        <CardHeader
          title="提交历史"
          description="倒序排列：最近一次提交在最前。判定方式与结果都来自后端响应。"
          action={
            history.status === "ready" ? <Tag>{history.items.length + " 次"}</Tag> : null
          }
        />
        <CardBody className="space-y-3">
          {history.status === "loading" ? (
            <div aria-busy="true" className="space-y-2">
              <SkeletonLines rows={2} />
            </div>
          ) : null}

          {history.status === "error" ? (
            <Alert
              tone="warning"
              title="提交历史读取失败"
              action={
                <Button variant="secondary" onClick={reload}>
                  重试
                </Button>
              }
            >
              <p>
                {history.failure.message}
                <span className="ml-2 font-mono text-[11px]">{history.failure.code}</span>
              </p>
              <p>历史读取失败不影响作答与提交；提交成功后这里会按服务端记录刷新。</p>
            </Alert>
          ) : null}

          {history.status === "ready" && history.items.length === 0 ? (
            <EmptyState
              title="还没有提交记录"
              description="提交一次判定后，这里会按时间倒序列出每一次的结果与判定方式。"
            />
          ) : null}

          {history.status === "ready" && history.items.length > 0 ? (
            <ul className="divide-y divide-line">
              {history.items.map((item, index) => (
                <li
                  key={item.submissionId || String(index)}
                  className="flex flex-wrap items-center justify-between gap-2 py-2.5 text-[11px] first:pt-0 last:pb-0"
                >
                  <span className="font-mono tabular-nums text-muted">
                    {formatDateTime(item.submittedAt)}
                  </span>
                  <span className="min-w-0 text-muted">
                    {verificationMethodLabel(item.verificationMethod)}
                  </span>
                  <span
                    className={
                      item.isPassed === true
                        ? "font-medium text-success-text"
                        : item.isPassed === false
                          ? "font-medium text-danger-text"
                          : "text-muted"
                    }
                  >
                    {submissionStateLabel(item.isPassed)}
                  </span>
                  <EvidenceBadge kind={evidenceKind(item.verificationStrength, true)} />
                </li>
              ))}
            </ul>
          ) : null}

          {history.status === "ready" && history.fromDetail ? (
            <p className="text-[11px] leading-relaxed text-muted">
              提交历史接口未就绪，当前列表来自练习详情响应里的 history 字段，可能不完整。
            </p>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
