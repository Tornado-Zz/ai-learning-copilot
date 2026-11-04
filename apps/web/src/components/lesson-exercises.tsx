"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { EvidenceBadge, evidenceKind } from "@/components/evidence-badge";
import { Alert, SkeletonLines } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { formatMinutes } from "@/lib/learning";
import { exercisesByLessonPath, parseExerciseList, practicePagePath } from "@/lib/exercises";
import type { ExerciseSummary } from "@/lib/exercises";

// 课程详情里的练习入口：只读 GET /api/v1/exercises?lesson_id=。
// 接口未就绪时显示错误与重试，不显示占位题目；练习本轮不写入周计划，因此这里也不提供「加入计划」。

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; exercises: ExerciseSummary[] };

export function LessonExercises({ lessonId }: { lessonId: string }) {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<ExerciseSummary[]>(exercisesByLessonPath(lessonId), {
        parse: parseExerciseList,
      });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", exercises: result.data });
    })();
    return () => {
      active = false;
    };
  }, [lessonId, reloadToken]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setReloadToken((value) => value + 1);
  }, []);

  return (
    <Card>
      <CardHeader
        title="本课练习"
        description="判题只做静态规则比对与用户自检，系统不执行代码。"
        action={
          state.status === "ready" ? <Tag>{state.exercises.length + " 道"}</Tag> : null
        }
      />
      <CardBody className="space-y-3">
        {state.status === "loading" ? (
          <div aria-busy="true" className="space-y-2">
            <SkeletonLines rows={2} />
          </div>
        ) : null}

        {state.status === "error" ? (
          <Alert
            tone="warning"
            title="本课练习加载失败"
            action={
              <Button variant="secondary" onClick={retry}>
                重试
              </Button>
            }
          >
            <p>
              {state.failure.message}
              <span className="ml-2 font-mono text-[11px]">{state.failure.code}</span>
            </p>
            <p>练习接口未就绪时这里不会显示占位题目；课程正文与进度不受影响。</p>
          </Alert>
        ) : null}

        {state.status === "ready" && state.exercises.length === 0 ? (
          <p className="text-[11px] leading-relaxed text-muted">
            本课还没有练习。练习发布后会出现在这里，也可以到练习列表查看全部题目。
          </p>
        ) : null}

        {state.status === "ready" && state.exercises.length > 0 ? (
          <ul className="divide-y divide-line">
            {state.exercises.map((exercise) => (
              <li
                key={exercise.id}
                className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
              >
                <div className="min-w-0">
                  <Link
                    href={practicePagePath(exercise.id)}
                    className="text-[13px] font-medium text-fg hover:underline"
                  >
                    {exercise.title}
                  </Link>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-[11px] text-muted">
                    {exercise.difficulty ? <Tag>{exercise.difficulty}</Tag> : null}
                    <span>预计 {formatMinutes(exercise.estimatedMinutes)}</span>
                    {exercise.code ? <span className="font-mono">{exercise.code}</span> : null}
                  </p>
                </div>
                <EvidenceBadge
                  kind={evidenceKind(
                    exercise.lastSubmission ? exercise.lastSubmission.strength : null,
                    exercise.lastSubmission !== null,
                  )}
                />
              </li>
            ))}
          </ul>
        ) : null}

        <Link
          href="/practice"
          className="inline-block rounded-control text-[12px] font-medium text-accent hover:underline"
        >
          查看全部练习
        </Link>
      </CardBody>
    </Card>
  );
}
