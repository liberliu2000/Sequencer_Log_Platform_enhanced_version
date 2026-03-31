/* eslint-disable @typescript-eslint/no-explicit-any */
"use client";

import { useMemo } from "react";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Label } from "@/components/ui/label";

export type AnyRecord = Record<string, any>;
export type Notice = {
  tone: "success" | "error" | "info";
  text: string;
};

export function safeArray<T = AnyRecord>(value: unknown) {
  return Array.isArray(value) ? (value as T[]) : [];
}

export function safeObject(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as AnyRecord)
    : {};
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
      return "bg-amber-100 text-amber-900";
    case "failed":
    case "rejected":
    case "disabled":
      return "bg-rose-100 text-rose-900";
    case "needs_revision":
      return "bg-orange-100 text-orange-900";
    default:
      return "bg-slate-100 text-slate-900";
  }
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

export function JsonPreview({ value, title }: { value: unknown; title?: string }) {
  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        <pre className="max-h-[420px] overflow-auto rounded-2xl bg-[var(--muted)]/70 p-4 text-xs leading-6 whitespace-pre-wrap">
          {stringifyJson(value)}
        </pre>
      </CardContent>
    </Card>
  );
}

export function DistributionList({
  title,
  items,
}: {
  title: string;
  items: Array<{ label: string; value: number; note?: string }>;
}) {
  const total = items.reduce((sum, item) => sum + item.value, 0) || 1;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{title}</CardTitle>
        <CardDescription>以纯前端可视化方式替代 Streamlit 中的轻量图表。</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4 pt-0">
        {items.length ? (
          items.map((item) => {
            const percent = Math.round((item.value / total) * 100);
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
                    className="h-2 rounded-full bg-[var(--accent)]"
                    style={{ width: `${Math.max(percent, 6)}%` }}
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

export function DataTable({
  rows,
  columns,
  title,
}: {
  rows: AnyRecord[];
  columns?: string[];
  title?: string;
}) {
  const visibleColumns = useMemo(() => {
    if (columns?.length) {
      return columns;
    }
    return Array.from(new Set(rows.flatMap((row) => Object.keys(row)))).slice(0, 12);
  }, [columns, rows]);

  return (
    <Card>
      {title ? (
        <CardHeader>
          <CardTitle className="text-base">{title}</CardTitle>
        </CardHeader>
      ) : null}
      <CardContent className={title ? "pt-0" : "pt-6"}>
        {rows.length ? (
          <div className="overflow-auto rounded-2xl border border-[var(--border)]">
            <table className="min-w-full divide-y divide-[var(--border)] text-sm">
              <thead className="bg-[var(--muted)]/65">
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
                  <tr key={`${title || "table"}-${index}`}>
                    {visibleColumns.map((column) => (
                      <td key={`${column}-${index}`} className="max-w-[320px] px-3 py-2 align-top">
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
          <p className="text-sm text-[var(--muted-foreground)]">当前没有可展示的数据。</p>
        )}
      </CardContent>
    </Card>
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
