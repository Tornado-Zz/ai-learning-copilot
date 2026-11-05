"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { EvidenceLegend, EvidenceBadge, evidenceKind } from "@/components/evidence-badge";
import { Alert, EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag, cx } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { LESSONS_PATH, formatMinutes, parseLessons } from "@/lib/learning";
import type { LessonSummary } from "@/lib/learning";
import {
  EVIDENCE_DISCLAIMER,
  EXERCISES_PATH,
  parseExerciseList,
  practicePagePath,
  submissionStateLabel,
} from "@/lib/exercises";
import type { ExerciseSummary } from "@/lib/exercises";
import { formatDateTime } from "@/lib/labels";

type ExerciseGroup = {
  lessonId: string;
  lessonTitle: string;
  stage: string;
  exercises: ExerciseSummary[];
};

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; groups: ExerciseGroup[]; total: number; lessonsFailure: ApiFailure | null };

// 分组顺序优先跟随课程列表顺序；课程列表不可用（后端未就绪）时用练习响应里的 lesson_id 兜底，
// 绝不因为拿不到课程标题就不显示练习。
function groupExercises(exercises: ExerciseSummary[], lessons: LessonSummary[]): ExerciseGroup[] {
  const buckets = new Map<string, ExerciseSummary[]>();
  for (const exercise of exercises) {
    const key = exercise.lessonId === "" ? "unknown" : exercise.lessonId;
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.push(exercise);
    } else {
      buckets.set(key, [exercise]);
    }
  }
  const groups: ExerciseGroup[] = [];
  const used: string[] = [];
  for (const lesson of lessons) {
    const key = String(lesson.id);
    const bucket = buckets.get(key);
    if (!bucket || bucket.length === 0) {
      continue;
    }
    used.push(key);
    groups.push({
      lessonId: key,
      lessonTitle: lesson.title,
      stage: lesson.stage,
      exercises: bucket,
    });
  }
  for (const [key, bucket] of buckets) {
    if (used.indexOf(key) >= 0) {
      continue;
    }
    groups.push({
      lessonId: key,
      lessonTitle: key === "unknown" ? "未关联课程" : "课程 " + key,
      stage: "",
      exercises: bucket,
    });
  }
  return groups;
}

// 每道题的状态：未开始 / 已通过 / 未通过。左侧色条与标签都按它上色，
// 让「哪些题还没做、哪些已经过了」在列表里一眼可见。
function exerciseStatus(exercise: ExerciseSummary): {
  key: "todo" | "passed" | "failed";
  label: string;
  bar: string;
  tone: "neutral" | "success" | "danger";
} {
  const last = exercise.lastSubmission;
  if (!last) {
    return { key: "todo", label: "未开始", bar: "bg-line-strong", tone: "neutral" };
  }
  if (last.isPassed === true) {
    return { key: "passed", label: "已通过", bar: "bg-success", tone: "success" };
  }
  if (last.isPassed === false) {
    return { key: "failed", label: "未通过", bar: "bg-danger", tone: "danger" };
  }
  return { key: "todo", label: "结果未知", bar: "bg-warning", tone: "neutral" };
}

// 注意：difficulty 在后端是 1–5 的整数，但 lib/exercises.ts 已经把它映射成中文标签
// （入门/基础/中等/进阶/挑战）。之前这里按数字解析，Number("入门") 是 NaN，
// 于是难度徽标永远不显示——截图一直没变化才发现。现在按标签本身取色。
const DIFFICULTY_TONE: Record<string, "info" | "warning" | "danger"> = {
  入门: "info",
  基础: "info",
  中等: "warning",
  进阶: "danger",
  挑战: "danger",
};

function DifficultyPill({ value }: { value: string }) {
  const tone = DIFFICULTY_TONE[value];
  if (!tone) {
    return null;
  }
  return <Tag tone={tone}>{value}</Tag>;
}

function lastSubmissionText(exercise: ExerciseSummary): string {
  const last = exercise.lastSubmission;
  if (!last) {
    return "还没有提交记录";
  }
  return submissionStateLabel(last.isPassed) + " · " + formatDateTime(last.submittedAt);
}

// 静态说明不依赖任何接口：加载中与加载失败时同样保留，避免整页只剩一条错误或一片空白。
function PracticeAside() {
  return (
    <aside className="space-y-6">
      <Card>
        <CardHeader title="证据标签" description="标签只说明证据强度，不表示能力等级。" />
        <CardBody className="space-y-3">
          <EvidenceLegend />
          <p className="text-[11px] leading-relaxed text-muted">
            两种证据都不会写入六个技能域的等级，也不代表本产品认可的能力水平；等级仍只来自能力诊断。
          </p>
        </CardBody>
      </Card>

      <Card>
        <CardHeader title="判定方式" />
        <CardBody className="space-y-3 text-[11px] leading-relaxed text-muted">
          <p>
            <span className="font-medium text-fg">静态规则</span>
            ：按「必须出现 / 禁止出现」的模式比对你的代码文本，可选地比对你自己粘贴的输出文本。
          </p>
          <p>
            <span className="font-medium text-fg">自检</span>
            ：你在本地运行后勾选「我已自检通过」，系统原样记下，不做复核。
          </p>
          <p>系统不执行任何提交的代码，也没有代码执行沙箱。</p>
          <p className="rounded-control border border-line bg-surface px-3 py-2 text-fg">
            {EVIDENCE_DISCLAIMER}
          </p>
        </CardBody>
      </Card>
    </aside>
  );
}

export function PracticeView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      // 两个只读请求并发：练习列表是主数据，课程列表只用来补分组标题，后者的失败不影响前者。
      const [exerciseResult, lessonResult] = await Promise.all([
        apiRequest<ExerciseSummary[]>(EXERCISES_PATH, { parse: parseExerciseList }),
        apiRequest<LessonSummary[]>(LESSONS_PATH, { parse: parseLessons }),
      ]);
      if (!active) {
        return;
      }
      if (!exerciseResult.ok) {
        setState({ status: "error", failure: exerciseResult.failure });
        return;
      }
      const lessons = lessonResult.ok
        ? lessonResult.data.slice().sort((left, right) => left.orderIndex - right.orderIndex)
        : [];
      setState({
        status: "ready",
        groups: groupExercises(exerciseResult.data, lessons),
        total: exerciseResult.data.length,
        lessonsFailure: lessonResult.ok ? null : lessonResult.failure,
      });
    })();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setReloadToken((value) => value + 1);
  }, []);

  if (state.status === "loading") {
    return (
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <LoadingPanel
            title="正在读取练习列表"
            description="GET /api/v1/exercises；接口未就绪时显示错误态与重试，不显示占位题目。"
            rows={4}
          />
        </div>
        <PracticeAside />
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <ErrorPanel
            failure={state.failure}
            title="练习列表加载失败"
            onRetry={retry}
            extra={<p>拿不到真实练习时不展示任何题目条目，避免把占位内容当成可作答的题。</p>}
          />
        </div>
        <PracticeAside />
      </div>
    );
  }

  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6 lg:col-span-2">
        {state.lessonsFailure ? (
          <Alert
            tone="warning"
            title="课程标题读取失败"
            action={
              <Button variant="secondary" onClick={retry}>
                重试
              </Button>
            }
          >
            <p>
              练习列表本身已读取成功，但课程接口返回失败（{state.lessonsFailure.code}）。
              下面按 lesson_id 分组显示，标题暂时用课程编号代替。
            </p>
          </Alert>
        ) : null}

        {state.total === 0 ? (
          <EmptyState
            title="暂无练习题"
            description="后端还没有发布练习。练习发布后，这里会按课程分组列出，并显示每题最近一次的提交证据。"
          />
        ) : (
          <div className="space-y-6">
            {state.groups.map((group) => (
              <Card key={group.lessonId}>
                <CardHeader
                  title={group.lessonTitle}
                  description={
                    (group.stage ? "阶段 " + group.stage + " · " : "") +
                    String(group.exercises.length) +
                    " 道练习"
                  }
                  action={
                    group.lessonId === "unknown" ? null : (
                      <Link
                        href={"/learn/" + group.lessonId}
                        className="rounded-control text-[12px] font-medium text-accent hover:underline"
                      >
                        看课程
                      </Link>
                    )
                  }
                />
                <ul className="divide-y divide-line">
                  {group.exercises.map((exercise) => {
                    const status = exerciseStatus(exercise);
                    return (
                    <li
                      key={exercise.id}
                      className="flex flex-wrap items-start justify-between gap-3 px-5 py-4"
                    >
                      <span aria-hidden="true" className={cx("mt-1 h-9 w-1 shrink-0 rounded-full", status.bar)} />
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <Link
                            href={practicePagePath(exercise.id)}
                            className="text-[13px] font-medium text-fg hover:underline"
                          >
                            {exercise.title}
                          </Link>
                          <Tag tone={status.tone}>{status.label}</Tag>
                        </div>
                        <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                          {exercise.difficulty ? <DifficultyPill value={exercise.difficulty} /> : null}
                          <span>预计 {formatMinutes(exercise.estimatedMinutes)}</span>
                          {exercise.code ? (
                            <span className="font-mono">{exercise.code}</span>
                          ) : null}
                          {exercise.contentVersion ? (
                            <span className="font-mono">内容版本 {exercise.contentVersion}</span>
                          ) : null}
                        </p>
                      </div>
                      <div className="flex flex-wrap items-center gap-2">
                        <EvidenceBadge
                          kind={evidenceKind(
                            exercise.lastSubmission ? exercise.lastSubmission.strength : null,
                            exercise.lastSubmission !== null,
                          )}
                        />
                        <span className="text-[11px] text-muted">
                          {lastSubmissionText(exercise)}
                        </span>
                      </div>
                    </li>
                    );
                  })}
                </ul>
              </Card>
            ))}
          </div>
        )}
      </div>

      <PracticeAside />
    </div>
  );
}
