"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import type { ReactNode } from "react";
import {
  API_BASE_URL,
  HEALTH_PATH,
  POLL_INTERVAL_MS,
  READY_PATH,
  REQUEST_TIMEOUT_MS,
  parseHealth,
  parseReady,
  probeJson,
} from "@/lib/api";
import type { DatabaseCheck, HealthSummary } from "@/lib/api";
import { Card, CardBody, CardHeader, Dot, cx } from "@/components/ui";

export type SystemStatus = {
  phase: "checking" | "settled";
  backendOnline: boolean;
  databaseConnected: boolean;
  health: HealthSummary | null;
  database: DatabaseCheck | null;
  checkedAt: number | null;
};

const INITIAL_STATUS: SystemStatus = {
  phase: "checking",
  backendOnline: false,
  databaseConnected: false,
  health: null,
  database: null,
  checkedAt: null,
};

type SystemStatusContextValue = {
  status: SystemStatus;
  refresh: () => void;
};

const SystemStatusContext = createContext<SystemStatusContextValue | null>(null);

function offlineStatus(): SystemStatus {
  return {
    phase: "settled",
    backendOnline: false,
    databaseConnected: false,
    health: null,
    database: null,
    checkedAt: Date.now(),
  };
}

export function SystemStatusProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<SystemStatus>(INITIAL_STATUS);
  const [refreshToken, setRefreshToken] = useState(0);

  useEffect(() => {
    let active = true;
    let sequence = 0;
    const controllers = new Set<AbortController>();

    const run = async () => {
      sequence += 1;
      const current = sequence;
      const controller = new AbortController();
      controllers.add(controller);
      const timer = window.setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

      try {
        const health = await probeJson(API_BASE_URL + HEALTH_PATH, controller.signal);
        const ready = await probeJson(API_BASE_URL + READY_PATH, controller.signal);

        if (!active || current !== sequence) {
          return;
        }

        const backendOnline = health !== null && health.status === 200;
        const database = ready !== null ? parseReady(ready.body) : null;
        const databaseConnected =
          ready !== null &&
          ready.status === 200 &&
          database !== null &&
          database.status === "connected";

        setStatus({
          phase: "settled",
          backendOnline,
          databaseConnected,
          health: health !== null ? parseHealth(health.body) : null,
          database,
          checkedAt: Date.now(),
        });
      } catch {
        if (active && current === sequence) {
          setStatus(offlineStatus());
        }
      } finally {
        window.clearTimeout(timer);
        controllers.delete(controller);
      }
    };

    void run();
    const intervalId = window.setInterval(() => {
      void run();
    }, POLL_INTERVAL_MS);

    return () => {
      active = false;
      window.clearInterval(intervalId);
      controllers.forEach((value) => value.abort());
      controllers.clear();
    };
  }, [refreshToken]);

  const refresh = useCallback(() => {
    setStatus((previous) => ({ ...previous, phase: "checking" }));
    setRefreshToken((value) => value + 1);
  }, []);

  const value = useMemo(() => ({ status, refresh }), [status, refresh]);

  return (
    <SystemStatusContext.Provider value={value}>
      {children}
    </SystemStatusContext.Provider>
  );
}

export function useSystemStatus(): SystemStatusContextValue {
  const value = useContext(SystemStatusContext);
  if (!value) {
    throw new Error("useSystemStatus must be used inside SystemStatusProvider");
  }
  return value;
}

function backendText(status: SystemStatus): string {
  if (status.phase === "checking") return "检测中";
  return status.backendOnline ? "在线" : "离线";
}

function databaseText(status: SystemStatus): string {
  if (status.phase === "checking") return "检测中";
  return status.databaseConnected ? "已连接" : "未连接";
}

export function SystemStatusCompact({ className }: { className?: string }) {
  const { status } = useSystemStatus();
  const checking = status.phase === "checking";
  const tone = checking
    ? "warning"
    : status.backendOnline
      ? status.databaseConnected
        ? "success"
        : "warning"
      : "danger";
  const label = checking
    ? "系统状态检测中"
    : status.backendOnline
      ? status.databaseConnected
        ? "后端在线 · 数据库已连接"
        : "后端在线 · 数据库未连接"
      : "后端离线";

  return (
    <div className={cx("flex items-center gap-2", className)}>
      <Dot tone={tone} pulse={checking} />
      <span className="truncate text-[12px] text-muted">{label}</span>
    </div>
  );
}

export function SystemStatusCard() {
  const { status, refresh } = useSystemStatus();
  const checking = status.phase === "checking";
  const backendTone = checking
    ? "warning"
    : status.backendOnline
      ? "success"
      : "danger";
  const databaseTone = checking
    ? "warning"
    : status.databaseConnected
      ? "success"
      : status.backendOnline
        ? "warning"
        : "danger";

  const checkedLabel =
    status.checkedAt === null
      ? "—"
      : new Date(status.checkedAt).toLocaleTimeString("zh-CN", { hour12: false });

  const versionLabel = status.health && status.health.version ? status.health.version : "—";
  const environmentLabel =
    status.health && status.health.environment ? status.health.environment : "—";
  const aiLabel =
    status.health === null ? "—" : status.health.aiConfigured ? "已配置" : "未配置";

  return (
    <Card>
      <CardHeader
        title="系统状态"
        description={"接口地址 " + API_BASE_URL}
        action={
          <button
            type="button"
            onClick={refresh}
            disabled={checking}
            className="rounded-control border border-line px-2 py-1 text-[12px] font-medium text-muted transition-colors hover:border-line-strong hover:text-fg disabled:text-muted"
          >
            {checking ? "检测中" : "重新检测"}
          </button>
        }
      />
      <CardBody className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <span className="text-[12px] text-muted">后端 API</span>
          <span className="inline-flex items-center gap-2 text-[12px] font-medium text-fg">
            <Dot tone={backendTone} pulse={checking} />
            {backendText(status)}
          </span>
        </div>

        <div className="flex items-start justify-between gap-3">
          <span className="shrink-0 text-[12px] text-muted">数据库</span>
          <span className="inline-flex items-center gap-2 text-right text-[12px] font-medium text-fg">
            <Dot tone={databaseTone} pulse={checking} />
            {databaseText(status)}
            {!checking && status.database && status.database.latencyMs !== null ? (
              <span className="font-mono text-[11px] font-normal text-muted">
                {status.database.latencyMs} ms
              </span>
            ) : null}
          </span>
        </div>

        {!checking && status.database && status.database.detail ? (
          <p className="rounded-control bg-elevated px-2 py-1.5 text-[11px] leading-relaxed text-muted">
            {status.database.detail}
          </p>
        ) : null}

        <div className="grid grid-cols-2 gap-2 border-t border-line pt-3">
          <div>
            <p className="text-[11px] text-muted">服务版本</p>
            <p className="mt-0.5 font-mono text-[12px] text-fg">{versionLabel}</p>
          </div>
          <div>
            <p className="text-[11px] text-muted">环境</p>
            <p className="mt-0.5 font-mono text-[12px] text-fg">{environmentLabel}</p>
          </div>
          <div>
            <p className="text-[11px] text-muted">AI 能力</p>
            <p className="mt-0.5 text-[12px] text-fg">{aiLabel}</p>
          </div>
          <div>
            <p className="text-[11px] text-muted">最近检测</p>
            <p className="mt-0.5 font-mono text-[12px] text-fg">{checkedLabel}</p>
          </div>
        </div>

        {!checking && !status.backendOnline ? (
          <p className="text-[11px] leading-relaxed text-muted">
            后端未启动时属于预期状态：启动 apps/api 后点击「重新检测」即可。
          </p>
        ) : null}
      </CardBody>
    </Card>
  );
}
