"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { Button } from "@/components/form";
import { Alert, EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { practicePagePath } from "@/lib/exercises";
import { weekdayOfDate } from "@/lib/learning";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import {
  REVIEW_PAGE_LIMIT,
  REVIEW_SUMMARY_PATH,
  parseReviewItems,
  parseReviewSummary,
  reviewCountText,
  reviewDaysText,
  reviewItemsPath,
  reviewLastResultLabel,
  reviewStatusLabel,
} from "@/lib/review";
import type { ReviewItem, ReviewItemPage, ReviewSummary } from "@/lib/review";

// 「今天到期」用 due=1；「全部待复习」不加过滤，一律按后端返回的真实行渲染。
const DUE_ITEMS_PATH = reviewItemsPath({ due: true, limit: REVIEW_PAGE_LIMIT });
const ALL_ITEMS_PATH = reviewItemsPath({ limit: REVIEW_PAGE_LIMIT });

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure; path: string }
  | { status: "ready"; due: ReviewItemPage; all: ReviewItemPage; summary: ReviewSummary };

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-muted">{label}</dt>
      <dd className="mt-0.5 font-mono text-[14px] tabular-nums font-medium text-fg">{value}</dd>
    </div>
  );
}

// 日期是后端的 date 字段，按原样显示；只额外补一个本地推导的星期几，不改写日期本身。
function dateText(date: string | null): string {
  if (date === null) {
    return "—";
  }
  const weekday = weekdayOfDate(date);
  return weekday ? date + "（" + weekday + "）" : date;
}

function ReviewRow({ item, index }: { item: ReviewItem; index: number }) {
  const href = item.exerciseId === null ? null : practicePagePath(item.exerciseId);
  const title = item.exerciseTitle === null ? "—" : item.exerciseTitle;
  return (
    <li className="flex flex-wrap items-start gap-2 px-4 py-3">
      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-control border border-line bg-surface font-mono text-[10px] text-muted">
        {String(index)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {href === null ? (
            <span className="text-[13px] font-medium text-fg">{title}</span>
          ) : (
            <Link
              href={href}
              className="text-[13px] font-medium text-fg underline-offset-2 hover:text-accent hover:underline"
            >
              {title}
            </Link>
          )}
          <Tag tone={item.status === "pending" ? "accent" : "neutral"}>
            {reviewStatusLabel(item.status)}
          </Tag>
          {item.due === true ? <Tag tone="accent">今日到期</Tag> : <Tag>{reviewLastResultLabel(item.lastResult)}</Tag>}
        </div>
        <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] leading-relaxed text-muted">
          <span>连续答对 {item.streak === null ? "—" : String(item.streak) + " 次"}</span>
          <span>当前间隔 {reviewDaysText(item.intervalDays)}</span>
          <span>下次复习 {dateText(item.nextReviewOn)}</span>
          {item.exerciseId === null ? <span>缺 exercise_id，不可跳转</span> : null}
        </div>
      </div>
    </li>
  );
}

function ItemBlock({
  title,
  description,
  path,
  page,
  total,
  emptyTitle,
  emptyDescription,
  emptyAction,
}: {
  title: string;
  description: string;
  path: string;
  page: ReviewItemPage;
  total: number | null;
  emptyTitle: string;
  emptyDescription: string;
  emptyAction?: ReactNode;
}) {
  return (
    <Card>
      <CardHeader
        title={title}
        description={description}
        action={<Tag>{reviewCountText(total) + " 项"}</Tag>}
      />
      {page.items.length === 0 ? (
        <CardBody>
          <EmptyState title={emptyTitle} description={emptyDescription} action={emptyAction} />
        </CardBody>
      ) : (
        <ul className="divide-y divide-line">
          {page.items.map((item, index) => (
            <ReviewRow key={item.id} item={item} index={index + 1} />
          ))}
        </ul>
      )}
      <div className="border-t border-line px-5 py-3">
        <p className="font-mono text-[11px] text-muted">{path}</p>
      </div>
    </Card>
  );
}

export function ReviewView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const [dueResult, allResult, summaryResult] = await Promise.all([
        apiRequest<ReviewItemPage>(DUE_ITEMS_PATH, { parse: parseReviewItems }),
        apiRequest<ReviewItemPage>(ALL_ITEMS_PATH, { parse: parseReviewItems }),
        apiRequest<ReviewSummary>(REVIEW_SUMMARY_PATH, { parse: parseReviewSummary }),
      ]);
      if (!active) {
        return;
      }
      // 三个读接口任一失败就显示错误态（错误码 + request_id 由 ErrorPanel 渲染），
      // 不做「部分渲染 + 其余留空」，也不补任何占位复习项。
      if (!dueResult.ok) {
        setState({ status: "error", failure: dueResult.failure, path: DUE_ITEMS_PATH });
        return;
      }
      if (!allResult.ok) {
        setState({ status: "error", failure: allResult.failure, path: ALL_ITEMS_PATH });
        return;
      }
      if (!summaryResult.ok) {
        setState({ status: "error", failure: summaryResult.failure, path: REVIEW_SUMMARY_PATH });
        return;
      }
      setState({
        status: "ready",
        due: dueResult.data,
        all: allResult.data,
        summary: summaryResult.data,
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
      <LoadingPanel
        title="正在读取错题本"
        description={
          "同时读取 " + DUE_ITEMS_PATH + "、" + ALL_ITEMS_PATH + " 与 " + REVIEW_SUMMARY_PATH + "。"
        }
        rows={4}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="错题本加载失败"
        onRetry={retry}
        extra={
          <p>
            失败接口：<span className="font-mono">{state.path}</span>。
            接口未就绪时本页不显示任何占位复习项，也不会用本地数据补位。
          </p>
        }
      />
    );
  }

  const { due, all, summary } = state;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="复习概览"
          description="数字全部来自 GET /api/v1/review/summary；后端缺字段显示「—」，不补 0。"
        />
        <CardBody>
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="待复习" value={reviewCountText(summary.pending)} />
            <Metric label="今日到期" value={reviewCountText(summary.dueToday)} />
            <Metric label="已完成" value={reviewCountText(summary.done)} />
            <Metric label="下次到期" value={dateText(summary.nextDueOn)} />
          </dl>
        </CardBody>
      </Card>

      <ItemBlock
        title="今天到期"
        description="status='pending' 且 next_review_on 不晚于今天；点练习题名进入该题。"
        path={DUE_ITEMS_PATH}
        page={due}
        total={due.dueTotal}
        emptyTitle="今天没有到期的复习"
        emptyDescription="答错一道练习后，第二天起才会出现在这里；本页不凭空生成复习项。"
      />

      <ItemBlock
        title="全部待复习"
        description="GET /api/v1/review/items 的默认分页（不带 due 过滤），按后端返回的真实 status 显示。"
        path={ALL_ITEMS_PATH}
        page={all}
        total={all.total}
        emptyTitle="还没有复习项"
        emptyDescription="只有答错过的题才会建档；答对但从未答错的题不会产生任何行。"
        emptyAction={
          <Link
            href="/practice"
            className="rounded-control border border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg"
          >
            去练习
          </Link>
        }
      />

      <Alert tone="muted" title="口径说明">
        <p>
          复习项由练习提交在服务端同事务调度：答错重置为 1 天，答对按 1 /
          3 / 7 / 14 天推进，第 3 次答对后 status 变为 done。done 只是状态，行永不删除。
        </p>
        <p>本页只读，不发起写请求；间隔与 status 都以接口返回为准。</p>
      </Alert>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={retry}>
          重新读取错题本
        </Button>
        <Link
          href="/practice"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          练习列表
        </Link>
        <Link
          href="/plan"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          周计划
        </Link>
        <Link
          href="/"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          回到今日
        </Link>
      </div>
    </div>
  );
}
