import type {
  ModuleConfig,
  PaginatedItems,
  RepositoryConfig,
  SolutionRecord,
  SolutionReview,
  TaskCluster,
  User,
} from "@/lib/types";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000/api/v1";

type RequestOptions = {
  method?: "GET" | "POST" | "PUT";
  token?: string | null;
  body?: unknown;
  query?: Record<string, string | number | boolean | undefined | null>;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

function buildUrl(path: string, query?: RequestOptions["query"]) {
  const url = new URL(`${API_BASE_URL}${path}`);

  if (query) {
    for (const [key, value] of Object.entries(query)) {
      if (value === undefined || value === null || value === "") {
        continue;
      }

      url.searchParams.set(key, String(value));
    }
  }

  return url.toString();
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const response = await fetch(buildUrl(path, options.query), {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(options.token ? { Authorization: `Bearer ${options.token}` } : {}),
    },
    body: options.body === undefined ? undefined : JSON.stringify(options.body),
    cache: "no-store",
  });

  const text = await response.text();
  const data = text ? (JSON.parse(text) as unknown) : null;

  if (!response.ok) {
    const detail =
      typeof data === "object" && data && "detail" in data
        ? String((data as { detail?: unknown }).detail)
        : response.statusText;
    throw new ApiError(detail || "请求失败", response.status);
  }

  return data as T;
}

export const apiBaseUrl = API_BASE_URL;

export const api = {
  login(loginName: string, password: string) {
    return request<{ token: string; expires_at: string; user: User }>("/auth/login", {
      method: "POST",
      body: { login_name: loginName, password },
    });
  },

  me(token: string) {
    return request<User>("/auth/me", { token });
  },

  logout(token: string) {
    return request<{ status: string; user: User }>("/auth/logout", {
      method: "POST",
      token,
    });
  },

  changePassword(token: string, currentPassword: string, newPassword: string) {
    return request<{ status: string; user: User }>("/auth/change-password", {
      method: "POST",
      token,
      body: {
        current_password: currentPassword,
        new_password: newPassword,
      },
    });
  },

  register(payload: {
    username: string;
    email: string;
    password: string;
    registration_note?: string;
  }) {
    return request<{ user: User; next_status: string }>("/auth/register", {
      method: "POST",
      body: payload,
    });
  },

  listUsers(token: string) {
    return request<PaginatedItems<User> & { current_user: User }>("/admin/users", {
      token,
    });
  },

  updateUserStatus(token: string, userId: number, action: string) {
    return request<{ status: string; item: User }>(`/admin/users/${userId}/status`, {
      method: "POST",
      token,
      body: { action },
    });
  },

  updateUserRoles(
    token: string,
    userId: number,
    payload: { is_reviewer: boolean; is_admin: boolean },
  ) {
    return request<{ status: string; item: User }>(`/admin/users/${userId}/roles`, {
      method: "POST",
      token,
      body: payload,
    });
  },

  getRepositoryConfig(token: string) {
    return request<RepositoryConfig>("/solution-repository/config", { token });
  },

  listModules(token: string) {
    return request<PaginatedItems<ModuleConfig>>("/solution-repository/modules", {
      token,
    });
  },

  createOrUpdateModule(
    token: string,
    payload: {
      id?: number;
      module_key?: string;
      display_name: string;
      prefix: string;
      description?: string;
      is_active?: boolean;
    },
  ) {
    return request<{ status: string; item: ModuleConfig }>("/solution-repository/modules", {
      method: "POST",
      token,
      body: payload,
    });
  },

  listTaskClusters(token: string, includePending = false) {
    return request<PaginatedItems<TaskCluster>>("/solution-repository/task-clusters", {
      token,
      query: includePending ? { include_pending: true } : undefined,
    });
  },

  createTaskCluster(token: string, payload: { display_name: string; description?: string }) {
    return request<{ status: string; item: TaskCluster }>("/solution-repository/task-clusters", {
      method: "POST",
      token,
      body: payload,
    });
  },

  reviewTaskCluster(token: string, clusterId: number, reviewStatus: string) {
    return request<{ status: string; item: TaskCluster }>(
      `/solution-repository/task-clusters/${clusterId}/review`,
      {
        method: "POST",
        token,
        body: { review_status: reviewStatus },
      },
    );
  },

  listSolutionRecords(
    token: string,
    query?: {
      search?: string;
      module?: string;
      review_status?: string;
      error_code?: string;
      task_cluster?: string;
      limit?: number;
    },
  ) {
    return request<PaginatedItems<SolutionRecord>>("/solution-repository/records", {
      token,
      query,
    });
  },

  createSolutionRecord(token: string, payload: Record<string, unknown>) {
    return request<{ status: string; item: SolutionRecord }>("/solution-repository/records", {
      method: "POST",
      token,
      body: payload,
    });
  },

  updateSolutionRecord(
    token: string,
    recordId: number,
    payload: Record<string, unknown>,
  ) {
    return request<{ status: string; item: SolutionRecord }>(
      `/solution-repository/records/${recordId}`,
      {
        method: "PUT",
        token,
        body: payload,
      },
    );
  },

  listSolutionReviews(token: string, status?: string) {
    return request<PaginatedItems<SolutionReview>>("/solution-reviews", {
      token,
      query: status ? { status, limit: 200 } : { limit: 200 },
    });
  },

  submitSolutionReview(token: string, payload: Record<string, unknown>) {
    return request<{ status: string; item: SolutionReview }>("/solution-reviews", {
      method: "POST",
      token,
      body: payload,
    });
  },

  manualReviewSolution(
    token: string,
    reviewId: number,
    payload: {
      review_status: "approved" | "needs_revision" | "rejected";
      reviewer?: string;
      notes?: string;
    },
  ) {
    return request<{ status: string; item: SolutionReview }>(
      `/solution-reviews/${reviewId}/manual-review`,
      {
        method: "POST",
        token,
        body: payload,
      },
    );
  },

  generateErrorCode(token: string, moduleKey: string) {
    return request<{ status: string; module: string; prefix: string; error_code: string }>(
      "/error-code/generate",
      {
        method: "POST",
        token,
        body: { module: moduleKey },
      },
    );
  },

  getModulePrefixes(token: string) {
    return request<{ items: ModuleConfig[]; total: number; module_prefixes: Record<string, string> }>(
      "/module-prefixes",
      { token },
    );
  },
};
