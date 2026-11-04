import type { Metadata } from "next";
import { DiagnosticFlow } from "./diagnostic-flow";

export const metadata: Metadata = {
  title: "能力诊断",
};

export default function DiagnosticPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">学习流程 · 第 2 步</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">能力诊断（20 题）</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          题型包含单选、代码阅读与改错，覆盖 6 个技能域。每次作答都会写入本机草稿，刷新或关闭页面后回来可以继续。
        </p>
      </header>
      <div className="mt-8">
        <DiagnosticFlow />
      </div>
    </div>
  );
}
