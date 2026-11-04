import type { Metadata } from "next";
import { ProgressView } from "./progress-view";

export const metadata: Metadata = {
  title: "学习进度",
};

export default function ProgressPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">进度 · 课程 / 计划 / 练习 / 能力</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">学习进度</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          四块数据全部来自 GET /api/v1/progress/overview 的真实聚合；响应里没有的字段显示
          「—」，不补零、不估算。
        </p>
      </header>
      <div className="mt-8">
        <ProgressView />
      </div>
    </div>
  );
}
