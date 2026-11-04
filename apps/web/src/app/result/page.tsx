import type { Metadata } from "next";
import { ResultView } from "./result-view";

export const metadata: Metadata = {
  title: "诊断结果",
};

export default function ResultPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">学习流程 · 第 3 步</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">六维诊断结果</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          这是学习起点评估，不是能力认证。每个技能域给出等级、评估状态、本次诊断的正确率与判定依据；没有证据的域不会推测等级。
          <br />
          下面的等级是<strong className="font-medium text-fg">本次诊断</strong>的结论：未达门槛的域会显示 L0「已测未达标」，但<strong className="font-medium text-fg">不会降低你此前已建立的等级</strong>——当前等级以「进度」页为准。
        </p>
      </header>
      <div className="mt-8">
        <ResultView />
      </div>
    </div>
  );
}
