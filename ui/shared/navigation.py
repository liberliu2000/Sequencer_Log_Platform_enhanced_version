from __future__ import annotations

PAGE_ORDER = [
    "首页 / 仪表盘",
    "历史项目中心",
    "文件上传",
    "统一事件流",
    "耗时分析",
    "事件流时间轴",
    "错误分析",
    "参数趋势分析",
    "LLM 诊断",
    "原始文件预览",
    "未知日志待标注池",
    "规则建议审核视图",
    "配置页面",
    "导出",
]

PAGE_META = {
    "首页 / 仪表盘": {"title": "首页总览", "icon": "dashboard", "description": "集中查看任务状态、问题密度、组件分布与关键处理指标。"},
    "历史项目中心": {"title": "历史项目中心", "icon": "archive", "description": "浏览已有任务记录，快速切换不同项目并回看历史分析结果。"},
    "文件上传": {"title": "文件上传", "icon": "upload", "description": "上传日志文件或压缩包，提交后台解析与聚合任务。"},
    "统一事件流": {"title": "统一事件流", "icon": "stream", "description": "按组件、级别、Cycle 和关键词检索统一归档后的事件流。"},
    "耗时分析": {"title": "耗时分析", "icon": "clock", "description": "查看 Cycle 与 Sub-step 的耗时表现，定位潜在性能瓶颈。"},
    "事件流时间轴": {"title": "事件流时间轴", "icon": "timeline", "description": "从时间维度观察各组件动作顺序与阶段重叠关系。"},
    "错误分析": {"title": "错误分析", "icon": "alert", "description": "聚焦错误簇、错误家族和组件分布，快速识别高频问题。"},
    "参数趋势分析": {"title": "参数趋势分析", "icon": "sliders", "description": "分析关键参数随时间或 Cycle 的变化趋势。"},
    "LLM 诊断": {"title": "LLM 综合诊断", "icon": "brain", "description": "结合日志、上下文、源码与历史案例生成结构化诊断结论。"},
    "原始文件预览": {"title": "原始文件预览", "icon": "file", "description": "在线查看原始日志文件内容、编码与预览片段。"},
    "未知日志待标注池": {"title": "未知日志待标注池", "icon": "spark", "description": "收集未命中 parser 或规则的日志簇，便于补充规则与标注。"},
    "规则建议审核视图": {"title": "规则建议审核", "icon": "review", "description": "集中审核规则建议与解决方案记录，完善知识沉淀流程。"},
    "配置页面": {"title": "配置页面", "icon": "settings", "description": "查看并调整系统配置、策略开关和分析参数。"},
    "导出": {"title": "导出", "icon": "export", "description": "导出任务结果、解决方案数据及相关分析产物。"},
}
