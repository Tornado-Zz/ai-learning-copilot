"use client";

import { useCallback, useState } from "react";
import { Button, Field, TextInput, fieldAria, fieldClass } from "@/components/form";
import { EMPTY_FIELD_ERRORS, SELF_CHECK_ITEMS, hasFieldErrors, validateDraft } from "@/lib/capstone";
import type { CapstoneFieldErrors, CapstoneSubmissionDraft } from "@/lib/capstone";

// 表单只镜像冻结契约的字段与限制，不改写用户输入：
// 「保存草稿」= POST/PATCH，「提交」= 先落库再 POST /submit（由父组件编排）。
// 自评清单是固定 4 项 + 一个共享备注：后端 self_checks 是 list[str]，
// 勾选项写 label 原文，备注写成「备注：…」的一条陈述（见 lib/capstone.ts）。

export function CapstoneSubmissionForm({
  initial,
  mode,
  busy,
  onSaveDraft,
  onSubmit,
  onCancelEdit,
}: {
  initial: CapstoneSubmissionDraft;
  mode: "create" | "edit";
  busy: boolean;
  onSaveDraft: (draft: CapstoneSubmissionDraft) => void;
  onSubmit: (draft: CapstoneSubmissionDraft) => void;
  onCancelEdit: () => void;
}) {
  const [draft, setDraft] = useState<CapstoneSubmissionDraft>(initial);
  const [errors, setErrors] = useState<CapstoneFieldErrors>(EMPTY_FIELD_ERRORS);

  const update = useCallback((patch: Partial<CapstoneSubmissionDraft>) => {
    setDraft((previous) => ({ ...previous, ...patch }));
  }, []);

  const toggleCheck = useCallback((key: string) => {
    setDraft((previous) => ({
      ...previous,
      selfChecks: previous.selfChecks.map((item) =>
        item.key === key ? { ...item, checked: !item.checked } : item,
      ),
    }));
  }, []);

  const handleSaveDraft = useCallback(() => {
    const next = validateDraft(draft);
    setErrors(next);
    if (hasFieldErrors(next)) {
      return;
    }
    onSaveDraft(draft);
  }, [draft, onSaveDraft]);

  const handleSubmit = useCallback(() => {
    const next = validateDraft(draft);
    setErrors(next);
    if (hasFieldErrors(next)) {
      return;
    }
    onSubmit(draft);
  }, [draft, onSubmit]);

  const checkedCount = draft.selfChecks.filter((item) => item.checked).length;

  return (
    <div className="space-y-5">
      <Field
        id="capstone-title"
        label="标题（1–120 个字符）"
        hint="一句话说清这件作品做了什么。"
        error={errors.title}
      >
        <div className="space-y-1">
          <TextInput
            id="capstone-title"
            value={draft.title}
            maxLength={120}
            placeholder="例如：本地学习助手 v1"
            invalid={errors.title !== null}
            {...fieldAria("capstone-title", errors.title, true)}
            onChange={(event) => {
              update({ title: event.target.value });
              setErrors((previous) => ({ ...previous, title: null }));
            }}
          />
          <p className="text-right font-mono text-[11px] text-muted">
            {draft.title.trim().length} / 120
          </p>
        </div>
      </Field>

      <Field
        id="capstone-summary"
        label="作品简介（1–4000 个字符）"
        hint="解决的问题、关键功能、你最有把握的部分。"
        error={errors.summary}
      >
        <div className="space-y-1">
          <textarea
            id="capstone-summary"
            rows={4}
            value={draft.summary}
            maxLength={4000}
            aria-invalid={errors.summary ? true : undefined}
            aria-describedby={
              errors.summary ? "capstone-summary-error" : "capstone-summary-hint"
            }
            onChange={(event) => {
              update({ summary: event.target.value });
              setErrors((previous) => ({ ...previous, summary: null }));
            }}
            className={fieldClass(errors.summary !== null) + " leading-5"}
          />
          <p className="text-right font-mono text-[11px] text-muted">
            {draft.summary.trim().length} / 4000
          </p>
        </div>
      </Field>

      <Field
        id="capstone-repo-url"
        label="仓库链接（可选，最多 300 字符）"
        hint="留空表示不公开仓库；填了就必须以 http:// 或 https:// 开头。"
        error={errors.repoUrl}
      >
        <TextInput
          id="capstone-repo-url"
          value={draft.repoUrl}
          maxLength={300}
          placeholder="https://example.com/your-repo"
          invalid={errors.repoUrl !== null}
          {...fieldAria("capstone-repo-url", errors.repoUrl, true)}
          onChange={(event) => {
            update({ repoUrl: event.target.value });
            setErrors((previous) => ({ ...previous, repoUrl: null }));
          }}
        />
      </Field>

      <Field
        id="capstone-run-instructions"
        label="运行说明（1–4000 个字符）"
        hint="依赖、启动命令、需要的环境变量；照着这几行应当能从零跑起来。"
        error={errors.runInstructions}
      >
        <div className="space-y-1">
          <textarea
            id="capstone-run-instructions"
            rows={5}
            value={draft.runInstructions}
            maxLength={4000}
            aria-invalid={errors.runInstructions ? true : undefined}
            aria-describedby={
              errors.runInstructions
                ? "capstone-run-instructions-error"
                : "capstone-run-instructions-hint"
            }
            onChange={(event) => {
              update({ runInstructions: event.target.value });
              setErrors((previous) => ({ ...previous, runInstructions: null }));
            }}
            className={fieldClass(errors.runInstructions !== null) + " font-mono text-[12px] leading-5"}
          />
          <p className="text-right font-mono text-[11px] text-muted">
            {draft.runInstructions.trim().length} / 4000
          </p>
        </div>
      </Field>

      <div className="space-y-3 rounded-control border border-line bg-surface px-4 py-3">
        <div>
          <p id="capstone-selfchecks-label" className="text-[12px] font-medium text-fg">
            自评清单（固定 4 项，勾选符合的项 + 备注）
          </p>
          <p id="capstone-selfchecks-hint" className="mt-1 text-[11px] leading-relaxed text-muted">
            清单是提交前自检：不勾选不会阻止提交；记录里只保存勾选的项与下面的备注。
          </p>
        </div>

        <ul role="group" aria-labelledby="capstone-selfchecks-label" aria-describedby="capstone-selfchecks-hint" className="space-y-2">
          {draft.selfChecks.map((item) => (
            <li key={item.key}>
              <label
                htmlFor={"capstone-selfcheck-" + item.key}
                className={
                  "flex cursor-pointer items-start gap-2.5 rounded-control border px-3 py-2.5 text-[12px] transition-colors " +
                  (item.checked
                    ? "border-accent bg-accent-soft text-fg"
                    : "border-line bg-canvas text-fg hover:bg-elevated")
                }
              >
                <input
                  id={"capstone-selfcheck-" + item.key}
                  type="checkbox"
                  checked={item.checked}
                  onChange={() => toggleCheck(item.key)}
                  className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]"
                />
                <span className="min-w-0 flex-1 leading-relaxed">{item.label}</span>
              </label>
            </li>
          ))}
        </ul>

        <div className="space-y-1.5">
          <label htmlFor="capstone-self-note" className="block text-[12px] font-medium text-fg">
            备注（可选）
          </label>
          <textarea
            id="capstone-self-note"
            rows={3}
            value={draft.selfNote}
            maxLength={500}
            placeholder="哪一项没把握、为什么；会作为「备注：…」一条写进 self_checks。"
            onChange={(event) => update({ selfNote: event.target.value })}
            className={fieldClass(false) + " leading-5"}
          />
        </div>

        <p className="text-[11px] leading-relaxed text-muted">
          当前已勾选 {checkedCount} / {SELF_CHECK_ITEMS.length} 项。
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-3 border-t border-line pt-4">
        <Button variant="secondary" onClick={handleSaveDraft} disabled={busy}>
          保存草稿
        </Button>
        <Button variant="primary" onClick={handleSubmit} disabled={busy}>
          提交
        </Button>
        {mode === "edit" ? (
          <Button variant="quiet" onClick={onCancelEdit} disabled={busy}>
            取消编辑
          </Button>
        ) : null}
      </div>

      <p className="text-[11px] leading-relaxed text-muted">
        「提交」会把草稿先落库再调用 POST /submit：readiness 快照与 submitted_at 由后端在同一事务写入。
        未达标不会阻止提交，界面也不会替你判断达标与否。
      </p>
    </div>
  );
}
