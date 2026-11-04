"use client";

import { useCallback, useState } from "react";
import { Button, TextInput } from "@/components/form";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { formatDateTime } from "@/lib/labels";
import {
  KNOWLEDGE_LIMIT,
  KNOWLEDGE_QUERY_MIN,
  KNOWLEDGE_STALE_BADGE,
  KNOWLEDGE_STALE_DAYS_HINT,
  ageDaysText,
  buildSearchPath,
  parseKnowledgeSearch,
  scoreText,
  sourceDomain,
  validateKnowledgeQuery,
} from "@/lib/knowledge";
import type { KnowledgeHit, KnowledgeSearchResult } from "@/lib/knowledge";

// 三种结果态与三种过程态都复用现成组件（LoadingPanel / ErrorPanel / EmptyState），
// 页面不新增自己的骨架屏或空态样式。

type ViewState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; result: KnowledgeSearchResult };

const QUERY_ID = "knowledge-query";
const QUERY_ERROR_ID = "knowledge-query-error";
const QUERY_HINT_ID = "knowledge-query-hint";

export function KnowledgeView() {
  const [query, setQuery] = useState("");
  const [validation, setValidation] = useState<string | null>(null);
  const [state, setState] = useState<ViewState>({ status: "idle" });

  const runSearch = useCallback(async (raw: string) => {
    const invalid = validateKnowledgeQuery(raw);
    if (invalid !== null) {
      setValidation(invalid);
      setState({ status: "idle" });
      return;
    }
    setValidation(null);
    setState({ status: "loading" });
    const result = await apiRequest<KnowledgeSearchResult>(buildSearchPath(raw), {
      parse: parseKnowledgeSearch,
    });
    if (!result.ok) {
      setState({ status: "error", failure: result.failure });
      return;
    }
    setState({ status: "ready", result: result.data });
  }, []);

  const canSubmit = query.trim().length >= KNOWLEDGE_QUERY_MIN;

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="检索知识库快照"
          description="GET /api/v1/knowledge/search?q=&limit=5 · 只读数据库查询，不在线抓取任何页面。"
          action={<Tag>{String(KNOWLEDGE_LIMIT) + " 条上限"}</Tag>}
        />
        <CardBody className="space-y-4">
          <form
            className="flex flex-col gap-3 sm:flex-row sm:items-end"
            onSubmit={(event) => {
              event.preventDefault();
              void runSearch(query);
            }}
          >
            <div className="min-w-0 flex-1 space-y-1.5">
              <label htmlFor={QUERY_ID} className="block text-[12px] font-medium text-fg">
                检索词（至少 {String(KNOWLEDGE_QUERY_MIN)} 个字符）
              </label>
              <p id={QUERY_HINT_ID} className="text-[11px] leading-relaxed text-muted">
                按小写切词后匹配 content 与 keywords；不足 {String(KNOWLEDGE_QUERY_MIN)} 个字符不发起请求。
                当前 {String(query.trim().length)} 个字符。
              </p>
              <TextInput
                id={QUERY_ID}
                value={query}
                onChange={(event) => {
                  setQuery(event.target.value);
                  if (validation !== null) {
                    setValidation(null);
                  }
                }}
                placeholder="例如：generator 表达式"
                autoComplete="off"
                invalid={validation !== null}
                aria-invalid={validation !== null ? true : undefined}
                aria-describedby={validation !== null ? QUERY_ERROR_ID : QUERY_HINT_ID}
              />
              {validation !== null ? (
                <p id={QUERY_ERROR_ID} role="alert" className="text-[11px] leading-relaxed text-danger-text">
                  {validation}
                </p>
              ) : null}
            </div>
            <div className="flex shrink-0 flex-col items-start gap-1.5">
              <Button
                variant="primary"
                type="submit"
                disabled={!canSubmit || state.status === "loading"}
                aria-disabled={!canSubmit || state.status === "loading"}
              >
                {state.status === "loading" ? "正在检索…" : "检索"}
              </Button>
              <span className="text-[11px] leading-relaxed text-muted">
                {canSubmit ? "结果按 score 降序，同分按抓取时间降序。" : "先写满 2 个字符。"}
              </span>
            </div>
          </form>

          <p className="text-[11px] leading-relaxed text-muted">
            score = 命中词得分 / 查询词数（命中 heading 或标题各加 1 分）；age_days 大于{" "}
            {String(KNOWLEDGE_STALE_DAYS_HINT)} 天的来源标记「{KNOWLEDGE_STALE_BADGE}」，
            阈值由后端 KNOWLEDGE_STALE_DAYS 决定。
          </p>
        </CardBody>
      </Card>

      {state.status === "idle" ? (
        <EmptyState
          title="输入至少 2 个字符开始检索"
          description="知识库为空时不显示占位结果；命中为空与接口失败是两种状态，本页分开显示。"
        />
      ) : null}

      {state.status === "loading" ? (
        <LoadingPanel
          title="正在检索知识库快照"
          description="纯数据库查询，不发起任何外部网络请求，也不刷新任何来源。"
          rows={4}
        />
      ) : null}

      {state.status === "error" ? (
        <ErrorPanel
          failure={state.failure}
          title="知识检索失败"
          onRetry={() => void runSearch(query)}
          extra={
            <p>
              knowledge 接口未注册时会返回 404；此时本页只显示该失败态，不显示任何假结果。
            </p>
          }
        />
      ) : null}

      {state.status === "ready" && state.result.items.length === 0 ? (
        <EmptyState
          title="没有命中任何知识块"
          description={
            "查询「" +
            state.result.query +
            "」在快照里没有匹配到 content 或 keywords。入库未执行时知识库是空的，这不是接口失败。"
          }
          action={
            <Button variant="secondary" onClick={() => void runSearch(query)}>
              重新检索
            </Button>
          }
        />
      ) : null}

      {state.status === "ready" && state.result.items.length > 0 ? (
        <Card>
          <CardHeader
            title="检索结果"
            description={
              "共 " +
              String(state.result.total) +
              " 条命中，显示前 " +
              String(state.result.items.length) +
              " 条；每条都标注抓取时间，过期条目带徽章。"
            }
            action={
              <Button variant="secondary" onClick={() => void runSearch(query)}>
                重新检索
              </Button>
            }
          />
          <ul className="divide-y divide-line">
            {state.result.items.map((item, index) => (
              <ResultRow key={(item.chunkId ?? "chunk") + "-" + String(index)} item={item} />
            ))}
          </ul>
        </Card>
      ) : null}
    </div>
  );
}

function ResultRow({ item }: { item: KnowledgeHit }) {
  const domain = sourceDomain(item.url);
  return (
    <li className="px-5 py-3">
      <div className="flex flex-wrap items-center gap-2">
        {item.url ? (
          <a
            href={item.url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-[13px] font-medium text-fg underline-offset-4 hover:text-accent hover:underline"
          >
            {item.title}
          </a>
        ) : (
          <span className="text-[13px] font-medium text-fg">{item.title}</span>
        )}
        <Tag>{domain}</Tag>
        {item.stale ? <Tag tone="warning">{KNOWLEDGE_STALE_BADGE}</Tag> : null}
        <span className="ml-auto font-mono text-[11px] tabular-nums text-muted">
          score {scoreText(item.score)}
        </span>
      </div>
      {item.heading ? (
        <p className="mt-1 text-[11px] leading-relaxed text-muted">{item.heading}</p>
      ) : null}
      {item.snippet ? (
        <p className="mt-1.5 text-[12px] leading-relaxed text-fg">{item.snippet}</p>
      ) : null}
      <p className="mt-1.5 flex flex-wrap gap-x-3 font-mono text-[11px] text-muted">
        <span>抓取 {formatDateTime(item.fetchedAt)}</span>
        <span>age_days {ageDaysText(item.ageDays)}</span>
        <span>chunk {item.chunkId ?? "后端未返回"}</span>
      </p>
      {item.url === "" ? (
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          后端未返回原文链接，本行不可点开。
        </p>
      ) : null}
    </li>
  );
}
