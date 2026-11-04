"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardHeader, Meter, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { LESSONS_PATH, LESSON_STATUS_LABELS, formatMinutes, parseLessons } from "@/lib/learning";
import type { LessonSummary } from "@/lib/learning";

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; lessons: LessonSummary[] };

export function LessonList() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<LessonSummary[]>(LESSONS_PATH, { parse: parseLessons });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", lessons: result.data });
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
      <LoadingPanel
        title="正在读取课程列表"
        description="GET /api/v1/lessons，仅返回已发布课程。"
        rows={4}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="课程列表加载失败"
        onRetry={retry}
        extra={<p>接口未就绪时不显示任何占位课程，六域等级区块仍可正常阅读。</p>}
      />
    );
  }

  if (state.lessons.length === 0) {
    return (
      <EmptyState
        title="还没有已发布的课程"
        description="后端 lessons 表中没有 status='published' 的课程时，本区块保持为空，不展示占位课程。"
        action={
          <Button variant="secondary" onClick={retry}>
            重新读取
          </Button>
        }
      />
    );
  }

  return (
    <Card>
      <CardHeader
        title="课程"
        description="按课程顺序列出已发布课程；进度状态来自 GET /api/v1/lessons 的 progress 字段。"
        action={
          <Button variant="secondary" onClick={retry}>
            刷新
          </Button>
        }
      />
      <ul className="divide-y divide-line">
        {state.lessons.map((lesson, index) => (
          <li key={lesson.id} className="px-5 py-3">
            <Link
              href={`/learn/${String(lesson.id)}`}
              className="group block rounded-control outline-offset-4"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="grid size-5 shrink-0 place-items-center rounded-control border border-line bg-surface font-mono text-[10px] text-muted">
                  {String(index + 1)}
                </span>
                <span className="text-[13px] font-medium text-fg group-hover:text-accent">
                  {lesson.title}
                </span>
                {lesson.stage ? <Tag>阶段 {lesson.stage}</Tag> : null}
                <Tag tone={lesson.progress.status === "completed" ? "accent" : "neutral"}>
                  {LESSON_STATUS_LABELS[lesson.progress.status]}
                </Tag>
                <span className="ml-auto font-mono text-[11px] tabular-nums text-muted">
                  预计 {formatMinutes(lesson.estimatedMinutes)}
                </span>
              </div>
              {lesson.summary ? (
                <p className="mt-1 text-[11px] leading-relaxed text-muted">{lesson.summary}</p>
              ) : null}
              {lesson.code || lesson.contentVersion ? (
                <p className="mt-1 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
                  {lesson.code ? <span>{lesson.code}</span> : null}
                  {lesson.contentVersion ? <span>版本 {lesson.contentVersion}</span> : null}
                </p>
              ) : null}
              {lesson.progress.progressPct > 0 ? (
                <div className="mt-2 max-w-[320px]">
                  <Meter
                    value={lesson.progress.progressPct}
                    tone="muted"
                    label={lesson.title + " 完成率"}
                  />
                </div>
              ) : null}
            </Link>
          </li>
        ))}
      </ul>
      <div className="border-t border-line px-5 py-3">
        <p className="text-[11px] leading-relaxed text-muted">
          点击任意课程进入详情；打开课程不会自动标记完成，进度只在你点击按钮时写入。
        </p>
      </div>
    </Card>
  );
}
