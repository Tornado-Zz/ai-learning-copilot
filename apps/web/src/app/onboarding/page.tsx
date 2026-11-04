import type { Metadata } from "next";
import { ProfileForm } from "./profile-form";

export const metadata: Metadata = {
  title: "学习档案",
};

export default function OnboardingPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">学习流程 · 第 1 步</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">填写学习档案</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          学习日与每天可投入的时长决定计划容量；时区决定「今天 / 本周」的计算边界，必须显式确认后才会用于任何按周或按天的推导。
        </p>
      </header>
      <div className="mt-8 max-w-3xl">
        <ProfileForm />
      </div>
    </div>
  );
}
