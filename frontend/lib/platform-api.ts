"use client";

export type QueryValue =
  | string
  | number
  | boolean
  | null
  | undefined
  | Array<string | number | boolean>;

export type PlatformRequestOptions = {
  method?: "GET" | "POST" | "PUT" | "DELETE";
  token?: string | null;
  query?: Record<string, QueryValue>;
  body?: unknown;
  formData?: FormData;
  timeoutMs?: number;
};

const DEFAULT_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000/api/v1";

export class PlatformApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "PlatformApiError";
    this.status = status;
  }
}

export function normalizeApiBaseUrl(value?: string | null) {
  const trimmed = String(value || "").trim();
  return (trimmed || DEFAULT_API_BASE).replace(/\/$/, "");
}

export function buildApiUrl(
  baseUrl: string,
  path: string,
  query?: PlatformRequestOptions["query"],
) {
  const url = new URL(`${normalizeApiBaseUrl(baseUrl)}${path}`);

  if (query) {
    for (const [key, rawValue] of Object.entries(query)) {
      if (
        rawValue === undefined ||
        rawValue === null ||
        rawValue === ""
      ) {
        continue;
      }

      if (Array.isArray(rawValue)) {
        for (const item of rawValue) {
          url.searchParams.append(key, String(item));
        }
        continue;
      }

      url.searchParams.set(key, String(rawValue));
    }
  }

  return url.toString();
}

export async function platformRequest<T>(
  baseUrl: string,
  path: string,
  options: PlatformRequestOptions = {},
): Promise<T> {
  const headers = new Headers();
  const controller = new AbortController();
  const timeoutId =
    options.timeoutMs && options.timeoutMs > 0
      ? globalThis.setTimeout(() => controller.abort(), options.timeoutMs)
      : null;

  if (options.token) {
    headers.set("Authorization", `Bearer ${options.token}`);
  }

  if (!options.formData) {
    headers.set("Content-Type", "application/json");
  }

  try {
    const response = await fetch(buildApiUrl(baseUrl, path, options.query), {
      method: options.method ?? "GET",
      headers,
      body: options.formData
        ? options.formData
        : options.body === undefined
          ? undefined
          : JSON.stringify(options.body),
      cache: "no-store",
      signal: controller.signal,
    });

    const text = await response.text();
    let data: unknown = null;

    if (text) {
      try {
        data = JSON.parse(text);
      } catch {
        data = text;
      }
    }

    if (!response.ok) {
      const detail =
        typeof data === "object" && data && "detail" in data
          ? String((data as { detail?: unknown }).detail)
          : typeof data === "string"
            ? data
            : response.statusText;
      throw new PlatformApiError(detail || "Request failed", response.status);
    }

    return data as T;
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new PlatformApiError("请求超时，请稍后重试", 408);
    }
    throw error;
  } finally {
    if (timeoutId) {
      globalThis.clearTimeout(timeoutId);
    }
  }
}
