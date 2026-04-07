/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import {
  startTransition,
  useEffect,
  useDeferredValue,
  useId,
  useMemo,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type WheelEvent as ReactWheelEvent,
} from "react";

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
import { Label } from "@/components/ui/label";
import { Select } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";

export type AnyRecord = Record<string, any>;
export type Notice = {
  tone: "success" | "error" | "info";
  text: string;
};

const BEIJING_TIMEZONE = "Asia/Shanghai";

export type MappingEditorColumn = {
  key: string;
  label: string;
  placeholder?: string;
  multiline?: boolean;
};

export function safeArray<T = AnyRecord>(value: unknown) {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function safeObject(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as AnyRecord)
    : {};
}

export function safeNumber(value: unknown, fallback = 0) {
  const next = Number(value);
  return Number.isFinite(next) ? next : fallback;
}

export function toDisplayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") {
    return "-";
  }
  if (typeof value === "boolean") {
    return value ? "是" : "否";
  }
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => toDisplayValue(item)).join(" / ") : "-";
  }
  if (typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}

export function shortText(value: unknown, limit = 120) {
  const text = String(value ?? "").trim();
  if (!text) {
    return "-";
  }
  return text.length > limit ? `${text.slice(0, limit)}...` : text;
}

export function formatDate(value: unknown) {
  if (!value) {
    return "-";
  }
  const text = String(value).trim();
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    const date = new Date(`${normalized}T00:00:00Z`);
    if (!Number.isNaN(date.getTime())) {
      return new Intl.DateTimeFormat("zh-CN", {
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        timeZone: BEIJING_TIMEZONE,
      }).format(date);
    }
  }
  const hasTimezone = /[zZ]$|[+\-]\d{2}:\d{2}$/.test(normalized);
  const date = new Date(hasTimezone ? normalized : `${normalized}Z`);
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: BEIJING_TIMEZONE,
  }).format(date);
}

export function stringifyJson(value: unknown) {
  return JSON.stringify(value ?? {}, null, 2);
}

export function parseJsonText(text: string, label: string) {
  try {
    return JSON.parse(text);
  } catch (error) {
    throw new Error(`${label} 不是合法 JSON: ${(error as Error).message}`);
  }
}

export function statusBadgeTone(status: string) {
  switch (status) {
    case "completed":
    case "approved":
    case "enabled":
      return "border-[rgba(102,191,255,0.28)] bg-[rgba(102,191,255,0.12)] text-[#164a7c]";
    case "queued":
    case "running":
    case "pending_review":
    case "pending_admin_approval":
    case "submitted_for_review":
      return "border-[rgba(215,138,69,0.28)] bg-[rgba(215,138,69,0.12)] text-[#8a531e]";
    case "failed":
    case "rejected":
    case "disabled":
      return "border-[rgba(212,94,90,0.26)] bg-[rgba(212,94,90,0.12)] text-[#9a3a3c]";
    case "needs_revision":
    case "ignored":
      return "border-[rgba(112,184,255,0.26)] bg-[rgba(112,184,255,0.11)] text-[#24588c]";
    default:
      return "border-[rgba(69,128,212,0.22)] bg-[rgba(69,128,212,0.1)] text-[var(--foreground)]";
  }
}

function palette(index: number) {
  const colors = [
    "#2F67C7",
    "#7EB8FF",
    "#F06D42",
    "#49BFD6",
    "#6E7DF5",
    "#9CCBFF",
    "#3AA689",
    "#F0B45B",
    "#476691",
    "#78D7C8",
  ];
  return colors[index % colors.length];
}

function hashIndex(value: string) {
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function timelineColor(label: string) {
  return palette(hashIndex(label));
}

function clamp(value: number, min: number, max: number) {
  return Math.min(Math.max(value, min), max);
}

function compareDisplayValues(left: unknown, right: unknown) {
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  if (Number.isFinite(leftNumber) && Number.isFinite(rightNumber)) {
    return leftNumber - rightNumber;
  }
  return toDisplayValue(left).localeCompare(toDisplayValue(right), "zh-CN", {
    numeric: true,
    sensitivity: "base",
  });
}

function parseTimelineValue(value: unknown): number | null {
  if (value === null || value === undefined || value === "") {
    return null;
  }
  if (typeof value === "number" && Number.isFinite(value)) {
    if (Math.abs(value) > 1_000_000_000_000) {
      return value;
    }
    if (Math.abs(value) > 1_000_000_000) {
      return value * 1000;
    }
    return value * 1000;
  }
  const text = String(value).trim();
  if (!text) {
    return null;
  }
  const numeric = Number(text);
  if (Number.isFinite(numeric)) {
    return parseTimelineValue(numeric);
  }
  const normalized = text.includes("T") ? text : text.replace(" ", "T");
  if (/^\d{4}-\d{2}-\d{2}$/.test(normalized)) {
    const parsedDateOnly = Date.parse(`${normalized}T00:00:00+08:00`);
    return Number.isNaN(parsedDateOnly) ? null : parsedDateOnly;
  }
  const withTimezone = /[zZ]$|[+\-]\d{2}:\d{2}$/.test(normalized) ? normalized : `${normalized}+08:00`;
  const parsed = Date.parse(withTimezone);
  return Number.isNaN(parsed) ? null : parsed;
}

function formatDurationText(value: unknown) {
  const seconds = Number(value);
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "-";
  }
  if (seconds < 1) {
    return `${seconds.toFixed(2)}s`;
  }
  const rounded = Math.round(seconds);
  const days = Math.floor(rounded / 86400);
  const hours = Math.floor((rounded % 86400) / 3600);
  const minutes = Math.floor((rounded % 3600) / 60);
  const secs = rounded % 60;
  return [days ? `${days}d` : null, hours ? `${hours}h` : null, minutes ? `${minutes}m` : null, `${secs}s`]
    .filter(Boolean)
    .slice(0, 3)
    .join(" ");
}

function formatDateTimeText(value: unknown) {
  if (!value) {
    return "-";
  }
  const parsed = parseTimelineValue(value);
  if (parsed === null) {
    const date = new Date(String(value));
    if (Number.isNaN(date.getTime())) {
      return String(value);
    }
    return formatDate(date.toISOString());
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: BEIJING_TIMEZONE,
  }).format(new Date(parsed));
}

function normalizeProgressStage(status: AnyRecord) {
  const progress = clamp(safeNumber(status.progress_percent, 0), 0, 100);
  const runtimeStatus = String(status.status || "").toLowerCase();
  const rawStage = String(status.current_stage || "").toLowerCase();
  if (runtimeStatus === "completed" || progress >= 100) {
    return "completed";
  }
  if (runtimeStatus === "uploaded" || runtimeStatus === "queued" || progress < 20 || /upload|queue|discover|prescan|prepare|workspace|input/.test(rawStage)) {
    return "uploaded";
  }
  if (/parse|parser/.test(rawStage) || progress < 68) {
    return "parsing";
  }
  if (/merge|normalize|cycle_context|aggregate|summary|context/.test(rawStage) || progress < 84) {
    return "summary";
  }
  return "postprocess";
}

function progressStageLabel(stageKey: string) {
  switch (stageKey) {
    case "uploaded":
      return "上传";
    case "parsing":
      return "解析";
    case "summary":
      return "汇总";
    case "postprocess":
      return "后处理";
    case "completed":
      return "完成";
    default:
      return stageKey || "-";
  }
}

function compactStageText(value: unknown) {
  return String(value || "-").trim().replace(/[_\s]+/g, " ");
}

function detectActiveFileLabel(status: AnyRecord) {
  const fallback = String(status.filename || status.task_uuid || "-").trim() || "-";
  const message = String(status.message || "").trim();
  if (!message) {
    return fallback;
  }
  const explicitPatterns = [
    /checking archive\/file:\s*(.+)$/i,
    /^(.+?)\s*\[[^\]]+\]$/i,
    /^(.+?)\s+retried serially$/i,
  ];
  for (const pattern of explicitPatterns) {
    const match = message.match(pattern);
    const next = match?.[1]?.trim();
    if (next) {
      return next;
    }
  }
  const fileMatch = message.match(/([^\s\\/:*?"<>|]+?\.(?:csv|log|txt|zip|7z|tar|jsonl?|gz|tsv|xlsx?))/i);
  return fileMatch?.[1] || fallback;
}

function pickVisibleTicks<T>(values: T[], maxCount: number) {
  if (values.length <= maxCount) {
    return values;
  }
  const step = Math.max(1, Math.ceil(values.length / maxCount));
  return values.filter((_, index) => index % step === 0 || index === values.length - 1);
}

function timelineBaseTrack(value: unknown) {
  return String(value || "").replace(/\s+\|\s+lane\s+\d+$/i, "").trim();
}

function timelineLaneIndex(value: unknown) {
  const match = String(value || "").match(/\|\s+lane\s+(\d+)$/i);
  return match ? Number(match[1]) : 1;
}

const progressStageFlow = ["uploaded", "parsing", "summary", "postprocess", "completed"] as const;

function niceStep(span: number, targetTickCount: number) {
  if (!Number.isFinite(span) || span <= 0) {
    return 1;
  }
  const rawStep = span / Math.max(targetTickCount, 1);
  const magnitude = 10 ** Math.floor(Math.log10(rawStep));
  const normalized = rawStep / magnitude;
  if (normalized <= 1) {
    return magnitude;
  }
  if (normalized <= 2) {
    return 2 * magnitude;
  }
  if (normalized <= 5) {
    return 5 * magnitude;
  }
  return 10 * magnitude;
}

function createLinearTicks(min: number, max: number, targetTickCount: number) {
  if (!Number.isFinite(min) || !Number.isFinite(max)) {
    return [];
  }
  if (max <= min) {
    return [min];
  }
  const step = niceStep(max - min, targetTickCount);
  const start = Math.ceil(min / step) * step;
  const ticks: number[] = [min];
  for (let value = start; value < max; value += step) {
    ticks.push(Number(value.toFixed(12)));
  }
  ticks.push(max);
  return Array.from(new Set(ticks)).sort((left, right) => left - right);
}

function formatNumericTick(value: number, span: number) {
  if (!Number.isFinite(value)) {
    return "-";
  }
  const absValue = Math.abs(value);
  if (span >= 1000 || absValue >= 1000) {
    return value.toFixed(0);
  }
  if (span >= 100 || absValue >= 100) {
    return value.toFixed(1);
  }
  if (span >= 10 || absValue >= 10) {
    return value.toFixed(2);
  }
  return value.toFixed(3);
}

function formatTimelineAxisLabel(timestampMs: number, spanMs: number) {
  const date = new Date(timestampMs);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  const dayText = new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    timeZone: BEIJING_TIMEZONE,
  }).format(date);
  const timeText = new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    timeZone: BEIJING_TIMEZONE,
  }).format(date);
  if (spanMs < 60_000) {
    return `${timeText}.${String(date.getMilliseconds()).padStart(3, "0")}`;
  }
  if (spanMs < 86_400_000) {
    return timeText;
  }
  return `${dayText} ${timeText}`;
}

function cleanComponentTrackLabel(value: unknown) {
  return String(value || "")
    .replace(/\s+\|\s+cycle\s+[^|]+/i, "")
    .replace(/\s+\|\s+lane\s+\d+$/i, "")
    .trim();
}

function clampViewport(
  start: number,
  end: number,
  min: number,
  max: number,
  minSpan: number,
): [number, number] {
  if (!Number.isFinite(start) || !Number.isFinite(end) || !Number.isFinite(min) || !Number.isFinite(max)) {
    return [min, max];
  }
  if (max <= min) {
    return [min, max];
  }
  const fullSpan = max - min;
  const safeMinSpan = Math.min(Math.max(minSpan, 0.0001), fullSpan);
  if (fullSpan <= safeMinSpan) {
    return [min, max];
  }
  let nextStart = Math.min(start, end);
  let nextEnd = Math.max(start, end);
  if (nextEnd - nextStart < safeMinSpan) {
    const center = (nextStart + nextEnd) / 2;
    nextStart = center - safeMinSpan / 2;
    nextEnd = center + safeMinSpan / 2;
  }
  if (nextStart < min) {
    nextEnd += min - nextStart;
    nextStart = min;
  }
  if (nextEnd > max) {
    nextStart -= nextEnd - max;
    nextEnd = max;
  }
  if (nextStart < min) {
    nextStart = min;
  }
  if (nextEnd > max) {
    nextEnd = max;
  }
  if (nextEnd - nextStart < safeMinSpan) {
    nextStart = Math.max(min, nextEnd - safeMinSpan);
    nextEnd = Math.min(max, nextStart + safeMinSpan);
  }
  return [nextStart, nextEnd];
}

export function SectionTitle({
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
        <h2 className="text-2xl font-semibold tracking-tight text-[var(--foreground)]">{title}</h2>
        <p className="max-w-4xl text-sm leading-6 text-[var(--muted-foreground)]">{description}</p>
      </div>
      {actions ? <div className="flex flex-wrap gap-3">{actions}</div> : null}
    </div>
  );
}

export function Field({
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
      {hint ? <p className="text-xs leading-5 text-[var(--muted-foreground)]">{hint}</p> : null}
    </div>
  );
}

export function NoticeBanner({ notice }: { notice: Notice | null }) {
  if (!notice) {
    return null;
  }
  const toneClass =
    notice.tone === "success"
      ? "border-[rgba(102,191,255,0.28)] bg-[rgba(102,191,255,0.12)] text-[#164a7c]"
      : notice.tone === "error"
        ? "border-[rgba(212,94,90,0.26)] bg-[rgba(212,94,90,0.12)] text-[#9a3a3c]"
        : "border-[rgba(69,128,212,0.26)] bg-[rgba(69,128,212,0.12)] text-[#1b5d9a]";
  return <div className={cn("rounded-2xl border px-4 py-3 text-sm", toneClass)}>{notice.text}</div>;
}

export function MetricCard({
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
        <p className="text-3xl font-semibold tracking-tight text-[var(--foreground)]">{value}</p>
        <p className="text-xs leading-5 text-[var(--muted-foreground)]">{helper}</p>
      </CardContent>
    </Card>
  );
}

function flattenDetailRows(
  value: unknown,
  prefix = "",
  depth = 0,
): Array<{ label: string; value: string; note?: string }> {
  const label = prefix || "value";
  if (value === null || value === undefined || typeof value !== "object") {
    return [{ label, value: toDisplayValue(value) }];
  }

  if (Array.isArray(value)) {
    if (!value.length) {
      return [{ label, value: "-" }];
    }
    if (value.every((item) => item === null || typeof item !== "object")) {
      return [{ label, value: value.map((item) => toDisplayValue(item)).join(" / ") }];
    }
    if (depth >= 1) {
      return [
        {
          label,
          value: `${value.length} 项`,
          note: `示例: ${shortText(stringifyJson(value[0]), 120)}`,
        },
      ];
    }
    return value.slice(0, 6).flatMap((item, index) =>
      flattenDetailRows(item, `${label}[${index + 1}]`, depth + 1),
    );
  }

  const entries = Object.entries(safeObject(value));
  if (!entries.length) {
    return [{ label, value: "-" }];
  }
  if (depth >= 2) {
    return [{ label, value: shortText(stringifyJson(value), 180) }];
  }
  return entries.flatMap(([key, item]) =>
    flattenDetailRows(item, prefix ? `${prefix}.${key}` : key, depth + 1),
  );
}

export function StatusBadge({ status }: { status: unknown }) {
  return <Badge className={statusBadgeTone(String(status ?? ""))}>{String(status ?? "-")}</Badge>;
}

export function DetailListCard({
  value,
  title,
  description,
  maxHeight = 420,
}: {
  value: unknown;
  title?: string;
  description?: string;
  maxHeight?: number;
}) {
  const rows = flattenDetailRows(value).slice(0, 80);
  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        {rows.length ? (
          <div
            className="overflow-auto rounded-2xl border border-[var(--border)] bg-[var(--card)]"
            style={{ maxHeight }}
          >
            {rows.map((row, index) => (
              <div
                key={`${row.label}-${index}`}
                className="grid gap-2 border-b border-[var(--border)] px-4 py-3 last:border-b-0 lg:grid-cols-[220px_minmax(0,1fr)]"
              >
                <div className="space-y-1">
                  <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
                    {row.label}
                  </p>
                  {row.note ? (
                    <p className="text-xs leading-5 text-[var(--muted-foreground)]">{row.note}</p>
                  ) : null}
                </div>
                <p className="text-sm leading-6 whitespace-pre-wrap break-all text-[var(--foreground)]">
                  {row.value}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可展示的数据。</p>
        )}
      </CardContent>
    </Card>
  );
}

export function JsonPreview({
  value,
  title,
  description,
  maxHeight = 420,
}: {
  value: unknown;
  title?: string;
  description?: string;
  maxHeight?: number;
}) {
  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        <pre
          className="overflow-auto rounded-2xl bg-[var(--muted)]/70 p-4 text-xs leading-6 whitespace-pre-wrap"
          style={{ maxHeight }}
        >
          {stringifyJson(value)}
        </pre>
      </CardContent>
    </Card>
  );
}

export function UsageGuideCard({
  title = "本页使用逻辑",
  description,
  steps,
}: {
  title?: string;
  description?: string;
  steps: string[];
}) {
  return (
    <Card className="border-dashed">
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="grid gap-3 pt-0 lg:grid-cols-3">
        {steps.map((step, index) => (
          <div
            key={`${title}-${index + 1}`}
            className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/35 p-4"
          >
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Step {index + 1}
            </p>
            <p className="mt-2 text-sm leading-6 text-[var(--foreground)]">{step}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function CodePreview({
  code,
  title,
  description,
  maxHeight = 420,
}: {
  code: string;
  title?: string;
  description?: string;
  maxHeight?: number;
}) {
  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        <pre
          className="overflow-auto rounded-2xl bg-[#0b1625] p-4 text-xs leading-6 whitespace-pre-wrap text-slate-100"
          style={{ maxHeight }}
        >
          {code || "暂无内容"}
        </pre>
      </CardContent>
    </Card>
  );
}

export function LinePreviewCard({
  text,
  title,
  description,
  maxHeight = 420,
}: {
  text: string;
  title?: string;
  description?: string;
  maxHeight?: number;
}) {
  const rows = (text || "").split(/\r?\n/);
  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        {text ? (
          <div
            className="overflow-auto rounded-2xl border border-[var(--border)] bg-[#0b1625] text-slate-100"
            style={{ maxHeight }}
          >
            <div className="min-w-full divide-y divide-slate-800/70 font-mono text-xs leading-6">
              {rows.map((line, index) => (
                <div
                  key={`${title || "line"}-${index + 1}`}
                  className="grid grid-cols-[72px_minmax(0,1fr)] gap-4 px-4 py-2"
                >
                  <span className="select-none text-right text-slate-500">{index + 1}</span>
                  <span className="whitespace-pre-wrap break-all">{line || " "}</span>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <p className="text-sm text-[var(--muted-foreground)]">暂无内容</p>
        )}
      </CardContent>
    </Card>
  );
}

export function DistributionList({
  title,
  items,
  description,
}: {
  title: string;
  items: Array<{ label: string; value: number; note?: string; color?: string }>;
  description?: string;
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {items.length ? (
          items.map((item, index) => {
            const percent = Math.round((item.value / total) * 100);
            const accent = item.color || palette(index);
            return (
              <div key={`${title}-${item.label}`} className="space-y-2">
                <div className="flex items-center justify-between gap-3">
                  <p className="truncate text-sm font-medium text-[var(--foreground)]">{item.label}</p>
                  <p className="text-xs text-[var(--muted-foreground)]">
                    {item.value} / {percent}%
                  </p>
                </div>
                <div className="h-2 rounded-full bg-[var(--muted)]">
                  <div
                    className="h-2 rounded-full"
                    style={{ width: `${Math.max(percent, 6)}%`, backgroundColor: accent }}
                  />
                </div>
                {item.note ? (
                  <p className="text-xs leading-5 text-[var(--muted-foreground)]">{item.note}</p>
                ) : null}
              </div>
            );
          })
        ) : (
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可展示的数据。</p>
        )}
      </CardContent>
    </Card>
  );
}

export function InfoTileGrid({
  items,
  columns = 3,
}: {
  items: Array<{ label: string; value: unknown; note?: string }>;
  columns?: 2 | 3 | 4;
}) {
  const gridClass =
    columns === 4
      ? "lg:grid-cols-4"
      : columns === 2
        ? "lg:grid-cols-2"
        : "lg:grid-cols-3";
  return (
    <div className={cn("grid gap-4", gridClass)}>
      {items.map((item) => (
        <Card key={`${item.label}-${String(item.value)}`}>
          <CardContent className="space-y-2 pt-6">
            <p className="text-xs uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              {item.label}
            </p>
            <p className="text-xl font-semibold text-[var(--foreground)]">
              {toDisplayValue(item.value)}
            </p>
            {item.note ? (
              <p className="text-xs leading-5 text-[var(--muted-foreground)]">{item.note}</p>
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

type DataTableProps = {
  rows: AnyRecord[];
  columns?: string[];
  title?: string;
  caption?: string;
  maxHeight?: number;
  emptyText?: string;
  selectedRowIndex?: number;
  onRowClick?: (row: AnyRecord, index: number) => void;
};

function InteractiveDataTable({
  rows,
  columns,
  title,
  caption,
  maxHeight = 420,
  emptyText = "当前没有可展示的数据。",
  selectedRowIndex,
  onRowClick,
}: DataTableProps) {
  const visibleColumns = useMemo(() => {
    if (columns?.length) {
      return columns;
    }
    return Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 18);
  }, [columns, rows]);

  const [searchText, setSearchText] = useState("");
  const [filterColumn, setFilterColumn] = useState("__all__");
  const [filterValue, setFilterValue] = useState("");
  const [sortState, setSortState] = useState<{ key: string | null; direction: "asc" | "desc" }>({
    key: null,
    direction: "asc",
  });

  const deferredSearch = useDeferredValue(searchText.trim().toLowerCase());
  const deferredFilterValue = useDeferredValue(filterValue.trim().toLowerCase());

  const indexedRows = useMemo(
    () => rows.map((row, originalIndex) => ({ row, originalIndex })),
    [rows],
  );

  const suggestedFilterValues = useMemo(() => {
    if (filterColumn === "__all__") {
      return [];
    }
    return Array.from(
      new Set(
        rows
          .map((row) => toDisplayValue(row[filterColumn]))
          .filter((value) => value !== "-"),
      ),
    )
      .sort((left, right) => compareDisplayValues(left, right))
      .slice(0, 100);
  }, [filterColumn, rows]);

  const viewRows = useMemo(() => {
    let nextRows = [...indexedRows];
    if (deferredSearch) {
      nextRows = nextRows.filter(({ row }) =>
        visibleColumns.some((column) =>
          toDisplayValue(row[column]).toLowerCase().includes(deferredSearch),
        ),
      );
    }
    if (filterColumn !== "__all__" && deferredFilterValue) {
      nextRows = nextRows.filter(({ row }) =>
        toDisplayValue(row[filterColumn]).toLowerCase().includes(deferredFilterValue),
      );
    }
    if (sortState.key) {
      nextRows.sort((left, right) => {
        const result = compareDisplayValues(
          left.row[sortState.key as string],
          right.row[sortState.key as string],
        );
        return sortState.direction === "asc" ? result : -result;
      });
    }
    return nextRows;
  }, [
    deferredFilterValue,
    deferredSearch,
    filterColumn,
    indexedRows,
    sortState.direction,
    sortState.key,
    visibleColumns,
  ]);

  function toggleSort(column: string) {
    startTransition(() => {
      setSortState((current) => {
        if (current.key === column) {
          return {
            key: column,
            direction: current.direction === "asc" ? "desc" : "asc",
          };
        }
        return { key: column, direction: "asc" };
      });
    });
  }

  function resetControls() {
    startTransition(() => {
      setSearchText("");
      setFilterColumn("__all__");
      setFilterValue("");
      setSortState({ key: null, direction: "asc" });
    });
  }

  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {caption ? <CardDescription>{caption}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className={cn("space-y-4", title ? "pt-0" : "pt-6")}>
        <div className="grid gap-3 rounded-2xl border border-[var(--border)] bg-[var(--muted)]/20 p-4 lg:grid-cols-[1.4fr_1fr_1fr_auto]">
          <Field label="搜索">
            <Input
              value={searchText}
              placeholder="输入关键词检索当前表格"
              onChange={(event) => startTransition(() => setSearchText(event.target.value))}
            />
          </Field>
          <Field label="筛选列">
            <Select
              value={filterColumn}
              onChange={(event) => startTransition(() => setFilterColumn(event.target.value))}
            >
              <option value="__all__">全部列</option>
              {visibleColumns.map((column) => (
                <option key={`${title || "table"}-${column}`} value={column}>
                  {column}
                </option>
              ))}
            </Select>
          </Field>
          <Field
            label="筛选值"
            hint={
              suggestedFilterValues.length
                ? `已为当前列准备 ${suggestedFilterValues.length} 个候选值`
                : "输入后按当前列进行模糊筛选"
            }
          >
            <Input
              list={filterColumn === "__all__" ? undefined : `${title || "table"}-filters`}
              value={filterValue}
              placeholder="输入要匹配的值"
              onChange={(event) => startTransition(() => setFilterValue(event.target.value))}
            />
            {filterColumn !== "__all__" ? (
              <datalist id={`${title || "table"}-filters`}>
                {suggestedFilterValues.map((value) => (
                  <option key={`${filterColumn}-${value}`} value={value} />
                ))}
              </datalist>
            ) : null}
          </Field>
          <div className="flex items-end">
            <Button variant="secondary" className="w-full" onClick={resetControls}>
              重置条件
            </Button>
          </div>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--muted-foreground)]">
          <span>显示 {viewRows.length} / {rows.length} 行</span>
          <span>点击表头排序，支持搜索、列筛选与纵向滚动</span>
        </div>
        {viewRows.length ? (
          <div className="overflow-auto rounded-2xl border border-[var(--border)]" style={{ maxHeight }}>
            <table className="min-w-full divide-y divide-[var(--border)] text-sm">
              <thead className="sticky top-0 z-10 bg-[var(--muted)]/95 backdrop-blur">
                <tr>
                  {visibleColumns.map((column) => {
                    const active = sortState.key === column;
                    const indicator = active ? (sortState.direction === "asc" ? "ASC" : "DESC") : "SORT";
                    return (
                      <th key={column} className="px-3 py-2 text-left">
                        <button
                          type="button"
                          onClick={() => toggleSort(column)}
                          className="inline-flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted-foreground)] transition hover:text-[var(--foreground)]"
                        >
                          <span>{column}</span>
                          <span className={cn("text-[10px]", active ? "text-[var(--foreground)]" : "")}>{indicator}</span>
                        </button>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {viewRows.map(({ row, originalIndex }) => (
                  <tr
                    key={`${title || "smart-table"}-${originalIndex}`}
                    onClick={() => onRowClick?.(row, originalIndex)}
                    className={cn(
                      onRowClick ? "cursor-pointer transition hover:bg-[var(--muted)]/40" : "",
                      selectedRowIndex === originalIndex ? "bg-[color:rgba(11,92,173,0.08)]" : "",
                    )}
                  >
                    {visibleColumns.map((column) => (
                      <td key={`${column}-${originalIndex}`} className="max-w-[360px] px-3 py-2 align-top">
                        <div className="whitespace-pre-wrap break-words text-sm leading-6 text-[var(--foreground)]">
                          {toDisplayValue(row[column])}
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--muted)]/15 px-4 py-8 text-center text-sm text-[var(--muted-foreground)]">
            {emptyText}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export function DataTable(props: DataTableProps) {
  return <InteractiveDataTable {...props} />;
}

export function SmartDataTable(props: DataTableProps) {
  return <InteractiveDataTable {...props} />;
}
export function PaginationBar({
  page,
  pageSize,
  total,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [50, 100, 200, 500],
}: {
  page: number;
  pageSize: number;
  total: number;
  onPageChange: (page: number) => void;
  onPageSizeChange: (pageSize: number) => void;
  pageSizeOptions?: number[];
}) {
  const totalPages = Math.max(1, Math.ceil((total || 0) / pageSize));
  const safePage = Math.min(Math.max(page, 1), totalPages);
  const start = total ? (safePage - 1) * pageSize + 1 : 0;
  const end = total ? Math.min(total, safePage * pageSize) : 0;

  return (
    <div className="flex flex-col gap-3 rounded-2xl border border-[var(--border)] bg-[var(--card)]/70 p-4 lg:flex-row lg:items-center lg:justify-between">
      <div className="text-sm text-[var(--muted-foreground)]">
        {total ? `显示 ${start}-${end} / 共 ${total} 条` : "暂无数据"}
      </div>
      <div className="flex flex-wrap items-center gap-3">
        <div className="flex items-center gap-2">
          <span className="text-sm text-[var(--muted-foreground)]">每页</span>
          <Select
            className="h-9 w-auto min-w-[90px]"
            value={String(pageSize)}
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {pageSizeOptions.map((option) => (
              <option key={option} value={option}>
                {option}
              </option>
            ))}
          </Select>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            disabled={safePage <= 1}
            onClick={() => onPageChange(safePage - 1)}
          >
            上一页
          </Button>
          <span className="text-sm text-[var(--foreground)]">
            第 {safePage} / {totalPages} 页
          </span>
          <Button
            variant="secondary"
            size="sm"
            disabled={safePage >= totalPages}
            onClick={() => onPageChange(safePage + 1)}
          >
            下一页
          </Button>
        </div>
      </div>
    </div>
  );
}

export function ChipToggleGroup({
  options,
  selected,
  onToggle,
}: {
  options: string[];
  selected: string[];
  onToggle: (value: string) => void;
}) {
  if (!options.length) {
    return <p className="text-sm text-[var(--muted-foreground)]">当前没有可选项。</p>;
  }

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => {
        const active = selected.includes(option);
        return (
          <button
            key={option}
            type="button"
            onClick={() => onToggle(option)}
            className={cn(
              "rounded-full border px-3 py-1.5 text-sm transition",
              active
                ? "border-[var(--accent)] bg-[var(--accent)] text-[var(--accent-foreground)]"
                : "border-[var(--border)] bg-[var(--card)] text-[var(--foreground)] hover:bg-[var(--muted)]/80",
            )}
          >
            {option}
          </button>
        );
      })}
    </div>
  );
}

export function TabBar<T extends string>({
  tabs,
  active,
  onChange,
}: {
  tabs: Array<{ key: T; label: string }>;
  active: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          onClick={() => onChange(tab.key)}
          className={cn(
            "rounded-full px-4 py-2 text-sm transition",
            active === tab.key
              ? "bg-[var(--accent)] text-[var(--accent-foreground)]"
              : "bg-[var(--muted)]/70 text-[var(--foreground)] hover:bg-[var(--muted)]",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

export function ProcessingProgressPanel({
  status,
  title = "实时文件处理进度",
}: {
  status: AnyRecord;
  title?: string;
}) {
  const progress = clamp(safeNumber(status.progress_percent, 0), 0, 100);
  const stageKey = normalizeProgressStage(status);
  const activeFile = detectActiveFileLabel(status);
  const historyRows = safeArray(status.progress_history).slice(-5).reverse();
  const runtimeSnapshot = safeObject(status.runtime_snapshot);
  const runtimeCpu = safeObject(runtimeSnapshot.cpu);
  const runtimeMemory = safeObject(runtimeSnapshot.memory);
  const runtimeCaption =
    runtimeCpu.percent !== undefined || runtimeMemory.percent !== undefined
      ? `CPU ${safeNumber(runtimeCpu.percent, Number.NaN).toFixed(0).replace("NaN", "-")}% · Memory ${safeNumber(runtimeMemory.percent, Number.NaN).toFixed(0).replace("NaN", "-")}%`
      : "等待资源状态快照...";

  const infoTiles = [
    { label: "当前处理文件名", value: activeFile },
    { label: "当前处理阶段", value: progressStageLabel(stageKey) },
    { label: "已用时间", value: formatDurationText(status.elapsed_seconds) },
    { label: "预计剩余时间", value: formatDurationText(status.estimated_remaining_seconds) },
    { label: "预计结束时间", value: formatDateTimeText(status.estimated_finish_at) },
    { label: "任务状态", value: String(status.status || "-") },
  ];

  return (
    <Card className="overflow-hidden border-[rgba(84,131,179,0.18)] bg-[linear-gradient(135deg,rgba(3,27,58,0.98),rgba(8,44,91,0.96),rgba(17,71,130,0.94))] text-white shadow-[0_20px_48px_-24px_rgba(5,38,89,0.55)]">
      <CardContent className="space-y-6 pt-6">
        <div className="space-y-4 rounded-[28px] border border-white/10 bg-white/5 p-5 backdrop-blur">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
            <div className="space-y-2">
              <p className="text-xs uppercase tracking-[0.2em] text-sky-100/90">{title}</p>
              <div className="text-2xl font-semibold tracking-tight text-white">{activeFile}</div>
              <div className="flex flex-wrap items-center gap-3 text-sm text-sky-50/90">
                <span>阶段：{progressStageLabel(stageKey)}</span>
                <span>{compactStageText(status.current_stage)}</span>
              </div>
            </div>
            <div className="inline-flex min-w-[5rem] items-center justify-center rounded-full border border-white/15 bg-white/10 px-4 py-2 text-xl font-semibold">
              {Math.round(progress)}%
            </div>
          </div>
          <div className="space-y-3">
            <div className="h-4 overflow-hidden rounded-full bg-white/10">
              <div
                className="h-full rounded-full bg-[linear-gradient(90deg,#7EE0FF_0%,#92BFFF_38%,#F8FBFF_100%)] shadow-[0_0_18px_rgba(126,224,255,0.55)] transition-all"
                style={{ width: `${progress}%` }}
              />
            </div>
            <p className="text-sm leading-6 text-sky-50/85">{String(status.message || "系统正在持续刷新任务状态。")}</p>
          </div>
          <div className="grid gap-3 lg:grid-cols-5">
            {progressStageFlow.map((item, index) => {
              const currentIndex = progressStageFlow.indexOf(stageKey as (typeof progressStageFlow)[number]);
              const state =
                index < currentIndex ? "completed" : item === stageKey ? "active" : "pending";
              return (
                <div
                  key={item}
                  className={cn(
                    "flex items-center gap-3 rounded-2xl border px-4 py-3 text-sm",
                    state === "completed"
                      ? "border-cyan-200/35 bg-cyan-200/15 text-white"
                      : state === "active"
                        ? "border-white/35 bg-white/15 text-white"
                        : "border-white/10 bg-white/5 text-sky-100/75",
                  )}
                >
                  <span className="inline-flex h-7 w-7 items-center justify-center rounded-full bg-white/15 text-xs font-semibold">
                    {index + 1}
                  </span>
                  <span className="font-medium">{progressStageLabel(item)}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          {infoTiles.map((item) => (
            <div key={`${item.label}-${item.value}`} className="rounded-2xl border border-white/10 bg-white/6 p-4 backdrop-blur">
              <p className="text-xs uppercase tracking-[0.14em] text-sky-100/80">{item.label}</p>
              <p className="mt-2 text-base font-semibold text-white">{item.value}</p>
            </div>
          ))}
        </div>
        <div className="text-sm text-sky-100/80">{runtimeCaption}</div>
        {historyRows.length ? (
          <div className="space-y-3">
            <div className="text-sm font-medium text-white">最近处理轨迹</div>
            <div className="grid gap-3 lg:grid-cols-5">
              {historyRows.map((row, index) => {
                const nextRow = safeObject(row);
                return (
                  <div key={`${nextRow.timestamp || index}`} className="rounded-2xl border border-white/10 bg-white/6 p-4">
                    <div className="flex items-center justify-between gap-3 text-xs text-sky-100/70">
                      <span>{formatDateTimeText(nextRow.timestamp)}</span>
                      <span>{safeNumber(nextRow.progress_percent, 0)}%</span>
                    </div>
                    <div className="mt-3 text-sm font-semibold text-white">
                      {progressStageLabel(normalizeProgressStage(nextRow))}
                    </div>
                    <div className="mt-2 text-xs leading-5 text-sky-100/78">
                      {compactStageText(nextRow.message || nextRow.current_stage)}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function SimpleLineChart({
  title,
  description,
  rows,
  xKey,
  yKey,
  seriesKey,
  thresholdLines = [],
  maxHeight = 320,
}: {
  title: string;
  description?: string;
  rows: AnyRecord[];
  xKey: string;
  yKey: string;
  seriesKey?: string;
  thresholdLines?: Array<{ label: string; value: number; color: string; dash?: string }>;
  maxHeight?: number;
}) {
  const clipId = useId().replace(/:/g, "");
  const normalized = useMemo(() => {
    const filtered = rows
      .map((row) => ({
        row,
        xLabel: String(row[xKey] ?? "-"),
        y: safeNumber(row[yKey], Number.NaN),
        series: String(seriesKey ? row[seriesKey] ?? "Default" : "Default"),
      }))
      .filter((row) => Number.isFinite(row.y));

    if (!filtered.length) {
      return null;
    }

    const xLabels = Array.from(new Set(filtered.map((row) => row.xLabel)));
    const xIndexMap = new Map(xLabels.map((label, index) => [label, index]));
    const grouped = new Map<string, Array<{ xIndex: number; xLabel: string; y: number; row: AnyRecord }>>();

    filtered.forEach((item) => {
      const bucket = grouped.get(item.series) ?? [];
      bucket.push({
        xIndex: xIndexMap.get(item.xLabel) ?? 0,
        xLabel: item.xLabel,
        y: item.y,
        row: item.row,
      });
      grouped.set(item.series, bucket);
    });

    const seriesList = Array.from(grouped.entries()).map(([name, points], index) => {
      const sorted = [...points].sort((left, right) => left.xIndex - right.xIndex);
      return {
        name,
        color: palette(index),
        points: sorted,
        pointMap: new Map(sorted.map((point) => [point.xIndex, point])),
      };
    });

    const allValues = filtered.map((item) => item.y);
    return {
      xLabels,
      seriesList,
      yMin: Math.min(...allValues),
      yMax: Math.max(...allValues),
    };
  }, [rows, seriesKey, xKey, yKey]);

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<{
    mode: "pan" | "brush";
    pointerId: number;
    startDomain: [number, number];
    startSvgX: number;
  } | null>(null);

  const [hiddenSeries, setHiddenSeries] = useState<string[]>([]);
  const [viewport, setViewport] = useState<[number, number] | null>(null);
  const [brushRange, setBrushRange] = useState<[number, number] | null>(null);
  const [tooltip, setTooltip] = useState<{
    left: number;
    top: number;
    xIndex: number;
    xLabel: string;
    entries: Array<{ name: string; color: string; y: number; row: AnyRecord }>;
  } | null>(null);

  const width = 980;
  const height = Math.max(280, maxHeight);
  const margin = { top: 24, right: 24, bottom: 68, left: 64 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  if (!normalized) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可绘制的折线数据。</p>
        </CardContent>
      </Card>
    );
  }

  const chartData = normalized;
  const totalMaxIndex = Math.max(0, chartData.xLabels.length - 1);
  const domain = clampViewport(
    viewport?.[0] ?? 0,
    viewport?.[1] ?? totalMaxIndex,
    0,
    Math.max(totalMaxIndex, 0.0001),
    totalMaxIndex > 0 ? 1 : 0.0001,
  );
  const domainSpan = Math.max(domain[1] - domain[0], 0.0001);
  const hiddenSet = new Set(hiddenSeries);
  const visibleSeries = chartData.seriesList.filter((series) => !hiddenSet.has(series.name));

  const visiblePoints = visibleSeries.flatMap((series) =>
    series.points.filter((point) => point.xIndex >= Math.floor(domain[0]) && point.xIndex <= Math.ceil(domain[1])),
  );
  const thresholdValues = thresholdLines
    .map((line) => safeNumber(line.value, Number.NaN))
    .filter((value) => Number.isFinite(value));
  const rawYMin = visiblePoints.length ? Math.min(...visiblePoints.map((point) => point.y), ...thresholdValues) : Math.min(chartData.yMin, ...thresholdValues);
  const rawYMax = visiblePoints.length ? Math.max(...visiblePoints.map((point) => point.y), ...thresholdValues) : Math.max(chartData.yMax, ...thresholdValues);
  const yPadding = rawYMax === rawYMin ? 1 : Math.max((rawYMax - rawYMin) * 0.08, 0.001);
  const yMin = rawYMin - yPadding;
  const yMax = rawYMax + yPadding;
  const yTicks = createLinearTicks(yMin, yMax, 5);
  const xTickSource = chartData.xLabels
    .map((label, index) => ({ label, index }))
    .filter((item) => item.index >= Math.floor(domain[0]) && item.index <= Math.ceil(domain[1]));
  const xTicks = pickVisibleTicks(xTickSource, Math.max(2, Math.floor(plotWidth / 100)));
  const rotateLabels = xTicks.length > 6 || xTicks.some((item) => item.label.length > 8);

  const xPos = (index: number) => margin.left + ((index - domain[0]) / domainSpan) * plotWidth;
  const yPos = (value: number) => margin.top + plotHeight - ((value - yMin) / Math.max(yMax - yMin, 0.0001)) * plotHeight;

  function setClampedViewport(nextStart: number, nextEnd: number) {
    startTransition(() => {
      setViewport(
        clampViewport(
          nextStart,
          nextEnd,
          0,
          Math.max(totalMaxIndex, 0.0001),
          totalMaxIndex > 0 ? 1 : 0.0001,
        ),
      );
    });
  }

  function readSvgPosition(event: { currentTarget: EventTarget & Element; clientX: number; clientY: number }) {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    const svgY = ((event.clientY - rect.top) / rect.height) * height;
    return {
      svgX: clamp(svgX, margin.left, width - margin.right),
      svgY: clamp(svgY, margin.top, height - margin.bottom),
      clientX: event.clientX,
      clientY: event.clientY,
    };
  }

  function syncTooltip(clientX: number, clientY: number, svgX: number) {
    if (!visibleSeries.length || !wrapperRef.current) {
      setTooltip(null);
      return;
    }
    const ratio = clamp((svgX - margin.left) / Math.max(plotWidth, 1), 0, 1);
    const xIndex = clamp(Math.round(domain[0] + ratio * domainSpan), 0, totalMaxIndex);
    const entries = visibleSeries
      .map((series) => {
        const point = series.pointMap.get(xIndex);
        return point
          ? { name: series.name, color: series.color, y: point.y, row: point.row }
          : null;
      })
      .filter((value): value is { name: string; color: string; y: number; row: AnyRecord } => Boolean(value))
      .sort((left, right) => right.y - left.y);

    if (!entries.length) {
      setTooltip(null);
      return;
    }

    const containerRect = wrapperRef.current.getBoundingClientRect();
    setTooltip({
      left: clientX - containerRect.left + 14,
      top: clientY - containerRect.top + 14,
      xIndex,
      xLabel: chartData.xLabels[xIndex] ?? "-",
      entries,
    });
  }

  function handleWheel(event: ReactWheelEvent<SVGRectElement>) {
    event.preventDefault();
    if (totalMaxIndex <= 0) {
      return;
    }
    const { svgX } = readSvgPosition(event);
    const anchor = clamp((svgX - margin.left) / Math.max(plotWidth, 1), 0, 1);
    const zoomFactor = event.deltaY > 0 ? 1.18 : 0.82;
    const nextSpan = clamp(domainSpan * zoomFactor, 1, Math.max(totalMaxIndex, 1));
    const center = domain[0] + anchor * domainSpan;
    setClampedViewport(center - anchor * nextSpan, center + (1 - anchor) * nextSpan);
    syncTooltip(event.clientX, event.clientY, svgX);
  }

  function handlePointerDown(event: ReactPointerEvent<SVGRectElement>) {
    if (totalMaxIndex <= 0) {
      return;
    }
    const { svgX } = readSvgPosition(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    gestureRef.current = {
      mode: event.shiftKey ? "brush" : "pan",
      pointerId: event.pointerId,
      startDomain: domain,
      startSvgX: svgX,
    };
    if (event.shiftKey) {
      setBrushRange([svgX, svgX]);
    }
    syncTooltip(event.clientX, event.clientY, svgX);
  }

  function handlePointerMove(event: ReactPointerEvent<SVGRectElement>) {
    const { svgX, clientX, clientY } = readSvgPosition(event);
    const gesture = gestureRef.current;
    if (gesture && gesture.pointerId === event.pointerId) {
      if (gesture.mode === "pan") {
        const delta = ((svgX - gesture.startSvgX) / Math.max(plotWidth, 1)) * domainSpan;
        setClampedViewport(gesture.startDomain[0] - delta, gesture.startDomain[1] - delta);
      } else {
        setBrushRange([gesture.startSvgX, svgX]);
      }
    }
    syncTooltip(clientX, clientY, svgX);
  }

  function finishGesture(event: ReactPointerEvent<SVGRectElement>) {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) {
      return;
    }
    if (gesture.mode === "brush" && brushRange) {
      const left = Math.min(brushRange[0], brushRange[1]);
      const right = Math.max(brushRange[0], brushRange[1]);
      if (right - left > 14) {
        const leftRatio = clamp((left - margin.left) / Math.max(plotWidth, 1), 0, 1);
        const rightRatio = clamp((right - margin.left) / Math.max(plotWidth, 1), 0, 1);
        const nextStart = domain[0] + leftRatio * domainSpan;
        const nextEnd = domain[0] + rightRatio * domainSpan;
        setClampedViewport(nextStart, nextEnd);
      }
    }
    event.currentTarget.releasePointerCapture(event.pointerId);
    gestureRef.current = null;
    setBrushRange(null);
  }

  function resetView() {
    startTransition(() => {
      setViewport(null);
      setHiddenSeries([]);
      setBrushRange(null);
    });
  }

  function toggleSeries(name: string) {
    startTransition(() => {
      setHiddenSeries((current) =>
        current.includes(name) ? current.filter((item) => item !== name) : [...current, name],
      );
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--muted)]/18 px-4 py-3 text-xs text-[var(--muted-foreground)]">
          <span>滚轮缩放，Shift + 拖拽框选，拖拽平移，悬浮查看详细值</span>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={resetView}>重置视图</Button>
            {hiddenSeries.length ? (
              <Button variant="secondary" size="sm" onClick={() => startTransition(() => setHiddenSeries([]))}>
                恢复全部系列
              </Button>
            ) : null}
          </div>
        </div>
        <div ref={wrapperRef} className="relative overflow-hidden rounded-2xl border border-[var(--border)] bg-[var(--muted)]/18 p-3">
          <svg className="w-full" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
            <defs>
              <clipPath id={`line-plot-${clipId}`}>
                <rect x={margin.left} y={margin.top} width={plotWidth} height={plotHeight} rx="12" ry="12" />
              </clipPath>
            </defs>
            <line x1={margin.left} x2={margin.left} y1={margin.top} y2={height - margin.bottom} stroke="rgba(16,36,61,0.18)" />
            <line x1={margin.left} x2={width - margin.right} y1={height - margin.bottom} y2={height - margin.bottom} stroke="rgba(16,36,61,0.18)" />
            {yTicks.map((tick) => {
              const y = yPos(tick);
              return (
                <g key={`${title}-y-${tick}`}>
                  <line x1={margin.left} x2={width - margin.right} y1={y} y2={y} stroke="rgba(16,36,61,0.08)" />
                  <text x={margin.left - 10} y={y + 4} textAnchor="end" fontSize="11" fill="rgba(16,36,61,0.62)">
                    {formatNumericTick(tick, yMax - yMin)}
                  </text>
                </g>
              );
            })}
            {thresholdLines
              .filter((line) => Number.isFinite(line.value))
              .map((line) => {
                const y = yPos(line.value);
                return (
                  <g key={`${title}-${line.label}`}>
                    <line
                      x1={margin.left}
                      x2={width - margin.right}
                      y1={y}
                      y2={y}
                      stroke={line.color}
                      strokeDasharray={line.dash || "6 6"}
                      strokeWidth="1.5"
                    />
                    <text x={width - margin.right} y={y - 6} textAnchor="end" fontSize="11" fill={line.color}>
                      {line.label}: {formatNumericTick(line.value, yMax - yMin)}
                    </text>
                  </g>
                );
              })}
            {visibleSeries.map((series) => {
              const linePoints = series.points.filter(
                (point) => point.xIndex >= Math.floor(domain[0]) - 1 && point.xIndex <= Math.ceil(domain[1]) + 1,
              );
              const markerPoints = series.points.filter(
                (point) => point.xIndex >= domain[0] && point.xIndex <= domain[1],
              );
              const path = linePoints
                .map((point, index) => `${index === 0 ? "M" : "L"} ${xPos(point.xIndex)} ${yPos(point.y)}`)
                .join(" ");
              return (
                <g key={`${title}-${series.name}`} clipPath={`url(#line-plot-${clipId})`} opacity={1}>
                  {path ? (
                    <path
                      d={path}
                      fill="none"
                      stroke={series.color}
                      strokeWidth="3"
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      vectorEffect="non-scaling-stroke"
                    />
                  ) : null}
                  {markerPoints.map((point) => {
                    const active = tooltip?.xIndex === point.xIndex;
                    return (
                      <circle
                        key={`${series.name}-${point.xIndex}-${point.y}`}
                        cx={xPos(point.xIndex)}
                        cy={yPos(point.y)}
                        r={active ? 5.5 : 4}
                        fill={series.color}
                        stroke={active ? "white" : "none"}
                        strokeWidth={active ? 1.5 : 0}
                      >
                        <title>{`${series.name} | ${point.xLabel} | ${point.y}`}</title>
                      </circle>
                    );
                  })}
                </g>
              );
            })}
            {xTicks.map((item) => (
              <g key={`${title}-x-${item.index}`}>
                <line x1={xPos(item.index)} x2={xPos(item.index)} y1={margin.top} y2={height - margin.bottom} stroke="rgba(16,36,61,0.04)" />
                <text
                  x={xPos(item.index)}
                  y={height - 18}
                  textAnchor={rotateLabels ? "end" : "middle"}
                  fontSize="11"
                  fill="rgba(16,36,61,0.65)"
                  transform={rotateLabels ? `rotate(-32 ${xPos(item.index)} ${height - 18})` : undefined}
                >
                  {shortText(item.label, rotateLabels ? 16 : 20)}
                </text>
              </g>
            ))}
            {brushRange ? (
              <rect
                x={Math.min(brushRange[0], brushRange[1])}
                y={margin.top}
                width={Math.abs(brushRange[1] - brushRange[0])}
                height={plotHeight}
                fill="rgba(11,92,173,0.12)"
                stroke="rgba(11,92,173,0.42)"
                strokeDasharray="6 4"
              />
            ) : null}
            <rect
              x={margin.left}
              y={margin.top}
              width={plotWidth}
              height={plotHeight}
              fill="transparent"
              onWheel={handleWheel}
              onPointerDown={handlePointerDown}
              onPointerMove={handlePointerMove}
              onPointerUp={finishGesture}
              onPointerCancel={finishGesture}
              onDoubleClick={resetView}
              onPointerLeave={() => {
                if (!gestureRef.current) {
                  setTooltip(null);
                }
              }}
            />
          </svg>
          {tooltip ? (
            <div
              className="pointer-events-none absolute z-10 min-w-[220px] rounded-2xl border border-slate-200/80 bg-white/95 px-4 py-3 text-xs shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)] backdrop-blur"
              style={{ left: Math.min(tooltip.left, 620), top: Math.min(tooltip.top, Math.max(maxHeight - 120, 120)) }}
            >
              <div className="font-semibold text-[var(--foreground)]">{tooltip.xLabel}</div>
              <div className="mt-2 space-y-2">
                {tooltip.entries.map((entry) => (
                  <div key={`${tooltip.xLabel}-${entry.name}`} className="flex items-start gap-2 text-[var(--foreground)]">
                    <span className="mt-1 h-2.5 w-2.5 rounded-full" style={{ backgroundColor: entry.color }} />
                    <div>
                      <div className="font-medium">{entry.name}</div>
                      <div className="text-[var(--muted-foreground)]">
                        {yKey}: {formatNumericTick(entry.y, yMax - yMin)}
                      </div>
                      <div className="text-[var(--muted-foreground)]">
                        {xKey}: {tooltip.xLabel}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        {chartData.seriesList.length > 1 ? (
          <div className="flex flex-wrap gap-2">
            {chartData.seriesList.map((series) => {
              const active = !hiddenSet.has(series.name);
              return (
                <button
                  key={`${title}-${series.name}-legend`}
                  type="button"
                  onClick={() => toggleSeries(series.name)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition",
                    active
                      ? "border-[var(--accent)] bg-[color:rgba(11,92,173,0.08)] text-[var(--foreground)]"
                      : "border-[var(--border)] bg-[var(--card)] text-[var(--muted-foreground)] opacity-70",
                  )}
                >
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: series.color }} />
                  <span>{series.name}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

type TimelineChartProps = {
  title: string;
  description?: string;
  rows: AnyRecord[];
  errors?: AnyRecord[];
  orderMode?: "default" | "cycle";
  resetKey?: string;
};

function StreamlitTimelineChart({
  title,
  description,
  rows,
  errors = [],
  orderMode = "default",
  resetKey,
}: TimelineChartProps) {
  const clipId = useId().replace(/:/g, "");
  const normalized = useMemo(() => {
    const bars = rows
      .map((row) => {
        const startMs =
          parseTimelineValue(row.start ?? row.start_time_sec ?? row.start_time_text ?? row.start_time ?? row.start_epoch_ms) ??
          parseTimelineValue(row.start_time);
        const endMs =
          parseTimelineValue(row.end ?? row.end_time_sec ?? row.end_time_text ?? row.end_time ?? row.end_epoch_ms) ??
          parseTimelineValue(row.end_time);
        const track = String(
          row.track || `${row.component || row.module || "Unknown"} | Cycle ${row.cycle_no ?? "NA"}`,
        );
        const series = String(row.sub_step || row.message || row.component || row.module || "Segment");
        const cycleValue = Number(row.cycle_no);
        return {
          ...row,
          startMs,
          endMs,
          track,
          baseTrack: timelineBaseTrack(track) || track,
          label: series,
          series,
          color: timelineColor(series),
          cycleSort: Number.isFinite(cycleValue) ? cycleValue : Number.POSITIVE_INFINITY,
        };
      })
      .filter(
        (row): row is typeof row & { startMs: number; endMs: number } =>
          row.startMs !== null && row.endMs !== null && row.endMs >= row.startMs,
      )
      .sort((left, right) => {
        if (orderMode === "cycle") {
          return (
            left.cycleSort - right.cycleSort ||
            left.startMs - right.startMs ||
            compareDisplayValues(left.track, right.track)
          );
        }
        return (
          left.startMs - right.startMs ||
          left.cycleSort - right.cycleSort ||
          compareDisplayValues(left.track, right.track)
        );
      }) as Array<
        AnyRecord & {
          startMs: number;
          endMs: number;
          track: string;
          baseTrack: string;
          label: string;
          series: string;
          color: string;
          cycleSort: number;
        }
      >;

    const points = errors
      .map((row) => {
        const timeMs =
          parseTimelineValue(row.time ?? row.formatted_ms ?? row.time_text ?? row.epoch_ms ?? row.start) ??
          parseTimelineValue(row.start_time_sec);
        const track = String(
          row.track || `${row.component || row.module || "Unknown"} | Cycle ${row.cycle_no ?? "NA"}`,
        );
        const cycleValue = Number(row.cycle_no);
        return {
          ...row,
          timeMs,
          track,
          baseTrack: timelineBaseTrack(track) || track,
          severity: String(row.severity || "unknown"),
          cycleSort: Number.isFinite(cycleValue) ? cycleValue : Number.POSITIVE_INFINITY,
        };
      })
      .filter((row): row is typeof row & { timeMs: number } => row.timeMs !== null)
      .sort((left, right) => {
        if (orderMode === "cycle") {
          return (
            left.cycleSort - right.cycleSort ||
            left.timeMs - right.timeMs ||
            compareDisplayValues(left.track, right.track)
          );
        }
        return (
          left.timeMs - right.timeMs ||
          left.cycleSort - right.cycleSort ||
          compareDisplayValues(left.track, right.track)
        );
      }) as Array<
        AnyRecord & {
          timeMs: number;
          track: string;
          baseTrack: string;
          severity: string;
          cycleSort: number;
        }
      >;

    if (!bars.length && !points.length) {
      return null;
    }

    const seriesMap = new Map<
      string,
      {
        name: string;
        color: string;
        count: number;
      }
    >();
    const tracksMap = new Map<
      string,
      {
        track: string;
        baseTrack: string;
        bars: typeof bars;
        errors: typeof points;
        cycles: Set<string>;
        firstStart: number;
        minCycle: number;
        orderIndex: number;
      }
    >();
    let nextOrderIndex = 0;

    bars.forEach((row) => {
      const track =
        tracksMap.get(row.track) ??
        {
          track: row.track,
          baseTrack: row.baseTrack,
          bars: [] as typeof bars,
          errors: [] as typeof points,
          cycles: new Set<string>(),
          firstStart: row.startMs,
          minCycle: row.cycleSort,
          orderIndex: nextOrderIndex++,
        };
      track.bars.push(row);
      track.firstStart = Math.min(track.firstStart, row.startMs);
      track.minCycle = Math.min(track.minCycle, row.cycleSort);
      track.cycles.add(row.cycle_no === null || row.cycle_no === undefined ? "NA" : String(row.cycle_no));
      tracksMap.set(row.track, track);

      const series = seriesMap.get(row.series) ?? {
        name: row.series,
        color: row.color,
        count: 0,
      };
      series.count += 1;
      seriesMap.set(row.series, series);
    });

    points.forEach((row) => {
      const track =
        tracksMap.get(row.track) ??
        {
          track: row.track,
          baseTrack: row.baseTrack,
          bars: [] as typeof bars,
          errors: [] as typeof points,
          cycles: new Set<string>(),
          firstStart: row.timeMs,
          minCycle: row.cycleSort,
          orderIndex: nextOrderIndex++,
        };
      track.errors.push(row);
      track.firstStart = Math.min(track.firstStart, row.timeMs);
      track.minCycle = Math.min(track.minCycle, row.cycleSort);
      track.cycles.add(row.cycle_no === null || row.cycle_no === undefined ? "NA" : String(row.cycle_no));
      tracksMap.set(row.track, track);
    });

    const minTime = Math.min(
      ...(bars.length ? bars.map((row) => row.startMs) : []),
      ...(points.length ? points.map((row) => row.timeMs) : []),
    );
    const maxTime = Math.max(
      ...(bars.length ? bars.map((row) => row.endMs) : []),
      ...(points.length ? points.map((row) => row.timeMs) : []),
    );
    const tracks = Array.from(tracksMap.values()).sort((left, right) => {
      if (orderMode === "cycle") {
        return (
          left.minCycle - right.minCycle ||
          left.firstStart - right.firstStart ||
          left.orderIndex - right.orderIndex ||
          compareDisplayValues(left.track, right.track)
        );
      }
      return (
        left.firstStart - right.firstStart ||
        left.minCycle - right.minCycle ||
        left.orderIndex - right.orderIndex ||
        compareDisplayValues(left.track, right.track)
      );
    });

    return {
      minTime,
      maxTime: maxTime === minTime ? minTime + 1 : maxTime,
      tracks,
      seriesList: Array.from(seriesMap.values()),
    };
  }, [errors, orderMode, rows]);

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<{
    mode: "pan" | "brush";
    pointerId: number;
    startDomain: [number, number];
    startSvgX: number;
  } | null>(null);

  const [hiddenSeries, setHiddenSeries] = useState<string[]>([]);
  const [viewport, setViewport] = useState<[number, number] | null>(null);
  const [brushRange, setBrushRange] = useState<[number, number] | null>(null);
  const [activeTrack, setActiveTrack] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{
    left: number;
    top: number;
    title: string;
    subtitle?: string;
    rows: Array<{ label: string; value: string }>;
  } | null>(null);

  useEffect(() => {
    gestureRef.current = null;
    setViewport(null);
    setHiddenSeries([]);
    setBrushRange(null);
    setActiveTrack(null);
    setTooltip(null);
  }, [resetKey]);

  if (!normalized) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可绘制的时间轴片段。</p>
        </CardContent>
      </Card>
    );
  }

  const timelineData = normalized;
  const fullSpan = Math.max(timelineData.maxTime - timelineData.minTime, 1);
  const minViewportSpan = Math.min(Math.max(fullSpan / 150, 100), fullSpan);
  const domain = clampViewport(
    viewport?.[0] ?? timelineData.minTime,
    viewport?.[1] ?? timelineData.maxTime,
    timelineData.minTime,
    timelineData.maxTime,
    minViewportSpan,
  );
  const domainSpan = Math.max(domain[1] - domain[0], 1);
  const hiddenSet = new Set(hiddenSeries);
  const visibleTracks = timelineData.tracks
    .map((track) => ({
      ...track,
      visibleBars: track.bars.filter((bar) => !hiddenSet.has(bar.series)),
    }))
    .filter((track) => track.visibleBars.length || track.errors.length);
  const width = 1320;
  const margin = { top: 30, right: 28, bottom: 86, left: 280 };
  const plotWidth = width - margin.left - margin.right;
  const trackBandHeight = 40;
  const trackGap = 12;
  const plotHeight = Math.max(
    visibleTracks.length * trackBandHeight + Math.max(visibleTracks.length - 1, 0) * trackGap,
    280,
  );
  const height = margin.top + plotHeight + margin.bottom;
  const timeTicks = createLinearTicks(domain[0], domain[1], Math.max(4, Math.floor(plotWidth / 170)));
  const rotateLabels = timeTicks.length > 7;

  function xPos(timeMs: number) {
    return margin.left + ((timeMs - domain[0]) / domainSpan) * plotWidth;
  }

  function setClampedViewport(nextStart: number, nextEnd: number) {
    startTransition(() => {
      setViewport(
        clampViewport(
          nextStart,
          nextEnd,
          timelineData.minTime,
          timelineData.maxTime,
          minViewportSpan,
        ),
      );
    });
  }

  function readSvgPosition(event: { currentTarget: EventTarget & Element; clientX: number; clientY: number }) {
    const rect = event.currentTarget.getBoundingClientRect();
    const svgX = ((event.clientX - rect.left) / rect.width) * width;
    return {
      svgX: clamp(svgX, margin.left, width - margin.right),
      clientX: event.clientX,
      clientY: event.clientY,
    };
  }

  function toggleSeries(seriesName: string) {
    startTransition(() => {
      setHiddenSeries((current) =>
        current.includes(seriesName)
          ? current.filter((item) => item !== seriesName)
          : [...current, seriesName],
      );
    });
  }

  function resetView() {
    startTransition(() => {
      setViewport(null);
      setHiddenSeries([]);
      setBrushRange(null);
    });
    setActiveTrack(null);
    setTooltip(null);
  }

  function openTooltip(
    event: { clientX: number; clientY: number },
    titleText: string,
    subtitle: string | undefined,
    items: Array<{ label: string; value: string }>,
  ) {
    if (!wrapperRef.current) {
      return;
    }
    const rect = wrapperRef.current.getBoundingClientRect();
    setTooltip({
      left: event.clientX - rect.left + 14,
      top: event.clientY - rect.top + 14,
      title: titleText,
      subtitle,
      rows: items,
    });
  }

  function handleWheel(event: ReactWheelEvent<SVGRectElement>) {
    event.preventDefault();
    const { svgX } = readSvgPosition(event);
    const ratio = clamp((svgX - margin.left) / Math.max(plotWidth, 1), 0, 1);
    const zoomFactor = event.deltaY > 0 ? 1.18 : 0.82;
    const nextSpan = clamp(domainSpan * zoomFactor, minViewportSpan, fullSpan);
    const center = domain[0] + ratio * domainSpan;
    setClampedViewport(center - ratio * nextSpan, center + (1 - ratio) * nextSpan);
  }

  function handlePointerDown(event: ReactPointerEvent<SVGRectElement>) {
    const { svgX } = readSvgPosition(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    gestureRef.current = {
      mode: event.shiftKey ? "brush" : "pan",
      pointerId: event.pointerId,
      startDomain: domain,
      startSvgX: svgX,
    };
    if (event.shiftKey) {
      setBrushRange([svgX, svgX]);
    }
  }

  function handlePointerMove(event: ReactPointerEvent<SVGRectElement>) {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) {
      return;
    }
    const { svgX } = readSvgPosition(event);
    if (gesture.mode === "pan") {
      const deltaTime = ((svgX - gesture.startSvgX) / Math.max(plotWidth, 1)) * domainSpan;
      setClampedViewport(gesture.startDomain[0] - deltaTime, gesture.startDomain[1] - deltaTime);
    } else {
      setBrushRange([gesture.startSvgX, svgX]);
    }
  }

  function finishGesture(event: ReactPointerEvent<SVGRectElement>) {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) {
      return;
    }
    if (gesture.mode === "brush" && brushRange) {
      const left = Math.min(brushRange[0], brushRange[1]);
      const right = Math.max(brushRange[0], brushRange[1]);
      if (right - left > 14) {
        const leftRatio = clamp((left - margin.left) / Math.max(plotWidth, 1), 0, 1);
        const rightRatio = clamp((right - margin.left) / Math.max(plotWidth, 1), 0, 1);
        const nextStart = domain[0] + leftRatio * domainSpan;
        const nextEnd = domain[0] + rightRatio * domainSpan;
        setClampedViewport(nextStart, nextEnd);
      }
    }
    event.currentTarget.releasePointerCapture(event.pointerId);
    gestureRef.current = null;
    setBrushRange(null);
  }

  function errorColor(severity: string) {
    switch (severity.toLowerCase()) {
      case "fatal":
        return "#9A2532";
      case "error":
        return "#D95D54";
      case "warn":
      case "warning":
        return "#D78A45";
      case "info":
        return "#5B88B7";
      default:
        return "#6B7280";
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[rgba(126,184,255,0.24)] bg-[linear-gradient(180deg,rgba(255,255,255,0.82),rgba(237,245,255,0.72))] px-4 py-3 text-xs text-[var(--muted-foreground)]">
          <span>滚轮缩放，Shift + 拖拽框选，拖拽平移，悬浮查看详细时间段</span>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={resetView}>重置视图</Button>
            {hiddenSeries.length ? (
              <Button variant="secondary" size="sm" onClick={() => startTransition(() => setHiddenSeries([]))}>
                恢复全部系列
              </Button>
            ) : null}
          </div>
        </div>
        {timelineData.seriesList.length ? (
          <div className="flex flex-wrap gap-2 rounded-2xl border border-[rgba(126,184,255,0.24)] bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(240,248,255,0.84))] p-3">
            {timelineData.seriesList.map((series) => {
              const active = !hiddenSet.has(series.name);
              return (
                <button
                  key={`${title}-${series.name}`}
                  type="button"
                  onClick={() => toggleSeries(series.name)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition",
                    active
                      ? "border-[rgba(69,128,212,0.34)] bg-[rgba(69,128,212,0.12)] text-[var(--foreground)]"
                      : "border-[var(--border)] bg-[var(--card)]/70 text-[var(--muted-foreground)] opacity-65",
                  )}
                >
                  <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: series.color }} />
                  <span>{shortText(series.name, 42)}</span>
                </button>
              );
            })}
          </div>
        ) : null}
        <div className="rounded-2xl border border-[rgba(126,184,255,0.22)] bg-[linear-gradient(180deg,rgba(255,255,255,0.9),rgba(239,247,255,0.78))] p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--muted-foreground)]">
            <span>起点 {formatTimelineAxisLabel(domain[0], fullSpan)}</span>
            <span>终点 {formatTimelineAxisLabel(domain[1], fullSpan)}</span>
            <span>轨道 {visibleTracks.length}</span>
            <span>错误点 {errors.length}</span>
          </div>
        </div>
        <div ref={wrapperRef} className="relative overflow-auto rounded-3xl border border-[rgba(126,184,255,0.24)] bg-[linear-gradient(180deg,rgba(255,255,255,0.96),rgba(239,247,255,0.88))] p-4">
          {visibleTracks.length ? (
            <svg className="min-w-[1080px] w-full" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
              <defs>
                <clipPath id={`timeline-plot-${clipId}`}>
                  <rect x={margin.left} y={margin.top} width={plotWidth} height={plotHeight} rx="16" ry="16" />
                </clipPath>
              </defs>
              <rect
                x={margin.left}
                y={margin.top}
                width={plotWidth}
                height={plotHeight}
                rx="18"
                ry="18"
                fill="rgba(255,255,255,0.72)"
                stroke="rgba(126,184,255,0.16)"
              />
              {timeTicks.map((tick) => {
                const x = xPos(tick);
                return (
                  <g key={`${title}-tick-${tick}`}>
                    <line x1={x} x2={x} y1={margin.top} y2={margin.top + plotHeight} stroke="rgba(17,52,94,0.08)" />
                    <text
                      x={x}
                      y={height - 18}
                      textAnchor={rotateLabels ? "end" : "middle"}
                      fontSize="11"
                      fill="rgba(16,36,61,0.7)"
                      transform={rotateLabels ? `rotate(-28 ${x} ${height - 18})` : undefined}
                    >
                      {formatTimelineAxisLabel(tick, fullSpan)}
                    </text>
                  </g>
                );
              })}
              {visibleTracks.map((track, index) => {
                const y = margin.top + index * (trackBandHeight + trackGap);
                const midY = y + trackBandHeight / 2;
                const highlighted = activeTrack === track.track;
                const muted = Boolean(activeTrack && activeTrack !== track.track);
                return (
                  <g key={`${title}-${track.track}`}>
                    <rect
                      x={margin.left}
                      y={y}
                      width={plotWidth}
                      height={trackBandHeight}
                      rx="12"
                      ry="12"
                      fill={highlighted ? "rgba(47,103,199,0.10)" : "rgba(47,103,199,0.035)"}
                      stroke={highlighted ? "rgba(47,103,199,0.24)" : "rgba(126,184,255,0.06)"}
                    />
                    <text
                      x={margin.left - 14}
                      y={midY + 4}
                      textAnchor="end"
                      fontSize="12"
                      fontWeight={highlighted ? "700" : "500"}
                      fill={highlighted ? "rgba(15,39,66,0.98)" : "rgba(16,36,61,0.86)"}
                    >
                      {shortText(track.track, 34)}
                    </text>
                    <g clipPath={`url(#timeline-plot-${clipId})`} opacity={muted ? 0.32 : 1}>
                      {track.visibleBars.map((row, barIndex) => {
                        if (row.endMs < domain[0] || row.startMs > domain[1]) {
                          return null;
                        }
                        const visibleStart = Math.max(row.startMs, domain[0]);
                        const visibleEnd = Math.min(row.endMs, domain[1]);
                        const x = xPos(visibleStart);
                        const barWidth = Math.max(xPos(visibleEnd) - x, 3);
                        const barY = y + (trackBandHeight - 18) / 2;
                        return (
                          <g
                            key={`${track.track}-${row.series}-${barIndex}`}
                            onMouseEnter={(event) => {
                              setActiveTrack(track.track);
                              openTooltip(event, row.label, track.track, [
                                { label: "开始", value: formatDateTimeText(row.start ?? row.start_time_sec ?? row.startMs) },
                                { label: "结束", value: formatDateTimeText(row.end ?? row.end_time_sec ?? row.endMs) },
                                { label: "时长", value: formatDurationText(safeNumber(row.duration_ms, row.endMs - row.startMs) / 1000) },
                                { label: "Cycle", value: toDisplayValue(row.cycle_no) },
                                { label: "组件", value: toDisplayValue(row.component || row.module || row.baseTrack) },
                              ]);
                            }}
                            onMouseMove={(event) => {
                              setActiveTrack(track.track);
                              openTooltip(event, row.label, track.track, [
                                { label: "开始", value: formatDateTimeText(row.start ?? row.start_time_sec ?? row.startMs) },
                                { label: "结束", value: formatDateTimeText(row.end ?? row.end_time_sec ?? row.endMs) },
                                { label: "时长", value: formatDurationText(safeNumber(row.duration_ms, row.endMs - row.startMs) / 1000) },
                                { label: "Cycle", value: toDisplayValue(row.cycle_no) },
                                { label: "组件", value: toDisplayValue(row.component || row.module || row.baseTrack) },
                              ]);
                            }}
                            onMouseLeave={() => {
                              setTooltip(null);
                              setActiveTrack((current) => (current === track.track ? null : current));
                            }}
                            style={{ cursor: "pointer" }}
                          >
                            <rect
                              x={x}
                              y={barY}
                              width={barWidth}
                              height={18}
                              rx="5"
                              ry="5"
                              fill={row.color}
                              opacity={0.95}
                            />
                            {barWidth > 64 ? (
                              <text x={x + 8} y={barY + 12} fontSize="10.5" fill="white">
                                {shortText(row.label, 28)}
                              </text>
                            ) : null}
                          </g>
                        );
                      })}
                      {track.errors.map((row, errorIndex) => {
                        if (row.timeMs < domain[0] || row.timeMs > domain[1]) {
                          return null;
                        }
                        const x = xPos(row.timeMs);
                        const size = 10;
                        return (
                          <g
                            key={`${track.track}-error-${errorIndex}`}
                            onMouseEnter={(event) => {
                              setActiveTrack(track.track);
                              openTooltip(event, String(row.normalized_signature || row.message || "Error Point"), track.track, [
                                { label: "时间", value: toDisplayValue(row.time_text || formatDateTimeText(row.time ?? row.timeMs)) },
                                { label: "严重级别", value: toDisplayValue(row.severity) },
                                { label: "错误家族", value: toDisplayValue(row.error_family_display || row.error_family) },
                                { label: "组件", value: toDisplayValue(row.component || row.module || row.baseTrack) },
                              ]);
                            }}
                            onMouseMove={(event) => {
                              setActiveTrack(track.track);
                              openTooltip(event, String(row.normalized_signature || row.message || "Error Point"), track.track, [
                                { label: "时间", value: toDisplayValue(row.time_text || formatDateTimeText(row.time ?? row.timeMs)) },
                                { label: "严重级别", value: toDisplayValue(row.severity) },
                                { label: "错误家族", value: toDisplayValue(row.error_family_display || row.error_family) },
                                { label: "组件", value: toDisplayValue(row.component || row.module || row.baseTrack) },
                              ]);
                            }}
                            onMouseLeave={() => {
                              setTooltip(null);
                              setActiveTrack((current) => (current === track.track ? null : current));
                            }}
                            style={{ cursor: "pointer" }}
                          >
                            <rect
                              x={x - size / 2}
                              y={midY - size / 2}
                              width={size}
                              height={size}
                              fill={errorColor(row.severity)}
                              stroke="white"
                              strokeWidth="1.4"
                              transform={`rotate(45 ${x} ${midY})`}
                            />
                          </g>
                        );
                      })}
                    </g>
                  </g>
                );
              })}
              <line x1={margin.left} x2={margin.left} y1={margin.top} y2={margin.top + plotHeight} stroke="rgba(16,36,61,0.2)" />
              <line x1={margin.left} x2={width - margin.right} y1={margin.top + plotHeight} y2={margin.top + plotHeight} stroke="rgba(16,36,61,0.2)" />
              <text
                x={30}
                y={margin.top + plotHeight / 2}
                transform={`rotate(-90 30 ${margin.top + plotHeight / 2})`}
                fontSize="13"
                fontWeight="600"
                fill="rgba(16,36,61,0.9)"
              >
                track
              </text>
              {brushRange ? (
                <rect
                  x={Math.min(brushRange[0], brushRange[1])}
                  y={margin.top}
                  width={Math.abs(brushRange[1] - brushRange[0])}
                  height={plotHeight}
                  fill="rgba(47,103,199,0.12)"
                  stroke="rgba(47,103,199,0.42)"
                  strokeDasharray="6 4"
                />
              ) : null}
              <rect
                x={margin.left}
                y={margin.top}
                width={plotWidth}
                height={plotHeight}
                fill="transparent"
                onWheel={handleWheel}
                onPointerDown={handlePointerDown}
                onPointerMove={handlePointerMove}
                onPointerUp={finishGesture}
                onPointerCancel={finishGesture}
                onDoubleClick={resetView}
                onPointerLeave={() => {
                  if (!gestureRef.current) {
                    setTooltip(null);
                    setActiveTrack(null);
                  }
                }}
              />
            </svg>
          ) : (
            <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--muted)]/15 px-4 py-8 text-center text-sm text-[var(--muted-foreground)]">
              当前筛选条件下没有可展示的时间轴片段。
            </div>
          )}
          {tooltip ? (
            <div
              className="pointer-events-none absolute z-10 min-w-[240px] rounded-2xl border border-slate-200/80 bg-white/95 px-4 py-3 text-xs shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)] backdrop-blur"
              style={{ left: Math.min(tooltip.left, 840), top: Math.max(tooltip.top, 12) }}
            >
              <div className="font-semibold text-[var(--foreground)]">{tooltip.title}</div>
              {tooltip.subtitle ? <div className="mt-1 text-[var(--muted-foreground)]">{tooltip.subtitle}</div> : null}
              <div className="mt-3 space-y-2 text-[var(--foreground)]">
                {tooltip.rows.map((item) => (
                  <div key={`${tooltip.title}-${item.label}`} className="flex items-start justify-between gap-4">
                    <span className="text-[var(--muted-foreground)]">{item.label}</span>
                    <span className="text-right">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}

export function TimelineChart(props: TimelineChartProps) {
  const useLegacyRenderer = false;
  return useLegacyRenderer ? <LegacyTimelineChart {...props} /> : <StreamlitTimelineChart {...props} />;
}

function LegacyTimelineChart({
  title,
  description,
  rows,
  errors = [],
  orderMode = "default",
}: TimelineChartProps) {
  const normalized = useMemo(() => {
    const bars = rows
      .map((row) => {
        const startMs =
          parseTimelineValue(row.start ?? row.start_time_sec ?? row.start_time_text ?? row.start_time ?? row.start_epoch_ms) ??
          parseTimelineValue(row.start_time);
        const endMs =
          parseTimelineValue(row.end ?? row.end_time_sec ?? row.end_time_text ?? row.end_time ?? row.end_epoch_ms) ??
          parseTimelineValue(row.end_time);
        const rawTrack = String(
          row.track || `${row.component || row.module || "Unknown"} | Cycle ${row.cycle_no ?? "NA"}`,
        );
        const baseTrack = timelineBaseTrack(rawTrack) || rawTrack;
        return {
          ...row,
          startMs,
          endMs,
          rawTrack,
          baseTrack,
          groupTrack:
            cleanComponentTrackLabel(row.component || row.module) ||
            cleanComponentTrackLabel(baseTrack) ||
            "Unknown",
          lane: Math.max(1, timelineLaneIndex(rawTrack)),
          label: String(row.sub_step || row.message || row.component || row.module || "Segment"),
        };
      })
      .filter(
        (row): row is typeof row & { startMs: number; endMs: number } =>
          row.startMs !== null && row.endMs !== null && row.endMs >= row.startMs,
      )
      .sort((left, right) => left.startMs - right.startMs || left.endMs - right.endMs || left.lane - right.lane) as Array<
        AnyRecord & {
          startMs: number;
          endMs: number;
          rawTrack: string;
          baseTrack: string;
          lane: number;
          label: string;
        }
      >;

    if (!bars.length) {
      return null;
    }

    const points = errors
      .map((row) => {
        const timeMs =
          parseTimelineValue(row.time ?? row.formatted_ms ?? row.time_text ?? row.epoch_ms ?? row.start) ??
          parseTimelineValue(row.start_time_sec);
        const rawTrack = String(
          row.track || `${row.component || row.module || "Unknown"} | Cycle ${row.cycle_no ?? "NA"}`,
        );
        return {
          ...row,
          timeMs,
          rawTrack,
          baseTrack: timelineBaseTrack(rawTrack) || rawTrack,
          groupTrack:
            cleanComponentTrackLabel(row.component || row.module) ||
            cleanComponentTrackLabel(rawTrack) ||
            "Unknown",
          severity: String(row.severity || "unknown"),
        };
      })
      .filter((row): row is typeof row & { timeMs: number } => row.timeMs !== null)
      .sort((left, right) => left.timeMs - right.timeMs) as Array<
        AnyRecord & {
          timeMs: number;
          rawTrack: string;
          baseTrack: string;
          severity: string;
        }
      >;

    const groupsMap = new Map<
      string,
      {
        baseTrack: string;
        bars: typeof bars;
        errors: typeof points;
        laneCount: number;
        cycles: string[];
        firstStart: number;
        minCycle: number;
      }
    >();

    bars.forEach((row) => {
      const current =
        groupsMap.get(row.groupTrack) ??
        {
          baseTrack: row.groupTrack,
          bars: [] as typeof bars,
          errors: [] as typeof points,
          laneCount: 0,
          cycles: [] as string[],
          firstStart: row.startMs,
          minCycle: Number.isFinite(Number(row.cycle_no)) ? Number(row.cycle_no) : Number.POSITIVE_INFINITY,
        };
      current.bars.push(row);
      current.laneCount = Math.max(current.laneCount, row.lane);
      current.firstStart = Math.min(current.firstStart, row.startMs);
      if (Number.isFinite(Number(row.cycle_no))) {
        current.minCycle = Math.min(current.minCycle, Number(row.cycle_no));
      }
      const cycleLabel = row.cycle_no === null || row.cycle_no === undefined ? "NA" : String(row.cycle_no);
      if (!current.cycles.includes(cycleLabel)) {
        current.cycles.push(cycleLabel);
      }
      groupsMap.set(row.groupTrack, current);
    });

    points.forEach((point) => {
      const current =
        groupsMap.get(point.groupTrack) ??
        {
          baseTrack: point.groupTrack,
          bars: [] as typeof bars,
          errors: [] as typeof points,
          laneCount: 1,
          cycles: [] as string[],
          firstStart: point.timeMs,
          minCycle: Number.isFinite(Number(point.cycle_no)) ? Number(point.cycle_no) : Number.POSITIVE_INFINITY,
        };
      current.errors.push(point);
      current.firstStart = Math.min(current.firstStart, point.timeMs);
      if (Number.isFinite(Number(point.cycle_no))) {
        current.minCycle = Math.min(current.minCycle, Number(point.cycle_no));
      }
      const cycleLabel = point.cycle_no === null || point.cycle_no === undefined ? "NA" : String(point.cycle_no);
      if (!current.cycles.includes(cycleLabel)) {
        current.cycles.push(cycleLabel);
      }
      groupsMap.set(point.groupTrack, current);
    });

    const minTime = Math.min(...bars.map((row) => row.startMs), ...points.map((row) => row.timeMs));
    const maxTime = Math.max(...bars.map((row) => row.endMs), ...points.map((row) => row.timeMs));
    const groups = Array.from(groupsMap.values()).sort((left, right) => {
      if (orderMode === "cycle") {
        return (
          left.minCycle - right.minCycle ||
          left.firstStart - right.firstStart ||
          compareDisplayValues(left.baseTrack, right.baseTrack)
        );
      }
      return (
        left.firstStart - right.firstStart ||
        left.minCycle - right.minCycle ||
        compareDisplayValues(left.baseTrack, right.baseTrack)
      );
    });

    return {
      minTime,
      maxTime: maxTime === minTime ? minTime + 1 : maxTime,
      groups,
    };
  }, [errors, orderMode, rows]);

  const wrapperRef = useRef<HTMLDivElement | null>(null);
  const gestureRef = useRef<{
    mode: "pan" | "brush";
    pointerId: number;
    startDomain: [number, number];
    startClientX: number;
    startRatio: number;
  } | null>(null);

  const [hiddenTracks, setHiddenTracks] = useState<string[]>([]);
  const [viewport, setViewport] = useState<[number, number] | null>(null);
  const [brushRange, setBrushRange] = useState<[number, number] | null>(null);
  const [activeTrack, setActiveTrack] = useState<string | null>(null);
  const [tooltip, setTooltip] = useState<{
    left: number;
    top: number;
    title: string;
    subtitle?: string;
    rows: Array<{ label: string; value: string }>;
  } | null>(null);

  if (!normalized) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可绘制的时间轴片段。</p>
        </CardContent>
      </Card>
    );
  }

  const timelineData = normalized;
  const fullSpan = Math.max(timelineData.maxTime - timelineData.minTime, 1);
  const minViewportSpan = Math.min(Math.max(fullSpan / 150, 100), fullSpan);
  const domain = clampViewport(
    viewport?.[0] ?? timelineData.minTime,
    viewport?.[1] ?? timelineData.maxTime,
    timelineData.minTime,
    timelineData.maxTime,
    minViewportSpan,
  );
  const domainSpan = Math.max(domain[1] - domain[0], 1);
  const timeTicks = createLinearTicks(domain[0], domain[1], 8);
  const hiddenSet = new Set(hiddenTracks);
  const visibleGroups = timelineData.groups.filter((group) => !hiddenSet.has(group.baseTrack));

  function setClampedViewport(nextStart: number, nextEnd: number) {
    startTransition(() => {
      setViewport(
        clampViewport(
          nextStart,
          nextEnd,
          timelineData.minTime,
          timelineData.maxTime,
          minViewportSpan,
        ),
      );
    });
  }

  function readTrackPosition(event: { currentTarget: EventTarget & Element; clientX: number }) {
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = clamp((event.clientX - rect.left) / Math.max(rect.width, 1), 0, 1);
    return {
      ratio,
      clientX: event.clientX,
      rect,
    };
  }

  function toggleTrack(baseTrack: string) {
    startTransition(() => {
      setHiddenTracks((current) =>
        current.includes(baseTrack)
          ? current.filter((item) => item !== baseTrack)
          : [...current, baseTrack],
      );
    });
  }

  function resetView() {
    startTransition(() => {
      setViewport(null);
      setHiddenTracks([]);
      setBrushRange(null);
    });
    setActiveTrack(null);
    setTooltip(null);
  }

  function openTooltip(
    event: { clientX: number; clientY: number },
    titleText: string,
    subtitle: string | undefined,
    items: Array<{ label: string; value: string }>,
  ) {
    if (!wrapperRef.current) {
      return;
    }
    const rect = wrapperRef.current.getBoundingClientRect();
    setTooltip({
      left: event.clientX - rect.left + 14,
      top: event.clientY - rect.top + 14,
      title: titleText,
      subtitle,
      rows: items,
    });
  }

  function handleWheel(event: ReactWheelEvent<HTMLDivElement>) {
    event.preventDefault();
    const { ratio } = readTrackPosition(event);
    const zoomFactor = event.deltaY > 0 ? 1.18 : 0.82;
    const nextSpan = clamp(domainSpan * zoomFactor, minViewportSpan, fullSpan);
    const center = domain[0] + ratio * domainSpan;
    setClampedViewport(center - ratio * nextSpan, center + (1 - ratio) * nextSpan);
  }

  function handlePointerDown(event: ReactPointerEvent<HTMLDivElement>) {
    const { clientX, ratio } = readTrackPosition(event);
    event.currentTarget.setPointerCapture(event.pointerId);
    gestureRef.current = {
      mode: event.shiftKey ? "brush" : "pan",
      pointerId: event.pointerId,
      startDomain: domain,
      startClientX: clientX,
      startRatio: ratio,
    };
    if (event.shiftKey) {
      setBrushRange([ratio, ratio]);
    }
  }

  function handlePointerMove(event: ReactPointerEvent<HTMLDivElement>) {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) {
      return;
    }
    const { rect, clientX } = readTrackPosition(event);
    if (gesture.mode === "pan") {
      const deltaRatio = (clientX - gesture.startClientX) / Math.max(rect.width, 1);
      const deltaTime = deltaRatio * domainSpan;
      setClampedViewport(gesture.startDomain[0] - deltaTime, gesture.startDomain[1] - deltaTime);
    } else {
      setBrushRange([gesture.startRatio, clamp((clientX - rect.left) / Math.max(rect.width, 1), 0, 1)]);
    }
  }

  function finishGesture(event: ReactPointerEvent<HTMLDivElement>) {
    const gesture = gestureRef.current;
    if (!gesture || gesture.pointerId !== event.pointerId) {
      return;
    }
    if (gesture.mode === "brush" && brushRange) {
      const leftRatio = Math.min(brushRange[0], brushRange[1]);
      const rightRatio = Math.max(brushRange[0], brushRange[1]);
      if (rightRatio - leftRatio > 0.02) {
        const nextStart = domain[0] + leftRatio * domainSpan;
        const nextEnd = domain[0] + rightRatio * domainSpan;
        setClampedViewport(nextStart, nextEnd);
      }
    }
    event.currentTarget.releasePointerCapture(event.pointerId);
    gestureRef.current = null;
    setBrushRange(null);
  }

  function errorColor(severity: string) {
    switch (severity.toLowerCase()) {
      case "fatal":
        return "#8C1C13";
      case "error":
        return "#D94841";
      case "warn":
      case "warning":
        return "#D96B3B";
      case "info":
        return "#5B7C99";
      default:
        return "#6B7280";
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-[var(--border)] bg-[var(--muted)]/18 px-4 py-3 text-xs text-[var(--muted-foreground)]">
          <span>滚轮缩放，Shift + 拖拽框选，拖拽平移，悬浮查看详细时间段</span>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" size="sm" onClick={resetView}>重置视图</Button>
            {hiddenTracks.length ? (
              <Button variant="secondary" size="sm" onClick={() => startTransition(() => setHiddenTracks([]))}>
                恢复全部组件
              </Button>
            ) : null}
          </div>
        </div>
        <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/15 p-4">
          <div className="flex flex-wrap items-center justify-between gap-3 text-xs text-[var(--muted-foreground)]">
            <span>起点 {formatTimelineAxisLabel(domain[0], fullSpan)}</span>
            <span>终点 {formatTimelineAxisLabel(domain[1], fullSpan)}</span>
          </div>
          <div className="relative mt-4 h-12 overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--card)]/80">
            {timeTicks.map((tick) => {
              const left = ((tick - domain[0]) / domainSpan) * 100;
              return (
                <div key={`${title}-tick-${tick}`} className="absolute inset-y-0" style={{ left: `${left}%` }}>
                  <div className="h-full border-l border-[rgba(16,36,61,0.08)]" />
                  <div className="absolute left-1 top-1 rounded-full bg-white/90 px-2 py-1 text-[10px] text-[var(--muted-foreground)] shadow-sm">
                    {formatTimelineAxisLabel(tick, fullSpan)}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        <div ref={wrapperRef} className="relative space-y-3">
          {visibleGroups.length ? (
            visibleGroups.map((group) => {
              const laneHeight = 26;
              const laneGap = 8;
              const errorRailTop = 10;
              const laneStartTop = 34;
              const trackHeight = Math.max(86, laneStartTop + group.laneCount * laneHeight + Math.max(group.laneCount - 1, 0) * laneGap + 12);
              const highlighted = activeTrack === group.baseTrack;
              return (
                <div key={`${title}-${group.baseTrack}`} className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
                  <div className={cn(
                    "rounded-2xl border px-4 py-3 transition",
                    highlighted
                      ? "border-[var(--accent)] bg-[color:rgba(11,92,173,0.08)]"
                      : "border-[var(--border)] bg-[var(--muted)]/35",
                  )}>
                    <div className="text-sm font-semibold text-[var(--foreground)]">{group.baseTrack}</div>
                    <div className="mt-2 text-xs text-[var(--muted-foreground)]">
                      {group.bars.length} 个片段，{group.laneCount} 条 lane
                    </div>
                    <div className="mt-2 text-xs text-[var(--muted-foreground)]">
                      Cycle: {group.cycles.join(", ") || "NA"}
                    </div>
                  </div>
                  <div className={cn(
                    "relative overflow-hidden rounded-2xl border bg-[var(--card)] transition",
                    highlighted
                      ? "border-[var(--accent)] shadow-[0_20px_36px_-26px_rgba(11,92,173,0.45)]"
                      : "border-[var(--border)]",
                  )} style={{ height: trackHeight }} onMouseLeave={() => {
                    setTooltip(null);
                    setActiveTrack((current) => (current === group.baseTrack ? null : current));
                  }}>
                    {timeTicks.map((tick) => {
                      const left = ((tick - domain[0]) / domainSpan) * 100;
                      return (
                        <div key={`${group.baseTrack}-${tick}`} className="pointer-events-none absolute inset-y-0" style={{ left: `${left}%` }}>
                          <div className="h-full border-l border-[rgba(16,36,61,0.06)]" />
                        </div>
                      );
                    })}
                    <div className="pointer-events-none absolute inset-x-0 top-0 h-7 border-b border-[var(--border)] bg-[linear-gradient(180deg,rgba(217,107,59,0.08),rgba(217,107,59,0.02))]">
                      <div className="px-3 pt-2 text-[10px] font-medium uppercase tracking-[0.18em] text-[var(--muted-foreground)]">Error Rail</div>
                    </div>
                    {Array.from({ length: group.laneCount }).map((_, index) => {
                      const top = laneStartTop + index * (laneHeight + laneGap);
                      return (
                        <div
                          key={`${group.baseTrack}-lane-${index + 1}`}
                          className="pointer-events-none absolute left-0 right-0 rounded-xl border border-transparent bg-[rgba(11,92,173,0.03)]"
                          style={{ top, height: laneHeight }}
                        >
                          <div className="absolute left-3 top-1/2 -translate-y-1/2 rounded-full bg-white/90 px-2 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)] shadow-sm">
                            Lane {index + 1}
                          </div>
                        </div>
                      );
                    })}
                    {group.bars.map((row, index) => {
                      const visibleStart = Math.max(row.startMs, domain[0]);
                      const visibleEnd = Math.min(row.endMs, domain[1]);
                      if (visibleEnd < domain[0] || visibleStart > domain[1]) {
                        return null;
                      }
                      const left = ((visibleStart - domain[0]) / domainSpan) * 100;
                      const width = Math.max(((visibleEnd - visibleStart) / domainSpan) * 100, 0.45);
                      const top = laneStartTop + (row.lane - 1) * (laneHeight + laneGap) + 3;
                      const color = timelineColor(String(row.label));
                      return (
                        <button
                          key={`${group.baseTrack}-${row.label}-${index}`}
                          type="button"
                          className="absolute z-10 flex h-5 items-center overflow-hidden rounded-full px-3 text-left text-[11px] font-medium text-white shadow-[0_12px_24px_-18px_rgba(0,0,0,0.45)] transition hover:brightness-105"
                          style={{ left: `${left}%`, width: `${width}%`, top, backgroundColor: color }}
                          onMouseEnter={(event) => {
                            setActiveTrack(group.baseTrack);
                            openTooltip(event, row.label, group.baseTrack, [
                              { label: "开始", value: formatDateTimeText(row.start ?? row.start_time_sec ?? row.startMs) },
                              { label: "结束", value: formatDateTimeText(row.end ?? row.end_time_sec ?? row.endMs) },
                              { label: "时长", value: formatDurationText(safeNumber(row.duration_ms, row.endMs - row.startMs) / 1000) },
                              { label: "Cycle", value: toDisplayValue(row.cycle_no) },
                              { label: "组件", value: toDisplayValue(row.component || row.module) },
                            ]);
                          }}
                          onMouseMove={(event) => {
                            setActiveTrack(group.baseTrack);
                            openTooltip(event, row.label, group.baseTrack, [
                              { label: "开始", value: formatDateTimeText(row.start ?? row.start_time_sec ?? row.startMs) },
                              { label: "结束", value: formatDateTimeText(row.end ?? row.end_time_sec ?? row.endMs) },
                              { label: "时长", value: formatDurationText(safeNumber(row.duration_ms, row.endMs - row.startMs) / 1000) },
                              { label: "Cycle", value: toDisplayValue(row.cycle_no) },
                              { label: "组件", value: toDisplayValue(row.component || row.module) },
                            ]);
                          }}
                          onMouseLeave={() => {
                            setTooltip(null);
                            setActiveTrack((current) => (current === group.baseTrack ? null : current));
                          }}
                        >
                          <span className="truncate">{shortText(row.label, 34)}</span>
                        </button>
                      );
                    })}
                    {group.errors.map((row, index) => {
                      if (row.timeMs < domain[0] || row.timeMs > domain[1]) {
                        return null;
                      }
                      const left = ((row.timeMs - domain[0]) / domainSpan) * 100;
                      return (
                        <button
                          key={`${group.baseTrack}-error-${index}`}
                          type="button"
                          className="absolute z-10 h-3.5 w-3.5 rotate-45 rounded-[2px] border border-white shadow-sm transition hover:scale-110"
                          style={{ left: `${left}%`, top: errorRailTop, backgroundColor: errorColor(row.severity) }}
                          onMouseEnter={(event) => {
                            setActiveTrack(group.baseTrack);
                            openTooltip(event, String(row.normalized_signature || row.message || "Error Point"), group.baseTrack, [
                              { label: "时间", value: toDisplayValue(row.time_text || formatDateTimeText(row.time ?? row.timeMs)) },
                              { label: "严重级别", value: toDisplayValue(row.severity) },
                              { label: "错误家族", value: toDisplayValue(row.error_family_display || row.error_family) },
                              { label: "组件", value: toDisplayValue(row.component || row.module) },
                            ]);
                          }}
                          onMouseMove={(event) => {
                            setActiveTrack(group.baseTrack);
                            openTooltip(event, String(row.normalized_signature || row.message || "Error Point"), group.baseTrack, [
                              { label: "时间", value: toDisplayValue(row.time_text || formatDateTimeText(row.time ?? row.timeMs)) },
                              { label: "严重级别", value: toDisplayValue(row.severity) },
                              { label: "错误家族", value: toDisplayValue(row.error_family_display || row.error_family) },
                              { label: "组件", value: toDisplayValue(row.component || row.module) },
                            ]);
                          }}
                          onMouseLeave={() => {
                            setTooltip(null);
                            setActiveTrack((current) => (current === group.baseTrack ? null : current));
                          }}
                        />
                      );
                    })}
                    <div
                      className="absolute inset-0 z-0"
                      onWheel={handleWheel}
                      onPointerDown={handlePointerDown}
                      onPointerMove={handlePointerMove}
                      onPointerUp={finishGesture}
                      onPointerCancel={finishGesture}
                      onDoubleClick={resetView}
                    />
                    {brushRange ? (
                      <div
                        className="pointer-events-none absolute inset-y-0 rounded-none border border-[rgba(11,92,173,0.42)] bg-[rgba(11,92,173,0.12)]"
                        style={{
                          left: `${Math.min(brushRange[0], brushRange[1]) * 100}%`,
                          width: `${Math.abs(brushRange[1] - brushRange[0]) * 100}%`,
                        }}
                      />
                    ) : null}
                  </div>
                </div>
              );
            })
          ) : (
            <div className="rounded-2xl border border-dashed border-[var(--border)] bg-[var(--muted)]/15 px-4 py-8 text-center text-sm text-[var(--muted-foreground)]">
              当前筛选条件下没有可展示的时间轴片段。
            </div>
          )}
          {tooltip ? (
            <div
              className="pointer-events-none absolute z-10 min-w-[240px] rounded-2xl border border-slate-200/80 bg-white/95 px-4 py-3 text-xs shadow-[0_20px_40px_-24px_rgba(15,23,42,0.45)] backdrop-blur"
              style={{ left: Math.min(tooltip.left, 720), top: Math.max(tooltip.top, 12) }}
            >
              <div className="font-semibold text-[var(--foreground)]">{tooltip.title}</div>
              {tooltip.subtitle ? <div className="mt-1 text-[var(--muted-foreground)]">{tooltip.subtitle}</div> : null}
              <div className="mt-3 space-y-2 text-[var(--foreground)]">
                {tooltip.rows.map((item) => (
                  <div key={`${tooltip.title}-${item.label}`} className="flex items-start justify-between gap-4">
                    <span className="text-[var(--muted-foreground)]">{item.label}</span>
                    <span className="text-right">{item.value}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </div>
        {timelineData.groups.length > 1 ? (
          <div className="flex flex-wrap gap-2">
            {timelineData.groups.map((group) => {
              const active = !hiddenSet.has(group.baseTrack);
              return (
                <button
                  key={`${title}-${group.baseTrack}`}
                  type="button"
                  onClick={() => toggleTrack(group.baseTrack)}
                  className={cn(
                    "inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs transition",
                    active
                      ? "border-[var(--accent)] bg-[color:rgba(11,92,173,0.08)] text-[var(--foreground)]"
                      : "border-[var(--border)] bg-[var(--card)] text-[var(--muted-foreground)] opacity-70",
                  )}
                >
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: timelineColor(group.baseTrack) }} />
                  <span>{shortText(group.baseTrack, 36)}</span>
                </button>
              );
            })}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}
export function MappingEditorTable({
  title,
  description,
  rows,
  columns,
  onChange,
  addLabel = "新增一行",
}: {
  title: string;
  description?: string;
  rows: AnyRecord[];
  columns: MappingEditorColumn[];
  onChange: (rows: AnyRecord[]) => void;
  addLabel?: string;
}) {
  function updateCell(rowIndex: number, columnKey: string, value: string) {
    onChange(
      rows.map((row, index) =>
        index === rowIndex
          ? {
              ...row,
              [columnKey]: value,
            }
          : row,
      ),
    );
  }

  function removeRow(rowIndex: number) {
    onChange(rows.filter((_, index) => index !== rowIndex));
  }

  function addRow() {
    onChange([
      ...rows,
      Object.fromEntries(columns.map((column) => [column.key, ""])),
    ]);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="overflow-auto rounded-2xl border border-[var(--border)]">
          <table className="min-w-full divide-y divide-[var(--border)] text-sm">
            <thead className="bg-[var(--muted)]/60">
              <tr>
                {columns.map((column) => (
                  <th
                    key={column.key}
                    className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted-foreground)]"
                  >
                    {column.label}
                  </th>
                ))}
                <th className="px-3 py-2 text-right text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted-foreground)]">
                  操作
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[var(--border)]">
              {rows.map((row, rowIndex) => (
                <tr key={`${title}-${rowIndex}`}>
                  {columns.map((column) => (
                    <td key={`${rowIndex}-${column.key}`} className="px-3 py-2 align-top">
                      {column.multiline ? (
                        <Textarea
                          rows={3}
                          value={String(row[column.key] ?? "")}
                          placeholder={column.placeholder}
                          onChange={(event) => updateCell(rowIndex, column.key, event.target.value)}
                        />
                      ) : (
                        <Input
                          value={String(row[column.key] ?? "")}
                          placeholder={column.placeholder}
                          onChange={(event) => updateCell(rowIndex, column.key, event.target.value)}
                        />
                      )}
                    </td>
                  ))}
                  <td className="px-3 py-2 text-right align-top">
                    <Button variant="ghost" size="sm" onClick={() => removeRow(rowIndex)}>
                      删除
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button variant="secondary" size="sm" onClick={addRow}>
          {addLabel}
        </Button>
      </CardContent>
    </Card>
  );
}
