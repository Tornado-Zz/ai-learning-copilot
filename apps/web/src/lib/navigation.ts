export type NavItem = {
  href: string;
  label: string;
  en: string;
  title: string;
  summary: string;
};

export const NAV_ITEMS: NavItem[] = [
  {
    href: "/",
    label: "今日",
    en: "Today",
    title: "今日概览",
    summary: "今天要做的三件事",
  },
  {
    href: "/learn",
    label: "学习",
    en: "Learn",
    title: "学习路线",
    summary: "路线 A · 六阶段进度",
  },
  {
    href: "/practice",
    label: "练习",
    en: "Practice",
    title: "练习与判题",
    summary: "练习列表骨架与判题说明",
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
];

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
