"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Alert, ErrorPanel, LoadingPanel } from "@/components/states";
import { LessonList } from "@/components/lesson-list";
import { Button } from "@/components/form";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseUsersMe } from "@/lib/contract";
import type { SkillLevelRow, UsersMe } from "@/lib/contract";
import { DOMAINS } from "@/lib/questions";
import type { DomainMeta } from "@/lib/questions";
import { levelLabel, stateLabel } from "@/lib/labels";

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; me: UsersMe; guide: boolean };

type StageCell = {
  domain: DomainMeta;
  skill: SkillLevelRow | null;
};

function stageCells(skills: SkillLevelRow[]): StageCell[] {
  return DOMAINS.map((domain) => {
    let found: SkillLevelRow | null = null;
    for (const skill of skills) {
      if (skill.code === domain.code) {
        found = skill;
      }
    }
    return { domain, skill: found };
  });
}

// 六个域全部没有任何评估记录时才进入引导态：缺行也算未评估，不做任何推测。
function allUnassessed(cells: StageCell[]): boolean {
  for (const cell of cells) {
    if (cell.skill && cell.skill.state !== "unassessed") {
      return false;
    }
  }
  return true;
}

function stageStateOf(cell: StageCell): SkillLevelRow["state"] {
  return cell.skill ? cell.skill.state : "unassessed";
}

function tagTone(cell: StageCell): "accent" | "neutral" {
  return stageStateOf(cell) === "established" ? "accent" : "neutral";
}

// L0 有两种含义：没有评估记录 vs 已测但未达门槛。两者必须分开写，避免把「已测」写成「未评估」。
function levelText(cell: StageCell): string {
  const level = cell.skill ? cell.skill.level : 0;
  if (level > 0) {
    return levelLabel(level);
  }
  return stageStateOf(cell) === "assessed_below_threshold" ? "L0 · 未达门槛" : "L0 · 未评估";
}

function stageSentence(cell: StageCell): string {
  const state = stageStateOf(cell);
  if (state === "established") {
    return "该域已有诊断证据，等级 " + levelText(cell) + "。下一步用练习与项目继续积累可复核的证据。";
  }
  if (state === "assessed_below_threshold") {
    return "参加过诊断，但正确率未达 L1 门槛，因此不授予等级——这不等于「能力弱」。";
  }
  if (state === "requested_verification") {
    return "存在待验证的等级申请，但仍缺少实践证据，暂不建立等级。";
  }
  return "该域还没有任何评估记录，系统不推测等级，也不显示进度。";
}

export function LearnView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<UsersMe>("/api/v1/users/me", { parse: parseUsersMe });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      const cells = stageCells(result.data.skills);
      setState({ status: "ready", me: result.data, guide: allUnassessed(cells) });
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
        title="正在读取六域等级状态"
        description="GET /api/v1/users/me 的 skills 是路线 A 六个阶段的唯一状态来源。"
        rows={3}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="路线状态加载失败"
        onRetry={retry}
        extra={<p>拿不到真实等级时不展示任何课程内容或进度，避免把占位数据当成你的进度。</p>}
      />
    );
  }

  if (state.guide) {
    return (
      <Card>
        <CardHeader
          title="先完成能力诊断"
          description="六个技能域全部为 unassessed，说明系统还没有任何证据，因此本页不展示课程内容与完成度。"
          action={<Tag>六域均未评估</Tag>}
        />
        <CardBody className="space-y-4">
          <p className="text-[13px] leading-relaxed text-fg">
            路线 A 的六个阶段按你的实际水平决定起点。现在还没有诊断记录，先做一次 20 题诊断，
            拿到六个域的起始等级后，本页会显示真实的阶段状态。
          </p>
          <ul className="space-y-1.5 text-[11px] leading-relaxed text-muted">
            <li>诊断共 20 题，覆盖 Python 基础、编程实践、API、LLM、RAG 与 Agent 基础、简单 AI 项目。</li>
            <li>作答进度自动保存在本机草稿里，中途刷新不会丢；未提交前不会产生任何服务端批次。</li>
            <li>没有诊断证据的阶段一律保持「尚未评估」，系统不会给出猜测等级，也不会显示虚假进度。</li>
          </ul>
          <div className="flex flex-wrap items-center gap-2">
            <Link
              href="/diagnostic"
              className="rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas"
            >
              开始 20 题诊断
            </Link>
            <Link
              href="/onboarding"
              className="rounded-control border border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg"
            >
              先去完善学习档案
            </Link>
          </div>
          <p className="text-[11px] leading-relaxed text-muted">
            学习档案里设置学习日与每天可用时长，诊断结果会与档案一起决定本页的阶段状态。
          </p>
        </CardBody>
      </Card>
    );
  }

  const cells = stageCells(state.me.skills);
  let unassessedCount = 0;
  for (const cell of cells) {
    if (stageStateOf(cell) === "unassessed") {
      unassessedCount += 1;
    }
  }

  return (
    <div className="space-y-6">
      {unassessedCount > 0 ? (
        <Alert
          tone="warning"
          title={"还有 " + String(unassessedCount) + " 个域没有诊断记录"}
          action={
            <Link
              href="/diagnostic"
              className="rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas"
            >
              补做一次诊断
            </Link>
          }
        >
          <p>
            这些域保持「尚未评估」，不显示等级也不显示进度；已建立等级的域直接展示接口返回的等级。
          </p>
        </Alert>
      ) : null}

      <Card>
        <CardHeader
          title="路线 A · 六阶段真实状态"
          description="等级与评估状态逐域来自 GET /api/v1/users/me；本页不计算、不推测任何完成百分比。"
          action={<Tag>{String(cells.length)} 个阶段</Tag>}
        />
        <CardBody>
          <ul className="divide-y divide-line">
            {cells.map((cell, index) => (
              <li key={cell.domain.code} className="py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="grid size-6 shrink-0 place-items-center rounded-control border border-line bg-surface font-mono text-[11px] text-muted">
                    {String(index + 1)}
                  </span>
                  <span className="text-[13px] font-medium text-fg">{cell.domain.nameZh}</span>
                  <Tag tone={tagTone(cell)}>{levelText(cell)}</Tag>
                  <Tag>{stateLabel(stageStateOf(cell))}</Tag>
                  <span className="font-mono text-[11px] text-muted">{cell.domain.code}</span>
                </div>
                <p className="mt-1.5 text-[12px] leading-relaxed text-muted">{cell.domain.summary}</p>
                <p className="mt-1 text-[11px] leading-relaxed text-muted">{stageSentence(cell)}</p>
              </li>
            ))}
          </ul>
        </CardBody>
      </Card>

      <LessonList />

      <Card>
        <CardHeader
          title="数据来源与边界"
          description="本页只读接口返回的六域状态与已发布课程，不生成任何课程内容或学时统计。"
        />
        <CardBody className="space-y-2">
          <p className="text-[11px] leading-relaxed text-muted">
            阶段状态来自 GET /api/v1/users/me 的 skills[].state 与 skills[].level；
            最近一次诊断的六域结果见「诊断结果」，历史批次见「历史结果」。
          </p>
          <p className="text-[11px] leading-relaxed text-muted">
            {"课程区块来自 GET /api/v1/lessons（仅 status='published'），每节课的进度状态取自接口的 progress 字段；练习尚未接入后端，本页不会用占位课程或演示进度填充阶段内容。"}
          </p>
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button variant="secondary" onClick={retry}>
              刷新六域状态
            </Button>
            <Link
              href="/result"
              className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
            >
              查看本次诊断结果
            </Link>
            <Link
              href="/history"
              className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
            >
              历史结果
            </Link>
            <Link
              href="/plan"
              className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
            >
              路线预览
            </Link>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
