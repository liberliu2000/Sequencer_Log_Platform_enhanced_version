from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class RawLogRecord(BaseModel):
    source_file: str
    parser_name: str
    raw_text: str
    original_time_text: str | None = None
    level: str | None = None
    component: str | None = None
    module: str | None = None
    thread: str | None = None
    method_name: str | None = None
    class_name: str | None = None
    source_path: str | None = None
    line_no: int | None = None
    message: str
    extra: dict[str, Any] = Field(default_factory=dict)


class NormalizedEvent(BaseModel):
    source_file: str
    parser_name: str
    original_time_text: str | None = None
    parsed_datetime: datetime | None = None
    epoch_ms: int | None = None
    formatted_ms: str | None = None
    level: str = "INFO"
    component: str | None = None
    module: str | None = None
    thread: str | None = None
    method_name: str | None = None
    class_name: str | None = None
    source_path: str | None = None
    line_no: int | None = None
    message: str
    raw_text: str
    cycle_no: int | None = None
    sub_step: str | None = None
    instrument_scope: str | None = None
    side_scope: str | None = None
    side_group: str | None = None
    chip_name: str | None = None
    chip_position: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    stage_key: str | None = None
    stage_name: str | None = None
    board_name: str | None = None
    event_kind: str | None = None
    direction: str | None = None
    duration_ms: float | None = None
    status: str | None = None
    error_code: str | None = None
    exception_type: str | None = None
    normalized_signature: str | None = None
    error_family: str | None = None
    severity: str | None = None
    cycle_inferred: bool = False
    cycle_infer_method: str | None = None
    cycle_infer_confidence: str | None = None
    cycle_infer_reason: str | None = None
    side_confidence: float | None = None
    side_evidence: dict[str, Any] = Field(default_factory=dict)
    extra_json: dict[str, Any] = Field(default_factory=dict)


class CycleSummary(BaseModel):
    cycle_no: int | None = None
    instrument_scope: str | None = None
    side_scope: str | None = None
    side_group: str | None = None
    chip_name: str | None = None
    chip_position: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    stage_key: str | None = None
    side_confidence: float | None = None
    side_evidence: dict[str, Any] = Field(default_factory=dict)
    total_duration_ms: float | None = None
    started_at: int | None = None
    ended_at: int | None = None


class StepSummary(BaseModel):
    cycle_no: int | None = None
    parameter_name: str | None = None
    sub_step: str
    component: str | None = None
    instrument_scope: str | None = None
    side_scope: str | None = None
    side_group: str | None = None
    chip_name: str | None = None
    chip_position: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    stage_key: str | None = None
    start_epoch_ms: int | None = None
    end_epoch_ms: int | None = None
    duration_ms: float | None = None
    threshold_ms: float | None = None
    is_over_threshold: bool = False
    start_time_text: str | None = None
    end_time_text: str | None = None
    side_confidence: float | None = None
    side_evidence: dict[str, Any] = Field(default_factory=dict)


class ParameterResult(BaseModel):
    parameter_name: str
    parameter_display_name: str
    cycle: int | None = None
    slide: str | None = None
    instrument_scope: str | None = None
    side_scope: str | None = None
    side_group: str | None = None
    chip_name: str | None = None
    chip_position: str | None = None
    chuck_no: str | None = None
    slot_no: str | None = None
    stage_key: str | None = None
    duration_seconds: float | None = None
    duration_ms: float | None = None
    start_time: str | None = None
    end_time: str | None = None
    start_message: str | None = None
    end_message: str | None = None
    source_file: str | None = None
    source_type: str
    threshold: float | None = None
    expected: float | None = None
    is_exceed: bool = False
    component: str | None = None
    start_event_id: int | None = None
    end_event_id: int | None = None
    side_confidence: float | None = None
    side_evidence: dict[str, Any] = Field(default_factory=dict)
    extra: dict[str, Any] = Field(default_factory=dict)


class ErrorSignature(BaseModel):
    normalized_signature: str
    error_family: str | None = None
    error_severity: str | None = None
    representative_message: str
    exception_type: str | None = None
    function_name: str | None = None


class ErrorOccurrence(BaseModel):
    normalized_signature: str
    event_id: int | None = None
    cycle_no: int | None = None
    component: str | None = None
    epoch_ms: int | None = None
    message: str


class LLMAnalysisResult(BaseModel):
    root_cause_summary: str = ""
    probable_module: str | None = None
    evidence_chain: list[str] = Field(default_factory=list)
    direct_evidence: list[str] = Field(default_factory=list)
    historical_inferences: list[str] = Field(default_factory=list)
    unverified_hypotheses: list[str] = Field(default_factory=list)
    possible_causes: list[str] = Field(default_factory=list)
    affected_modules: list[str] = Field(default_factory=list)
    recommended_checks: list[str] = Field(default_factory=list)
    troubleshooting_steps: list[str] = Field(default_factory=list)
    possible_fix_paths: list[str] = Field(default_factory=list)
    risk_warnings: list[str] = Field(default_factory=list)
    owner_departments: list[str] = Field(default_factory=list)
    severity: str = "unknown"
    confidence: float = 0.0


class SourceContextSnippet(BaseModel):
    file_name: str
    snippet_reason: str
    language: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str
    score: float = 0.0


class SimilarCaseSummary(BaseModel):
    case_id: int
    error_name: str
    normalized_signature: str | None = None
    module: str
    error_code: str | None = None
    trigger_scenario_summary: str | None = None
    root_cause_summary: str | None = None
    solution_summary: str | None = None
    success_flag: bool = False
    similarity_score: float = 0.0


class SolutionReviewResult(BaseModel):
    review_status: str = "needs_revision"
    review_reason: str = ""
    revision_suggestions: list[str] = Field(default_factory=list)
    completeness_score: float = 0.0
    reusability_score: float = 0.0
    clarity_score: float = 0.0
    llm_used: bool = False


class UploadTaskResponse(BaseModel):
    task_uuid: str
    status: str
    message: str | None = None
    file_count: int = 0
    filename: str | None = None
    total_events: int = 0
    total_errors: int = 0
    progress_percent: int = 0
    current_stage: str | None = None
    queue_position: int | None = None
    cpu_cores: int | None = None
    started_at: str | None = None
    finished_at: str | None = None
    elapsed_seconds: float | None = None


class DashboardSummary(BaseModel):
    file_count: int
    total_events: int
    total_errors: int
    unique_error_count: int
    top_errors: list[dict[str, Any]]
    component_distribution: list[dict[str, Any]]


def build_raw_log_record(**kwargs: Any) -> RawLogRecord:
    return RawLogRecord.model_construct(**kwargs)


def build_normalized_event(**kwargs: Any) -> NormalizedEvent:
    return NormalizedEvent.model_construct(**kwargs)
