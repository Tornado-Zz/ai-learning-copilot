export const API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL || "http://127.0.0.1:8000"
).replace(/\/+$/, "");

export const HEALTH_PATH = "/api/v1/health";
export const READY_PATH = "/api/v1/ready";
export const DIAGNOSTIC_PAPER_PATH = "/api/v1/diagnostics/paper?version=v1";

export const REQUEST_TIMEOUT_MS = 5000;
export const POLL_INTERVAL_MS = 30000;

export type HealthSummary = {
  status: string;
  service: string;
  version: string;
  environment: string;
  aiConfigured: boolean;
};

export type DatabaseCheck = {
  status: "connected" | "disconnected";
  latencyMs: number | null;
  detail: string | null;
};

export type ProbeResult = {
  status: number;
  ok: boolean;
  body: unknown;
};

function asRecord(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  return value as Record<string, unknown>;
}

export async function probeJson(
  url: string,
  signal: AbortSignal,
): Promise<ProbeResult | null> {
  try {
    const response = await fetch(url, {
      signal,
      cache: "no-store",
      headers: { Accept: "application/json" },
    });
    let body: unknown = null;
    try {
      body = await response.json();
    } catch {
      body = null;
    }
    return { status: response.status, ok: response.ok, body };
  } catch {
    return null;
  }
}

export function parseHealth(body: unknown): HealthSummary {
  const record = asRecord(body);
  const text = (key: string): string => {
    const value = record ? record[key] : null;
    return typeof value === "string" ? value : "";
  };
  return {
    status: text("status"),
    service: text("service"),
    version: text("version"),
    environment: text("environment"),
    aiConfigured: record ? record.ai_configured === true : false,
  };
}

export function parseReady(body: unknown): DatabaseCheck | null {
  const record = asRecord(body);
  const checks = record ? asRecord(record.checks) : null;
  const database = checks ? asRecord(checks.database) : null;
  if (!database) {
    return null;
  }
  const rawStatus = database.status;
  if (rawStatus !== "connected" && rawStatus !== "disconnected") {
    return null;
  }
  const latency = typeof database.latency_ms === "number" ? database.latency_ms : null;
  const detail = typeof database.detail === "string" ? database.detail : null;
  return { status: rawStatus, latencyMs: latency, detail };
}
