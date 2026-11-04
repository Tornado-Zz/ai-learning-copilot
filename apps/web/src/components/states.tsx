import type { ReactNode } from "react";
import { Button } from "@/components/form";
import { cx } from "@/components/ui";
import type { ApiFailure } from "@/lib/http";

type AlertTone = "muted" | "warning" | "danger" | "accent";

const ALERT_TONE: Record<AlertTone, string> = {
  muted: "border-line bg-surface",
  warning: "border-line-strong bg-surface",
  danger: "border-danger bg-surface",
  accent: "border-accent bg-accent-soft",
};

export function Alert({
  tone = "muted",
  title,
  children,
  action,
}: {
  tone?: AlertTone;
  title: string;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className={cx("rounded-card border px-4 py-3", ALERT_TONE[tone])} role="status">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[12px] font-medium text-fg">{title}</p>
          {children ? (
            <div className="mt-1 space-y-1 text-[11px] leading-relaxed text-muted">{children}</div>
          ) : null}
        </div>
        {action ? <div className="shrink-0">{action}</div> : null}
      </div>
    </div>
  );
}

export function SkeletonLines({ rows = 3 }: { rows?: number }) {
  return (
    <div className="space-y-2" aria-hidden="true">
      {Array.from({ length: rows }).map((_, index) => (
        <div
          key={index}
          className={cx("h-3 rounded-full bg-elevated", index === rows - 1 ? "w-2/3" : "w-full")}
        />
      ))}
    </div>
  );
}

export function LoadingPanel({
  title = "正在加载",
  description = "从后端读取数据，请稍候。",
  rows = 3,
}: {
  title?: string;
  description?: string;
  rows?: number;
}) {
  return (
    <div
      aria-busy="true"
      aria-live="polite"
      className="rounded-card border border-line bg-canvas px-5 py-5"
    >
      <p className="text-[13px] font-semibold tracking-tight text-fg">{title}</p>
      <p className="mt-1 text-[11px] leading-relaxed text-muted">{description}</p>
      <div className="mt-4">
        <SkeletonLines rows={rows} />
      </div>
    </div>
  );
}

export function ErrorPanel({
  failure,
  title = "加载失败",
  onRetry,
  extra,
}: {
  failure: ApiFailure | null;
  title?: string;
  onRetry?: () => void;
  extra?: ReactNode;
}) {
  const message = failure ? failure.message : "请求失败。";
  const code = failure ? failure.code : "INTERNAL_ERROR";
  const requestId = failure ? failure.requestId : null;
  return (
    <div className="rounded-card border border-line bg-canvas px-5 py-5" role="alert">
      <p className="text-[13px] font-semibold tracking-tight text-fg">{title}</p>
      <p className="mt-1.5 text-[12px] leading-relaxed text-danger-text">{message}</p>
      <dl className="mt-3 space-y-1 border-t border-line pt-3 text-[11px] text-muted">
        <div className="flex items-center justify-between gap-3">
          <dt>错误码</dt>
          <dd className="font-mono text-fg">{code}</dd>
        </div>
        {requestId ? (
          <div className="flex items-center justify-between gap-3">
            <dt>request_id</dt>
            <dd className="font-mono text-fg">{requestId}</dd>
          </div>
        ) : null}
      </dl>
      {extra ? <div className="mt-3 text-[11px] leading-relaxed text-muted">{extra}</div> : null}
      {onRetry ? (
        <div className="mt-4">
          <Button variant="secondary" onClick={onRetry}>
            重试
          </Button>
        </div>
      ) : null}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="rounded-card border border-dashed border-line-strong px-5 py-10 text-center">
      <p className="text-[13px] font-medium text-fg">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-[11px] leading-relaxed text-muted">{description}</p>
      {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
    </div>
  );
}
