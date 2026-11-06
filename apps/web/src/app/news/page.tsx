import type { Metadata } from "next";

import { NewsView } from "./news-view";

// 布局里已经有 " · AI Learning Copilot" 模板，这里不要再写一遍。
export const metadata: Metadata = {
  title: "研究专栏",
};

export default function NewsPage() {
  return <NewsView />;
}
