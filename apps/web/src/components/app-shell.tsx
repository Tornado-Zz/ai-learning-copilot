"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useState } from "react";
import type { ComponentType, ReactNode } from "react";
import { NAV_ITEMS, findNavItem, isActivePath } from "@/lib/navigation";
import { ThemeToggle } from "@/components/theme-toggle";
import { SystemStatusCompact, SystemStatusProvider } from "@/components/system-status";
import { SoonTag, cx } from "@/components/ui";
import {
  IconClose,
  IconLearn,
  IconMenu,
  IconPractice,
  IconProgress,
  IconProjects,
  IconSpark,
  IconToday,
  LogoGlyph,
} from "@/components/icons";

const NAV_ICONS: Record<string, ComponentType<{ className?: string }>> = {
  "/": IconToday,
  "/learn": IconLearn,
  "/practice": IconPractice,
  "/projects": IconProjects,
  "/progress": IconProgress,
};

function Brand({
  compact = false,
  onNavigate,
}: {
  compact?: boolean;
  onNavigate?: () => void;
}) {
  return (
    <Link
      href="/"
      onClick={onNavigate}
      className="flex min-w-0 items-center gap-2 rounded-control outline-offset-4"
      aria-label="AI Learning Copilot 首页"
    >
      <span className="grid size-6 shrink-0 place-items-center rounded-control bg-accent text-canvas">
        <LogoGlyph />
      </span>
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-semibold tracking-tight text-fg">
          AI Learning Copilot
        </span>
        {compact ? null : (
          <span className="block truncate text-[11px] text-muted">自学路线 · Sprint 0</span>
        )}
      </span>
    </Link>
  );
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();

  return (
    <ul className="space-y-0.5">
      {NAV_ITEMS.map((item) => {
        const Icon = NAV_ICONS[item.href] ?? IconToday;
        const active = isActivePath(pathname, item.href);
        return (
          <li key={item.href}>
            <Link
              href={item.href}
              onClick={onNavigate}
              aria-current={active ? "page" : undefined}
              className={cx(
                "group flex items-center gap-2.5 rounded-control px-2.5 py-2 text-[13px] transition-colors",
                active
                  ? "bg-elevated font-medium text-fg"
                  : "text-muted hover:bg-elevated hover:text-fg",
              )}
            >
              <Icon className={active ? "size-4 text-accent" : "size-4 text-muted group-hover:text-fg"} />
              <span className="flex-1 truncate">{item.label}</span>
              <span className="font-mono text-[10px] tracking-wide text-muted">
                {item.en}
              </span>
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

function AiTutorEntry() {
  return (
    <button
      type="button"
      disabled
      aria-disabled="true"
      title="AI 导师对话尚未实现"
      className="flex w-full items-center gap-2.5 rounded-control border border-dashed border-line-strong px-2.5 py-2 text-left text-[13px] text-muted"
    >
      <IconSpark className="size-4" />
      <span className="flex-1 truncate">AI 导师</span>
      <SoonTag />
    </button>
  );
}

function SidebarFooter() {
  return (
    <div className="border-t border-line px-3 py-3">
      <SystemStatusCompact />
      <p className="mt-1.5 px-0.5 text-[11px] text-muted">Sprint 0 · 预览版</p>
    </div>
  );
}

function Sidebar() {
  return (
    <aside className="fixed inset-y-0 left-0 z-30 hidden w-[240px] flex-col border-r border-line bg-surface md:flex">
      <div className="flex h-14 shrink-0 items-center border-b border-line px-3">
        <Brand />
      </div>
      <div className="flex-1 overflow-y-auto px-2 py-3">
        <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-muted">
          主导航
        </p>
        <NavLinks />
        <p className="px-2.5 pt-5 pb-2 text-[11px] font-medium tracking-wide text-muted">
          学习空间
        </p>
        <AiTutorEntry />
      </div>
      <SidebarFooter />
    </aside>
  );
}

function TopBar({ onOpenMenu }: { onOpenMenu: () => void }) {
  const pathname = usePathname();
  const item = findNavItem(pathname);

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-canvas">
      <div className="flex h-14 items-center gap-3 px-4 md:px-6">
        <button
          type="button"
          onClick={onOpenMenu}
          aria-label="打开导航菜单"
          className="grid size-8 shrink-0 place-items-center rounded-control border border-line text-muted transition-colors hover:text-fg md:hidden"
        >
          <IconMenu className="size-4" />
        </button>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[13px] font-medium text-fg">{item.title}</p>
          <p className="truncate text-[11px] text-muted">{item.summary}</p>
        </div>
        <ThemeToggle />
      </div>
    </header>
  );
}

function MobileNav({ open, onClose }: { open: boolean; onClose: () => void }) {
  useEffect(() => {
    if (!open) {
      return;
    }
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, onClose]);

  if (!open) {
    return null;
  }

  return (
    <div className="fixed inset-0 z-40 md:hidden">
      <div
        className="absolute inset-0 bg-black/45"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="主导航"
        className="absolute inset-y-0 left-0 flex w-[272px] flex-col border-r border-line bg-surface shadow-overlay"
      >
        <div className="flex h-14 shrink-0 items-center justify-between gap-2 border-b border-line px-3">
          <Brand compact onNavigate={onClose} />
          <button
            type="button"
            onClick={onClose}
            aria-label="关闭导航菜单"
            className="grid size-8 shrink-0 place-items-center rounded-control border border-line text-muted"
          >
            <IconClose className="size-4" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-2 py-3">
          <p className="px-2.5 pb-2 text-[11px] font-medium tracking-wide text-muted">
            主导航
          </p>
          <NavLinks onNavigate={onClose} />
          <p className="px-2.5 pt-5 pb-2 text-[11px] font-medium tracking-wide text-muted">
            学习空间
          </p>
          <AiTutorEntry />
        </div>
        <SidebarFooter />
      </div>
    </div>
  );
}

export function AppShell({ children }: { children: ReactNode }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const closeMenu = useCallback(() => setMenuOpen(false), []);
  const openMenu = useCallback(() => setMenuOpen(true), []);

  return (
    <SystemStatusProvider>
      <Sidebar />
      <MobileNav open={menuOpen} onClose={closeMenu} />
      <div className="flex min-h-screen flex-col md:pl-[240px]">
        <TopBar onOpenMenu={openMenu} />
        <main className="flex-1">{children}</main>
        <footer className="border-t border-line">
          <div className="mx-auto w-full max-w-content px-4 py-4 md:px-8">
            <p className="text-[11px] leading-relaxed text-muted">
              界面为 Sprint 0 预览版，标注「演示数据」的内容均非真实学习数据；标注「开发中」的入口尚不可用。
            </p>
          </div>
        </footer>
      </div>
    </SystemStatusProvider>
  );
}
