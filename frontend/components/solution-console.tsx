"use client";

import { useCallback, useEffect, useState } from "react";
import { useTheme } from "next-themes";
import {
  BookCopy,
  ClipboardCheck,
  KeyRound,
  LoaderCircle,
  Lock,
  LogIn,
  LogOut,
  Moon,
  Search,
  ShieldCheck,
  SunMedium,
  UserCog,
  UserPlus,
  WandSparkles,
} from "lucide-react";

import { api, ApiError, apiBaseUrl } from "@/lib/api";
import type {
  ModuleConfig,
  RepositoryConfig,
  SolutionRecord,
  SolutionReview,
  TaskCluster,
  User,
} from "@/lib/types";
import { cn, formatDate, joinList, takeFirstSentence } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableWrapper,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";

type PageKey =
  | "welcome"
  | "login"
  | "register"
  | "dashboard"
  | "admin"
  | "library"
  | "codes";

type Notice = {
  tone: "success" | "error" | "info";
  text: string;
};

type SolutionFormState = {
  module: string;
  submodule: string;
  error_name: string;
  error_category: string;
  normalized_signature: string;
  message: string;
  trigger_scenario: string;
  root_cause_analysis: string;
  verified_solution: string;
  workaround: string;
  impact_scope: string;
  owner_department: string;
  report_source: string;
  exception_description: string;
  tags: string;
  message_keywords: string;
  task_clusters: string[];
  reusable: boolean;
};

const TOKEN_STORAGE_KEY = "solution-console-auth-token";

const defaultSolutionForm: SolutionFormState = {
  module: "",
  submodule: "",
  error_name: "",
  error_category: "",
  normalized_signature: "",
  message: "",
  trigger_scenario: "",
  root_cause_analysis: "",
  verified_solution: "",
  workaround: "",
  impact_scope: "",
  owner_department: "",
  report_source: "nextjs_console",
  exception_description: "",
  tags: "",
  message_keywords: "",
  task_clusters: [],
  reusable: true,
};

function splitCommaText(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function statusBadgeTone(status: string) {
  switch (status) {
    case "approved":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200";
    case "pending_admin_approval":
    case "pending_review":
      return "bg-amber-100 text-amber-800 dark:bg-amber-950 dark:text-amber-200";
    case "needs_revision":
      return "bg-orange-100 text-orange-800 dark:bg-orange-950 dark:text-orange-200";
    case "rejected":
    case "disabled":
      return "bg-rose-100 text-rose-800 dark:bg-rose-950 dark:text-rose-200";
    default:
      return "bg-slate-100 text-slate-800 dark:bg-slate-900 dark:text-slate-200";
  }
}

function SectionTitle({
  title,
  description,
  actions,
}: {
  title: string;
  description: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
      <div className="space-y-2">
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--foreground)]">
          {title}
        </h2>
        <p className="max-w-3xl text-sm leading-6 text-[var(--muted-foreground)]">
          {description}
        </p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </div>
  );
}

function Field({
  label,
  children,
  hint,
}: {
  label: string;
  children: React.ReactNode;
  hint?: string;
}) {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      {children}
      {hint ? <p className="text-xs text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

function NoticeBanner({ notice }: { notice: Notice | null }) {
  if (!notice) {
    return null;
  }

  const toneClass =
    notice.tone === "success"
      ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200"
      : notice.tone === "error"
        ? "border-rose-200 bg-rose-50 text-rose-800 dark:border-rose-900 dark:bg-rose-950/40 dark:text-rose-200"
        : "border-sky-200 bg-sky-50 text-sky-800 dark:border-sky-900 dark:bg-sky-950/40 dark:text-sky-200";

  return <div className={cn("rounded-2xl border px-4 py-3 text-sm", toneClass)}>{notice.text}</div>;
}

function MetricCard({
  label,
  value,
  helper,
}: {
  label: string;
  value: string | number;
  helper: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-2 pt-6">
        <p className="text-sm text-[var(--muted-foreground)]">{label}</p>
        <p className="text-3xl font-semibold tracking-tight text-[var(--foreground)]">
          {value}
        </p>
        <p className="text-xs leading-5 text-[var(--muted-foreground)]">{helper}</p>
      </CardContent>
    </Card>
  );
}

export function SolutionConsole() {
  const { resolvedTheme, setTheme } = useTheme();

  const [token, setToken] = useState("");
  const [user, setUser] = useState<User | null>(null);
  const [page, setPage] = useState<PageKey>("welcome");
  const [loading, setLoading] = useState(true);
  const [busyLabel, setBusyLabel] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);

  const [repositoryConfig, setRepositoryConfig] = useState<RepositoryConfig | null>(null);
  const [records, setRecords] = useState<SolutionRecord[]>([]);
  const [reviews, setReviews] = useState<SolutionReview[]>([]);
  const [users, setUsers] = useState<User[]>([]);
  const [taskClusters, setTaskClusters] = useState<TaskCluster[]>([]);
  const [modules, setModules] = useState<ModuleConfig[]>([]);

  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");

  const [registerUsername, setRegisterUsername] = useState("");
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerPasswordConfirm, setRegisterPasswordConfirm] = useState("");
  const [registerNote, setRegisterNote] = useState("");

  const [solutionForm, setSolutionForm] = useState<SolutionFormState>(defaultSolutionForm);
  const [librarySearch, setLibrarySearch] = useState("");
  const [libraryModule, setLibraryModule] = useState("");
  const [libraryReviewStatus, setLibraryReviewStatus] = useState("");
  const [libraryErrorCode, setLibraryErrorCode] = useState("");
  const [libraryTaskCluster, setLibraryTaskCluster] = useState("");
  const [editingRecord, setEditingRecord] = useState<SolutionRecord | null>(null);

  const [reviewNotes, setReviewNotes] = useState("");
  const [clusterDraftName, setClusterDraftName] = useState("");
  const [clusterDraftDescription, setClusterDraftDescription] = useState("");
  const [moduleDraftName, setModuleDraftName] = useState("");
  const [moduleDraftKey, setModuleDraftKey] = useState("");
  const [moduleDraftPrefix, setModuleDraftPrefix] = useState("");
  const [moduleDraftDescription, setModuleDraftDescription] = useState("");

  const [generatorModule, setGeneratorModule] = useState("");
  const [generatedCode, setGeneratedCode] = useState("");
  const [generatedHistory, setGeneratedHistory] = useState<string[]>([]);

  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [nextPasswordConfirm, setNextPasswordConfirm] = useState("");

  const isAuthenticated = Boolean(token && user);
  const isReviewer = Boolean(user?.is_reviewer || user?.is_admin);
  const isAdmin = Boolean(user?.is_admin);
  const darkMode = resolvedTheme === "dark";

  async function withBusy<T>(label: string, action: () => Promise<T>) {
    setBusyLabel(label);
    try {
      return await action();
    } finally {
      setBusyLabel("");
    }
  }

  function setAuth(nextToken: string, nextUser: User | null) {
    setToken(nextToken);
    setUser(nextUser);
    if (typeof window !== "undefined") {
      if (nextToken) {
        window.localStorage.setItem(TOKEN_STORAGE_KEY, nextToken);
      } else {
        window.localStorage.removeItem(TOKEN_STORAGE_KEY);
      }
    }
  }

  function showApiError(error: unknown) {
    const message =
      error instanceof ApiError ? error.message : "操作失败，请稍后再试。";
    setNotice({ tone: "error", text: message });
  }

  const loadProtectedData = useCallback(async (activeToken: string) => {
    const [config, recordList, reviewList, moduleList, clusterList] = await Promise.all([
      api.getRepositoryConfig(activeToken),
      api.listSolutionRecords(activeToken, { limit: 200 }),
      api.listSolutionReviews(activeToken),
      api.listModules(activeToken),
      api.listTaskClusters(activeToken, true),
    ]);

    setRepositoryConfig(config);
    setRecords(recordList.items);
    setReviews(reviewList.items);
    setModules(moduleList.items);
    setTaskClusters(clusterList.items);

    if (!solutionForm.module && config.modules.length > 0) {
      setSolutionForm((current) => ({
        ...current,
        module: config.modules[0].module_key,
      }));
      setGeneratorModule(config.modules[0].module_key);
    }

    if (user?.is_admin) {
      const userList = await api.listUsers(activeToken);
      setUsers(userList.items);
    } else {
      setUsers([]);
    }
  }, [solutionForm.module, user?.is_admin]);

  const refreshAll = useCallback(async (activeToken = token) => {
    if (!activeToken) {
      return;
    }

    try {
      await withBusy("刷新数据中", async () => {
        await loadProtectedData(activeToken);
      });
    } catch (error) {
      showApiError(error);
    }
  }, [loadProtectedData, token]);

  useEffect(() => {
    const storedToken =
      typeof window !== "undefined"
        ? window.localStorage.getItem(TOKEN_STORAGE_KEY) ?? ""
        : "";

    async function bootstrap() {
      if (!storedToken) {
        setLoading(false);
        return;
      }

      try {
        const currentUser = await api.me(storedToken);
        setAuth(storedToken, currentUser);
        setPage("dashboard");
      } catch {
        setAuth("", null);
      } finally {
        setLoading(false);
      }
    }

    void bootstrap();
  }, []);

  useEffect(() => {
    if (!token || !user) {
      setRepositoryConfig(null);
      setRecords([]);
      setReviews([]);
      setUsers([]);
      setModules([]);
      setTaskClusters([]);
      return;
    }
    void refreshAll(token);
  }, [refreshAll, token, user]);

  useEffect(() => {
    if (!isAuthenticated && !["welcome", "login", "register"].includes(page)) {
      setPage("welcome");
    }
  }, [isAuthenticated, page]);

  async function handleLogin(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);

    try {
      const response = await withBusy("登录中", () =>
        api.login(loginName.trim(), loginPassword),
      );
      setAuth(response.token, response.user);
      setLoginPassword("");
      setNotice({ tone: "success", text: `欢迎回来，${response.user.username}。` });
      setPage("dashboard");
    } catch (error) {
      showApiError(error);
    }
  }

  async function handleLogout() {
    setNotice(null);

    try {
      if (token) {
        await withBusy("退出登录中", () => api.logout(token));
      }
    } catch {
      // Ignore logout failures and clear local state anyway.
    } finally {
      setAuth("", null);
      setPage("welcome");
      setNotice({ tone: "info", text: "已退出当前账号。" });
    }
  }

  async function handleSubmitRegistration() {
    setNotice(null);
    if (registerPassword !== registerPasswordConfirm) {
      setNotice({ tone: "error", text: "两次输入的密码不一致。" });
      return;
    }

    try {
      await withBusy("提交注册申请中", () =>
        api.register({
          username: registerUsername.trim(),
          email: registerEmail.trim(),
          password: registerPassword,
          registration_note: registerNote.trim(),
        }),
      );
      setRegisterUsername("");
      setRegisterEmail("");
      setRegisterPassword("");
      setRegisterPasswordConfirm("");
      setRegisterNote("");
      setNotice({
        tone: "success",
        text: "注册申请已提交，等待管理员审批后即可登录。",
      });
    } catch (error) {
      showApiError(error);
    }
  }

  function resetSolutionForm() {
    setSolutionForm({
      ...defaultSolutionForm,
      module:
        repositoryConfig?.modules[0]?.module_key ??
        modules[0]?.module_key ??
        defaultSolutionForm.module,
    });
  }

  async function submitSolution(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setNotice(null);

    if (!token || !user) {
      setNotice({ tone: "error", text: "请先登录后再提交方案。" });
      return;
    }

    const payload = {
      ...solutionForm,
      tags: splitCommaText(solutionForm.tags),
      message_keywords: splitCommaText(solutionForm.message_keywords),
      submitter: user.username,
      source: "nextjs_solution_console",
    };

    try {
      await withBusy("提交方案中", async () => {
        if (isReviewer) {
          await api.createSolutionRecord(token, payload);
        } else {
          await api.submitSolutionReview(token, {
            ...payload,
            submission_type: "solution_record",
            created_by: user.username,
          });
        }
      });
      resetSolutionForm();
      await refreshAll();
      setNotice({
        tone: "success",
        text: isReviewer ? "方案已直接写入共享方案库。" : "方案已提交审核中心。",
      });
    } catch (error) {
      showApiError(error);
    }
  }

  async function applyLibraryFilters() {
    if (!token) {
      return;
    }

    setNotice(null);

    try {
      const response = await withBusy("检索方案库中", () =>
        api.listSolutionRecords(token, {
          search: librarySearch.trim() || undefined,
          module: libraryModule || undefined,
          review_status: libraryReviewStatus || undefined,
          error_code: libraryErrorCode.trim() || undefined,
          task_cluster: libraryTaskCluster || undefined,
          limit: 200,
        }),
      );
      setRecords(response.items);
      setNotice({ tone: "info", text: `已加载 ${response.items.length} 条方案记录。` });
    } catch (error) {
      showApiError(error);
    }
  }

  async function saveEditedRecord() {
    if (!token || !editingRecord) {
      return;
    }

    setNotice(null);

    try {
      await withBusy("保存方案中", () =>
        api.updateSolutionRecord(token, editingRecord.id, {
          ...editingRecord,
        }),
      );
      setEditingRecord(null);
      await refreshAll();
      setNotice({ tone: "success", text: "方案记录已更新。" });
    } catch (error) {
      showApiError(error);
    }
  }

  async function handleUserStatus(userId: number, action: string) {
    if (!token) {
      return;
    }

    try {
      await withBusy("更新用户状态中", () => api.updateUserStatus(token, userId, action));
      await refreshAll();
      setNotice({ tone: "success", text: "用户状态已更新。" });
    } catch (error) {
      showApiError(error);
    }
  }

  async function handleUserRole(userId: number, isReviewerRole: boolean, isAdminRole: boolean) {
    if (!token) {
      return;
    }

    try {
      await withBusy("更新权限中", () =>
        api.updateUserRoles(token, userId, {
          is_reviewer: isReviewerRole,
          is_admin: isAdminRole,
        }),
      );
      await refreshAll();
      setNotice({ tone: "success", text: "角色权限已保存。" });
    } catch (error) {
      showApiError(error);
    }
  }

  async function handleManualReview(
    reviewId: number,
    reviewStatus: "approved" | "needs_revision" | "rejected",
  ) {
    if (!token || !user) {
      return;
    }

    try {
      await withBusy("审核方案中", () =>
        api.manualReviewSolution(token, reviewId, {
          review_status: reviewStatus,
          reviewer: user.username,
          notes: reviewNotes,
        }),
      );
      setReviewNotes("");
      await refreshAll();
      setNotice({ tone: "success", text: "审核动作已提交。" });
    } catch (error) {
      showApiError(error);
    }
  }

  async function createCluster() {
    if (!token) {
      return;
    }

    try {
      await withBusy("创建任务簇中", () =>
        api.createTaskCluster(token, {
          display_name: clusterDraftName.trim(),
          description: clusterDraftDescription.trim(),
        }),
      );
      setClusterDraftName("");
      setClusterDraftDescription("");
      await refreshAll();
      setNotice({
        tone: "success",
        text: isReviewer ? "任务簇已创建。" : "任务簇已提交，等待审核。",
      });
    } catch (error) {
      showApiError(error);
    }
  }

  async function reviewCluster(clusterId: number, reviewStatus: string) {
    if (!token) {
      return;
    }

    try {
      await withBusy("审核任务簇中", () =>
        api.reviewTaskCluster(token, clusterId, reviewStatus),
      );
      await refreshAll();
      setNotice({ tone: "success", text: "任务簇状态已更新。" });
    } catch (error) {
      showApiError(error);
    }
  }

  async function createModule() {
    if (!token) {
      return;
    }

    try {
      await withBusy("创建模块中", () =>
        api.createOrUpdateModule(token, {
          module_key: moduleDraftKey.trim() || undefined,
          display_name: moduleDraftName.trim(),
          prefix: moduleDraftPrefix.trim().toUpperCase(),
          description: moduleDraftDescription.trim(),
          is_active: true,
        }),
      );
      setModuleDraftKey("");
      setModuleDraftName("");
      setModuleDraftPrefix("");
      setModuleDraftDescription("");
      await refreshAll();
      setNotice({ tone: "success", text: "模块前缀已更新。" });
    } catch (error) {
      showApiError(error);
    }
  }

  async function generateErrorCode() {
    if (!token || !generatorModule) {
      return;
    }

    try {
      const response = await withBusy("生成错误码中", () =>
        api.generateErrorCode(token, generatorModule),
      );
      setGeneratedCode(response.error_code);
      setGeneratedHistory((current) => [response.error_code, ...current].slice(0, 8));
      setNotice({ tone: "success", text: `已生成错误码 ${response.error_code}` });
    } catch (error) {
      showApiError(error);
    }
  }

  async function changePassword() {
    if (!token) {
      return;
    }

    if (nextPassword !== nextPasswordConfirm) {
      setNotice({ tone: "error", text: "两次输入的新密码不一致。" });
      return;
    }

    try {
      const response = await withBusy("更新密码中", () =>
        api.changePassword(token, currentPassword, nextPassword),
      );
      setUser(response.user);
      setCurrentPassword("");
      setNextPassword("");
      setNextPasswordConfirm("");
      setNotice({ tone: "success", text: "密码已更新。" });
    } catch (error) {
      showApiError(error);
    }
  }

  function toggleClusterSelection(clusterName: string) {
    setSolutionForm((current) => ({
      ...current,
      task_clusters: current.task_clusters.includes(clusterName)
        ? current.task_clusters.filter((value) => value !== clusterName)
        : [...current.task_clusters, clusterName],
    }));
  }

  function renderWelcomePage() {
    return (
      <div className="space-y-8">
        <SectionTitle
          title="解决方案库动态网页控制台"
          description="这套网页按 Streamlit 的使用逻辑来设计：左侧切页，右侧直接渲染，不引入复杂前端路由和状态机。所有核心动作都连接真实后端 API，可直接切到你的正式域名。"
          actions={
            <>
              <Button onClick={() => setPage("login")}>
                <LogIn className="h-4 w-4" />
                登录系统
              </Button>
              <Button variant="secondary" onClick={() => setPage("register")}>
                <UserPlus className="h-4 w-4" />
                注册账号
              </Button>
            </>
          }
        />

        <div className="grid gap-4 md:grid-cols-3">
          <MetricCard label="导航方式" value="单页切换" helper="像 Streamlit 一样简单直达，不需要前端路由跳转。" />
          <MetricCard label="认证流程" value="提交申请 + 审批" helper="注册只需提供邮箱账户，管理员审核通过后即可登录。" />
          <MetricCard label="部署方式" value="域名可替换" helper="前端通过环境变量连接真实后端，替换域名即可上线。" />
        </div>

        <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
          <Card>
            <CardHeader>
              <CardTitle>你会得到什么</CardTitle>
              <CardDescription>完整覆盖方案库系统的动态网页入口。</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-4 md:grid-cols-2">
              {[
                "欢迎页 / 登录 / 注册",
                "用户仪表盘与方案提报",
                "管理员审批与角色管理",
                "共享解决方案库搜索与编辑",
                "任务簇管理与审核",
                "错误码生成器与模块前缀展示",
              ].map((item) => (
                <div
                  key={item}
                  className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/60 px-4 py-3 text-sm text-[var(--foreground)]"
                >
                  {item}
                </div>
              ))}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>部署约定</CardTitle>
              <CardDescription>前后端可分开部署，也可以各自绑定自定义域名。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-[var(--muted-foreground)]">
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/70 p-4">
                <p className="font-medium text-[var(--foreground)]">前端域名</p>
                <p>`NEXT_PUBLIC_API_BASE_URL=https://your-domain.com/api/v1`</p>
              </div>
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/70 p-4">
                <p className="font-medium text-[var(--foreground)]">后端域名</p>
                <p>保持现有 FastAPI 服务，对外暴露 `/api/v1/*` 即可。</p>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  function renderLoginPage() {
    return (
      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>登录页面</CardTitle>
          <CardDescription>支持用户名或邮箱登录，并沿用现有后端的审批与权限体系。</CardDescription>
        </CardHeader>
        <CardContent>
          <form className="space-y-5" onSubmit={handleLogin}>
            <Field label="用户名或邮箱">
              <Input value={loginName} onChange={(event) => setLoginName(event.target.value)} />
            </Field>
            <Field label="密码">
              <Input
                type="password"
                value={loginPassword}
                onChange={(event) => setLoginPassword(event.target.value)}
              />
            </Field>
            <div className="flex flex-wrap gap-3">
              <Button type="submit">登录系统</Button>
              <Button type="button" variant="secondary" onClick={() => setPage("register")}>
                去注册
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    );
  }

  function renderRegisterPage() {
    return (
      <Card>
        <CardHeader>
          <CardTitle>注册页面</CardTitle>
          <CardDescription>填写用户名、邮箱和密码后即可直接提交注册申请，等待管理员审核。</CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="grid gap-5 md:grid-cols-2">
            <Field label="用户名">
              <Input
                value={registerUsername}
                onChange={(event) => setRegisterUsername(event.target.value)}
              />
            </Field>
            <Field label="邮箱">
              <Input
                type="email"
                value={registerEmail}
                onChange={(event) => setRegisterEmail(event.target.value)}
              />
            </Field>
            <Field label="密码">
              <Input
                type="password"
                value={registerPassword}
                onChange={(event) => setRegisterPassword(event.target.value)}
              />
            </Field>
            <Field label="确认密码">
              <Input
                type="password"
                value={registerPasswordConfirm}
                onChange={(event) => setRegisterPasswordConfirm(event.target.value)}
              />
            </Field>
          </div>

          <Field label="注册备注" hint="可填写部门、用途或申请说明。">
            <Textarea
              value={registerNote}
              onChange={(event) => setRegisterNote(event.target.value)}
            />
          </Field>

          <div className="rounded-3xl border border-[var(--border)] bg-[var(--muted)]/60 p-5 text-sm leading-6 text-[var(--muted-foreground)]">
            注册说明：提交后账号会进入管理员审核队列，审核通过后即可使用该邮箱账户登录。
          </div>

          <div className="flex flex-wrap gap-3">
            <Button type="button" onClick={handleSubmitRegistration}>
              提交注册申请
            </Button>
            <Button type="button" variant="secondary" onClick={() => setPage("login")}>
              返回登录
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  function renderDashboardPage() {
    const approvedRecords = records.filter((item) => item.review_status === "approved").length;
    const pendingReviews = reviews.filter((item) => item.review_status === "pending_review").length;

    return (
      <div className="space-y-8">
        <SectionTitle
          title="用户仪表盘"
          description="这里是方案录入与个人工作台。普通用户提交后进入审核流，审核员和管理员可直接写入全局共享方案库。"
        />

        <div className="grid gap-4 md:grid-cols-3">
          <MetricCard label="共享方案数" value={approvedRecords} helper="已审核通过并可复用的正式记录。" />
          <MetricCard label="待审核项" value={pendingReviews} helper="等待人工审核的方案与修订建议。" />
          <MetricCard label="已启用模块" value={modules.length} helper="模块前缀由共享配置统一维护。" />
        </div>

        <Card>
          <CardHeader>
            <CardTitle>提交解决方案</CardTitle>
            <CardDescription>字段直连后端模型，保持和原系统同一套入库结构。</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-6" onSubmit={submitSolution}>
              <div className="grid gap-5 lg:grid-cols-3">
                <Field label="模块">
                  <Select
                    value={solutionForm.module}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, module: event.target.value }))
                    }
                  >
                    <option value="">请选择模块</option>
                    {modules.map((module) => (
                      <option key={module.id} value={module.module_key}>
                        {module.display_name}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="子模块">
                  <Input
                    value={solutionForm.submodule}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, submodule: event.target.value }))
                    }
                  />
                </Field>
                <Field label="错误名">
                  <Input
                    value={solutionForm.error_name}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, error_name: event.target.value }))
                    }
                  />
                </Field>
                <Field label="错误类别">
                  <Input
                    value={solutionForm.error_category}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, error_category: event.target.value }))
                    }
                  />
                </Field>
                <Field label="规范签名">
                  <Input
                    value={solutionForm.normalized_signature}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        normalized_signature: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="影响范围">
                  <Input
                    value={solutionForm.impact_scope}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, impact_scope: event.target.value }))
                    }
                  />
                </Field>
              </div>

              <div className="grid gap-5 lg:grid-cols-2">
                <Field label="错误消息">
                  <Textarea
                    value={solutionForm.message}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, message: event.target.value }))
                    }
                  />
                </Field>
                <Field label="触发场景">
                  <Textarea
                    value={solutionForm.trigger_scenario}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        trigger_scenario: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="根因分析">
                  <Textarea
                    value={solutionForm.root_cause_analysis}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        root_cause_analysis: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="已验证解决方案">
                  <Textarea
                    value={solutionForm.verified_solution}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        verified_solution: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="临时绕过方案">
                  <Textarea
                    value={solutionForm.workaround}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, workaround: event.target.value }))
                    }
                  />
                </Field>
                <Field label="异常说明">
                  <Textarea
                    value={solutionForm.exception_description}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        exception_description: event.target.value,
                      }))
                    }
                  />
                </Field>
              </div>

              <div className="grid gap-5 lg:grid-cols-4">
                <Field label="责任部门">
                  <Input
                    value={solutionForm.owner_department}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        owner_department: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="来源">
                  <Input
                    value={solutionForm.report_source}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        report_source: event.target.value,
                      }))
                    }
                  />
                </Field>
                <Field label="标签" hint="使用逗号分隔">
                  <Input
                    value={solutionForm.tags}
                    onChange={(event) =>
                      setSolutionForm((current) => ({ ...current, tags: event.target.value }))
                    }
                  />
                </Field>
                <Field label="关键词" hint="使用逗号分隔">
                  <Input
                    value={solutionForm.message_keywords}
                    onChange={(event) =>
                      setSolutionForm((current) => ({
                        ...current,
                        message_keywords: event.target.value,
                      }))
                    }
                  />
                </Field>
              </div>

              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <Label>任务簇</Label>
                  <div className="flex items-center gap-3 text-sm text-[var(--muted-foreground)]">
                    <span>可复用</span>
                    <Switch
                      checked={solutionForm.reusable}
                      onChange={(event) =>
                        setSolutionForm((current) => ({
                          ...current,
                          reusable: event.target.checked,
                        }))
                      }
                    />
                  </div>
                </div>
                <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
                  {taskClusters
                    .filter((cluster) => cluster.review_status === "approved")
                    .map((cluster) => {
                      const checked = solutionForm.task_clusters.includes(cluster.cluster_key);
                      return (
                        <button
                          key={cluster.id}
                          type="button"
                          className={cn(
                            "rounded-2xl border px-4 py-3 text-left text-sm transition",
                            checked
                              ? "border-[var(--accent)] bg-[rgba(11,92,173,0.08)]"
                              : "border-[var(--border)] bg-[var(--muted)]/55",
                          )}
                          onClick={() => toggleClusterSelection(cluster.cluster_key)}
                        >
                          <div className="font-medium text-[var(--foreground)]">
                            {cluster.display_name}
                          </div>
                          <p className="mt-1 text-xs leading-5 text-[var(--muted-foreground)]">
                            {cluster.description || "暂无说明"}
                          </p>
                        </button>
                      );
                    })}
                </div>
              </div>

              <div className="flex flex-wrap gap-3">
                <Button type="submit">{isReviewer ? "直接入库" : "提交审核"}</Button>
                <Button type="button" variant="secondary" onClick={resetSolutionForm}>
                  清空表单
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>自定义任务簇</CardTitle>
            <CardDescription>可由用户新增任务簇，审核通过后进入全局共享配置。</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4 lg:grid-cols-[1fr_1fr_auto]">
            <Field label="任务簇名称">
              <Input
                value={clusterDraftName}
                onChange={(event) => setClusterDraftName(event.target.value)}
              />
            </Field>
            <Field label="任务簇说明">
              <Input
                value={clusterDraftDescription}
                onChange={(event) => setClusterDraftDescription(event.target.value)}
              />
            </Field>
            <div className="flex items-end">
              <Button type="button" onClick={createCluster}>
                创建任务簇
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  function renderAdminPage() {
    const pendingReviews = reviews.filter((item) => item.review_status === "pending_review");
    const pendingClusters = taskClusters.filter((item) => item.review_status === "pending_review");

    return (
      <div className="space-y-8">
        <SectionTitle
          title="管理员仪表盘"
          description="集中处理注册审批、管理员提升、方案审核、模块前缀和任务簇治理。"
        />

        <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
          <Card>
            <CardHeader>
              <CardTitle>用户管理</CardTitle>
              <CardDescription>审批注册、禁用账号、提升 reviewer/admin 权限。</CardDescription>
            </CardHeader>
            <CardContent>
              <TableWrapper>
                <Table>
                  <THead>
                    <TR>
                      <TH>用户</TH>
                      <TH>状态</TH>
                      <TH>权限</TH>
                      <TH>操作</TH>
                    </TR>
                  </THead>
                  <TBody>
                    {users.map((item) => (
                      <TR key={item.id}>
                        <TD>
                          <div className="space-y-1">
                            <div className="font-medium">{item.username}</div>
                            <div className="text-xs text-[var(--muted-foreground)]">{item.email}</div>
                          </div>
                        </TD>
                        <TD>
                          <Badge className={statusBadgeTone(item.status)}>{item.status}</Badge>
                        </TD>
                        <TD>
                          <div className="flex flex-wrap gap-2">
                            <label className="flex items-center gap-2 text-xs">
                              <Switch
                                checked={item.is_reviewer || item.is_admin}
                                onChange={(event) =>
                                  void handleUserRole(item.id, event.target.checked, item.is_admin)
                                }
                              />
                              reviewer
                            </label>
                            <label className="flex items-center gap-2 text-xs">
                              <Switch
                                checked={item.is_admin}
                                onChange={(event) =>
                                  void handleUserRole(
                                    item.id,
                                    item.is_reviewer || event.target.checked,
                                    event.target.checked,
                                  )
                                }
                              />
                              admin
                            </label>
                          </div>
                        </TD>
                        <TD>
                          <div className="flex flex-wrap gap-2">
                            <Button size="sm" variant="secondary" onClick={() => void handleUserStatus(item.id, "approve")}>
                              通过
                            </Button>
                            <Button size="sm" variant="secondary" onClick={() => void handleUserStatus(item.id, "enable")}>
                              启用
                            </Button>
                            <Button size="sm" variant="ghost" onClick={() => void handleUserStatus(item.id, "disable")}>
                              停用
                            </Button>
                            <Button size="sm" variant="danger" onClick={() => void handleUserStatus(item.id, "reject")}>
                              拒绝
                            </Button>
                          </div>
                        </TD>
                      </TR>
                    ))}
                  </TBody>
                </Table>
              </TableWrapper>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>模块前缀维护</CardTitle>
              <CardDescription>新增模块时自动参与错误码生成。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="模块名称">
                <Input
                  value={moduleDraftName}
                  onChange={(event) => setModuleDraftName(event.target.value)}
                />
              </Field>
              <Field label="模块 key">
                <Input
                  value={moduleDraftKey}
                  onChange={(event) => setModuleDraftKey(event.target.value)}
                />
              </Field>
              <Field label="两位前缀">
                <Input
                  maxLength={2}
                  value={moduleDraftPrefix}
                  onChange={(event) => setModuleDraftPrefix(event.target.value.toUpperCase())}
                />
              </Field>
              <Field label="说明">
                <Textarea
                  value={moduleDraftDescription}
                  onChange={(event) => setModuleDraftDescription(event.target.value)}
                />
              </Field>
              <Button type="button" onClick={createModule}>
                保存模块
              </Button>
            </CardContent>
          </Card>
        </div>

        <Card>
          <CardHeader>
            <CardTitle>方案审核中心</CardTitle>
            <CardDescription>审核通过后，方案会自动写回全局共享方案库。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Field label="审核备注">
              <Textarea
                value={reviewNotes}
                onChange={(event) => setReviewNotes(event.target.value)}
              />
            </Field>
            <div className="grid gap-4">
              {pendingReviews.length === 0 ? (
                <p className="text-sm text-[var(--muted-foreground)]">暂无待审核方案。</p>
              ) : (
                pendingReviews.map((review) => (
                  <div key={review.id} className="rounded-2xl border border-[var(--border)] p-4">
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          <Badge className={statusBadgeTone(review.review_status)}>{review.review_status}</Badge>
                          <Badge>{review.module || "未指定模块"}</Badge>
                        </div>
                        <p className="text-base font-medium text-[var(--foreground)]">
                          {String(review.proposed_payload.error_name || "未命名方案")}
                        </p>
                        <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                          {takeFirstSentence(String(review.proposed_payload.verified_solution || ""))}
                        </p>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button size="sm" onClick={() => void handleManualReview(review.id, "approved")}>
                          通过
                        </Button>
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={() => void handleManualReview(review.id, "needs_revision")}
                        >
                          退回修改
                        </Button>
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={() => void handleManualReview(review.id, "rejected")}
                        >
                          拒绝
                        </Button>
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>任务簇审核</CardTitle>
            <CardDescription>审核用户新建的任务簇，决定是否进入共享方案库体系。</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-4">
            {pendingClusters.length === 0 ? (
              <p className="text-sm text-[var(--muted-foreground)]">暂无待审核任务簇。</p>
            ) : (
              pendingClusters.map((cluster) => (
                <div
                  key={cluster.id}
                  className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] p-4 lg:flex-row lg:items-center lg:justify-between"
                >
                  <div>
                    <p className="font-medium text-[var(--foreground)]">{cluster.display_name}</p>
                    <p className="text-sm text-[var(--muted-foreground)]">
                      {cluster.description || "暂无说明"}
                    </p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button size="sm" onClick={() => void reviewCluster(cluster.id, "approved")}>
                      通过
                    </Button>
                    <Button
                      size="sm"
                      variant="danger"
                      onClick={() => void reviewCluster(cluster.id, "rejected")}
                    >
                      拒绝
                    </Button>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  function renderLibraryPage() {
    const exportTokenSuffix = token ? `?access_token=${token}` : "";

    return (
      <div className="space-y-8">
        <SectionTitle
          title="解决方案库"
          description="全局共享知识库，支持全文检索、模块筛选、任务簇筛选、审核状态筛选，以及 reviewer/admin 编辑。"
          actions={
            <>
              <Button variant="secondary" onClick={() => void applyLibraryFilters()}>
                <Search className="h-4 w-4" />
                立即检索
              </Button>
              <Button variant="ghost" asChild>
                <a
                  href={`${apiBaseUrl}/solution-repository/export?format=csv${exportTokenSuffix}`}
                  target="_blank"
                  rel="noreferrer"
                >
                  导出 CSV
                </a>
              </Button>
            </>
          }
        />

        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-5">
            <Field label="全文搜索">
              <Input value={librarySearch} onChange={(event) => setLibrarySearch(event.target.value)} />
            </Field>
            <Field label="模块">
              <Select value={libraryModule} onChange={(event) => setLibraryModule(event.target.value)}>
                <option value="">全部模块</option>
                {modules.map((module) => (
                  <option key={module.id} value={module.module_key}>
                    {module.display_name}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="审核状态">
              <Select
                value={libraryReviewStatus}
                onChange={(event) => setLibraryReviewStatus(event.target.value)}
              >
                <option value="">全部状态</option>
                <option value="approved">approved</option>
                <option value="pending_review">pending_review</option>
                <option value="needs_revision">needs_revision</option>
                <option value="rejected">rejected</option>
              </Select>
            </Field>
            <Field label="错误码">
              <Input
                value={libraryErrorCode}
                onChange={(event) => setLibraryErrorCode(event.target.value)}
              />
            </Field>
            <Field label="任务簇">
              <Select
                value={libraryTaskCluster}
                onChange={(event) => setLibraryTaskCluster(event.target.value)}
              >
                <option value="">全部任务簇</option>
                {taskClusters
                  .filter((cluster) => cluster.review_status === "approved")
                  .map((cluster) => (
                    <option key={cluster.id} value={cluster.cluster_key}>
                      {cluster.display_name}
                    </option>
                  ))}
              </Select>
            </Field>
          </CardContent>
        </Card>

        {editingRecord && isReviewer ? (
          <Card>
            <CardHeader>
              <CardTitle>编辑方案记录</CardTitle>
              <CardDescription>直接修改共享方案库中的正式记录。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-4 lg:grid-cols-2">
                <Field label="错误名">
                  <Input
                    value={editingRecord.error_name}
                    onChange={(event) =>
                      setEditingRecord((current) =>
                        current ? { ...current, error_name: event.target.value } : current,
                      )
                    }
                  />
                </Field>
                <Field label="错误码">
                  <Input
                    value={editingRecord.error_code || ""}
                    onChange={(event) =>
                      setEditingRecord((current) =>
                        current ? { ...current, error_code: event.target.value } : current,
                      )
                    }
                  />
                </Field>
                <Field label="根因分析">
                  <Textarea
                    value={editingRecord.root_cause_analysis || ""}
                    onChange={(event) =>
                      setEditingRecord((current) =>
                        current ? { ...current, root_cause_analysis: event.target.value } : current,
                      )
                    }
                  />
                </Field>
                <Field label="已验证解决方案">
                  <Textarea
                    value={editingRecord.verified_solution || ""}
                    onChange={(event) =>
                      setEditingRecord((current) =>
                        current ? { ...current, verified_solution: event.target.value } : current,
                      )
                    }
                  />
                </Field>
              </div>
              <div className="flex flex-wrap gap-3">
                <Button onClick={saveEditedRecord}>保存修改</Button>
                <Button variant="secondary" onClick={() => setEditingRecord(null)}>
                  取消
                </Button>
              </div>
            </CardContent>
          </Card>
        ) : null}

        <div className="grid gap-4">
          {records.map((record) => (
            <Card key={record.id}>
              <CardContent className="space-y-4 pt-6">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-2">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge className={statusBadgeTone(record.review_status)}>{record.review_status}</Badge>
                      <Badge>{record.error_code || "自动生成"}</Badge>
                      <Badge>{record.module}</Badge>
                    </div>
                    <h3 className="text-lg font-semibold text-[var(--foreground)]">{record.error_name}</h3>
                    <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                      {takeFirstSentence(record.message || record.trigger_scenario || "")}
                    </p>
                  </div>
                  {isReviewer ? (
                    <Button variant="secondary" onClick={() => setEditingRecord(record)}>
                      编辑
                    </Button>
                  ) : null}
                </div>
                <div className="grid gap-4 text-sm lg:grid-cols-3">
                  <div>
                    <p className="font-medium text-[var(--foreground)]">任务簇</p>
                    <p className="text-[var(--muted-foreground)]">{joinList(record.task_clusters)}</p>
                  </div>
                  <div>
                    <p className="font-medium text-[var(--foreground)]">标签</p>
                    <p className="text-[var(--muted-foreground)]">{joinList(record.tags)}</p>
                  </div>
                  <div>
                    <p className="font-medium text-[var(--foreground)]">最近更新</p>
                    <p className="text-[var(--muted-foreground)]">{formatDate(record.updated_at)}</p>
                  </div>
                </div>
                <Separator />
                <div className="grid gap-4 lg:grid-cols-2">
                  <div>
                    <p className="mb-2 text-sm font-medium text-[var(--foreground)]">根因分析</p>
                    <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                      {takeFirstSentence(record.root_cause_analysis)}
                    </p>
                  </div>
                  <div>
                    <p className="mb-2 text-sm font-medium text-[var(--foreground)]">已验证解决方案</p>
                    <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                      {takeFirstSentence(record.verified_solution)}
                    </p>
                  </div>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>
    );
  }

  function renderErrorCodePage() {
    return (
      <div className="space-y-8">
        <SectionTitle
          title="错误代码生成器"
          description="基于后端真实序列生成错误码，前缀取自模块配置。当前生成格式为 `XX0001`，和模块前缀配置保持一致。"
        />

        <div className="grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <Card>
            <CardHeader>
              <CardTitle>生成错误码</CardTitle>
              <CardDescription>选择模块后向真实 API 请求，不使用前端本地模拟。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <Field label="模块">
                <Select
                  value={generatorModule}
                  onChange={(event) => setGeneratorModule(event.target.value)}
                >
                  <option value="">请选择模块</option>
                  {modules.map((module) => (
                    <option key={module.id} value={module.module_key}>
                      {module.display_name} / {module.prefix}
                    </option>
                  ))}
                </Select>
              </Field>
              <Button onClick={generateErrorCode}>
                <WandSparkles className="h-4 w-4" />
                生成错误码
              </Button>
              <div className="rounded-3xl border border-dashed border-[var(--border)] bg-[var(--muted)]/55 p-6">
                <p className="text-sm text-[var(--muted-foreground)]">当前结果</p>
                <p className="mt-2 text-4xl font-semibold tracking-tight text-[var(--foreground)]">
                  {generatedCode || "--"}
                </p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>模块前缀列表</CardTitle>
              <CardDescription>和后端统一维护，新增模块会即时出现在这里。</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="grid gap-3 md:grid-cols-2">
                {modules.map((module) => (
                  <div key={module.id} className="rounded-2xl border border-[var(--border)] p-4">
                    <div className="flex items-center justify-between gap-3">
                      <p className="font-medium text-[var(--foreground)]">{module.display_name}</p>
                      <Badge>{module.prefix}</Badge>
                    </div>
                    <p className="mt-2 text-sm text-[var(--muted-foreground)]">
                      {module.description || "暂无说明"}
                    </p>
                  </div>
                ))}
              </div>
              {generatedHistory.length > 0 ? (
                <>
                  <Separator />
                  <div className="space-y-2">
                    <p className="text-sm font-medium text-[var(--foreground)]">本次会话生成历史</p>
                    <div className="flex flex-wrap gap-2">
                      {generatedHistory.map((item) => (
                        <Badge key={item}>{item}</Badge>
                      ))}
                    </div>
                  </div>
                </>
              ) : null}
            </CardContent>
          </Card>
        </div>
      </div>
    );
  }

  function renderActivePage() {
    if (!isAuthenticated) {
      if (page === "login") {
        return renderLoginPage();
      }

      if (page === "register") {
        return renderRegisterPage();
      }

      return renderWelcomePage();
    }

    if (page === "dashboard") {
      return renderDashboardPage();
    }

    if (page === "admin") {
      return renderAdminPage();
    }

    if (page === "library") {
      return renderLibraryPage();
    }

    if (page === "codes") {
      return renderErrorCodePage();
    }

    return renderDashboardPage();
  }

  const publicNav = [
    { key: "welcome" as const, label: "欢迎页", icon: ShieldCheck },
    { key: "login" as const, label: "登录", icon: LogIn },
    { key: "register" as const, label: "注册", icon: UserPlus },
  ];

  const protectedNav = [
    { key: "dashboard" as const, label: "用户仪表盘", icon: ClipboardCheck },
    ...(isAdmin ? [{ key: "admin" as const, label: "管理员页", icon: UserCog }] : []),
    { key: "library" as const, label: "解决方案库", icon: BookCopy },
    { key: "codes" as const, label: "错误码生成器", icon: KeyRound },
  ];

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex items-center gap-3 rounded-full border border-[var(--border)] bg-[var(--card)] px-5 py-3 text-sm text-[var(--muted-foreground)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          正在加载控制台...
        </div>
      </div>
    );
  }

  return (
    <div className="grid gap-6 xl:grid-cols-[280px_minmax(0,1fr)]">
      <aside className="space-y-6">
        <Card className="sticky top-6 overflow-hidden">
          <CardHeader className="gap-4">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.22em] text-[var(--muted-foreground)]">
                  Streamlit Style
                </p>
                <CardTitle className="text-xl">Solution Console</CardTitle>
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setTheme(darkMode ? "light" : "dark")}
              >
                {darkMode ? <SunMedium className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </Button>
            </div>
            <CardDescription>单页导航、直连真实 API、生产可部署。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <div className="grid gap-2">
              {(isAuthenticated ? protectedNav : publicNav).map((item) => {
                const Icon = item.icon;
                const active = page === item.key;
                return (
                  <button
                    key={item.key}
                    type="button"
                    onClick={() => setPage(item.key)}
                    className={cn(
                      "flex items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm transition",
                      active
                        ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
                        : "bg-[var(--muted)]/55 text-[var(--foreground)] hover:bg-[var(--muted)]",
                    )}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>

            <Separator />

            {user ? (
              <div className="space-y-4">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-[var(--foreground)]">{user.username}</p>
                  <p className="text-xs text-[var(--muted-foreground)]">{user.email}</p>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge className={statusBadgeTone(user.status)}>{user.status}</Badge>
                  {user.roles.map((role) => (
                    <Badge key={role}>{role}</Badge>
                  ))}
                </div>

                <div className="space-y-3 rounded-2xl border border-[var(--border)] p-4">
                  <p className="text-sm font-medium text-[var(--foreground)]">修改密码</p>
                  <Input
                    type="password"
                    placeholder="当前密码"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                  />
                  <Input
                    type="password"
                    placeholder="新密码"
                    value={nextPassword}
                    onChange={(event) => setNextPassword(event.target.value)}
                  />
                  <Input
                    type="password"
                    placeholder="确认新密码"
                    value={nextPasswordConfirm}
                    onChange={(event) => setNextPasswordConfirm(event.target.value)}
                  />
                  <Button className="w-full" variant="secondary" onClick={changePassword}>
                    <Lock className="h-4 w-4" />
                    更新密码
                  </Button>
                </div>

                <Button className="w-full" variant="ghost" onClick={handleLogout}>
                  <LogOut className="h-4 w-4" />
                  退出登录
                </Button>
              </div>
            ) : (
              <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/60 p-4 text-sm text-[var(--muted-foreground)]">
                初始管理员账号由后端自动创建，前端不在公开页直接暴露密码。需要时请在部署配置中统一管理。
              </div>
            )}
          </CardContent>
        </Card>
      </aside>

      <main className="space-y-6 pb-12">
        <NoticeBanner notice={notice} />
        {busyLabel ? (
          <div className="inline-flex items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--card)] px-4 py-2 text-sm text-[var(--muted-foreground)]">
            <LoaderCircle className="h-4 w-4 animate-spin" />
            {busyLabel}
          </div>
        ) : null}
        {renderActivePage()}
      </main>
    </div>
  );
}
