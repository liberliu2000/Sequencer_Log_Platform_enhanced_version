from __future__ import annotations

import json
from typing import Any


def _compact_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)


def build_error_analysis_prompt(
    error_cluster: dict[str, Any],
    context_events: list[dict[str, Any]],
    stats: dict[str, Any],
    *,
    mode: str = "medium",
    template: dict | None = None,
    user_context: dict[str, Any] | None = None,
    source_snippets: list[dict[str, Any]] | None = None,
    similar_cases: list[dict[str, Any]] | None = None,
    depth_strategy: dict[str, Any] | None = None,
) -> str:
    template = template or {}
    user_context = user_context or {}
    source_snippets = source_snippets or []
    similar_cases = similar_cases or []
    depth_strategy = depth_strategy or {}

    policy = template.get("analysis_policy") or "优先根据当前日志直接证据判断，再引用历史经验辅助推断，最后明确未验证假设。"
    response_schema = {
        "root_cause_summary": "",
        "probable_module": "",
        "evidence_chain": [],
        "direct_evidence": [],
        "historical_inferences": [],
        "unverified_hypotheses": [],
        "possible_causes": [],
        "affected_modules": [],
        "recommended_checks": [],
        "troubleshooting_steps": [],
        "possible_fix_paths": [],
        "risk_warnings": [],
        "owner_departments": [],
        "severity": "",
        "confidence": 0.0,
    }
    allowed_departments = ["软件控制", "流路系统", "光学系统", "运动平台", "温控系统", "调度系统", "数据算法", "硬件电气", "测试运维"]
    compact_stats = {
        "stage": stats.get("stage"),
        "matched_event_count": stats.get("matched_event_count"),
        "candidate_row_count": stats.get("candidate_row_count"),
        "anchor_components": stats.get("anchor_components"),
        "anchor_cycles": stats.get("anchor_cycles"),
        "anchor_chip_names": stats.get("anchor_chip_names"),
        "context_summary": stats.get("context_summary", {}),
    }
    output_style = {
        "low": "输出简洁，优先给出最可能原因、模块归属、优先检查项。",
        "medium": "输出中等详细程度，补充关键证据、责任部门、建议排查路径。",
        "high": "输出完整，给出分层根因分析、证据链、修复路径和风险提示。",
    }.get(str(depth_strategy.get("depth") or mode), "输出结构化结论。")

    return (
        "你是测序仪错误综合诊断助手。请基于当前日志、用户补充场景、最小必要源码片段和少量历史案例，输出 JSON。\n"
        f"返回字段 schema={_compact_json(response_schema)}\n"
        f"owner_departments 只能从 {allowed_departments} 中选择。\n"
        "强约束：\n"
        "1. direct_evidence 只能写当前日志、当前场景、当前源码片段中可直接支持的事实。\n"
        "2. historical_inferences 只能写由历史案例辅助得到的推断，不能当作已证实结论。\n"
        "3. unverified_hypotheses 只能写尚待验证的假设。\n"
        "4. 不要引用未提供的外部事实，不要扩写无关源码。\n"
        f"5. {policy}\n"
        f"6. {output_style}\n"
        f"分析深度策略={_compact_json(depth_strategy)}\n"
        f"当前错误簇={_compact_json(error_cluster)}\n"
        f"当前日志最小必要上下文={_compact_json(context_events)}\n"
        f"当前日志统计={_compact_json(compact_stats)}\n"
        f"用户补充上下文={_compact_json(user_context)}\n"
        f"当前相关源码片段={_compact_json(source_snippets)}\n"
        f"历史相似案例摘要={_compact_json(similar_cases)}"
    )
