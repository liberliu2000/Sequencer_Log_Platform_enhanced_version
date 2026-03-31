/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { startTransition, useEffect, useMemo, useState, type FormEvent } from "react";
import { useTheme } from "next-themes";
import {
  AlertTriangle,
  Archive,
  BookCopy,
  Brain,
  Clock3,
  Database,
  Download,
  FileSearch,
  Gauge,
  GitPullRequestArrow,
  Home,
  KeyRound,
  LoaderCircle,
  LogIn,
  LogOut,
  Moon,
  RefreshCcw,
  Search,
  Send,
  Settings2,
  Shield,
  SunMedium,
  Upload,
  Users,
  WandSparkles,
  Workflow,
} from "lucide-react";

import {
  PlatformApiError,
  buildApiUrl,
  normalizeApiBaseUrl,
  platformRequest,
} from "@/lib/platform-api";
import { cn } from "@/lib/utils";
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
import { Separator } from "@/components/ui/separator";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import {
  type AnyRecord,
  type Notice,
  ChipToggleGroup,
  DataTable,
  DistributionList,
  Field,
  JsonPreview,
  MetricCard,
  NoticeBanner,
  SectionTitle,
  StatusBadge,
  TabBar,
  formatDate,
  parseJsonText,
  safeArray,
  safeObject,
  shortText,
} from "@/components/platform-shared";

type PageKey =
  | "welcome"
  | "login"
  | "register"
  | "dashboard"
  | "history"
  | "upload"
  | "events"
  | "performance"
  | "timeline"
  | "errors"
  | "parameters"
  | "llm"
  | "solutionHub"
  | "files"
  | "unknown"
  | "rules"
  | "config"
  | "exports"
  | "users";

type LlmTabKey = "history" | "diagnose";
type SolutionTabKey = "submit" | "query" | "review" | "taxonomy";

const TOKEN_STORAGE_KEY = "sequencer-platform-auth-token";
const API_BASE_STORAGE_KEY = "sequencer-platform-api-base";
const TASK_STORAGE_KEY = "sequencer-platform-selected-task";

const durationUnits = [
  { label: "毫秒 (ms)", value: "ms" },
  { label: "秒 (s)", value: "s" },
  { label: "分钟 (min)", value: "min" },
  { label: "小时 (h)", value: "h" },
];

const defaultReviewDraft = {
  error_name: "",
  error_category: "",
  error_code: "",
  impact_scope: "",
  owner_department: "",
  root_cause_analysis: "",
  verified_solution: "",
  workaround: "",
  submitter: "",
  reusable: true,
};

export function LogPlatformConsole() {
  const { resolvedTheme, setTheme } = useTheme();

  const [apiBase, setApiBase] = useState(normalizeApiBaseUrl(""));
  const [token, setToken] = useState("");
  const [user, setUser] = useState<AnyRecord | null>(null);
  const [page, setPage] = useState<PageKey>("welcome");
  const [loading, setLoading] = useState(true);
  const [busyLabel, setBusyLabel] = useState("");
  const [notice, setNotice] = useState<Notice | null>(null);
  const [health, setHealth] = useState<AnyRecord | null>(null);

  const [tasks, setTasks] = useState<AnyRecord[]>([]);
  const [selectedTaskUuid, setSelectedTaskUuid] = useState("");
  const [repoConfig, setRepoConfig] = useState<AnyRecord | null>(null);
  const [modules, setModules] = useState<AnyRecord[]>([]);
  const [taskClusters, setTaskClusters] = useState<AnyRecord[]>([]);
  const [userList, setUserList] = useState<AnyRecord[]>([]);

  const [loginName, setLoginName] = useState("");
  const [loginPassword, setLoginPassword] = useState("");
  const [registerUsername, setRegisterUsername] = useState("");
  const [registerEmail, setRegisterEmail] = useState("");
  const [registerPassword, setRegisterPassword] = useState("");
  const [registerPasswordConfirm, setRegisterPasswordConfirm] = useState("");
  const [registerNote, setRegisterNote] = useState("");
  const [registerCode, setRegisterCode] = useState("");
  const [registerVerificationToken, setRegisterVerificationToken] = useState("");
  const [registerStep, setRegisterStep] = useState<"draft" | "code_sent" | "verified" | "submitted">("draft");

  const [currentPassword, setCurrentPassword] = useState("");
  const [nextPassword, setNextPassword] = useState("");
  const [nextPasswordConfirm, setNextPasswordConfirm] = useState("");

  const [uploadFiles, setUploadFiles] = useState<File[]>([]);
  const [uploadCpuCores, setUploadCpuCores] = useState("4");

  const [eventsFilter, setEventsFilter] = useState({ component: "", level: "", cycleNo: "", chipName: "", search: "" });
  const [eventsResponse, setEventsResponse] = useState<AnyRecord>({ items: [], total: 0 });

  const [performanceUnit, setPerformanceUnit] = useState("ms");
  const [performanceBundle, setPerformanceBundle] = useState<AnyRecord>({
    cycleSummary: [],
    steps: { items: [], total: 0 },
    operationalMetrics: {},
  });

  const [timelineCycleNo, setTimelineCycleNo] = useState("");
  const [timelineTrackOrder, setTimelineTrackOrder] = useState("default");
  const [timelineBundle, setTimelineBundle] = useState<AnyRecord>({ cycles: [], rows: [], errors: [] });

  const [errorsResponse, setErrorsResponse] = useState<AnyRecord>({ items: [], total: 0 });
  const [selectedParameters, setSelectedParameters] = useState<string[]>([]);
  const [parameterUnit, setParameterUnit] = useState("s");
  const [parameterBundle, setParameterBundle] = useState<AnyRecord>({
    definitions: [],
    parameterSeries: {},
    substepSeries: [],
    rowScanMetrics: [],
  });

  const [llmTab, setLlmTab] = useState<LlmTabKey>("history");
  const [llmBundle, setLlmBundle] = useState<AnyRecord>({
    config: {},
    errors: [],
    history: [],
    latestDiagnosis: null,
    latestReview: null,
    similarCases: [],
  });
  const [selectedErrorSignature, setSelectedErrorSignature] = useState("");
  const [selectedHistoryIndex, setSelectedHistoryIndex] = useState("0");
  const [reviewDraft, setReviewDraft] = useState({ ...defaultReviewDraft });
  const [llmForm, setLlmForm] = useState({
    analysisDepth: "medium",
    module: "",
    submodule: "",
    triggerScenario: "",
    operationPath: "",
    customerSymptom: "",
    environmentInfo: "",
    reproductionSteps: "",
    sourceNotes: "",
    force: false,
  });
  const [llmSourceFiles, setLlmSourceFiles] = useState<File[]>([]);

  const [solutionTab, setSolutionTab] = useState<SolutionTabKey>("submit");
  const [hubForm, setHubForm] = useState({
    module: "",
    error_name: "",
    message: "",
    message_keywords: "",
    tags: "",
    root_cause_analysis: "",
    verified_solution: "",
    workaround: "",
    trigger_scenario: "",
    task_uuid: "",
    normalized_signature: "",
    new_cluster: "",
  });
  const [hubSelectedClusters, setHubSelectedClusters] = useState<string[]>([]);
  const [hubQuery, setHubQuery] = useState({
    search: "",
    module: "",
    task_cluster: "",
    error_code: "",
    error_name: "",
    submitter: "",
    message_keyword: "",
    review_status: "",
    reusable: "",
  });
  const [hubBundle, setHubBundle] = useState<AnyRecord>({
    records: { items: [], total: 0 },
    reviews: { items: [], total: 0 },
    taskClusters: [],
    modules: [],
  });
  const [selectedReviewId, setSelectedReviewId] = useState("");
  const [selectedClusterId, setSelectedClusterId] = useState("");
  const [hubReviewNotes, setHubReviewNotes] = useState("");
  const [newClusterDraft, setNewClusterDraft] = useState({ name: "", description: "" });
  const [newModuleDraft, setNewModuleDraft] = useState({ module_key: "", display_name: "", prefix: "", description: "" });

  const [filesBundle, setFilesBundle] = useState<AnyRecord>({ list: { items: [], total: 0 }, preview: null });
  const [selectedFilePath, setSelectedFilePath] = useState("");
  const [filePreviewLines, setFilePreviewLines] = useState("120");

  const [unknownBundle, setUnknownBundle] = useState<AnyRecord>({ items: [], total: 0 });
  const [unknownFilter, setUnknownFilter] = useState({ min_occurrence: "1", limit: "100", review_status: "" });
  const [selectedUnknownSignature, setSelectedUnknownSignature] = useState("");
  const [unknownReviewer, setUnknownReviewer] = useState("");
  const [unknownReviewNotes, setUnknownReviewNotes] = useState("");

  const [rulesBundle, setRulesBundle] = useState<AnyRecord>({
    localPreview: null,
    llmPreview: null,
    files: { items: [], total: 0 },
    reviews: { items: [], total: 0 },
    unknownPool: { items: [], total: 0 },
  });
  const [ruleLlmEnabled, setRuleLlmEnabled] = useState(false);
  const [ruleForceRefresh, setRuleForceRefresh] = useState(false);
  const [selectedRuleSignatures, setSelectedRuleSignatures] = useState<string[]>([]);
  const [selectedRuleFile, setSelectedRuleFile] = useState("");
  const [ruleFileContent, setRuleFileContent] = useState<AnyRecord | null>(null);
  const [ruleReviewer, setRuleReviewer] = useState("");
  const [ruleReviewNotes, setRuleReviewNotes] = useState("");

  const [configBundle, setConfigBundle] = useState<AnyRecord>({});
  const [thresholdEditor, setThresholdEditor] = useState({
    default_threshold_ms: "0",
    step_thresholds_ms: "{}",
    parameter_thresholds_seconds: "{}",
    parameter_expected_seconds: "{}",
    llm_context: "{}",
  });

  const [dashboardBundle, setDashboardBundle] = useState<AnyRecord>({
    dashboard: null,
    status: null,
    performance: null,
  });

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

  function showError(error: unknown) {
    const text =
      error instanceof PlatformApiError || error instanceof Error
        ? error.message
        : "请求失败，请稍后重试。";
    setNotice({ tone: "error", text });
  }

  async function request<T>(path: string, options: Parameters<typeof platformRequest<T>>[2] = {}) {
    return platformRequest<T>(apiBase, path, {
      ...options,
      token: options.token === undefined ? token : options.token,
    });
  }

  function applySession(nextToken: string, nextUser: AnyRecord | null) {
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

  async function refreshHealth(currentBase = apiBase) {
    try {
      const nextHealth = await platformRequest<AnyRecord>(currentBase, "/health", { token: null });
      setHealth(nextHealth);
    } catch (error) {
      setHealth({ status: "error", detail: error instanceof Error ? error.message : "unreachable" });
    }
  }

  async function refreshShell(activeToken = token) {
    if (!activeToken) {
      return;
    }
    const [tasksPage, repo] = await Promise.all([
      platformRequest<AnyRecord>(apiBase, "/tasks", {
        token: activeToken,
        query: { page: 1, page_size: 100 },
      }),
      platformRequest<AnyRecord>(apiBase, "/solution-repository/config", {
        token: activeToken,
      }),
    ]);
    const nextTasks = safeArray(tasksPage.items);
    const nextRepo = safeObject(repo);
    setTasks(nextTasks);
    setRepoConfig(nextRepo);
    setModules(safeArray(nextRepo.modules));
    setTaskClusters(safeArray(nextRepo.task_clusters));
    const validSelected = nextTasks.some((task) => String(task.task_uuid) === selectedTaskUuid);
    const nextSelected = validSelected ? selectedTaskUuid : String(nextTasks[0]?.task_uuid || "");
    setSelectedTaskUuid(nextSelected);
    if (typeof window !== "undefined" && nextSelected) {
      window.localStorage.setItem(TASK_STORAGE_KEY, nextSelected);
    }
  }

  async function loadDashboard() {
    if (!selectedTaskUuid) {
      setDashboardBundle({ dashboard: null, status: null, performance: null });
      return;
    }
    const [dashboard, status, performance] = await Promise.all([
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/dashboard`),
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/status`),
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/performance-summary`),
    ]);
    setDashboardBundle({ dashboard, status, performance });
  }

  async function loadEvents() {
    if (!selectedTaskUuid) {
      setEventsResponse({ items: [], total: 0 });
      return;
    }
    const result = await request<AnyRecord>(`/tasks/${selectedTaskUuid}/events`, {
      query: {
        component: eventsFilter.component || undefined,
        level: eventsFilter.level || undefined,
        cycle_no: eventsFilter.cycleNo || undefined,
        chip_name: eventsFilter.chipName || undefined,
        search: eventsFilter.search || undefined,
        limit: 200,
        offset: 0,
      },
    });
    setEventsResponse(result);
  }

  async function loadPerformance() {
    if (!selectedTaskUuid) {
      setPerformanceBundle({ cycleSummary: [], steps: { items: [], total: 0 }, operationalMetrics: {} });
      return;
    }
    const [cycleSummary, steps, operationalMetrics] = await Promise.all([
      request<any[]>(`/tasks/${selectedTaskUuid}/cycle-summary`, { query: { unit: performanceUnit } }),
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/steps`, { query: { limit: 200, offset: 0 } }),
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/operational-metrics`),
    ]);
    setPerformanceBundle({ cycleSummary: safeArray(cycleSummary), steps, operationalMetrics });
  }

  async function loadTimeline() {
    if (!selectedTaskUuid) {
      setTimelineBundle({ cycles: [], rows: [], errors: [] });
      return;
    }
    const cycleParam = timelineCycleNo ? Number(timelineCycleNo) : undefined;
    const [cycles, rows, errors] = await Promise.all([
      request<any[]>(`/tasks/${selectedTaskUuid}/cycles`),
      request<any[]>(`/tasks/${selectedTaskUuid}/movement-timeline`, {
        query: { cycle_no: cycleParam, track_order: timelineTrackOrder },
      }),
      request<any[]>(`/tasks/${selectedTaskUuid}/movement-timeline/errors`, {
        query: { cycle_no: cycleParam },
      }),
    ]);
    setTimelineBundle({ cycles: safeArray(cycles), rows: safeArray(rows), errors: safeArray(errors) });
  }

  async function loadErrors() {
    if (!selectedTaskUuid) {
      setErrorsResponse({ items: [], total: 0 });
      return;
    }
    const result = await request<AnyRecord>(`/tasks/${selectedTaskUuid}/errors`, {
      query: { limit: 200, offset: 0 },
    });
    const items = safeArray(result.items);
    setErrorsResponse(result);
    if (!selectedErrorSignature && items[0]?.normalized_signature) {
      setSelectedErrorSignature(String(items[0].normalized_signature));
    }
    if (!reviewDraft.error_name && items[0]?.display_signature) {
      setReviewDraft((current) => ({ ...current, error_name: String(items[0].display_signature) }));
    }
  }

  async function loadParameters() {
    if (!selectedTaskUuid) {
      setParameterBundle({ definitions: [], parameterSeries: {}, substepSeries: [], rowScanMetrics: [] });
      return;
    }
    const definitions = await request<any[]>("/parameter-definitions");
    const filtered = safeArray(definitions).filter((item) => item?.parameter_name !== "imaging_time");
    let active = selectedParameters;
    if (!active.length && filtered.length) {
      active = filtered.slice(0, 4).map((item) => String(item.parameter_name));
      setSelectedParameters(active);
    }
    const seriesEntries = await Promise.all(
      active.map(async (name) => {
        const rows = await request<any[]>(`/tasks/${selectedTaskUuid}/parameter-series/${name}`, {
          query: { unit: parameterUnit },
        });
        return [name, safeArray(rows)] as const;
      }),
    );
    const [substepSeries, rowScanMetrics] = await Promise.all([
      request<any[]>(`/tasks/${selectedTaskUuid}/substep-cycle-series`, { query: { agg_mode: "mean", unit: parameterUnit } }),
      request<any[]>(`/tasks/${selectedTaskUuid}/row-scan-metric-series`, { query: { unit: "ms" } }),
    ]);
    setParameterBundle({
      definitions: filtered,
      parameterSeries: Object.fromEntries(seriesEntries),
      substepSeries: safeArray(substepSeries),
      rowScanMetrics: safeArray(rowScanMetrics),
    });
  }

  async function loadLlm() {
    if (!selectedTaskUuid) {
      setLlmBundle({ config: {}, errors: [], history: [], latestDiagnosis: null, latestReview: null, similarCases: [] });
      return;
    }
    const [config, errors, history] = await Promise.all([
      request<AnyRecord>("/config"),
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/errors`, { query: { limit: 200, offset: 0 } }),
      request<any[]>(`/tasks/${selectedTaskUuid}/llm-results`, { query: { limit: 300 } }),
    ]);
    setLlmBundle((current) => ({
      ...current,
      config,
      errors: safeArray(errors.items),
      history: safeArray(history),
    }));
  }

  async function loadSolutionHub() {
    const [records, reviews, clusters, moduleResp] = await Promise.all([
      request<AnyRecord>("/solution-repository/records", {
        query: {
          ...hubQuery,
          reusable: hubQuery.reusable === "" ? undefined : hubQuery.reusable === "true",
          limit: 200,
        },
      }),
      request<AnyRecord>("/solution-reviews", { query: { status: hubQuery.review_status || undefined, limit: 200 } }),
      request<AnyRecord>("/solution-repository/task-clusters", { query: { include_pending: isReviewer } }),
      request<AnyRecord>("/solution-repository/modules"),
    ]);
    const nextModules = safeArray(moduleResp.items);
    const nextClusters = safeArray(clusters.items);
    setModules(nextModules);
    setTaskClusters(nextClusters);
    setHubBundle({ records, reviews, taskClusters: nextClusters, modules: nextModules });
  }

  async function loadFiles() {
    if (!selectedTaskUuid) {
      setFilesBundle({ list: { items: [], total: 0 }, preview: null });
      return;
    }
    const list = await request<AnyRecord>(`/tasks/${selectedTaskUuid}/files`, { query: { limit: 300, offset: 0 } });
    const items = safeArray(list.items);
    const filePath = selectedFilePath || String(items[0]?.relative_path || "");
    setSelectedFilePath(filePath);
    const preview = filePath
      ? await request<AnyRecord>(`/tasks/${selectedTaskUuid}/files/preview`, {
          query: { relative_path: filePath, max_lines: Number(filePreviewLines || 120) },
        })
      : null;
    setFilesBundle({ list, preview });
  }

  async function loadUnknown() {
    const response = await request<AnyRecord>("/active-learning/unknown-clusters", {
      query: {
        min_occurrence: Number(unknownFilter.min_occurrence || 1),
        limit: Number(unknownFilter.limit || 100),
        review_status: unknownFilter.review_status || undefined,
      },
    });
    const items = safeArray(response.items);
    setUnknownBundle(response);
    if (!selectedUnknownSignature && items[0]?.signature) {
      setSelectedUnknownSignature(String(items[0].signature));
    }
  }

  async function loadRules(fetchLlmPreview = false) {
    const [localPreview, files, reviews, unknownPool] = await Promise.all([
      request<AnyRecord>("/active-learning/rule-suggestions/preview", { query: { use_llm: false } }),
      request<AnyRecord>("/active-learning/rule-suggestions/files", { query: { limit: 50 } }),
      request<AnyRecord>("/active-learning/rule-suggestions/reviews", { query: { limit: 200 } }),
      request<AnyRecord>("/active-learning/unknown-clusters", { query: { min_occurrence: 1, limit: 200 } }),
    ]);
    let llmPreview = rulesBundle.llmPreview;
    if (fetchLlmPreview && ruleLlmEnabled) {
      llmPreview = await request<AnyRecord>("/active-learning/rule-suggestions/preview", {
        query: {
          use_llm: true,
          force_refresh: ruleForceRefresh,
          selected_signatures: selectedRuleSignatures.length ? selectedRuleSignatures.join(",") : undefined,
        },
      });
    }
    setRulesBundle({ localPreview, llmPreview, files, reviews, unknownPool });
  }

  async function loadRuleFile(filename: string) {
    if (!filename) {
      setRuleFileContent(null);
      return;
    }
    const result = await request<AnyRecord>("/active-learning/rule-suggestions/file", { query: { filename } });
    setRuleFileContent(result);
  }

  async function loadConfig() {
    const config = await request<AnyRecord>("/config");
    const thresholds = safeObject(config.thresholds);
    setConfigBundle(config);
    setThresholdEditor({
      default_threshold_ms: String(thresholds.default_threshold_ms ?? 0),
      step_thresholds_ms: JSON.stringify(thresholds.step_thresholds_ms ?? {}, null, 2),
      parameter_thresholds_seconds: JSON.stringify(thresholds.parameter_thresholds_seconds ?? {}, null, 2),
      parameter_expected_seconds: JSON.stringify(thresholds.parameter_expected_seconds ?? {}, null, 2),
      llm_context: JSON.stringify(thresholds.llm_context ?? {}, null, 2),
    });
  }

  async function loadUsers() {
    if (!isAdmin) {
      setUserList([]);
      return;
    }
    const response = await request<AnyRecord>("/admin/users");
    setUserList(safeArray(response.items));
  }

  async function handleLogin(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    try {
      const response = await withBusy("正在登录", () =>
        platformRequest<AnyRecord>(apiBase, "/auth/login", {
          token: null,
          method: "POST",
          body: { login_name: loginName.trim(), password: loginPassword },
        }),
      );
      applySession(String(response.token || ""), safeObject(response.user));
      setPage("dashboard");
      setLoginPassword("");
      setNotice({ tone: "success", text: `欢迎回来，${response.user?.username || loginName}。` });
    } catch (error) {
      showError(error);
    }
  }

  async function handleRequestCode() {
    if (registerPassword !== registerPasswordConfirm) {
      setNotice({ tone: "error", text: "两次输入的密码不一致。" });
      return;
    }
    try {
      await withBusy("正在发送验证码", () =>
        platformRequest(apiBase, "/auth/register/request-code", {
          token: null,
          method: "POST",
          body: {
            username: registerUsername.trim(),
            email: registerEmail.trim(),
            password: registerPassword,
            registration_note: registerNote.trim() || undefined,
          },
        }),
      );
      setRegisterStep("code_sent");
      setNotice({ tone: "success", text: "验证码已发送，请前往邮箱查收。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleVerifyCode() {
    try {
      const response = await withBusy("正在验证邮箱", () =>
        platformRequest<AnyRecord>(apiBase, "/auth/register/verify-email", {
          token: null,
          method: "POST",
          body: { login_name: registerUsername.trim() || registerEmail.trim(), code: registerCode.trim() },
        }),
      );
      setRegisterVerificationToken(String(response.verification_token || ""));
      setRegisterStep("verified");
      setNotice({ tone: "success", text: "邮箱验证通过，现在可以提交注册申请。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleSubmitRegistration() {
    try {
      await withBusy("正在提交注册申请", () =>
        platformRequest(apiBase, "/auth/register", {
          token: null,
          method: "POST",
          body: { verification_token: registerVerificationToken },
        }),
      );
      setRegisterVerificationToken("");
      setRegisterCode("");
      setRegisterStep("submitted");
      setNotice({ tone: "success", text: "注册申请已提交，请等待管理员审核。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleLogout() {
    try {
      if (token) {
        await request("/auth/logout", { method: "POST", body: {} });
      }
    } catch {
      // ignore
    } finally {
      applySession("", null);
      setTasks([]);
      setRepoConfig(null);
      setSelectedTaskUuid("");
      setPage("welcome");
    }
  }

  async function handleChangePassword() {
    if (nextPassword !== nextPasswordConfirm) {
      setNotice({ tone: "error", text: "两次输入的新密码不一致。" });
      return;
    }
    try {
      const response = await withBusy("正在修改密码", () =>
        request<AnyRecord>("/auth/change-password", {
          method: "POST",
          body: { current_password: currentPassword, new_password: nextPassword },
        }),
      );
      setUser(safeObject(response.user));
      setCurrentPassword("");
      setNextPassword("");
      setNextPasswordConfirm("");
      setNotice({ tone: "success", text: "密码已更新。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleUploadLogs() {
    if (!uploadFiles.length) {
      setNotice({ tone: "error", text: "请先选择要上传的日志文件。" });
      return;
    }
    try {
      const formData = new FormData();
      uploadFiles.forEach((file) => formData.append("files", file));
      formData.append("cpu_cores", String(Number(uploadCpuCores || 1)));
      const result = await withBusy("正在上传并创建任务", () =>
        request<AnyRecord>("/tasks/upload", { method: "POST", formData }),
      );
      setSelectedTaskUuid(String(result.task_uuid || ""));
      setUploadFiles([]);
      await refreshShell();
      setPage("upload");
      setNotice({ tone: "success", text: "任务已提交，后台正在处理。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleDeleteTask(taskUuid: string) {
    try {
      await withBusy("正在删除任务", () => request(`/tasks/${taskUuid}`, { method: "DELETE" }));
      await refreshShell();
      setNotice({ tone: "success", text: `任务 ${taskUuid} 已删除。` });
    } catch (error) {
      showError(error);
    }
  }

  async function handleSaveThresholds() {
    try {
      await withBusy("正在保存阈值配置", () =>
        request("/config/thresholds", {
          method: "PUT",
          body: {
            default_threshold_ms: Number(thresholdEditor.default_threshold_ms || 0),
            step_thresholds_ms: parseJsonText(thresholdEditor.step_thresholds_ms, "step_thresholds_ms"),
            parameter_thresholds_seconds: parseJsonText(thresholdEditor.parameter_thresholds_seconds, "parameter_thresholds_seconds"),
            parameter_expected_seconds: parseJsonText(thresholdEditor.parameter_expected_seconds, "parameter_expected_seconds"),
            llm_context: parseJsonText(thresholdEditor.llm_context, "llm_context"),
          },
        }),
      );
      setNotice({ tone: "success", text: "阈值配置已保存。" });
      await loadConfig();
    } catch (error) {
      showError(error);
    }
  }

  async function handleRunDiagnosis() {
    if (!selectedTaskUuid || !selectedErrorSignature) {
      setNotice({ tone: "error", text: "请先选择任务和错误签名。" });
      return;
    }
    try {
      const formData = new FormData();
      formData.append("analysis_depth", llmForm.analysisDepth);
      formData.append("module", llmForm.module);
      formData.append("submodule", llmForm.submodule);
      formData.append("trigger_scenario", llmForm.triggerScenario);
      formData.append("operation_path", llmForm.operationPath);
      formData.append("customer_symptom", llmForm.customerSymptom);
      formData.append("environment_info", llmForm.environmentInfo);
      formData.append("reproduction_steps", llmForm.reproductionSteps);
      formData.append("source_notes", llmForm.sourceNotes);
      formData.append("existing_solution_json", JSON.stringify(reviewDraft));
      llmSourceFiles.forEach((file) => formData.append("source_files", file));
      const result = await withBusy("正在执行综合诊断", () =>
        request<AnyRecord>(`/tasks/${selectedTaskUuid}/errors/${selectedErrorSignature}/analyze`, {
          method: "POST",
          query: { force: llmForm.force },
          formData,
        }),
      );
      setLlmBundle((current) => ({ ...current, latestDiagnosis: result }));
      setNotice({ tone: "success", text: "综合诊断已完成。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleSubmitSolutionHub() {
    if (!hubForm.module || !hubForm.error_name) {
      setNotice({ tone: "error", text: "请至少填写模块和错误名称。" });
      return;
    }
    try {
      const payload = {
        module: hubForm.module,
        error_name: hubForm.error_name,
        message: hubForm.message,
        message_keywords: hubForm.message_keywords.split(",").map((item) => item.trim()).filter(Boolean),
        tags: hubForm.tags.split(",").map((item) => item.trim()).filter(Boolean),
        task_clusters: hubSelectedClusters,
        root_cause_analysis: hubForm.root_cause_analysis,
        verified_solution: hubForm.verified_solution,
        workaround: hubForm.workaround,
        trigger_scenario: hubForm.trigger_scenario,
        task_uuid: hubForm.task_uuid || undefined,
        normalized_signature: hubForm.normalized_signature || undefined,
        reusable: true,
        source: "next_frontend_solution_hub",
      };
      const endpoint = isReviewer ? "/solution-repository/records" : "/solution-reviews";
      await withBusy("正在提交方案", () =>
        request(endpoint, {
          method: "POST",
          body: payload,
        }),
      );
      setNotice({ tone: "success", text: isReviewer ? "方案已写入方案库。" : "方案已提交审核。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleUnknownReview(status: string) {
    if (!selectedUnknownSignature) {
      setNotice({ tone: "error", text: "请先选择一个未知日志簇。" });
      return;
    }
    try {
      await withBusy("正在提交未知日志审核", () =>
        request(`/active-learning/unknown-clusters/${selectedUnknownSignature}/review`, {
          method: "POST",
          body: {
            review_status: status,
            reviewer: unknownReviewer || user?.username,
            notes: unknownReviewNotes || undefined,
          },
        }),
      );
      setNotice({ tone: "success", text: `未知日志簇已更新为 ${status}。` });
      await loadUnknown();
    } catch (error) {
      showError(error);
    }
  }

  useEffect(() => {
    const storedBase = typeof window !== "undefined" ? window.localStorage.getItem(API_BASE_STORAGE_KEY) || normalizeApiBaseUrl("") : normalizeApiBaseUrl("");
    const storedToken = typeof window !== "undefined" ? window.localStorage.getItem(TOKEN_STORAGE_KEY) || "" : "";
    const storedTask = typeof window !== "undefined" ? window.localStorage.getItem(TASK_STORAGE_KEY) || "" : "";
    async function bootstrap() {
      setApiBase(storedBase);
      setSelectedTaskUuid(storedTask);
      await refreshHealth(storedBase);
      if (!storedToken) {
        setLoading(false);
        return;
      }
      try {
        const currentUser = await platformRequest<AnyRecord>(storedBase, "/auth/me", { token: storedToken });
        applySession(storedToken, currentUser);
        setPage("dashboard");
      } catch {
        applySession("", null);
      } finally {
        setLoading(false);
      }
    }
    void bootstrap();
  }, []);

  useEffect(() => {
    if (typeof window !== "undefined") {
      window.localStorage.setItem(API_BASE_STORAGE_KEY, apiBase);
    }
    void refreshHealth(apiBase);
  }, [apiBase]);

  useEffect(() => {
    if (typeof window !== "undefined" && selectedTaskUuid) {
      window.localStorage.setItem(TASK_STORAGE_KEY, selectedTaskUuid);
    }
  }, [selectedTaskUuid]);

  useEffect(() => {
    if (token && user) {
      void refreshShell(token);
    }
  }, [apiBase, token, user]);

  useEffect(() => {
    if (!isAuthenticated) {
      return;
    }
    const runners: Partial<Record<PageKey, () => Promise<void>>> = {
      dashboard: loadDashboard,
      upload: loadDashboard,
      events: loadEvents,
      performance: loadPerformance,
      timeline: loadTimeline,
      errors: loadErrors,
      parameters: loadParameters,
      llm: async () => {
        await loadErrors();
        await loadLlm();
      },
      solutionHub: loadSolutionHub,
      files: loadFiles,
      unknown: loadUnknown,
      rules: async () => loadRules(false),
      config: loadConfig,
      users: loadUsers,
    };
    const runner = runners[page];
    if (runner) {
      void runner().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid]);

  const selectedTask = tasks.find((task) => String(task.task_uuid) === selectedTaskUuid) || null;
  const errorItems = safeArray(errorsResponse.items);
  const topErrorDistribution = useMemo(
    () =>
      errorItems.slice(0, 8).map((row) => ({
        label: shortText(row.display_signature || row.normalized_signature, 80),
        value: Number(row.count || 0),
        note: String(row.error_family_display || row.error_family || ""),
      })),
    [errorItems],
  );
  const componentDistribution = useMemo(
    () =>
      safeArray(dashboardBundle.dashboard?.component_distribution)
        .map((row) => ({ label: String(row.component || "unknown"), value: Number(row.count || 0) }))
        .sort((a, b) => b.value - a.value)
        .slice(0, 8),
    [dashboardBundle],
  );
  const selectedUnknownCluster =
    safeArray(unknownBundle.items).find((item) => String(item.signature) === selectedUnknownSignature) || null;
  const ruleFiles = safeArray(rulesBundle.files?.items);
  const localPreview = safeObject(rulesBundle.localPreview);
  const llmPreview = safeObject(rulesBundle.llmPreview);
  const localNewSuggestions = safeArray(localPreview.new_rule_suggestions);
  const llmMeta = safeObject((llmPreview || localPreview).llm_assisted);
  const llmNewSuggestions = safeArray(safeObject(llmMeta.result).new_rule_suggestions);

  function toggleParameter(name: string) {
    setSelectedParameters((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));
  }

  function toggleTaskCluster(name: string) {
    setHubSelectedClusters((current) => (current.includes(name) ? current.filter((item) => item !== name) : [...current, name]));
  }

  function toggleRuleSignature(signature: string) {
    setSelectedRuleSignatures((current) => (current.includes(signature) ? current.filter((item) => item !== signature) : [...current, signature]));
  }

  const publicNav = [
    { key: "welcome" as const, label: "欢迎页", icon: Shield },
    { key: "login" as const, label: "登录", icon: LogIn },
    { key: "register" as const, label: "注册", icon: Users },
  ];
  const protectedNav = [
    { key: "dashboard" as const, label: "首页 / 仪表盘", icon: Home },
    { key: "history" as const, label: "历史项目中心", icon: Archive },
    { key: "upload" as const, label: "文件上传", icon: Upload },
    { key: "events" as const, label: "统一事件流", icon: Workflow },
    { key: "performance" as const, label: "耗时分析", icon: Clock3 },
    { key: "timeline" as const, label: "事件流时间轴", icon: Gauge },
    { key: "errors" as const, label: "错误分析", icon: AlertTriangle },
    { key: "parameters" as const, label: "参数趋势分析", icon: Database },
    { key: "llm" as const, label: "LLM 诊断", icon: Brain },
    { key: "solutionHub" as const, label: "方案库中心", icon: BookCopy },
    { key: "files" as const, label: "原始文件预览", icon: FileSearch },
    { key: "unknown" as const, label: "未知日志待标注池", icon: Search },
    { key: "rules" as const, label: "规则建议审核", icon: GitPullRequestArrow },
    { key: "config" as const, label: "配置页面", icon: Settings2 },
    { key: "exports" as const, label: "导出", icon: Download },
    ...(isAdmin ? [{ key: "users" as const, label: "用户管理", icon: Users }] : []),
  ];

  if (loading) {
    return (
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="flex items-center gap-3 rounded-full border border-[var(--border)] bg-[var(--card)] px-5 py-3 text-sm text-[var(--muted-foreground)]">
          <LoaderCircle className="h-4 w-4 animate-spin" />
          正在加载平台状态...
        </div>
      </div>
    );
  }

  const mainContent =
    !isAuthenticated && page === "welcome" ? (
      <div className="space-y-6">
        <SectionTitle title="前后端分离版日志平台" description="按 Streamlit 使用逻辑重建上传、分析、诊断、主动学习和方案管理流程。" />
        <div className="grid gap-6 lg:grid-cols-3">
          <MetricCard label="接口健康" value={String(health?.status || "unknown")} helper="实时探测后端 /health 状态。" />
          <MetricCard label="当前 API" value={apiBase.replace(/^https?:\/\//, "")} helper="可在左侧直接切换后端地址。" />
          <MetricCard label="前端模式" value="Strict API" helper="前端不再直接调用 Python 服务对象。" />
        </div>
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => startTransition(() => setPage("login"))}><LogIn className="h-4 w-4" />前往登录</Button>
          <Button variant="secondary" onClick={() => startTransition(() => setPage("register"))}>申请注册</Button>
        </div>
      </div>
    ) : !isAuthenticated && page === "login" ? (
      <div className="mx-auto max-w-xl space-y-6">
        <SectionTitle title="登录" description="登录后即可访问日志任务、方案库、LLM 诊断和主动学习工作台。" />
        <Card><CardContent className="pt-6"><form className="space-y-5" onSubmit={(event) => void handleLogin(event)}><Field label="用户名或邮箱"><Input value={loginName} onChange={(event) => setLoginName(event.target.value)} /></Field><Field label="密码"><Input type="password" value={loginPassword} onChange={(event) => setLoginPassword(event.target.value)} /></Field><div className="flex flex-wrap gap-3"><Button type="submit">登录</Button><Button type="button" variant="secondary" onClick={() => setPage("register")}>去注册</Button></div></form></CardContent></Card>
      </div>
    ) : !isAuthenticated ? (
      <div className="mx-auto max-w-2xl space-y-6">
        <SectionTitle title="注册申请" description="流程与 Streamlit 保持一致：发送验证码、邮箱验证、提交审核。" />
        <Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-2"><Field label="用户名"><Input value={registerUsername} onChange={(event) => setRegisterUsername(event.target.value)} /></Field><Field label="邮箱"><Input value={registerEmail} onChange={(event) => setRegisterEmail(event.target.value)} /></Field><Field label="密码"><Input type="password" value={registerPassword} onChange={(event) => setRegisterPassword(event.target.value)} /></Field><Field label="确认密码"><Input type="password" value={registerPasswordConfirm} onChange={(event) => setRegisterPasswordConfirm(event.target.value)} /></Field><div className="lg:col-span-2"><Field label="申请说明"><Textarea value={registerNote} onChange={(event) => setRegisterNote(event.target.value)} /></Field></div><div className="lg:col-span-2"><Field label={`验证码 / 当前状态: ${registerStep}`}><Input value={registerCode} onChange={(event) => setRegisterCode(event.target.value)} /></Field></div><div className="lg:col-span-2 flex flex-wrap gap-3"><Button onClick={() => void handleRequestCode()}>发送验证码</Button><Button variant="secondary" onClick={() => void handleVerifyCode()}>验证邮箱</Button><Button variant="secondary" onClick={() => void handleSubmitRegistration()}>提交注册</Button></div></CardContent></Card>
      </div>
    ) : page === "dashboard" ? (
      <div className="space-y-8"><SectionTitle title="首页 / 仪表盘" description="优先回答当前任务是否异常、问题集中在哪里、是否值得继续深挖。" actions={<Button variant="secondary" onClick={() => void loadDashboard()}><RefreshCcw className="h-4 w-4" />刷新仪表盘</Button>} /><div className="grid gap-4 lg:grid-cols-4"><MetricCard label="文件数" value={dashboardBundle.dashboard?.file_count || 0} helper="纳入本次分析的原始文件数量。" /><MetricCard label="总事件数" value={dashboardBundle.dashboard?.total_events || 0} helper="统一归档后的事件总量。" /><MetricCard label="总错误数" value={dashboardBundle.dashboard?.total_errors || 0} helper="任务中识别到的错误总数。" /><MetricCard label="唯一错误簇" value={dashboardBundle.dashboard?.unique_error_count || 0} helper="按签名去重后的错误簇数量。" /></div><DistributionList title="高频错误簇" items={topErrorDistribution} /><DistributionList title="组件错误分布" items={componentDistribution} /><JsonPreview title="任务状态快照" value={dashboardBundle} /></div>
    ) : page === "history" ? (
      <div className="space-y-8"><SectionTitle title="历史项目中心" description="浏览已有任务记录，快速切换任务并回看结果。" actions={<Button variant="secondary" onClick={() => void refreshShell()}><RefreshCcw className="h-4 w-4" />刷新任务列表</Button>} /><DataTable title={`任务列表 (${tasks.length})`} rows={tasks} /></div>
    ) : page === "upload" ? (
      <div className="space-y-8"><SectionTitle title="文件上传" description="支持多文件上传，提交后进入后端任务队列。" actions={<Button onClick={() => void handleUploadLogs()}><Upload className="h-4 w-4" />开始上传并分析</Button>} /><Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-2"><Field label="选择日志文件"><Input type="file" multiple onChange={(event) => setUploadFiles(Array.from(event.target.files || []))} /></Field><Field label="CPU 核心数"><Input type="number" min="1" value={uploadCpuCores} onChange={(event) => setUploadCpuCores(event.target.value)} /></Field></CardContent></Card><JsonPreview title="当前任务进度" value={dashboardBundle.status || {}} /></div>
    ) : page === "events" ? (
      <div className="space-y-8"><SectionTitle title="统一事件流" description="按组件、级别、Cycle 和关键词检索统一归档后的事件流。" actions={<Button variant="secondary" onClick={() => void loadEvents()}><RefreshCcw className="h-4 w-4" />刷新事件流</Button>} /><Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-5"><Field label="组件"><Input value={eventsFilter.component} onChange={(event) => setEventsFilter((current) => ({ ...current, component: event.target.value }))} /></Field><Field label="级别"><Select value={eventsFilter.level} onChange={(event) => setEventsFilter((current) => ({ ...current, level: event.target.value }))}><option value="">全部</option><option value="INFO">INFO</option><option value="WARN">WARN</option><option value="ERROR">ERROR</option><option value="FATAL">FATAL</option></Select></Field><Field label="Cycle"><Input value={eventsFilter.cycleNo} onChange={(event) => setEventsFilter((current) => ({ ...current, cycleNo: event.target.value }))} /></Field><Field label="芯片名"><Input value={eventsFilter.chipName} onChange={(event) => setEventsFilter((current) => ({ ...current, chipName: event.target.value }))} /></Field><Field label="关键词"><Input value={eventsFilter.search} onChange={(event) => setEventsFilter((current) => ({ ...current, search: event.target.value }))} /></Field></CardContent></Card><DataTable title="事件流" rows={safeArray(eventsResponse.items)} /></div>
    ) : page === "performance" ? (
      <div className="space-y-8"><SectionTitle title="耗时分析" description="查看 Cycle 总耗时、Sub-step 表现和操作指标摘要。" actions={<Button variant="secondary" onClick={() => void loadPerformance()}><RefreshCcw className="h-4 w-4" />刷新耗时分析</Button>} /><Card><CardContent className="pt-6"><Field label="单位"><Select value={performanceUnit} onChange={(event) => setPerformanceUnit(event.target.value)}>{durationUnits.map((unit) => <option key={unit.value} value={unit.value}>{unit.label}</option>)}</Select></Field></CardContent></Card><DataTable title="Cycle Summary" rows={safeArray(performanceBundle.cycleSummary)} /><DataTable title="Sub-step Steps" rows={safeArray(performanceBundle.steps?.items)} /><JsonPreview title="Operational Metrics" value={performanceBundle.operationalMetrics} /></div>
    ) : page === "timeline" ? (
      <div className="space-y-8"><SectionTitle title="事件流时间轴" description="从时间维度观察各组件动作顺序和错误点。" actions={<Button variant="secondary" onClick={() => void loadTimeline()}><RefreshCcw className="h-4 w-4" />刷新时间轴</Button>} /><Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-2"><Field label="Cycle"><Select value={timelineCycleNo} onChange={(event) => setTimelineCycleNo(event.target.value)}><option value="">全程</option>{safeArray(timelineBundle.cycles).map((value) => <option key={String(value)} value={String(value)}>{String(value)}</option>)}</Select></Field><Field label="纵轴顺序"><Select value={timelineTrackOrder} onChange={(event) => setTimelineTrackOrder(event.target.value)}><option value="default">默认顺序</option><option value="cycle">按 cycle 排序</option></Select></Field></CardContent></Card><DataTable title="Movement Timeline" rows={safeArray(timelineBundle.rows)} /><DataTable title="Timeline Error Points" rows={safeArray(timelineBundle.errors)} /></div>
    ) : page === "errors" ? (
      <div className="space-y-8"><SectionTitle title="错误分析" description="聚焦错误簇和错误家族分布。" actions={<Button variant="secondary" onClick={() => void loadErrors()}><RefreshCcw className="h-4 w-4" />刷新错误分析</Button>} /><DistributionList title="Top 错误簇" items={topErrorDistribution} /><DataTable title="错误簇" rows={errorItems} /></div>
    ) : page === "parameters" ? (
      <div className="space-y-8"><SectionTitle title="参数趋势分析" description="按参数和单位查看趋势、子步骤聚合和 Row Scan 指标。" actions={<Button variant="secondary" onClick={() => void loadParameters()}><RefreshCcw className="h-4 w-4" />刷新参数趋势</Button>} /><Card><CardContent className="space-y-4 pt-6"><Field label="参数列表"><ChipToggleGroup options={safeArray(parameterBundle.definitions).map((item) => String(item.parameter_name))} selected={selectedParameters} onToggle={toggleParameter} /></Field><Field label="趋势单位"><Select value={parameterUnit} onChange={(event) => setParameterUnit(event.target.value)}>{durationUnits.map((unit) => <option key={unit.value} value={unit.value}>{unit.label}</option>)}</Select></Field></CardContent></Card>{selectedParameters.map((name) => <DataTable key={name} title={`参数趋势: ${name}`} rows={safeArray(safeObject(parameterBundle.parameterSeries)[name])} />)}<DataTable title="Sub-step Cycle Series" rows={safeArray(parameterBundle.substepSeries)} /><DataTable title="Row Scan Metric Series" rows={safeArray(parameterBundle.rowScanMetrics)} /></div>
    ) : page === "llm" ? (
      <div className="space-y-8"><SectionTitle title="LLM 诊断" description="结合日志、上下文、源代码片段和历史案例执行综合诊断。" actions={<Button variant="secondary" onClick={() => void loadLlm()}><RefreshCcw className="h-4 w-4" />刷新诊断数据</Button>} /><TabBar tabs={[{ key: "history", label: "历史诊断" }, { key: "diagnose", label: "综合诊断" }]} active={llmTab} onChange={setLlmTab} />{llmTab === "history" ? <DataTable title="历史诊断列表" rows={safeArray(llmBundle.history)} /> : <><Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-2"><Field label="错误签名"><Select value={selectedErrorSignature} onChange={(event) => setSelectedErrorSignature(event.target.value)}><option value="">请选择错误</option>{safeArray(llmBundle.errors).map((row) => <option key={String(row.normalized_signature)} value={String(row.normalized_signature)}>{shortText(row.display_signature || row.normalized_signature, 70)}</option>)}</Select></Field><Field label="分析深度"><Select value={llmForm.analysisDepth} onChange={(event) => setLlmForm((current) => ({ ...current, analysisDepth: event.target.value }))}><option value="low">low</option><option value="medium">medium</option><option value="high">high</option></Select></Field><Field label="模块"><Input value={llmForm.module} onChange={(event) => setLlmForm((current) => ({ ...current, module: event.target.value }))} /></Field><Field label="子模块"><Input value={llmForm.submodule} onChange={(event) => setLlmForm((current) => ({ ...current, submodule: event.target.value }))} /></Field><div className="lg:col-span-2"><Field label="触发场景"><Textarea value={llmForm.triggerScenario} onChange={(event) => setLlmForm((current) => ({ ...current, triggerScenario: event.target.value }))} /></Field></div><div className="lg:col-span-2"><Field label="上传相关源文件"><Input type="file" multiple onChange={(event) => setLlmSourceFiles(Array.from(event.target.files || []))} /></Field></div></CardContent></Card><div className="flex flex-wrap gap-3"><Button onClick={() => void handleRunDiagnosis()}><Send className="h-4 w-4" />开始综合诊断</Button></div>{llmBundle.latestDiagnosis ? <JsonPreview title="最新诊断结果" value={llmBundle.latestDiagnosis} /> : null}</>}<JsonPreview title="LLM 配置快照" value={llmBundle.config} /></div>
    ) : page === "solutionHub" ? (
      <div className="space-y-8"><SectionTitle title="方案库中心" description="围绕全局可复用方案、任务簇、模块前缀和审核流的统一入口。" actions={<Button variant="secondary" onClick={() => void loadSolutionHub()}><RefreshCcw className="h-4 w-4" />刷新方案中心</Button>} /><TabBar tabs={[{ key: "submit", label: "方案提交" }, { key: "query", label: "方案检索" }, { key: "review", label: "方案审核" }, { key: "taxonomy", label: "任务簇与模块" }]} active={solutionTab} onChange={setSolutionTab} />{solutionTab === "submit" ? <><Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-2"><Field label="模块"><Select value={hubForm.module} onChange={(event) => setHubForm((current) => ({ ...current, module: event.target.value }))}><option value="">请选择模块</option>{modules.map((module) => <option key={String(module.id)} value={String(module.module_key)}>{module.display_name} / {module.prefix}</option>)}</Select></Field><Field label="错误名称"><Input value={hubForm.error_name} onChange={(event) => setHubForm((current) => ({ ...current, error_name: event.target.value }))} /></Field><div className="lg:col-span-2"><Field label="任务簇"><ChipToggleGroup options={taskClusters.map((item) => String(item.display_name || item.cluster_key))} selected={hubSelectedClusters} onToggle={toggleTaskCluster} /></Field></div><div className="lg:col-span-2"><Field label="message / 现象描述"><Textarea value={hubForm.message} onChange={(event) => setHubForm((current) => ({ ...current, message: event.target.value }))} /></Field></div><div className="lg:col-span-2"><Field label="根因分析"><Textarea value={hubForm.root_cause_analysis} onChange={(event) => setHubForm((current) => ({ ...current, root_cause_analysis: event.target.value }))} /></Field></div><div className="lg:col-span-2"><Field label="已验证解决方案"><Textarea value={hubForm.verified_solution} onChange={(event) => setHubForm((current) => ({ ...current, verified_solution: event.target.value }))} /></Field></div></CardContent></Card><Button onClick={() => void handleSubmitSolutionHub()}><Send className="h-4 w-4" />提交方案</Button></> : solutionTab === "query" ? <DataTable title="方案记录" rows={safeArray(hubBundle.records?.items)} /> : solutionTab === "review" ? <DataTable title="审核中心" rows={safeArray(hubBundle.reviews?.items)} /> : <><DataTable title="任务簇" rows={safeArray(hubBundle.taskClusters)} /><DataTable title="模块配置" rows={safeArray(hubBundle.modules)} /></>}</div>
    ) : page === "files" ? (
      <div className="space-y-8"><SectionTitle title="原始文件预览" description="查看任务中收录的原始文件和预览片段。" actions={<Button variant="secondary" onClick={() => void loadFiles()}><RefreshCcw className="h-4 w-4" />刷新文件列表</Button>} /><DataTable title="原始文件列表" rows={safeArray(filesBundle.list?.items)} /><JsonPreview title="文件预览" value={filesBundle.preview || {}} /></div>
    ) : page === "unknown" ? (
      <div className="space-y-8"><SectionTitle title="未知日志待标注池" description="收集尚未命中 parser 或规则的日志簇，支持审核。" actions={<Button variant="secondary" onClick={() => void loadUnknown()}><RefreshCcw className="h-4 w-4" />刷新未知日志池</Button>} /><DataTable title="未知日志簇" rows={safeArray(unknownBundle.items)} />{selectedUnknownCluster ? <><Card><CardContent className="grid gap-4 pt-6 lg:grid-cols-2"><Field label="审核人"><Input value={unknownReviewer} onChange={(event) => setUnknownReviewer(event.target.value)} /></Field><Field label="审核备注"><Textarea value={unknownReviewNotes} onChange={(event) => setUnknownReviewNotes(event.target.value)} /></Field></CardContent></Card><div className="flex flex-wrap gap-3"><Button onClick={() => void handleUnknownReview("approved")}>通过</Button><Button variant="secondary" onClick={() => void handleUnknownReview("ignored")}>忽略</Button><Button variant="danger" onClick={() => void handleUnknownReview("rejected")}>拒绝</Button></div><JsonPreview title="未知日志详情" value={selectedUnknownCluster} /></> : null}</div>
    ) : page === "rules" ? (
      <div className="space-y-8"><SectionTitle title="规则建议审核视图" description="先看本地规则建议，再按需触发 LLM 规则建议。" actions={<div className="flex flex-wrap gap-3"><Button variant="secondary" onClick={() => void loadRules(false)}><RefreshCcw className="h-4 w-4" />刷新本地建议</Button><Button onClick={() => void loadRules(true)}><WandSparkles className="h-4 w-4" />生成 / 刷新 LLM 建议</Button></div>} /><Card><CardContent className="space-y-4 pt-6"><label className="flex items-center gap-3 text-sm"><input type="checkbox" checked={ruleLlmEnabled} onChange={(event) => setRuleLlmEnabled(event.target.checked)} />启用 LLM 规则建议</label><Field label="送入 LLM 的未知日志簇"><ChipToggleGroup options={safeArray(rulesBundle.unknownPool?.items).map((item) => String(item.signature))} selected={selectedRuleSignatures} onToggle={toggleRuleSignature} /></Field></CardContent></Card><DataTable title="本地新规则建议" rows={localNewSuggestions} />{ruleLlmEnabled ? <DataTable title="LLM 新规则建议" rows={llmNewSuggestions} /> : null}<DataTable title="建议文件" rows={ruleFiles} />{ruleFiles.length ? <Card><CardContent className="space-y-4 pt-6"><Field label="选择建议文件"><Select value={selectedRuleFile} onChange={(event) => { const filename = event.target.value; setSelectedRuleFile(filename); void loadRuleFile(filename); }}><option value="">请选择文件</option>{ruleFiles.map((file) => <option key={String(file.filename)} value={String(file.filename)}>{file.filename}</option>)}</Select></Field><JsonPreview value={ruleFileContent || {}} /></CardContent></Card> : null}</div>
    ) : page === "config" ? (
      <div className="space-y-8"><SectionTitle title="配置页面" description="查看配置快照，并以 JSON 编辑器方式维护 thresholds。" actions={<Button variant="secondary" onClick={() => void loadConfig()}><RefreshCcw className="h-4 w-4" />刷新配置</Button>} /><Card><CardHeader><CardTitle className="text-base">阈值编辑</CardTitle><CardDescription>这里直接调用 `/config/thresholds`，不在前端复制 YAML 写入逻辑。</CardDescription></CardHeader><CardContent className="space-y-4"><Field label="default_threshold_ms"><Input type="number" value={thresholdEditor.default_threshold_ms} onChange={(event) => setThresholdEditor((current) => ({ ...current, default_threshold_ms: event.target.value }))} /></Field><Field label="step_thresholds_ms"><Textarea rows={6} value={thresholdEditor.step_thresholds_ms} onChange={(event) => setThresholdEditor((current) => ({ ...current, step_thresholds_ms: event.target.value }))} /></Field><Field label="parameter_thresholds_seconds"><Textarea rows={6} value={thresholdEditor.parameter_thresholds_seconds} onChange={(event) => setThresholdEditor((current) => ({ ...current, parameter_thresholds_seconds: event.target.value }))} /></Field><Field label="parameter_expected_seconds"><Textarea rows={6} value={thresholdEditor.parameter_expected_seconds} onChange={(event) => setThresholdEditor((current) => ({ ...current, parameter_expected_seconds: event.target.value }))} /></Field><Field label="llm_context"><Textarea rows={6} value={thresholdEditor.llm_context} onChange={(event) => setThresholdEditor((current) => ({ ...current, llm_context: event.target.value }))} /></Field><Button onClick={() => void handleSaveThresholds()}>保存阈值配置</Button></CardContent></Card><JsonPreview title="配置快照" value={configBundle} /></div>
    ) : page === "exports" ? (
      <div className="space-y-8"><SectionTitle title="导出" description="统一使用后端 FileResponse 接口导出任务产物和方案库数据。" />{selectedTaskUuid ? <Card><CardContent className="flex flex-wrap gap-3 pt-6"><Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/events`, { access_token: token })} target="_blank" rel="noreferrer">导出事件 CSV</a></Button><Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/errors`, { access_token: token })} target="_blank" rel="noreferrer">导出错误 CSV</a></Button><Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/report.json`, { access_token: token })} target="_blank" rel="noreferrer">导出 JSON 报告</a></Button></CardContent></Card> : <Card><CardContent className="pt-6"><p className="text-sm text-[var(--muted-foreground)]">请先选择任务 UUID。</p></CardContent></Card>}</div>
    ) : (
      <div className="space-y-8"><SectionTitle title="用户管理" description="仅管理员可见，用于处理注册审核、账号启停和角色配置。" actions={<Button variant="secondary" onClick={() => void loadUsers()}><RefreshCcw className="h-4 w-4" />刷新用户列表</Button>} /><DataTable title="用户列表" rows={userList} /></div>
    );

  return (
    <div className="grid gap-6 xl:grid-cols-[320px_minmax(0,1fr)]">
      <aside className="space-y-6">
        <Card className="sticky top-6 overflow-hidden">
          <CardHeader className="gap-4">
            <div className="flex items-start justify-between gap-3">
              <div className="space-y-1">
                <p className="text-xs uppercase tracking-[0.22em] text-[var(--muted-foreground)]">Streamlit Mirror</p>
                <CardTitle className="text-xl">Sequencer Log Platform</CardTitle>
              </div>
              <Button variant="ghost" size="sm" onClick={() => setTheme(darkMode ? "light" : "dark")}>
                {darkMode ? <SunMedium className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
              </Button>
            </div>
            <CardDescription>前端只做页面与状态管理，业务逻辑全部走 FastAPI。</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            <Field label="FastAPI 地址">
              <Input value={apiBase} onChange={(event) => setApiBase(normalizeApiBaseUrl(event.target.value))} />
            </Field>
            <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/55 p-4 text-sm">
              <p className="font-medium text-[var(--foreground)]">API Health</p>
              <p className="mt-2 text-[var(--muted-foreground)]">{String(health?.status || "unknown")}</p>
            </div>
            {isAuthenticated ? (
              <>
                <Separator />
                <Field label="历史任务">
                  <Select value={selectedTaskUuid} onChange={(event) => startTransition(() => setSelectedTaskUuid(event.target.value))}>
                    <option value="">(不选择历史任务)</option>
                    {tasks.map((task) => (
                      <option key={String(task.task_uuid)} value={String(task.task_uuid)}>
                        {formatDate(task.created_at)} | {String(task.task_uuid).slice(0, 8)} | {task.status}
                      </option>
                    ))}
                  </Select>
                </Field>
              </>
            ) : null}
            <Separator />
            <div className="grid gap-2">
              {(isAuthenticated ? protectedNav : publicNav).map((item) => {
                const Icon = item.icon;
                const active = page === item.key;
                return (
                  <button key={item.key} type="button" onClick={() => startTransition(() => setPage(item.key))} className={cn("flex items-center gap-3 rounded-2xl px-4 py-3 text-left text-sm transition", active ? "bg-[var(--accent)] text-[var(--accent-foreground)]" : "bg-[var(--muted)]/55 text-[var(--foreground)] hover:bg-[var(--muted)]")}>
                    <Icon className="h-4 w-4 shrink-0" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
            {user ? (
              <>
                <Separator />
                <div className="space-y-4">
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-[var(--foreground)]">{user.username}</p>
                    <p className="text-xs text-[var(--muted-foreground)]">{user.email}</p>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <StatusBadge status={user.status} />
                    {safeArray(user.roles).map((role) => <Badge key={String(role)}>{String(role)}</Badge>)}
                  </div>
                  <div className="space-y-3 rounded-2xl border border-[var(--border)] p-4">
                    <p className="text-sm font-medium text-[var(--foreground)]">修改密码</p>
                    <Input type="password" placeholder="当前密码" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
                    <Input type="password" placeholder="新密码" value={nextPassword} onChange={(event) => setNextPassword(event.target.value)} />
                    <Input type="password" placeholder="确认新密码" value={nextPasswordConfirm} onChange={(event) => setNextPasswordConfirm(event.target.value)} />
                    <Button className="w-full" variant="secondary" onClick={() => void handleChangePassword()}>
                      <KeyRound className="h-4 w-4" />
                      更新密码
                    </Button>
                  </div>
                  {selectedTask ? <Button className="w-full" variant="danger" onClick={() => void handleDeleteTask(String(selectedTask.task_uuid))}>删除当前任务</Button> : null}
                  <Button className="w-full" variant="ghost" onClick={handleLogout}>
                    <LogOut className="h-4 w-4" />
                    退出登录
                  </Button>
                </div>
              </>
            ) : null}
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
        {mainContent}
      </main>
    </div>
  );
}
