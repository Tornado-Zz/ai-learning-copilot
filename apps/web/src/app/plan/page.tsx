import type { Metadata } from "next";
import { PlanView } from "./plan-view";

export const metadata: Metadata = {
  title: "周计划",
};

export default function PlanPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">周计划</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">本周学习计划</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          每天按你的可用分钟排入课程与练习；点标题直接进入该项。
        </p>
      </header>
      <div className="mt-8">
        <PlanView />
      </div>
    </div>
  );
}
