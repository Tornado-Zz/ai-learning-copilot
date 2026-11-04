import type { Metadata } from "next";
import { KNOWLEDGE_PAGE_NOTICE } from "@/lib/knowledge";
import { KnowledgeView } from "./knowledge-view";

export const metadata: Metadata = {
  title: "知识检索",
};

export default function KnowledgePage() {
  return (
    <div className="mx-auto w-full max-w-content px-4 py-8 md:px-8 md:py-10">
      <header className="border-b border-line pb-6">
        <p className="text-[12px] font-medium text-muted">学习空间 · 知识库</p>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-fg">知识检索</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-fg">{KNOWLEDGE_PAGE_NOTICE}</p>
        <p className="mt-2 max-w-2xl text-[11px] leading-relaxed text-muted">
          入库只来自 docs.python.org 官方文档页与 lessons 课程快照；检索是纯数据库查询，不发起外部请求。
        </p>
      </header>
      <div className="mt-8">
        <KnowledgeView />
      </div>
    </div>
  );
}
