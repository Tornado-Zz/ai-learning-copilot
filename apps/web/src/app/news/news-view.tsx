"use client";

import { useCallback, useEffect, useState } from "react";

import { Callout } from "@/components/callout";
import { Button } from "@/components/form";
import { Alert, EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { formatDateTime } from "@/lib/labels";
import {
  NEWS_LIMIT,
  NEWS_PATH,
  NEWS_REFRESH_PATH,
  aiStatusLabel,
  analyzePath,
  askPath,
  parseNewsAnswer,
  newsSourceLabel,
  parseNewsItem,
  parseNewsList,
  parseNewsRefresh,
} from "@/lib/news";
import type { NewsAnswer, NewsItem, NewsList, NewsRefresh } from "@/lib/news";

type ViewState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; data: NewsList };

export function NewsView() {
  const [state, setState] = useState<ViewState>({ status: "loading" });
  const [refreshing, setRefreshing] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionFailure, setActionFailure] = useState<ApiFailure | null>(null);

  const [reloadToken, setReloadToken] = useState(0);

  // 首屏与每次重试都走这里；active 守卫避免卸载后写入。
  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<NewsList>(
        NEWS_PATH + "?limit=" + String(NEWS_LIMIT),
        { parse: parseNewsList },
      );
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", data: result.data });
    })();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const load = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  const refresh = useCallback(async () => {
    setRefreshing(true);
    setActionFailure(null);
    setNotice(null);
    const result = await apiRequest<NewsRefresh>(NEWS_REFRESH_PATH, {
      method: "POST",
      parse: parseNewsRefresh,
    });
    setRefreshing(false);
    if (!result.ok) {
      setActionFailure(result.failure);
      return;
    }
    const stats = result.data.sources
      .map((stat) =>
        stat.status === "ok"
          ? stat.source + " +" + String(stat.inserted ?? 0)
          : stat.source + " " + stat.status,
      )
      .join(" · ");
    setNotice(
      "已抓取：" + stats + "；条目 " + String(result.data.itemsBefore) + " → " + String(result.data.itemsAfter),
    );
    load();
  }, [load]);

  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [questions, setQuestions] = useState<Record<string, string>>({});

  const ask = useCallback(async (id: string) => {
    const question = (questions[id] ?? "").trim();
    if (question.length < 2) {
      return;
    }
    setBusyId(id);
    setActionFailure(null);
    setNotice(null);
    const result = await apiRequest<NewsAnswer>(askPath(id), {
      method: "POST",
      body: { question },
      parse: parseNewsAnswer,
    });
    setBusyId(null);
    if (!result.ok) {
      setActionFailure(result.failure);
      return;
    }
    setAnswers((value) => ({ ...value, [id]: result.data.answer }));
  }, [questions]);

  const analyze = useCallback(
    async (id: string) => {
      setBusyId(id);
      setActionFailure(null);
      setNotice(null);
      const result = await apiRequest<NewsItem>(analyzePath(id), {
        method: "POST",
        parse: parseNewsItem,
      });
      setBusyId(null);
      if (!result.ok) {
        setActionFailure(result.failure);
        return;
      }
      setNotice("已生成重点解析，本条内容已刷新。");
      load();
    },
    [load],
  );

  return (
    <div className="space-y-5">
      <header className="border-b border-line pb-5">
        <p className="text-[12px] font-medium text-muted">研究 · 技术新闻与论文</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">研究专栏</h1>
        <p className="mt-2 max-w-3xl text-[13px] leading-relaxed text-muted">
          从固定的三个源抓取条目，再由模型提炼「一句话摘要 + 三到五条要点」。
          抓取是显式动作：源在目录里写死，不接受任意 URL；开关关闭时端点直接拒绝。
        </p>
      </header>

      {state.status === "ready" && !state.data.enabled ? (
        <Alert tone="warning" title="抓取未启用：NEWS_ENABLED=false">
          <p>
            现在只能看已入库的条目。要抓新内容，请在 <code>apps/api/.env</code> 里设置{" "}
            <code>NEWS_ENABLED=true</code> 并重启后端。
          </p>
        </Alert>
      ) : null}

      {notice ? (
        <Alert tone="accent" title="操作完成">
          <p>{notice}</p>
        </Alert>
      ) : null}

      {actionFailure ? (
        <ErrorPanel failure={actionFailure} title="操作没有成功" />
      ) : null}

      <Card>
        <CardHeader
          title="条目"
          description="按发布时间倒序；同一个链接只入库一次，已生成的解析不会被覆盖。"
          action={
            <Button variant="primary" onClick={() => void refresh()} disabled={refreshing}>
              {refreshing ? "抓取中…" : "抓取最新"}
            </Button>
          }
        />
        <CardBody>
          {state.status === "loading" ? (
            <LoadingPanel title="正在读取专栏" description={"GET " + NEWS_PATH} rows={4} />
          ) : null}

          {state.status === "error" ? (
            <ErrorPanel
              failure={state.failure}
              title="读取失败"
              onRetry={load}
            />
          ) : null}

          {state.status === "ready" && state.data.items.length === 0 ? (
            <EmptyState
              title="还没有条目"
              description="点右上角「抓取最新」从 Hacker News、arXiv 与 GitHub Releases 拉一批。"
            />
          ) : null}

          {state.status === "ready" && state.data.items.length > 0 ? (
            <ul className="divide-y divide-line">
              {state.data.items.map((item) => (
                <li key={item.id} className="space-y-2 py-4 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Tag tone="accent">{newsSourceLabel(item.sourceKey)}</Tag>
                    <Tag tone={item.aiStatus === "ok" ? "success" : "neutral"}>
                      {aiStatusLabel(item.aiStatus)}
                    </Tag>
                    <span className="font-mono text-[11px] text-muted">
                      {item.publishedAt === null ? "时间未知" : formatDateTime(item.publishedAt)}
                    </span>
                  </div>
                  <a
                    href={item.url}
                    target="_blank"
                    rel="noreferrer"
                    className="block text-[14px] font-medium leading-snug text-fg underline-offset-2 hover:text-accent hover:underline"
                  >
                    {item.title}
                  </a>
                  {item.aiSummary ? (
                    <p className="text-[12.5px] leading-relaxed text-fg">
                      <span className="mr-1.5 rounded-[3px] bg-accent-soft px-1 py-px text-[11px] font-medium text-accent">
                        摘要
                      </span>
                      {item.aiSummary}
                    </p>
                  ) : null}
                  {item.aiKeyPoints.length > 0 ? (
                    <ul className="space-y-1 rounded-control border border-accent-line bg-accent-soft px-3 py-2">
                      {item.aiKeyPoints.map((point, index) => (
                        <li key={index} className="flex gap-2 text-[12.5px] leading-relaxed text-fg">
                          <span className="shrink-0 font-mono text-[11px] font-semibold text-accent">
                            {String(index + 1)}
                          </span>
                          <span>{point}</span>
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <div className="flex flex-wrap items-center gap-2">
                    <Button
                      variant="secondary"
                      onClick={() => void analyze(item.id)}
                      disabled={busyId !== null}
                    >
                      {busyId === item.id
                        ? "提炼中…"
                        : item.aiStatus === "ok"
                          ? "重新提炼"
                          : "AI 提炼重点"}
                    </Button>
                    {item.aiTokens !== null ? (
                      <span className="font-mono text-[11px] text-muted">
                        {String(item.aiTokens)} tokens
                      </span>
                    ) : null}
                    {item.excerpt ? (
                      <span className="line-clamp-2 text-[11px] leading-relaxed text-muted">
                        原文摘要：{item.excerpt}
                      </span>
                    ) : null}
                  </div>

                  <div className="flex flex-wrap items-center gap-2">
                    <input
                      type="text"
                      value={questions[item.id] ?? ""}
                      onChange={(event) =>
                        setQuestions((value) => ({ ...value, [item.id]: event.target.value }))
                      }
                      placeholder="就这条问 AI，例如：它解决什么问题？"
                      aria-label={"就《" + item.title + "》提问"}
                      className="min-w-[220px] flex-1 rounded-control border border-line-strong bg-surface px-2.5 py-1.5 text-[12px] text-fg"
                    />
                    <Button
                      variant="secondary"
                      onClick={() => void ask(item.id)}
                      disabled={busyId !== null || (questions[item.id] ?? "").trim().length < 2}
                    >
                      {busyId === item.id ? "思考中…" : "问 AI"}
                    </Button>
                  </div>
                  {answers[item.id] ? (
                    <p className="rounded-control border border-info-line bg-info-soft px-3 py-2 text-[12.5px] leading-relaxed text-fg">
                      <span className="mr-1.5 font-medium text-info-text">AI 回答</span>
                      {answers[item.id]}
                    </p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </CardBody>
      </Card>

      <Callout tone="info" title="这些来源是什么">
        <p>
          <strong>Hacker News 首页</strong> 是技术社区的热榜，够快但良莠不齐；
          <strong>arXiv cs.AI</strong> 是预印本，未经同行评审；
          <strong>Next.js Releases</strong> 是框架官方更新日志。
          三种源的可靠性不同，界面用不同标签区分，不合并成一个「权威」。
        </p>
      </Callout>
    </div>
  );
}
