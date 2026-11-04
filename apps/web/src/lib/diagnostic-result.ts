import type { DiagnosticResult } from "@/lib/contract";
import { parseDiagnosticResult } from "@/lib/contract";

export const LAST_RESULT_STORAGE_KEY = "alc-diagnostic-last-result-v1";
export const LAST_RESULT_EVENT = "alc-last-result-change";

export type StoredResult = DiagnosticResult & {
  questionSetVersion: string | null;
  storedAt: number;
};

export function parseLastResult(raw: string | null): StoredResult | null {
  if (!raw) {
    return null;
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return null;
  }
  const result = parseDiagnosticResult(parsed);
  if (!result) {
    return null;
  }
  const record = parsed as Record<string, unknown>;
  return {
    ...result,
    questionSetVersion:
      typeof record.questionSetVersion === "string" ? record.questionSetVersion : null,
    storedAt: typeof record.storedAt === "number" ? record.storedAt : 0,
  };
}

function readRaw(): string {
  try {
    return window.sessionStorage.getItem(LAST_RESULT_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function getLastResultRaw(): string {
  return readRaw();
}

export function getServerLastResultRaw(): string {
  return "";
}

export function subscribeLastResult(onChange: () => void): () => void {
  const handleStorage = (event: StorageEvent) => {
    if (event.key === LAST_RESULT_STORAGE_KEY || event.key === null) {
      onChange();
    }
  };
  window.addEventListener("storage", handleStorage);
  window.addEventListener(LAST_RESULT_EVENT, onChange);
  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(LAST_RESULT_EVENT, onChange);
  };
}

export function writeLastResult(result: DiagnosticResult): boolean {
  try {
    window.sessionStorage.setItem(
      LAST_RESULT_STORAGE_KEY,
      JSON.stringify({ ...result, storedAt: Date.now() }),
    );
  } catch {
    return false;
  }
  window.dispatchEvent(new Event(LAST_RESULT_EVENT));
  return true;
}

