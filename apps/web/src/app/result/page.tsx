import type { Metadata } from "next";
import { ResultView } from "./result-view";

export const metadata: Metadata = {
  title: "诊断结果",
};

export default function ResultPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">Sprint 1 · 第 3 步</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">六维诊断结果</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          这是学习起点评估，不是能力认证。每个技能域给出等级、评估状态、本次诊断的正确率与判定依据；没有证据的域不会推测等级。
        </p>
      </header>
      <div className="mt-8">
        <ResultView />
      </div>
    </div>
  );
}
