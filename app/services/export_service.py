from __future__ import annotations

import csv
import json
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import Any
from sqlalchemy.orm import Session

from app.core.settings import get_settings
from app.services.query_service import QueryService
from app.services.solution_repository import SolutionRepositoryService

TIME_AXIS_PARAMETERS = {"temperature_rise", "temperature_drop"}
SKIP_PARAMETER_PLOTS = {"imaging_time"}


class ExportService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.query = QueryService(db)

    def export_events_csv(self, task_id: int, task_uuid: str) -> str:
        output = Path(self.settings.export_dir) / f"{task_uuid}_events.csv"
        self._write_csv_stream(output, self._iter_event_rows(task_id))
        return str(output)

    def export_error_report_csv(self, task_id: int, task_uuid: str) -> str:
        rows = self.query.get_error_clusters(task_id=task_id, limit=100000, offset=0)["items"]
        output = Path(self.settings.export_dir) / f"{task_uuid}_errors.csv"
        self._write_csv(output, rows)
        return str(output)

    def export_parameter_results_csv(self, task_id: int, task_uuid: str) -> str:
        rows = self.query.get_parameter_results(task_id)
        output = Path(self.settings.export_dir) / f"{task_uuid}_parameter_results.csv"
        self._write_csv(output, rows)
        return str(output)

    def export_parameter_series_csv(self, task_id: int, task_uuid: str, parameter_name: str, unit: str = "s") -> str:
        rows = self.query.get_parameter_series(task_id, parameter_name, unit=unit)
        output = Path(self.settings.export_dir) / f"{task_uuid}_trend_{parameter_name}_{unit}.csv"
        self._write_csv(output, rows)
        return str(output)

    def export_row_scan_metric_series_csv(self, task_id: int, task_uuid: str, unit: str = "ms") -> str:
        rows = self.query.get_row_scan_metric_stage_series(task_id, unit=unit)
        output = Path(self.settings.export_dir) / f"{task_uuid}_trend_row_scan_metric_{unit}.csv"
        self._write_csv(output, rows)
        return str(output)

    def export_json_report(self, task_id: int, task_uuid: str) -> str:
        payload = self._build_report_payload(task_id)
        output = Path(self.settings.export_dir) / f"{task_uuid}_report.json"
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return str(output)

    def export_html_report(self, task_id: int, task_uuid: str) -> str:
        payload = self._build_report_payload(task_id)
        output = Path(self.settings.export_dir) / f"{task_uuid}_report.html"
        output.write_text(self._build_html(payload, task_uuid), encoding="utf-8")
        return str(output)

    def export_excel_report(self, task_id: int, task_uuid: str) -> str:
        try:
            from openpyxl import Workbook
            from openpyxl.utils import get_column_letter
        except ModuleNotFoundError as exc:
            raise RuntimeError("导出 Excel 依赖缺失：请安装 openpyxl（python -m pip install openpyxl）") from exc
        payload = self._build_report_payload(task_id)
        output = Path(self.settings.export_dir) / f"{task_uuid}_report.xlsx"
        wb = Workbook()
        ws = wb.active
        if ws is None:
            raise RuntimeError("Excel workbook 初始化失败：未创建默认工作表")
        ws.title = "Dashboard"
        dash = payload["dashboard"]
        ws.append(["指标", "值"])
        for k, v in dash.items():
            if isinstance(v, list):
                continue
            ws.append([k, self._safe_value(v)])
        self._autosize_sheet(ws, get_column_letter)
        self._add_sheet(wb, "Events", payload["events"][:5000], get_column_letter)
        self._add_sheet(wb, "Errors", payload["errors"], get_column_letter)
        self._add_sheet(wb, "CycleSummary", payload["cycle_summary"], get_column_letter)
        self._add_sheet(wb, "Timeline", payload["timeline"][:5000], get_column_letter)
        self._add_sheet(wb, "SubstepCycle", payload["substep_cycle"], get_column_letter)
        self._add_sheet(wb, "Audit", payload["audit_logs"], get_column_letter)
        self._add_sheet(wb, "LLM", payload["llm_results"], get_column_letter)
        for name, rows in payload["parameter_series"].items():
            self._add_sheet(wb, f"trend_{name}"[:31], rows, get_column_letter)
        self._add_sheet(wb, "trend_row_scan_metric", payload["row_scan_metric_series"], get_column_letter)
        wb.save(output)
        return str(output)

    def export_pdf_report(self, task_id: int, task_uuid: str) -> str:
        try:
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.utils import simpleSplit
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.cidfonts import UnicodeCIDFont
            from reportlab.pdfgen import canvas
        except ModuleNotFoundError as exc:
            raise RuntimeError("导出 PDF 依赖缺失：请安装 reportlab（python -m pip install reportlab）") from exc
        payload = self._build_report_payload(task_id)
        output = Path(self.settings.export_dir) / f"{task_uuid}_report.pdf"
        c = canvas.Canvas(str(output), pagesize=A4)
        width, height = A4
        margin_x = 40
        y = height - 40
        title_font, body_font = self._register_pdf_fonts(pdfmetrics, UnicodeCIDFont)
        c.setTitle(f"Sequencer Log Report - {task_uuid}")
        y = self._draw_wrapped_line(c, f"测序仪日志分析报告 / Sequencer Log Report - {task_uuid}", margin_x, y, width - 2 * margin_x, simpleSplit, title_font, 14, 18)
        dash = payload["dashboard"]
        lines = ["", "一、项目概览", f"文件数: {dash.get('file_count', 0)}", f"总事件数: {dash.get('total_events', 0)}", f"总错误数: {dash.get('total_errors', 0)}", f"唯一错误数: {dash.get('unique_error_count', 0)}"]
        for line in lines:
            y = self._draw_wrapped_line(c, line, margin_x, y, width - 2 * margin_x, simpleSplit, body_font, 10, 14)
        c.save()
        return str(output)

    def export_solution_repository(self, export_format: str = "json") -> str:
        return SolutionRepositoryService(self.db).export_records(export_format=export_format)

    @staticmethod
    def _plotly():
        import plotly.express as px
        import plotly.io as pio

        return px, pio

    def _build_report_payload(self, task_id: int) -> dict:
        defs = [d for d in self.query.get_parameter_definitions() if d["parameter_name"] not in SKIP_PARAMETER_PLOTS]
        payload = {}
        jobs = {
            "dashboard": ("get_dashboard", {}),
            "events": ("list_events", {"limit": 2000, "offset": 0}),
            "errors": ("get_error_clusters", {"limit": 500, "offset": 0}),
            "cycle_summary": ("get_cycle_summaries", {"unit": "s"}),
            "timeline": ("get_movement_timeline", {"track_order": "cycle"}),
            "substep_cycle": ("get_substep_cycle_series", {"agg_mode": "mean", "unit": "s"}),
            "row_scan_metric_series": ("get_row_scan_metric_stage_series", {"unit": "s"}),
            "audit_logs": ("get_audit_logs", {}),
            "llm_results": ("get_llm_results", {}),
        }
        for key, (fn, kwargs) in jobs.items():
            val = getattr(self.query, fn)(task_id, **kwargs)
            payload[key] = val["items"] if key in {"events", "errors"} else val

        param_series = {}
        for d in defs:
            param_series[d["parameter_name"]] = self.query.get_parameter_series(task_id, d["parameter_name"], unit="s")

        payload["parameter_definitions"] = defs
        payload["parameter_series"] = param_series
        return payload

    def _iter_event_rows(self, task_id: int, page_size: int = 2000) -> Iterator[dict[str, Any]]:
        offset = 0
        while True:
            payload = self.query.list_events(task_id=task_id, limit=page_size, offset=offset)
            rows = payload.get("items") or []
            if not rows:
                break
            for row in rows:
                yield row
            if len(rows) < page_size:
                break
            offset += len(rows)

    def _build_html(self, payload: dict, task_uuid: str) -> str:
        px, pio = self._plotly()
        def section(title: str, content: str, sid: str) -> str:
            return f'<div class="section"><h2 id="{sid}">{title}</h2>{content}</div>'
        sections = []
        sections.append(section("首页", f"<h1>Sequencer Unified HTML Report</h1><p><strong>Task UUID:</strong> {task_uuid}</p><p>本报告整合：事件流、耗时分析、参数趋势分析、错误分析、事件流时间轴、Substep-Cycle 趋势。</p>", "home"))
        sections.append(section("事件流", self._table(payload["events"][:200], "事件流摘要（前 200 条）"), "events"))
        sections.append(section("耗时分析", self._plot_cycle_summary(payload["cycle_summary"]) + self._table(payload["cycle_summary"], "Cycle 总耗时"), "timing"))
        param_html = ""
        for name, rows in sorted(payload["parameter_series"].items()):
            param_html += self._plot_parameter_series(name, rows) + self._table(rows[:100], f"{name} 趋势数据摘要")
        param_html += self._plot_metric_series(payload["row_scan_metric_series"]) + self._table(payload["row_scan_metric_series"][:200], "Row Scan Metrics 趋势数据摘要")
        sections.append(section("参数趋势分析", param_html, "params"))
        sections.append(section("错误分析", self._plot_errors(payload["errors"]) + self._table(payload["errors"][:50], "错误簇 Top 50"), "errors"))
        sections.append(section("事件流时间轴", self._plot_timeline(payload["timeline"]) + self._table(payload["timeline"][:150], "时间轴摘要"), "timeline"))
        sections.append(section("Substep-Cycle 趋势", self._plot_substep_cycle(payload["substep_cycle"]) + self._table(payload["substep_cycle"][:200], "Substep-Cycle 数据摘要"), "substep"))
        toc = '<div class="section"><h2>目录</h2><ul><li><a href="#events">事件流</a></li><li><a href="#timing">耗时分析</a></li><li><a href="#params">参数趋势分析</a></li><li><a href="#errors">错误分析</a></li><li><a href="#timeline">事件流时间轴</a></li><li><a href="#substep">Substep-Cycle 趋势</a></li></ul></div>'
        body = toc + ''.join(sections)
        style = '<style>body{font-family:Arial,"Microsoft YaHei",sans-serif;margin:18px;background:#f7f9fc;color:#111827}.section{background:white;padding:16px 20px;border-radius:10px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:16px}table{border-collapse:collapse;width:100%;font-size:12px}th,td{border:1px solid #dbe3ee;padding:6px 8px;vertical-align:top}th{background:#eff6ff}h1,h2{margin:0 0 12px 0}a{color:#2563eb}</style>'
        return f'<!DOCTYPE html><html><head><meta charset="utf-8"/><title>Sequencer Report</title>{style}</head><body>{body}</body></html>'

    def _plot_cycle_summary(self, rows: list[dict]) -> str:
        px, pio = self._plotly()
        if not rows:
            return '<p>暂无 cycle summary。</p>'
        fig = px.line(rows, x='cycle_no', y='total_duration_value', color='chip_name', markers=True, title='Cycle 总耗时趋势')
        return pio.to_html(fig, include_plotlyjs='inline', full_html=False)

    def _plot_parameter_series(self, name: str, rows: list[dict]) -> str:
        px, pio = self._plotly()
        if name in SKIP_PARAMETER_PLOTS:
            return ''
        if not rows:
            return f'<p>{name}: 无数据。</p>'
        x_col = 'cycle'
        plot_rows = rows
        if rows[0].get('x_axis_type') == 'time':
            x_col = 'start_time'
            plot_rows = sorted(rows, key=lambda r: (r.get('start_time') or '', r.get('cycle') if r.get('cycle') is not None else -1))
        fig = px.line(plot_rows, x=x_col, y='duration_value', markers=True, title=f'{name} 趋势')
        thr = next((r.get('threshold_value') for r in plot_rows if r.get('threshold_value') is not None), None)
        if thr is not None:
            fig.add_hline(y=thr, line_dash='dash', line_color='red')
        exp = next((r.get('expected_value') for r in plot_rows if r.get('expected_value') is not None), None)
        if exp is not None:
            fig.add_hline(y=exp, line_dash='dot', line_color='green')
        return pio.to_html(fig, include_plotlyjs=False, full_html=False)

    def _plot_metric_series(self, rows: list[dict]) -> str:
        px, pio = self._plotly()
        if not rows:
            return '<p>暂无 row scan metrics 数据。</p>'
        fig = px.line(rows, x='cycle', y='duration_value', color='metric_stage', markers=True, title='Row Scan Metrics 各阶段趋势')
        return pio.to_html(fig, include_plotlyjs=False, full_html=False)

    def _plot_errors(self, rows: list[dict]) -> str:
        px, pio = self._plotly()
        if not rows:
            return '<p>暂无错误数据。</p>'
        color_field = 'error_family_display' if rows and 'error_family_display' in rows[0] else 'error_family'
        fig = px.bar(rows[:20], x='display_signature', y='count', color=color_field, title='错误簇 Top 20')
        fig.update_xaxes(tickangle=-20)
        return pio.to_html(fig, include_plotlyjs=False, full_html=False)

    def _plot_timeline(self, rows: list[dict]) -> str:
        px, pio = self._plotly()
        if not rows:
            return '<p>暂无时间轴数据。</p>'
        fig = px.timeline(rows, x_start='start', x_end='end', y='track', color='sub_step', hover_data=['sub_step', 'cycle_no', 'start_time_sec', 'end_time_sec', 'duration_ms', 'component', 'module', 'message'])
        fig.update_layout(height=min(max(500, 22 * len({r['track'] for r in rows}) + 180), 2400))
        return pio.to_html(fig, include_plotlyjs=False, full_html=False)

    def _plot_substep_cycle(self, rows: list[dict]) -> str:
        px, pio = self._plotly()
        if not rows:
            return '<p>暂无 Substep-Cycle 数据。</p>'
        agg = {}
        counts = {}
        for r in rows:
            s = r.get('sub_step') or '未知'
            agg[s] = agg.get(s, 0.0) + float(r.get('duration_value') or 0.0)
            counts[s] = counts.get(s, 0) + 1
        top_substeps = sorted(agg.keys(), key=lambda s: agg[s] / max(counts[s], 1), reverse=True)[:12]
        plot_rows = [r for r in rows if (r.get('sub_step') or '未知') in top_substeps]
        fig = px.line(plot_rows, x='cycle_no', y='duration_value', color='sub_step', title='Substep-Cycle 趋势（Top 12 by avg duration）')
        return pio.to_html(fig, include_plotlyjs=False, full_html=False)

    def _table(self, rows: list[dict], title: str) -> str:
        if not rows:
            return f'<h3>{title}</h3><p>无数据。</p>'
        headers = list(rows[0].keys())
        head = ''.join(f'<th>{h}</th>' for h in headers)
        body = []
        for row in rows:
            body.append('<tr>' + ''.join(f'<td>{self._safe_value(row.get(h))}</td>' for h in headers) + '</tr>')
        return f'<h3>{title}</h3><table><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table>'

    @staticmethod
    def _safe_value(value: Any) -> Any:
        if value is None:
            return ''
        if isinstance(value, (str, int, float, bool)):
            return value
        if isinstance(value, (list, tuple, dict)):
            try:
                return json.dumps(value, ensure_ascii=False, default=str)
            except Exception:
                return str(value)
        return str(value)

    @classmethod
    def _write_csv(cls, output: Path, rows: list[dict]) -> None:
        if not rows:
            output.write_text('', encoding='utf-8')
            return
        with output.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            for row in rows:
                writer.writerow({k: cls._safe_value(v) for k, v in row.items()})

    @classmethod
    def _write_csv_stream(cls, output: Path, rows: Iterable[dict[str, Any]]) -> None:
        iterator = iter(rows)
        first = next(iterator, None)
        if first is None:
            output.write_text('', encoding='utf-8')
            return
        with output.open('w', encoding='utf-8-sig', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=list(first.keys()))
            writer.writeheader()
            writer.writerow({k: cls._safe_value(v) for k, v in first.items()})
            for row in iterator:
                writer.writerow({k: cls._safe_value(v) for k, v in row.items()})

    @classmethod
    def _add_sheet(cls, wb, name: str, rows: list[dict], get_column_letter) -> None:
        ws = wb.create_sheet(title=name[:31])
        if not rows:
            ws.append(['empty'])
            return
        headers = list(rows[0].keys())
        ws.append(headers)
        for row in rows:
            ws.append([cls._safe_value(row.get(h)) for h in headers])
        cls._autosize_sheet(ws, get_column_letter)

    @staticmethod
    def _autosize_sheet(ws, get_column_letter) -> None:
        max_widths: dict[int, int] = {}
        for row in ws.iter_rows():
            for cell in row:
                value = '' if cell.value is None else str(cell.value)
                max_widths[cell.column] = max(max_widths.get(cell.column, 0), min(len(value), 80))
        for idx, width in max_widths.items():
            ws.column_dimensions[get_column_letter(idx)].width = max(12, min(width + 2, 80))

    @staticmethod
    def _register_pdf_fonts(pdfmetrics, UnicodeCIDFont) -> tuple[str, str]:
        title_font = 'Helvetica-Bold'
        body_font = 'Helvetica'
        try:
            pdfmetrics.getFont('STSong-Light')
        except KeyError:
            pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
        return 'STSong-Light', 'STSong-Light'

    @staticmethod
    def _draw_wrapped_line(c, text_line: str, x: float, y: float, max_width: float, simpleSplit, font_name: str, font_size: int, leading: int = 14) -> float:
        text_line = text_line or ''
        wrapped = simpleSplit(str(text_line), font_name, font_size, max_width)
        if not wrapped:
            wrapped = ['']
        c.setFont(font_name, font_size)
        for seg in wrapped:
            c.drawString(x, y, seg)
            y -= leading
        return y
