import type { Metadata } from "next";
import { ProjectsView } from "./projects-view";

export const metadata: Metadata = {
  title: "项目实践",
};

export default function ProjectsPage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">项目实践 · 结业作品</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">项目实践</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-muted">
          GET /api/v1/capstone/readiness 用真实学习数据判定是否具备做结业作品的条件；
          提交与人工评审流程尚未实现，说明以后端返回为准。
        </p>
      </header>
      <div className="mt-8">
        <ProjectsView />
      </div>
    </div>
  );
}
