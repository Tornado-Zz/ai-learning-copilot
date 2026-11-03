export type ThemeChoice = "light" | "dark" | "system";

export type ResolvedTheme = "light" | "dark";

export const THEME_STORAGE_KEY = "alc-theme";

export function isThemeChoice(value: unknown): value is ThemeChoice {
  return value === "light" || value === "dark" || value === "system";
}

export function resolveTheme(
  choice: ThemeChoice,
  systemPrefersDark: boolean,
): ResolvedTheme {
  if (choice === "system") {
    return systemPrefersDark ? "dark" : "light";
  }
  return choice;
}

export const THEME_CHANGE_EVENT = "alc-theme-change";

export function getThemeSnapshot(): string {
  try {
    return window.localStorage.getItem(THEME_STORAGE_KEY) ?? "system";
  } catch {
    return "system";
  }
}

export function getServerThemeSnapshot(): string {
  return "system";
}

export function subscribeTheme(onChange: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === THEME_STORAGE_KEY || event.key === null) {
      onChange();
    }
  };
  window.addEventListener("storage", handleStorage);
  window.addEventListener(THEME_CHANGE_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(THEME_CHANGE_EVENT, onChange);
  };
}

export function readStoredTheme(): ThemeChoice {
  const raw = getThemeSnapshot();
  return isThemeChoice(raw) ? raw : "system";
}

export function persistTheme(choice: ThemeChoice): void {
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, choice);
  } catch {
    // Storage may be unavailable (private mode); theming still works for the session.
  }
  window.dispatchEvent(new Event(THEME_CHANGE_EVENT));
}

export function applyTheme(choice: ThemeChoice): ResolvedTheme {
  const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  const resolved = resolveTheme(choice, prefersDark);
  const root = document.documentElement;
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
  return resolved;
}

// Runs before the first paint so the document never flashes light on a dark preference.
export const THEME_INIT_SCRIPT =
  "(function(){try{" +
  "var key='" + THEME_STORAGE_KEY + "';" +
  "var stored=window.localStorage.getItem(key);" +
  "var dark=stored==='dark'||(stored!=='light'&&window.matchMedia('(prefers-color-scheme: dark)').matches);" +
  "var root=document.documentElement;" +
  "root.classList.toggle('dark',dark);" +
  "root.style.colorScheme=dark?'dark':'light';" +
  "}catch(error){}})();";
