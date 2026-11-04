import type { EvidenceStrength } from "@/lib/contract";
import { cx } from "@/components/ui";

// 证据标签只有三态，措辞与 B1 冻结口径逐字一致；它描述的是「证据强度」，不是得分或能力等级。
export type EvidenceKind = "static_rule" | "self_check" | "none";

export const EVIDENCE_LABELS: Record<EvidenceKind, string> = {
  static_rule: "已验证（静态规则）",
  self_check: "未验证（自检）",
  none: "未提交",
};

// B1：assessed 只可能来自 static_rule，self_reported 只可能来自 self_check，两者都不是 verified。
// 若后端返回 verified（本产品不存在该等级），这里同样不按「已验证」展示——宁可低估证据强度，
// 也不把静态规则或自检结果写成 verified。
export function evidenceKind(
  strength: EvidenceStrength | null | undefined,
  submitted: boolean,
): EvidenceKind {
  if (!submitted) {
    return "none";
  }
  return strength === "assessed" ? "static_rule" : "self_check";
}

// 配色只取 globals.css 已有令牌：文本 success-text / warning-text / muted，底色 surface。
// 不使用 accent（同一视图强调色不超过 3 处），也不新增颜色或写死十六进制。
const EVIDENCE_CLASS: Record<EvidenceKind, string> = {
  static_rule: "border-line bg-surface text-success-text",
  self_check: "border-line bg-surface text-warning-text",
  none: "border-line bg-elevated text-muted",
};

export function EvidenceBadge({
  kind,
  className,
}: {
  kind: EvidenceKind;
  className?: string;
}) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-control border px-1.5 py-0.5 text-[11px] leading-4 font-medium whitespace-nowrap",
        EVIDENCE_CLASS[kind],
        className,
      )}
    >
      {EVIDENCE_LABELS[kind]}
    </span>
  );
}

export function EvidenceLegend() {
  const rows: Array<{ kind: EvidenceKind; detail: string }> = [
    { kind: "static_rule", detail: "系统按必须出现/禁止出现的静态模式比对，给出通过与否。" },
    { kind: "self_check", detail: "来自你自己申报的本地运行结果，未被系统复核。" },
    { kind: "none", detail: "还没有提交记录。" },
  ];
  return (
    <ul className="space-y-2">
      {rows.map((row) => (
        <li key={row.kind} className="flex flex-wrap items-start gap-2">
          <EvidenceBadge kind={row.kind} />
          <span className="min-w-0 flex-1 text-[11px] leading-relaxed text-muted">{row.detail}</span>
        </li>
      ))}
    </ul>
  );
}
