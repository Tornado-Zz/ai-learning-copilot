"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { parseAttemptDetail } from "@/lib/contract";
import type { AttemptDetail, AttemptQuestion } from "@/lib/contract";
import { DOMAINS, KIND_LABELS } from "@/lib/questions";
import { domainName, formatDateTime } from "@/lib/labels";

type DetailState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; detail: AttemptDetail };

type DomainGroup = {
  code: string;
  nameZh: string;
  questions: AttemptQuestion[];
};

function attemptPath(attemptId: number): string {
  return "/api/v1/diagnostics/attempts/" + String(attemptId);
}

function kindLabel(kind: string): string {
  if (kind === "code_reading") {
    return KIND_LABELS.code_reading;
  }
  if (kind === "bug_fix" || kind === "fix_error") {
    return KIND_LABELS.fix_error;
  }
  if (kind === "single_choice") {
    return KIND_LABELS.single_choice;
  }
  return kind === "" ? "题型未提供" : kind;
}

function choiceLabel(choice: string | null): string {
  return choice === null || choice.trim() === "" ? "—" : choice;
}

function groupByDomain(questions: AttemptQuestion[]): DomainGroup[] {
  const groups: DomainGroup[] = [];
  for (const domain of DOMAINS) {
    const rows = questions.filter((question) => question.domainCode === domain.code);
    if (rows.length > 0) {
      groups.push({ code: domain.code, nameZh: domain.nameZh, questions: rows });
    }
  }
  const knownCodes = DOMAINS.map((domain) => domain.code);
  const rest = questions.filter((question) => knownCodes.indexOf(question.domainCode) < 0);
  if (rest.length > 0) {
    groups.push({ code: "", nameZh: "未标注域", questions: rest });
  }
  return groups;
}

function VerdictTag({ isCorrect }: { isCorrect: boolean | null }) {
  if (isCorrect === null) {
    return <Tag>接口未给出正误</Tag>;
  }
  if (isCorrect) {
    return <Tag tone="accent">正确</Tag>;
  }
  return <Tag tone="danger">错误</Tag>;
}

function QuestionRow({ question }: { question: AttemptQuestion }) {
  return (
    <li className="border-t border-line px-3 py-3 first:border-t-0">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-[11px] text-muted">第 {String(question.number)} 题</span>
        <Tag>{kindLabel(question.kind)}</Tag>
        <span className="font-mono text-[11px] text-muted">{question.id}</span>
        <span className="ml-auto">
          <VerdictTag isCorrect={question.isCorrect} />
        </span>
      </div>
      <p className="mt-2 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-fg">
        {question.prompt === "" ? "接口未返回题干" : question.prompt}
      </p>
      <dl className="mt-2 grid gap-2 text-[11px] sm:grid-cols-2">
        <div className="rounded-control bg-surface px-3 py-2">
          <dt className="text-muted">你的选择</dt>
          <dd className="mt-0.5 font-mono text-[12px] text-fg">{choiceLabel(question.yourChoice)}</dd>
        </div>
        <div className="rounded-control bg-surface px-3 py-2">
          <dt className="text-muted">正确答案</dt>
          <dd className="mt-0.5 font-mono text-[12px] text-fg">{choiceLabel(question.correctChoice)}</dd>
        </div>
      </dl>
      {question.explanation !== null ? (
        <div className="mt-2 rounded-control border-l-2 border-accent bg-surface px-3 py-2">
          <p className="text-[11px] font-medium text-muted">解析</p>
          <p className="mt-0.5 whitespace-pre-wrap break-words text-[12px] leading-relaxed text-fg">
            {question.explanation}
          </p>
        </div>
      ) : null}
    </li>
  );
}

// 只接受已提交批次的 attempt_id：提交前的页面不会拿到批次号，因此不会触发这个请求。
export function AttemptDetailPanel({ attemptId }: { attemptId: number }) {
  const [state, setState] = useState<DetailState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest<AttemptDetail>(attemptPath(attemptId), {
        parse: parseAttemptDetail,
      });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setState({ status: "error", failure: result.failure });
        return;
      }
      setState({ status: "ready", detail: result.data });
    })();
    return () => {
      active = false;
    };
  }, [attemptId, reloadToken]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setReloadToken((value) => value + 1);
  }, []);

  if (state.status === "loading") {
    return (
      <LoadingPanel
        title={"正在读取批次 #" + String(attemptId) + " 的逐题明细"}
        description={"GET " + attemptPath(attemptId) + "，只对已提交批次开放。"}
        rows={3}
      />
    );
  }

  if (state.status === "error") {
    return (
      <ErrorPanel
        failure={state.failure}
        title="逐题明细加载失败"
        onRetry={retry}
        extra={
          <p>
            接口 GET {attemptPath(attemptId)} 不可用时不会显示任何占位题目，也不会用本次页面上的草稿推断答案。
          </p>
        }
      />
    );
  }

  const { detail } = state;
  const groups = groupByDomain(detail.questions);

  if (groups.length === 0) {
    return (
      <Card>
        <CardHeader
          title={"逐题依据 · 批次 #" + String(attemptId)}
          description="该批次没有逐题明细数据。"
        />
        <CardBody>
          <EmptyState
            title="该批次没有逐题数据"
            description={
              "接口返回了批次 " +
              String(attemptId) +
              "，但不含任何题目条目；本页不会用其他批次的答案补齐，也不会展示推测结果。"
            }
          />
        </CardBody>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader
        title={"逐题依据 · 批次 #" + String(attemptId)}
        description={"来源 GET " + attemptPath(attemptId) + "；题号、题干、你的选择与正确答案均按接口返回展示。"}
        action={<Tag>{String(detail.totalCorrect ?? "—")} / {String(detail.totalQuestions ?? "—")} 题</Tag>}
      />
      <CardBody className="space-y-3">
        <dl className="grid grid-cols-2 gap-3 text-[11px] sm:grid-cols-4">
          <div>
            <dt className="text-muted">提交时间</dt>
            <dd className="mt-0.5 font-mono text-[12px] text-fg">{formatDateTime(detail.submittedAt)}</dd>
          </div>
          <div>
            <dt className="text-muted">题集版本</dt>
            <dd className="mt-0.5 font-mono text-[12px] text-fg">{detail.questionSetVersion}</dd>
          </div>
          <div>
            <dt className="text-muted">规则版本</dt>
            <dd className="mt-0.5 font-mono text-[12px] text-fg">{detail.ruleVersion}</dd>
          </div>
          <div>
            <dt className="text-muted">题目条目</dt>
            <dd className="mt-0.5 font-mono text-[12px] text-fg">{String(detail.questions.length)} 条</dd>
          </div>
        </dl>

        {groups.map((group) => (
          <div key={group.code === "" ? "group-unknown" : group.code} className="rounded-control border border-line">
            <div className="flex flex-wrap items-center gap-2 border-b border-line px-3 py-2">
              <p className="text-[12px] font-medium text-fg">
                {group.code === "" ? group.nameZh : domainName(group.code, group.nameZh)}
              </p>
              <span className="font-mono text-[11px] text-muted">{group.code === "" ? "—" : group.code}</span>
              <Tag>{String(group.questions.length)} 题</Tag>
            </div>
            <ul>
              {group.questions.map((question) => (
                <QuestionRow key={question.id} question={question} />
              ))}
            </ul>
          </div>
        ))}

        <div className="flex flex-wrap items-center gap-2">
          <Button variant="secondary" onClick={retry}>
            重新读取逐题明细
          </Button>
          <p className="text-[11px] leading-relaxed text-muted">
            逐题依据只对已提交批次开放；提交失败时保存的只是本机草稿，不会出现在这里。
          </p>
        </div>
      </CardBody>
    </Card>
  );
}
