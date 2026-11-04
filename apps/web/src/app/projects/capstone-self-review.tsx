"use client";

import { useCallback, useState } from "react";
import { Button, ChoiceOption, fieldClass } from "@/components/form";
import type { CapstoneVerdict } from "@/lib/capstone";

// 自评流程（reviewer = self）。三个前端门槛，与后端一一对应：
// 1) verdict 必须是 pass / needs_work（否则后端 422）；
// 2) 必须勾选确认框，提交时带 self_review_confirmed=true（否则后端 400 SELF_REVIEW_NOT_CONFIRMED）；
// 3) 只有 status='submitted' 的作品才渲染本面板（否则后端 409 CAPSTONE_INVALID_STATE）。
// 未满足 1)、2) 时按钮 disabled，并在按钮上方说明原因，用户不需要点一次才知道为什么。

export const SELF_REVIEW_CONFIRM_TEXT = "我确认这是本人自评，不是第三方评审";

export function CapstoneSelfReviewPanel({
  busy,
  onReview,
}: {
  busy: boolean;
  onReview: (input: { verdict: CapstoneVerdict; note: string }) => void;
}) {
  const [verdict, setVerdict] = useState<CapstoneVerdict | null>(null);
  const [note, setNote] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const disabledReason =
    verdict === null
      ? "先选择自评结论（通过 / 需要改进）才能提交。"
      : !confirmed
        ? "未勾选确认前不能提交：后端同样会返回 400 SELF_REVIEW_NOT_CONFIRMED。"
        : null;

  const submit = useCallback(() => {
    if (busy || verdict === null || !confirmed) {
      return;
    }
    onReview({ verdict, note });
  }, [busy, verdict, confirmed, note, onReview]);

  return (
    <div className="space-y-3 rounded-control border border-line-strong bg-surface px-4 py-4">
      <div>
        <p className="text-[12px] font-medium text-fg">自评（reviewer = self）</p>
        <p className="mt-1 text-[11px] leading-relaxed text-muted">
          结论由你本人给出，不经过任何第三方；后端会写入 reviewer=&apos;self&apos; 与 reviewed_at。
        </p>
      </div>

      <div role="radiogroup" aria-label="自评结论" className="space-y-2">
        <ChoiceOption
          id="capstone-verdict-pass"
          name="capstone-verdict"
          value="pass"
          checked={verdict === "pass"}
          onChange={() => setVerdict("pass")}
          disabled={busy}
          label={<span>通过：作品达到我在学习计划里设定的目标</span>}
        />
        <ChoiceOption
          id="capstone-verdict-needs-work"
          name="capstone-verdict"
          value="needs_work"
          checked={verdict === "needs_work"}
          onChange={() => setVerdict("needs_work")}
          disabled={busy}
          label={<span>需要改进：还差一步，我会继续迭代</span>}
        />
      </div>

      <div className="space-y-1.5">
        <label htmlFor="capstone-review-note" className="block text-[12px] font-medium text-fg">
          自评备注（可选）
        </label>
        <textarea
          id="capstone-review-note"
          rows={3}
          value={note}
          maxLength={2000}
          placeholder="写下这次自评的依据，或下一步要补的部分。"
          onChange={(event) => setNote(event.target.value)}
          className={fieldClass(false) + " leading-5"}
        />
      </div>

      <label htmlFor="capstone-self-review-confirmed" className="flex cursor-pointer items-start gap-2.5">
        <input
          id="capstone-self-review-confirmed"
          type="checkbox"
          checked={confirmed}
          onChange={(event) => setConfirmed(event.target.checked)}
          className="mt-0.5 size-3.5 shrink-0 accent-[var(--accent)]"
        />
        <span className="min-w-0 text-[12px] leading-relaxed text-fg">{SELF_REVIEW_CONFIRM_TEXT}</span>
      </label>

      {disabledReason ? (
        <p role="status" aria-live="polite" className="text-[11px] leading-relaxed text-muted">
          {disabledReason}
        </p>
      ) : (
        <p role="status" aria-live="polite" className="text-[11px] leading-relaxed text-muted">
          已确认这是本人自评，可以写入结论。
        </p>
      )}

      <Button variant="primary" onClick={submit} disabled={disabledReason !== null || busy}>
        {busy ? "正在写入自评…" : "提交自评"}
      </Button>
    </div>
  );
}
