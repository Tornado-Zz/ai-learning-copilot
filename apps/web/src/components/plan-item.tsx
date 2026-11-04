"use client";

import Link from "next/link";
import { useState } from "react";
import type { ReactNode } from "react";
import { Tag } from "@/components/ui";
import {
  PLAN_ITEM_STATUS_LABELS,
  formatMinutes,
  planItemKindLabel,
  planItemTitle,
} from "@/lib/learning";
import type { PlanItem } from "@/lib/learning";
import { planItemReadOnlyNote } from "@/lib/plan-rules";

// S6：类型徽章是零基础用户分辨「读课」与「动手练」的第一信息，所以排在标题之前。
// v0.1.2：kind 新增 review（间隔复习），与 exercise 同属动手项、共用强调色；文案统一由 planItemKindLabel 给出。
const ACTION_KINDS = ["exercise", "review"];

function KindBadge({ kind }: { kind: string }) {
  return (
    <Tag tone={ACTION_KINDS.indexOf(kind) >= 0 ? "accent" : "neutral"}>
      {planItemKindLabel(kind)}
    </Tag>
  );
}

// 跳转文案跟随 kind，不再把 review 行说成「去学习」；未知 kind 用中性说法。
const KIND_CTA: Record<string, string> = {
  lesson: "去学习 →",
  exercise: "去练习 →",
  review: "去复习 →",
};

function Minutes({ value }: { value: number }) {
  return <span className="font-mono text-[11px] tabular-nums text-muted">{formatMinutes(value)}</span>;
}

export function PlanItemRow({
  item,
  index,
  actions,
}: {
  item: PlanItem;
  index: number;
  actions?: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const panelId = "plan-item-rationale-" + String(index);
  const title = planItemTitle(item);
  // 终态（done/skipped）与 expired 行只读：用文案说明状态语义，按钮由调用方按 planItemActions 决定。
  const readOnlyNote = planItemReadOnlyNote(item.status);
  const rationale = item.rationale ? item.rationale : "后端未返回 rationale：本页不替它编造安排理由。";

  return (
    <li className="flex flex-wrap items-start gap-2 px-4 py-3">
      <span className="mt-0.5 grid size-5 shrink-0 place-items-center rounded-control border border-line bg-surface font-mono text-[10px] text-muted">
        {String(index)}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <KindBadge kind={item.kind} />
          {item.targetHref !== null ? (
            <Link
              href={item.targetHref}
              className="text-[13px] font-medium text-fg underline-offset-2 hover:text-accent hover:underline"
            >
              {title}
            </Link>
          ) : (
            <span className="text-[13px] font-medium text-fg">{title}</span>
          )}
          <Minutes value={item.plannedMinutes} />
          <Tag>{PLAN_ITEM_STATUS_LABELS[item.status]}</Tag>
          {readOnlyNote ? (
            <span className="text-[11px] leading-relaxed text-muted">{readOnlyNote}</span>
          ) : null}
        </div>
        {open ? null : (
          <p className="mt-1 line-clamp-1 text-[11px] leading-relaxed text-muted">{rationale}</p>
        )}
        <button
          type="button"
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => setOpen((value) => !value)}
          className="mt-1 text-[11px] font-medium text-accent hover:underline"
        >
          {open ? "收起安排理由" : "查看完整安排理由"}
        </button>
        <div
          id={panelId}
          hidden={!open}
          className="mt-1 rounded-control border border-line bg-surface px-2.5 py-2 text-[11px] leading-relaxed text-muted"
        >
          {rationale}
        </div>
      </div>
      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-1.5">{actions}</div> : null}
    </li>
  );
}

// 今日页的可点击卡片：整块是链接，不含任何会写状态的按钮（今日页只读，写操作都在周计划页）。
export function PlanItemCard({ item, index }: { item: PlanItem; index: number }) {
  const title = planItemTitle(item);
  const rationale = item.rationale ? item.rationale : "后端未返回 rationale：本页不替它编造安排理由。";
  const readOnlyNote = planItemReadOnlyNote(item.status);
  const body = (
    <>
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid size-5 shrink-0 place-items-center rounded-control border border-line bg-surface font-mono text-[10px] text-muted">
          {String(index)}
        </span>
        <KindBadge kind={item.kind} />
        <span className="min-w-0 flex-1 truncate text-[14px] font-medium text-fg">{title}</span>
        <Minutes value={item.plannedMinutes} />
      </div>
      <p className="mt-1.5 line-clamp-2 pl-7 text-[12px] leading-relaxed text-muted">{rationale}</p>
      <div className="mt-1.5 flex flex-wrap items-center gap-2 pl-7">
        <Tag>{PLAN_ITEM_STATUS_LABELS[item.status]}</Tag>
        {readOnlyNote ? <span className="text-[11px] text-muted">{readOnlyNote}</span> : null}
        {item.targetHref !== null ? (
          <span className="ml-auto text-[11px] font-medium text-accent">
            {KIND_CTA[item.kind] ?? "打开 →"}
          </span>
        ) : null}
      </div>
    </>
  );

  return (
    <li>
      {item.targetHref !== null ? (
        <Link
          href={item.targetHref}
          className="block rounded-control border border-line bg-canvas px-4 py-3 transition-colors hover:border-accent hover:bg-surface focus-visible:border-accent"
        >
          {body}
        </Link>
      ) : (
        <div className="block rounded-control border border-line bg-canvas px-4 py-3">{body}</div>
      )}
    </li>
  );
}
