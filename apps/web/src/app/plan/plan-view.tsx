"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { PlanItemRow } from "@/components/plan-item";
import { Alert, EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Meter, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseUsersMe } from "@/lib/contract";
import type { SkillLevelRow, UsersMe } from "@/lib/contract";
import {
  STUDY_PLAN_GENERATE_PATH,
  STUDY_PLAN_PATH,
  formatMinutes,
  parseAck,
  parseStudyPlan,
  studyPlanItemPath,
  weekdayOfDate,
} from "@/lib/learning";
import type { PlanItem, StudyPlan } from "@/lib/learning";
import {
  BUDGET_SCOPE_NOTE,
  PLAN_ITEM_ACTION_STATUS,
  budgetExceedsDailyMinutes,
  budgetOverLimitNote,
  planItemActions,
  resolveDayBudget,
  resolvePlanCounts,
} from "@/lib/plan-rules";
import type { PlanItemAction } from "@/lib/plan-rules";
import { levelLabel, timezoneLabel, weekdayLabel } from "@/lib/labels";
import { DOMAINS } from "@/lib/questions";

// S1：可写的只有 done / skipped 两个目标状态；页面不再拼任何其它状态值。
const ACTION_LABEL: Record<PlanItemAction, string> = {
  complete: "标记完成",
  skip: "跳过",
};

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "needs-timezone"; me: UsersMe; reason: "unconfirmed" | "conflict" }
  | { status: "ready"; me: UsersMe; plan: StudyPlan };

function findSkill(skills: SkillLevelRow[], code: string): SkillLevelRow | null {
  for (const skill of skills) {
    if (skill.code === code) {
      return skill;
    }
  }
  return null;
}

function stageAdvice(skill: SkillLevelRow | null): string {
  if (!skill) {
    return "该域还没有数据，先完成一次诊断拿到起始等级。";
  }
  if (skill.state === "established") {
    if (skill.level >= 2) {
      return "进入练习与项目阶段，用可复核的证据继续推进。";
    }
    return "按示例改写代码，把「认识概念」推进到能跟做的水平。";
  }
  if (skill.state === "assessed_below_threshold") {
    return "回到基础概念与语法，先把该域正确率推过 60% 的 L1 门槛。";
  }
  if (skill.state === "requested_verification") {
    return "先积累实践证据，再申请该域的等级核验。";
  }
  return "尚未评估：先完成一次诊断，再决定投入顺序。";
}

export function PlanView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);
  const [generating, setGenerating] = useState(false);
  const [pendingItemId, setPendingItemId] = useState<number | null>(null);
  const [actionFailure, setActionFailure] = useState<ApiFailure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

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
      setState({ status: "ready", me, plan: planResult.data });
    })();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setActionFailure(null);
    setReloadToken((value) => value + 1);
  }, []);

  // 写操作成功后只重读计划，不猜测新状态：列表始终等于接口返回的那一行。
  const reloadPlan = useCallback(async () => {
    const planResult = await apiRequest<StudyPlan>(STUDY_PLAN_PATH, { parse: parseStudyPlan });
    if (!planResult.ok) {
      setActionFailure(planResult.failure);
      return;
    }
    const next = planResult.data;
    setState((current) =>
      current.status === "ready" ? { status: "ready", me: current.me, plan: next } : current,
    );
  }, []);

  const regenerate = useCallback(async () => {
    setGenerating(true);
    setActionFailure(null);
    setNotice(null);
    const result = await apiRequest<true>(STUDY_PLAN_GENERATE_PATH, {
      method: "POST",
      parse: parseAck,
    });
    setGenerating(false);
    if (!result.ok) {
      setActionFailure(result.failure);
      return;
    }
    setNotice("已请求重新生成本周计划，计划列表已按接口返回结果刷新。");
    await reloadPlan();
  }, [reloadPlan]);

  const updateStatus = useCallback(
    async (item: PlanItem, action: PlanItemAction) => {
      // P1-05：非法操作不发出请求——只有 scheduled 行可写，且目标状态只能是 done / skipped。
      if (item.id < 0 || planItemActions(item.status).indexOf(action) < 0) {
        return;
      }
      setPendingItemId(item.id);
      setActionFailure(null);
      setNotice(null);
      const result = await apiRequest<true>(studyPlanItemPath(item.id), {
        method: "PATCH",
        body: { status: PLAN_ITEM_ACTION_STATUS[action] },
        parse: parseAck,
      });
      setPendingItemId(null);
      if (!result.ok) {
        setActionFailure(result.failure);
        return;
      }
      setNotice("任务状态已更新，计划列表已按接口返回结果刷新。");
      await reloadPlan();
    },
    [reloadPlan],
  );

  if (state.status === "loading") {
    return (
      <LoadingPanel
        title="正在读取本周计划"
        description="依次读取 GET /api/v1/users/me 与 GET /api/v1/study-plan。"
        rows={4}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="周计划加载失败"
        onRetry={retry}
        extra={<p>接口未就绪时不显示任何占位计划，也不会用本地数据补位。</p>}
      />
    );
  }

  if (state.status === "needs-timezone") {
    return (
      <div className="space-y-4">
        <Alert
          tone="warning"
          title="需要先确认时区，才能确定本周的起止日期"
          action={
            <Link
              href="/onboarding"
              className="rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas"
            >
              去档案页确认时区
            </Link>
          }
        >
          <p>
            {state.reason === "conflict"
              ? "后端返回 409 CONFLICT：users.timezone_source 尚未确认为 user_confirmed。"
              : "users.timezone_source 当前为 default；未确认前本页不展示任何「今天 / 本周」推导（契约 I7）。"}
          </p>
          <p>
            当前档案：{state.me.profile.studyDays.length} 个学习日 / 每天{" "}
            {formatMinutes(state.me.profile.dailyMinutes)}。
          </p>
        </Alert>
        <EmptyState
          title="本周计划暂不展示"
          description="确认时区后回到本页，即可看到按 plan_date 分组的真实任务。"
        />
      </div>
    );
  }

  const { me, plan } = state;
  // A3：逐日与整周都拆「待执行 / 历史」两个口径。历史终态分钟仍计入当日已分配预算
  // （所以新排课额度 = daily_minutes − 历史分钟），只是不计入「待执行工作量」。
  const dailyMinutes = plan.dailyMinutes ?? me.profile.dailyMinutes;
  const activeDays = plan.days
    .map((day) => {
      const budget = resolveDayBudget(
        {
          scheduledMinutes: day.scheduledMinutes,
          historyMinutes: day.historyMinutes,
          totalMinutes: day.totalMinutes,
        },
        day.items,
      );
      return {
        day,
        budget,
        counts: resolvePlanCounts({ scheduledItems: null, historyItems: null }, day.items),
        exceedsDaily: budgetExceedsDailyMinutes(budget, dailyMinutes),
      };
    })
    .filter((entry) => entry.day.items.length > 0);
  const weekBudget = plan.days.reduce(
    (sum, day) => {
      const budget = resolveDayBudget(
        {
          scheduledMinutes: day.scheduledMinutes,
          historyMinutes: day.historyMinutes,
          totalMinutes: day.totalMinutes,
        },
        day.items,
      );
      return {
        scheduledMinutes: sum.scheduledMinutes + budget.scheduledMinutes,
        historyMinutes: sum.historyMinutes + budget.historyMinutes,
        totalMinutes: sum.totalMinutes + budget.totalMinutes,
      };
    },
    { scheduledMinutes: 0, historyMinutes: 0, totalMinutes: 0 },
  );
  const weekCounts = resolvePlanCounts(
    { scheduledItems: plan.scheduledItems, historyItems: plan.historyItems },
    plan.days.reduce<PlanItem[]>((sum, day) => sum.concat(day.items), []),
  );
  const focus =
    (() => {
      for (const domain of DOMAINS) {
        const skill = findSkill(me.skills, domain.code);
        if (skill && (skill.state !== "established" || skill.level < 2)) {
          return skill;
        }
      }
      return me.skills.length > 0 ? me.skills[0] : null;
    })();

  // S1：只有 scheduled 行渲染「标记完成 / 跳过」；done / skipped 是终态、expired 只能被重生成复活，
  // 三类行一律只读，不出现任何会失败的操作按钮。也不存在「撤销」：scheduled 只能由重新生成写入。
  const itemActions = (item: PlanItem) => {
    const actions = planItemActions(item.status);
    if (actions.length === 0) {
      return null;
    }
    const blocked = item.id < 0;
    const disabled = pendingItemId !== null || blocked;
    return (
      <>
        {actions.map((action) => (
          <Button
            key={action}
            variant={action === "complete" ? "secondary" : "quiet"}
            onClick={() => void updateStatus(item, action)}
            disabled={disabled}
            aria-disabled={disabled}
            title={blocked ? "任务缺少 id，无法更新状态" : undefined}
          >
            {pendingItemId === item.id && action === "complete"
              ? "保存中…"
              : ACTION_LABEL[action]}
          </Button>
        ))}
      </>
    );
  };

  // 六个域全都没评估过 → 计划只能按默认 L0 排，理由会很空洞。此时最该做的是先诊断。
  const neverAssessed = me.skills.length > 0 && me.skills.every((skill) => skill.state === "unassessed");

  return (
    <div className="space-y-6">
      {neverAssessed ? (
        <Alert tone="accent" title="还没做过能力诊断：计划现在只能按默认 L0 排">
          <p>
            20 道题、约 10 分钟。做完之后，计划会按你六个领域的真实水平挑选课程与练习，
            每一条安排的「理由」也才有依据；现在生成的计划一律按 L0 起步。
          </p>
          <p className="mt-1">
            <Link href="/diagnostic" className="underline hover:text-fg">
              去做诊断
            </Link>
            <span className="text-muted">（做完再回来生成计划）</span>
          </p>
        </Alert>
      ) : null}
      <Card>
        <CardHeader
          title="本周计划"
          description={"时区 " + timezoneLabel(me.user.timezone) + " · 课程与练习都按 plan_date 排入当天"}
          action={
            <Button
              variant="primary"
              onClick={() => void regenerate()}
              disabled={generating}
              aria-disabled={generating}
            >
              {generating ? "正在生成…" : "重新生成本周计划"}
            </Button>
          }
        />
        <CardBody className="space-y-4">
          {notice ? (
            <Alert tone="accent" title="操作成功">
              <p>{notice}</p>
            </Alert>
          ) : null}

          {actionFailure ? (
            <Alert tone="danger" title="计划操作失败">
              <p>
                {actionFailure.message}
                <span className="ml-2 font-mono text-[11px]">{actionFailure.code}</span>
              </p>
              <p>
                失败时列表保持接口返回的真实状态，不做本地乐观改写。任务状态更新依赖
                PATCH /api/v1/study-plan/items/{"{id}"}；后端未提供时该操作返回 404。
              </p>
              <div className="mt-2">
                <Button variant="secondary" onClick={retry}>
                  重新读取计划
                </Button>
              </div>
            </Alert>
          ) : null}

          <dl className="grid grid-cols-2 gap-3 text-[11px] sm:grid-cols-5">
            <div>
              <dt className="text-muted">周区间</dt>
              <dd className="mt-0.5 font-mono text-[12px] tabular-nums font-medium text-fg">
                {plan.weekEnd ? plan.weekStart + " – " + plan.weekEnd : plan.weekStart}
              </dd>
            </div>
            <div>
              <dt className="text-muted">学习日</dt>
              <dd className="mt-0.5 text-[12px] font-medium text-fg">
                {me.profile.studyDays.length > 0
                  ? me.profile.studyDays.map((day) => weekdayLabel(day)).join("、")
                  : "未设置"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">每天可用</dt>
              <dd className="mt-0.5 font-mono text-[12px] tabular-nums font-medium text-fg">
                {formatMinutes(me.profile.dailyMinutes)}
              </dd>
            </div>
            <div>
              <dt className="text-muted">本周待执行</dt>
              <dd className="mt-0.5 font-mono text-[12px] tabular-nums font-medium text-fg">
                {formatMinutes(weekBudget.scheduledMinutes) +
                  " · " +
                  String(weekCounts.scheduledItems) +
                  " 项"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">已完成/已跳过</dt>
              <dd className="mt-0.5 font-mono text-[12px] tabular-nums font-medium text-fg">
                {formatMinutes(weekBudget.historyMinutes) +
                  " · " +
                  String(weekCounts.historyItems) +
                  " 项"}
              </dd>
            </div>
          </dl>

          {/* 口径与终态规则收进折叠块：零基础用户首屏先看到任务本身，需要时再展开细节。 */}
          <details className="rounded-control border border-line bg-surface px-3 py-2">
            <summary className="cursor-pointer text-[11px] font-medium text-muted hover:text-fg">
              预算与终态口径
            </summary>
            <div className="mt-2 space-y-2 text-[11px] leading-relaxed text-muted">
              <p>{BUDGET_SCOPE_NOTE}</p>
              <p>
                {plan.persisted === true
                  ? "persisted=true：数据来自已落库的 study_plan_items。"
                  : "响应未带 persisted 字段：GET /api/v1/study-plan 只返回已落库的 study_plan_items 行。"}
                重生成由后端按 dedupe_key 幂等执行，不会删除或改写 done / skipped 的行。
              </p>
              <p>
                <strong className="font-medium text-fg">复习优先于新练习。</strong>
                每日额度先排课程，再排到期复习，最后才排新练习。当日时长较紧时（例如 30 分钟课 + 15 分钟复习正好用满 45 分钟），
                唯一的 15 分钟槽位会被复习占用，因此<strong className="font-medium text-fg">复习密集的周可能没有新练习</strong>——
                这是刻意的：把答错的题再考一次，比多做一道新题更有价值。错题连续通过 3 次后会转为完成，不再占用额度。
              </p>
              <p>
                跳过不会顺延到次日，也不计为失败。done / skipped 是终态，本页不提供撤销；
                expired 只能由「重新生成」复活为待执行。计划完成不等于课程完成或能力等级。
              </p>
            </div>
          </details>

          {plan.persisted === false ? (
            <Alert tone="danger" title="接口返回了 persisted: false">
              <p>
                周计划应来自已落库的 study_plan_items 行；本页不会把未落库的预览当成本周计划，请后端确认。
              </p>
            </Alert>
          ) : null}

          {activeDays.length === 0 ? (
            <EmptyState
              title="本周没有计划任务"
              description="本周还没有生成计划，或没有可排的内容。"
              action={
                <Button
                  variant="secondary"
                  onClick={() => void regenerate()}
                  disabled={generating}
                  aria-disabled={generating}
                >
                  {generating ? "正在生成…" : "重新生成本周计划"}
                </Button>
              }
            />
          ) : (
            <div className="space-y-3">
              {activeDays.map(({ day, budget, counts, exceedsDaily }) => (
                <div key={day.date} className="rounded-control border border-line">
                  <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface px-4 py-2">
                    <p className="flex items-center gap-2 font-mono text-[12px] tabular-nums text-fg">
                      {day.date}
                      <span className="text-[11px] text-muted">
                        {day.weekday === null ? weekdayOfDate(day.date) : weekdayLabel(day.weekday)}
                      </span>
                      <Tag>{String(counts.scheduledItems) + " 待执行"}</Tag>
                      <Tag>{String(counts.historyItems) + " 已完成/已跳过"}</Tag>
                    </p>
                    <p className="font-mono text-[11px] tabular-nums text-muted">
                      待执行 {formatMinutes(budget.scheduledMinutes)} · 历史{" "}
                      {formatMinutes(budget.historyMinutes)} · 合计{" "}
                      {formatMinutes(budget.totalMinutes) + " / 每天可用 " + formatMinutes(dailyMinutes)}
                    </p>
                  </div>
                  {exceedsDaily ? (
                    <p
                      className="border-b border-line px-4 py-2 text-[11px] leading-relaxed text-danger-text"
                      role="status"
                    >
                      {budgetOverLimitNote(budget, dailyMinutes)}
                    </p>
                  ) : null}
                  <ul className="divide-y divide-line">
                    {day.items.map((item, index) => (
                      <PlanItemRow
                        key={item.id}
                        item={item}
                        index={index + 1}
                        actions={itemActions(item)}
                      />
                    ))}
                  </ul>
                </div>
              ))}
            </div>
          )}

        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="阶段级建议"
          description="按六域当前等级给出下一步方向。"
          action={focus ? <Tag tone="accent">建议先投入：{levelLabel(focus.level)}</Tag> : null}
        />
        <CardBody className="space-y-3">
          {focus ? (
            <div className="rounded-control border border-line bg-surface px-3 py-2.5">
              <p className="text-[12px] font-medium text-fg">
                本阶段建议从「
                {DOMAINS.find((domain) => domain.code === focus?.code)?.nameZh ?? focus.code}
                」开始
              </p>
              <p className="mt-1 text-[11px] leading-relaxed text-muted">{stageAdvice(focus)}</p>
            </div>
          ) : null}
          <ul className="divide-y divide-line">
            {DOMAINS.map((domain) => {
              const skill = findSkill(me.skills, domain.code);
              const level = skill ? skill.level : 0;
              return (
                <li key={domain.code} className="py-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-[12px] font-medium text-fg">{domain.nameZh}</span>
                    <Tag>{skill ? levelLabel(skill.level) : "L0 · 未评估"}</Tag>
                    <Tag>{skill ? skill.state : "unassessed"}</Tag>
                  </div>
                  <p className="mt-1 text-[11px] leading-relaxed text-muted">{stageAdvice(skill)}</p>
                  <div className="mt-2 max-w-[280px]">
                    <Meter value={(level / 4) * 100} tone="muted" label={domain.nameZh + " 等级进度"} />
                  </div>
                </li>
              );
            })}
          </ul>
        </CardBody>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Button variant="secondary" onClick={retry}>
          重新读取计划
        </Button>
        <Link
          href="/"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          回到今日
        </Link>
        <Link
          href="/learn"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          课程列表
        </Link>
        <Link
          href="/onboarding"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          修改学习档案
        </Link>
        <Link
          href="/history"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          历史结果
        </Link>
      </div>
    </div>
  );
}
