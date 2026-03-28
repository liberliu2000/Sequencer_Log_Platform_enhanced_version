from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from app.core.settings import BASE_DIR, get_settings
from app.llm.client import LLMClient
from app.utils.rules import load_yaml


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows


def normalize_text(text: str) -> str:
    s = text.strip().lower()
    s = re.sub(r"\d{4}[-/]\d{2}[-/]\d{2}", "<date>", s)
    s = re.sub(r"\d{2}:\d{2}:\d{2}(?:[.:]\d{3,6})?", "<time>", s)
    s = re.sub(r"\b[0-9a-f]{8,}\b", "<hex>", s)
    s = re.sub(r"\b\d+\b", "<num>", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def normalize_for_regex(text: str) -> str:
    s = text.strip()
    s = re.escape(s)
    s = re.sub(r"\d+", r"(\\d+)", s)
    s = s.replace(r"\ ", r"\s+")
    s = re.sub(r"\\<date\\>", r"(?:\\d{4}[-/]\\d{2}[-/]\\d{2})", s)
    s = re.sub(r"\\<time\\>", r"(?:\\d{2}:\\d{2}:\\d{2}(?:[.:]\\d{3,6})?)", s)
    return s


def infer_time_format(sample: str) -> str | None:
    if re.search(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+", sample):
        return "%Y/%m/%d %H:%M:%S.%f"
    if re.search(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}:\d+", sample):
        return "%Y/%m/%d %H:%M:%S:%f"
    if re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+", sample):
        return "%Y-%m-%d %H:%M:%S.%f"
    if re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", sample):
        return "%Y-%m-%d %H:%M:%S"
    return None


def suggest_parser_type(sample: str, source_file: str | None) -> str:
    lowered = sample.lower()
    src = (source_file or "").lower()
    if ".csv" in src or "," in sample:
        return "csv_like"
    if "|" in sample and any(k in lowered for k in ["info", "warn", "error", "fatal"]):
        return "service_log_like"
    if "exception" in lowered or "traceback" in lowered:
        return "runerror_like"
    return "text_log_like"


def extract_field_patterns(sample: str) -> dict[str, str]:
    patterns: dict[str, str] = {}
    if infer_time_format(sample):
        patterns["timestamp"] = r"(?P<ts>\d{4}[-/]\d{2}[-/]\d{2}\s+\d{2}:\d{2}:\d{2}(?:[.:]\d{3,6})?)"
    if re.search(r"\b(?:INFO|WARN|ERROR|FATAL|DEBUG)\b", sample):
        patterns["level"] = r"(?P<level>INFO|WARN|ERROR|FATAL|DEBUG)"
    if re.search(r"\bCycle\s*\d+\b|\bS\d{3,4}\b|\bcycle\d+\b", sample, re.IGNORECASE):
        patterns["cycle"] = r"(?P<cycle_no>\d+)"
    if re.search(r"\bHLAB\d{4,}\b", sample, re.IGNORECASE):
        patterns["chip_name"] = r"(?P<chip_name>HLAB\d{4,})"
    patterns["message"] = normalize_for_regex(normalize_text(sample))[:500]
    return patterns


def cluster_unknown_observations(unknown_rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    clusters: dict[str, dict[str, Any]] = {}
    for row in unknown_rows:
        raw = str(row.get("raw_text") or "").strip()
        if not raw:
            continue
        signature = str(row.get("signature") or "") or normalize_text(raw)
        key = signature if len(signature) <= 24 else signature[:24]
        item = clusters.setdefault(
            key,
            {
                "signature": key,
                "representative_text": raw,
                "representative_source_file": row.get("source_file"),
                "representative_timestamp": row.get("timestamp") or row.get("extracted_timestamp"),
                "occurrence_count": 0,
                "failure_reasons": Counter(),
                "samples": [],
                "attempted_parsers": Counter(),
                "attempted_rules": Counter(),
            },
        )
        item["occurrence_count"] += 1
        reason = str(row.get("failure_reason") or "unknown")
        item["failure_reasons"][reason] += 1
        for p in row.get("attempted_parsers") or []:
            item["attempted_parsers"][str(p.get("parser_name") or "unknown")] += 1
        for r in row.get("attempted_rules") or []:
            item["attempted_rules"][str(r.get("name") or r.get("parser_type") or "unknown")] += 1
        if len(item["samples"]) < 8:
            item["samples"].append(
                {
                    "raw_text": raw,
                    "source_file": row.get("source_file"),
                    "timestamp": row.get("timestamp") or row.get("extracted_timestamp"),
                    "context_lines": row.get("context_lines") or [],
                }
            )
    return clusters


def build_unknown_rule_suggestions(
    unknown_clusters: dict[str, Any],
    min_occurrence: int = 3,
    max_samples: int = 3,
) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []

    for signature, cluster in unknown_clusters.items():
        count = int(cluster.get("occurrence_count", 0))
        if count < min_occurrence:
            continue

        rep = cluster.get("representative_text") or ""
        source_file = cluster.get("representative_source_file")
        parser_type = suggest_parser_type(rep, source_file)
        time_fmt = infer_time_format(rep)

        context_examples = list(cluster.get("context_examples") or cluster.get("samples") or [])
        samples = [x.get("raw_text") for x in context_examples[:max_samples] if x.get("raw_text")]
        field_patterns = extract_field_patterns(rep)

        suggestion = {
            "suggestion_id": f"unknown-{signature}",
            "status": "pending_review",
            "source": "unknown_log_pool",
            "cluster_signature": signature,
            "occurrence_count": count,
            "suggested_log_type": parser_type,
            "possible_time_format": time_fmt,
            "suggested_parser_type": parser_type,
            "suggested_match_features": {
                "delimiter": "pipe" if "|" in rep else "comma" if "," in rep else "text",
                "contains_timestamp": bool(time_fmt),
                "contains_level": bool(re.search(r"\b(?:INFO|WARN|ERROR|FATAL|DEBUG)\b", rep)),
            },
            "suggested_field_regex": field_patterns,
            "confidence": round(min(0.95, 0.35 + math.log(max(count, 1), 10) * 0.25), 3),
            "representative_samples": samples or [rep],
            "failure_reasons": cluster.get("failure_reasons") or [],
            "parser_rules_yaml_fragment": {
                "custom_candidates": [
                    {
                        "name": f"suggested_{signature}",
                        "parser_type": parser_type,
                        "regex": field_patterns.get("message") or normalize_for_regex(rep)[:500],
                        "time_format": time_fmt,
                        "extract_fields": list(field_patterns.keys()),
                        "status": "pending_review",
                    }
                ]
            },
        }
        suggestions.append(suggestion)

    suggestions.sort(key=lambda x: (-x["occurrence_count"], -x["confidence"]))
    return suggestions


def build_feedback_rule_suggestions(
    feedback_rows: list[dict[str, Any]],
    min_occurrence: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for row in feedback_rows:
        orig = row.get("original_parse_result") or {}
        corr = row.get("corrected_result") or {}
        key = "||".join(
            [
                str(row.get("correction_type") or ""),
                str(row.get("source_file") or ""),
                str(orig.get("parser_name") or ""),
                str(orig.get("sub_step") or ""),
                str(corr.get("sub_step") or ""),
            ]
        )
        grouped[key].append(row)

    suggestions: list[dict[str, Any]] = []
    problematic_old_rules: list[dict[str, Any]] = []

    for key, rows in grouped.items():
        if len(rows) < min_occurrence:
            continue

        sample = rows[0]
        orig = sample.get("original_parse_result") or {}
        corr = sample.get("corrected_result") or {}

        suggestions.append(
            {
                "suggestion_id": f"feedback-{abs(hash(key))}",
                "status": "pending_review",
                "source": "feedback_pool",
                "correction_type": sample.get("correction_type"),
                "occurrence_count": len(rows),
                "original_parser_name": orig.get("parser_name"),
                "suggested_updates": {
                    "parser_name": corr.get("parser_name") or orig.get("parser_name"),
                    "cycle_patterns_hint": corr.get("cycle_no"),
                    "sub_step_hint": corr.get("sub_step"),
                    "component_hint": corr.get("component"),
                    "error_family_hint": corr.get("error_family"),
                    "field_delta": _build_field_delta(orig, corr),
                },
                "confidence": round(min(0.98, 0.45 + math.log(len(rows), 10) * 0.35), 3),
                "representative_sample": sample.get("raw_log"),
                "parser_rules_yaml_fragment": {
                    "feedback_adjustments": [
                        {
                            "source_file": sample.get("source_file"),
                            "correction_type": sample.get("correction_type"),
                            "original_parser": orig.get("parser_name"),
                            "suggested_parser": corr.get("parser_name") or orig.get("parser_name"),
                            "suggested_sub_step": corr.get("sub_step"),
                            "suggested_component": corr.get("component"),
                            "status": "pending_review",
                        }
                    ]
                },
            }
        )

        problematic_old_rules.append(
            {
                "original_parser_name": orig.get("parser_name"),
                "correction_type": sample.get("correction_type"),
                "count": len(rows),
                "source_file": sample.get("source_file"),
                "sample_raw_log": sample.get("raw_log"),
            }
        )

    problematic_old_rules.sort(key=lambda x: (-x["count"], str(x["original_parser_name"] or "")))
    suggestions.sort(key=lambda x: (-x["occurrence_count"], -x["confidence"]))
    return suggestions, problematic_old_rules


def render_yaml_fragment(unknown_suggestions: list[dict[str, Any]], feedback_suggestions: list[dict[str, Any]]) -> dict[str, Any]:
    fragment = {
        "custom_candidates": [],
        "feedback_adjustments": [],
    }

    for item in unknown_suggestions:
        fragment["custom_candidates"].extend(item.get("parser_rules_yaml_fragment", {}).get("custom_candidates", []))

    for item in feedback_suggestions:
        fragment["feedback_adjustments"].extend(item.get("parser_rules_yaml_fragment", {}).get("feedback_adjustments", []))

    return fragment


def _build_field_delta(original: dict[str, Any], corrected: dict[str, Any]) -> dict[str, Any]:
    delta = {}
    for key in sorted(set(original) | set(corrected)):
        if original.get(key) != corrected.get(key):
            delta[key] = {"from": original.get(key), "to": corrected.get(key)}
    return delta


def _read_text(path: Path, max_chars: int = 4000) -> str:
    if not path.exists():
        return ""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return ""
    return text[:max_chars]


def _collect_relevant_parser_snippets(unknown_suggestions: list[dict[str, Any]], feedback_suggestions: list[dict[str, Any]], max_files: int = 4, max_chars: int = 1800) -> list[dict[str, Any]]:
    parser_names: list[str] = []
    for item in feedback_suggestions[:max_files]:
        name = item.get("original_parser_name")
        if name:
            parser_names.append(str(name))
    for item in unknown_suggestions[:max_files]:
        log_type = str(item.get("suggested_log_type") or "")
        if "service" in log_type:
            parser_names.append("service_log")
        elif "runerror" in log_type:
            parser_names.append("runerror")
        elif "csv" in log_type:
            parser_names.append("csv_workflow")

    mapping = {
        "service_log": BASE_DIR / "app" / "parsers" / "service_log_parser.py",
        "runerror": BASE_DIR / "app" / "parsers" / "runerror_parser.py",
        "csv_workflow": BASE_DIR / "app" / "parsers" / "csv_workflow_parser.py",
        "error_log": BASE_DIR / "app" / "parsers" / "error_log_parser.py",
        "metrics_csv": BASE_DIR / "app" / "parsers" / "metrics_csv_parser.py",
    }
    snippets = []
    seen = set()
    for name in parser_names:
        path = mapping.get(name)
        if not path or path in seen:
            continue
        seen.add(path)
        snippets.append({"parser_name": name, "path": str(path.relative_to(BASE_DIR)), "snippet": _read_text(path, max_chars=max_chars)})
        if len(snippets) >= max_files:
            break
    return snippets


def _compact_unknown_for_llm(items: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in items[:limit]:
        compact.append(
            {
                "suggestion_id": item.get("suggestion_id"),
                "cluster_signature": item.get("cluster_signature"),
                "occurrence_count": item.get("occurrence_count"),
                "suggested_log_type": item.get("suggested_log_type"),
                "possible_time_format": item.get("possible_time_format"),
                "suggested_match_features": item.get("suggested_match_features"),
                "suggested_field_regex": item.get("suggested_field_regex"),
                "confidence": item.get("confidence"),
                "representative_samples": (item.get("representative_samples") or [])[:2],
                "failure_reasons": item.get("failure_reasons"),
            }
        )
    return compact


def _compact_feedback_for_llm(items: list[dict[str, Any]], limit: int = 4) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for item in items[:limit]:
        compact.append(
            {
                "suggestion_id": item.get("suggestion_id"),
                "correction_type": item.get("correction_type"),
                "occurrence_count": item.get("occurrence_count"),
                "original_parser_name": item.get("original_parser_name"),
                "suggested_updates": item.get("suggested_updates"),
                "confidence": item.get("confidence"),
                "representative_sample": item.get("representative_sample"),
            }
        )
    return compact


def _build_llm_prompt(
    *,
    parser_rules: dict[str, Any],
    unknown_suggestions: list[dict[str, Any]],
    feedback_suggestions: list[dict[str, Any]],
    llm_config: dict[str, Any] | None = None,
) -> tuple[str, str, dict[str, Any]]:
    llm_config = llm_config or {}
    max_unknown = max(1, int(llm_config.get("max_unknown_samples", 4)))
    max_feedback = max(1, int(llm_config.get("max_feedback_samples", 4)))
    max_parser_snippets = max(1, int(llm_config.get("max_parser_snippets", 3)))
    parser_snippets = _collect_relevant_parser_snippets(
        unknown_suggestions,
        feedback_suggestions,
        max_files=max_parser_snippets,
        max_chars=int(llm_config.get("max_parser_snippet_chars", 1800)),
    )
    context = {
        "task": "Generate parser rule suggestions in review-only mode.",
        "requirements": {
            "review_only": True,
            "must_not_overwrite_production_rules": True,
            "return_json_only": True,
            "compatible_with_parser_rules_yaml": True,
            "prefer_minimal_context": True,
        },
        "unknown_log_samples": _compact_unknown_for_llm(unknown_suggestions, limit=max_unknown),
        "feedback_samples": _compact_feedback_for_llm(feedback_suggestions, limit=max_feedback),
        "relevant_parser_code_snippets": parser_snippets,
        "relevant_parser_rules": {
            "time_formats": parser_rules.get("time_formats") or [],
            "cycle_patterns": parser_rules.get("cycle_patterns") or [],
            "chip_patterns": parser_rules.get("chip_patterns") or [],
            "pairing_rules": parser_rules.get("pairing_rules") or [],
            "custom_candidates": (parser_rules.get("custom_candidates") or [])[:8],
            "feedback_adjustments": (parser_rules.get("feedback_adjustments") or [])[:8],
        },
    }
    system_prompt = (
        "你是测序仪日志解析规则顾问。"
        "你只能输出 JSON，不允许输出 markdown。"
        "你生成的是 review-only 候选规则建议，不能直接覆盖生产规则。"
        "只基于提供的最小必要上下文给出候选建议，不要复述输入。"
        "输出字段至少包括：new_rule_suggestions、rule_fix_suggestions、high_frequency_misclassified_patterns、parser_rules_yaml_fragment、review_required。"
        "每条建议至少包含：建议归属的日志类型、建议匹配特征或正则、可提取字段、时间格式判断、与现有 parser 的兼容建议、置信度、代表性样本、status=pending_review。"
    )
    user_prompt = json.dumps(context, ensure_ascii=False, indent=2)
    fallback = {
        "fallback": True,
        "new_rule_suggestions": [],
        "rule_fix_suggestions": [],
        "high_frequency_misclassified_patterns": [],
        "parser_rules_yaml_fragment": {"custom_candidates": [], "feedback_adjustments": []},
        "review_required": True,
    }
    return system_prompt, user_prompt, fallback

def _normalize_suggestion_item(item: Any, default_source: str, index: int, *, fallback_sample: str | None = None) -> dict[str, Any]:
    """将 LLM 返回的任意建议项规整为 dict，避免 string / list / number 直接导致后续 setdefault 崩溃。"""
    if isinstance(item, dict):
        row = dict(item)
    else:
        text_value = str(item or '').strip()
        row = {
            "title": text_value[:120] or f"{default_source}_{index}",
            "description": text_value,
            "representative_samples": [fallback_sample or text_value] if (fallback_sample or text_value) else [],
        }
    row.setdefault("suggestion_id", f"llm-{default_source}-{index}")
    row.setdefault("status", "pending_review")
    row.setdefault("source", "llm_rule_suggestion")
    row.setdefault("review_required", True)
    row.setdefault("confidence", 0.5)
    row.setdefault("representative_samples", [fallback_sample] if fallback_sample else [])
    return row


def _normalize_yaml_fragment(fragment: Any) -> dict[str, Any]:
    """保证 parser_rules_yaml_fragment 永远是兼容 dict，而不是 string。"""
    if isinstance(fragment, dict):
        row = dict(fragment)
    else:
        row = {
            "notes": str(fragment or ""),
            "custom_candidates": [],
            "feedback_adjustments": [],
        }
    custom_candidates = row.get("custom_candidates")
    if not isinstance(custom_candidates, list):
        custom_candidates = [custom_candidates] if custom_candidates else []
    feedback_adjustments = row.get("feedback_adjustments")
    if not isinstance(feedback_adjustments, list):
        feedback_adjustments = [feedback_adjustments] if feedback_adjustments else []
    row["custom_candidates"] = [x if isinstance(x, dict) else {"name": f"llm_custom_candidate_{i+1}", "raw": str(x), "status": "pending_review"} for i, x in enumerate(custom_candidates)]
    row["feedback_adjustments"] = [x if isinstance(x, dict) else {"name": f"llm_feedback_adjustment_{i+1}", "raw": str(x), "status": "pending_review"} for i, x in enumerate(feedback_adjustments)]
    return row


def _normalize_llm_rule_result(result: Any, *, fallback_sample: str | None = None) -> dict[str, Any]:
    """对 LLM JSON 做防御性清洗，兼容字段缺失、字段类型错位、fragment 为 string 等情况。"""
    if isinstance(result, dict):
        row = dict(result)
    else:
        row = {"raw_result": result}

    normalized: dict[str, Any] = dict(row)
    normalized.setdefault("review_required", True)

    for block_name in ["new_rule_suggestions", "rule_fix_suggestions", "high_frequency_misclassified_patterns"]:
        block = normalized.get(block_name)
        if not isinstance(block, list):
            block = [block] if block not in (None, "") else []
        normalized[block_name] = [
            _normalize_suggestion_item(item, block_name, idx + 1, fallback_sample=fallback_sample)
            for idx, item in enumerate(block)
        ]

    normalized["parser_rules_yaml_fragment"] = _normalize_yaml_fragment(normalized.get("parser_rules_yaml_fragment"))
    return normalized


def build_llm_rule_suggestions(
    *,
    parser_rules: dict[str, Any],
    unknown_suggestions: list[dict[str, Any]],
    feedback_suggestions: list[dict[str, Any]],
    llm_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    llm_config = llm_config or {}
    system_prompt, user_prompt, fallback = _build_llm_prompt(
        parser_rules=parser_rules,
        unknown_suggestions=unknown_suggestions,
        feedback_suggestions=feedback_suggestions,
        llm_config=llm_config,
    )
    client = LLMClient()
    result, request_payload, response_payload = client.request_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        fallback=fallback,
        temperature=0.05,
        timeout_seconds=int(llm_config.get("timeout_seconds", get_settings().llm_preview_timeout_seconds)),
        max_retries=int(llm_config.get("max_retries", get_settings().llm_preview_max_retries)),
    )
    if result.get("fallback"):
        return {
            "used": False,
            "fallback_to_local": True,
            "request_payload": request_payload,
            "response_payload": response_payload,
            "result": fallback,
        }

    fallback_sample = None
    if unknown_suggestions:
        fallback_sample = (unknown_suggestions[0].get("representative_samples") or [None])[0]
    result = _normalize_llm_rule_result(result, fallback_sample=fallback_sample)
    return {
        "used": True,
        "fallback_to_local": False,
        "request_payload": request_payload,
        "response_payload": response_payload,
        "result": result,
    }

def main() -> None:
    parser = argparse.ArgumentParser(description="Learn parser rule suggestions from unknown log pool and feedback pool.")
    parser.add_argument("--write", action="store_true", help="Write suggestion file to configured output directory.")
    parser.add_argument("--mode", choices=["local", "llm", "auto"], default="auto", help="Suggestion generation mode.")
    args = parser.parse_args()

    settings = get_settings()
    parser_rules = load_yaml(settings.parser_rules_path)

    active_learning_cfg = parser_rules.get("active_learning") or {}
    suggestion_cfg = active_learning_cfg.get("suggestion_generation") or {}
    output_dir = Path(suggestion_cfg.get("write_suggestions_to", Path(settings.data_dir) / "active_learning" / "rule_suggestions"))
    if not output_dir.is_absolute():
        output_dir = BASE_DIR / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    base_dir = Path(settings.data_dir) / "active_learning"
    unknown_clusters = load_json(base_dir / "unknown_log_clusters.json")
    unknown_rows = load_jsonl(base_dir / "unknown_log_pool.jsonl")
    feedback_rows = load_jsonl(base_dir / "feedback_records.jsonl")

    if not unknown_clusters and unknown_rows:
        unknown_clusters = cluster_unknown_observations(unknown_rows)

    min_unknown = int(suggestion_cfg.get("min_unknown_occurrence_for_suggestion", 3))
    min_feedback = int(suggestion_cfg.get("min_feedback_occurrence_for_suggestion", 2))

    unknown_suggestions = build_unknown_rule_suggestions(unknown_clusters, min_occurrence=min_unknown)
    feedback_suggestions, problematic_rules = build_feedback_rule_suggestions(feedback_rows, min_occurrence=min_feedback)
    yaml_fragment = render_yaml_fragment(unknown_suggestions, feedback_suggestions)

    result = {
        "generated_at": datetime.utcnow().isoformat(),
        "mode": "local",
        "summary": {
            "unknown_clusters_total": len(unknown_clusters),
            "unknown_rows_total": len(unknown_rows),
            "feedback_records_total": len(feedback_rows),
            "new_rule_suggestions": len(unknown_suggestions),
            "rule_fix_suggestions": len(feedback_suggestions),
            "high_frequency_misclassified_patterns": len(problematic_rules),
        },
        "new_rule_suggestions": unknown_suggestions,
        "rule_fix_suggestions": feedback_suggestions,
        "high_frequency_misclassified_patterns": problematic_rules,
        "parser_rules_yaml_fragment": yaml_fragment,
        "review_required": True,
        "note": "These are review-only suggestions. Do NOT overwrite production parser rules without approval.",
        "llm_assisted": {"used": False, "fallback_to_local": False},
    }

    allow_llm = bool(suggestion_cfg.get("allow_llm_assisted_suggestions", True))
    effective_mode = args.mode
    if effective_mode == "auto":
        effective_mode = "llm" if allow_llm else "local"

    if effective_mode == "llm" and allow_llm:
        llm_bundle = build_llm_rule_suggestions(
            parser_rules=parser_rules,
            unknown_suggestions=unknown_suggestions,
            feedback_suggestions=feedback_suggestions,
            llm_config=(active_learning_cfg.get("llm_suggestion") or {}),
        )
        result["llm_assisted"] = {
            "used": llm_bundle["used"],
            "fallback_to_local": llm_bundle["fallback_to_local"],
            "request_payload": llm_bundle.get("request_payload"),
            "response_payload": llm_bundle.get("response_payload"),
        }
        if llm_bundle["used"]:
            llm_result = llm_bundle["result"]
            result["mode"] = "llm"
            result["new_rule_suggestions_llm"] = llm_result.get("new_rule_suggestions", [])
            result["rule_fix_suggestions_llm"] = llm_result.get("rule_fix_suggestions", [])
            result["high_frequency_misclassified_patterns_llm"] = llm_result.get("high_frequency_misclassified_patterns", [])
            result["parser_rules_yaml_fragment_llm"] = llm_result.get("parser_rules_yaml_fragment", {"custom_candidates": [], "feedback_adjustments": []})
            result["review_required"] = True
        else:
            result["mode"] = "local"

    text = yaml.safe_dump(result, allow_unicode=True, sort_keys=False)
    print(text)

    if args.write:
        out_path = output_dir / f"rule_suggestions_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.yaml"
        out_path.write_text(text, encoding="utf-8")
        print(f"[OK] suggestion file written to: {out_path}")


if __name__ == "__main__":
    main()
