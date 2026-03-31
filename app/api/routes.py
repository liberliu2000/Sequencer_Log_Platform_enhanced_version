from __future__ import annotations

from pathlib import Path
import json
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user, require_reviewer_user
from app.core.settings import get_settings
from app.db.session import get_db
from app.repositories.task_repository import TaskRepository
from app.schemas.common import DashboardSummary, UploadTaskResponse
from app.services.config_service import ConfigService
from app.services.export_service import ExportService
from app.services.ingestion_service import IngestionService
from app.services.llm_service import LLMService
from app.services.performance_service import PerformanceService
from app.services.pipeline_parallel import PIPELINE_STAGE_PLAN
from app.services.prompt_template_service import PromptTemplateService
from app.services.query_service import QueryService
from app.services.solution_repository import SolutionRepositoryService
from app.services.solution_review_service import SolutionReviewService
from app.services.case_retriever import CaseRetriever
from app.services.analysis_depth_manager import AnalysisDepthManager
from app.services.solution_catalog_service import SolutionCatalogService
from app.services.task_queue import queue
from app.services.task_state_cache import task_state_cache
from app.services.feedback_service import FeedbackService
from app.services.env_file_service import EnvFileService
from app.parsers.unknown_log_handler import UnknownLogHandler

router = APIRouter()


def _dt_text(v):
    return v.isoformat() if hasattr(v, 'isoformat') else str(v or '')


def _load_json(path: Path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _load_jsonl(path: Path, limit: int = 200):
    if not path.exists():
        return []
    rows = []
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue
    return rows[-limit:]


def _save_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _active_learning_dir() -> Path:
    return Path(get_settings().data_dir) / "active_learning"


def _rule_review_store() -> Path:
    return _active_learning_dir() / "rule_suggestion_reviews.json"


def _rule_preview_cache_store() -> Path:
    return _active_learning_dir() / "rule_suggestion_preview_cache.json"


def _load_rule_reviews() -> dict:
    return _load_json(_rule_review_store())


def _load_rule_preview_cache() -> dict:
    return _load_json(_rule_preview_cache_store())


def _save_rule_preview_cache(data: dict):
    _save_json(_rule_preview_cache_store(), data)


def _apply_rule_review_status(items: list[dict]) -> list[dict]:
    reviews = _load_rule_reviews()
    out = []
    for item in items:
        row = dict(item)
        rv = reviews.get(str(row.get("suggestion_id") or ""), {})
        if rv:
            row["review_status"] = rv.get("review_status", row.get("status", "pending_review"))
            row["review_history"] = rv.get("review_history", [])
        else:
            row.setdefault("review_status", row.get("status", "pending_review"))
            row.setdefault("review_history", [])
        out.append(row)
    return out


def _update_rule_review_status(suggestion_id: str, review_status: str, reviewer: str | None = None, notes: str | None = None) -> dict:
    reviews = _load_rule_reviews()
    item = reviews.get(suggestion_id, {"suggestion_id": suggestion_id, "review_history": []})
    history = list(item.get("review_history") or [])
    history.append({"review_status": review_status, "reviewed_at": __import__('datetime').datetime.utcnow().isoformat(), "reviewer": reviewer, "notes": notes})
    item["review_status"] = review_status
    item["review_history"] = history[-50:]
    reviews[suggestion_id] = item
    _save_json(_rule_review_store(), reviews)
    return item


def _parse_csv_param(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []
    return [part.strip() for part in str(raw_value).split(',') if part and part.strip()]


def _parse_json_text(raw_value: str | None, default):
    if not raw_value:
        return default
    try:
        return json.loads(raw_value)
    except Exception:
        return default


async def _save_uploaded_context_files(task_uuid: str, signature: str, uploads: list[UploadFile] | None) -> list[Path]:
    saved: list[Path] = []
    if not uploads:
        return saved
    base_dir = Path(get_settings().data_dir) / "source_context_uploads" / task_uuid / signature
    base_dir.mkdir(parents=True, exist_ok=True)
    for upload in uploads:
        safe_name = Path(upload.filename or f"source_{uuid.uuid4().hex[:8]}").name
        out_path = base_dir / f"{uuid.uuid4().hex[:8]}_{safe_name}"
        with out_path.open("wb") as f:
            while True:
                chunk = await upload.read(get_settings().chunk_size)
                if not chunk:
                    break
                f.write(chunk)
        await upload.close()
        saved.append(out_path)
    return saved


def _filter_rule_suggestions_by_signature(items: list[dict], selected_signatures: list[str]) -> list[dict]:
    if not selected_signatures:
        return list(items)
    selected = set(selected_signatures)
    out = []
    for item in items:
        sig = str(item.get('cluster_signature') or '')
        if sig and sig in selected:
            out.append(item)
    return out


def _llm_preview_cache_key(selected_signatures: list[str]) -> str:
    if not selected_signatures:
        return 'llm_preview_all'
    joined = '|'.join(sorted(selected_signatures))
    return f"llm_preview_{abs(hash(joined))}"


@router.get('/health')
def health():
    return {'status': 'ok', 'queue_pending': len(queue.pending), 'pipeline_stages': PIPELINE_STAGE_PLAN}


@router.post('/tasks/upload', response_model=UploadTaskResponse)
async def upload_logs(files: list[UploadFile] = File(...), cpu_cores: int = Form(default=1), db: Session = Depends(get_db)):
    settings = get_settings()
    repo = TaskRepository(db)
    task_uuid = uuid.uuid4().hex
    batch_dir = Path(settings.upload_dir) / task_uuid
    batch_dir.mkdir(parents=True, exist_ok=True)
    saved_count = 0
    total_bytes = 0
    for upload in files:
        safe_name = Path(upload.filename or f'upload_{saved_count+1}').name
        out_path = batch_dir / safe_name
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with out_path.open('wb') as f:
            while True:
                chunk = await upload.read(settings.chunk_size)
                if not chunk:
                    break
                f.write(chunk)
                total_bytes += len(chunk)
        await upload.close()
        saved_count += 1
    display_name = files[0].filename if len(files) == 1 else f'batch_{saved_count}files'
    task = repo.create_task(task_uuid=task_uuid, filename=display_name or f'batch_{saved_count}files', stored_path=str(batch_dir))
    repo.update_task_progress(task.id, status='queued', current_stage='等待异步任务队列调度', file_count=saved_count, message=f'批量上传完成，共 {saved_count} 个文件，{round(total_bytes / 1024 / 1024, 2)} MB')
    task_state_cache.init_task(task_uuid, display_name, cpu_cores=cpu_cores)
    task_state_cache.update(task_uuid, status='queued', current_stage='等待异步任务队列调度', file_count=saved_count, message=f'批量上传完成，共 {saved_count} 个文件，{round(total_bytes / 1024 / 1024, 2)} MB', cpu_cores=cpu_cores)
    position = queue.submit(task_uuid, lambda: IngestionService.process_task_by_uuid(task_uuid, cpu_cores=cpu_cores))
    repo.update_task_progress(task.id, queue_position=position)
    task_state_cache.update(task_uuid, status='queued', current_stage='等待异步任务队列调度', queue_position=position, file_count=saved_count, message=f'已进入队列，第 {position} 位', cpu_cores=cpu_cores)
    return UploadTaskResponse(task_uuid=task_uuid, status='queued', message=f'任务已提交，前方排队 {max(position - 1, 0)} 个', file_count=saved_count, filename=display_name, total_events=0, total_errors=0, progress_percent=0, current_stage='已上传，等待处理', queue_position=position, cpu_cores=cpu_cores)


@router.get('/tasks')
def list_tasks(page: int = Query(default=1, ge=1), page_size: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    tasks = repo.list_tasks()
    total = len(tasks)
    offset = (page - 1) * page_size
    items = tasks[offset: offset + page_size]
    return {
        'items': [{'task_uuid': t.task_uuid, 'filename': t.filename, 'status': t.status, 'file_count': t.file_count, 'total_events': t.total_events, 'total_errors': t.total_errors, 'progress_percent': t.progress_percent, 'current_stage': t.current_stage, 'queue_position': t.queue_position, 'message': t.message, 'created_at': _dt_text(t.created_at), 'updated_at': _dt_text(t.updated_at)} for t in items],
        'total': total,
        'page': page,
        'page_size': page_size,
    }


@router.get('/tasks/{task_uuid}/status')
def task_status(task_uuid: str, db: Session = Depends(get_db)):
    cached = task_state_cache.get(task_uuid)
    if cached is not None:
        return cached
    task = TaskRepository(db).get_task_by_uuid(task_uuid)
    if not task:
        raise HTTPException(status_code=404, detail='任务不存在')
    perf = PerformanceService().read_summary(task_uuid)
    return {'task_uuid': task.task_uuid, 'filename': task.filename, 'status': task.status, 'file_count': task.file_count, 'total_events': task.total_events, 'total_errors': task.total_errors, 'progress_percent': task.progress_percent, 'current_stage': task.current_stage, 'queue_position': task.queue_position or queue.queue_position(task.task_uuid), 'message': task.message, 'created_at': _dt_text(task.created_at), 'updated_at': _dt_text(task.updated_at), 'cpu_cores': perf.get('cpu_cores'), 'elapsed_seconds': perf.get('stage_timings', {}).get('total_seconds'), 'started_at': None, 'finished_at': None}


@router.get('/tasks/{task_uuid}/performance-summary')
def performance_summary(task_uuid: str):
    return PerformanceService().read_summary(task_uuid)


@router.get('/tasks/{task_uuid}/dashboard', response_model=DashboardSummary)
def dashboard(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_dashboard(task.id)


@router.get('/tasks/{task_uuid}/events')
def events(task_uuid: str, component: str | None = None, level: str | None = None, cycle_no: int | None = None, chip_name: str | None = None, search: str | None = None, limit: int = Query(default=100, le=500), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.list_events(task.id, component, level, cycle_no, chip_name, search, limit, offset)


@router.get('/tasks/{task_uuid}/cycles')
def list_cycles(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.list_cycles(task.id)


@router.get('/tasks/{task_uuid}/steps')
def step_summaries(task_uuid: str, cycle_no: int | None = None, parameter_name: str | None = None, limit: int = Query(default=100, le=500), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_step_summaries(task.id, cycle_no=cycle_no, parameter_name=parameter_name, offset=offset, limit=limit)


@router.get('/tasks/{task_uuid}/cycle-summary')
def cycle_summary(task_uuid: str, unit: str = Query(default='ms'), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_cycle_summaries(task.id, unit=unit)


@router.get('/tasks/{task_uuid}/movement-timeline')
def movement_timeline(task_uuid: str, cycle_no: int | None = None, track_order: str = Query(default='default'), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_movement_timeline(task.id, cycle_no=cycle_no, track_order=track_order)


@router.get('/tasks/{task_uuid}/movement-timeline/errors')
def movement_timeline_errors(task_uuid: str, cycle_no: int | None = None, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_timeline_error_points(task.id, cycle_no=cycle_no)


@router.get('/tasks/{task_uuid}/operational-metrics')
def operational_metrics(task_uuid: str, cycle_no: int | None = None, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_operational_metrics(task.id, cycle_no=cycle_no)


@router.get('/tasks/{task_uuid}/temperature-cycle-validation')
def temperature_cycle_validation(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_temperature_cycle_validation(task.id)


@router.get('/tasks/{task_uuid}/errors')
def error_clusters(task_uuid: str, limit: int = Query(default=100, le=500), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_error_clusters(task.id, offset=offset, limit=limit)


@router.get('/tasks/{task_uuid}/errors/trend')
def error_trend(task_uuid: str, signature: str | None = None, family: str | None = None, bucket: str = Query(default='day'), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_error_regression_trend(task.id, signature=signature, family=family, bucket=bucket)


@router.post('/tasks/{task_uuid}/errors/{signature}/analyze')
async def analyze_signature(
    task_uuid: str,
    signature: str,
    force: bool = Query(default=False),
    analysis_depth: str = Form(default="medium"),
    trigger_scenario: str | None = Form(default=None),
    module: str | None = Form(default=None),
    submodule: str | None = Form(default=None),
    environment_info: str | None = Form(default=None),
    reproduction_steps: str | None = Form(default=None),
    customer_symptom: str | None = Form(default=None),
    operation_path: str | None = Form(default=None),
    source_notes: str | None = Form(default=None),
    existing_solution_json: str | None = Form(default=None),
    source_files: list[UploadFile] | None = File(default=None),
    db: Session = Depends(get_db),
):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    saved_files = await _save_uploaded_context_files(task_uuid, signature, source_files)
    return LLMService(db).analyze_signature(
        task.id,
        signature,
        force=force,
        analysis_depth=analysis_depth,
        trigger_scenario=trigger_scenario,
        module=module,
        submodule=submodule,
        environment_info=environment_info,
        reproduction_steps=reproduction_steps,
        customer_symptom=customer_symptom,
        operation_path=operation_path,
        source_notes=source_notes,
        existing_solution=_parse_json_text(existing_solution_json, {}),
        source_files=saved_files,
    )


@router.get('/tasks/{task_uuid}/llm-results')
def list_llm_results(task_uuid: str, normalized_signature: str | None = None, limit: int = Query(default=200, ge=1, le=1000), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    rows = LLMService(db).list_results(task.id)
    if normalized_signature:
        rows = [row for row in rows if str(row.get('normalized_signature') or '') == normalized_signature]
    return rows[:limit]


@router.get('/tasks/{task_uuid}/llm-results/latest')
def latest_llm_result(task_uuid: str, normalized_signature: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    rows = LLMService(db).list_results(task.id)
    for row in rows:
        if str(row.get('normalized_signature') or '') == normalized_signature:
            return row
    raise HTTPException(status_code=404, detail='未找到对应历史诊断结果')


@router.get('/tasks/{task_uuid}/errors/{signature}/similar-cases')
def similar_cases(task_uuid: str, signature: str, module: str | None = None, trigger_scenario: str | None = None, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    cluster, _, _ = query.get_context_for_signature(task.id, signature, stage="light")
    items = CaseRetriever(db).retrieve_similar_cases(
        normalized_signature=signature,
        message=cluster.get("representative_message"),
        module=module or cluster.get("component"),
        error_code=cluster.get("error_code"),
        trigger_scenario=trigger_scenario,
        limit=5,
    )
    return {"items": items, "total": len(items)}


@router.get('/tasks/{task_uuid}/audit-logs')
def audit_logs(task_uuid: str, limit: int = 200, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_audit_logs(task.id, limit=limit)


@router.get('/tasks/{task_uuid}/files')
def task_files(task_uuid: str, limit: int = Query(default=200, le=500), offset: int = Query(default=0, ge=0), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.list_task_files(task.id, offset=offset, limit=limit)


@router.get('/tasks/{task_uuid}/files/preview')
def preview_file(task_uuid: str, relative_path: str, max_lines: int = 200, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.preview_task_file(task.id, relative_path, max_lines=max_lines)


@router.get('/config')
def get_config():
    return ConfigService().get_all()


@router.put('/config/thresholds')
def update_thresholds(payload: dict):
    return ConfigService().update_thresholds(payload)


@router.get('/config/env')
def get_env_items():
    return {"items": EnvFileService().list_items()}


@router.get('/config/env/{key}')
def get_env_item(key: str):
    try:
        return EnvFileService().get_item(key)
    except KeyError:
        raise HTTPException(status_code=404, detail='env key not found')


@router.put('/config/env/{key}')
def update_env_item(key: str, payload: dict):
    if "value" not in payload:
        raise HTTPException(status_code=400, detail='missing value')
    try:
        return EnvFileService().update_item(key, str(payload.get("value") or ""))
    except KeyError:
        raise HTTPException(status_code=404, detail='env key not found')


@router.post('/config/env/{key}/reset')
def reset_env_item(key: str):
    try:
        return EnvFileService().reset_item(key)
    except KeyError:
        raise HTTPException(status_code=404, detail='env key not found or default missing')


@router.get('/config/prompt-templates')
def get_prompt_templates():
    return PromptTemplateService().get_templates()


@router.put('/config/prompt-templates/active')
def set_active_prompt_template(payload: dict):
    version = payload.get('version')
    if not version:
        raise HTTPException(status_code=400, detail='缺少 version')
    return PromptTemplateService().set_active_version(version)


@router.get('/parameter-definitions')
def parameter_definitions(db: Session = Depends(get_db)):
    return QueryService(db).get_parameter_definitions()


@router.get('/tasks/{task_uuid}/parameter-series/{parameter_name}')
def parameter_series(task_uuid: str, parameter_name: str, unit: str = Query(default='s'), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_parameter_series(task.id, parameter_name, unit=unit)


@router.get('/tasks/{task_uuid}/row-scan-metric-series')
def row_scan_metric_series(task_uuid: str, unit: str = Query(default='ms'), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_row_scan_metric_stage_series(task.id, unit=unit)


@router.get('/tasks/{task_uuid}/substep-cycle-series')
def substep_cycle_series(task_uuid: str, agg_mode: str = Query(default='mean'), unit: str = Query(default='s'), db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    return query.get_substep_cycle_series(task.id, agg_mode=agg_mode, unit=unit)




@router.get('/active-learning/unknown-clusters')
def active_learning_unknown_clusters(limit: int = Query(default=100, ge=1, le=1000), min_occurrence: int = Query(default=1, ge=1), review_status: str | None = None):
    items = UnknownLogHandler().list_clusters(limit=limit, min_occurrence=min_occurrence, review_status=review_status)
    return {'items': items, 'total': len(items)}


@router.post('/active-learning/unknown-clusters/{signature}/review')
def review_unknown_cluster(signature: str, payload: dict):
    review_status = str(payload.get('review_status') or '').strip()
    if not review_status:
        raise HTTPException(status_code=400, detail='缺少 review_status')
    try:
        row = UnknownLogHandler().update_review_status(signature, review_status, reviewer=payload.get('reviewer'), notes=payload.get('notes'))
    except KeyError:
        raise HTTPException(status_code=404, detail='未知日志簇不存在')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'ok', 'item': row}


@router.get('/active-learning/feedback-records')
def active_learning_feedback_records(limit: int = Query(default=100, ge=1, le=1000), correction_type: str | None = None, source_file: str | None = None, task_uuid: str | None = None, review_status: str | None = None):
    rows = FeedbackService().list_feedback(limit=limit, correction_type=correction_type, source_file=source_file, task_uuid=task_uuid, review_status=review_status)
    return {'items': rows, 'total': len(rows)}


@router.post('/active-learning/feedback-records')
def create_feedback_record(payload: dict):
    required = ['raw_log', 'correction_type', 'source_file']
    missing = [k for k in required if not payload.get(k)]
    if missing:
        raise HTTPException(status_code=400, detail=f"缺少必要字段: {', '.join(missing)}")
    row = FeedbackService().record_feedback(
        raw_log=str(payload.get('raw_log') or ''),
        original_parse_result=payload.get('original_parse_result') or {},
        corrected_result=payload.get('corrected_result') or {},
        correction_type=str(payload.get('correction_type') or ''),
        source_file=str(payload.get('source_file') or ''),
        user_id=payload.get('user_id'),
        notes=payload.get('notes'),
        task_uuid=payload.get('task_uuid'),
    )
    return {'status': 'ok', 'item': row}



@router.get('/active-learning/feedback-clusters')
def active_learning_feedback_clusters(limit: int = Query(default=100, ge=1, le=1000), review_status: str | None = None):
    rows = FeedbackService().list_feedback_clusters(limit=limit, review_status=review_status)
    return {'items': rows, 'total': len(rows)}


@router.post('/active-learning/feedback-records/{feedback_id}/review')
def review_feedback_record(feedback_id: str, payload: dict):
    review_status = str(payload.get('review_status') or '').strip()
    if not review_status:
        raise HTTPException(status_code=400, detail='缺少 review_status')
    try:
        row = FeedbackService().update_feedback_review_status(feedback_id=feedback_id, review_status=review_status, reviewer=payload.get('reviewer'), notes=payload.get('notes'), scope='record')
    except KeyError:
        raise HTTPException(status_code=404, detail='反馈记录不存在')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'ok', 'item': row}


@router.post('/active-learning/feedback-clusters/review')
def review_feedback_cluster(payload: dict):
    review_status = str(payload.get('review_status') or '').strip()
    cluster_key = str(payload.get('cluster_key') or '').strip()
    if not review_status or not cluster_key:
        raise HTTPException(status_code=400, detail='缺少 cluster_key 或 review_status')
    try:
        row = FeedbackService().update_feedback_review_status(cluster_key=cluster_key, review_status=review_status, reviewer=payload.get('reviewer'), notes=payload.get('notes'), scope='cluster')
    except KeyError:
        raise HTTPException(status_code=404, detail='反馈簇不存在')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'ok', 'item': row}


@router.get('/active-learning/rule-suggestions/preview')
def active_learning_rule_suggestions_preview(
    use_llm: bool = Query(default=False),
    force_refresh: bool = Query(default=False),
    selected_signatures: str | None = Query(default=None, description='Comma separated unknown cluster signatures for LLM suggestion generation.'),
):
    from scripts.learn_parser_rules import build_feedback_rule_suggestions, build_llm_rule_suggestions, build_unknown_rule_suggestions, load_json, load_jsonl, render_yaml_fragment

    settings = get_settings()
    parser_rules = ConfigService().get_all().get('parser_rules', {})
    active_learning_cfg = (parser_rules.get('active_learning') or {})
    suggestion_cfg = active_learning_cfg.get('suggestion_generation') or {}
    llm_cfg = active_learning_cfg.get('llm_suggestion') or {}
    base_dir = _active_learning_dir()
    selected_signature_list = _parse_csv_param(selected_signatures)

    unknown_clusters = load_json(base_dir / 'unknown_log_clusters.json')
    feedback_rows = load_jsonl(base_dir / 'feedback_records.jsonl')

    min_unknown = int(suggestion_cfg.get('min_unknown_occurrence_for_suggestion', 3))
    min_feedback = int(suggestion_cfg.get('min_feedback_occurrence_for_suggestion', 2))

    unknown_suggestions = build_unknown_rule_suggestions(unknown_clusters, min_occurrence=min_unknown)
    feedback_suggestions, problematic_rules = build_feedback_rule_suggestions(feedback_rows, min_occurrence=min_feedback)
    yaml_fragment = render_yaml_fragment(unknown_suggestions, feedback_suggestions)

    unknown_suggestions = _apply_rule_review_status(unknown_suggestions)
    feedback_suggestions = _apply_rule_review_status(feedback_suggestions)
    problematic_rules = _apply_rule_review_status(problematic_rules)

    llm_enabled = bool(use_llm) and bool(suggestion_cfg.get('allow_llm_assisted_suggestions', True))
    llm_source_unknown_suggestions = _filter_rule_suggestions_by_signature(unknown_suggestions, selected_signature_list)
    llm_bundle = {
        'used': False,
        'fallback_to_local': False,
        'from_cache': False,
        'request_payload': {},
        'response_payload': {},
        'cache_ttl_seconds': int(llm_cfg.get('preview_cache_ttl_seconds', settings.llm_preview_cache_ttl_seconds)),
        'selected_signatures': selected_signature_list,
        'selected_unknown_cluster_count': len(llm_source_unknown_suggestions),
        'result': {'new_rule_suggestions': [], 'rule_fix_suggestions': [], 'high_frequency_misclassified_patterns': [], 'parser_rules_yaml_fragment': {'custom_candidates': [], 'feedback_adjustments': []}, 'review_required': True},
    }

    if llm_enabled:
        cache_store = _load_rule_preview_cache()
        cache_key = _llm_preview_cache_key(selected_signature_list)
        ttl_seconds = int(llm_cfg.get('preview_cache_ttl_seconds', settings.llm_preview_cache_ttl_seconds))
        cached = cache_store.get(cache_key) if isinstance(cache_store, dict) else None
        fresh_cached = False
        if cached and not force_refresh:
            try:
                created_at = datetime.fromisoformat(str(cached.get('created_at')))
                fresh_cached = datetime.utcnow() - created_at <= timedelta(seconds=ttl_seconds)
            except Exception:
                fresh_cached = False
        if fresh_cached and isinstance(cached, dict):
            llm_bundle = dict(cached.get('payload') or llm_bundle)
            llm_bundle['from_cache'] = True
            llm_bundle['cache_ttl_seconds'] = ttl_seconds
        else:
            effective_llm_cfg = {
                **llm_cfg,
                'timeout_seconds': int(llm_cfg.get('timeout_seconds', settings.llm_preview_timeout_seconds)),
                'max_retries': int(llm_cfg.get('max_retries', settings.llm_preview_max_retries)),
                'max_unknown_samples': int(llm_cfg.get('max_unknown_samples', settings.llm_preview_max_unknown_samples)),
                'max_feedback_samples': int(llm_cfg.get('max_feedback_samples', settings.llm_preview_max_feedback_samples)),
                'max_parser_snippets': int(llm_cfg.get('max_parser_snippets', settings.llm_preview_max_parser_snippets)),
            }
            llm_bundle = build_llm_rule_suggestions(
                parser_rules=parser_rules,
                unknown_suggestions=llm_source_unknown_suggestions,
                feedback_suggestions=feedback_suggestions,
                llm_config=effective_llm_cfg,
            )
            llm_bundle['from_cache'] = False
            llm_bundle['cache_ttl_seconds'] = ttl_seconds
            llm_bundle['selected_signatures'] = selected_signature_list
            llm_bundle['selected_unknown_cluster_count'] = len(llm_source_unknown_suggestions)
            cache_store[cache_key] = {'created_at': datetime.utcnow().isoformat(), 'payload': llm_bundle}
            _save_rule_preview_cache(cache_store)

    llm_result = llm_bundle.get('result', {}) if llm_bundle else {}
    llm_new = _apply_rule_review_status(llm_result.get('new_rule_suggestions', []) or [])
    llm_fix = _apply_rule_review_status(llm_result.get('rule_fix_suggestions', []) or [])
    llm_patterns = _apply_rule_review_status(llm_result.get('high_frequency_misclassified_patterns', []) or [])

    return {
        'summary': {
            'unknown_clusters_total': len(unknown_clusters),
            'feedback_records_total': len(feedback_rows),
            'new_rule_suggestions': len(unknown_suggestions),
            'rule_fix_suggestions': len(feedback_suggestions),
            'high_frequency_misclassified_patterns': len(problematic_rules),
        },
        'selected_signatures': selected_signature_list,
        'new_rule_suggestions': unknown_suggestions,
        'rule_fix_suggestions': feedback_suggestions,
        'high_frequency_misclassified_patterns': problematic_rules,
        'parser_rules_yaml_fragment': yaml_fragment,
        'review_required': True,
        'llm_assisted': {
            'switch_enabled': bool(suggestion_cfg.get('allow_llm_assisted_suggestions', True)),
            'requested': bool(use_llm),
            'used': bool(llm_bundle.get('used')),
            'fallback_to_local': bool(llm_bundle.get('fallback_to_local')),
            'from_cache': bool(llm_bundle.get('from_cache')),
            'cache_ttl_seconds': llm_bundle.get('cache_ttl_seconds'),
            'timeout_seconds': llm_cfg.get('timeout_seconds', settings.llm_preview_timeout_seconds),
            'max_retries': llm_cfg.get('max_retries', settings.llm_preview_max_retries),
            'max_unknown_samples': llm_cfg.get('max_unknown_samples', settings.llm_preview_max_unknown_samples),
            'max_feedback_samples': llm_cfg.get('max_feedback_samples', settings.llm_preview_max_feedback_samples),
            'max_parser_snippets': llm_cfg.get('max_parser_snippets', settings.llm_preview_max_parser_snippets),
            'selected_signatures': selected_signature_list,
            'selected_unknown_cluster_count': llm_bundle.get('selected_unknown_cluster_count', len(llm_source_unknown_suggestions)),
            'request_payload': llm_bundle.get('request_payload'),
            'response_payload': llm_bundle.get('response_payload'),
            'result': {
                'new_rule_suggestions': llm_new,
                'rule_fix_suggestions': llm_fix,
                'high_frequency_misclassified_patterns': llm_patterns,
                'parser_rules_yaml_fragment': llm_result.get('parser_rules_yaml_fragment', {'custom_candidates': [], 'feedback_adjustments': []}),
                'review_required': True,
            },
        },
    }


@router.post('/active-learning/rule-suggestions/{suggestion_id}/review')
def review_rule_suggestion(suggestion_id: str, payload: dict):
    review_status = str(payload.get('review_status') or '').strip()
    if not review_status:
        raise HTTPException(status_code=400, detail='缺少 review_status')
    item = _update_rule_review_status(suggestion_id, review_status, reviewer=payload.get('reviewer'), notes=payload.get('notes'))
    return {'status': 'ok', 'item': item}


@router.get('/active-learning/rule-suggestions/reviews')
def active_learning_rule_suggestion_reviews(limit: int = Query(default=200, ge=1, le=1000)):
    rows = list(_load_rule_reviews().values())
    rows.sort(key=lambda x: str((x.get('review_history') or [{}])[-1].get('reviewed_at', '')), reverse=True)
    return {'items': rows[:limit], 'total': len(rows)}


@router.get('/active-learning/rule-suggestions/files')
def active_learning_rule_suggestion_files(limit: int = Query(default=50, ge=1, le=200)):
    settings = get_settings()
    parser_rules = ConfigService().get_all().get('parser_rules', {})
    active_learning_cfg = (parser_rules.get('active_learning') or {})
    out_dir = Path(active_learning_cfg.get('suggestion_generation', {}).get('write_suggestions_to', Path(settings.data_dir) / 'active_learning' / 'rule_suggestions'))
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []
    for p in sorted(out_dir.glob('*.yaml'), key=lambda x: x.stat().st_mtime, reverse=True):
        files.append({
            'filename': p.name,
            'size_bytes': p.stat().st_size,
            'modified_at': _dt_text(None if not p.exists() else __import__('datetime').datetime.fromtimestamp(p.stat().st_mtime)),
        })
    return {'items': files[:limit], 'total': len(files)}


@router.get('/active-learning/rule-suggestions/file')
def active_learning_rule_suggestion_file(filename: str):
    settings = get_settings()
    parser_rules = ConfigService().get_all().get('parser_rules', {})
    active_learning_cfg = (parser_rules.get('active_learning') or {})
    out_dir = Path(active_learning_cfg.get('suggestion_generation', {}).get('write_suggestions_to', Path(settings.data_dir) / 'active_learning' / 'rule_suggestions'))
    path = (out_dir / filename).resolve()
    if out_dir.resolve() not in path.parents and path != out_dir.resolve():
        raise HTTPException(status_code=400, detail='非法文件名')
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail='建议文件不存在')
    return {'filename': path.name, 'content': path.read_text(encoding='utf-8')}

@router.get('/solution-repository/config')
def solution_repository_config(db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    catalog = SolutionCatalogService(db)
    repo = ConfigService().get_all().get('solution_repository', {})
    return {
        'module_tree': repo.get('module_tree', []),
        'module_prefixes': repo.get('module_prefixes', {}),
        'modules': catalog.list_modules(active_only=True),
        'task_clusters': catalog.list_task_clusters(include_pending=bool(current_user.get("is_reviewer") or current_user.get("is_admin"))),
        'fts_enabled': SolutionRepositoryService(db).fts_enabled(),
        'analysis_depths': AnalysisDepthManager().list_strategies(),
    }


@router.get('/solution-repository/records')
def list_solution_records(
    module: str | None = None,
    submodule: str | None = None,
    error_code: str | None = None,
    error_name: str | None = None,
    message: str | None = None,
    message_keyword: str | None = None,
    normalized_signature: str | None = None,
    trigger_scenario: str | None = None,
    task_cluster: str | None = None,
    submitter: str | None = None,
    reusable: bool | None = None,
    review_status: str | None = None,
    search: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
    updated_from: str | None = None,
    updated_to: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    items = SolutionRepositoryService(db).list_records(
        module=module,
        submodule=submodule,
        error_code=error_code,
        error_name=error_name,
        message=message,
        message_keyword=message_keyword,
        normalized_signature=normalized_signature,
        trigger_scenario=trigger_scenario,
        task_cluster=task_cluster,
        submitter=submitter,
        reusable=reusable,
        review_status=review_status,
        search=search,
        created_from=created_from,
        created_to=created_to,
        updated_from=updated_from,
        updated_to=updated_to,
        viewer_username=str(current_user.get("username") or ""),
        viewer_is_reviewer=bool(current_user.get("is_reviewer") or current_user.get("is_admin")),
        limit=limit,
    )
    return {'items': items, 'total': len(items)}


@router.post('/solution-repository/records')
def create_solution_record(payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_reviewer_user)):
    try:
        item = SolutionRepositoryService(db).create_record(
            {**payload, 'submitter': payload.get('submitter') or current_user.get('username'), 'review_status': 'approved'},
            actor=str(current_user.get("username") or "reviewer"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'ok', 'item': item}


@router.put('/solution-repository/records/{record_id}')
def update_solution_record(record_id: int, payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_reviewer_user)):
    try:
        item = SolutionRepositoryService(db).update_record(record_id, payload, actor=str(current_user.get("username") or "reviewer"))
    except KeyError:
        raise HTTPException(status_code=404, detail='solution record not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'ok', 'item': item}


@router.get('/solution-reviews')
def list_solution_reviews(status: str | None = None, limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    items = SolutionReviewService(db).list_reviews(
        status=status,
        limit=limit,
        viewer_username=str(current_user.get("username") or ""),
        viewer_is_reviewer=bool(current_user.get("is_reviewer") or current_user.get("is_admin")),
    )
    return {'items': items, 'total': len(items)}


@router.post('/solution-reviews')
def create_solution_review(payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    item = SolutionReviewService(db).submit_for_review(
        {**payload, 'submitter': payload.get('submitter') or current_user.get('username'), 'created_by': current_user.get('username')},
        attachments=payload.get('attachments') or [],
    )
    return {'status': 'ok', 'item': item}


@router.post('/solution-reviews/{review_id}/manual-review')
def manual_solution_review(review_id: int, payload: dict, db: Session = Depends(get_db), current_user: dict = Depends(require_reviewer_user)):
    review_status = str(payload.get('review_status') or '').strip()
    if not review_status:
        raise HTTPException(status_code=400, detail='missing review_status')
    try:
        item = SolutionReviewService(db).manually_review(
            review_id,
            review_status=review_status,
            reviewer=payload.get('reviewer') or current_user.get('username'),
            notes=payload.get('notes'),
        )
    except KeyError:
        raise HTTPException(status_code=404, detail='review record not found')
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {'status': 'ok', 'item': item}


@router.get('/solution-repository/export')
def export_solution_repository(format: str = Query(default='json'), db: Session = Depends(get_db), current_user: dict = Depends(get_current_user)):
    path = ExportService(db).export_solution_repository(export_format=format)
    return FileResponse(path=path, filename=Path(path).name)


@router.get('/tasks/{task_uuid}/export/events')
def export_events(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_events_csv(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name)


@router.get('/tasks/{task_uuid}/export/errors')
def export_errors(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_error_report_csv(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name)


@router.get('/tasks/{task_uuid}/export/parameters')
def export_parameters(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_parameter_results_csv(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name)


@router.get('/tasks/{task_uuid}/export/report.json')
def export_report_json(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_json_report(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name)


@router.get('/tasks/{task_uuid}/export/report.html')
def export_report_html(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_html_report(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name, media_type='text/html')


@router.get('/tasks/{task_uuid}/export/report.xlsx')
def export_report_xlsx(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_excel_report(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name)


@router.get('/tasks/{task_uuid}/export/report.pdf')
def export_report_pdf(task_uuid: str, db: Session = Depends(get_db)):
    query = QueryService(db)
    task = query.get_task_or_raise(task_uuid)
    path = ExportService(db).export_pdf_report(task.id, task_uuid)
    return FileResponse(path=path, filename=Path(path).name)


@router.delete('/tasks/{task_uuid}')
def delete_task(task_uuid: str, db: Session = Depends(get_db)):
    repo = TaskRepository(db)
    ok = repo.delete_task_by_uuid(task_uuid)
    if not ok:
        raise HTTPException(status_code=404, detail='任务不存在')
    return {'success': True, 'task_uuid': task_uuid}
