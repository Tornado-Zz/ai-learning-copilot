"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Button } from "@/components/form";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { SkillCard } from "@/components/skill-card";
import { AttemptDetailPanel } from "@/components/diagnostic/attempt-detail";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseHistory } from "@/lib/contract";
import type { HistoryItem } from "@/lib/contract";
import { formatDateTime } from "@/lib/labels";

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "empty" }
  | { status: "ready"; items: HistoryItem[] };

function summarize(item: HistoryItem): string {
  if (item.domains.length === 0) {
    return "该批次未返回六域明细";
  }
  let established = 0;
  let below = 0;
  let other = 0;
  for (const domain of item.domains) {
    if (domain.state === "established") {
      established += 1;
    } else if (domain.state === "assessed_below_threshold") {
      below += 1;
    } else {
      other += 1;
    }
  }
  const parts = [
    String(established) + " 域已建立等级",
    String(below) + " 域未达 L1 门槛",
  ];
  if (other > 0) {
    parts.push(String(other) + " 域尚未评估");
  }
  return parts.join(" · ");
}

function rowKey(item: HistoryItem, index: number): string {
  return item.attemptId === null ? "row-" + String(index) : "attempt-" + String(item.attemptId);
}

export function HistoryView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [expanded, setExpanded] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<HistoryItem[]>("/api/v1/diagnostics/history", {
        parse: parseHistory,
      });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      if (result.data.length === 0) {
        setState({ status: "empty" });
        return;
      }
      setState({ status: "ready", items: result.data });
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
        title="正在读取历史批次"
        description="GET /api/v1/diagnostics/history，按提交时间倒序展示。"
        rows={4}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="历史结果加载失败"
        onRetry={retry}
        extra={<p>接口尚未就绪时不会显示任何占位批次；历史数据只来自真实提交。</p>}
      />
    );
  }

  if (state.status === "empty") {
    return (
      <EmptyState
        title="还没有历史诊断批次"
        description="完成一次 20 题诊断后，这里会按时间列出每一个批次：时间、题集版本、规则版本与六域摘要。"
        action={
          <Link
            href="/diagnostic"
            className="rounded-control border border-accent bg-accent px-3 py-1.5 text-[12px] font-medium text-canvas"
          >
            去完成诊断
          </Link>
        }
      />
    );
  }

  return (
    <Card>
      <CardHeader
        title="历史批次"
        description={"共 " + String(state.items.length) + " 个批次，点开任意一行查看该批次的六域结果与逐题依据。"}
        action={
          <Button variant="secondary" onClick={retry}>
            刷新
          </Button>
        }
      />
      <CardBody className="space-y-3">
        {state.items.map((item, index) => {
          const key = rowKey(item, index);
          const open = expanded === key;
          const detailId = "history-detail-" + String(index);
          return (
            <div key={key} className="rounded-control border border-line">
              <button
                type="button"
                onClick={() => setExpanded(open ? null : key)}
                aria-expanded={open}
                aria-controls={detailId}
                aria-label={
                  "批次 " +
                  (item.attemptId === null ? "未知" : "#" + String(item.attemptId)) +
                  "，提交时间 " +
                  formatDateTime(item.submittedAt) +
                  "，" +
                  (open ? "收起六域结果" : "展开六域结果")
                }
                className="flex w-full flex-wrap items-center gap-3 px-3 py-3 text-left transition-colors hover:bg-elevated"
              >
                <span className="min-w-0 flex-1">
                  <span className="block font-mono text-[12px] text-fg">
                    {formatDateTime(item.submittedAt)}
                  </span>
                  <span className="mt-0.5 block text-[11px] text-muted">{summarize(item)}</span>
                </span>
                <span className="flex shrink-0 flex-wrap items-center gap-1.5">
                  <Tag>批次 {item.attemptId === null ? "—" : "#" + String(item.attemptId)}</Tag>
                  <Tag>题集 {item.questionSetVersion}</Tag>
                  <Tag>规则 {item.ruleVersion}</Tag>
                  <Tag>{open ? "收起" : "查看"}</Tag>
                </span>
              </button>
              {open ? (
                <div id={detailId} className="border-t border-line px-3 py-3">
                  {item.domains.length > 0 ? (
                    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                      {item.domains.map((domain) => (
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
                  ) : (
                    <p className="text-[11px] leading-relaxed text-muted">
                      该批次的响应里没有六域明细，本页不会推测等级。批次快照保存在诊断批次表中，六域结果页来自提交时的响应。
                    </p>
                  )}
                  <p className="mt-3 text-[11px] leading-relaxed text-muted">
                    总答对 {item.totalCorrect === null ? "—" : String(item.totalCorrect)} / 总题数{" "}
                    {item.totalQuestions === null ? "—" : String(item.totalQuestions)}。
                  </p>
                  <div className="mt-3">
                    {item.attemptId === null ? (
                      <p className="text-[11px] leading-relaxed text-muted">
                        该行没有批次号，无法读取逐题依据；本页不会用其他批次的答案补齐。
                      </p>
                    ) : (
                      <AttemptDetailPanel attemptId={item.attemptId} />
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          );
        })}
      </CardBody>
    </Card>
  );
}
