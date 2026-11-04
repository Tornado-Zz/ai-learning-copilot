export type NavItem = {
  href: string;
  label: string;
  en: string;
  title: string;
  summary: string;
};

export type NavGroup = {
  id: string;
  label: string;
  items: NavItem[];
};

export const NAV_GROUPS: NavGroup[] = [
  {
    id: "main",
    label: "主导航",
    items: [
      {
        href: "/",
        label: "今日",
        en: "Today",
        title: "今日概览",
        summary: "周计划里今天的真实任务",
      },
      {
        href: "/learn",
        label: "学习",
        en: "Learn",
        title: "学习路线",
        summary: "六阶段等级与已发布课程",
      },
      {
        href: "/practice",
        label: "练习",
        en: "Practice",
        title: "练习",
        summary: "按课程分组的练习 · 静态规则与自检",
      },
      {
        href: "/projects",
        label: "项目",
        en: "Projects",
        title: "项目实践",
        summary: "三个候选项目与提交要求",
      },
      {
        href: "/progress",
        label: "进度",
        en: "Progress",
        title: "学习进度",
        summary: "完成率与掌握度",
      },
    ],
  },
  {
    id: "flow",
    label: "学习流程",
    items: [
      {
        href: "/onboarding",
        label: "档案",
        en: "Profile",
        title: "学习档案",
        summary: "学习日、每天时长与时区确认",
      },
      {
        href: "/diagnostic",
        label: "诊断",
        en: "Diagnostic",
        title: "能力诊断",
        summary: "20 题 · 草稿自动保存",
      },
      {
        href: "/result",
        label: "结果",
        en: "Result",
        title: "诊断结果",
        summary: "六维等级与判定依据",
      },
      {
        href: "/plan",
        label: "周计划",
        en: "Plan",
        title: "周计划",
        summary: "按日期分组的真实计划 · 可重新生成",
      },
      {
        href: "/history",
        label: "历史",
        en: "History",
        title: "历史结果",
        summary: "历史诊断批次与六域摘要",
      },
      {
        href: "/knowledge",
        label: "知识库",
        en: "Knowledge",
        title: "知识检索",
        summary: "只读知识库快照 · 每条结果标注抓取时间",
      },
    ],
  },
];

export const NAV_ITEMS: NavItem[] = NAV_GROUPS.flatMap((group) => group.items);

export function isActivePath(pathname: string, href: string): boolean {
  if (href === "/") {
    return pathname === "/";
  }
  return pathname === href || pathname.startsWith(href + "/");
}

export function findNavItem(pathname: string): NavItem {
  const match = NAV_ITEMS.find((item) => isActivePath(pathname, item.href));
  return match ?? NAV_ITEMS[0];
}
