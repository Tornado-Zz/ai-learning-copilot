"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Meter, Tag } from "@/components/ui";
import { verificationMethodLabel } from "@/lib/exercises";
import {
  AI_INTERACTIONS_PATH,
  aiStatusLabel,
  parseInteractionList,
} from "@/lib/ai-tutor";
import type { AiInteractionRecord } from "@/lib/ai-tutor";
import { formatMinutes } from "@/lib/learning";
import { formatDateTime, levelLabel } from "@/lib/labels";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";

// v0.1.1：本页只渲染 GET /api/v1/progress/overview 的真实聚合，不保留任何演示数字。
// 解析口径：分组缺失 -> null（卡片显示「后端未返回」）；分组内字段缺失 -> null（显示「—」）。
// 页面从不把缺失字段补成 0，也不做本地估算——数字只能来自后端。

const PROGRESS_OVERVIEW_PATH = "/api/v1/progress/overview";

// by_evidence 是 GROUP BY 口径：某个 verification_method 没有行就是 0 条提交，
// 所以固定展示冻结契约列出的三种方式（缺失键按 0 条），其它方法名原样追加。
const EVIDENCE_METHOD_ORDER = ["static_rule", "self_report", "none"];

const DASH = "—";

export type ProgressLessons = {
  total: number | null;
  completed: number | null;
  inProgress: number | null;
  notStarted: number | null;
  minutesCompleted: number | null;
};

export type ProgressPlan = {
  weekStart: string | null;
  scheduled: number | null;
  done: number | null;
  skipped: number | null;
  minutesDone: number | null;
  minutesScheduled: number | null;
};

export type ProgressPractice = {
  exercisesTotal: number | null;
  exercisesAttempted: number | null;
  exercisesPassed: number | null;
  submissionsTotal: number | null;
  byEvidence: Record<string, number | null> | null;
};

export type CapabilityDomain = {
  skillCode: string;
  name: string | null;
  level: number | null;
  source: string | null;
};

export type ProgressCapability = {
  averageLevel: number | null;
  domains: CapabilityDomain[] | null;
};

export type ActivityPoint = {
  date: string;
  minutes: number | null;
};

export type ProgressOverview = {
  lessons: ProgressLessons | null;
  plan: ProgressPlan | null;
  practice: ProgressPractice | null;
  capability: ProgressCapability | null;
  activity: ActivityPoint[] | null;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

// 字段不存在、类型不对都返回 null：调用方必须显示占位，而不是 0。
function readNumber(source: Record<string, unknown> | null, key: string): number | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return null;
  }
  return value;
}

function readText(source: Record<string, unknown> | null, key: string): string | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  if (typeof value !== "string" || value.trim() === "") {
    return null;
  }
  return value;
}

function parseLessons(value: unknown): ProgressLessons | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    total: readNumber(record, "total"),
    completed: readNumber(record, "completed"),
    inProgress: readNumber(record, "in_progress"),
    notStarted: readNumber(record, "not_started"),
    minutesCompleted: readNumber(record, "minutes_completed"),
  };
}

function parsePlan(value: unknown): ProgressPlan | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    weekStart: readText(record, "week_start"),
    scheduled: readNumber(record, "scheduled"),
    done: readNumber(record, "done"),
    skipped: readNumber(record, "skipped"),
    minutesDone: readNumber(record, "minutes_done"),
    minutesScheduled: readNumber(record, "minutes_scheduled"),
  };
}

function parseEvidenceCounts(value: unknown): Record<string, number | null> | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const counts: Record<string, number | null> = {};
  for (const [key, raw] of Object.entries(record)) {
    counts[key] = typeof raw === "number" && Number.isFinite(raw) ? raw : null;
  }
  return counts;
}

function parsePractice(value: unknown): ProgressPractice | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  return {
    exercisesTotal: readNumber(record, "exercises_total"),
    exercisesAttempted: readNumber(record, "exercises_attempted"),
    exercisesPassed: readNumber(record, "exercises_passed"),
    submissionsTotal: readNumber(record, "submissions_total"),
    byEvidence: parseEvidenceCounts(record.by_evidence),
  };
}

function parseDomain(value: unknown): CapabilityDomain | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const skillCode = readText(record, "skill_code");
  if (skillCode === null) {
    // 缺 skill_code 的行无法定位到能力域，直接跳过，不编造编码。
    return null;
  }
  return {
    skillCode,
    name: readText(record, "name"),
    level: readNumber(record, "level"),
    source: readText(record, "source"),
  };
}

function parseCapability(value: unknown): ProgressCapability | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const rawDomains = record.domains;
  let domains: CapabilityDomain[] | null = null;
  if (Array.isArray(rawDomains)) {
    domains = [];
    for (const item of rawDomains) {
      const domain = parseDomain(item);
      if (domain) {
        domains.push(domain);
      }
    }
  }
  return { averageLevel: readNumber(record, "average_level"), domains };
}

function parseActivity(value: unknown): ActivityPoint[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const points: ActivityPoint[] = [];
  for (const item of value) {
    const record = asRecord(item);
    if (!record) {
      continue;
    }
    const date = readText(record, "date");
    if (date === null) {
      continue;
    }
    points.push({ date, minutes: readNumber(record, "minutes") });
  }
  return points;
}

export function parseProgressOverview(body: unknown): ProgressOverview | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  return {
    lessons: parseLessons(record.lessons),
    plan: parsePlan(record.plan),
    practice: parsePractice(record.practice),
    capability: parseCapability(record.capability),
    activity: parseActivity(record.activity),
  };
}

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; overview: ProgressOverview };

function numberText(value: number | null): string {
  return value === null ? DASH : String(value);
}

function minutesText(value: number | null): string {
  return value === null ? DASH : formatMinutes(value);
}

function averageText(value: number | null): string {
  return value === null ? DASH : value.toFixed(1);
}

// 分母为 0 或缺失时不画进度条：0 课时的「完成率」没有意义，画出来就是假数据。
function ratioPercent(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null || denominator <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, (numerator / denominator) * 100));
}

function shortDate(date: string): string {
  return date.length >= 10 ? date.slice(5) : date;
}

// 只有一组数据都明确为 0 / 空数组时才算空态；任何 null 都表示「后端没给」，不当作空。
function isEmptyOverview(overview: ProgressOverview): boolean {
  const lessonsEmpty = overview.lessons !== null && overview.lessons.total === 0;
  const planEmpty = overview.plan !== null && overview.plan.scheduled === 0;
  const practiceEmpty = overview.practice !== null && overview.practice.submissionsTotal === 0;
  const capabilityEmpty =
    overview.capability !== null &&
    overview.capability.domains !== null &&
    overview.capability.domains.length === 0;
  const activityEmpty = overview.activity !== null && overview.activity.length === 0;
  return lessonsEmpty && planEmpty && practiceEmpty && capabilityEmpty && activityEmpty;
}

// verification_method 的已知取值沿用 lib/exercises 的中文说明；契约里的 none 表示没有判定方式，
// 其余未知值原样显示（不折叠成默认文案，也不隐藏）。
function evidenceMethodLabel(method: string): string {
  if (method === "none") {
    return "未验证（none）";
  }
  return verificationMethodLabel(method);
}

function evidenceRows(
  counts: Record<string, number | null>,
): Array<{ method: string; count: number | null }> {
  const rows: Array<{ method: string; count: number | null }> = EVIDENCE_METHOD_ORDER.map(
    (method) => ({ method, count: counts[method] ?? 0 }),
  );
  for (const [method, count] of Object.entries(counts)) {
    if (!EVIDENCE_METHOD_ORDER.includes(method)) {
      rows.push({ method, count });
    }
  }
  return rows;
}

function sumKnownMinutes(points: ActivityPoint[]): number | null {
  let total = 0;
  for (const point of points) {
    if (point.minutes === null) {
      return null;
    }
    total += point.minutes;
  }
  return total;
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-control border border-line bg-surface px-3 py-2">
      <p className="text-[11px] text-muted">{label}</p>
      <p className="mt-1 font-mono text-[15px] font-semibold text-fg">{value}</p>
    </div>
  );
}

function MissingGroup({ name }: { name: string }) {
  return (
    <p className="text-[11px] leading-relaxed text-muted">
      后端本次没有返回 <span className="font-mono text-fg">{name}</span>{" "}
      分组，本卡不做任何补值。
    </p>
  );
}

export function ProgressView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  // AI 导师的调用台账：后端一直有这个接口，前端有路径与解析器但从未调用过。
  // 课程里讲「token 是计费单位」，这里是它变成真实数字的地方。
  const [aiCalls, setAiCalls] = useState<AiInteractionRecord[] | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const [result, callsResult] = await Promise.all([
        apiRequest<ProgressOverview>(PROGRESS_OVERVIEW_PATH, { parse: parseProgressOverview }),
        apiRequest<AiInteractionRecord[]>(AI_INTERACTIONS_PATH + "?limit=10", {
          parse: parseInteractionList,
        }),
      ]);
      if (!active) {
        return;
      }
      // 台账失败不影响进度页：它只是补充信息，null 表示「没拿到」，页面写清楚而不是显示空表。
      setAiCalls(callsResult.ok ? callsResult.data : null);
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", overview: result.data });
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
        title="正在读取学习进度"
        description="GET /api/v1/progress/overview 是课程、计划、练习与能力等级的唯一数据来源。"
        rows={6}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="学习进度加载失败"
        onRetry={retry}
        extra={<p>读取失败时不展示任何估算值或缓存数字，避免把旧数据当成当前进度。</p>}
      />
    );
  }

  const overview = state.overview;

  if (isEmptyOverview(overview)) {
    return (
      <EmptyState
        title="还没有可统计的学习数据"
        description="后端确实读到了空数据：课程与计划计数为 0、没有提交记录、还没有能力等级。完成一节课或提交一次练习后回到本页。"
        action={
          <Button variant="secondary" onClick={retry}>
            重新读取
          </Button>
        }
      />
    );
  }

  const { lessons, plan, practice, capability, activity } = overview;
  const lessonRatio = lessons ? ratioPercent(lessons.completed, lessons.total) : null;
  const planRatio = plan ? ratioPercent(plan.minutesDone, plan.minutesScheduled) : null;
  const activityMax = activity ? Math.max(1, ...activity.map((point) => point.minutes ?? 0)) : 1;
  const activityTotal = activity ? sumKnownMinutes(activity) : null;

  return (
    <div className="space-y-6">
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader
            title="课程进度"
            description="lessons：已完成课程的 estimated_minutes 合计为已完成时长。"
            action={<Tag>{lessons === null ? "未返回" : "真实聚合"}</Tag>}
          />
          <CardBody className="space-y-4">
            {lessons === null ? (
              <MissingGroup name="lessons" />
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Metric label="总课程" value={numberText(lessons.total)} />
                  <Metric label="已完成" value={numberText(lessons.completed)} />
                  <Metric label="进行中" value={numberText(lessons.inProgress)} />
                  <Metric label="未开始" value={numberText(lessons.notStarted)} />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between text-[11px] text-muted">
                    <span>完成率</span>
                    <span className="font-mono text-fg">
                      {lessonRatio === null ? DASH : String(Math.round(lessonRatio)) + "%"}
                    </span>
                  </div>
                  {lessonRatio === null ? null : <Meter value={lessonRatio} label="课程完成率" />}
                </div>
                <p className="text-[11px] leading-relaxed text-muted">
                  已完成课程时长合计{" "}
                  <span className="font-mono text-fg">{minutesText(lessons.minutesCompleted)}</span>
                </p>
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="本周计划"
            description="plan：本周（按 users.timezone 计算的周一）全部 study_plan_items，不限 kind。"
            action={<Tag>{plan === null ? "未返回" : plan.weekStart ?? "周起始缺失"}</Tag>}
          />
          <CardBody className="space-y-4">
            {plan === null ? (
              <MissingGroup name="plan" />
            ) : (
              <>
                <p className="text-[11px] leading-relaxed text-muted">
                  本周起始{" "}
                  <span className="font-mono text-fg">{plan.weekStart ?? DASH}</span>
                </p>
                <div className="grid grid-cols-3 gap-2">
                  <Metric label="已排期" value={numberText(plan.scheduled)} />
                  <Metric label="已完成" value={numberText(plan.done)} />
                  <Metric label="已跳过" value={numberText(plan.skipped)} />
                </div>
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-3 text-[11px] text-muted">
                    <span>分钟（完成 / 排期）</span>
                    <span className="font-mono text-fg">
                      {minutesText(plan.minutesDone)} / {minutesText(plan.minutesScheduled)}
                    </span>
                  </div>
                  {planRatio === null ? null : (
                    <Meter value={planRatio} tone="muted" label="本周计划分钟完成率" />
                  )}
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="练习与证据"
            description="practice：按 submissions.verification_method 分组计数，不做任何加权。"
            action={<Tag>{practice === null ? "未返回" : "真实聚合"}</Tag>}
          />
          <CardBody className="space-y-4">
            {practice === null ? (
              <MissingGroup name="practice" />
            ) : (
              <>
                <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                  <Metric label="练习总数" value={numberText(practice.exercisesTotal)} />
                  <Metric label="已作答" value={numberText(practice.exercisesAttempted)} />
                  <Metric label="已通过" value={numberText(practice.exercisesPassed)} />
                  <Metric label="提交次数" value={numberText(practice.submissionsTotal)} />
                </div>
                <div className="space-y-2">
                  <p className="text-[11px] font-medium text-fg">按判定方式（verification_method）</p>
                  {practice.byEvidence === null ? (
                    <p className="text-[11px] leading-relaxed text-muted">
                      后端未返回 by_evidence 分组，这里不按 0 显示。
                    </p>
                  ) : (
                    <ul className="space-y-2">
                      {evidenceRows(practice.byEvidence).map((row) => (
                        <li
                          key={row.method}
                          className="flex items-center justify-between gap-3 border-b border-line pb-2 last:border-b-0 last:pb-0"
                        >
                          <span className="min-w-0 text-[12px] text-muted">
                            {evidenceMethodLabel(row.method)}
                          </span>
                          <span className="shrink-0 font-mono text-[12px] text-fg">
                            {numberText(row.count)}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              </>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="能力等级"
            description="capability：user_skill_levels.level 的算术平均，domains 关联 skills.name。"
            action={<Tag>{capability === null ? "未返回" : "真实聚合"}</Tag>}
          />
          <CardBody className="space-y-3">
            {capability === null ? (
              <MissingGroup name="capability" />
            ) : (
              <>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-3">
                  <span className="text-[12px] text-muted">平均等级</span>
                  <span className="font-mono text-[15px] font-semibold text-fg">
                    {averageText(capability.averageLevel)}
                  </span>
                </div>
                {capability.domains === null ? (
                  <p className="text-[11px] leading-relaxed text-muted">
                    后端未返回 domains 数组，这里不按空列表显示。
                  </p>
                ) : capability.domains.length === 0 ? (
                  <p className="text-[11px] leading-relaxed text-muted">
                    还没有任何能力域记录；完成一次诊断后这里会出现真实等级。
                  </p>
                ) : (
                  <ul className="space-y-2">
                    {capability.domains.map((domain, index) => (
                      <li
                        key={domain.skillCode + String(index)}
                        className="flex flex-wrap items-center justify-between gap-2 border-b border-line pb-2 last:border-b-0 last:pb-0"
                      >
                        <div className="min-w-0">
                          <p className="text-[12px] font-medium text-fg">
                            {domain.name ?? domain.skillCode}
                          </p>
                          <p className="mt-0.5 font-mono text-[10px] text-muted">
                            {domain.skillCode}
                            {domain.source === null ? "" : " · " + domain.source}
                          </p>
                        </div>
                        <span className="shrink-0 font-mono text-[11px] text-fg">
                          {domain.level === null ? DASH : levelLabel(domain.level)}
                        </span>
                      </li>
                    ))}
                  </ul>
                )}
              </>
            )}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="最近 7 天活动"
          description="activity：study_plan_items 中 status=done 的 planned_minutes 按日期求和，缺失日期由后端补 0。"
          action={
            <Tag>
              {activity === null ? "未返回" : "合计 " + minutesText(activityTotal)}
            </Tag>
          }
        />
        <CardBody>
          {activity === null ? (
            <MissingGroup name="activity" />
          ) : activity.length === 0 ? (
            <p className="text-[11px] leading-relaxed text-muted">
              近 7 天没有已完成的计划任务。
            </p>
          ) : (
            <ul className="flex items-end gap-2">
              {activity.map((point) => (
                <li key={point.date} className="flex min-w-0 flex-1 flex-col items-center gap-1.5">
                  <span className="font-mono text-[10px] text-muted">
                    {point.minutes === null ? DASH : String(point.minutes)}
                  </span>
                  <div className="flex h-24 w-full items-end rounded-control bg-elevated">
                    {point.minutes === null ? (
                      <div className="h-px w-full bg-line-strong" aria-hidden="true" />
                    ) : (
                      <div
                        className="w-full rounded-control bg-accent"
                        style={{ height: String(Math.round((point.minutes / activityMax) * 100)) + "%" }}
                        role="img"
                        aria-label={point.date + " 完成 " + String(point.minutes) + " 分钟"}
                      />
                    )}
                  </div>
                  <span className="font-mono text-[10px] text-muted">{shortDate(point.date)}</span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="AI 导师调用"
          description="GET /api/v1/ai/interactions 的最近 10 条：课程里讲「token 是计费单位」，这里是真实数字。"
          action={<Tag>{aiCalls === null ? "未返回" : String(aiCalls.length) + " 条"}</Tag>}
        />
        <CardBody>
          {aiCalls === null ? (
            <p className="text-[11px] leading-relaxed text-muted">
              接口没有返回调用记录（可能未配置模型密钥，或还没有提问过）。
            </p>
          ) : aiCalls.length === 0 ? (
            <p className="text-[11px] leading-relaxed text-muted">
              还没有向 AI 导师提问过。在课程或练习页底部展开「AI 导师」提问，这里会出现每一次调用的
              token 与状态。
            </p>
          ) : (
            <ul className="divide-y divide-line">
              {aiCalls.map((call, index) => (
                <li
                  key={call.interactionId ?? String(index)}
                  className="flex flex-wrap items-center justify-between gap-2 py-2 text-[11px] first:pt-0 last:pb-0"
                >
                  <span className="font-mono tabular-nums text-muted">
                    {call.createdAt === null ? DASH : formatDateTime(call.createdAt)}
                  </span>
                  <span className="text-muted">{call.model || DASH}</span>
                  <span className="text-muted">{call.assistanceLevel || DASH}</span>
                  <span className="font-mono tabular-nums text-fg">
                    {call.totalTokens === null ? DASH : String(call.totalTokens) + " tokens"}
                  </span>
                  <span className="text-muted">{aiStatusLabel(call.status)}</span>
                </li>
              ))}
            </ul>
          )}
        </CardBody>
      </Card>

      <p className="text-[11px] leading-relaxed text-muted">
        「{DASH}」表示本次响应没有该字段：页面不补零、不估算、不沿用上一次的数字。
      </p>
    </div>
  );
}
