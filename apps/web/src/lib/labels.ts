import type { AssessmentState } from "@/lib/contract";
import { DOMAINS } from "@/lib/questions";

export const LEVEL_NAMES: string[] = [
  "未评估",
  "认识概念",
  "能跟做",
  "能独立完成",
  "能迁移应用",
];

export function clampLevelValue(level: number): number {
  if (!Number.isFinite(level)) {
    return 0;
  }
  return Math.min(4, Math.max(0, Math.round(level)));
}

export function levelShort(level: number): string {
  return "L" + String(clampLevelValue(level));
}

export function levelLabel(level: number): string {
  const value = clampLevelValue(level);
  return "L" + String(value) + " · " + LEVEL_NAMES[value];
}

/**
 * levelLabel 但考虑评估状态：LEVEL_NAMES[0] 是「未评估」，而 assessed_below_threshold
 * 是「已经测过、只是没到 L1 门槛」。把两者拼在一起会印出「L0 · 未评估」紧挨着
 * 「已测，未达 L1 门槛」这样的自相矛盾，所以 level 0 遇上这个状态时改口径。
 */
export function levelLabelForState(level: number, state: AssessmentState): string {
  const value = clampLevelValue(level);
  if (value === 0 && state === "assessed_below_threshold") {
    return "L0 · 已测未达标";
  }
  return levelLabel(value);
}

export const STATE_LABELS: Record<AssessmentState, string> = {
  unassessed: "尚未评估",
  assessed_below_threshold: "已测，未达 L1 门槛",
  established: "已建立等级",
  requested_verification: "待验证申请",
};

export function stateLabel(state: AssessmentState): string {
  return STATE_LABELS[state] ?? STATE_LABELS.unassessed;
}


export function domainName(code: string, fallback?: string | null): string {
  for (const domain of DOMAINS) {
    if (domain.code === code) {
      return domain.nameZh;
    }
  }
  if (fallback) {
    return fallback;
  }
  return code;
}

export function formatRate(rate: number): string {
  if (!Number.isFinite(rate)) {
    return "—";
  }
  return String(Math.round(rate * 100)) + "%";
}

export function formatScore(correct: number, total: number, rate: number): string {
  return String(correct) + " / " + String(total) + " 题（" + formatRate(rate) + "）";
}

export function formatDateTime(iso: string | null, timeZone?: string): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  try {
    return date.toLocaleString("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: timeZone,
    });
  } catch {
    return date.toLocaleString("zh-CN", { hour12: false });
  }
}

export const WEEKDAYS: Array<{ value: number; label: string }> = [
  { value: 1, label: "周一" },
  { value: 2, label: "周二" },
  { value: 3, label: "周三" },
  { value: 4, label: "周四" },
  { value: 5, label: "周五" },
  { value: 6, label: "周六" },
  { value: 7, label: "周日" },
];

export function weekdayLabel(value: number): string {
  for (const day of WEEKDAYS) {
    if (day.value === value) {
      return day.label;
    }
  }
  return "第 " + String(value) + " 天";
}

export const TIMEZONE_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "Asia/Shanghai", label: "Asia/Shanghai（中国标准时间 UTC+8）" },
  { value: "Asia/Hong_Kong", label: "Asia/Hong_Kong（香港时间 UTC+8）" },
  { value: "Asia/Taipei", label: "Asia/Taipei（台北时间 UTC+8）" },
  { value: "Asia/Tokyo", label: "Asia/Tokyo（日本标准时间 UTC+9）" },
  { value: "Asia/Singapore", label: "Asia/Singapore（新加坡时间 UTC+8）" },
  { value: "Europe/London", label: "Europe/London（英国时间）" },
  { value: "Europe/Berlin", label: "Europe/Berlin（中欧时间）" },
  { value: "America/New_York", label: "America/New_York（美国东部时间）" },
  { value: "America/Los_Angeles", label: "America/Los_Angeles（美国西部时间）" },
  { value: "UTC", label: "UTC（协调世界时）" },
];

export function timezoneLabel(value: string): string {
  for (const zone of TIMEZONE_OPTIONS) {
    if (zone.value === value) {
      return zone.label;
    }
  }
  return value;
}
