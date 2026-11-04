"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Meter, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";

// v0.1.1：结业作品页只读 GET /api/v1/capstone/readiness，前端不重算、不补字段、不改写 note。
//
// 四条判定口径全部在服务端用真实数据推导，注释与代码一一对应（前端只负责展示）：
// 1) lessons_completed：课程进度里 status = completed 的课程数，required 为全部课程数；
// 2) exercises_passed：submissions.is_passed = true 的 exercise 去重计数（同一道题多次通过只算一次）；
// 3) domains_at_l2：user_skill_levels.level >= 2 的能力域数量（同一 skill_code 只算一个域）；
// 4) plan_items_done：study_plan_items.status = 'done' 的行数，跨周累计。
// ready = 四条 met 全为 true。作品提交与人工评审流程在 v0.1.x 尚未实现，
// 因此页面原样显示后端 note，不给出任何评审结论或提交入口。

const READINESS_PATH = "/api/v1/capstone/readiness";
const DASH = "—";

export type ReadinessRequirement = {
  key: string;
  label: string | null;
  required: number | null;
  actual: number | null;
  met: boolean | null;
};

export type CapstoneReadiness = {
  ready: boolean | null;
  requirements: ReadinessRequirement[] | null;
  note: string | null;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}

// 字段缺失一律返回 null：调用方显示占位，而不是把「没给」写成 0 / false。
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

function readBoolean(source: Record<string, unknown> | null, key: string): boolean | null {
  if (!source) {
    return null;
  }
  const value = source[key];
  return typeof value === "boolean" ? value : null;
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

function parseRequirement(value: unknown): ReadinessRequirement | null {
  const record = asRecord(value);
  if (!record) {
    return null;
  }
  const key = readText(record, "key");
  if (key === null) {
    // 缺 key 的行无法稳定渲染列表（也无法定位），直接跳过，不编造 key。
    return null;
  }
  return {
    key,
    label: readText(record, "label"),
    required: readNumber(record, "required"),
    actual: readNumber(record, "actual"),
    met: readBoolean(record, "met"),
  };
}

function parseRequirements(value: unknown): ReadinessRequirement[] | null {
  if (!Array.isArray(value)) {
    return null;
  }
  const rows: ReadinessRequirement[] = [];
  for (const item of value) {
    const row = parseRequirement(item);
    if (row) {
      rows.push(row);
    }
  }
  return rows;
}

export function parseCapstoneReadiness(body: unknown): CapstoneReadiness | null {
  const record = asRecord(body);
  if (!record) {
    return null;
  }
  return {
    ready: readBoolean(record, "ready"),
    requirements: parseRequirements(record.requirements),
    note: readText(record, "note"),
  };
}

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; readiness: CapstoneReadiness };

function numberText(value: number | null): string {
  return value === null ? DASH : String(value);
}

// required 为 0 或缺失时不画进度条：分母不存在时「完成比例」是无意义的。
function ratioPercent(numerator: number | null, denominator: number | null): number | null {
  if (numerator === null || denominator === null || denominator <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, (numerator / denominator) * 100));
}

function ReadyTag({ ready }: { ready: boolean | null }) {
  if (ready === true) {
    return <Tag tone="accent">已具备条件</Tag>;
  }
  if (ready === false) {
    return <Tag>尚未达标</Tag>;
  }
  return <Tag>未返回</Tag>;
}

function readySummary(ready: boolean | null): string {
  if (ready === true) {
    return "后端判定：四条要求已全部满足，具备进入结业作品的资格。";
  }
  if (ready === false) {
    return "后端判定：仍有要求未满足；未达标前不进入作品提交阶段。";
  }
  return "后端本次没有返回 ready 字段，无法判断是否具备条件。";
}

export function ProjectsView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<CapstoneReadiness>(READINESS_PATH, {
        parse: parseCapstoneReadiness,
      });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", readiness: result.data });
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
        title="正在读取结业作品达标情况"
        description="GET /api/v1/capstone/readiness 是四条要求的唯一数据来源。"
        rows={4}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="结业作品达标情况加载失败"
        onRetry={retry}
        extra={<p>读取失败时不展示任何估算进度，也不提前给出「已具备条件」的结论。</p>}
      />
    );
  }

  const { ready, requirements, note } = state.readiness;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="结业作品达标情况"
          description="四条要求全部由真实学习记录推导：completed 课程数、去重后的通过练习数、L2 能力域数、已完成计划任务数。"
          action={<ReadyTag ready={ready} />}
        />
        <CardBody className="space-y-4">
          <p className="text-[12px] leading-relaxed text-fg">{readySummary(ready)}</p>
          {requirements === null ? (
            <p className="text-[11px] leading-relaxed text-muted">
              后端未返回 requirements 数组，本页不自行补齐四条判定。
            </p>
          ) : requirements.length === 0 ? (
            <EmptyState
              title="后端没有返回任何判定要求"
              description="结业作品要求由后端定义；列表为空时不展示任何本地默认门槛。"
              action={
                <Button variant="secondary" onClick={retry}>
                  重新读取
                </Button>
              }
            />
          ) : (
            <ul className="space-y-4">
              {requirements.map((requirement) => {
                const ratio = ratioPercent(requirement.actual, requirement.required);
                return (
                  <li key={requirement.key} className="space-y-2">
                    <div className="flex flex-wrap items-start justify-between gap-2">
                      <span className="min-w-0 text-[12px] font-medium text-fg">
                        {requirement.label ?? requirement.key}
                      </span>
                      <div className="flex shrink-0 items-center gap-2">
                        <span className="font-mono text-[11px] text-muted">
                          {numberText(requirement.actual)} / {numberText(requirement.required)}
                        </span>
                        {requirement.met === null ? (
                          <Tag>未返回</Tag>
                        ) : requirement.met ? (
                          <Tag tone="accent">已达标</Tag>
                        ) : (
                          <Tag>未达标</Tag>
                        )}
                      </div>
                    </div>
                    {ratio === null ? (
                      <p className="text-[11px] text-muted">完成比例：{DASH}（required 缺失或为 0）</p>
                    ) : (
                      <Meter
                        value={ratio}
                        tone={requirement.met === true ? "success" : "accent"}
                        label={requirement.label ?? requirement.key}
                      />
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="提交与评审说明"
          description="后端 note 原样显示，前端不改写、不补充承诺。"
          action={<Tag>{note === null ? "未返回" : "原样显示"}</Tag>}
        />
        <CardBody>
          <p className="text-[12px] leading-relaxed text-fg">{note ?? DASH}</p>
        </CardBody>
      </Card>

      <p className="text-[11px] leading-relaxed text-muted">
        「{DASH}」表示本次响应没有该字段：页面不补零、不估算，也不把未返回的判定当成未达标。
      </p>
    </div>
  );
}
