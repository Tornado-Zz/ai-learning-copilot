import type { ReactNode } from "react";

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("rounded-card border border-line bg-canvas", className)}>
      {children}
    </div>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-line px-5 py-4">
      <div className="min-w-0">
        <h2 className="text-[13px] font-semibold tracking-tight text-fg">{title}</h2>
        {description ? (
          <p className="mt-1 text-[12px] leading-relaxed text-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </div>
  );
}

export function CardBody({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={cx("px-5 py-4", className)}>{children}</div>;
}

type TagTone = "neutral" | "accent" | "success" | "warning" | "danger";

const TAG_TONE: Record<TagTone, string> = {
  neutral: "border-line bg-elevated text-muted",
  accent: "border-transparent bg-accent-soft text-accent",
  success: "border-line bg-elevated text-fg",
  warning: "border-line bg-elevated text-fg",
  danger: "border-line bg-elevated text-fg",
};

export function Tag({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: TagTone;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-control border px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap",
        TAG_TONE[tone],
      )}
    >
      {children}
    </span>
  );
}

export function DemoTag({ label = "演示数据" }: { label?: string }) {
  return <Tag>{label}</Tag>;
}

export function SoonTag({ label = "开发中" }: { label?: string }) {
  return (
    <span className="inline-flex items-center rounded-control border border-dashed border-line-strong px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap text-muted">
      {label}
    </span>
  );
}

export function DisabledButton({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      title="该功能尚未实现"
      className={cx(
        "inline-flex items-center gap-2 rounded-control border border-dashed border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium whitespace-nowrap text-muted",
        className,
      )}
    >
      <span>{children}</span>
      <SoonTag />
    </button>
  );
}

type DotTone = "success" | "warning" | "danger" | "muted";

const DOT_TONE: Record<DotTone, string> = {
  success: "bg-success",
  warning: "bg-warning",
  danger: "bg-danger",
  muted: "bg-line-strong",
};

export function Dot({
  tone = "muted",
  pulse = false,
}: {
  tone?: DotTone;
  pulse?: boolean;
}) {
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-block size-1.5 shrink-0 rounded-full",
        DOT_TONE[tone],
        pulse ? "animate-pulse" : null,
      )}
    />
  );
}

type MeterTone = "accent" | "muted" | "success" | "warning";

const METER_TONE: Record<MeterTone, string> = {
  accent: "bg-accent",
  muted: "bg-muted",
  success: "bg-success",
  warning: "bg-warning",
};

export function Meter({
  value,
  tone = "accent",
  label,
  className,
}: {
  value: number;
  tone?: MeterTone;
  label?: string;
  className?: string;
}) {
  const percent = Math.max(0, Math.min(100, Math.round(value)));
  return (
    <div
      className={cx("h-1.5 w-full overflow-hidden rounded-full bg-elevated", className)}
      role="img"
      aria-label={(label ?? "进度") + " " + percent + "%"}
    >
      <div
        className={cx("h-full rounded-full", METER_TONE[tone])}
        style={{ width: percent + "%" }}
      />
    </div>
  );
}

export function MetaRow({
  label,
  children,
}: {
  label: string;
  children: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-line py-2 last:border-b-0 last:pb-0">
      <span className="text-[12px] text-muted">{label}</span>
      <span className="text-right text-[12px] font-medium text-fg">{children}</span>
    </div>
  );
}
