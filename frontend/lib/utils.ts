import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function formatDate(value?: string | null) {
  if (!value) {
    return "未记录";
  }

  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }

  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export function takeFirstSentence(value?: string | null, fallback = "暂无内容") {
  const text = String(value ?? "").trim();
  if (!text) {
    return fallback;
  }

  return text.length > 120 ? `${text.slice(0, 120)}...` : text;
}

export function joinList(items?: string[] | null) {
  if (!items?.length) {
    return "未设置";
  }

  return items.join(" / ");
}
