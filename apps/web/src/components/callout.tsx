"use client";

import type { ReactNode } from "react";
import { cx } from "@/components/ui";

// 讲义里的「重点块」。之前所有内容都是同一张白卡片 + 灰正文，重点看不出来；
// 这里用一条左色边 + 淡色底把四类信息分开：目标 / 坑 / 自检 / 补充。
export type CalloutTone = "accent" | "info" | "success" | "warning" | "danger";

const TONE: Record<CalloutTone, { box: string; bar: string; title: string }> = {
  accent: {
    box: "border-accent-line bg-accent-soft",
    bar: "bg-accent",
    title: "text-accent",
  },
  info: {
    box: "border-info-line bg-info-soft",
    bar: "bg-info",
    title: "text-info-text",
  },
  success: {
    box: "border-success-line bg-success-soft",
    bar: "bg-success",
    title: "text-success-text",
  },
  warning: {
    box: "border-warning-line bg-warning-soft",
    bar: "bg-warning",
    title: "text-warning-text",
  },
  danger: {
    box: "border-danger-line bg-danger-soft",
    bar: "bg-danger",
    title: "text-danger-text",
  },
};

export function Callout({
  tone = "info",
  title,
  children,
  marker,
}: {
  tone?: CalloutTone;
  title?: string;
  children?: ReactNode;
  marker?: ReactNode;
}) {
  const t = TONE[tone];
  return (
    <div className={cx("relative overflow-hidden rounded-card border px-4 py-3 pl-5", t.box)}>
      <span aria-hidden="true" className={cx("absolute inset-y-0 left-0 w-1", t.bar)} />
      <div className="flex items-start gap-2.5">
        {marker ? <div className="mt-0.5 shrink-0">{marker}</div> : null}
        <div className="min-w-0 flex-1">
          {title ? (
            <p className={cx("text-[12.5px] font-semibold tracking-tight", t.title)}>{title}</p>
          ) : null}
          {children ? <div className="mt-1 space-y-1.5 text-[13px] leading-relaxed text-fg">{children}</div> : null}
        </div>
      </div>
    </div>
  );
}

// 行内代码：讲义正文里的 nums[0]、d.get("score", 0) 这类片段需要从中文里跳出来。
export function InlineCode({ children }: { children: ReactNode }) {
  return (
    <code className="rounded-[4px] border border-line bg-elevated px-1 py-px font-mono text-[12px] text-fg">
      {children}
    </code>
  );
}

// 正文里天然夹着 nums[1:3]、d.get("score", 0)、len(x) 这类片段。它们是重点，
// 却和中文糊在一起看不出边界，所以这里自动识别成行内代码。
// 只认「标识符 + 方括号或圆括号」，避免把普通英文单词当代码。
const CODE_SPAN = /(`[^`]+`|[A-Za-z_][A-Za-z0-9_.]*(?:\[[^\]]*\]|\([^)]*\))(?:\.[A-Za-z_][A-Za-z0-9_]*)?)/g;

export function RichText({ text }: { text: string }) {
  const parts = text.split(CODE_SPAN).filter((part) => part !== "");
  return (
    <p className="whitespace-pre-line text-[13.5px] leading-7 text-fg">
      {parts.map((part, index) => {
        const ticked = part.startsWith("`") && part.endsWith("`") && part.length > 2;
        const codeish = !ticked && /[[(]/.test(part);
        if (ticked || codeish) {
          return <InlineCode key={index}>{ticked ? part.slice(1, -1) : part}</InlineCode>;
        }
        return <span key={index}>{part}</span>;
      })}
    </p>
  );
}