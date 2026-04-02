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
  CodePreview,
  DataTable,
  DetailListCard,
  DistributionList,
  Field,
  InfoTileGrid,
  JsonPreview,
  LinePreviewCard,
  MappingEditorTable,
  MetricCard,
  NoticeBanner,
  PaginationBar,
  SectionTitle,
  SimpleLineChart,
  StatusBadge,
  TabBar,
  TimelineChart,
  UsageGuideCard,
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

type LlmTabKey = "history" | "diagnose" | "solutionEntry" | "repo" | "review";
type SolutionTabKey = "submit" | "query" | "review" | "taxonomy";
type ConfigTabKey = "overview" | "env" | "thresholds" | "rules" | "knowledge";
type EnvItem = {
  key: string;
  value: string;
  display_value: string;
  default_value?: string | null;
  default_display_value?: string | null;
  is_sensitive: boolean;
  has_default: boolean;
  is_modified: boolean;
};

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
  impact_scope: "",
  owner_department: "",
  root_cause_analysis: "",
  verified_solution: "",
  workaround: "",
  submitter: "",
  reusable: true,
};

const pageUsageGuides: Record<PageKey, { title: string; description: string; steps: string[] }> = {
  welcome: {
    title: "欢迎页使用逻辑",
    description: "先确认服务健康和入口，再进入登录或注册流程。",
    steps: [
      "先看页面顶部的接口健康状态，确认后端服务可以正常响应。",
      "确认服务健康后，进入登录或注册流程。",
      "登录成功后，再依次进入上传、分析、诊断和方案管理页面。",
    ],
  },
  login: {
    title: "登录页使用逻辑",
    description: "输入账号信息后直接进入平台，不需要额外跳转。",
    steps: [
      "输入用户名或邮箱与密码，点击登录。",
      "如还没有账号，可切换到注册页完成验证码和审核流程。",
      "登录后优先在左侧选择任务或新建上传任务，再进入各分析子页面。",
    ],
  },
  register: {
    title: "注册页使用逻辑",
    description: "注册流程保持三段式：申请验证码、邮箱验证、提交审核。",
    steps: [
      "先填写用户名、邮箱、密码和注册说明，然后发送验证码。",
      "收到邮箱验证码后完成验证，拿到注册提交资格。",
      "提交申请后等待管理员审核，审核通过即可登录平台。",
    ],
  },
  dashboard: {
    title: "首页使用逻辑",
    description: "首页用于快速判断任务是否异常，以及下一步该去哪一页深入分析。",
    steps: [
      "先在左侧选择一个任务 UUID，观察当前状态、进度和错误密度。",
      "结合高频错误簇与组件分布判断问题集中区域。",
      "若要继续深挖，进入错误分析、时间轴或 LLM 诊断页面。",
    ],
  },
  history: {
    title: "历史项目中心使用逻辑",
    description: "历史页负责选择任务、切换上下文以及执行删除管理。",
    steps: [
      "按分页浏览历史任务记录，先找到目标任务。",
      "点击任务行后先决定是设为当前任务，还是在这里直接删除历史任务。",
      "切换完成后再去首页、错误分析或参数页查看详情。",
    ],
  },
  upload: {
    title: "文件上传页使用逻辑",
    description: "上传页负责创建新任务，并把文件送入后端队列。",
    steps: [
      "选择一个或多个日志文件，必要时调整 CPU 核心数。",
      "点击开始上传并分析，等待任务进入队列。",
      "创建成功后关注任务进度，再去首页或历史页继续查看结果。",
    ],
  },
  events: {
    title: "统一事件流使用逻辑",
    description: "事件流页适合按条件检索和回放统一归档后的日志事件。",
    steps: [
      "先选定任务，再按组件、级别、Cycle 或关键词做过滤。",
      "分页查看匹配到的统一事件流记录。",
      "如果定位到异常事件，再回到错误、时间轴或原始文件页交叉验证。",
    ],
  },
  performance: {
    title: "耗时分析页使用逻辑",
    description: "耗时页负责发现慢步骤、波动周期和拍照等关键性能指标。",
    steps: [
      "先选耗时单位，再观察 Cycle 总耗时趋势图。",
      "向下查看 Sub-step 耗时表和拍照时间摘要。",
      "发现异常耗时后，可联动时间轴和参数趋势页继续分析。",
    ],
  },
  timeline: {
    title: "时间轴页使用逻辑",
    description: "时间轴页负责把组件动作、错误点和时间顺序放到同一视图中。",
    steps: [
      "选择全程或某个 Cycle，并设置纵轴排序方式。",
      "按需开启错误点标记，并筛选错误家族与严重级别。",
      "如需核对细节，可开启表格明细继续查看每一条时间轴记录。",
    ],
  },
  errors: {
    title: "错误分析页使用逻辑",
    description: "错误页用于确定最值得优先处理的错误簇和错误家族。",
    steps: [
      "先查看错误簇表并结合分页锁定高频问题。",
      "切换到 Top N 或错误家族分布，确认主要异常类型。",
      "若需要给出原因和处理建议，再进入 LLM 诊断或方案库中心。",
    ],
  },
  parameters: {
    title: "参数趋势页使用逻辑",
    description: "参数页用于看阈值、期望值与真实数据趋势的偏差。",
    steps: [
      "先选择要关注的参数和趋势单位。",
      "对照参数曲线中的阈值线与期望值线判断是否越界。",
      "再结合 Sub-step 和 Row Scan 指标，判断异常发生在哪个阶段。",
    ],
  },
  llm: {
    title: "LLM 诊断页使用逻辑",
    description: "LLM 页负责围绕错误簇完成综合诊断、方案录入和审核。",
    steps: [
      "先看历史诊断确认是否已有结果可复用。",
      "如需重新分析，在综合诊断标签下选择错误簇、深度和上下文后发起诊断。",
      "诊断完成后把有效结果提交到审核流或方案库，形成可复用知识。",
    ],
  },
  solutionHub: {
    title: "方案库中心使用逻辑",
    description: "方案库中心负责统一提交、检索、审核、导入导出和智能问答。",
    steps: [
      "在方案提交标签录入根因、解决方案、任务簇和模块信息，错误码由系统自动分配。",
      "在方案检索标签按全文、模块或审核状态筛选现有记录，并可直接向方案库提问。",
      "在审核和任务簇标签维护审核流、任务簇与模块配置。",
    ],
  },
  files: {
    title: "原始文件预览页使用逻辑",
    description: "原始文件页用于回到源日志本身，确认解析结果是否可信。",
    steps: [
      "先从文件列表中选择目标原始文件。",
      "设置预览行数后加载文本内容，快速定位上下文。",
      "若发现解析偏差，可继续去未知日志池或规则审核页处理。",
    ],
  },
  unknown: {
    title: "未知日志池使用逻辑",
    description: "未知日志池用于处理尚未命中 parser 或规则的日志簇。",
    steps: [
      "先按出现次数和审核状态筛选待处理日志簇。",
      "查看代表样本、上下文样本和已尝试过的解析器/规则。",
      "确认后执行通过、忽略或拒绝，为后续规则学习提供依据。",
    ],
  },
  rules: {
    title: "规则审核页使用逻辑",
    description: "规则页把本地建议、LLM 建议、文件产物和审核动作集中到一起。",
    steps: [
      "先查看本地规则建议，再按需启用 LLM 建议。",
      "从建议详情、误判模式和候选文件判断是否值得入库。",
      "填写审核人和备注后执行通过、退回修改或拒绝。",
    ],
  },
  config: {
    title: "配置页使用逻辑",
    description: "配置页负责环境变量、阈值、规则策略和 Prompt 知识的集中维护。",
    steps: [
      "先在环境变量标签维护 `.env` 中的真实运行配置。",
      "再到阈值、规则和知识标签维护分析参数与知识配置。",
      "修改后刷新页面或切换业务页验证新配置是否生效。",
    ],
  },
  exports: {
    title: "导出页使用逻辑",
    description: "导出页用于把当前任务结果导出为标准文件格式。",
    steps: [
      "先确认左侧已选中目标任务 UUID。",
      "根据用途选择事件、错误、参数或完整报告导出格式。",
      "下载后可用于复盘、共享或归档留存。",
    ],
  },
  users: {
    title: "用户管理页使用逻辑",
    description: "用户页只面向管理员，用于账号审核、启停和角色授权。",
    steps: [
      "先在用户列表中选中目标账号。",
      "根据审核结果执行通过、拒绝、停用或启用。",
      "如需授权，再调整 reviewer/admin 角色并保存。",
    ],
  },
};

function splitCommaText(value: string) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function formatPercent(numerator: number, denominator: number, digits = 1) {
  if (!denominator) {
    return "0%";
  }
  return `${((numerator / denominator) * 100).toFixed(digits)}%`;
}

function rowsFromMapping(source: Record<string, unknown>) {
  return Object.entries(source || {}).map(([key, value]) => ({
    key,
    value: String(value ?? ""),
  }));
}

function rowsFromNestedMapping(source: Record<string, Record<string, unknown>>) {
  const rows: Array<{ module: string; step: string; value: string }> = [];
  Object.entries(source || {}).forEach(([moduleName, steps]) => {
    Object.entries(steps || {}).forEach(([stepName, value]) => {
      rows.push({
        module: moduleName,
        step: stepName,
        value: String(value ?? ""),
      });
    });
  });
  return rows;
}

function mappingFromRows(rows: AnyRecord[]) {
  const result: Record<string, number | string> = {};
  rows.forEach((row) => {
    const key = String(row.key || "").trim();
    if (!key) {
      return;
    }
    const rawValue = String(row.value ?? "").trim();
    const numeric = Number(rawValue);
    result[key] = Number.isFinite(numeric) && rawValue !== "" ? numeric : rawValue;
  });
  return result;
}

function nestedMappingFromRows(rows: AnyRecord[]) {
  const result: Record<string, Record<string, number | string>> = {};
  rows.forEach((row) => {
    const moduleName = String(row.module || "").trim();
    const stepName = String(row.step || "").trim();
    if (!moduleName || !stepName) {
      return;
    }
    const rawValue = String(row.value ?? "").trim();
    const numeric = Number(rawValue);
    result[moduleName] ??= {};
    result[moduleName][stepName] =
      Number.isFinite(numeric) && rawValue !== "" ? numeric : rawValue;
  });
  return result;
}

function envGroupFromKey(key: string) {
  if (key.startsWith("APP_") || key === "DEBUG") {
    return "基础运行";
  }
  if (
    key.startsWith("DATABASE_") ||
    key.endsWith("_DIR") ||
    key.startsWith("DATA_") ||
    key.startsWith("UPLOAD_") ||
    key.startsWith("EXPORT_") ||
    key.startsWith("LOG_") ||
    key.startsWith("TEMP_") ||
    key.startsWith("INTERMEDIATE_")
  ) {
    return "数据与目录";
  }
  if (
    key.includes("PARALLEL") ||
    key.includes("THREAD") ||
    key.includes("PROCESS") ||
    key.includes("QUEUE") ||
    key.includes("BATCH") ||
    key.includes("SQLITE_WRITE")
  ) {
    return "并行调度";
  }
  if (
    key.includes("CACHE") ||
    key.includes("PAGE") ||
    key.includes("UI_") ||
    key.includes("LIGHTWEIGHT") ||
    key.includes("PERFORMANCE")
  ) {
    return "前端与性能";
  }
  if (key.startsWith("SYSTEM_")) {
    return "系统资源";
  }
  if (key.startsWith("LLM_")) {
    return "LLM 配置";
  }
  if (key.startsWith("API_") || key.startsWith("CORS_")) {
    return "API 接口";
  }
  if (key.startsWith("AUTH_")) {
    return "鉴权与管理员";
  }
  if (key.startsWith("MAIL_") || key.startsWith("SMTP_")) {
    return "邮件发送";
  }
  if (key.startsWith("MAX_") || key === "CHUNK_SIZE") {
    return "上传与读取";
  }
  return "其他";
}

function formatRuntimeNumber(value: unknown, digits = 1) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  const fixed = numeric.toFixed(digits);
  return fixed.endsWith(".0") ? fixed.slice(0, -2) : fixed;
}

function formatPercentLabel(value: unknown) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  return `${formatRuntimeNumber(numeric)}%`;
}

function formatStorageLabel(value: unknown, unit: "MB" | "GB") {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return "-";
  }
  return `${formatRuntimeNumber(numeric, unit === "GB" ? 2 : 1)} ${unit}`;
}

function UsageStatusCard({
  label,
  percent,
  primary,
  secondary,
  helper,
}: {
  label: string;
  percent: number | null;
  primary: string;
  secondary: string;
  helper: string;
}) {
  const progress = percent === null ? 0 : Math.max(0, Math.min(percent, 100));
  const toneClass =
    percent === null
      ? "bg-slate-300"
      : progress >= 90
        ? "bg-rose-500"
        : progress >= 75
          ? "bg-amber-500"
          : "bg-emerald-500";

  return (
    <Card>
      <CardContent className="space-y-4 pt-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">{label}</p>
            <p className="mt-2 text-2xl font-semibold text-[var(--foreground)]">{primary}</p>
          </div>
          <div className="rounded-full border border-[var(--border)] bg-[var(--muted)]/50 px-3 py-1 text-xs text-[var(--muted-foreground)]">
            {percent === null ? "unknown" : formatPercentLabel(progress)}
          </div>
        </div>
        <div className="h-2 rounded-full bg-[var(--muted)]">
          <div className={cn("h-2 rounded-full transition-all", toneClass)} style={{ width: `${progress}%` }} />
        </div>
        <div className="space-y-1">
          <p className="text-sm text-[var(--foreground)]">{secondary}</p>
          <p className="text-xs leading-5 text-[var(--muted-foreground)]">{helper}</p>
        </div>
      </CardContent>
    </Card>
  );
}

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
  const [passwordEditorOpen, setPasswordEditorOpen] = useState(false);

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
  const [historyDetailTab, setHistoryDetailTab] = useState<
    "structured" | "context" | "source" | "cases" | "full"
  >("structured");
  const [diagnosisResultTab, setDiagnosisResultTab] = useState<
    "structured" | "context" | "source" | "cases" | "payload"
  >("structured");
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
  const [hubImportFile, setHubImportFile] = useState<File | null>(null);
  const [hubImportResult, setHubImportResult] = useState<AnyRecord | null>(null);
  const [hubAssistantQuestion, setHubAssistantQuestion] = useState("");
  const [hubAssistantResult, setHubAssistantResult] = useState<AnyRecord | null>(null);

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
  const [selectedLocalNewSuggestionId, setSelectedLocalNewSuggestionId] = useState("");
  const [selectedLocalFixSuggestionId, setSelectedLocalFixSuggestionId] = useState("");
  const [selectedLlmNewSuggestionId, setSelectedLlmNewSuggestionId] = useState("");
  const [selectedLlmFixSuggestionId, setSelectedLlmFixSuggestionId] = useState("");
  const [ruleFileContent, setRuleFileContent] = useState<AnyRecord | null>(null);
  const [ruleReviewer, setRuleReviewer] = useState("");
  const [ruleReviewNotes, setRuleReviewNotes] = useState("");
  const [rulesTab, setRulesTab] = useState<
    "localNew" | "localFix" | "llmNew" | "llmFix" | "patterns" | "yaml" | "reviews" | "files" | "payload"
  >("localNew");

  const [configBundle, setConfigBundle] = useState<AnyRecord>({});
  const [thresholdEditor, setThresholdEditor] = useState({
    default_threshold_ms: "0",
    step_thresholds_ms: "{}",
    parameter_thresholds_seconds: "{}",
    parameter_expected_seconds: "{}",
    llm_context: "{}",
  });
  const [configTab, setConfigTab] = useState<ConfigTabKey>("overview");
  const [envItems, setEnvItems] = useState<EnvItem[]>([]);
  const [envDrafts, setEnvDrafts] = useState<Record<string, string>>({});
  const [envSearch, setEnvSearch] = useState("");
  const [envGroup, setEnvGroup] = useState("全部");

  const [dashboardBundle, setDashboardBundle] = useState<AnyRecord>({
    dashboard: null,
    status: null,
    performance: null,
  });
  const [systemRuntimeBundle, setSystemRuntimeBundle] = useState<AnyRecord>({});
  const [memoryLimitPercentDraft, setMemoryLimitPercentDraft] = useState("");
  const [memoryReserveDraft, setMemoryReserveDraft] = useState("");

  const [historyPage, setHistoryPage] = useState(1);
  const [historyPageSize, setHistoryPageSize] = useState(50);
  const [historyBundle, setHistoryBundle] = useState<AnyRecord>({ items: [], total: 0, page: 1, page_size: 50 });
  const [selectedHistoryTaskUuid, setSelectedHistoryTaskUuid] = useState("");

  const [eventsPage, setEventsPage] = useState(1);
  const [eventsPageSize, setEventsPageSize] = useState(100);

  const [performanceStepPage, setPerformanceStepPage] = useState(1);
  const [performanceStepPageSize, setPerformanceStepPageSize] = useState(100);

  const [timelineShowErrors, setTimelineShowErrors] = useState(true);
  const [timelineShowDetails, setTimelineShowDetails] = useState(false);
  const [timelineSelectedFamilies, setTimelineSelectedFamilies] = useState<string[]>([]);
  const [timelineSelectedSeverities, setTimelineSelectedSeverities] = useState<string[]>([]);

  const [errorsPage, setErrorsPage] = useState(1);
  const [errorsPageSize, setErrorsPageSize] = useState(100);
  const [errorTab, setErrorTab] = useState<"top" | "family" | "guide">("top");

  const [llmHistorySignatureFilter, setLlmHistorySignatureFilter] = useState("");
  const [diagnoseTimeout, setDiagnoseTimeout] = useState("120");
  const [manualReviewer, setManualReviewer] = useState("");
  const [manualReviewNotes, setManualReviewNotes] = useState("");

  const [editingRecordId, setEditingRecordId] = useState("");
  const [editingRecordDraft, setEditingRecordDraft] = useState({
    root_cause_analysis: "",
    verified_solution: "",
    workaround: "",
    reusable: true,
  });

  const [filesPage, setFilesPage] = useState(1);
  const [filesPageSize, setFilesPageSize] = useState(100);

  const [parameterShowMetricTable, setParameterShowMetricTable] = useState(false);

  const [thresholdRows, setThresholdRows] = useState<Array<{ key: string; value: string }>>([]);
  const [expectedRows, setExpectedRows] = useState<Array<{ key: string; value: string }>>([]);
  const [stepThresholdRows, setStepThresholdRows] = useState<Array<{ module: string; step: string; value: string }>>([]);
  const [contextRows, setContextRows] = useState<Array<{ key: string; value: string }>>([]);

  const [selectedUserId, setSelectedUserId] = useState("");
  const [selectedUserRoles, setSelectedUserRoles] = useState({ is_reviewer: false, is_admin: false });
  const [refreshingKeys, setRefreshingKeys] = useState<string[]>([]);

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

  function isRefreshing(key: string) {
    return refreshingKeys.includes(key);
  }

  async function withRefresh<T>(key: string, action: () => Promise<T>) {
    setRefreshingKeys((current) => (current.includes(key) ? current : [...current, key]));
    try {
      return await action();
    } finally {
      setRefreshingKeys((current) => current.filter((item) => item !== key));
    }
  }

  async function runRefreshAction(key: string, action: () => Promise<unknown>) {
    try {
      await withRefresh(key, action);
    } catch (error) {
      showError(error);
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

  async function loadHistory() {
    const result = await request<AnyRecord>("/tasks", {
      query: { page: historyPage, page_size: historyPageSize },
    });
    setHistoryBundle(result);
    const nextItems = safeArray(result.items);
    const preferredTask =
      nextItems.find((item) => String(item.task_uuid) === selectedHistoryTaskUuid) ||
      nextItems.find((item) => String(item.task_uuid) === selectedTaskUuid) ||
      nextItems[0] ||
      null;
    setSelectedHistoryTaskUuid(String(preferredTask?.task_uuid || ""));
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

  async function loadSystemRuntime() {
    const result = await request<AnyRecord>("/system/runtime");
    setSystemRuntimeBundle(result);
    const policy = safeObject(result.policy);
    setMemoryLimitPercentDraft(String(policy.memory_soft_limit_percent ?? ""));
    setMemoryReserveDraft(String(policy.memory_soft_reserve_mb ?? ""));
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
        limit: eventsPageSize,
        offset: (eventsPage - 1) * eventsPageSize,
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
      request<AnyRecord>(`/tasks/${selectedTaskUuid}/steps`, {
        query: {
          limit: performanceStepPageSize,
          offset: (performanceStepPage - 1) * performanceStepPageSize,
        },
      }),
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
      query: { limit: errorsPageSize, offset: (errorsPage - 1) * errorsPageSize },
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
    const list = await request<AnyRecord>(`/tasks/${selectedTaskUuid}/files`, {
      query: { limit: filesPageSize, offset: (filesPage - 1) * filesPageSize },
    });
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
    const [config, envResponse] = await Promise.all([
      request<AnyRecord>("/config"),
      request<AnyRecord>("/config/env"),
    ]);
    const thresholds = safeObject(config.thresholds);
    const envList = safeArray<EnvItem>(envResponse.items).sort((left, right) =>
      String(left.key).localeCompare(String(right.key)),
    );
    setConfigBundle(config);
    setEnvItems(envList);
    setEnvDrafts(
      Object.fromEntries(envList.map((item) => [item.key, String(item.value ?? "")])),
    );
    setThresholdEditor({
      default_threshold_ms: String(thresholds.default_threshold_ms ?? 0),
      step_thresholds_ms: JSON.stringify(thresholds.step_thresholds_ms ?? {}, null, 2),
      parameter_thresholds_seconds: JSON.stringify(thresholds.parameter_thresholds_seconds ?? {}, null, 2),
      parameter_expected_seconds: JSON.stringify(thresholds.parameter_expected_seconds ?? {}, null, 2),
      llm_context: JSON.stringify(thresholds.llm_context ?? {}, null, 2),
    });
    setThresholdRows(rowsFromMapping(safeObject(thresholds.parameter_thresholds_seconds)));
    setExpectedRows(rowsFromMapping(safeObject(thresholds.parameter_expected_seconds)));
    setStepThresholdRows(rowsFromNestedMapping(safeObject(thresholds.step_thresholds_ms) as Record<string, Record<string, unknown>>));
    setContextRows(rowsFromMapping(safeObject(thresholds.llm_context)));
  }

  async function loadUsers() {
    if (!isAdmin) {
      setUserList([]);
      return;
    }
    const response = await request<AnyRecord>("/admin/users");
    const items = safeArray(response.items);
    setUserList(items);
    const selected = items.find((item) => String(item.id) === selectedUserId) || items[0];
    if (selected) {
      setSelectedUserId(String(selected.id));
      setSelectedUserRoles({
        is_reviewer: Boolean(selected.is_reviewer),
        is_admin: Boolean(selected.is_admin),
      });
    }
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
    if (nextPassword.length < 8) {
      setNotice({ tone: "error", text: "新密码至少需要 8 个字符。" });
      return;
    }
    if (currentPassword === nextPassword) {
      setNotice({ tone: "error", text: "新密码不能与当前密码相同。" });
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
      setPasswordEditorOpen(false);
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
      if (String(selectedHistoryTaskUuid) === taskUuid) {
        setSelectedHistoryTaskUuid("");
      }
      setNotice({ tone: "success", text: `任务 ${taskUuid} 已删除。` });
    } catch (error) {
      showError(error);
    }
  }

  async function handleApplyHistoryTask() {
    if (!selectedHistoryTaskUuid) {
      setNotice({ tone: "error", text: "请先在历史任务表中选择一个任务。" });
      return;
    }
    setSelectedTaskUuid(selectedHistoryTaskUuid);
    setPage("dashboard");
    setNotice({ tone: "success", text: `已将任务 ${selectedHistoryTaskUuid} 设为当前任务。` });
  }

  async function handleUpdateMemoryPolicy() {
    try {
      const response = await withBusy("正在更新内存软限额", () =>
        request<AnyRecord>("/admin/system/runtime-policy", {
          method: "POST",
          body: {
            memory_soft_limit_percent: Number(memoryLimitPercentDraft || 0),
            memory_soft_reserve_mb: Number(memoryReserveDraft || 0),
          },
        }),
      );
      const item = safeObject(response.item);
      const policy = safeObject(item.policy);
      setSystemRuntimeBundle(item);
      setMemoryLimitPercentDraft(String(policy.memory_soft_limit_percent ?? memoryLimitPercentDraft));
      setMemoryReserveDraft(String(policy.memory_soft_reserve_mb ?? memoryReserveDraft));
      setNotice({ tone: "success", text: "内存软限额已更新，新任务会按新阈值调度。" });
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
            step_thresholds_ms:
              stepThresholdRows.length > 0
                ? nestedMappingFromRows(stepThresholdRows)
                : parseJsonText(thresholdEditor.step_thresholds_ms, "step_thresholds_ms"),
            parameter_thresholds_seconds:
              thresholdRows.length > 0
                ? mappingFromRows(thresholdRows)
                : parseJsonText(thresholdEditor.parameter_thresholds_seconds, "parameter_thresholds_seconds"),
            parameter_expected_seconds:
              expectedRows.length > 0
                ? mappingFromRows(expectedRows)
                : parseJsonText(thresholdEditor.parameter_expected_seconds, "parameter_expected_seconds"),
            llm_context:
              contextRows.length > 0
                ? mappingFromRows(contextRows)
                : parseJsonText(thresholdEditor.llm_context, "llm_context"),
          },
        }),
      );
      setNotice({ tone: "success", text: "阈值配置已保存。" });
      await loadConfig();
    } catch (error) {
      showError(error);
    }
  }

  async function handleSaveEnvItem(key: string) {
    try {
      await withBusy(`正在保存 ${key}`, () =>
        request(`/config/env/${key}`, {
          method: "PUT",
          body: { value: String(envDrafts[key] ?? "") },
        }),
      );
      setNotice({ tone: "success", text: `${key} 已保存。` });
      await loadConfig();
    } catch (error) {
      showError(error);
    }
  }

  async function handleResetEnvItem(key: string) {
    try {
      await withBusy(`正在重置 ${key}`, () =>
        request(`/config/env/${key}/reset`, {
          method: "POST",
          body: {},
        }),
      );
      setNotice({ tone: "success", text: `${key} 已恢复默认值。` });
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
          timeoutMs: Math.max(Number(diagnoseTimeout || 120), 30) * 1000,
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
      let finalClusters = [...hubSelectedClusters];
      if (hubForm.new_cluster.trim()) {
        const clusterResponse = await request<AnyRecord>("/solution-repository/task-clusters", {
          method: "POST",
          body: {
            display_name: hubForm.new_cluster.trim(),
            description: hubForm.trigger_scenario || undefined,
          },
        });
        const newClusterName = String(clusterResponse.item?.display_name || hubForm.new_cluster.trim());
        finalClusters = finalClusters.includes(newClusterName)
          ? finalClusters
          : [...finalClusters, newClusterName];
      }
      const payload = {
        module: hubForm.module,
        error_name: hubForm.error_name,
        message: hubForm.message,
        message_keywords: splitCommaText(hubForm.message_keywords),
        tags: splitCommaText(hubForm.tags),
        task_clusters: finalClusters,
        root_cause_analysis: hubForm.root_cause_analysis,
        verified_solution: hubForm.verified_solution,
        workaround: hubForm.workaround,
        trigger_scenario: hubForm.trigger_scenario,
        task_uuid: hubForm.task_uuid || selectedTaskUuid || undefined,
        normalized_signature: hubForm.normalized_signature || selectedErrorSignature || undefined,
        submitter: String(user?.username || ""),
        submission_type: "solution_record",
        reusable: true,
        source: "next_frontend_solution_center",
      };
      const endpoint = isReviewer ? "/solution-repository/records" : "/solution-reviews";
      await withBusy("正在提交方案", () =>
        request(endpoint, {
          method: "POST",
          body: payload,
        }),
      );
      setHubForm({
        module: hubForm.module,
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
      setHubSelectedClusters([]);
      setNotice({ tone: "success", text: isReviewer ? "方案已写入方案库。" : "方案已提交审核。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  function handlePrefillSolutionEntry() {
    const diagnosis = safeObject(llmBundle.latestDiagnosis);
    const structuredResult = safeObject(diagnosis.structured_result);
    const currentError =
      errorItems.find((item) => String(item.normalized_signature) === selectedErrorSignature) || null;
    setHubForm((current) => ({
      ...current,
      module: current.module || llmForm.module || "",
      error_name:
        current.error_name ||
        reviewDraft.error_name ||
        String(currentError?.display_signature || currentError?.normalized_signature || ""),
      message: current.message || String(currentError?.representative_message || ""),
      root_cause_analysis:
        current.root_cause_analysis ||
        reviewDraft.root_cause_analysis ||
        String(structuredResult.root_cause_summary || ""),
      verified_solution: current.verified_solution || reviewDraft.verified_solution,
      workaround: current.workaround || reviewDraft.workaround,
      trigger_scenario: current.trigger_scenario || llmForm.triggerScenario || "",
      task_uuid: current.task_uuid || selectedTaskUuid || "",
      normalized_signature: current.normalized_signature || selectedErrorSignature || "",
    }));
    setNotice({ tone: "info", text: "已尝试带入当前错误簇和诊断上下文，请继续补充后提交。" });
  }

  async function handleImportSolutionRepository() {
    if (!hubImportFile) {
      setNotice({ tone: "error", text: "请先选择要导入的方案库文件。" });
      return;
    }
    try {
      const formData = new FormData();
      formData.append("file", hubImportFile);
      formData.append("preserve_error_codes", "true");
      const response = await withBusy("正在导入方案库文件", () =>
        request<AnyRecord>("/solution-repository/import", {
          method: "POST",
          formData,
        }),
      );
      setHubImportResult(safeObject(response.item));
      setNotice({ tone: "success", text: "方案库导入已完成，请查看导入摘要。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleAskSolutionRepository() {
    if (!hubAssistantQuestion.trim()) {
      setNotice({ tone: "error", text: "请先输入问题或现象描述。" });
      return;
    }
    try {
      const response = await withBusy("正在基于方案库生成回答", () =>
        request<AnyRecord>("/solution-repository/ask", {
          method: "POST",
          body: { question: hubAssistantQuestion.trim(), limit: 8 },
        }),
      );
      setHubAssistantResult(safeObject(response.item));
      setNotice({ tone: "success", text: "方案库问答已生成。" });
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

  async function handleResendCode() {
    try {
      await withBusy("正在重新发送验证码", () =>
        platformRequest(apiBase, "/auth/register/resend-code", {
          token: null,
          method: "POST",
          body: { login_name: registerUsername.trim() || registerEmail.trim() },
        }),
      );
      setNotice({ tone: "success", text: "验证码已重新发送，请检查邮箱。" });
    } catch (error) {
      showError(error);
    }
  }

  async function handleFindSimilarCases() {
    if (!selectedTaskUuid || !selectedErrorSignature) {
      setNotice({ tone: "error", text: "请先选择任务和错误簇。" });
      return;
    }
    try {
      const response = await withBusy("正在检索相似案例", () =>
        request<AnyRecord>(`/tasks/${selectedTaskUuid}/errors/${selectedErrorSignature}/similar-cases`, {
          query: {
            module: llmForm.module || undefined,
            trigger_scenario: llmForm.triggerScenario || undefined,
          },
        }),
      );
      setLlmBundle((current) => ({ ...current, similarCases: safeArray(response.items) }));
      setNotice({ tone: "success", text: `已检索到 ${safeArray(response.items).length} 条相似案例。` });
    } catch (error) {
      showError(error);
    }
  }

  async function handleSubmitDiagnosisReview() {
    const selectedError =
      safeArray(llmBundle.errors).find(
        (item) => String(item.normalized_signature) === selectedErrorSignature,
      ) || null;
    const diagnosis = safeObject(llmBundle.latestDiagnosis);
    if (!selectedTaskUuid || !selectedErrorSignature || !selectedError || !diagnosis) {
      setNotice({ tone: "error", text: "请先完成一次综合诊断。" });
      return;
    }
    try {
      const payload = {
        task_uuid: selectedTaskUuid,
        submission_type: "solution_record",
        error_name: reviewDraft.error_name || String(selectedError.display_signature || ""),
        error_category: reviewDraft.error_category,
        module: llmForm.module,
        submodule: llmForm.submodule,
        message: String(
          selectedError.representative_message || selectedError.display_signature || "",
        ),
        normalized_signature: selectedErrorSignature,
        exception_description: String(
          selectedError.error_family_display || selectedError.error_family || "",
        ),
        trigger_scenario: llmForm.triggerScenario,
        impact_scope: reviewDraft.impact_scope,
        report_source: `task:${selectedTaskUuid}`,
        related_logs: {
          display_signature: selectedError.display_signature,
          representative_message: selectedError.representative_message,
          count: selectedError.count,
        },
        related_source_files: diagnosis.source_context_snippets || [],
        root_cause_analysis:
          reviewDraft.root_cause_analysis ||
          safeObject(diagnosis.structured_result).root_cause_summary,
        verified_solution: reviewDraft.verified_solution,
        workaround: reviewDraft.workaround,
        owner_department:
          reviewDraft.owner_department ||
          safeArray(safeObject(diagnosis.structured_result).owner_departments).join(","),
        submitter: reviewDraft.submitter || String(user?.username || "next_frontend"),
        source: "next_frontend_submit_review",
        reusable: reviewDraft.reusable,
        similar_case_refs: safeArray(diagnosis.similar_cases).map((row) => row.case_id),
        metadata: {
          analysis_depth: diagnosis.analysis_stage,
          analysis_result: diagnosis.structured_result || {},
          customer_symptom: llmForm.customerSymptom,
          environment_info: llmForm.environmentInfo,
          reproduction_steps: llmForm.reproductionSteps,
          operation_path: llmForm.operationPath,
        },
        attachments: diagnosis.source_context_snippets || [],
      };
      const response = await withBusy("正在提交入库审核", () =>
        request<AnyRecord>("/solution-reviews", {
          method: "POST",
          body: payload,
        }),
      );
      setLlmBundle((current) => ({ ...current, latestReview: response.item || response }));
      setNotice({ tone: "success", text: "诊断结果已提交审核。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleSaveRepositoryRecord() {
    if (!editingRecordId) {
      setNotice({ tone: "error", text: "请先选择一条方案记录。" });
      return;
    }
    const record = safeArray(hubBundle.records?.items).find(
      (item) => String(item.id) === editingRecordId,
    );
    if (!record) {
      setNotice({ tone: "error", text: "未找到当前选中的方案记录。" });
      return;
    }
    try {
      await withBusy("正在保存方案记录", () =>
        request(`/solution-repository/records/${editingRecordId}`, {
          method: "PUT",
          body: {
            ...record,
            ...editingRecordDraft,
          },
        }),
      );
      setNotice({ tone: "success", text: "方案记录已更新。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleManualSolutionReview(status: "approved" | "needs_revision" | "rejected") {
    if (!selectedReviewId) {
      setNotice({ tone: "error", text: "请先选择一条审核记录。" });
      return;
    }
    try {
      await withBusy("正在提交人工审核", () =>
        request(`/solution-reviews/${selectedReviewId}/manual-review`, {
          method: "POST",
          body: {
            review_status: status,
            reviewer: manualReviewer || user?.username,
            notes: hubReviewNotes || manualReviewNotes || undefined,
          },
        }),
      );
      setNotice({ tone: "success", text: `审核状态已更新为 ${status}。` });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleCreateTaskCluster() {
    if (!newClusterDraft.name.trim()) {
      setNotice({ tone: "error", text: "请填写任务簇名称。" });
      return;
    }
    try {
      const response = await withBusy("正在提交任务簇", () =>
        request<AnyRecord>("/solution-repository/task-clusters", {
          method: "POST",
          body: {
            display_name: newClusterDraft.name.trim(),
            description: newClusterDraft.description.trim() || undefined,
          },
        }),
      );
      setNewClusterDraft({ name: "", description: "" });
      const item = safeObject(response.item);
      if (item.display_name) {
        setHubSelectedClusters((current) =>
          current.includes(String(item.display_name))
            ? current
            : [...current, String(item.display_name)],
        );
      }
      setNotice({ tone: "success", text: "任务簇已提交。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleReviewTaskCluster(status: "approved" | "rejected" | "disabled") {
    if (!selectedClusterId) {
      setNotice({ tone: "error", text: "请先选择要审核的任务簇。" });
      return;
    }
    try {
      await withBusy("正在更新任务簇状态", () =>
        request(`/solution-repository/task-clusters/${selectedClusterId}/review`, {
          method: "POST",
          body: { review_status: status },
        }),
      );
      setNotice({ tone: "success", text: `任务簇已更新为 ${status}。` });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleSaveModuleConfig() {
    if (!newModuleDraft.module_key.trim() || !newModuleDraft.display_name.trim()) {
      setNotice({ tone: "error", text: "请至少填写 module_key 和 display_name。" });
      return;
    }
    try {
      await withBusy("正在保存模块配置", () =>
        request("/solution-repository/modules", {
          method: "POST",
          body: {
            ...newModuleDraft,
            is_active: true,
          },
        }),
      );
      setNewModuleDraft({ module_key: "", display_name: "", prefix: "", description: "" });
      setNotice({ tone: "success", text: "模块配置已保存。" });
      await loadSolutionHub();
    } catch (error) {
      showError(error);
    }
  }

  async function handleRuleReview(status: string, suggestionId: string) {
    if (!suggestionId) {
      setNotice({ tone: "error", text: "请先选择一条规则建议。" });
      return;
    }
    try {
      await withBusy("正在提交规则建议审核", () =>
        request(`/active-learning/rule-suggestions/${suggestionId}/review`, {
          method: "POST",
          body: {
            review_status: status,
            reviewer: ruleReviewer || user?.username,
            notes: ruleReviewNotes || undefined,
          },
        }),
      );
      setNotice({ tone: "success", text: `规则建议已更新为 ${status}。` });
      await loadRules(ruleLlmEnabled);
    } catch (error) {
      showError(error);
    }
  }

  async function handleUpdateUserStatus(action: "approve" | "reject" | "disable" | "enable") {
    if (!selectedUserId) {
      setNotice({ tone: "error", text: "请先选择用户。" });
      return;
    }
    try {
      await withBusy("正在更新用户状态", () =>
        request(`/admin/users/${selectedUserId}/status`, {
          method: "POST",
          body: { action },
        }),
      );
      setNotice({ tone: "success", text: `用户状态已更新为 ${action}。` });
      await loadUsers();
    } catch (error) {
      showError(error);
    }
  }

  async function handleSaveUserRoles() {
    if (!selectedUserId) {
      setNotice({ tone: "error", text: "请先选择用户。" });
      return;
    }
    try {
      await withBusy("正在保存角色设置", () =>
        request(`/admin/users/${selectedUserId}/roles`, {
          method: "POST",
          body: selectedUserRoles,
        }),
      );
      setNotice({ tone: "success", text: "角色设置已保存。" });
      await loadUsers();
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
    if (typeof window !== "undefined") {
      if (selectedTaskUuid) {
        window.localStorage.setItem(TASK_STORAGE_KEY, selectedTaskUuid);
      } else {
        window.localStorage.removeItem(TASK_STORAGE_KEY);
      }
    }
  }, [selectedTaskUuid]);

  useEffect(() => {
    if (token && user) {
      void refreshShell(token);
    }
  }, [apiBase, token, user]);

  useEffect(() => {
    if (isAuthenticated && page === "dashboard") {
      void Promise.all([loadDashboard(), loadSystemRuntime()]).catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid]);

  useEffect(() => {
    if (isAuthenticated && page === "upload") {
      void loadDashboard().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid]);

  useEffect(() => {
    if (isAuthenticated && page === "history") {
      void loadHistory().catch(showError);
    }
  }, [isAuthenticated, page, historyPage, historyPageSize]);

  useEffect(() => {
    if (isAuthenticated && page === "events") {
      void loadEvents().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid, eventsPage, eventsPageSize]);

  useEffect(() => {
    if (isAuthenticated && page === "performance") {
      void loadPerformance().catch(showError);
    }
  }, [
    isAuthenticated,
    page,
    selectedTaskUuid,
    performanceUnit,
    performanceStepPage,
    performanceStepPageSize,
  ]);

  useEffect(() => {
    if (isAuthenticated && page === "timeline") {
      void loadTimeline().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid, timelineCycleNo, timelineTrackOrder]);

  useEffect(() => {
    if (isAuthenticated && page === "errors") {
      void loadErrors().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid, errorsPage, errorsPageSize]);

  useEffect(() => {
    if (isAuthenticated && page === "parameters") {
      void loadParameters().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid, parameterUnit, selectedParameters]);

  useEffect(() => {
    if (isAuthenticated && page === "llm") {
      void (async () => {
        await loadErrors();
        await loadLlm();
        await loadSolutionHub();
      })().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid, errorsPage, errorsPageSize]);

  useEffect(() => {
    if (isAuthenticated && page === "solutionHub") {
      void loadSolutionHub().catch(showError);
    }
  }, [isAuthenticated, page]);

  useEffect(() => {
    if (isAuthenticated && page === "files") {
      void loadFiles().catch(showError);
    }
  }, [isAuthenticated, page, selectedTaskUuid, filesPage, filesPageSize]);

  useEffect(() => {
    if (isAuthenticated && page === "unknown") {
      void loadUnknown().catch(showError);
    }
  }, [isAuthenticated, page]);

  useEffect(() => {
    if (isAuthenticated && page === "rules") {
      void loadRules(false).catch(showError);
    }
  }, [isAuthenticated, page]);

  useEffect(() => {
    if (isAuthenticated && page === "config") {
      void loadConfig().catch(showError);
    }
  }, [isAuthenticated, page]);

  useEffect(() => {
    if (isAuthenticated && page === "users" && isAdmin) {
      void loadUsers().catch(showError);
    }
  }, [isAuthenticated, page, isAdmin]);

  useEffect(() => {
    const record = safeArray(hubBundle.records?.items).find(
      (item) => String(item.id) === editingRecordId,
    );
    if (!record) {
      return;
    }
    setEditingRecordDraft({
      root_cause_analysis: String(record.root_cause_analysis || ""),
      verified_solution: String(record.verified_solution || ""),
      workaround: String(record.workaround || ""),
      reusable: Boolean(record.reusable),
    });
  }, [editingRecordId, hubBundle.records]);

  useEffect(() => {
    const currentUserItem = userList.find((item) => String(item.id) === selectedUserId);
    if (!currentUserItem) {
      return;
    }
    setSelectedUserRoles({
      is_reviewer: Boolean(currentUserItem.is_reviewer),
      is_admin: Boolean(currentUserItem.is_admin),
    });
  }, [selectedUserId, userList]);

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
  const localFixSuggestions = safeArray(localPreview.rule_fix_suggestions);
  const llmResult = safeObject(llmMeta.result);
  const llmFixSuggestions = safeArray(llmResult.rule_fix_suggestions);
  const ruleReviews = safeArray(rulesBundle.reviews?.items);
  const historyItems = safeArray(historyBundle.items);
  const historyRows = safeArray(llmBundle.history);
  const uniqueHistorySignatures = Array.from(
    new Set(
      historyRows
        .map((row) => String(row.normalized_signature || ""))
        .filter(Boolean),
    ),
  ).sort();
  const filteredHistoryRows =
    llmHistorySignatureFilter && llmHistorySignatureFilter !== "全部"
      ? historyRows.filter(
          (row) => String(row.normalized_signature || "") === llmHistorySignatureFilter,
        )
      : historyRows;
  const selectedHistoryRow =
    filteredHistoryRows[Number(selectedHistoryIndex || 0)] || filteredHistoryRows[0] || null;
  const llmStrategyMap = safeObject(repoConfig?.analysis_depths);
  const llmModuleTree = safeArray(repoConfig?.module_tree);
  const llmModuleOptions = llmModuleTree
    .map((row) => String(row.name || ""))
    .filter(Boolean);
  const activeStrategy = safeObject(llmStrategyMap[llmForm.analysisDepth]);
  const dashboardData = safeObject(dashboardBundle.dashboard);
  const statusData = safeObject(dashboardBundle.status);
  const performanceSummaryData = safeObject(dashboardBundle.performance);
  const cycleSummaryRows = safeArray(performanceBundle.cycleSummary);
  const stepRows = safeArray(performanceBundle.steps?.items);
  const photoSummaryRows = safeArray(safeObject(performanceBundle.operationalMetrics).photo_summary);
  const timelineRows = safeArray(timelineBundle.rows);
  const timelineErrors = safeArray(timelineBundle.errors);
  const timelineFamilyOptions = Array.from(
    new Set(
      timelineErrors
        .map((row) => String(row.error_family_display || row.error_family || ""))
        .filter(Boolean),
    ),
  ).sort();
  const timelineSeverityOptions = Array.from(
    new Set(
      timelineErrors
        .map((row) => String(row.severity || "unknown"))
        .filter(Boolean),
    ),
  ).sort();
  const activeTimelineFamilies =
    timelineSelectedFamilies.length > 0 ? timelineSelectedFamilies : timelineFamilyOptions;
  const activeTimelineSeverities =
    timelineSelectedSeverities.length > 0 ? timelineSelectedSeverities : timelineSeverityOptions;
  const filteredTimelineErrors = timelineShowErrors
    ? timelineErrors.filter((row) => {
        const family = String(row.error_family_display || row.error_family || "");
        const severity = String(row.severity || "unknown");
        return activeTimelineFamilies.includes(family) && activeTimelineSeverities.includes(severity);
      })
    : [];
  const errorFamilyRows = useMemo(() => {
    const groups = new Map<string, { label: string; description: string; value: number }>();
    errorItems.forEach((row) => {
      const key = String(row.error_family || row.error_family_display || "unknown");
      const current = groups.get(key) || {
        label: String(row.error_family_display || row.error_family || "unknown"),
        description: String(row.error_family_description || ""),
        value: 0,
      };
      current.value += Number(row.count || 0);
      groups.set(key, current);
    });
    return Array.from(groups.values()).sort((left, right) => right.value - left.value);
  }, [errorItems]);
  const selectedError =
    errorItems.find((item) => String(item.normalized_signature) === selectedErrorSignature) || null;
  const selectedHubReview =
    safeArray(hubBundle.reviews?.items).find((item) => String(item.id) === selectedReviewId) || null;
  const selectedHubCluster =
    safeArray(hubBundle.taskClusters).find((item) => String(item.id) === selectedClusterId) || null;
  const selectedRepositoryRecord =
    safeArray(hubBundle.records?.items).find((item) => String(item.id) === editingRecordId) || null;
  const selectedUserRecord = userList.find((item) => String(item.id) === selectedUserId) || null;
  const llmLatestDiagnosis = safeObject(llmBundle.latestDiagnosis);
  const llmLatestReview = safeObject(llmBundle.latestReview);
  const selectedHistoryTask =
    historyItems.find((item) => String(item.task_uuid) === selectedHistoryTaskUuid) || null;
  const runtimeData = safeObject(systemRuntimeBundle);
  const runtimeCpu = safeObject(runtimeData.cpu);
  const runtimeMemory = safeObject(runtimeData.memory);
  const runtimeDisk = safeObject(runtimeData.disk);
  const runtimePolicy = safeObject(runtimeData.policy);
  const runtimeGuard = safeObject(runtimeData.guard);
  const passwordChecks = useMemo(
    () => [
      { label: "当前密码已填写", passed: Boolean(currentPassword.trim()) },
      { label: "新密码至少 8 位", passed: nextPassword.length >= 8 },
      { label: "新旧密码不能相同", passed: Boolean(nextPassword) && currentPassword !== nextPassword },
      { label: "两次输入保持一致", passed: Boolean(nextPassword) && nextPassword === nextPasswordConfirm },
    ],
    [currentPassword, nextPassword, nextPasswordConfirm],
  );
  const canSubmitPasswordChange = passwordChecks.every((item) => item.passed);

  useEffect(() => {
    if (!filteredHistoryRows.length) {
      setSelectedHistoryIndex("0");
      return;
    }
    const nextIndex = Math.min(
      Math.max(Number(selectedHistoryIndex || 0), 0),
      Math.max(filteredHistoryRows.length - 1, 0),
    );
    if (String(nextIndex) !== selectedHistoryIndex) {
      setSelectedHistoryIndex(String(nextIndex));
    }
  }, [filteredHistoryRows.length, selectedHistoryIndex]);

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

  function renderRefreshButton(
    key: string,
    label: string,
    action: () => Promise<unknown>,
    variant: "default" | "secondary" | "ghost" | "danger" = "secondary",
  ) {
    const refreshing = isRefreshing(key);
    return (
      <Button variant={variant} disabled={refreshing} onClick={() => void runRefreshAction(key, action)}>
        <RefreshCcw className={cn("h-4 w-4", refreshing ? "animate-spin" : "")} />
        {label}
      </Button>
    );
  }

  function renderWelcome() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="日志分析平台"
          description="上传、分析、诊断、主动学习和方案全流程管理"
        />
        <div className="grid gap-6 lg:grid-cols-3">
          <MetricCard
            label="接口健康"
            value={String(health?.status || "unknown")}
            helper="实时探测后端 /health 状态。"
          />
          <MetricCard
            label="队列待处理"
            value={Number(health?.queue_pending || 0)}
            helper="反映当前正在等待调度的任务数量。"
          />
          <MetricCard
            label="前端模式"
            value="Streamlit Mirror"
            helper="保留 Streamlit 的使用路径，但交互与展示改为原生 Web。"
          />
        </div>
        <InfoTileGrid
          items={[
            { label: "上传与任务队列", value: "已接入", note: "支持多文件与压缩包日志提交。" },
            { label: "LLM 诊断", value: "已接入", note: "支持错误簇综合诊断、相似案例检索与审核提交。" },
            { label: "主动学习", value: "已接入", note: "未知日志池、规则建议审核与方案沉淀流程已接通。" },
          ]}
        />
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => startTransition(() => setPage("login"))}>
            <LogIn className="h-4 w-4" />
            前往登录
          </Button>
          <Button variant="secondary" onClick={() => startTransition(() => setPage("register"))}>
            申请注册
          </Button>
        </div>
      </div>
    );
  }

  function renderLogin() {
    return (
      <div className="mx-auto max-w-xl space-y-6">
        <SectionTitle title="登录" description="登录后即可访问日志任务、方案库、LLM 诊断和主动学习工作台。" />
        <Card>
          <CardContent className="pt-6">
            <form className="space-y-5" onSubmit={(event) => void handleLogin(event)}>
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
                <Button type="submit">登录</Button>
                <Button type="button" variant="secondary" onClick={() => setPage("register")}>
                  去注册
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    );
  }

  function renderRegister() {
    return (
      <div className="mx-auto max-w-3xl space-y-6">
        <SectionTitle title="注册申请" description="保持与 Streamlit 相同的三段式流程：发送验证码、邮箱验证、提交审核。" />
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
            <Field label="用户名">
              <Input value={registerUsername} onChange={(event) => setRegisterUsername(event.target.value)} />
            </Field>
            <Field label="邮箱">
              <Input value={registerEmail} onChange={(event) => setRegisterEmail(event.target.value)} />
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
            <div className="lg:col-span-2">
              <Field label="注册备注">
                <Textarea value={registerNote} onChange={(event) => setRegisterNote(event.target.value)} />
              </Field>
            </div>
            <div className="lg:col-span-2">
              <Field label={`验证码 / 当前状态: ${registerStep}`}>
                <Input value={registerCode} onChange={(event) => setRegisterCode(event.target.value)} />
              </Field>
            </div>
            <div className="lg:col-span-2 flex flex-wrap gap-3">
              <Button onClick={() => void handleRequestCode()}>发送验证码</Button>
              <Button variant="secondary" onClick={() => void handleVerifyCode()}>
                验证邮箱
              </Button>
              <Button variant="secondary" onClick={() => void handleResendCode()}>
                重发验证码
              </Button>
              <Button variant="secondary" onClick={() => void handleSubmitRegistration()}>
                提交注册
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  function renderDashboardPage() {
    const cpuPercent = Number.isFinite(Number(runtimeCpu.percent)) ? Number(runtimeCpu.percent) : null;
    const memoryPercent = Number.isFinite(Number(runtimeMemory.percent)) ? Number(runtimeMemory.percent) : null;
    const diskPercent = Number.isFinite(Number(runtimeDisk.percent)) ? Number(runtimeDisk.percent) : null;
    const loadAvg = safeObject(runtimeCpu.load_avg);

    return (
      <div className="space-y-8">
        <SectionTitle
          title="首页 / 仪表盘"
          description="优先回答当前任务是否异常、问题集中在哪里、是否值得继续深挖。"
          actions={renderRefreshButton("dashboard", "刷新仪表盘", () => Promise.all([loadDashboard(), loadSystemRuntime()]))}
        />
        <div className="grid gap-4 lg:grid-cols-4">
          <MetricCard label="文件数" value={dashboardData.file_count || 0} helper="纳入本次分析的原始文件数量。" />
          <MetricCard label="总事件数" value={dashboardData.total_events || 0} helper="统一归档后的事件总量。" />
          <MetricCard label="总错误数" value={dashboardData.total_errors || 0} helper="任务中识别到的错误总数。" />
          <MetricCard label="唯一错误簇" value={dashboardData.unique_error_count || 0} helper="按签名去重后的错误簇数量。" />
        </div>
        <div className="grid gap-4 xl:grid-cols-3">
          <UsageStatusCard
            label="CPU 使用状态"
            percent={cpuPercent}
            primary={formatPercentLabel(runtimeCpu.percent)}
            secondary={`${runtimeCpu.logical_cores || "-"} 逻辑核 | load1 ${formatRuntimeNumber(loadAvg.load_1m, 2)}`}
            helper="用于观察服务当前计算压力。"
          />
          <UsageStatusCard
            label="内存使用状态"
            percent={memoryPercent}
            primary={`${formatStorageLabel(runtimeMemory.used_mb, "MB")} / ${formatStorageLabel(runtimeMemory.total_mb, "MB")}`}
            secondary={`可用 ${formatStorageLabel(runtimeMemory.available_mb, "MB")} | 软上限 ${runtimePolicy.memory_soft_limit_percent || "-"}%`}
            helper="达到软限额后只会延迟新任务调度，不会中断正在进行的分析。"
          />
          <UsageStatusCard
            label="存储使用状态"
            percent={diskPercent}
            primary={`${formatStorageLabel(runtimeDisk.used_gb, "GB")} / ${formatStorageLabel(runtimeDisk.total_gb, "GB")}`}
            secondary={`剩余 ${formatStorageLabel(runtimeDisk.free_gb, "GB")} | ${runtimeDisk.path || "data"}`}
            helper="基于服务数据目录所在磁盘统计当前占用。"
          />
        </div>
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
              <div className="space-y-2">
                <p className="text-sm font-medium text-[var(--foreground)]">服务器资源守护</p>
                <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                  {runtimeGuard.summary || "当前尚未获取到资源守护状态。"}
                </p>
              </div>
              <StatusBadge status={runtimeGuard.blocked ? "queued" : "completed"} />
            </div>
            <InfoTileGrid
              columns={4}
              items={[
                { label: "新任务调度", value: runtimeGuard.dispatch_allowed ? "允许" : "延迟", note: "只影响新任务，不影响运行中任务" },
                { label: "内存软上限", value: runtimePolicy.memory_soft_limit_percent || "-", note: "单位为 %" },
                { label: "保留内存", value: runtimePolicy.memory_soft_reserve_mb || "-", note: "单位为 MB" },
                { label: "守护检查间隔", value: runtimePolicy.guard_wait_seconds || "-", note: "单位为秒" },
              ]}
            />
            {isAdmin ? (
              <div className="grid gap-4 rounded-2xl border border-[var(--border)] bg-[var(--muted)]/25 p-4 lg:grid-cols-[1fr_1fr_auto]">
                <Field label="内存软上限 (%)" hint="建议保留一定冗余，避免新任务挤占分析进程资源。">
                  <Input
                    type="number"
                    min="50"
                    max="98"
                    value={memoryLimitPercentDraft}
                    onChange={(event) => setMemoryLimitPercentDraft(event.target.value)}
                  />
                </Field>
                <Field label="保留内存 (MB)" hint="当可用内存低于该值时，新任务会继续排队等待。">
                  <Input
                    type="number"
                    min="0"
                    value={memoryReserveDraft}
                    onChange={(event) => setMemoryReserveDraft(event.target.value)}
                  />
                </Field>
                <div className="flex items-end">
                  <Button className="w-full" onClick={() => void handleUpdateMemoryPolicy()}>
                    保存限额
                  </Button>
                </div>
              </div>
            ) : null}
          </CardContent>
        </Card>
        <InfoTileGrid
          items={[
            { label: "当前状态", value: statusData.status || "-", note: statusData.current_stage || "等待状态同步" },
            { label: "任务进度", value: `${statusData.progress_percent || 0}%`, note: String(statusData.message || "暂无补充信息") },
            {
              label: "错误密度",
              value: formatPercent(Number(dashboardData.total_errors || 0), Number(dashboardData.total_events || 0), 2),
              note: "错误条目 / 总事件数",
            },
            {
              label: "平均每文件事件",
              value: dashboardData.file_count ? Math.round(Number(dashboardData.total_events || 0) / Number(dashboardData.file_count || 1)) : 0,
              note: "总事件 / 文件数",
            },
          ]}
          columns={4}
        />
        <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
          <DistributionList title="高频错误簇 Top 8" items={topErrorDistribution} />
          <DistributionList title="组件错误分布" items={componentDistribution} />
        </div>
        <DetailListCard title="任务状态摘要" value={dashboardBundle} />
        {safeObject(performanceSummaryData).stage_timings ? (
          <DetailListCard
            title="性能摘要"
            description="保留 Streamlit 中折叠区的关键信息，便于查看后端阶段耗时。"
            value={performanceSummaryData}
          />
        ) : null}
      </div>
    );
  }

  function renderHistoryPage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="历史项目中心"
          description="浏览已有任务记录，快速切换任务并回看分析结果。"
          actions={renderRefreshButton("history", "刷新任务列表", () => loadHistory())}
        />
        <PaginationBar
          page={historyPage}
          pageSize={historyPageSize}
          total={Number(historyBundle.total || 0)}
          onPageChange={setHistoryPage}
          onPageSizeChange={(value) => {
            setHistoryPage(1);
            setHistoryPageSize(value);
          }}
        />
        <DataTable
          title={`任务列表 (${Number(historyBundle.total || 0)})`}
          rows={historyItems}
          selectedRowIndex={historyItems.findIndex((item) => String(item.task_uuid) === selectedHistoryTaskUuid)}
          onRowClick={(row) => setSelectedHistoryTaskUuid(String(row.task_uuid || ""))}
          maxHeight={520}
        />
        {selectedHistoryTask ? (
          <>
            <DetailListCard
              title="历史任务详情"
              description="在这里先确认任务是否需要继续查看，或直接执行删除。"
              value={selectedHistoryTask}
            />
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void handleApplyHistoryTask()}>设为当前任务</Button>
              <Button
                variant="danger"
                onClick={() => {
                  if (
                    typeof window === "undefined" ||
                    window.confirm(`确定要删除任务 ${selectedHistoryTask.task_uuid} 吗？该操作不可恢复。`)
                  ) {
                    void handleDeleteTask(String(selectedHistoryTask.task_uuid));
                  }
                }}
              >
                删除选中任务
              </Button>
            </div>
          </>
        ) : null}
      </div>
    );
  }

  function renderUploadPage() {
    return (
      <div className="space-y-8">
        <SectionTitle
          title="文件上传"
          description="支持多文件与压缩包日志上传，任务提交后进入后端队列分析。"
          actions={
            <Button onClick={() => void handleUploadLogs()}>
              <Upload className="h-4 w-4" />
              开始上传并分析
            </Button>
          }
        />
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
            <Field label="选择日志文件">
              <Input type="file" multiple onChange={(event) => setUploadFiles(Array.from(event.target.files || []))} />
            </Field>
            <Field label="CPU 核心数">
              <Input type="number" min="1" value={uploadCpuCores} onChange={(event) => setUploadCpuCores(event.target.value)} />
            </Field>
          </CardContent>
        </Card>
        <InfoTileGrid
          columns={4}
          items={[
            { label: "状态", value: statusData.status || "-", note: "当前任务的处理状态。" },
            { label: "进度", value: `${statusData.progress_percent || 0}%`, note: statusData.current_stage || "-" },
            { label: "识别文件数", value: statusData.file_count || 0, note: "后端已登记的文件数量。" },
            { label: "队列位置", value: statusData.queue_position || 0, note: "0 表示正在执行或无需排队。" },
          ]}
        />
        <DetailListCard title="当前任务进度" value={statusData} />
      </div>
    );
  }

  function renderEventsPage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="统一事件流"
          description="按组件、级别、Cycle、芯片名和关键词检索统一归档后的事件流。"
          actions={renderRefreshButton("events", "刷新事件流", () => loadEvents())}
        />
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-5">
            <Field label="组件">
              <Input value={eventsFilter.component} onChange={(event) => setEventsFilter((current) => ({ ...current, component: event.target.value }))} />
            </Field>
            <Field label="级别">
              <Select value={eventsFilter.level} onChange={(event) => setEventsFilter((current) => ({ ...current, level: event.target.value }))}>
                <option value="">全部</option>
                <option value="INFO">INFO</option>
                <option value="WARN">WARN</option>
                <option value="ERROR">ERROR</option>
                <option value="FATAL">FATAL</option>
              </Select>
            </Field>
            <Field label="Cycle">
              <Input value={eventsFilter.cycleNo} onChange={(event) => setEventsFilter((current) => ({ ...current, cycleNo: event.target.value }))} />
            </Field>
            <Field label="芯片名">
              <Input value={eventsFilter.chipName} onChange={(event) => setEventsFilter((current) => ({ ...current, chipName: event.target.value }))} />
            </Field>
            <Field label="关键词">
              <Input value={eventsFilter.search} onChange={(event) => setEventsFilter((current) => ({ ...current, search: event.target.value }))} />
            </Field>
          </CardContent>
        </Card>
        <PaginationBar
          page={eventsPage}
          pageSize={eventsPageSize}
          total={Number(eventsResponse.total || 0)}
          onPageChange={setEventsPage}
          onPageSizeChange={(value) => {
            setEventsPage(1);
            setEventsPageSize(value);
          }}
        />
        <DataTable title="统一事件流" rows={safeArray(eventsResponse.items)} maxHeight={560} />
      </div>
    );
  }

  function renderPerformancePage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="耗时分析"
          description="查看 Cycle 总耗时趋势、Sub-step 表现和操作指标摘要。"
          actions={renderRefreshButton("performance", "刷新耗时分析", () => loadPerformance())}
        />
        <Card>
          <CardContent className="pt-6">
            <Field label="Cycle 总耗时单位">
              <Select value={performanceUnit} onChange={(event) => setPerformanceUnit(event.target.value)}>
                {durationUnits.map((unit) => (
                  <option key={unit.value} value={unit.value}>
                    {unit.label}
                  </option>
                ))}
              </Select>
            </Field>
          </CardContent>
        </Card>
        <SimpleLineChart
          title={`Cycle 总耗时趋势 (${performanceUnit})`}
          rows={cycleSummaryRows}
          xKey="cycle_no"
          yKey="total_duration_value"
          seriesKey="chip_name"
        />
        <PaginationBar
          page={performanceStepPage}
          pageSize={performanceStepPageSize}
          total={Number(performanceBundle.steps?.total || 0)}
          onPageChange={setPerformanceStepPage}
          onPageSizeChange={(value) => {
            setPerformanceStepPage(1);
            setPerformanceStepPageSize(value);
          }}
        />
        <DataTable title="Sub-step 耗时表" rows={stepRows} maxHeight={520} />
        <DataTable title="拍照时间摘要" rows={photoSummaryRows} maxHeight={320} />
        <DetailListCard title="操作指标摘要" value={performanceBundle.operationalMetrics} />
      </div>
    );
  }

  function renderTimelinePage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="事件流时间轴"
          description="从时间维度观察各组件动作顺序和错误点，并支持按错误家族与严重级别筛选。"
          actions={renderRefreshButton("timeline", "刷新时间轴", () => loadTimeline())}
        />
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
            <Field label="选择 Cycle">
              <Select value={timelineCycleNo} onChange={(event) => setTimelineCycleNo(event.target.value)}>
                <option value="">全程</option>
                {safeArray(timelineBundle.cycles).map((value) => (
                  <option key={String(value)} value={String(value)}>
                    {String(value)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="纵轴顺序">
              <Select value={timelineTrackOrder} onChange={(event) => setTimelineTrackOrder(event.target.value)}>
                <option value="default">默认顺序</option>
                <option value="cycle">按 cycle 排序</option>
              </Select>
            </Field>
            <div className="lg:col-span-2 flex flex-wrap gap-6">
              <label className="flex items-center gap-2 text-sm text-[var(--foreground)]">
                <input type="checkbox" checked={timelineShowErrors} onChange={(event) => setTimelineShowErrors(event.target.checked)} />
                标记错误发生时间点
              </label>
              <label className="flex items-center gap-2 text-sm text-[var(--foreground)]">
                <input type="checkbox" checked={timelineShowDetails} onChange={(event) => setTimelineShowDetails(event.target.checked)} />
                显示时间轴表格明细
              </label>
            </div>
            {timelineShowErrors ? (
              <>
                <div className="lg:col-span-2">
                  <Field label="显示哪些错误家族">
                    <ChipToggleGroup options={timelineFamilyOptions} selected={activeTimelineFamilies} onToggle={(value) => setTimelineSelectedFamilies((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value])} />
                  </Field>
                </div>
                <div className="lg:col-span-2">
                  <Field label="显示哪些严重级别">
                    <ChipToggleGroup options={timelineSeverityOptions} selected={activeTimelineSeverities} onToggle={(value) => setTimelineSelectedSeverities((current) => current.includes(value) ? current.filter((item) => item !== value) : [...current, value])} />
                  </Field>
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
        <TimelineChart
          title="按 Cycle / 全程查看各组件运动时间轴"
          rows={timelineRows}
          errors={filteredTimelineErrors}
        />
        {timelineShowDetails ? (
          <DataTable
            title="时间轴表格明细"
            rows={timelineRows.map((row) => ({
              track: row.track,
              cycle_no: row.cycle_no,
              component: row.component,
              sub_step: row.sub_step,
              start_time_sec: row.start_time_sec,
              end_time_sec: row.end_time_sec,
              duration_ms: row.duration_ms,
              message: row.message,
            }))}
          />
        ) : null}
      </div>
    );
  }

  function renderErrorsPage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="错误分析"
          description="保留 Streamlit 的错误簇表、Top N 分布、错误家族分布和家族说明。"
          actions={renderRefreshButton("errors", "刷新错误分析", () => loadErrors())}
        />
        <PaginationBar
          page={errorsPage}
          pageSize={errorsPageSize}
          total={Number(errorsResponse.total || 0)}
          onPageChange={setErrorsPage}
          onPageSizeChange={(value) => {
            setErrorsPage(1);
            setErrorsPageSize(value);
          }}
        />
        <DataTable title="错误簇" rows={errorItems} maxHeight={420} />
        <TabBar
          tabs={[
            { key: "top", label: "错误簇 Top N" },
            { key: "family", label: "错误家族分布" },
            { key: "guide", label: "家族说明" },
          ]}
          active={errorTab}
          onChange={setErrorTab}
        />
        {errorTab === "top" ? (
          <DistributionList title="高频错误簇 Top 8" items={topErrorDistribution} />
        ) : errorTab === "family" ? (
          <DistributionList
            title="错误家族分布"
            items={errorFamilyRows.map((row) => ({
              label: row.label,
              value: row.value,
              note: row.description,
            }))}
          />
        ) : (
          <DataTable
            title="家族说明"
            rows={errorFamilyRows.map((row) => ({
              家族名称: row.label,
              错误次数: row.value,
              说明: row.description,
            }))}
          />
        )}
      </div>
    );
  }

  function renderParametersPage() {
    const parameterDefinitions = safeArray(parameterBundle.definitions).map((item) =>
      String(item.parameter_name),
    );
    return (
      <div className="space-y-6">
        <SectionTitle
          title="参数趋势分析"
          description="按参数与单位查看趋势曲线、Sub-step 聚合以及 Row Scan Metrics。"
          actions={renderRefreshButton("parameters", "刷新参数趋势", () => loadParameters())}
        />
        <Card>
          <CardContent className="space-y-4 pt-6">
            <Field label="选择参数">
              <ChipToggleGroup options={parameterDefinitions} selected={selectedParameters} onToggle={toggleParameter} />
            </Field>
            <Field label="趋势图单位">
              <Select value={parameterUnit} onChange={(event) => setParameterUnit(event.target.value)}>
                {durationUnits.map((unit) => (
                  <option key={unit.value} value={unit.value}>
                    {unit.label}
                  </option>
                ))}
              </Select>
            </Field>
          </CardContent>
        </Card>
        {selectedParameters.map((name) => {
          const rows = safeArray(safeObject(parameterBundle.parameterSeries)[name]);
          const firstRow = rows[0] || {};
          const thresholds = [];
          if (firstRow.threshold_value !== undefined && firstRow.threshold_value !== null) {
            thresholds.push({ label: "阈值", value: Number(firstRow.threshold_value), color: "#D94841", dash: "6 6" });
          }
          if (firstRow.expected_value !== undefined && firstRow.expected_value !== null) {
            thresholds.push({ label: "期望值", value: Number(firstRow.expected_value), color: "#1E8E6A", dash: "4 6" });
          }
          return (
            <SimpleLineChart
              key={name}
              title={`${name} 趋势`}
              rows={rows}
              xKey={name.startsWith("temperature_") ? "start_time" : "cycle"}
              yKey="duration_value"
              thresholdLines={thresholds}
            />
          );
        })}
        <SimpleLineChart title="Sub-step Cycle Mean" rows={safeArray(parameterBundle.substepSeries)} xKey="cycle" yKey="duration_value" seriesKey="sub_step" />
        <SimpleLineChart title="Row Scan Metrics 各阶段趋势" rows={safeArray(parameterBundle.rowScanMetrics)} xKey="cycle" yKey="duration_value" seriesKey="metric_stage" />
        <label className="flex items-center gap-2 text-sm text-[var(--foreground)]">
          <input type="checkbox" checked={parameterShowMetricTable} onChange={(event) => setParameterShowMetricTable(event.target.checked)} />
          显示 metrics 表格明细
        </label>
        {parameterShowMetricTable ? <DataTable title="Row Scan Metrics 明细" rows={safeArray(parameterBundle.rowScanMetrics)} /> : null}
      </div>
    );
  }

  function renderUnifiedSolutionSubmissionForm({
    title,
    description,
    showPrefillButton = false,
    submitLabel,
  }: {
    title: string;
    description: string;
    showPrefillButton?: boolean;
    submitLabel: string;
  }) {
    return (
      <div className="space-y-4">
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="space-y-2">
              <p className="text-sm font-medium text-[var(--foreground)]">{title}</p>
              <p className="text-sm leading-6 text-[var(--muted-foreground)]">{description}</p>
            </div>
            <InfoTileGrid
              columns={4}
              items={[
                { label: "错误码分配", value: "系统自动分配", note: "不再允许手动填写错误码" },
                { label: "统一落库", value: "solution_records", note: "与综合诊断审核、方案中心共用同一数据库" },
                { label: "当前任务", value: selectedTaskUuid || "-", note: "可为空，支持纯经验方案录入" },
                { label: "当前签名", value: selectedErrorSignature || "-", note: "如已选错误簇，可用于补全上下文" },
              ]}
            />
          </CardContent>
        </Card>
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
            <Field label="模块">
              <Select value={hubForm.module} onChange={(event) => setHubForm((current) => ({ ...current, module: event.target.value }))}>
                <option value="">请选择模块</option>
                {modules.map((module) => (
                  <option key={String(module.id)} value={String(module.module_key)}>
                    {`${module.display_name} | ${module.prefix}`}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="错误名">
              <Input value={hubForm.error_name} onChange={(event) => setHubForm((current) => ({ ...current, error_name: event.target.value }))} />
            </Field>
            <div className="lg:col-span-2">
              <Field label="任务簇">
                <ChipToggleGroup options={taskClusters.map((item) => String(item.display_name || item.cluster_key))} selected={hubSelectedClusters} onToggle={toggleTaskCluster} />
              </Field>
            </div>
            <Field label="新增任务簇候选">
              <Input value={hubForm.new_cluster} onChange={(event) => setHubForm((current) => ({ ...current, new_cluster: event.target.value }))} />
            </Field>
            <Field label="关联 task_uuid">
              <Input value={hubForm.task_uuid} onChange={(event) => setHubForm((current) => ({ ...current, task_uuid: event.target.value }))} />
            </Field>
            <div className="lg:col-span-2">
              <Field label="现象描述 / message">
                <Textarea value={hubForm.message} onChange={(event) => setHubForm((current) => ({ ...current, message: event.target.value }))} />
              </Field>
            </div>
            <Field label="message 关键词">
              <Input value={hubForm.message_keywords} onChange={(event) => setHubForm((current) => ({ ...current, message_keywords: event.target.value }))} />
            </Field>
            <Field label="标签">
              <Input value={hubForm.tags} onChange={(event) => setHubForm((current) => ({ ...current, tags: event.target.value }))} />
            </Field>
            <div className="lg:col-span-2">
              <Field label="根因分析">
                <Textarea value={hubForm.root_cause_analysis} onChange={(event) => setHubForm((current) => ({ ...current, root_cause_analysis: event.target.value }))} />
              </Field>
            </div>
            <div className="lg:col-span-2">
              <Field label="已验证解决方案">
                <Textarea value={hubForm.verified_solution} onChange={(event) => setHubForm((current) => ({ ...current, verified_solution: event.target.value }))} />
              </Field>
            </div>
            <div className="lg:col-span-2">
              <Field label="临时绕过方案">
                <Textarea value={hubForm.workaround} onChange={(event) => setHubForm((current) => ({ ...current, workaround: event.target.value }))} />
              </Field>
            </div>
            <div className="lg:col-span-2">
              <Field label="触发场景 / 问题簇">
                <Textarea value={hubForm.trigger_scenario} onChange={(event) => setHubForm((current) => ({ ...current, trigger_scenario: event.target.value }))} />
              </Field>
            </div>
            <Field label="关联 normalized_signature">
              <Input value={hubForm.normalized_signature} onChange={(event) => setHubForm((current) => ({ ...current, normalized_signature: event.target.value }))} />
            </Field>
          </CardContent>
        </Card>
        <div className="flex flex-wrap gap-3">
          {showPrefillButton ? (
            <Button variant="secondary" onClick={handlePrefillSolutionEntry}>
              从当前诊断带入
            </Button>
          ) : null}
          <Button onClick={() => void handleSubmitSolutionHub()}>{submitLabel}</Button>
        </div>
      </div>
    );
  }

  function renderLlmPage() {
    const historyTokenSummary = safeObject(selectedHistoryRow?.token_summary);

    return (
      <div className="space-y-6">
        <SectionTitle
          title="LLM 诊断"
          description="结合日志、上下文、源码片段、历史案例和分析深度策略执行综合诊断。"
          actions={renderRefreshButton("llm", "刷新诊断数据", () => loadLlm())}
        />
        <details className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
          <summary className="cursor-pointer text-sm font-medium text-[var(--foreground)]">
            当前策略与开关
          </summary>
          <div className="mt-4 space-y-4">
            <InfoTileGrid
              columns={4}
              items={[
                { label: "LLM 启用", value: safeObject(llmBundle.config).llm?.enabled, note: "总开关" },
                { label: "模型", value: safeObject(llmBundle.config).llm?.model || "-", note: "当前诊断模型" },
                { label: "诊断超时(秒)", value: safeObject(llmBundle.config).llm?.timeout_seconds || "-", note: "后端配置" },
                { label: "可用深度档位", value: Object.keys(llmStrategyMap).length, note: "analysis_depths" },
              ]}
            />
            <DetailListCard
              title="当前配置摘要"
              description="这里展示诊断开关、模型和方案库策略的结构化摘要。"
              value={{ llm: safeObject(llmBundle.config).llm, solution_repository: repoConfig }}
            />
          </div>
        </details>
        <TabBar
          tabs={[
            { key: "history", label: "历史诊断" },
            { key: "diagnose", label: "综合诊断" },
            { key: "solutionEntry", label: "已有方案录入" },
            { key: "repo", label: "解决方案库" },
            { key: "review", label: "审核中心" },
          ]}
          active={llmTab}
          onChange={setLlmTab}
        />
        {llmTab === "history" ? (
          <div className="space-y-4">
            <DataTable title="历史诊断列表" rows={historyRows} maxHeight={320} />
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="按错误签名过滤">
                <Select value={llmHistorySignatureFilter} onChange={(event) => setLlmHistorySignatureFilter(event.target.value)}>
                  <option value="">全部</option>
                  {uniqueHistorySignatures.map((value) => (
                    <option key={value} value={value}>
                      {value}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="选择历史结果">
                <Select value={selectedHistoryIndex} onChange={(event) => setSelectedHistoryIndex(event.target.value)}>
                  {filteredHistoryRows.map((row, index) => (
                    <option key={`${row.normalized_signature}-${index}`} value={String(index)}>
                      {`${index + 1}. ${row.normalized_signature || ""} | ${row.analysis_stage || "-"} | ${row.created_at || "-"}`}
                    </option>
                  ))}
                </Select>
              </Field>
            </div>
            {selectedHistoryRow ? (
              <>
                {selectedHistoryRow.chinese_summary ? (
                  <Card>
                    <CardContent className="pt-6">
                      <p className="text-sm leading-7 text-[var(--foreground)]">
                        {String(selectedHistoryRow.chinese_summary)}
                      </p>
                    </CardContent>
                  </Card>
                ) : null}
                <InfoTileGrid
                  columns={4}
                  items={[
                    { label: "分析深度", value: selectedHistoryRow.analysis_stage || "-" },
                    { label: "Prompt 版本", value: selectedHistoryRow.prompt_version || "-" },
                    { label: "LLM 状态", value: selectedHistoryRow.llm_status || "-" },
                    { label: "总 Token", value: historyTokenSummary.final_total_tokens || "-", note: "来自 token_summary" },
                  ]}
                />
                <TabBar
                  tabs={[
                    { key: "structured", label: "结构化结果" },
                    { key: "context", label: "上下文摘要" },
                    { key: "source", label: "源码片段" },
                    { key: "cases", label: "相似案例" },
                    { key: "full", label: "完整片段" },
                  ]}
                  active={historyDetailTab}
                  onChange={setHistoryDetailTab}
                />
                {historyDetailTab === "structured" ? (
                  <JsonPreview
                    value={
                      safeObject(selectedHistoryRow.response_payload).structured_result ||
                      selectedHistoryRow.response_payload ||
                      {}
                    }
                  />
                ) : null}
                {historyDetailTab === "context" ? <DetailListCard value={selectedHistoryRow.context_summary || {}} /> : null}
                {historyDetailTab === "source" ? <JsonPreview value={selectedHistoryRow.source_context_snippets || []} /> : null}
                {historyDetailTab === "cases" ? <DetailListCard value={selectedHistoryRow.similar_cases || []} /> : null}
                {historyDetailTab === "full" ? <JsonPreview value={selectedHistoryRow} /> : null}
              </>
            ) : (
              <p className="text-sm text-[var(--muted-foreground)]">当前没有可查看的历史诊断记录。</p>
            )}
          </div>
        ) : llmTab === "diagnose" ? (
          <div className="space-y-6">
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="选择错误簇">
                <Select value={selectedErrorSignature} onChange={(event) => setSelectedErrorSignature(event.target.value)}>
                  <option value="">请选择错误簇</option>
                  {errorItems.map((row) => (
                    <option key={String(row.normalized_signature)} value={String(row.normalized_signature)}>
                      {`${shortText(row.display_signature || row.normalized_signature, 72)} | count=${row.count || 0}`}
                    </option>
                  ))}
                </Select>
              </Field>
              <Field label="分析深度">
                <Select value={llmForm.analysisDepth} onChange={(event) => setLlmForm((current) => ({ ...current, analysisDepth: event.target.value }))}>
                  {Object.keys(llmStrategyMap).length ? Object.keys(llmStrategyMap).map((depth) => (
                    <option key={depth} value={depth}>
                      {depth}
                    </option>
                  )) : (
                    <>
                      <option value="low">low</option>
                      <option value="medium">medium</option>
                      <option value="high">high</option>
                    </>
                  )}
                </Select>
              </Field>
            </div>
            {selectedError ? (
              <InfoTileGrid
                columns={4}
                items={[
                  { label: "错误签名", value: shortText(selectedError.display_signature || selectedError.normalized_signature, 48), note: "当前选中的错误簇" },
                  { label: "错误次数", value: selectedError.count || 0 },
                  { label: "错误家族", value: selectedError.error_family_display || selectedError.error_family || "-" },
                  { label: "代表消息", value: shortText(selectedError.representative_message || "", 48) },
                ]}
              />
            ) : null}
            <InfoTileGrid
              columns={4}
              items={[
                { label: "上下文预算", value: activeStrategy.token_budget || "-", note: activeStrategy.description || "" },
                { label: "历史案例数", value: activeStrategy.history_case_limit || "-" },
                { label: "源码片段数", value: activeStrategy.max_source_snippets || "-" },
                { label: "推理粒度", value: activeStrategy.reasoning_granularity || "-" },
              ]}
            />
            <Card>
              <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
                <Field label="所属模块">
                  <Select value={llmForm.module} onChange={(event) => setLlmForm((current) => ({ ...current, module: event.target.value }))}>
                    <option value="">请选择模块</option>
                    {llmModuleOptions.map((value) => (
                      <option key={value} value={value}>
                        {value}
                      </option>
                    ))}
                  </Select>
                </Field>
                <Field label="子模块">
                  <Input value={llmForm.submodule} onChange={(event) => setLlmForm((current) => ({ ...current, submodule: event.target.value }))} />
                </Field>
                <div className="lg:col-span-2">
                  <Field label="触发场景">
                    <Textarea value={llmForm.triggerScenario} onChange={(event) => setLlmForm((current) => ({ ...current, triggerScenario: event.target.value }))} />
                  </Field>
                </div>
                <Field label="操作路径 / 前置动作">
                  <Textarea value={llmForm.operationPath} onChange={(event) => setLlmForm((current) => ({ ...current, operationPath: event.target.value }))} />
                </Field>
                <Field label="客户现象描述">
                  <Textarea value={llmForm.customerSymptom} onChange={(event) => setLlmForm((current) => ({ ...current, customerSymptom: event.target.value }))} />
                </Field>
                <Field label="环境信息">
                  <Textarea value={llmForm.environmentInfo} onChange={(event) => setLlmForm((current) => ({ ...current, environmentInfo: event.target.value }))} />
                </Field>
                <Field label="复现步骤">
                  <Textarea value={llmForm.reproductionSteps} onChange={(event) => setLlmForm((current) => ({ ...current, reproductionSteps: event.target.value }))} />
                </Field>
                <div className="lg:col-span-2">
                  <Field label="源码补充说明">
                    <Textarea value={llmForm.sourceNotes} onChange={(event) => setLlmForm((current) => ({ ...current, sourceNotes: event.target.value }))} />
                  </Field>
                </div>
                <Field label="上传相关源码">
                  <Input type="file" multiple onChange={(event) => setLlmSourceFiles(Array.from(event.target.files || []))} />
                </Field>
                <Field label="前端等待超时(秒)">
                  <Input value={diagnoseTimeout} onChange={(event) => setDiagnoseTimeout(event.target.value)} />
                </Field>
                <div className="lg:col-span-2 flex flex-wrap gap-4">
                  <label className="flex items-center gap-2 text-sm text-[var(--foreground)]">
                    <input
                      type="checkbox"
                      checked={llmForm.force}
                      onChange={(event) => setLlmForm((current) => ({ ...current, force: event.target.checked }))}
                    />
                    忽略缓存，重新调用 LLM
                  </label>
                </div>
              </CardContent>
            </Card>
            <div className="flex flex-wrap gap-3">
              <Button variant="secondary" onClick={() => void handleFindSimilarCases()}>
                <Search className="h-4 w-4" />
                检索相似案例
              </Button>
              <Button onClick={() => void handleRunDiagnosis()}>
                <Send className="h-4 w-4" />
                开始综合诊断
              </Button>
            </div>
            {safeArray(llmBundle.similarCases).length ? <DataTable title="相似案例推荐" rows={safeArray(llmBundle.similarCases)} maxHeight={260} /> : null}
            {Object.keys(llmLatestDiagnosis).length ? (
              <>
                <InfoTileGrid columns={4} items={[{ label: "分析深度", value: llmLatestDiagnosis.analysis_stage || "-" }, { label: "缓存命中", value: llmLatestDiagnosis.from_cache ? "是" : "否" }, { label: "LLM 状态", value: llmLatestDiagnosis.llm_status || "-" }, { label: "总 Token", value: safeObject(llmLatestDiagnosis.token_summary).final_total_tokens || "-" }]} />
                <TabBar tabs={[{ key: "structured", label: "结构化结果" }, { key: "context", label: "日志与证据摘要" }, { key: "source", label: "源码片段" }, { key: "cases", label: "相似案例" }, { key: "payload", label: "请求 / 响应" }]} active={diagnosisResultTab} onChange={setDiagnosisResultTab} />
                {diagnosisResultTab === "structured" ? <JsonPreview title="结构化结果" value={llmLatestDiagnosis.structured_result || {}} /> : null}
                 {diagnosisResultTab === "context" ? <DetailListCard title="日志与证据摘要" value={llmLatestDiagnosis.context_summary || {}} /> : null}
                {diagnosisResultTab === "source" ? <JsonPreview title="源码片段" value={llmLatestDiagnosis.source_context_snippets || []} /> : null}
                 {diagnosisResultTab === "cases" ? <DetailListCard title="相似案例" value={llmLatestDiagnosis.similar_cases || []} /> : null}
                {diagnosisResultTab === "payload" ? <JsonPreview title="请求 / 响应" value={{ request_payload: llmLatestDiagnosis.request_payload || {}, response_payload: llmLatestDiagnosis.response_payload || {} }} /> : null}
              </>
            ) : null}
            {Object.keys(llmLatestDiagnosis).length ? <Button onClick={() => void handleSubmitDiagnosisReview()}>提交入库审核</Button> : null}
            {Object.keys(llmLatestReview).length ? <DetailListCard title="最新审核提交结果" value={llmLatestReview} /> : null}
          </div>
        ) : llmTab === "solutionEntry" ? (
          renderUnifiedSolutionSubmissionForm({
            title: "已有方案录入",
            description: "这个入口和方案库中心使用同一套解决方案数据库与审核链，错误码会在入库时自动分配。",
            showPrefillButton: true,
            submitLabel: isReviewer ? "直接写入方案库" : "提交到审核流",
          })
        ) : llmTab === "repo" ? (
          <div className="space-y-4">
            <DataTable title="解决方案库记录" rows={safeArray(hubBundle.records?.items)} maxHeight={320} />
            <Field label="选择记录">
              <Select value={editingRecordId} onChange={(event) => setEditingRecordId(event.target.value)}>
                <option value="">请选择</option>
                {safeArray(hubBundle.records?.items).map((item) => (
                  <option key={String(item.id)} value={String(item.id)}>
                    {`${item.id} | ${item.error_name || ""} | ${item.module || ""}`}
                  </option>
                ))}
              </Select>
            </Field>
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="编辑根因分析"><Textarea value={editingRecordDraft.root_cause_analysis} onChange={(event) => setEditingRecordDraft((current) => ({ ...current, root_cause_analysis: event.target.value }))} /></Field>
              <Field label="编辑已验证解决方案"><Textarea value={editingRecordDraft.verified_solution} onChange={(event) => setEditingRecordDraft((current) => ({ ...current, verified_solution: event.target.value }))} /></Field>
              <div className="lg:col-span-2"><Field label="编辑临时绕过方案"><Textarea value={editingRecordDraft.workaround} onChange={(event) => setEditingRecordDraft((current) => ({ ...current, workaround: event.target.value }))} /></Field></div>
            </div>
            {selectedRepositoryRecord ? <DetailListCard value={selectedRepositoryRecord} /> : null}
            <Button onClick={() => void handleSaveRepositoryRecord()}>保存当前记录编辑</Button>
          </div>
        ) : (
          <div className="space-y-4">
            <DataTable title="审核列表" rows={safeArray(hubBundle.reviews?.items)} maxHeight={300} />
            <Field label="选择审核记录">
              <Select value={selectedReviewId} onChange={(event) => setSelectedReviewId(event.target.value)}>
                <option value="">请选择</option>
                {safeArray(hubBundle.reviews?.items).map((item) => (
                  <option key={String(item.id)} value={String(item.id)}>
                    {`${item.id} | ${item.review_status || ""} | ${item.module || ""} | ${item.normalized_signature || ""}`}
                  </option>
                ))}
              </Select>
            </Field>
            {selectedHubReview ? <DetailListCard value={selectedHubReview} /> : null}
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="人工复核人"><Input value={manualReviewer} onChange={(event) => setManualReviewer(event.target.value)} /></Field>
              <Field label="审核意见"><Textarea value={manualReviewNotes} onChange={(event) => setManualReviewNotes(event.target.value)} /></Field>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void handleManualSolutionReview("approved")}>人工通过</Button>
              <Button variant="secondary" onClick={() => void handleManualSolutionReview("needs_revision")}>退回修改</Button>
              <Button variant="danger" onClick={() => void handleManualSolutionReview("rejected")}>拒绝入库</Button>
            </div>
          </div>
        )}
      </div>
    );
  }

  function renderSolutionHubPage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="方案库中心"
          description="围绕统一解决方案数据库，提供提交、检索、导入导出、智能问答和审核管理。"
          actions={renderRefreshButton("solutionHub", "刷新方案中心", () => loadSolutionHub())}
        />
        <TabBar
          tabs={[
            { key: "submit", label: "方案提交" },
            { key: "query", label: "方案检索" },
            { key: "review", label: "方案审核" },
            { key: "taxonomy", label: "任务簇与模块" },
          ]}
          active={solutionTab}
          onChange={setSolutionTab}
        />
        {solutionTab === "submit" ? (
          renderUnifiedSolutionSubmissionForm({
            title: "统一方案提交",
            description: "无论来自人工经验、综合诊断还是历史问题复盘，都会汇总到同一个解决方案数据库中。",
            submitLabel: isReviewer ? "直接写入方案库" : "提交到审核流",
          })
        ) : solutionTab === "query" ? (
          <div className="space-y-4">
            <Card>
              <CardContent className="grid gap-4 pt-6 lg:grid-cols-[1fr_1fr_1fr_auto]">
                <Field label="全文检索"><Input value={hubQuery.search} onChange={(event) => setHubQuery((current) => ({ ...current, search: event.target.value }))} /></Field>
                <Field label="模块过滤"><Select value={hubQuery.module} onChange={(event) => setHubQuery((current) => ({ ...current, module: event.target.value }))}><option value="">全部</option>{modules.map((item) => <option key={String(item.id)} value={String(item.module_key)}>{String(item.module_key)}</option>)}</Select></Field>
                <Field label="审核状态"><Select value={hubQuery.review_status} onChange={(event) => setHubQuery((current) => ({ ...current, review_status: event.target.value }))}><option value="">全部</option><option value="approved">approved</option><option value="pending_review">pending_review</option><option value="needs_revision">needs_revision</option><option value="rejected">rejected</option></Select></Field>
                <div className="flex items-end">{renderRefreshButton("solutionSearch", "按条件检索", () => loadSolutionHub())}</div>
              </CardContent>
            </Card>
            <Card>
              <CardContent className="space-y-4 pt-6">
                <div className="grid gap-4 lg:grid-cols-[1fr_auto]">
                  <Field label="向方案库提问" hint="输入现象、问题或处理诉求，大模型会先检索方案库再给出回答。">
                    <Textarea value={hubAssistantQuestion} onChange={(event) => setHubAssistantQuestion(event.target.value)} />
                  </Field>
                  <div className="flex items-end">
                    <Button className="w-full" onClick={() => void handleAskSolutionRepository()}>
                      方案库问答
                    </Button>
                  </div>
                </div>
                {hubAssistantResult ? (
                  <>
                    <DetailListCard title="问答结果" value={hubAssistantResult} />
                    {safeArray(hubAssistantResult.matches).length ? (
                      <DataTable title="命中的方案记录" rows={safeArray(hubAssistantResult.matches)} maxHeight={260} />
                    ) : null}
                  </>
                ) : null}
              </CardContent>
            </Card>
            <Card>
              <CardContent className="grid gap-4 pt-6 lg:grid-cols-[1fr_auto_auto_auto]">
                <Field label="导入方案库" hint="支持导入 JSON、CSV、XLSX；导入时会优先匹配已有记录，新增记录可保留原错误码。">
                  <Input type="file" accept=".json,.csv,.xlsx" onChange={(event) => setHubImportFile(event.target.files?.[0] || null)} />
                </Field>
                <div className="flex items-end">
                  <Button className="w-full" onClick={() => void handleImportSolutionRepository()}>
                    导入方案库
                  </Button>
                </div>
                <div className="flex items-end">
                  <Button variant="secondary" asChild>
                    <a href={buildApiUrl(apiBase, "/solution-repository/export", { access_token: token, format: "json" })} target="_blank" rel="noreferrer">
                      导出 JSON
                    </a>
                  </Button>
                </div>
                <div className="flex items-end">
                  <Button variant="secondary" asChild>
                    <a href={buildApiUrl(apiBase, "/solution-repository/export", { access_token: token, format: "xlsx" })} target="_blank" rel="noreferrer">
                      导出 Excel
                    </a>
                  </Button>
                </div>
              </CardContent>
            </Card>
            {hubImportResult ? <DetailListCard title="导入摘要" value={hubImportResult} /> : null}
            <DataTable
              title="方案记录"
              rows={safeArray(hubBundle.records?.items)}
              selectedRowIndex={safeArray(hubBundle.records?.items).findIndex((item) => String(item.id) === editingRecordId)}
              onRowClick={(row) => setEditingRecordId(String(row.id || ""))}
              maxHeight={360}
            />
            {selectedRepositoryRecord ? <DetailListCard title="当前选中方案" value={selectedRepositoryRecord} /> : null}
          </div>
        ) : solutionTab === "review" ? (
          <div className="space-y-4">
            <DataTable title="审核中心" rows={safeArray(hubBundle.reviews?.items)} maxHeight={320} />
            {isReviewer ? (
              <>
                <Field label="选择审核记录">
                  <Select value={selectedReviewId} onChange={(event) => setSelectedReviewId(event.target.value)}>
                    <option value="">请选择</option>
                    {safeArray(hubBundle.reviews?.items).map((item) => (
                      <option key={String(item.id)} value={String(item.id)}>
                        {`${item.id} | ${item.review_status || ""} | ${item.module || ""} | ${item.created_by || ""}`}
                      </option>
                    ))}
                  </Select>
                </Field>
                {selectedHubReview ? <DetailListCard value={selectedHubReview} /> : null}
                <Field label="审核意见"><Textarea value={hubReviewNotes} onChange={(event) => setHubReviewNotes(event.target.value)} /></Field>
                <div className="flex flex-wrap gap-3">
                  <Button onClick={() => void handleManualSolutionReview("approved")}>通过</Button>
                  <Button variant="secondary" onClick={() => void handleManualSolutionReview("needs_revision")}>退回修改</Button>
                  <Button variant="danger" onClick={() => void handleManualSolutionReview("rejected")}>拒绝</Button>
                </div>
              </>
            ) : null}
          </div>
        ) : (
          <div className="space-y-4">
            <DataTable title="任务簇" rows={safeArray(hubBundle.taskClusters)} maxHeight={260} />
            <Card>
              <CardContent className="grid gap-4 pt-6 lg:grid-cols-2">
                <Field label="新任务簇名称"><Input value={newClusterDraft.name} onChange={(event) => setNewClusterDraft((current) => ({ ...current, name: event.target.value }))} /></Field>
                <Field label="任务簇说明"><Textarea value={newClusterDraft.description} onChange={(event) => setNewClusterDraft((current) => ({ ...current, description: event.target.value }))} /></Field>
              </CardContent>
            </Card>
            <Button onClick={() => void handleCreateTaskCluster()}>提交任务簇</Button>
            {isReviewer ? (
              <>
                <Field label="审核任务簇">
                  <Select value={selectedClusterId} onChange={(event) => setSelectedClusterId(event.target.value)}>
                    <option value="">请选择</option>
                    {safeArray(hubBundle.taskClusters).map((item) => (
                      <option key={String(item.id)} value={String(item.id)}>
                        {`${item.id} | ${item.display_name || ""} | ${item.review_status || ""}`}
                      </option>
                    ))}
                  </Select>
                </Field>
                {selectedHubCluster ? <DetailListCard value={selectedHubCluster} /> : null}
                <div className="flex flex-wrap gap-3">
                  <Button onClick={() => void handleReviewTaskCluster("approved")}>通过</Button>
                  <Button variant="secondary" onClick={() => void handleReviewTaskCluster("rejected")}>拒绝</Button>
                  <Button variant="danger" onClick={() => void handleReviewTaskCluster("disabled")}>停用</Button>
                </div>
                <DataTable title="模块配置" rows={modules} maxHeight={260} />
                <Card>
                  <CardContent className="grid gap-4 pt-6 lg:grid-cols-3">
                    <Field label="module_key"><Input value={newModuleDraft.module_key} onChange={(event) => setNewModuleDraft((current) => ({ ...current, module_key: event.target.value }))} /></Field>
                    <Field label="display_name"><Input value={newModuleDraft.display_name} onChange={(event) => setNewModuleDraft((current) => ({ ...current, display_name: event.target.value }))} /></Field>
                    <Field label="prefix"><Input value={newModuleDraft.prefix} onChange={(event) => setNewModuleDraft((current) => ({ ...current, prefix: event.target.value }))} /></Field>
                    <div className="lg:col-span-3"><Field label="模块说明"><Textarea value={newModuleDraft.description} onChange={(event) => setNewModuleDraft((current) => ({ ...current, description: event.target.value }))} /></Field></div>
                  </CardContent>
                </Card>
                <Button onClick={() => void handleSaveModuleConfig()}>保存模块配置</Button>
              </>
            ) : null}
          </div>
        )}
      </div>
    );
  }

  function renderFilesPage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="原始文件预览"
          description="查看任务中收录的原始文件列表，并按预览行数查看文件内容。"
          actions={renderRefreshButton("files", "刷新文件列表", () => loadFiles())}
        />
        <PaginationBar
          page={filesPage}
          pageSize={filesPageSize}
          total={Number(filesBundle.list?.total || 0)}
          onPageChange={setFilesPage}
          onPageSizeChange={(value) => {
            setFilesPage(1);
            setFilesPageSize(value);
          }}
        />
        <DataTable title="原始文件列表" rows={safeArray(filesBundle.list?.items)} maxHeight={360} />
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-[1fr_180px_auto]">
            <Field label="选择原始文件">
              <Select value={selectedFilePath} onChange={(event) => setSelectedFilePath(event.target.value)}>
                <option value="">请选择文件</option>
                {safeArray(filesBundle.list?.items).map((row) => (
                  <option key={String(row.relative_path)} value={String(row.relative_path)}>
                    {String(row.relative_path)}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="预览行数">
              <Input value={filePreviewLines} onChange={(event) => setFilePreviewLines(event.target.value)} />
            </Field>
            <div className="flex items-end">
              <Button className="w-full" onClick={() => void loadFiles()}>加载预览</Button>
            </div>
          </CardContent>
        </Card>
        {filesBundle.preview ? (
          <>
            <InfoTileGrid
              columns={4}
              items={[
                { label: "文件", value: filesBundle.preview.relative_path || "-" },
                { label: "类型", value: filesBundle.preview.mime_type || "unknown" },
                { label: "编码", value: filesBundle.preview.encoding || "unknown" },
                { label: "预览行数", value: filesBundle.preview.line_count || 0 },
              ]}
            />
            <LinePreviewCard
              text={safeArray(filesBundle.preview.preview).join("\n")}
              title="文件预览"
              description="按行查看原始日志内容，便于与解析结果对照。"
              maxHeight={520}
            />
          </>
        ) : null}
      </div>
    );
  }

  function renderUnknownPage() {
    return (
      <div className="space-y-6">
        <SectionTitle
          title="未知日志待标注池"
          description="优先按出现次数筛选，再查看代表样本、审核历史、尝试过的解析器和上下文样本。"
          actions={renderRefreshButton("unknown", "刷新未知日志池", () => loadUnknown())}
        />
        <Card>
          <CardContent className="grid gap-4 pt-6 lg:grid-cols-3">
            <Field label="最小出现次数"><Input value={unknownFilter.min_occurrence} onChange={(event) => setUnknownFilter((current) => ({ ...current, min_occurrence: event.target.value }))} /></Field>
            <Field label="展示条数"><Input value={unknownFilter.limit} onChange={(event) => setUnknownFilter((current) => ({ ...current, limit: event.target.value }))} /></Field>
            <Field label="审核状态过滤"><Select value={unknownFilter.review_status} onChange={(event) => setUnknownFilter((current) => ({ ...current, review_status: event.target.value }))}><option value="">全部</option><option value="pending_review">pending_review</option><option value="submitted_for_review">submitted_for_review</option><option value="approved">approved</option><option value="rejected">rejected</option><option value="ignored">ignored</option></Select></Field>
          </CardContent>
        </Card>
        <DataTable title="未知日志簇" rows={safeArray(unknownBundle.items)} maxHeight={320} />
        <Field label="选择未知日志簇">
          <Select value={selectedUnknownSignature} onChange={(event) => setSelectedUnknownSignature(event.target.value)}>
            <option value="">请选择</option>
            {safeArray(unknownBundle.items).map((item) => (
              <option key={String(item.signature)} value={String(item.signature)}>
                {String(item.signature)}
              </option>
            ))}
          </Select>
        </Field>
        {selectedUnknownCluster ? (
          <>
            <InfoTileGrid columns={3} items={[{ label: "当前状态", value: selectedUnknownCluster.review_status || "pending_review" }, { label: "出现次数", value: selectedUnknownCluster.occurrence_count || 0 }, { label: "源文件数", value: Object.keys(safeObject(selectedUnknownCluster.source_files)).length }]} />
             <LinePreviewCard
               text={String(selectedUnknownCluster.representative_text || "")}
               title="代表性样本"
               description="优先查看这段代表文本，再决定是否通过、忽略或拒绝。"
             />
            <div className="grid gap-4 lg:grid-cols-2">
              <Field label="审核人"><Input value={unknownReviewer} onChange={(event) => setUnknownReviewer(event.target.value)} /></Field>
              <Field label="审核备注"><Textarea value={unknownReviewNotes} onChange={(event) => setUnknownReviewNotes(event.target.value)} /></Field>
            </div>
            <div className="flex flex-wrap gap-3">
              <Button onClick={() => void handleUnknownReview("approved")}>通过</Button>
              <Button variant="secondary" onClick={() => void handleUnknownReview("ignored")}>忽略</Button>
              <Button variant="danger" onClick={() => void handleUnknownReview("rejected")}>拒绝</Button>
            </div>
            {safeArray(selectedUnknownCluster.review_history).length ? <DataTable title="审核历史" rows={safeArray(selectedUnknownCluster.review_history)} maxHeight={220} /> : null}
            <div className="grid gap-6 xl:grid-cols-2">
               <DataTable
                 title="尝试过的 Parsers"
                 rows={safeArray(selectedUnknownCluster.attempted_parsers || []).map((item, index) => ({
                   序号: index + 1,
                   parser: typeof item === "object" ? JSON.stringify(item) : String(item),
                 }))}
                 maxHeight={240}
               />
               <DataTable
                 title="尝试过的 Rules"
                 rows={safeArray(selectedUnknownCluster.attempted_rules || []).map((item, index) => ({
                   序号: index + 1,
                   rule: typeof item === "object" ? JSON.stringify(item) : String(item),
                 }))}
                 maxHeight={240}
               />
             </div>
             {safeArray(selectedUnknownCluster.context_examples).map((item, index) => (
              <details key={`context-example-${index}`} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4">
                <summary className="cursor-pointer text-sm font-medium text-[var(--foreground)]">
                  {`样本 ${index + 1} | ${item.source_file || "-"} | line ${item.line_no || "-"}`}
                </summary>
                <div className="mt-4">
                  <DetailListCard value={item} />
                </div>
              </details>
            ))}
          </>
        ) : null}
      </div>
    );
  }

  function renderRulesPage() {
    const currentLocalNew =
      localNewSuggestions.find((item) => String(item.suggestion_id) === selectedLocalNewSuggestionId) ||
      localNewSuggestions[0] ||
      null;
    const currentLocalFix =
      localFixSuggestions.find((item) => String(item.suggestion_id) === selectedLocalFixSuggestionId) ||
      localFixSuggestions[0] ||
      null;
    const currentLlmNew =
      llmNewSuggestions.find((item) => String(item.suggestion_id) === selectedLlmNewSuggestionId) ||
      llmNewSuggestions[0] ||
      null;
    const currentLlmFix =
      llmFixSuggestions.find((item) => String(item.suggestion_id) === selectedLlmFixSuggestionId) ||
      llmFixSuggestions[0] ||
      null;

    return (
      <div className="space-y-6">
        <SectionTitle
          title="规则建议审核视图"
          description="先看本地规则建议，再按需触发 LLM 候选建议；所有建议都只进入审核流，不会直接改生产规则。"
          actions={
            <div className="flex flex-wrap gap-3">
              {renderRefreshButton("rulesLocal", "刷新本地建议", () => loadRules(false))}
              <Button
                disabled={isRefreshing("rulesLLM")}
                onClick={() => void runRefreshAction("rulesLLM", () => loadRules(true))}
              >
                <WandSparkles className={cn("h-4 w-4", isRefreshing("rulesLLM") ? "animate-spin" : "")} />
                生成 / 刷新 LLM 建议
              </Button>
            </div>
          }
        />
        <Card>
          <CardContent className="space-y-4 pt-6">
            <label className="flex items-center gap-2 text-sm text-[var(--foreground)]">
              <input type="checkbox" checked={ruleLlmEnabled} onChange={(event) => setRuleLlmEnabled(event.target.checked)} />
              启用 LLM 规则建议
            </label>
            <label className="flex items-center gap-2 text-sm text-[var(--foreground)]">
              <input type="checkbox" checked={ruleForceRefresh} onChange={(event) => setRuleForceRefresh(event.target.checked)} />
              忽略 LLM 预览缓存并重新生成
            </label>
            <Field label="送入 LLM 的未知日志簇">
              <ChipToggleGroup options={safeArray(rulesBundle.unknownPool?.items).map((item) => String(item.signature))} selected={selectedRuleSignatures} onToggle={toggleRuleSignature} />
            </Field>
          </CardContent>
        </Card>
        <InfoTileGrid columns={4} items={[{ label: "未知簇总数", value: safeObject(localPreview.summary).unknown_clusters_total || 0 }, { label: "反馈记录总数", value: safeObject(localPreview.summary).feedback_records_total || 0 }, { label: "新规则建议", value: safeObject(localPreview.summary).new_rule_suggestions || 0 }, { label: "修正规则建议", value: safeObject(localPreview.summary).rule_fix_suggestions || 0 }]} />
        <TabBar tabs={[{ key: "localNew", label: "本地新规则建议" }, { key: "localFix", label: "本地修正规则建议" }, { key: "llmNew", label: "LLM 新规则建议" }, { key: "llmFix", label: "LLM 修正规则建议" }, { key: "patterns", label: "高频误判模式" }, { key: "yaml", label: "YAML 候选片段" }, { key: "reviews", label: "审核记录" }, { key: "files", label: "已写入建议文件" }, { key: "payload", label: "LLM 请求 / 响应" }]} active={rulesTab} onChange={setRulesTab} />
        {rulesTab === "localNew" ? <><DataTable title="本地新规则建议" rows={localNewSuggestions} maxHeight={320} /><Field label="选择本地新规则建议"><Select value={selectedLocalNewSuggestionId} onChange={(event) => setSelectedLocalNewSuggestionId(event.target.value)}><option value="">自动选择首条</option>{localNewSuggestions.map((item) => <option key={String(item.suggestion_id)} value={String(item.suggestion_id)}>{String(item.suggestion_id)}</option>)}</Select></Field>{currentLocalNew ? <DetailListCard value={currentLocalNew} /> : null}{currentLocalNew ? <div className="flex flex-wrap gap-3"><Button onClick={() => void handleRuleReview("approved", String(currentLocalNew.suggestion_id || ""))}>通过</Button><Button variant="secondary" onClick={() => void handleRuleReview("needs_revision", String(currentLocalNew.suggestion_id || ""))}>退回修改</Button><Button variant="danger" onClick={() => void handleRuleReview("rejected", String(currentLocalNew.suggestion_id || ""))}>拒绝</Button></div> : null}</> : null}
        {rulesTab === "localFix" ? <><DataTable title="本地修正规则建议" rows={localFixSuggestions} maxHeight={320} /><Field label="选择本地修正规则建议"><Select value={selectedLocalFixSuggestionId} onChange={(event) => setSelectedLocalFixSuggestionId(event.target.value)}><option value="">自动选择首条</option>{localFixSuggestions.map((item) => <option key={String(item.suggestion_id)} value={String(item.suggestion_id)}>{String(item.suggestion_id)}</option>)}</Select></Field>{currentLocalFix ? <DetailListCard value={currentLocalFix} /> : null}{currentLocalFix ? <div className="flex flex-wrap gap-3"><Button onClick={() => void handleRuleReview("approved", String(currentLocalFix.suggestion_id || ""))}>通过</Button><Button variant="secondary" onClick={() => void handleRuleReview("needs_revision", String(currentLocalFix.suggestion_id || ""))}>退回修改</Button><Button variant="danger" onClick={() => void handleRuleReview("rejected", String(currentLocalFix.suggestion_id || ""))}>拒绝</Button></div> : null}</> : null}
        {rulesTab === "llmNew" ? <><DataTable title="LLM 新规则建议" rows={llmNewSuggestions} maxHeight={320} /><Field label="选择 LLM 新规则建议"><Select value={selectedLlmNewSuggestionId} onChange={(event) => setSelectedLlmNewSuggestionId(event.target.value)}><option value="">自动选择首条</option>{llmNewSuggestions.map((item) => <option key={String(item.suggestion_id)} value={String(item.suggestion_id)}>{String(item.suggestion_id)}</option>)}</Select></Field>{currentLlmNew ? <DetailListCard value={currentLlmNew} /> : null}{currentLlmNew ? <div className="flex flex-wrap gap-3"><Button onClick={() => void handleRuleReview("approved", String(currentLlmNew.suggestion_id || ""))}>通过</Button><Button variant="secondary" onClick={() => void handleRuleReview("needs_revision", String(currentLlmNew.suggestion_id || ""))}>退回修改</Button><Button variant="danger" onClick={() => void handleRuleReview("rejected", String(currentLlmNew.suggestion_id || ""))}>拒绝</Button></div> : null}</> : null}
        {rulesTab === "llmFix" ? <><DataTable title="LLM 修正规则建议" rows={llmFixSuggestions} maxHeight={320} /><Field label="选择 LLM 修正规则建议"><Select value={selectedLlmFixSuggestionId} onChange={(event) => setSelectedLlmFixSuggestionId(event.target.value)}><option value="">自动选择首条</option>{llmFixSuggestions.map((item) => <option key={String(item.suggestion_id)} value={String(item.suggestion_id)}>{String(item.suggestion_id)}</option>)}</Select></Field>{currentLlmFix ? <DetailListCard value={currentLlmFix} /> : null}{currentLlmFix ? <div className="flex flex-wrap gap-3"><Button onClick={() => void handleRuleReview("approved", String(currentLlmFix.suggestion_id || ""))}>通过</Button><Button variant="secondary" onClick={() => void handleRuleReview("needs_revision", String(currentLlmFix.suggestion_id || ""))}>退回修改</Button><Button variant="danger" onClick={() => void handleRuleReview("rejected", String(currentLlmFix.suggestion_id || ""))}>拒绝</Button></div> : null}</> : null}
        {rulesTab === "patterns" ? <DataTable title="高频误判模式" rows={[...safeArray(localPreview.high_frequency_misclassified_patterns), ...safeArray(llmResult.high_frequency_misclassified_patterns)]} maxHeight={320} /> : null}
        {rulesTab === "yaml" ? <CodePreview title="YAML 候选片段" code={JSON.stringify(localPreview.parser_rules_yaml_fragment || {}, null, 2)} maxHeight={420} /> : null}
        {rulesTab === "reviews" ? <DataTable title="审核记录" rows={ruleReviews} maxHeight={320} /> : null}
        {rulesTab === "files" ? <><DataTable title="已写入建议文件" rows={ruleFiles} maxHeight={240} /><Field label="选择建议文件"><Select value={selectedRuleFile} onChange={(event) => { const next = event.target.value; setSelectedRuleFile(next); void loadRuleFile(next); }}><option value="">请选择</option>{ruleFiles.map((item) => <option key={String(item.filename)} value={String(item.filename)}>{String(item.filename)}</option>)}</Select></Field>{ruleFileContent ? <CodePreview title={String(ruleFileContent.filename || "建议文件")} code={String(ruleFileContent.content || "")} maxHeight={480} /> : null}</> : null}
        {rulesTab === "payload" ? <JsonPreview title="LLM 请求 / 响应" value={{ request_payload: llmMeta.request_payload || {}, response_payload: llmMeta.response_payload || {} }} /> : null}
        <div className="grid gap-4 lg:grid-cols-[1fr_1fr]">
          <Field label="审核人"><Input value={ruleReviewer} onChange={(event) => setRuleReviewer(event.target.value)} /></Field>
          <Field label="审核备注"><Textarea value={ruleReviewNotes} onChange={(event) => setRuleReviewNotes(event.target.value)} /></Field>
        </div>
      </div>
    );
  }

  function renderConfigPage() {
    const thresholds = safeObject(configBundle.thresholds);
    const parserRules = safeObject(configBundle.parser_rules);
    const errorRules = safeObject(configBundle.error_rules);
    const promptTemplates = safeObject(configBundle.prompt_templates);
    const llmConfig = safeObject(configBundle.llm);
    const repoBundle = safeObject(configBundle.solution_repository);
    const promptVersions = safeObject(promptTemplates.templates);
    const activeLearning = safeObject(parserRules.active_learning);
    const familyRules = safeArray(errorRules.family_rules);
    const moduleTree = safeArray(repoBundle.module_tree);
    const modulePrefixes = safeObject(repoBundle.module_prefixes);
    const envGroupOptions = Array.from(new Set(envItems.map((item) => envGroupFromKey(item.key))));
    const filteredEnvItems = envItems.filter((item) => {
      const keyword = envSearch.trim().toLowerCase();
      const matchesKeyword =
        !keyword ||
        item.key.toLowerCase().includes(keyword) ||
        String(item.value ?? "").toLowerCase().includes(keyword);
      const currentGroup = envGroupFromKey(item.key);
      const matchesGroup = envGroup === "全部" || currentGroup === envGroup;
      return matchesKeyword && matchesGroup;
    });
    const promptVersionRows = Object.entries(promptVersions).map(([version, template]) => {
      const row = safeObject(template);
      return {
        version,
        status: promptTemplates.active_version === version ? "active" : "inactive",
        system_prompt: shortText(row.system_prompt || row.system || row.prompt || "-", 80),
        user_prompt: shortText(row.user_prompt || row.user || row.template || "-", 80),
      };
    });
    const envModifiedCount = envItems.filter((item) => item.is_modified).length;
    const envSensitiveCount = envItems.filter((item) => item.is_sensitive).length;

    return (
      <div className="space-y-6">
        <SectionTitle
          title="配置页面"
          description="集中维护 `.env`、阈值、规则审核策略和 Prompt / 方案库知识配置。"
          actions={renderRefreshButton("config", "刷新配置", () => loadConfig())}
        />
        <TabBar
          tabs={[
            { key: "overview", label: "总览" },
            { key: "env", label: "环境变量" },
            { key: "thresholds", label: "时间与阈值" },
            { key: "rules", label: "异常与审核" },
            { key: "knowledge", label: "Prompt 与方案库" },
          ]}
          active={configTab}
          onChange={setConfigTab}
        />
        {configTab === "overview" ? (
          <InfoTileGrid
            columns={4}
            items={[
              { label: "环境变量总数", value: envItems.length, note: "直接来自当前 `.env` 文件" },
              { label: "已修改环境变量", value: envModifiedCount, note: "与 `.env.example` 默认值不一致" },
              { label: "敏感字段数", value: envSensitiveCount, note: "API Key、密码、Token 等字段" },
              { label: "默认超时阈值", value: thresholds.default_threshold_ms || 0, note: "单位 ms" },
              { label: "LLM 诊断开关", value: llmConfig.enabled, note: "控制诊断页面是否启用大模型分析" },
              { label: "诊断模型", value: llmConfig.model || "-", note: "当前综合诊断模型" },
              { label: "Prompt 版本", value: promptTemplates.active_version || "-", note: "当前生效模板" },
              { label: "解决方案模块", value: moduleTree.length, note: "一级模块数量" },
            ]}
          />
        ) : null}
        {configTab === "env" ? (
          <div className="space-y-4">
            <Card>
              <CardContent className="grid gap-4 pt-6 lg:grid-cols-[1.2fr_260px]">
                <Field label="搜索环境变量">
                  <Input
                    value={envSearch}
                    onChange={(event) => setEnvSearch(event.target.value)}
                    placeholder="按 key 或 value 搜索"
                  />
                </Field>
                <Field label="按分类筛选">
                  <Select value={envGroup} onChange={(event) => setEnvGroup(event.target.value)}>
                    <option value="全部">全部</option>
                    {envGroupOptions.map((group) => (
                      <option key={group} value={group}>
                        {group}
                      </option>
                    ))}
                  </Select>
                </Field>
              </CardContent>
            </Card>
            <InfoTileGrid
              columns={4}
              items={[
                { label: "当前展示", value: filteredEnvItems.length, note: "已应用搜索与分类筛选" },
                { label: "已修改", value: envModifiedCount, note: "与默认值不同的字段" },
                { label: "敏感字段", value: envSensitiveCount, note: "默认以密码形式显示" },
                { label: "有默认值", value: envItems.filter((item) => item.has_default).length, note: "可一键重置回 `.env.example`" },
              ]}
            />
            {filteredEnvItems.length ? (
              <div className="grid gap-4 xl:grid-cols-2">
                {filteredEnvItems.map((item) => {
                  const draft = envDrafts[item.key] ?? String(item.value ?? "");
                  const useTextarea = draft.length > 72 || draft.includes(",") || draft.includes(" ");
                  const defaultDisplay = item.has_default
                    ? item.is_sensitive
                      ? item.default_display_value ?? item.default_value ?? "-"
                      : item.default_value || "-"
                    : "无默认值";

                  return (
                    <Card key={item.key}>
                      <CardHeader className="space-y-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <CardTitle className="text-base">{item.key}</CardTitle>
                          <Badge>{envGroupFromKey(item.key)}</Badge>
                          {item.is_sensitive ? (
                            <Badge className="bg-slate-100 text-slate-900">敏感字段</Badge>
                          ) : null}
                          <Badge className={item.is_modified ? "bg-amber-100 text-amber-900" : "bg-emerald-100 text-emerald-900"}>
                            {item.is_modified ? "已修改" : "默认一致"}
                          </Badge>
                        </div>
                        <CardDescription>
                          {item.is_sensitive
                            ? "当前值已隐藏显示，可直接输入新值后保存。"
                            : `当前值：${item.display_value || "(空值)"}`}
                        </CardDescription>
                      </CardHeader>
                      <CardContent className="space-y-4">
                        <Field
                          label="当前值"
                          hint={item.is_sensitive ? "敏感字段使用密码输入框显示，保存时会直接写回 `.env`。" : undefined}
                        >
                          {useTextarea ? (
                            <Textarea
                              rows={3}
                              value={draft}
                              onChange={(event) =>
                                setEnvDrafts((current) => ({ ...current, [item.key]: event.target.value }))
                              }
                            />
                          ) : (
                            <Input
                              type={item.is_sensitive ? "password" : "text"}
                              value={draft}
                              onChange={(event) =>
                                setEnvDrafts((current) => ({ ...current, [item.key]: event.target.value }))
                              }
                            />
                          )}
                        </Field>
                        <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/35 px-4 py-3">
                          <p className="text-xs uppercase tracking-[0.14em] text-[var(--muted-foreground)]">默认值</p>
                          <p className="mt-2 text-sm leading-6 break-all text-[var(--foreground)]">{defaultDisplay}</p>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          <Button onClick={() => void handleSaveEnvItem(item.key)}>保存</Button>
                          <Button
                            variant="secondary"
                            onClick={() =>
                              setEnvDrafts((current) => ({ ...current, [item.key]: String(item.value ?? "") }))
                            }
                          >
                            恢复当前线上值
                          </Button>
                          {item.has_default ? (
                            <Button variant="secondary" onClick={() => void handleResetEnvItem(item.key)}>
                              重置默认值
                            </Button>
                          ) : null}
                        </div>
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            ) : (
              <Card>
                <CardContent className="pt-6">
                  <p className="text-sm text-[var(--muted-foreground)]">
                    当前筛选条件下没有找到环境变量，请调整关键词或分类。
                  </p>
                </CardContent>
              </Card>
            )}
          </div>
        ) : null}
        {configTab === "thresholds" ? <div className="space-y-4"><Card><CardContent className="pt-6"><Field label="默认超时阈值 (ms)"><Input type="number" value={thresholdEditor.default_threshold_ms} onChange={(event) => setThresholdEditor((current) => ({ ...current, default_threshold_ms: event.target.value }))} /></Field></CardContent></Card><MappingEditorTable title="参数阈值" rows={thresholdRows} columns={[{ key: "key", label: "参数项" }, { key: "value", label: "阈值(秒)" }]} onChange={(rows) => setThresholdRows(rows as Array<{ key: string; value: string }>)} /><MappingEditorTable title="参数期望值" rows={expectedRows} columns={[{ key: "key", label: "参数项" }, { key: "value", label: "期望(秒)" }]} onChange={(rows) => setExpectedRows(rows as Array<{ key: string; value: string }>)} /><MappingEditorTable title="步骤级阈值" rows={stepThresholdRows} columns={[{ key: "module", label: "业务模块" }, { key: "step", label: "步骤名称" }, { key: "value", label: "超时阈值(ms)" }]} onChange={(rows) => setStepThresholdRows(rows as Array<{ module: string; step: string; value: string }>)} /><MappingEditorTable title="诊断上下文窗口" rows={contextRows} columns={[{ key: "key", label: "上下文项" }, { key: "value", label: "值" }]} onChange={(rows) => setContextRows(rows as Array<{ key: string; value: string }>)} /><Button onClick={() => void handleSaveThresholds()}>保存阈值配置</Button></div> : null}
        {configTab === "rules" ? <div className="space-y-4"><InfoTileGrid columns={4} items={[{ label: "时间格式规则", value: safeArray(parserRules.time_formats).length }, { label: "Cycle 提取规则", value: safeArray(parserRules.cycle_patterns).length }, { label: "Chip 提取规则", value: safeArray(parserRules.chip_patterns).length }, { label: "回退异常家族", value: errorRules.fallback_family || "-" }]} /><DetailListCard title="主动学习与审核策略" value={activeLearning} />{familyRules.length ? <DataTable title="异常家族" rows={familyRules} maxHeight={360} /> : null}</div> : null}
        {configTab === "knowledge" ? <div className="space-y-4"><DataTable title="Prompt 模板摘要" rows={promptVersionRows} maxHeight={320} /><InfoTileGrid columns={4} items={[{ label: "模块前缀数", value: Object.keys(modulePrefixes).length }, { label: "一级模块", value: moduleTree.length }, { label: "子模块", value: moduleTree.reduce((sum, item) => sum + safeArray(item.children).length, 0) }, { label: "建议输出目录", value: safeObject(activeLearning.suggestion_generation).write_suggestions_to || "-" }]} />{moduleTree.map((module) => <details key={String(module.name || "module")} className="rounded-2xl border border-[var(--border)] bg-[var(--card)] p-4"><summary className="cursor-pointer text-sm font-medium text-[var(--foreground)]">{`${module.name || "未命名模块"} · ${safeArray(module.children).length} 个子模块`}</summary><div className="mt-4"><InfoTileGrid columns={2} items={[{ label: "错误码前缀", value: modulePrefixes[module.name] || "-" }, { label: "子模块数量", value: safeArray(module.children).length }]} /><div className="mt-4"><ChipToggleGroup options={safeArray(module.children).map((item) => String(item))} selected={[]} onToggle={() => {}} /></div></div></details>)}</div> : null}
      </div>
    );
  }

  function renderExportsPage() {
    return (
      <div className="space-y-6">
        <SectionTitle title="导出" description="统一使用后端 FileResponse 接口导出任务产物和方案库数据。" />
        {selectedTaskUuid ? (
          <Card>
            <CardContent className="flex flex-wrap gap-3 pt-6">
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/events`, { access_token: token })} target="_blank" rel="noreferrer">导出统一事件 CSV</a></Button>
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/errors`, { access_token: token })} target="_blank" rel="noreferrer">导出错误分析 CSV</a></Button>
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/parameters`, { access_token: token })} target="_blank" rel="noreferrer">导出参数结果 CSV</a></Button>
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/report.html`, { access_token: token })} target="_blank" rel="noreferrer">导出 HTML 报告</a></Button>
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/report.json`, { access_token: token })} target="_blank" rel="noreferrer">导出 JSON 报告</a></Button>
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/report.xlsx`, { access_token: token })} target="_blank" rel="noreferrer">导出 Excel 报告</a></Button>
              <Button variant="secondary" asChild><a href={buildApiUrl(apiBase, `/tasks/${selectedTaskUuid}/export/report.pdf`, { access_token: token })} target="_blank" rel="noreferrer">导出 PDF 报告</a></Button>
            </CardContent>
          </Card>
        ) : (
          <Card><CardContent className="pt-6"><p className="text-sm text-[var(--muted-foreground)]">请先选择任务 UUID。</p></CardContent></Card>
        )}
      </div>
    );
  }

  function renderUsersPage() {
    return (
      <div className="space-y-6">
        <SectionTitle title="用户管理" description="仅管理员可见，用于处理注册审核、账号启停与角色设置。" actions={renderRefreshButton("users", "刷新用户列表", () => loadUsers())} />
        <DataTable title="用户列表" rows={userList} maxHeight={320} />
        <Field label="选择用户">
          <Select value={selectedUserId} onChange={(event) => setSelectedUserId(event.target.value)}>
            <option value="">请选择</option>
            {userList.map((item) => (
              <option key={String(item.id)} value={String(item.id)}>
                {`${item.id} | ${item.username || ""} | ${item.status || ""} | ${safeArray(item.roles).join(",")}`}
              </option>
            ))}
          </Select>
        </Field>
        {selectedUserRecord ? <DetailListCard value={selectedUserRecord} /> : null}
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => void handleUpdateUserStatus("approve")}>通过</Button>
          <Button variant="secondary" onClick={() => void handleUpdateUserStatus("reject")}>拒绝</Button>
          <Button variant="secondary" onClick={() => void handleUpdateUserStatus("disable")}>停用</Button>
          <Button variant="secondary" onClick={() => void handleUpdateUserStatus("enable")}>启用</Button>
        </div>
        <div className="flex flex-wrap gap-6 rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-4">
          <label className="flex items-center gap-2 text-sm text-[var(--foreground)]"><input type="checkbox" checked={selectedUserRoles.is_reviewer} onChange={(event) => setSelectedUserRoles((current) => ({ ...current, is_reviewer: event.target.checked }))} />设为 reviewer</label>
          <label className="flex items-center gap-2 text-sm text-[var(--foreground)]"><input type="checkbox" checked={selectedUserRoles.is_admin} onChange={(event) => setSelectedUserRoles((current) => ({ ...current, is_admin: event.target.checked }))} />设为 admin</label>
        </div>
        <Button onClick={() => void handleSaveUserRoles()}>保存角色设置</Button>
      </div>
    );
  }

  function renderMainContent() {
    if (!isAuthenticated) {
      if (page === "welcome") {
        return renderWelcome();
      }
      if (page === "login") {
        return renderLogin();
      }
      return renderRegister();
    }

    switch (page) {
      case "dashboard":
        return renderDashboardPage();
      case "history":
        return renderHistoryPage();
      case "upload":
        return renderUploadPage();
      case "events":
        return renderEventsPage();
      case "performance":
        return renderPerformancePage();
      case "timeline":
        return renderTimelinePage();
      case "errors":
        return renderErrorsPage();
      case "parameters":
        return renderParametersPage();
      case "llm":
        return renderLlmPage();
      case "solutionHub":
        return renderSolutionHubPage();
      case "files":
        return renderFilesPage();
      case "unknown":
        return renderUnknownPage();
      case "rules":
        return renderRulesPage();
      case "config":
        return renderConfigPage();
      case "exports":
        return renderExportsPage();
      case "users":
        return renderUsersPage();
      default:
        return renderDashboardPage();
    }
  }

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

  const currentPageGuide = pageUsageGuides[page];
  const shellDescription =
    page === "login"
      ? "如果有任何问题，请咨询liuyanbo1@genomics.cn"
      : "MGI";
  const mainContent = renderMainContent();

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
            <CardDescription>{shellDescription}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-5">
            {isAdmin ? (
              <div className="space-y-4 rounded-2xl border border-[var(--border)] bg-[var(--muted)]/30 p-4">
                <p className="text-sm font-medium text-[var(--foreground)]">管理员接口控制</p>
                <Field label="FastAPI 地址">
                  <Input value={apiBase} onChange={(event) => setApiBase(normalizeApiBaseUrl(event.target.value))} />
                </Field>
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--card)] px-4 py-3 text-sm">
                  <p className="text-xs uppercase tracking-[0.14em] text-[var(--muted-foreground)]">当前 API</p>
                  <p className="mt-2 break-all text-[var(--foreground)]">{apiBase.replace(/^https?:\/\//, "")}</p>
                </div>
              </div>
            ) : null}
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
                    <div className="flex items-center justify-between gap-3">
                      <p className="text-sm font-medium text-[var(--foreground)]">修改密码</p>
                      <Button variant="ghost" size="sm" onClick={() => setPasswordEditorOpen((current) => !current)}>
                        <KeyRound className="h-4 w-4" />
                        {passwordEditorOpen ? "收起" : "展开"}
                      </Button>
                    </div>
                    {passwordEditorOpen ? (
                      <div className="space-y-3">
                        <Input type="password" placeholder="当前密码" value={currentPassword} onChange={(event) => setCurrentPassword(event.target.value)} />
                        <Input type="password" placeholder="新密码" value={nextPassword} onChange={(event) => setNextPassword(event.target.value)} />
                        <Input type="password" placeholder="确认新密码" value={nextPasswordConfirm} onChange={(event) => setNextPasswordConfirm(event.target.value)} />
                        <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/25 px-4 py-3">
                          <p className="text-xs uppercase tracking-[0.14em] text-[var(--muted-foreground)]">提交前校验</p>
                          <div className="mt-3 space-y-2">
                            {passwordChecks.map((item) => (
                              <p key={item.label} className={cn("text-sm", item.passed ? "text-emerald-700" : "text-[var(--muted-foreground)]")}>
                                {item.passed ? "已满足" : "待完成"} · {item.label}
                              </p>
                            ))}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-3">
                          <Button className="flex-1" variant="secondary" disabled={!canSubmitPasswordChange} onClick={() => void handleChangePassword()}>
                            更新密码
                          </Button>
                          <Button
                            variant="ghost"
                            onClick={() => {
                              setPasswordEditorOpen(false);
                              setCurrentPassword("");
                              setNextPassword("");
                              setNextPasswordConfirm("");
                            }}
                          >
                            取消
                          </Button>
                        </div>
                      </div>
                    ) : (
                      <p className="text-sm leading-6 text-[var(--muted-foreground)]">
                        展开后填写当前密码和新密码，所有校验通过后才允许提交。
                      </p>
                    )}
                  </div>
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
        {currentPageGuide ? (
          <UsageGuideCard
            title={currentPageGuide.title}
            description={currentPageGuide.description}
            steps={currentPageGuide.steps}
          />
        ) : null}
        {mainContent}
      </main>
    </div>
  );
}
