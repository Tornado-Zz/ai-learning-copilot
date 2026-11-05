"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button, ChoiceOption } from "@/components/form";
import { Alert, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { LessonExercises } from "@/components/lesson-exercises";
import { AiTutorPanel } from "@/components/ai-tutor-panel";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import {
  LESSON_STATUS_LABELS,
  SELF_ASSESSMENT_OPTIONS,
  formatMinutes,
  lessonPath,
  lessonProgressPath,
  parseAck,
  parseLessonDetail,
} from "@/lib/learning";
import { LESSONS_PATH, parseLessons } from "@/lib/learning";
import type { LessonDetail, LessonSummary } from "@/lib/learning";

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; lesson: LessonDetail };

type Busy = null | "start" | "complete";

export function LessonDetailView({ lessonId }: { lessonId: string }) {
  // 上一课 / 下一课：线性课程最常见的动作是「读完这节接着读下一节」，
  // 但页面原本只有「返回课程列表」，等于每次都多一次跳转。
  const [navigation, setNavigation] = useState<{
    prev: LessonSummary | null;
    next: LessonSummary | null;
  } | null>(null);
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);
  const [revealed, setRevealed] = useState<Record<number, boolean>>({});
  const [assessment, setAssessment] = useState<0 | 1 | 2 | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [actionFailure, setActionFailure] = useState<ApiFailure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // 只读拉取：打开页面不发任何写请求，进度写入完全由下面的按钮触发。
  useEffect(() => {
    let active = true;
    void (async () => {
      const [result, listResult] = await Promise.all([
        apiRequest<LessonDetail>(lessonPath(lessonId), { parse: parseLessonDetail }),
        apiRequest<LessonSummary[]>(LESSONS_PATH, { parse: parseLessons }),
      ]);
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", lesson: result.data });
      // 导航只是锦上添花：列表拿不到就不显示，绝不影响课程正文。
      if (listResult.ok && listResult.data.length > 0) {
        const index = listResult.data.findIndex((item) => item.id === result.data.id);
        setNavigation(
          index < 0
            ? null
            : {
                prev: index > 0 ? listResult.data[index - 1] : null,
                next: index < listResult.data.length - 1 ? listResult.data[index + 1] : null,
              },
        );
      } else {
        setNavigation(null);
      }
    })();
    return () => {
      active = false;
    };
  }, [lessonId, reloadToken]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setActionFailure(null);
    setReloadToken((value) => value + 1);
  }, []);

  const writeProgress = useCallback(
    async (next: "in_progress" | "completed") => {
      // P1-05：非法操作不发出请求。S4 只允许前进，in_progress 只能从 not_started 出发；
      // 已完成课程没有回退路径，重复提交 completed 是幂等的（200），允许（只更新自评）。
      if (
        next === "in_progress" &&
        state.status === "ready" &&
        state.lesson.progress.status !== "not_started"
      ) {
        return;
      }
      setBusy(next === "completed" ? "complete" : "start");
      setActionFailure(null);
      setNotice(null);
      const body: { status: "in_progress" | "completed"; self_assessment?: 0 | 1 | 2 } = {
        status: next,
      };
      if (next === "completed" && assessment !== null) {
        body.self_assessment = assessment;
      }
      const result = await apiRequest<true>(lessonProgressPath(lessonId), {
        method: "PUT",
        body,
        parse: parseAck,
      });
      setBusy(null);
      if (!result.ok) {
        setActionFailure(result.failure);
        return;
      }
      setNotice(next === "completed" ? "已标记完成。" : "已标记为学习中。");
      setReloadToken((value) => value + 1);
    },
    [assessment, lessonId, state],
  );

  if (state.status === "loading") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">课程详情</h1>
        <LoadingPanel
          title="正在读取课程内容"
          description="GET /api/v1/lessons/{id}；打开页面不会写入任何进度。"
          rows={5}
        />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-semibold tracking-tight text-fg">课程详情</h1>
        <ErrorPanel
          failure={state.failure}
          title="课程内容加载失败"
          onRetry={retry}
          extra={<p>接口未就绪时不显示任何占位正文，也不会写入任何进度。</p>}
        />
        <Link
          href="/learn"
          className="inline-block rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          返回课程列表
        </Link>
      </div>
    );
  }

  const lesson = state.lesson;
  // 课程完成状态只认 learning_progress（S3/S4 的可信来源）；本页不用计划项状态推断课程完成。
  const progressStatus = lesson.progress.status;
  const completed = progressStatus === "completed";
  const storedSelfAssessment =
    lesson.progress.selfAssessment === null ? null : lesson.progress.selfAssessment;
  const emptyContent =
    lesson.objectives.length === 0 &&
    lesson.sections.length === 0 &&
    lesson.examples.length === 0 &&
    lesson.commonErrors.length === 0 &&
    lesson.selfCheck.length === 0;

  return (
    <div className="space-y-6">
      <header className="border-b border-line pb-6">
        <div className="flex flex-wrap items-center gap-2">
          <Link
            href="/learn"
            className="rounded-control text-[12px] font-medium text-muted hover:text-fg"
          >
            学习路线
          </Link>
          <span aria-hidden="true" className="text-[12px] text-muted">/</span>
          {lesson.stage ? <Tag>阶段 {lesson.stage}</Tag> : null}
          <Tag tone={completed ? "accent" : "neutral"}>
            {LESSON_STATUS_LABELS[lesson.progress.status]}
          </Tag>
        </div>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">{lesson.title}</h1>
        <p className="mt-2 flex flex-wrap gap-x-4 font-mono text-[11px] tabular-nums text-muted">
          <span>预计 {formatMinutes(lesson.estimatedMinutes)}</span>
          {lesson.code ? <span>{lesson.code}</span> : null}
          {lesson.contentVersion ? <span>内容版本 {lesson.contentVersion}</span> : null}
          <span>完成率 {String(lesson.progress.progressPct)}%</span>
        </p>
      </header>

      {emptyContent ? (
        <Alert tone="warning" title="该课程暂无正文内容">
          <p>后端返回的 content 字段为空；本页不填充任何占位正文，请等待内容发布。</p>
        </Alert>
      ) : null}

      {lesson.objectives.length > 0 ? (
        <Card>
          <CardHeader title="学习目标" description="完成后应能独立做到的事，逐条来自课程内容。" />
          <CardBody>
            <ul className="space-y-1.5">
              {lesson.objectives.map((objective, index) => (
                <li key={index} className="flex items-start gap-2 text-[13px] leading-relaxed text-fg">
                  <span className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-[3px] border border-line bg-surface font-mono text-[10px] text-muted">
                    {String(index + 1)}
                  </span>
                  <span className="min-w-0">{objective}</span>
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {lesson.sections.length > 0 ? (
        <Card>
          <CardHeader title="讲解" />
          <CardBody className="space-y-5">
            {lesson.sections.map((section, index) => (
              <section key={index} className="space-y-1.5">
                {section.heading ? (
                  <h3 className="text-[13px] font-semibold tracking-tight text-fg">{section.heading}</h3>
                ) : null}
                {section.body ? (
                  <p className="whitespace-pre-line text-[13px] leading-relaxed text-muted">
                    {section.body}
                  </p>
                ) : null}
              </section>
            ))}
          </CardBody>
        </Card>
      ) : null}

      {lesson.examples.length > 0 ? (
        <Card>
          <CardHeader title="代码示例" description="代码块使用等宽字体，超宽时在块内横向滚动。" />
          <CardBody className="space-y-4">
            {lesson.examples.map((example, index) => (
              <figure key={index} className="space-y-1.5">
                {example.title ? (
                  <figcaption className="text-[12px] font-medium text-fg">{example.title}</figcaption>
                ) : null}
                {example.code ? (
                  <pre
                    tabIndex={0}
                    aria-label={"代码示例：" + (example.title || String(index + 1))}
                    className="overflow-x-auto rounded-control border border-line bg-surface px-3 py-2.5"
                  >
                    <code className="font-mono text-[13px] leading-5 whitespace-pre text-fg">
                      {example.code}
                    </code>
                  </pre>
                ) : null}
                {example.note ? (
                  <p className="text-[11px] leading-relaxed text-muted">{example.note}</p>
                ) : null}
              </figure>
            ))}
          </CardBody>
        </Card>
      ) : null}

      {lesson.commonErrors.length > 0 ? (
        <Card>
          <CardHeader title="典型错误" description="错误写法、原因与改法；不是必答项，先看懂再动手。" />
          <CardBody>
            <ul className="divide-y divide-line">
              {lesson.commonErrors.map((error, index) => (
                <li key={index} className="space-y-1.5 py-3 first:pt-0 last:pb-0">
                  {error.wrong ? (
                    <pre className="overflow-x-auto rounded-control border border-line bg-surface px-3 py-2">
                      <code className="font-mono text-[13px] leading-5 whitespace-pre text-danger-text">
                        {error.wrong}
                      </code>
                    </pre>
                  ) : null}
                  {error.why ? (
                    <p className="text-[12px] leading-relaxed text-muted">为什么错：{error.why}</p>
                  ) : null}
                  {error.fix ? (
                    <p className="text-[12px] leading-relaxed text-fg">怎么改：{error.fix}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      {lesson.selfCheck.length > 0 ? (
        <Card>
          <CardHeader
            title="自测问题"
            description="答案默认折叠，先自己想一遍，再点「显示参考答案」核对。"
          />
          <CardBody>
            <ul className="space-y-3">
              {lesson.selfCheck.map((check, index) => {
                const open = revealed[index] === true;
                const panelId = "self-check-answer-" + String(index);
                return (
                  <li key={index} className="rounded-control border border-line px-3 py-2.5">
                    <p className="text-[13px] leading-relaxed text-fg">
                      {String(index + 1)}. {check.question}
                    </p>
                    <button
                      type="button"
                      aria-expanded={open}
                      aria-controls={panelId}
                      onClick={() =>
                        setRevealed((value) => ({ ...value, [index]: !open }))
                      }
                      className="mt-1.5 text-[11px] font-medium text-accent hover:underline"
                    >
                      {open ? "收起参考答案" : "显示参考答案"}
                    </button>
                    <div id={panelId} hidden={!open} className="mt-1.5">
                      <p className="rounded-control border border-line bg-surface px-2.5 py-2 text-[12px] leading-relaxed text-muted">
                        {check.answerHint ? check.answerHint : "后端未返回 answer_hint。"}
                      </p>
                    </div>
                  </li>
                );
              })}
            </ul>
          </CardBody>
        </Card>
      ) : null}

      <LessonExercises lessonId={lessonId} />

      {/* AI 导师：可选区块，默认折叠；展开前不发任何请求。只发送问句 + 等级 + 课程编号。 */}
      <AiTutorPanel lessonId={lessonId} />

      <Card>
        <CardHeader
          title="进度与自评"
          description="进度只在你点击下面的按钮时写入；打开本页不会自动标记完成。"
          action={<Tag tone={completed ? "accent" : "neutral"}>{LESSON_STATUS_LABELS[lesson.progress.status]}</Tag>}
        />
        <CardBody className="space-y-4">
          {notice ? (
            <Alert tone="accent" title={notice}>
              <p>进度已按接口返回结果重新读取，未做任何本地猜测。</p>
            </Alert>
          ) : null}

          {actionFailure ? (
            <Alert tone="danger" title="进度写入失败">
              <p>
                {actionFailure.message}
                <span className="ml-2 font-mono text-[11px]">{actionFailure.code}</span>
              </p>
              <p>
                写入没有生效，页面仍显示接口返回的真实状态；后端接口未就绪时（404）请稍后重试。
              </p>
            </Alert>
          ) : null}

          <fieldset className="space-y-2">
            <legend className="text-[12px] font-medium text-fg">
              完成时可选自评（L0–L2，不选也可以）
            </legend>
            <div className="grid gap-2 sm:grid-cols-2">
              {SELF_ASSESSMENT_OPTIONS.map((option) => (
                <ChoiceOption
                  key={option.value}
                  id={"self-assessment-" + String(option.value)}
                  name="lesson-self-assessment"
                  value={String(option.value)}
                  checked={assessment === option.value}
                  onChange={() => setAssessment(option.value)}
                  label={option.label}
                />
              ))}
              <ChoiceOption
                id="self-assessment-none"
                name="lesson-self-assessment"
                value="none"
                checked={assessment === null}
                onChange={() => setAssessment(null)}
                label="不选（稍后再评）"
              />
            </div>
            <p className="text-[11px] leading-relaxed text-muted">
              课程自评不等于能力等级：它只写入 learning_progress 的自评字段，不会改变六个技能域的等级，
              也不会成为 L3/L4 的证据。本页不提供 L3/L4 选项。
            </p>
          </fieldset>

          <p className="text-[11px] leading-relaxed text-muted">
            上面的「{LESSON_STATUS_LABELS[progressStatus]}」来自 learning_progress，是课程的真实完成状态；
            计划项被标成 done 不等于课程完成，也不等于能力等级（六域等级只来自诊断与核验）。
            {storedSelfAssessment === null
              ? ""
              : " 已记录自评：L" + String(storedSelfAssessment) + "（来自 learning_progress）。"}
          </p>

          <div className="flex flex-wrap items-center gap-2">
            {progressStatus === "not_started" ? (
              <Button
                variant="secondary"
                onClick={() => void writeProgress("in_progress")}
                disabled={busy !== null}
                aria-disabled={busy !== null}
              >
                {busy === "start" ? "正在保存…" : "开始学习"}
              </Button>
            ) : null}
            <Button
              variant="primary"
              onClick={() => void writeProgress("completed")}
              disabled={busy !== null}
              aria-disabled={busy !== null}
            >
              {busy === "complete" ? "正在保存…" : completed ? "更新完成记录" : "标记完成"}
            </Button>
            <span className="text-[11px] leading-relaxed text-muted">
              {progressStatus === "not_started"
                ? "还没开始：点「开始学习」记录开始时间，或直接点「标记完成」。"
                : progressStatus === "in_progress"
                  ? "学习中：读完后点「标记完成」；进度只前进，不会回退。"
                  : "已完成：重复提交只会更新自评（幂等 200），不会退回未开始或学习中，因此不再展示「开始学习」。"}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            {navigation?.prev ? (
              <Link
                href={"/learn/" + String(navigation.prev.id)}
                className="rounded-control text-[12px] font-medium text-muted hover:text-fg"
              >
                ← 上一课：{navigation.prev.title}
              </Link>
            ) : null}
            {navigation?.next ? (
              <Link
                href={"/learn/" + String(navigation.next.id)}
                className="rounded-control text-[12px] font-medium text-accent hover:underline"
              >
                下一课：{navigation.next.title} →
              </Link>
            ) : null}
            <Link
              href="/learn"
              className="rounded-control text-[12px] font-medium text-muted hover:text-fg"
            >
              返回课程列表
            </Link>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
