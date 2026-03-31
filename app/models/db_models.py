from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UploadTaskModel(Base):
    __tablename__ = "upload_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_uuid: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    filename: Mapped[str] = mapped_column(String(512))
    stored_path: Mapped[str] = mapped_column(String(1024))
    status: Mapped[str] = mapped_column(String(32), default="uploaded")
    file_count: Mapped[int] = mapped_column(Integer, default=0)
    total_events: Mapped[int] = mapped_column(Integer, default=0)
    total_errors: Mapped[int] = mapped_column(Integer, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    queue_position: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    events = relationship("NormalizedEventModel", back_populates="task", cascade="all, delete-orphan")


class TaskAuditLogModel(Base):
    __tablename__ = "task_audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int | None] = mapped_column(ForeignKey("upload_tasks.id"), nullable=True, index=True)
    task_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="info")
    stage: Mapped[str | None] = mapped_column(String(128), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    actor: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class NormalizedEventModel(Base):
    __tablename__ = "normalized_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("upload_tasks.id"), index=True)
    source_file: Mapped[str] = mapped_column(String(512), index=True)
    parser_name: Mapped[str] = mapped_column(String(128))
    original_time_text: Mapped[str | None] = mapped_column(String(128), nullable=True)
    parsed_datetime: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    epoch_ms: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    formatted_ms: Mapped[str | None] = mapped_column(String(64), nullable=True)
    level: Mapped[str] = mapped_column(String(16), default="INFO", index=True)
    component: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    module: Mapped[str | None] = mapped_column(String(256), nullable=True)
    thread: Mapped[str | None] = mapped_column(String(128), nullable=True)
    method_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    class_name: Mapped[str | None] = mapped_column(String(256), nullable=True)
    source_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    line_no: Mapped[int | None] = mapped_column(Integer, nullable=True)
    message: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str] = mapped_column(Text)
    cycle_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    sub_step: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    chip_name: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    stage_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    board_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    event_kind: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    direction: Mapped[str | None] = mapped_column(String(32), nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    normalized_signature: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_family: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cycle_inferred: Mapped[bool] = mapped_column(Boolean, default=False)
    cycle_infer_method: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cycle_infer_confidence: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cycle_infer_reason: Mapped[str | None] = mapped_column(String(128), nullable=True)
    extra_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    task = relationship("UploadTaskModel", back_populates="events")

    __table_args__ = (
        Index("idx_event_task_time", "task_id", "epoch_ms"),
        Index("idx_event_task_sig", "task_id", "normalized_signature"),
    )


class StepSummaryModel(Base):
    __tablename__ = "step_summaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("upload_tasks.id"), index=True)
    cycle_no: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    parameter_name: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    sub_step: Mapped[str] = mapped_column(String(256), index=True)
    component: Mapped[str | None] = mapped_column(String(128), nullable=True)
    chip_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    start_epoch_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    end_epoch_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_over_threshold: Mapped[bool] = mapped_column(Boolean, default=False)
    start_time_text: Mapped[str | None] = mapped_column(String(64), nullable=True)
    end_time_text: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ErrorClusterModel(Base):
    __tablename__ = "error_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("upload_tasks.id"), index=True)
    normalized_signature: Mapped[str] = mapped_column(String(128), index=True)
    error_family: Mapped[str | None] = mapped_column(String(128), nullable=True)
    severity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    representative_message: Mapped[str] = mapped_column(Text)
    representative_exception: Mapped[str | None] = mapped_column(String(256), nullable=True)
    component: Mapped[str | None] = mapped_column(String(128), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_epoch_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    last_seen_epoch_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


class LLMAnalysisResultModel(Base):
    __tablename__ = "llm_analysis_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("upload_tasks.id"), index=True)
    normalized_signature: Mapped[str] = mapped_column(String(128), index=True)
    model_name: Mapped[str] = mapped_column(String(128))
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    analysis_stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    request_payload: Mapped[str] = mapped_column(Text)
    response_payload: Mapped[str] = mapped_column(Text)
    chinese_summary: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(String(32), default="pending_verification", index=True)
    is_reviewer: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    force_password_change: Mapped[bool] = mapped_column(Boolean, default=False)
    email_verified: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approval_requested_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    approved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    failed_login_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    registration_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class UserSessionModel(Base):
    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class EmailVerificationCodeModel(Base):
    __tablename__ = "email_verification_codes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    code_hash: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    resend_count: Mapped[int] = mapped_column(Integer, default=1)
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class RegistrationChallengeModel(Base):
    __tablename__ = "registration_challenges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(512))
    registration_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    code_hash: Mapped[str] = mapped_column(String(128), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    last_sent_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    resend_count: Mapped[int] = mapped_column(Integer, default=1)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    verification_token_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True, index=True)
    verification_token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    request_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ModuleConfigModel(Base):
    __tablename__ = "solution_module_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    module_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    prefix: Mapped[str] = mapped_column(String(8), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class ErrorCodeSequenceModel(Base):
    __tablename__ = "error_code_sequences"

    prefix: Mapped[str] = mapped_column(String(8), primary_key=True)
    next_value: Mapped[int] = mapped_column(Integer, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class TaskClusterModel(Base):
    __tablename__ = "task_clusters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    cluster_key: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="approved", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_system: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SolutionRecordModel(Base):
    __tablename__ = "solution_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    error_name: Mapped[str] = mapped_column(String(256), index=True)
    error_category: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    module: Mapped[str] = mapped_column(String(128), index=True)
    submodule: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_code: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    error_code_prefix: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    normalized_signature: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    exception_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    trigger_scenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    impact_scope: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_source: Mapped[str | None] = mapped_column(String(256), nullable=True)
    related_logs: Mapped[str | None] = mapped_column(Text, nullable=True)
    related_source_files: Mapped[str | None] = mapped_column(Text, nullable=True)
    root_cause_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    verified_solution: Mapped[str | None] = mapped_column(Text, nullable=True)
    workaround: Mapped[str | None] = mapped_column(Text, nullable=True)
    owner_department: Mapped[str | None] = mapped_column(String(128), nullable=True)
    submitter: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="approved", index=True)
    reusable: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    similar_case_refs: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("idx_solution_module_code", "module", "error_code"),
        Index("idx_solution_sig_module", "normalized_signature", "module"),
    )


class SolutionTaskLinkModel(Base):
    __tablename__ = "solution_task_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution_records.id"), index=True)
    task_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    normalized_signature: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), default="reference", index=True)
    source_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("solution_id", "task_uuid", "normalized_signature", name="uq_solution_task_link"),
    )


class SolutionModuleLinkModel(Base):
    __tablename__ = "solution_module_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution_records.id"), index=True)
    module_config_id: Mapped[int | None] = mapped_column(ForeignKey("solution_module_configs.id"), nullable=True, index=True)
    module_key: Mapped[str] = mapped_column(String(64), index=True)
    module_display_name: Mapped[str] = mapped_column(String(128), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("solution_id", "module_key", name="uq_solution_module_link"),
    )


class SolutionTaskClusterLinkModel(Base):
    __tablename__ = "solution_task_cluster_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution_records.id"), index=True)
    cluster_id: Mapped[int] = mapped_column(ForeignKey("task_clusters.id"), index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("solution_id", "cluster_id", name="uq_solution_cluster_link"),
    )


class SolutionTagModel(Base):
    __tablename__ = "solution_tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(96), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)


class SolutionTagLinkModel(Base):
    __tablename__ = "solution_tag_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution_records.id"), index=True)
    tag_id: Mapped[int] = mapped_column(ForeignKey("solution_tags.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("solution_id", "tag_id", name="uq_solution_tag_link"),
    )


class SolutionMessageKeywordModel(Base):
    __tablename__ = "solution_message_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    solution_id: Mapped[int] = mapped_column(ForeignKey("solution_records.id"), index=True)
    keyword: Mapped[str] = mapped_column(String(128), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        UniqueConstraint("solution_id", "keyword", name="uq_solution_keyword_link"),
    )


class SolutionReviewRecordModel(Base):
    __tablename__ = "solution_review_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_uuid: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    normalized_signature: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)
    module: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    submodule: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    submission_type: Mapped[str] = mapped_column(String(64), default="solution_record", index=True)
    proposed_payload: Mapped[str] = mapped_column(Text)
    attachments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending_review", index=True)
    review_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    revision_suggestions: Mapped[str | None] = mapped_column(Text, nullable=True)
    completeness_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    reusability_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    clarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_payload: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_history_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    linked_solution_id: Mapped[int | None] = mapped_column(ForeignKey("solution_records.id"), nullable=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
