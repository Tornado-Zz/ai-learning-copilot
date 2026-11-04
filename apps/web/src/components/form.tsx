import type {
  ButtonHTMLAttributes,
  InputHTMLAttributes,
  ReactNode,
  SelectHTMLAttributes,
} from "react";
import { cx } from "@/components/ui";

export type ButtonVariant = "primary" | "secondary" | "quiet" | "danger";

const BUTTON_VARIANT: Record<ButtonVariant, string> = {
  primary: "border-accent bg-accent text-canvas hover:opacity-90",
  secondary: "border-line-strong bg-surface text-fg hover:bg-elevated",
  quiet: "border-transparent bg-transparent text-muted hover:text-fg",
  danger: "border-line-strong bg-surface text-danger-text hover:bg-elevated",
};

export function Button({
  variant = "secondary",
  className,
  children,
  ...props
}: { variant?: ButtonVariant } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cx(
        "inline-flex items-center justify-center gap-2 rounded-control border px-3 py-1.5 text-[12px] font-medium transition-colors disabled:cursor-not-allowed disabled:border-line disabled:bg-surface disabled:text-muted",
        BUTTON_VARIANT[variant],
        className,
      )}
      {...props}
    >
      {children}
    </button>
  );
}

export function fieldClass(invalid: boolean): string {
  return cx(
    "w-full rounded-control border bg-surface px-3 py-2 text-[13px] text-fg placeholder:text-muted",
    invalid ? "border-danger" : "border-line-strong",
  );
}

export function Field({
  id,
  label,
  hint,
  error,
  children,
  className,
}: {
  id: string;
  label: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("space-y-1.5", className)}>
      <label htmlFor={id} className="block text-[12px] font-medium text-fg">
        {label}
      </label>
      {hint ? (
        <p id={id + "-hint"} className="text-[11px] leading-relaxed text-muted">
          {hint}
        </p>
      ) : null}
      {children}
      {error ? (
        <p id={id + "-error"} role="alert" className="text-[11px] leading-relaxed text-danger-text">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export function fieldAria(
  id: string,
  error: string | null | undefined,
  hasHint: boolean,
): { "aria-invalid"?: boolean; "aria-describedby"?: string } {
  const describedBy = error ? id + "-error" : hasHint ? id + "-hint" : undefined;
  return {
    "aria-invalid": error ? true : undefined,
    "aria-describedby": describedBy,
  };
}

export function TextInput({
  invalid = false,
  className,
  ...props
}: { invalid?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return <input className={cx(fieldClass(invalid), className)} {...props} />;
}

export function Select({
  invalid = false,
  className,
  children,
  ...props
}: { invalid?: boolean } & SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <select className={cx(fieldClass(invalid), className)} {...props}>
      {children}
    </select>
  );
}

export function ChoiceOption({
  id,
  name,
  value,
  checked,
  onChange,
  label,
  disabled = false,
}: {
  id: string;
  name: string;
  value: string;
  checked: boolean;
  onChange: () => void;
  label: ReactNode;
  disabled?: boolean;
}) {
  return (
    <label
      htmlFor={id}
      className={cx(
        "flex cursor-pointer items-start gap-2.5 rounded-control border px-3 py-2.5 text-[13px] transition-colors",
        checked ? "border-accent bg-accent-soft text-fg" : "border-line bg-surface text-fg hover:bg-elevated",
        disabled ? "cursor-not-allowed opacity-70" : null,
      )}
    >
      <input
        id={id}
        name={name}
        type="radio"
        value={value}
        checked={checked}
        disabled={disabled}
        onChange={onChange}
        className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]"
      />
      <span className="min-w-0 flex-1 leading-relaxed">{label}</span>
    </label>
  );
}
