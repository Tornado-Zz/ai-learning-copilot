import type { Metadata } from "next";
import { ExerciseView } from "./exercise-view";

// 题目 id 来自后端数据，构建期无法静态枚举；本路由按请求渲染（与 /learn/[id] 一致）。
export const instant = false;

export const metadata: Metadata = {
  title: "练习详情",
};

export default async function ExercisePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <ExerciseView exerciseId={id} />
    </div>
  );
}
