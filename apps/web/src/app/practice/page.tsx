import type { Metadata } from "next";
import { PracticeView } from "./practice-view";

export const metadata: Metadata = {
  title: "练习",
};

export default function PracticePage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">练习 · 静态规则与自检</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">练习</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          按课程分组；判题只做静态规则比对与自检申报，系统不会执行你提交的代码。
        </p>
      </header>
      <div className="mt-8">
        <PracticeView />
      </div>
    </div>
  );
}
