import type { AssessmentState } from "@/lib/contract";
import { cx, Tag } from "@/components/ui";
import { levelLabelForState, levelShort, stateLabel, formatScore, domainName } from "@/lib/labels";

export type SkillView = {
  code: string;
  nameZh?: string | null;
  level: number;
  state: AssessmentState;
  correct?: number;
  total?: number;
  rate?: number;
};

function hasScore(skill: SkillView): boolean {
  return (
    typeof skill.correct === "number" &&
    typeof skill.total === "number" &&
    typeof skill.rate === "number"
  );
}

export function basisSentence(skill: SkillView): string {
  const score = hasScore(skill)
    ? "该域正确率 " + String(Math.round((skill.rate as number) * 100)) + "%（" +
      String(skill.correct) + " / " + String(skill.total) + " 题）"
    : "该域";
  if (skill.state === "established") {
    if (skill.level >= 3) {
      return "已建立 L" + String(skill.level) + "：需要运行测试或人工复核证据，Sprint 1 不可自动授予。";
    }
    if (skill.level === 2) {
      return score + "，达到 L2 门槛（≥85%），按诊断规则授予 L2。";
    }
    if (skill.level === 1) {
      return score + "，达到 L1 门槛（≥60%），按诊断规则授予 L1。";
    }
    return "该域状态标记为已建立，但等级为 L0，请以接口返回为准。";
  }
  if (skill.state === "assessed_below_threshold") {
    return score + "，未达 L1 门槛（≥60%），因此不授予等级。";
  }
  if (skill.state === "requested_verification") {
    return "用户主张了更高等级，但仍缺少实践证据，暂不建立等级。";
  }
  return "该域尚无任何评估记录，系统不做推测。";
}

export function SkillCard({ skill }: { skill: SkillView }) {
  const established = skill.state === "established";
  return (
    <article className="rounded-card border border-line bg-canvas">
      <header className="flex items-start justify-between gap-3 border-b border-line px-4 py-3">
        <div className="min-w-0">
          <p className="truncate text-[13px] font-semibold tracking-tight text-fg">
            {domainName(skill.code, skill.nameZh)}
          </p>
          <p className="mt-0.5 font-mono text-[11px] text-muted">{skill.code}</p>
        </div>
        <span
          className={cx(
            "shrink-0 rounded-control border px-2 py-0.5 text-[11px] font-medium",
            established
              ? "border-transparent bg-accent-soft text-accent"
              : "border-line bg-elevated text-muted",
          )}
        >
          {levelShort(skill.level)}
        </span>
      </header>
      <div className="space-y-3 px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Tag tone={established ? "accent" : "neutral"}>{levelLabelForState(skill.level, skill.state)}</Tag>
          <Tag>{stateLabel(skill.state)}</Tag>
        </div>
        <dl className="space-y-1 text-[11px]">
          <div className="flex items-start justify-between gap-3">
            <dt className="shrink-0 text-muted">assessment_state</dt>
            <dd className="text-right font-mono text-fg">{skill.state}</dd>
          </div>
          <div className="flex items-start justify-between gap-3">
            <dt className="shrink-0 text-muted">答对 / 总题（正确率）</dt>
            <dd className="text-right font-mono text-fg">
              {hasScore(skill)
                ? formatScore(skill.correct as number, skill.total as number, skill.rate as number)
                : "本次诊断未返回该域题数"}
            </dd>
          </div>
        </dl>
        <div className="rounded-control bg-surface px-3 py-2">
          <p className="text-[11px] font-medium text-muted">判定依据</p>
          <p className="mt-1 text-[12px] leading-relaxed text-fg">{basisSentence(skill)}</p>
        </div>
      </div>
    </article>
  );
}
