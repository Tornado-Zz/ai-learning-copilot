"use client";

import Link from "next/link";
import { useMemo, useSyncExternalStore } from "react";
import { EmptyState, LoadingPanel } from "@/components/states";
import { SkillCard } from "@/components/skill-card";
import { AttemptDetailPanel } from "@/components/diagnostic/attempt-detail";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import {
  LAST_RESULT_STORAGE_KEY,
  getLastResultRaw,
  getServerLastResultRaw,
  parseLastResult,
  subscribeLastResult,
} from "@/lib/diagnostic-result";
import { formatDateTime } from "@/lib/labels";

const subscribeMount = () => () => {};
const getMounted = () => true;
const getNotMounted = () => false;

const STATE_LEGEND: Array<{ state: string; label: string; detail: string }> = [
  {
    state: "established",
    label: "已建立等级",
    detail: "达到该等级的证据充分：诊断正确率 ≥60% 授 L1，≥85% 授 L2。",
  },
  {
    state: "assessed_below_threshold",
    label: "已测，未达 L1 门槛",
    detail: "参加过诊断，但该域正确率低于 60%，因此不授予等级——这不等于「能力弱」。",
  },
  {
    state: "unassessed",
    label: "尚未评估",
    detail: "该域还没有任何评估记录，系统回退为 L0，不做任何推测。",
  },
];

export function ResultView() {
  const mounted = useSyncExternalStore(subscribeMount, getMounted, getNotMounted);
  const raw = useSyncExternalStore(subscribeLastResult, getLastResultRaw, getServerLastResultRaw);
  const result = useMemo(() => parseLastResult(raw), [raw]);

  if (!mounted) {
    return (
      <LoadingPanel
        title="正在读取本次诊断结果"
        description="结果保存在 sessionStorage，挂载后才读取，首屏不读浏览器存储。"
        rows={4}
      />
    );
  }

  if (!result) {
    return (
      <EmptyState
        title="还没有本次诊断结果"
        description="完成 20 题诊断后，六维结果会显示在这里；已经提交过的批次可以在「历史结果」里查看。"
        action={
          <div className="flex flex-wrap items-center justify-center gap-2">
            <Link
              href="/diagnostic"
              className="rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas"
            >
              开始 20 题诊断
            </Link>
            <Link
              href="/history"
              className="rounded-control border border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg"
            >
              查看历史结果
            </Link>
          </div>
        }
      />
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="本次诊断概览"
          description={
            "批次 " +
            (result.attemptId === null ? "未知" : "#" + String(result.attemptId)) +
            " · 规则版本 " +
            (result.ruleVersion || "—")
          }
          action={<Tag tone="accent">这是学习起点评估，不是能力认证</Tag>}
        />
        <CardBody className="space-y-3">
          <dl className="grid grid-cols-2 gap-3 text-[11px] sm:grid-cols-4">
            <div>
              <dt className="text-muted">attempt_id</dt>
              <dd className="mt-0.5 font-mono text-[12px] text-fg">
                {result.attemptId === null ? "—" : String(result.attemptId)}
              </dd>
            </div>
            <div>
              <dt className="text-muted">题集版本</dt>
              <dd className="mt-0.5 font-mono text-[12px] text-fg">
                {result.questionSetVersion ?? "—"}
              </dd>
            </div>
            <div>
              <dt className="text-muted">规则版本</dt>
              <dd className="mt-0.5 font-mono text-[12px] text-fg">{result.ruleVersion || "—"}</dd>
            </div>
            <div>
              <dt className="text-muted">提交时间</dt>
              <dd className="mt-0.5 font-mono text-[12px] text-fg">
                {formatDateTime(result.storedAt > 0 ? new Date(result.storedAt).toISOString() : null)}
              </dd>
            </div>
          </dl>
          <p className="text-[11px] leading-relaxed text-muted">
            结果同时保存在本机 sessionStorage（键名{" "}
            <span className="font-mono">{LAST_RESULT_STORAGE_KEY}</span>），刷新本页不会丢失；关闭标签页后请从「历史结果」查看。
          </p>
        </CardBody>
      </Card>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        {result.domains.map((domain) => (
          <SkillCard
            key={domain.skillCode}
            skill={{
              code: domain.skillCode,
              level: domain.level,
              state: domain.state,
              correct: domain.correct,
              total: domain.total,
              rate: domain.rate,
            }}
          />
        ))}
      </div>

      <section aria-label="逐题依据" className="space-y-3">
        {result.attemptId === null ? (
          <EmptyState
            title="无法定位批次"
            description="本次结果响应里没有 attempt_id。逐题依据只对已提交并能定位到的批次开放，本页不做任何推测。"
          />
        ) : (
          <AttemptDetailPanel attemptId={result.attemptId} />
        )}
      </section>

      <Card>
        <CardHeader
          title="三种状态的读法"
          description="L0 有两种含义，界面文案必须区分，且都不是「能力弱」。"
        />
        <CardBody className="space-y-3">
          {STATE_LEGEND.map((item) => (
            <div key={item.state} className="rounded-control border border-line bg-surface px-3 py-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <Tag>{item.label}</Tag>
                <span className="font-mono text-[11px] text-muted">{item.state}</span>
              </div>
              <p className="mt-1 text-[11px] leading-relaxed text-muted">{item.detail}</p>
            </div>
          ))}
          <p className="text-[11px] leading-relaxed text-muted">
            L3 / L4 在 Sprint 1–3 不能由诊断自动授予，只能以待验证申请存在。
          </p>
        </CardBody>
      </Card>

      <div className="flex flex-wrap items-center gap-2">
        <Link
          href="/plan"
          className="rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas"
        >
          查看个性化路线预览
        </Link>
        <Link
          href="/history"
          className="rounded-control border border-line-strong bg-surface px-3 py-1.5 text-[12px] font-medium text-fg"
        >
          查看历史结果
        </Link>
        <Link
          href="/diagnostic"
          className="rounded-control px-2 py-1.5 text-[12px] font-medium text-muted hover:text-fg"
        >
          重新做一次诊断
        </Link>
      </div>
    </div>
  );
}
