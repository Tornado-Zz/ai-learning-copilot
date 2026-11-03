"use client";

import { useCallback, useEffect, useSyncExternalStore } from "react";
import type { ComponentType } from "react";
import { cx } from "@/components/ui";
import { IconMonitor, IconMoon, IconSun } from "@/components/icons";
import {
  applyTheme,
  getServerThemeSnapshot,
  getThemeSnapshot,
  isThemeChoice,
  persistTheme,
  readStoredTheme,
  subscribeTheme,
} from "@/lib/theme";
import type { ThemeChoice } from "@/lib/theme";

type ThemeOption = {
  value: ThemeChoice;
  label: string;
  Icon: ComponentType<{ className?: string }>;
};

const OPTIONS: ThemeOption[] = [
  { value: "light", label: "浅色", Icon: IconSun },
  { value: "dark", label: "深色", Icon: IconMoon },
  { value: "system", label: "跟随系统", Icon: IconMonitor },
];

export function ThemeToggle() {
  const stored = useSyncExternalStore(
    subscribeTheme,
    getThemeSnapshot,
    getServerThemeSnapshot,
  );
  const choice: ThemeChoice = isThemeChoice(stored) ? stored : "system";

  useEffect(() => {
    applyTheme(readStoredTheme());

    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const handleSystemChange = () => {
      if (readStoredTheme() === "system") {
        applyTheme("system");
      }
    };
    media.addEventListener("change", handleSystemChange);
    return () => media.removeEventListener("change", handleSystemChange);
  }, []);

  const select = useCallback((value: ThemeChoice) => {
    persistTheme(value);
    applyTheme(value);
  }, []);

  return (
    <div
      role="group"
      aria-label="主题切换"
      className="flex items-center gap-0.5 rounded-control border border-line bg-surface p-0.5"
    >
      {OPTIONS.map((option) => {
        const active = choice === option.value;
        const Icon = option.Icon;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => select(option.value)}
            aria-pressed={active}
            aria-label={option.label}
            title={option.label}
            className={cx(
              "grid size-7 place-items-center rounded-control transition-colors",
              active
                ? "bg-elevated text-fg"
                : "text-muted hover:bg-elevated hover:text-fg",
            )}
          >
            <Icon className="size-4" />
          </button>
        );
      })}
    </div>
  );
}
