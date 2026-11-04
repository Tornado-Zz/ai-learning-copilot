import type { Metadata } from "next";
import { LearnView } from "./learn-view";

export const metadata: Metadata = {
  title: "学习路线",
};

export default function LearnPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">路线 A · 六阶段</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">学习路线</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          阶段状态只来自能力诊断；没有评估记录的阶段保持「尚未评估」，本页不推测等级。
        </p>
      </header>
      <div className="mt-8">
        <LearnView />
      </div>
    </div>
  );
}
