import { API_BASE_URL, REQUEST_TIMEOUT_MS } from "@/lib/api";
import { parseApiError, readRequestId } from "@/lib/contract";

export type ApiFailure = {
  status: number | null;
  code: string;
  message: string;
  details: unknown;
  requestId: string | null;
  retryable: boolean;
};

export type ApiResult<T> =
  | { ok: true; data: T }
  | { ok: false; failure: ApiFailure };

type RequestOptions<T> = {
  method?: "GET" | "POST" | "PUT" | "PATCH";
  body?: unknown;
  parse: (payload: unknown) => T | null;
  // 单次请求的客户端超时上限；默认沿用 REQUEST_TIMEOUT_MS。
  // AI 导师的上游超时是 30s（AI_TIMEOUT_SECONDS），必须让服务端 504 AI_TIMEOUT 先到达，
  // 而不是被浏览器在 5s 处 abort 成「服务未就绪」。
  timeoutMs?: number;
};

const STATUS_MESSAGE: Record<number, string> = {
  404: "接口不存在：后端尚未注册该路由。",
  409: "当前状态不允许该操作。",
  422: "提交的内容未通过校验。",
  500: "后端处理失败，请稍后重试。",
  502: "后端暂时不可用，请稍后重试。",
  503: "数据库不可用，请稍后重试。",
  504: "后端响应超时，请稍后重试。",
};

function statusCode(status: number): string {
  switch (status) {
    case 404:
      return "NOT_FOUND";
    case 409:
      return "CONFLICT";
    case 422:
      return "VALIDATION_ERROR";
    case 500:
      return "INTERNAL_ERROR";
    case 503:
      return "DB_UNAVAILABLE";
    default:
      return "HTTP_" + String(status);
  }
}

async function readJson(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

// 未注册路由由框架兜底返回英文 "Not Found"；设计系统要求错误态只显示中文，
// 这类兜底文案统一换成本地的中文说明，业务自身的 404 文案保持不变。
function isFrameworkNotFound(status: number, message: string): boolean {
  return status === 404 && message.trim().toLowerCase() === "not found";
}

function failureFromResponse(status: number, payload: unknown): ApiFailure {
  const details = parseApiError(payload);
  const fallback = STATUS_MESSAGE[status] ?? "请求失败（HTTP " + String(status) + "）。";
  return {
    status,
    code: details ? details.code : statusCode(status),
    message: details
      ? isFrameworkNotFound(status, details.message)
        ? fallback
        : details.message
      : fallback,
    details: details ? details.details : null,
    requestId: readRequestId(payload),
    retryable: status >= 500,
  };
}

function offlineFailure(reason: string): ApiFailure {
  return {
    status: null,
    code: "SERVICE_UNAVAILABLE",
    message:
      "服务未就绪：" + reason + " 目标地址 " + API_BASE_URL + "，启动后端后可点击重试。",
    details: null,
    requestId: null,
    retryable: true,
  };
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions<T>,
): Promise<ApiResult<T>> {
  const controller = new AbortController();
  const timeoutMs = options.timeoutMs ?? REQUEST_TIMEOUT_MS;
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) {
    headers["Content-Type"] = "application/json";
  }

  try {
    const response = await fetch(API_BASE_URL + path, {
      method: options.method ?? "GET",
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      cache: "no-store",
      signal: controller.signal,
    });
    const payload = await readJson(response);
    if (!response.ok) {
      return { ok: false, failure: failureFromResponse(response.status, payload) };
    }
    const data = options.parse(payload);
    if (data === null) {
      return {
        ok: false,
        failure: {
          status: response.status,
          code: "INVALID_RESPONSE",
          message: "接口返回结构不符合已冻结的契约，页面无法安全渲染。",
          details: null,
          requestId: readRequestId(payload),
          retryable: true,
        },
      };
    }
    return { ok: true, data };
  } catch (error) {
    const aborted = error instanceof DOMException && error.name === "AbortError";
    return {
      ok: false,
      failure: offlineFailure(aborted ? "请求超时。" : "无法连接后端接口。"),
    };
  } finally {
    clearTimeout(timer);
  }
}
