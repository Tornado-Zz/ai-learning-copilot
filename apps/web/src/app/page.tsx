import type { Metadata } from "next";
import { TodayView } from "./today-view";

export const metadata: Metadata = {
  title: "今日概览",
};

export default function TodayPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <TodayView />
    </div>
  );
}
