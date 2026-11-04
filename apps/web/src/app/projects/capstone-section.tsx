"use client";

import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/form";
import { Alert, EmptyState, ErrorPanel, LoadingPanel } from "@/components/states";
import { Card, CardBody, CardHeader, MetaRow, Tag } from "@/components/ui";
import { apiRequest } from "@/lib/http";
import type { ApiFailure } from "@/lib/http";
import { formatDateTime } from "@/lib/labels";
import { CapstoneSubmissionForm } from "./capstone-form";
import { CapstoneSelfReviewPanel } from "./capstone-self-review";
import {
  CAPSTONE_SUBMISSIONS_PATH,
  DASH,
  capstoneFailureHint,
  capstoneItemPath,
  capstoneListPath,
  capstoneReviewPath,
  capstoneSubmitPath,
  draftFromSubmission,
  emptyDraft,
  parseMutationResult,
  parseSubmissionEnvelope,
  parseSubmissionList,
  reviewerLabel,
  splitSelfChecks,
  statusLabel,
  toSubmissionBody,
  verdictLabel,
} from "@/lib/capstone";
import type {
  CapstoneStatus,
  CapstoneSubmission,
  CapstoneSubmissionDraft,
  CapstoneVerdict,
} from "@/lib/capstone";

// v0.1.3 · 结业作品提交区块（在 /projects 页内，不新建页面）
//
// 状态机（后端是唯一权威，前端只在成功后按 GET 结果重绘）：
//   draft      —— 可编辑（PATCH）、可提交（POST /submit，同事务写 readiness_snapshot + submitted_at）
//   submitted  —— 不可编辑；可自评（POST /review，reviewer='self'）
//   reviewed   —— 终态，仅展示自评结论、备注与时间
//
// 诚实性：单用户本地版本没有第三方评审者，所有结论都是本人自评。
// 界面固定说明这一点，且不使用「通过审核 / 官方认证」这类措辞。

type ListState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; items: CapstoneSubmission[]; total: number | null };

type DetailState =
  | { status: "loading" }
  | { status: "error"; failure: ApiFailure }
  | { status: "ready"; submission: CapstoneSubmission };

type ActionState =
  | { status: "idle" }
  | { status: "busy"; label: string }
  | { status: "error"; title: string; failure: ApiFailure }
  | { status: "done"; message: string };

type FormMode = { kind: "create" } | { kind: "edit"; submission: CapstoneSubmission };

function statusTone(status: CapstoneStatus | null): "neutral" | "accent" | "success" {
  if (status === "reviewed") {
    return "success";
  }
  if (status === "submitted") {
    return "accent";
  }
  return "neutral";
}

function textOrDash(value: string | null): string {
  return value === null ? DASH : value;
}

function numberOrDash(value: number | null): string {
  return value === null ? DASH : String(value);
}

function SubmissionDetail({
  state,
  busy,
  onClose,
  onEdit,
  onReview,
  onRetry,
}: {
  state: DetailState;
  busy: boolean;
  onClose: () => void;
  onEdit: (id: number) => void;
  onReview: (id: number, input: { verdict: CapstoneVerdict; note: string }) => void;
  onRetry: () => void;
}) {
  return (
    <div className="space-y-3 rounded-control border border-line-strong bg-surface px-4 py-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-[12px] font-medium text-fg">
          作品详情{state.status === "ready" ? " #" + String(state.submission.id) : ""}
        </p>
        <Button variant="quiet" onClick={onClose}>
          关闭
        </Button>
      </div>

      {state.status === "loading" ? (
        <LoadingPanel title="正在读取作品详情" description="GET /api/v1/capstone/submissions/{id}" rows={3} />
      ) : null}

      {state.status === "error" ? (
        <ErrorPanel
          failure={state.failure}
          title="作品详情加载失败"
          onRetry={onRetry}
          extra={
            capstoneFailureHint(state.failure) ? (
              <p>{capstoneFailureHint(state.failure)}</p>
            ) : null
          }
        />
      ) : null}

      {state.status === "ready" ? (
        <SubmissionDetailBody
          submission={state.submission}
          busy={busy}
          onEdit={onEdit}
          onReview={onReview}
        />
      ) : null}
    </div>
  );
}

function SubmissionDetailBody({
  submission,
  busy,
  onEdit,
  onReview,
}: {
  submission: CapstoneSubmission;
  busy: boolean;
  onEdit: (id: number) => void;
  onReview: (id: number, input: { verdict: CapstoneVerdict; note: string }) => void;
}) {
  const snapshot = submission.readinessSnapshot;
  const { labels: selfCheckLabels, note: selfCheckNote } = splitSelfChecks(submission.selfChecks);
  const repositoryUrl =
    submission.repoUrl !== null && /^https?:\/\//i.test(submission.repoUrl) ? submission.repoUrl : null;

  return (
    <div className="space-y-4">
      <dl className="text-[12px]">
        <MetaRow label="状态">
          <Tag tone={statusTone(submission.status)}>{statusLabel(submission.status)}</Tag>
        </MetaRow>
        <MetaRow label="创建时间">{formatDateTime(submission.createdAt)}</MetaRow>
        <MetaRow label="更新时间">{formatDateTime(submission.updatedAt)}</MetaRow>
        <MetaRow label="提交时间">{formatDateTime(submission.submittedAt)}</MetaRow>
        {submission.status === "reviewed" ? (
          <>
            <MetaRow label="自评时间">{formatDateTime(submission.reviewedAt)}</MetaRow>
            <MetaRow label="自评结论">
              {submission.verdict === null ? DASH : verdictLabel(submission.verdict) + "（自评）"}
            </MetaRow>
            <MetaRow label="自评人">{reviewerLabel(submission.reviewer)}</MetaRow>
          </>
        ) : null}
      </dl>

      <div>
        <p className="text-[11px] text-muted">标题</p>
        <p className="mt-0.5 text-[12px] leading-relaxed text-fg">{textOrDash(submission.title)}</p>
      </div>

      <div>
        <p className="text-[11px] text-muted">作品简介</p>
        <p className="mt-0.5 whitespace-pre-wrap text-[12px] leading-relaxed text-fg">
          {textOrDash(submission.summary)}
        </p>
      </div>

      <div>
        <p className="text-[11px] text-muted">仓库链接</p>
        {repositoryUrl !== null ? (
          <a
            href={repositoryUrl}
            target="_blank"
            rel="noreferrer noopener"
            className="mt-0.5 break-all text-[12px] leading-relaxed text-accent underline"
          >
            {repositoryUrl}
          </a>
        ) : (
          <p className="mt-0.5 break-all text-[12px] leading-relaxed text-fg">
            {submission.repoUrl === null
              ? DASH
              : submission.repoUrl + "（不是 http(s) 链接，仅显示原文，不渲染为可点击链接）"}
          </p>
        )}
      </div>

      <div>
        <p className="text-[11px] text-muted">运行说明</p>
        <p className="mt-0.5 whitespace-pre-wrap font-mono text-[12px] leading-5 text-fg">
          {textOrDash(submission.runInstructions)}
        </p>
      </div>

      <div>
        <p className="text-[11px] text-muted">自评清单（self_checks，提交时勾选的项 + 备注）</p>
        {submission.selfChecks === null ? (
          <p className="mt-0.5 text-[12px] leading-relaxed text-fg">{DASH}</p>
        ) : selfCheckLabels.length === 0 && selfCheckNote === null ? (
          <p className="mt-0.5 text-[12px] leading-relaxed text-muted">
            记录里是空数组 self_checks=[]：提交时没有勾选任何自检项，也没有写备注。
          </p>
        ) : (
          <div className="mt-1 space-y-1">
            {selfCheckLabels.length > 0 ? (
              <ul className="space-y-1">
                {selfCheckLabels.map((label, index) => (
                  <li key={label + "#" + String(index)} className="text-[12px] leading-relaxed text-fg">
                    <span className="font-mono text-muted">·</span>
                    <span className="ml-2">{label}</span>
                  </li>
                ))}
              </ul>
            ) : null}
            <p className="text-[12px] leading-relaxed text-fg">备注：{selfCheckNote ?? DASH}</p>
          </div>
        )}
      </div>

      <div>
        <p className="text-[11px] text-muted">
          提交时的达标快照（提交瞬间的四条要求，非实时；未达标不影响提交）
        </p>
        {snapshot === null ? (
          <p className="mt-0.5 text-[12px] leading-relaxed text-fg">
            {DASH}
            {submission.status === "draft" ? "（草稿尚未提交，后端在 /submit 时才写 snapshot）" : ""}
          </p>
        ) : (
          <div className="mt-1 space-y-1">
            <p className="text-[12px] leading-relaxed text-fg">
              {snapshot.ready === null
                ? "快照未返回 ready 字段。"
                : snapshot.ready
                  ? "快照记录：四条要求已全部满足。"
                  : "快照记录：仍有要求未满足（后端不因此拒绝提交）。"}
            </p>
            {snapshot.requirements === null ? (
              <p className="text-[11px] leading-relaxed text-muted">快照里没有 requirements 数组。</p>
            ) : (
              <ul className="space-y-1">
                {snapshot.requirements.map((row) => (
                  <li
                    key={row.key}
                    className="flex flex-wrap items-center justify-between gap-2 text-[11px]"
                  >
                    <span className="min-w-0 text-fg">{row.label ?? row.key}</span>
                    <span className="shrink-0 font-mono text-muted">
                      {numberOrDash(row.actual) + " / " + numberOrDash(row.required)}
                      {row.met === null ? " · 未返回" : row.met ? " · 已达标" : " · 未达标"}
                    </span>
                  </li>
                ))}
              </ul>
            )}
            {snapshot.note ? (
              <p className="text-[11px] leading-relaxed text-muted">{snapshot.note}</p>
            ) : null}
          </div>
        )}
      </div>

      {submission.status === "reviewed" ? (
        <div className="rounded-control border border-line bg-canvas px-3 py-2">
          <p className="text-[11px] text-muted">
            自评备注（reviewer = {reviewerLabel(submission.reviewer)}）
          </p>
          <p className="mt-0.5 whitespace-pre-wrap text-[12px] leading-relaxed text-fg">
            {textOrDash(submission.reviewerNote)}
          </p>
        </div>
      ) : null}

      {submission.status === "draft" ? (
        <div className="flex flex-wrap items-center gap-3 border-t border-line pt-3">
          <Button variant="secondary" onClick={() => onEdit(submission.id)} disabled={busy}>
            编辑草稿
          </Button>
          <p className="text-[11px] leading-relaxed text-muted">
            草稿可以继续修改；提交后不可再改（后端对非 draft 的 PATCH 返回 409）。
          </p>
        </div>
      ) : null}

      {submission.status === "submitted" ? (
        <CapstoneSelfReviewPanel
          key={"self-review-" + String(submission.id)}
          busy={busy}
          onReview={(input) => onReview(submission.id, input)}
        />
      ) : null}

      {submission.status === null ? (
        <Alert tone="warning" title="状态字段缺失或不在冻结枚举内">
          <p>后端返回的 status 不是 draft / submitted / reviewed，页面不提供任何状态流转按钮。</p>
        </Alert>
      ) : null}
    </div>
  );
}

export function CapstoneSection() {
  const [listState, setListState] = useState<ListState>({ status: "loading" });
  const [reloadToken, setReloadToken] = useState(0);
  const [detail, setDetail] = useState<{ id: number; state: DetailState } | null>(null);
  const [formMode, setFormMode] = useState<FormMode>({ kind: "create" });
  const [formKey, setFormKey] = useState(0);
  const [action, setAction] = useState<ActionState>({ status: "idle" });

  useEffect(() => {
    let active = true;
    void (async () => {
      const result = await apiRequest(capstoneListPath(), { parse: parseSubmissionList });
      if (!active) {
        return;
      }
      if (!result.ok) {
        setListState({ status: "error", failure: result.failure });
        return;
      }
      setListState({ status: "ready", items: result.data.items, total: result.data.total });
    })();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const refresh = useCallback(() => {
    setReloadToken((value) => value + 1);
  }, []);

  const loadDetail = useCallback(async (id: number) => {
    setDetail({ id, state: { status: "loading" } });
    const result = await apiRequest(capstoneItemPath(id), { parse: parseSubmissionEnvelope });
    if (!result.ok) {
      setDetail({ id, state: { status: "error", failure: result.failure } });
      return;
    }
    setDetail({ id, state: { status: "ready", submission: result.data } });
  }, []);

  const openDetail = useCallback(
    (id: number) => {
      if (detail !== null && detail.id === id) {
        setDetail(null);
        return;
      }
      void loadDetail(id);
    },
    [detail, loadDetail],
  );

  const startEdit = useCallback(async (id: number) => {
    setAction({ status: "busy", label: "正在读取草稿…" });
    const result = await apiRequest(capstoneItemPath(id), { parse: parseSubmissionEnvelope });
    if (!result.ok) {
      setAction({ status: "error", title: "读取草稿失败", failure: result.failure });
      return;
    }
    setFormMode({ kind: "edit", submission: result.data });
    setFormKey((value) => value + 1);
    setDetail(null);
    setAction({ status: "idle" });
  }, []);

  const cancelEdit = useCallback(() => {
    setFormMode({ kind: "create" });
    setFormKey((value) => value + 1);
    setAction({ status: "idle" });
  }, []);

  const saveDraft = useCallback(
    async (draft: CapstoneSubmissionDraft, thenSubmit: boolean) => {
      const editId = formMode.kind === "edit" ? formMode.submission.id : null;
      setAction({ status: "busy", label: thenSubmit ? "正在提交…" : "正在保存草稿…" });
      const body = toSubmissionBody(draft);

      let targetId: number;
      if (editId === null) {
        const created = await apiRequest(CAPSTONE_SUBMISSIONS_PATH, {
          method: "POST",
          body,
          parse: parseSubmissionEnvelope,
        });
        if (!created.ok) {
          setAction({ status: "error", title: "保存草稿失败", failure: created.failure });
          return;
        }
        targetId = created.data.id;
      } else {
        const patched = await apiRequest(capstoneItemPath(editId), {
          method: "PATCH",
          body,
          parse: parseMutationResult,
        });
        if (!patched.ok) {
          setAction({ status: "error", title: "保存草稿失败", failure: patched.failure });
          return;
        }
        targetId = patched.data.kind === "submission" ? patched.data.submission.id : editId;
      }

      let message =
        editId === null
          ? "草稿已保存（id=" + String(targetId) + "）。"
          : "草稿已更新（id=" + String(targetId) + "）。";

      if (thenSubmit) {
        const submitted = await apiRequest(capstoneSubmitPath(targetId), {
          method: "POST",
          parse: parseMutationResult,
        });
        if (!submitted.ok) {
          setAction({ status: "error", title: "提交失败", failure: submitted.failure });
          refresh();
          void loadDetail(targetId);
          return;
        }
        message =
          "已提交（id=" +
          String(targetId) +
          "）：readiness 快照与 submitted_at 由后端在同一事务写入；未达标不会阻止提交。";
      }

      setFormMode({ kind: "create" });
      setFormKey((value) => value + 1);
      setAction({ status: "done", message });
      refresh();
      void loadDetail(targetId);
    },
    [formMode, loadDetail, refresh],
  );

  const reviewSubmission = useCallback(
    async (id: number, input: { verdict: CapstoneVerdict; note: string }) => {
      setAction({ status: "busy", label: "正在写入自评…" });
      const note = input.note.trim();
      const result = await apiRequest(capstoneReviewPath(id), {
        method: "POST",
        body: {
          verdict: input.verdict,
          note: note === "" ? undefined : note,
          self_review_confirmed: true,
        },
        parse: parseMutationResult,
      });
      if (!result.ok) {
        setAction({ status: "error", title: "自评写入失败", failure: result.failure });
        return;
      }
      setAction({
        status: "done",
        message: "自评结论已写入（reviewer='self'，由你本人给出，不构成外部认证）。",
      });
      refresh();
      void loadDetail(id);
    },
    [loadDetail, refresh],
  );

  const busy = action.status === "busy";

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader
          title="结业作品提交"
          description="草稿 → 已提交 → 已自评。提交不因 readiness 未达标而失败，达标情况以提交时的快照记录。"
          action={<Tag>{formMode.kind === "edit" ? "编辑草稿 #" + String(formMode.submission.id) : "新建草稿"}</Tag>}
        />
        <CardBody className="space-y-5">
          <Alert tone="warning" title="关于「评审」的说明">
            <p>
              单用户本地版本没有第三方评审者；这里的结论是
              <strong className="font-medium text-fg">自评</strong>，不构成外部认证。
            </p>
          </Alert>

          {action.status === "busy" ? (
            <p aria-live="polite" className="text-[11px] leading-relaxed text-muted">
              {action.label}
            </p>
          ) : null}

          {action.status === "done" ? (
            <Alert tone="accent" title="操作完成">
              <p>{action.message}</p>
            </Alert>
          ) : null}

          {action.status === "error" ? (
            <ErrorPanel
              failure={action.failure}
              title={action.title}
              extra={
                capstoneFailureHint(action.failure) ? (
                  <p>{capstoneFailureHint(action.failure)}</p>
                ) : null
              }
            />
          ) : null}

          <CapstoneSubmissionForm
            key={formKey}
            mode={formMode.kind === "edit" ? "edit" : "create"}
            initial={
              formMode.kind === "edit" ? draftFromSubmission(formMode.submission) : emptyDraft()
            }
            busy={busy}
            onSaveDraft={(draft) => void saveDraft(draft, false)}
            onSubmit={(draft) => void saveDraft(draft, true)}
            onCancelEdit={cancelEdit}
          />
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="提交记录"
          description="GET /api/v1/capstone/submissions?limit=20，按 created_at DESC, id DESC。"
          action={
            <Tag>
              {listState.status === "ready"
                ? "共 " + String(listState.total ?? listState.items.length) + " 条"
                : "读取中"}
            </Tag>
          }
        />
        <CardBody className="space-y-4">
          {listState.status === "loading" ? (
            <LoadingPanel
              title="正在读取提交记录"
              description="列表与详情都以服务端返回为准，前端不做本地排序或状态推断。"
              rows={3}
            />
          ) : null}

          {listState.status === "error" ? (
            <ErrorPanel
              failure={listState.failure}
              title="提交记录加载失败"
              onRetry={refresh}
              extra={
                capstoneFailureHint(listState.failure) ? (
                  <p>{capstoneFailureHint(listState.failure)}</p>
                ) : (
                  <p>四条要求的达标情况仍可正常查看；作品提交依赖后端 0009 路由。</p>
                )
              }
            />
          ) : null}

          {listState.status === "ready" && listState.items.length === 0 ? (
            <EmptyState
              title="还没有提交记录"
              description="在上面的表单里填写并保存草稿或直接提交，记录会按创建时间倒序出现在这里。"
            />
          ) : null}

          {listState.status === "ready" && listState.items.length > 0 ? (
            <ul className="divide-y divide-line">
              {listState.items.map((item) => (
                <li
                  key={item.id}
                  className="flex flex-wrap items-start justify-between gap-3 py-3 first:pt-0 last:pb-0"
                >
                  <div className="min-w-0 space-y-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="text-[12px] font-medium text-fg">{textOrDash(item.title)}</span>
                      <Tag tone={statusTone(item.status)}>{statusLabel(item.status)}</Tag>
                      {item.status === "reviewed" ? (
                        <Tag>自评：{verdictLabel(item.verdict)}</Tag>
                      ) : null}
                    </div>
                    <p className="text-[11px] leading-relaxed text-muted">
                      创建 {formatDateTime(item.createdAt)} · 提交 {formatDateTime(item.submittedAt)}
                      {item.status === "reviewed"
                        ? " · 自评 " + formatDateTime(item.reviewedAt)
                        : ""}
                    </p>
                  </div>
                  <div className="flex shrink-0 items-center gap-2">
                    <Button variant="quiet" onClick={() => openDetail(item.id)}>
                      {detail !== null && detail.id === item.id ? "收起详情" : "查看详情"}
                    </Button>
                    {item.status === "draft" ? (
                      <Button variant="secondary" onClick={() => void startEdit(item.id)} disabled={busy}>
                        编辑草稿
                      </Button>
                    ) : null}
                    {item.status === "submitted" ? (
                      <Button variant="primary" onClick={() => openDetail(item.id)}>
                        自评
                      </Button>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          ) : null}

          {detail !== null ? (
            <SubmissionDetail
              state={detail.state}
              busy={busy}
              onClose={() => setDetail(null)}
              onEdit={(id) => void startEdit(id)}
              onReview={(id, input) => void reviewSubmission(id, input)}
              onRetry={() => void loadDetail(detail.id)}
            />
          ) : null}
        </CardBody>
      </Card>

      <p className="text-[11px] leading-relaxed text-muted">
        本版本所有结论都写在 reviewer=&apos;self&apos; 的记录里（本人自评），不存在第三方评审者；
        状态与时间一律以服务端返回为准，前端只在成功后按 GET 结果重绘。
      </p>
    </div>
  );
}
