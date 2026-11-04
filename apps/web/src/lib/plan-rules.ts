// 冻结语义 S1 / S2 / S5 的前端纯规则：计划项操作可见性 + 每日预算拆分。
// 本文件不引入任何依赖（连 @/ 别名都不用），因此 node 可以直接 import 断言：
//   node apps/web/scripts/plan-rules-check.mjs
// 页面只允许通过这些函数决定「显示什么按钮 / 展示哪个分钟数」，不要在 JSX 里另写一套判断。

export type PlanItemStatus = "scheduled" | "done" | "skipped" | "expired";

// PATCH /study-plan/items/{id} 的合法目标状态只有 done / skipped：
// 不存在「撤销」——scheduled 只能由重新生成写入，expired 只能由重新生成复活。
export type PlanItemAction = "complete" | "skip";

export const PLAN_ITEM_ACTION_STATUS: Record<PlanItemAction, PlanItemStatus> = {
  complete: "done",
  skip: "skipped",
};

// S1：done / skipped 是终态，任何路径都不得改写；expired 只能被「重新生成」复活。
export function isTerminalPlanStatus(status: PlanItemStatus): boolean {
  return status === "done" || status === "skipped";
}

// S1：只有 scheduled 行可写。终态与 expired 行在 UI 上必须只读，不得出现会失败的操作按钮。
export function planItemActions(status: PlanItemStatus): PlanItemAction[] {
  return status === "scheduled" ? ["complete", "skip"] : [];
}

// 终态 / expired 行的只读说明：用文案承担风险提示，而不是把按钮灰着摆在那里。
export function planItemReadOnlyNote(status: PlanItemStatus): string | null {
  if (status === "done") {
    return "已完成（终态只读）；计划完成不等于课程完成或能力等级。";
  }
  if (status === "skipped") {
    return "已跳过（终态只读）；不会顺延到次日，也不能撤销。";
  }
  if (status === "expired") {
    return "已过期；只有「重新生成」可以把它复活为待执行，本页不提供改写操作。";
  }
  return null;
}

export type PlanItemLike = {
  status: PlanItemStatus;
  plannedMinutes: number;
};

export type DayBudget = {
  scheduledMinutes: number;
  historyMinutes: number;
  totalMinutes: number;
};

function toMinutes(value: number | null | undefined): number | null {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return Math.max(0, Math.round(value));
}

// S5：days[] 必须分别给出 scheduled_minutes（待执行）与 history_minutes（done+skipped）。
// 后端给了数值就直接采用；字段缺失时按行状态汇总同一口径（不猜、不做本地乐观改写）。
// 历史量永远不计入待执行——这是本函数的唯一目的。
export function resolveDayBudget(
  raw: {
    scheduledMinutes?: number | null;
    historyMinutes?: number | null;
    totalMinutes?: number | null;
  },
  items: PlanItemLike[],
): DayBudget {
  let scheduled = toMinutes(raw.scheduledMinutes);
  let history = toMinutes(raw.historyMinutes);
  if (scheduled === null || history === null) {
    let scheduledSum = 0;
    let historySum = 0;
    for (const item of items) {
      if (item.status === "scheduled") {
        scheduledSum += item.plannedMinutes;
      } else if (isTerminalPlanStatus(item.status)) {
        historySum += item.plannedMinutes;
      }
    }
    if (scheduled === null) {
      scheduled = Math.max(0, Math.round(scheduledSum));
    }
    if (history === null) {
      history = Math.max(0, Math.round(historySum));
    }
  }
  const total = toMinutes(raw.totalMinutes) ?? scheduled + history;
  return { scheduledMinutes: scheduled, historyMinutes: history, totalMinutes: total };
}

export type PlanCounts = { scheduledItems: number; historyItems: number };

// 顶层 scheduled_items / history_items：缺字段时同样按行状态计数。
export function resolvePlanCounts(
  raw: { scheduledItems?: number | null; historyItems?: number | null },
  items: PlanItemLike[],
): PlanCounts {
  let scheduled = toMinutes(raw.scheduledItems);
  let history = toMinutes(raw.historyItems);
  if (scheduled === null || history === null) {
    let scheduledCount = 0;
    let historyCount = 0;
    for (const item of items) {
      if (item.status === "scheduled") {
        scheduledCount += 1;
      } else if (isTerminalPlanStatus(item.status)) {
        historyCount += 1;
      }
    }
    if (scheduled === null) {
      scheduled = scheduledCount;
    }
    if (history === null) {
      history = historyCount;
    }
  }
  return { scheduledItems: scheduled, historyItems: history };
}

// A3：total_minutes <= daily_minutes 只由「生成那一刻」的算法保证（新排课额度 = daily_minutes − 历史分钟）。
// 用户事后调小 daily_minutes，该日 total 就可能超过新额度——这是预期内的状态，不是接口违约。
// 因此越界必须如实提示：不静默截断、不改写接口数据、也不宣称该不变式恒成立。
export function budgetExceedsDailyMinutes(budget: DayBudget, dailyMinutes: number): boolean {
  if (!Number.isFinite(dailyMinutes) || dailyMinutes <= 0) {
    return false;
  }
  return budget.totalMinutes > dailyMinutes;
}

// 超限提示文案：页面与脚本共用同一句，避免两处措辞漂移。
export function budgetOverLimitNote(budget: DayBudget, dailyMinutes: number): string {
  return (
    "当日已分配预算 " +
    String(budget.totalMinutes) +
    " 分钟已超过当前每日额度 " +
    String(dailyMinutes) +
    " 分钟（待执行 " +
    String(budget.scheduledMinutes) +
    " + 历史终态 " +
    String(budget.historyMinutes) +
    "）。历史终态（done/skipped）分钟仍计入当日已分配预算，total_minutes <= daily_minutes 仅在生成那一刻成立；" +
    "调小每日额度后该日就可能超限，本页按接口原样展示并提示，不截断已排内容。"
  );
}

// A3 预算口径说明文案：页面与脚本共用同一句，避免两处措辞漂移。
// 两个口径必须分开读：待执行工作量 = scheduled_minutes；当日已分配预算 = total_minutes = scheduled + history。
export const BUDGET_SCOPE_NOTE =
  "「待执行工作量」= status='scheduled' 行的 planned_minutes 之和（scheduled_minutes）；" +
  "「当日已分配预算」= total_minutes = scheduled_minutes + history_minutes（done+skipped 的合计）。" +
  "历史终态（done/skipped）分钟仍计入当日已分配预算，所以生成时的新排课额度 = daily_minutes − 历史分钟；" +
  "total_minutes <= daily_minutes 仅在生成时成立，用户事后调小 daily_minutes 时该日 total 可能超限，页面会显示超限提示。";
