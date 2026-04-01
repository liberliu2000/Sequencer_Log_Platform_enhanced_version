/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useMemo } from "react";

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
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) {
    return String(value);
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
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
      return "bg-emerald-100 text-emerald-900";
    case "queued":
    case "running":
    case "pending_review":
    case "pending_admin_approval":
    case "submitted_for_review":
      return "bg-amber-100 text-amber-900";
    case "failed":
    case "rejected":
    case "disabled":
      return "bg-rose-100 text-rose-900";
    case "needs_revision":
    case "ignored":
      return "bg-orange-100 text-orange-900";
    default:
      return "bg-slate-100 text-slate-900";
  }
}

function palette(index: number) {
  const colors = [
    "#0B5CAD",
    "#D96B3B",
    "#1E8E6A",
    "#8B5CF6",
    "#CC4C7A",
    "#0384A8",
    "#7A5C29",
    "#48566A",
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
      ? "border-emerald-200 bg-emerald-50 text-emerald-900"
      : notice.tone === "error"
        ? "border-rose-200 bg-rose-50 text-rose-900"
        : "border-sky-200 bg-sky-50 text-sky-900";
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

export function StatusBadge({ status }: { status: unknown }) {
  return <Badge className={statusBadgeTone(String(status ?? ""))}>{String(status ?? "-")}</Badge>;
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

export function DataTable({
  rows,
  columns,
  title,
  caption,
  maxHeight = 420,
  emptyText = "当前没有可展示的数据。",
  selectedRowIndex,
  onRowClick,
}: {
  rows: AnyRecord[];
  columns?: string[];
  title?: string;
  caption?: string;
  maxHeight?: number;
  emptyText?: string;
  selectedRowIndex?: number;
  onRowClick?: (row: AnyRecord, index: number) => void;
}) {
  const visibleColumns = useMemo(() => {
    if (columns?.length) {
      return columns;
    }
    return Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 14);
  }, [columns, rows]);

  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {caption ? <CardDescription>{caption}</CardDescription> : null}
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        {rows.length ? (
          <div className="overflow-auto rounded-2xl border border-[var(--border)]" style={{ maxHeight }}>
            <table className="min-w-full divide-y divide-[var(--border)] text-sm">
              <thead className="sticky top-0 z-10 bg-[var(--muted)]/95 backdrop-blur">
                <tr>
                  {visibleColumns.map((column) => (
                    <th
                      key={column}
                      className="px-3 py-2 text-left text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted-foreground)]"
                    >
                      {column}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {rows.map((row, index) => (
                  <tr
                    key={`${title || "table"}-${index}`}
                    onClick={() => onRowClick?.(row, index)}
                    className={cn(
                      onRowClick ? "cursor-pointer transition hover:bg-[var(--muted)]/40" : "",
                      selectedRowIndex === index ? "bg-[color:rgba(11,92,173,0.08)]" : "",
                    )}
                  >
                    {visibleColumns.map((column) => (
                      <td key={`${column}-${index}`} className="max-w-[360px] px-3 py-2 align-top">
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
          <p className="text-sm text-[var(--muted-foreground)]">{emptyText}</p>
        )}
      </CardContent>
    </Card>
  );
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
  const chart = useMemo(() => {
    const filtered = rows
      .map((row) => ({
        x: row[xKey],
        y: safeNumber(row[yKey], Number.NaN),
        series: String(seriesKey ? row[seriesKey] ?? "默认序列" : "默认序列"),
      }))
      .filter((row) => Number.isFinite(row.y));

    if (!filtered.length) {
      return null;
    }

    const xLabels = Array.from(new Set(filtered.map((row) => String(row.x ?? ""))));
    const grouped = new Map<string, Array<{ xIndex: number; y: number; xLabel: string }>>();
    filtered.forEach((row) => {
      const xLabel = String(row.x ?? "");
      const bucket = grouped.get(row.series) ?? [];
      bucket.push({ xIndex: xLabels.indexOf(xLabel), y: row.y, xLabel });
      grouped.set(row.series, bucket);
    });

    const allValues = filtered.map((item) => item.y);
    const yMinRaw = Math.min(...allValues);
    const yMaxRaw = Math.max(...allValues);
    const yMin = Math.min(yMinRaw, ...thresholdLines.map((line) => safeNumber(line.value, yMinRaw)));
    const yMax = Math.max(yMaxRaw, ...thresholdLines.map((line) => safeNumber(line.value, yMaxRaw)));

    return {
      xLabels,
      grouped,
      yMin,
      yMax: yMax === yMin ? yMin + 1 : yMax,
    };
  }, [rows, xKey, yKey, seriesKey, thresholdLines]);

  const width = 920;
  const height = 260;
  const margin = { top: 18, right: 24, bottom: 42, left: 48 };
  const plotWidth = width - margin.left - margin.right;
  const plotHeight = height - margin.top - margin.bottom;

  if (!chart) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可绘制的趋势数据。</p>
        </CardContent>
      </Card>
    );
  }

  const xCount = Math.max(1, chart.xLabels.length - 1);
  const xPos = (index: number) => margin.left + (plotWidth * index) / xCount;
  const yPos = (value: number) =>
    margin.top + plotHeight - ((value - chart.yMin) / (chart.yMax - chart.yMin)) * plotHeight;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        <div className="overflow-auto rounded-2xl border border-[var(--border)] bg-[var(--muted)]/20 p-3">
          <svg
            className="w-full min-w-[760px]"
            viewBox={`0 0 ${width} ${height}`}
            role="img"
            aria-label={title}
            style={{ maxHeight }}
          >
            <line
              x1={margin.left}
              x2={margin.left}
              y1={margin.top}
              y2={height - margin.bottom}
              stroke="rgba(16,36,61,0.18)"
            />
            <line
              x1={margin.left}
              x2={width - margin.right}
              y1={height - margin.bottom}
              y2={height - margin.bottom}
              stroke="rgba(16,36,61,0.18)"
            />
            {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
              const y = margin.top + plotHeight * ratio;
              const value = chart.yMax - (chart.yMax - chart.yMin) * ratio;
              return (
                <g key={ratio}>
                  <line
                    x1={margin.left}
                    x2={width - margin.right}
                    y1={y}
                    y2={y}
                    stroke="rgba(16,36,61,0.08)"
                  />
                  <text
                    x={margin.left - 10}
                    y={y + 4}
                    textAnchor="end"
                    fontSize="11"
                    fill="rgba(16,36,61,0.58)"
                  >
                    {Number.isFinite(value) ? value.toFixed(value >= 10 ? 0 : 2) : "-"}
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
                    <text
                      x={width - margin.right}
                      y={y - 6}
                      textAnchor="end"
                      fontSize="11"
                      fill={line.color}
                    >
                      {line.label}: {line.value}
                    </text>
                  </g>
                );
              })}
            {Array.from(chart.grouped.entries()).map(([name, points], seriesIndex) => {
              const sorted = [...points].sort((left, right) => left.xIndex - right.xIndex);
              const color = palette(seriesIndex);
              const path = sorted
                .map((point, pointIndex) => {
                  const command = pointIndex === 0 ? "M" : "L";
                  return `${command} ${xPos(point.xIndex)} ${yPos(point.y)}`;
                })
                .join(" ");
              return (
                <g key={`${title}-${name}`}>
                  <path d={path} fill="none" stroke={color} strokeWidth="3" strokeLinecap="round" />
                  {sorted.map((point) => (
                    <g key={`${name}-${point.xLabel}-${point.y}`}>
                      <circle cx={xPos(point.xIndex)} cy={yPos(point.y)} r="4" fill={color} />
                      <title>
                        {name} | {point.xLabel} | {point.y}
                      </title>
                    </g>
                  ))}
                </g>
              );
            })}
            {chart.xLabels.map((label, index) => (
              <text
                key={`${title}-${label}-${index}`}
                x={xPos(index)}
                y={height - 14}
                textAnchor={index === 0 ? "start" : index === chart.xLabels.length - 1 ? "end" : "middle"}
                fontSize="11"
                fill="rgba(16,36,61,0.62)"
              >
                {shortText(label, 18)}
              </text>
            ))}
          </svg>
        </div>
        {chart.grouped.size > 1 ? (
          <div className="flex flex-wrap gap-3">
            {Array.from(chart.grouped.keys()).map((name, index) => (
              <div key={`${title}-${name}-legend`} className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                <span
                  className="h-2.5 w-2.5 rounded-full"
                  style={{ backgroundColor: palette(index) }}
                />
                <span>{name}</span>
              </div>
            ))}
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}

export function TimelineChart({
  title,
  description,
  rows,
  errors = [],
}: {
  title: string;
  description?: string;
  rows: AnyRecord[];
  errors?: AnyRecord[];
}) {
  const normalized = useMemo(() => {
    const lanes = rows
      .map((row) => {
        const start = safeNumber(row.start_time_sec ?? row.start_time ?? row.start, Number.NaN);
        const end = safeNumber(row.end_time_sec ?? row.end_time ?? row.end, Number.NaN);
        const track = String(row.track || row.component || "未命名泳道");
        const label = String(row.sub_step || row.component || row.module || "片段");
        return {
          ...row,
          start,
          end,
          track,
          label,
        };
      })
      .filter((row) => Number.isFinite(row.start) && Number.isFinite(row.end) && row.end >= row.start);

    if (!lanes.length) {
      return null;
    }

    const trackNames = Array.from(new Set(lanes.map((row) => row.track)));
    const min = Math.min(...lanes.map((row) => row.start));
    const max = Math.max(...lanes.map((row) => row.end));
    const points = errors
      .map((row) => {
        const time = safeNumber(row.time_sec ?? row.start_time_sec ?? row.time, Number.NaN);
        const track = String(row.track || row.component || "未命名泳道");
        return {
          ...row,
          time,
          track,
          severity: String(row.severity || "unknown"),
        };
      })
      .filter((row) => Number.isFinite(row.time));

    return {
      lanes,
      points,
      trackNames,
      min,
      max: max === min ? min + 1 : max,
    };
  }, [rows, errors]);

  if (!normalized) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </CardHeader>
        <CardContent className="pt-0">
          <p className="text-sm text-[var(--muted-foreground)]">当前筛选条件下暂无可展示的时间轴。</p>
        </CardContent>
      </Card>
    );
  }

  const total = normalized.max - normalized.min || 1;
  const errorColor = (severity: string) => {
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
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        {description ? <CardDescription>{description}</CardDescription> : null}
      </CardHeader>
      <CardContent className="space-y-3 pt-0">
        <div className="flex items-center justify-between text-xs text-[var(--muted-foreground)]">
          <span>开始 {normalized.min.toFixed(3)}s</span>
          <span>结束 {normalized.max.toFixed(3)}s</span>
        </div>
        <div className="space-y-3">
          {normalized.trackNames.map((track) => {
            const laneRows = normalized.lanes.filter((row) => row.track === track);
            const laneErrors = normalized.points.filter((row) => row.track === track);
            return (
              <div key={`${title}-${track}`} className="grid gap-3 lg:grid-cols-[220px_minmax(0,1fr)]">
                <div className="rounded-2xl border border-[var(--border)] bg-[var(--muted)]/45 px-4 py-3">
                  <p className="text-sm font-medium text-[var(--foreground)]">{track}</p>
                  <p className="mt-1 text-xs text-[var(--muted-foreground)]">{laneRows.length} 个动作片段</p>
                </div>
                <div className="relative min-h-[72px] rounded-2xl border border-[var(--border)] bg-[var(--card)] px-3 py-4">
                  <div className="absolute inset-y-4 left-3 right-3 rounded-xl bg-[linear-gradient(90deg,rgba(11,92,173,0.04),rgba(11,92,173,0.09),rgba(11,92,173,0.04))]" />
                  {laneRows.map((row, index) => {
                    const left = ((row.start - normalized.min) / total) * 100;
                    const width = Math.max(((row.end - row.start) / total) * 100, 1.2);
                    const color = timelineColor(String(row.label));
                    return (
                      <div
                        key={`${track}-${row.label}-${index}`}
                        className="absolute top-1/2 flex -translate-y-1/2 items-center overflow-hidden rounded-full px-3 py-2 text-[11px] font-medium text-white shadow-[0_12px_24px_-18px_rgba(0,0,0,0.45)]"
                        style={{ left: `${left}%`, width: `${width}%`, backgroundColor: color }}
                        title={`${row.label} | ${row.start.toFixed(3)}s - ${row.end.toFixed(3)}s | ${String((row as AnyRecord).message || "")}`}
                      >
                        <span className="truncate">{shortText(row.label, 24)}</span>
                      </div>
                    );
                  })}
                  {laneErrors.map((row, index) => {
                    const left = ((row.time - normalized.min) / total) * 100;
                    return (
                      <div
                        key={`${track}-error-${index}`}
                        className="absolute top-1/2 h-3 w-3 -translate-y-1/2 rotate-45 rounded-[2px] border border-white"
                        style={{ left: `${left}%`, backgroundColor: errorColor(row.severity) }}
                        title={`${row.severity} | ${String((row as AnyRecord).normalized_signature || (row as AnyRecord).message || "错误点")}`}
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
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
