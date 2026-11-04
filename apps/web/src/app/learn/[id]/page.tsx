import type { Metadata } from "next";
import { LessonDetailView } from "./lesson-detail-view";

// 课程 id 来自后端数据，无法在构建期静态枚举；本路由按请求渲染（Next 16 cacheComponents 的阻塞路由开关）。
export const instant = false;

export const metadata: Metadata = {
  title: "课程详情",
};

export default async function LessonPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <LessonDetailView lessonId={id} />
    </div>
  );
}
