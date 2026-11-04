#!/usr/bin/env node
// Sprint 2 Patch 前端校验脚本（无第三方依赖，直接 node 运行）：
//   node apps/web/scripts/plan-rules-check.mjs
//
// 断言三件事：
//   1) S1 按钮可见性：只有 status='scheduled' 的行有「标记完成 / 跳过」；
//      done / skipped / expired 一律只读，且不存在任何写回 'scheduled' 的路径（撤销已删除）。
//   2) A3 预算语义：待执行工作量（scheduled）与当日已分配预算（total = scheduled + history）分开统计；
//      历史终态分钟计入当日已分配预算，total_minutes <= daily_minutes 只在生成时成立、事后可能超限；
//      文案不得出现与「历史终态仍计入当日已分配预算」相反的表述，也不得宣称 total 恒不超过 daily。
//   3) 页面源码层：计划页不再出现「撤销」与任何非法目标状态字面量，且超限提示走 budgetOverLimitNote。

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

// 直接导入生产代码（未编译的 .ts），断言的就是页面真正调用的那套规则；
// Node >= 22.6 默认剥离类型，低版本会在这里给出明确失败信息而不是静默跳过。
let rules;
try {
  rules = await import("../src/lib/plan-rules.ts");
} catch (error) {
  console.log("FAIL 无法导入 src/lib/plan-rules.ts（需要 Node >= 22.6 的 TS 类型剥离）");
  throw error;
}
const {
  BUDGET_SCOPE_NOTE,
  PLAN_ITEM_ACTION_STATUS,
  budgetExceedsDailyMinutes,
  budgetOverLimitNote,
  isTerminalPlanStatus,
  planItemActions,
  planItemReadOnlyNote,
  resolveDayBudget,
  resolvePlanCounts,
} = rules;

const here = dirname(fileURLToPath(import.meta.url));
const passed = [];
const failed = [];

function assertEqual(label, actual, expected) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    throw new Error(label + "：期望 " + e + "，实际 " + a);
  }
}

function assertTrue(label, value) {
  if (!value) {
    throw new Error(label);
  }
}

function check(name, fn) {
  try {
    const detail = fn();
    passed.push(name);
    console.log("PASS " + String(passed.length) + ". " + name + (detail ? " — " + detail : ""));
  } catch (error) {
    failed.push(name);
    console.log("FAIL " + name + " — " + error.message);
  }
}

// ---------- S1：按钮可见性规则 ----------
check("scheduled 行渲染「标记完成 / 跳过」两个按钮", () => {
  assertEqual("planItemActions('scheduled')", planItemActions("scheduled"), ["complete", "skip"]);
  return "complete + skip";
});

check("done / skipped 是终态：零按钮", () => {
  for (const status of ["done", "skipped"]) {
    assertEqual("planItemActions('" + status + "')", planItemActions(status), []);
    assertTrue(status + " 必须是终态", isTerminalPlanStatus(status));
    assertTrue(status + " 必须给出只读文案", (planItemReadOnlyNote(status) ?? "").length > 0);
  }
  return "done / skipped 只读";
});

check("done 行文案注明「计划完成不等于课程完成或能力等级」", () => {
  const note = planItemReadOnlyNote("done") ?? "";
  assertTrue("done 文案缺失该澄清", note.includes("计划完成不等于课程完成或能力等级"));
  return note;
});

check("expired 行零按钮、只能由重新生成复活", () => {
  assertEqual("planItemActions('expired')", planItemActions("expired"), []);
  assertTrue("expired 不是终态（可被重生成复活）", isTerminalPlanStatus("expired") === false);
  assertTrue("expired 文案必须指向重新生成", (planItemReadOnlyNote("expired") ?? "").includes("重新生成"));
  return "expired 只读";
});

check("可写目标状态只有 done / skipped，不存在撤销（scheduled）", () => {
  assertEqual("PLAN_ITEM_ACTION_STATUS", PLAN_ITEM_ACTION_STATUS, {
    complete: "done",
    skip: "skipped",
  });
  const targets = Object.values(PLAN_ITEM_ACTION_STATUS);
  assertTrue("目标状态里出现 scheduled，等于恢复了撤销语义", targets.indexOf("scheduled") < 0);
  assertTrue("目标状态里出现 expired，越权复活", targets.indexOf("expired") < 0);
  return targets.join(" / ");
});

// ---------- S5：预算展示拆分 ----------
const mixedItems = [
  { status: "done", plannedMinutes: 30 },
  { status: "skipped", plannedMinutes: 20 },
  { status: "scheduled", plannedMinutes: 45 },
  { status: "expired", plannedMinutes: 15 },
];

check("预算拆分：历史量不计入待执行", () => {
  const budget = resolveDayBudget({}, mixedItems);
  assertEqual("budget", budget, { scheduledMinutes: 45, historyMinutes: 50, totalMinutes: 95 });
  assertTrue("待执行被写成了含历史的合计", budget.scheduledMinutes !== 95);
  return "待执行 45 / 历史 50 / 合计 95";
});

check("expired 行既不进待执行也不进历史", () => {
  const budget = resolveDayBudget({}, mixedItems);
  assertTrue("expired 的 15 分钟混进了预算", budget.scheduledMinutes + budget.historyMinutes === 95);
  return "45 + 50 = 95（不含 expired 15）";
});

check("后端给出 days[] 预算字段时按原值展示", () => {
  const budget = resolveDayBudget(
    { scheduledMinutes: 40, historyMinutes: 55, totalMinutes: 90 },
    mixedItems,
  );
  assertEqual("budget", budget, { scheduledMinutes: 40, historyMinutes: 55, totalMinutes: 90 });
  return "接口值优先，不在前端重算";
});

check("A3 越界检测：total_minutes 超过 daily_minutes 时告警（生成后调小额度即可能发生）", () => {
  const ok = resolveDayBudget({}, mixedItems);
  assertTrue("95 <= 120 不应告警", budgetExceedsDailyMinutes(ok, 120) === false);
  const over = resolveDayBudget({ scheduledMinutes: 45, historyMinutes: 50, totalMinutes: 130 }, []);
  assertTrue("130 > 120 必须告警", budgetExceedsDailyMinutes(over, 120) === true);
  assertTrue("daily 未知时不误报", budgetExceedsDailyMinutes(over, 0) === false);
  return "越界只提示、不静默截断";
});

check("顶层计数拆分：scheduled_items / history_items", () => {
  assertEqual("counts", resolvePlanCounts({}, mixedItems), { scheduledItems: 1, historyItems: 2 });
  assertEqual(
    "counts（接口值优先）",
    resolvePlanCounts({ scheduledItems: 3, historyItems: 4 }, mixedItems),
    { scheduledItems: 3, historyItems: 4 },
  );
  return "待执行 1 项 / 历史 2 项";
});

// A3：文案断言不能只看关键字，要断言语义与生成算法一致（算法确实把 done/skipped 分钟从当日额度扣除）。
// 矛盾表述用 join 拼出来：本文件是「断言脚本」而不是文案，拼写后运行时的被测字符串与全局 grep 的口径一致，
// 这样全局 grep 这些矛盾措辞为 0 时，就等于「仓库里没有任何地方真的写出这句话」。
const CONTRADICTORY_PHRASES = [
  ["不再", "占用"].join(""),
  ["恒", "小于等于"].join(""),
  ["恒", " <="].join(""),
  ["恒", "<="].join(""),
  ["由后端", "保证"].join(""),
  ["恒", "成立"].join(""),
];
const REQUIRED_NOTE_SEMANTICS = [
  "待执行工作量",
  "当日已分配预算",
  "计入当日已分配预算",
  "新排课额度",
  "历史分钟",
  "仅在生成时成立",
  "可能超限",
];

check("预算口径文案语义：历史终态计入当日已分配预算、仅生成时成立、事后可能超限", () => {
  for (const phrase of REQUIRED_NOTE_SEMANTICS) {
    assertTrue("文案缺少语义串「" + phrase + "」", BUDGET_SCOPE_NOTE.includes(phrase));
  }
  for (const phrase of CONTRADICTORY_PHRASES) {
    assertTrue("文案含与生成算法矛盾的表述「" + phrase + "」", BUDGET_SCOPE_NOTE.includes(phrase) === false);
  }
  assertTrue("文案未说明新排课额度 = daily_minutes − 历史分钟", BUDGET_SCOPE_NOTE.includes("daily_minutes − 历史分钟"));
  return String(REQUIRED_NOTE_SEMANTICS.length) + " 个必需语义串齐备、" + String(CONTRADICTORY_PHRASES.length) + " 个矛盾表述为 0";
});

check("超限提示文案：说明 total 超额度、历史已占用、来源是调小额度（不是接口违约）", () => {
  const note = budgetOverLimitNote({ scheduledMinutes: 45, historyMinutes: 50, totalMinutes: 130 }, 120);
  assertTrue("未给出 actual/limit 数值", note.includes("130") && note.includes("120"));
  assertTrue("未说明历史计入当日已分配预算", note.includes("计入当日已分配预算"));
  assertTrue("未说明仅在生成时成立", note.includes("仅在生成"));
  assertTrue("未说明事后可能超限", note.includes("可能超限"));
  for (const phrase of CONTRADICTORY_PHRASES) {
    assertTrue("超限提示含矛盾表述「" + phrase + "」", note.includes(phrase) === false);
  }
  return note.slice(0, 12) + "…";
});

// ---------- 页面源码层 ----------
const planViewPath = join(here, "..", "src", "app", "plan", "plan-view.tsx");
const planView = readFileSync(planViewPath, "utf8");

check("计划页不再出现「撤销」按钮，也没有写回 scheduled 的路径", () => {
  // 「撤销」只允许出现在解释性文案里；任何 <Button>…撤销…</Button> 都算回退。
  const buttons = planView.match(/<Button[\s\S]*?<\/Button>/g) ?? [];
  const offenders = buttons.filter((block) => block.includes("撤销"));
  assertTrue("仍有 Button 渲染「撤销」", offenders.length === 0);
  assertTrue("仍有 updateStatus(item, \"scheduled\") 调用", planView.includes('updateStatus(item, "scheduled")') === false);
  assertTrue("仍有 status: \"scheduled\" 请求体", planView.includes('status: "scheduled"') === false);
  const labelBlock = planView.slice(
    planView.indexOf("const ACTION_LABEL"),
    planView.indexOf("type ViewState"),
  );
  assertTrue("ACTION_LABEL 里出现了撤销", labelBlock.length > 0 && labelBlock.includes("撤销") === false);
  return "<Button> 数量 " + String(buttons.length) + "，撤销按钮 0";
});

check("计划页按钮可见性只由 planItemActions 决定", () => {
  assertTrue("未导入 planItemActions", planView.includes("planItemActions"));
  assertTrue("未按 planItemActions 决定按钮", planView.includes("planItemActions(item.status)"));
  assertTrue("缺少 actions={itemActions(item)} 渲染", planView.includes("actions={itemActions(item)}"));
  assertTrue("PATCH 目标状态未走 PLAN_ITEM_ACTION_STATUS", planView.includes("PLAN_ITEM_ACTION_STATUS[action]"));
  return "单一来源 lib/plan-rules";
});

const lessonViewPath = join(here, "..", "src", "app", "learn", "[id]", "lesson-detail-view.tsx");
const lessonView = readFileSync(lessonViewPath, "utf8");

check("课程页对非 not_started 的课程不渲染「开始学习」", () => {
  const gate = lessonView.indexOf('{progressStatus === "not_started" ? (');
  const startLabel = lessonView.indexOf("开始学习");
  assertTrue("缺少 progressStatus === 'not_started' 的门控", gate >= 0);
  assertTrue("「开始学习」出现在门控之外", startLabel > gate);
  return "已完成 / 学习中都没有回退入口";
});

check("课程页写进度前有前进方向守卫（非法操作不发请求）", () => {
  assertTrue("缺少 in_progress 守卫", lessonView.includes('next === "in_progress" &&'));
  assertTrue("守卫未比对当前状态", lessonView.includes('state.lesson.progress.status !== "not_started"'));
  return "not_started 之外不发 in_progress";
});

check("计划页分别渲染 scheduled / history 分钟数", () => {
  assertTrue("未使用 resolveDayBudget", planView.includes("resolveDayBudget("));
  assertTrue("未渲染待执行分钟数", planView.includes("budget.scheduledMinutes"));
  assertTrue("未渲染历史分钟数", planView.includes("budget.historyMinutes"));
  assertTrue("未渲染预算口径文案", planView.includes("BUDGET_SCOPE_NOTE"));
  return "待执行 / 历史 分开渲染";
});

check("计划页三分栏保留，超限时渲染 budgetOverLimitNote 提示（不静默截断）", () => {
  assertTrue("未按 budgetExceedsDailyMinutes 判定越界", planView.includes("budgetExceedsDailyMinutes(budget, dailyMinutes)"));
  assertTrue("超限分支未渲染 budgetOverLimitNote", planView.includes("budgetOverLimitNote(budget, dailyMinutes)"));
  assertTrue("三分栏提示行缺失", planView.includes("formatMinutes(budget.totalMinutes)") && planView.includes("formatMinutes(dailyMinutes)"));
  for (const phrase of CONTRADICTORY_PHRASES) {
    assertTrue("计划页出现矛盾表述「" + phrase + "」", planView.includes(phrase) === false);
  }
  assertTrue("计划页仍把越界归咎于 API 口径", planView.includes("请在 API 侧核对预算口径") === false);
  assertTrue("计划页仍断言后端保证不超过额度", planView.includes("后端返回的 total_minutes 超过 daily_minutes") === false);
  return "越界提示走共享文案";
});

const total = passed.length + failed.length;
if (failed.length > 0) {
  console.log("");
  console.log("FAILED " + String(failed.length) + "/" + String(total) + " 项断言未通过");
  throw new Error("plan-rules-check 失败：" + failed.join("；"));
}
console.log("");
console.log("PASS " + String(total) + "/" + String(total) + " 项断言全部通过（按钮可见性 + A3 预算语义 + 页面渲染）");
