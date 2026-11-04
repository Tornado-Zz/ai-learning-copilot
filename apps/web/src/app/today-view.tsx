"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { SystemStatusCard } from "@/components/system-status";
import { PlanItemCard } from "@/components/plan-item";
import { Button } from "@/components/form";
import { Alert, EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseUsersMe } from "@/lib/contract";
import type { UsersMe } from "@/lib/contract";
import {
  STUDY_PLAN_PATH,
  formatMinutes,
  localDateISO,
  parseStudyPlan,
  planItemTitle,
  weekdayOfDate,
} from "@/lib/learning";
import type { PlanItem, StudyPlan } from "@/lib/learning";
import { resolveDayBudget, resolvePlanCounts } from "@/lib/plan-rules";
import { timezoneLabel } from "@/lib/labels";

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "needs-timezone"; me: UsersMe; reason: "unconfirmed" | "conflict" }
  | { status: "ready"; me: UsersMe; plan: StudyPlan; today: string; items: PlanItem[] };

const CONFIRM_LINK =
  "rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas";

export function TodayView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const meResult = await apiRequest<UsersMe>("/api/v1/users/me", { parse: parseUsersMe });
      if (!active) {
        return;
      }
      if (!meResult.ok) {
        setState({ status: "error", failure: meResult.failure });
        return;
      }
      const me = meResult.data;
      // 时区未确认时不做任何「今天 / 本周」推导（DATABASE 4.14 R6、契约 I7）。
      if (me.user.timezoneSource !== "user_confirmed") {
        setState({ status: "needs-timezone", me, reason: "unconfirmed" });
        return;
      }
      const planResult = await apiRequest<StudyPlan>(STUDY_PLAN_PATH, { parse: parseStudyPlan });
      if (!active) {
        return;
      }
      if (!planResult.ok) {
        if (planResult.failure.status === 409) {
          setState({ status: "needs-timezone", me, reason: "conflict" });
          return;
        }
        setState({ status: "error", failure: planResult.failure });
        return;
      }
      const plan = planResult.data;
      const today = plan.today ?? localDateISO(me.user.timezone);
      if (today === null) {
        setState({ status: "needs-timezone", me, reason: "unconfirmed" });
        return;
      }
      let items: PlanItem[] = [];
      for (const day of plan.days) {
        if (day.date === today) {
          items = day.items;
        }
      }
      setState({ status: "ready", me, plan, today, items });
    })();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setReloadToken((value) => value + 1);
  }, []);

  let eyebrow = "本周计划";
  let subtitle = "今日任务来自后端周计划，本页不显示任何演示任务。";
  if (state.status === "loading") {
    eyebrow = "正在读取本周计划";
    subtitle = "按用户时区取今天这一天的分组。";
  } else if (state.status === "needs-timezone") {
    eyebrow = "需要先确认时区";
    subtitle = "时区未确认前，本页不推导「今天」，也不显示任何任务。";
  } else if (state.status === "ready") {
    eyebrow =
      "本周计划 " +
      state.plan.weekStart +
      " 起 · " +
      state.today +
      "（" +
      (weekdayOfDate(state.today) || "日期未知") +
      "）· " +
      timezoneLabel(state.me.user.timezone);
    // S5：今日同样把「待执行」与「已完成/已跳过」分开，历史量不计入待执行。
    const todayBudget = resolveDayBudget({}, state.items);
    const todayCounts = resolvePlanCounts({ scheduledItems: null, historyItems: null }, state.items);
    subtitle =
      state.items.length === 0
        ? "今天没有安排任务。"
        : "待执行 " +
          String(todayCounts.scheduledItems) +
          " 项 · " +
          formatMinutes(todayBudget.scheduledMinutes) +
          "，已完成或已跳过 " +
          String(todayCounts.historyItems) +
          " 项 · " +
          formatMinutes(todayBudget.historyMinutes) +
          "。";
  }

  // 任务 4：全页唯一的显眼引导入口。只用今天已有的计划项，不新增接口、不补占位任务。
  // 有 scheduled 项就「继续」它；否则退回第一项，文案改成通用入口，不改写任何数据。
  const nextEntry =
    state.status === "ready"
      ? (state.items.find((item) => item.status === "scheduled" && item.targetHref !== null) ??
        state.items.find((item) => item.targetHref !== null) ??
        null)
      : null;
  const nextEntryHref = nextEntry ? nextEntry.targetHref : null;

  return (
    <div className="space-y-8">
      <header className="flex flex-col gap-5 border-b border-line pb-6 lg:flex-row lg:items-end lg:justify-between">
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-muted">{eyebrow}</p>
          <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">今日概览</h1>
          <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">{subtitle}</p>
        </div>
        <div className="flex shrink-0 flex-col items-stretch gap-2 sm:items-end">
          {nextEntry && nextEntryHref !== null ? (
            <Link
              href={nextEntryHref}
              className="inline-flex items-center justify-between gap-3 rounded-control bg-accent px-4 py-2.5 text-canvas transition-opacity hover:opacity-90"
            >
              <span className="flex min-w-0 flex-col">
                <span className="text-[11px] font-medium opacity-80">
                  {nextEntry.status === "scheduled" ? "继续学习" : "从今天的第一项开始"}
                </span>
                <span className="max-w-[220px] truncate text-[13px] font-semibold">
                  {planItemTitle(nextEntry)}
                </span>
              </span>
              <span aria-hidden="true" className="text-[15px] leading-none">
                →
              </span>
            </Link>
          ) : null}
          <div className="flex items-center gap-2 sm:justify-end">
            <Link
              href="/plan"
              className="rounded-control border border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg"
            >
              查看周计划
            </Link>
            <Link
              href="/learn"
              className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
            >
              浏览课程
            </Link>
          </div>
        </div>
      </header>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          {state.status === "loading" ? (
            <LoadingPanel title="正在读取今日任务" description="按用户时区取当天分组。" rows={4} />
          ) : null}

          {state.status === "error" ? (
            <ErrorPanel
              failure={state.failure}
              title="今日任务加载失败"
              onRetry={retry}
              extra={<p>接口未就绪时不显示任何占位任务，也不会用本地数据补位。</p>}
            />
          ) : null}

          {state.status === "needs-timezone" ? (
            <div className="space-y-4">
              <Alert
                tone="warning"
                title="需要先确认时区，才能确定「今天」"
                action={
                  <Link href="/onboarding" className={CONFIRM_LINK}>
                    去档案页确认时区
                  </Link>
                }
              >
                <p>
                  {state.reason === "conflict"
                    ? "后端返回 409 CONFLICT：users.timezone_source 尚未确认为 user_confirmed。"
                    : "users.timezone_source 当前为 default；未确认前本页不推导今天与本周。"}
                </p>
                <p>当前档案：{state.me.profile.studyDays.length} 个学习日 / 每天 {formatMinutes(state.me.profile.dailyMinutes)}。</p>
              </Alert>
              <EmptyState
                title="今日任务暂不展示"
                description="确认时区后回到本页，即可看到本周计划里今天的真实任务。"
              />
            </div>
          ) : null}

          {state.status === "ready" ? (
            <>
              <Card>
                <CardHeader
                  title="今日任务"
                  description={state.today + " · " + (weekdayOfDate(state.today) || "日期未知")}
                  action={<Tag>{String(state.items.length)} 项</Tag>}
                />
                {state.items.length === 0 ? (
                  <CardBody>
                    <EmptyState
                      title="今天没有安排"
                      description="今天可能是非学习日，或本周计划还没有生成。"
                      action={
                        <Link
                          href="/plan"
                          className="rounded-control border border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg"
                        >
                          打开周计划
                        </Link>
                      }
                    />
                  </CardBody>
                ) : (
                  <ul className="space-y-2 border-t border-line p-4">
                    {state.items.map((item, index) => (
                      <PlanItemCard key={item.id} item={item} index={index + 1} />
                    ))}
                  </ul>
                )}
                <div className="border-t border-line px-5 py-3">
                  <p className="text-[11px] leading-relaxed text-muted">
                    本页只读；标记完成与重新生成都在周计划页。
                  </p>
                </div>
              </Card>
            </>
          ) : null}
        </div>

        <aside className="space-y-6">
          <SystemStatusCard />

          <Card>
            <CardHeader title="本周计划" description="整周安排来自同一份 study_plan_items。" />
            <CardBody className="space-y-3">
              {state.status === "ready" ? (
                <>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[12px] text-muted">周起始</span>
                    <span className="font-mono text-[12px] tabular-nums text-fg">
                      {state.plan.weekStart}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[12px] text-muted">有任务的天数</span>
                    <span className="font-mono text-[12px] tabular-nums text-fg">
                      {String(state.plan.days.filter((day) => day.items.length > 0).length)} 天
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[12px] text-muted">本周待执行</span>
                    <span className="font-mono text-[12px] tabular-nums text-fg">
                      {formatMinutes(
                        state.plan.days.reduce(
                          (sum, day) => sum + resolveDayBudget({}, day.items).scheduledMinutes,
                          0,
                        ),
                      )}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[12px] text-muted">本周已完成/已跳过</span>
                    <span className="font-mono text-[12px] tabular-nums text-fg">
                      {formatMinutes(
                        state.plan.days.reduce(
                          (sum, day) => sum + resolveDayBudget({}, day.items).historyMinutes,
                          0,
                        ),
                      )}
                    </span>
                  </div>
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-[12px] text-muted">每天可用</span>
                    <span className="font-mono text-[12px] tabular-nums text-fg">
                      {formatMinutes(state.me.profile.dailyMinutes)}
                    </span>
                  </div>
                </>
              ) : (
                <p className="text-[11px] leading-relaxed text-muted">
                  周计划数据尚未读取完成；本卡片不会用估算值占位。
                </p>
              )}
              <Link
                href="/plan"
                className="inline-block rounded-control text-[12px] font-medium text-muted hover:text-fg"
              >
                打开周计划页
              </Link>
            </CardBody>
          </Card>

          {state.status === "error" ? (
            <Button variant="secondary" onClick={retry}>
              重新读取今日任务
            </Button>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
