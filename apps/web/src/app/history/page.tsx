import type { Metadata } from "next";
import { HistoryView } from "./history-view";

export const metadata: Metadata = {
  title: "历史结果",
};

export default function HistoryPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">学习流程 · 历史记录</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">历史诊断结果</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          诊断批次是追加式记录：同一次诊断请求的重试（同一 attempt_token）不会重复产生批次；重新参加诊断会新增批次并保留历史。点开任意一行可以查看该批次的六域明细。
        </p>
      </header>
      <div className="mt-8">
        <HistoryView />
      </div>
    </div>
  );
}
