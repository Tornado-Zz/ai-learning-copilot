import type { Metadata } from "next";
import { ReviewView } from "./review-view";

export const metadata: Metadata = {
  title: "错题本",
};

export default function ReviewPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">错题本</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">错题本与间隔复习</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          答错自动进入复习，答对后按 1 / 3 / 7 / 14 天推进；每一行都来自后端已落库的复习项。
        </p>
      </header>
      <div className="mt-8">
        <ReviewView />
      </div>
    </div>
  );
}
