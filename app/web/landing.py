from __future__ import annotations

import json
from html import escape

from app.core.settings import Settings


NAV_ITEMS = [
    ("home", "首页 / 仪表盘"),
    ("history", "历史项目中心"),
    ("upload", "文件上传"),
    ("events", "统一事件流"),
    ("timing", "耗时分析"),
    ("timeline", "事件流时间轴"),
    ("errors", "错误分析"),
    ("parameters", "参数趋势分析"),
    ("diagnosis", "LLM 诊断"),
    ("files", "原始文件预览"),
    ("unknown", "未知日志待标注池"),
    ("rules", "规则建议审核"),
    ("config", "配置页面"),
    ("solutions", "方案库"),
    ("exports", "导出"),
    ("admin", "用户管理"),
]


def _render_nav() -> str:
    buttons = []
    for index, (key, label) in enumerate(NAV_ITEMS):
        active = "true" if index == 0 else "false"
        buttons.append(
            f'<button class="nav-button" data-page="{escape(key)}" data-active="{active}" type="button">{escape(label)}</button>'
        )
    return "\n".join(buttons)


def render_root_console(settings: Settings) -> str:
    config_json = json.dumps(
        {
            "appName": settings.app_name,
            "apiPrefix": settings.api_prefix,
            "docsUrl": "/docs",
            "healthUrl": f"{settings.api_prefix}/health",
            "environment": settings.app_env,
        },
        ensure_ascii=False,
    )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{escape(settings.app_name)}</title>
  <link rel="stylesheet" href="/web-assets/style.css" />
  <script>
    window.__APP_CONFIG__ = {config_json};
  </script>
  <script defer src="https://cdn.plot.ly/plotly-2.35.2.min.js"></script>
  <script defer src="/web-assets/app.js"></script>
</head>
<body>
  <div class="app-shell" data-app-root="true">
    <aside class="sidebar">
      <div class="brand-card">
        <div class="brand-mark">SLP</div>
        <div>
          <p class="brand-kicker">Web Workspace</p>
          <h1>{escape(settings.app_name)}</h1>
        </div>
      </div>

      <div class="sidebar-group">
        <label class="field-label" for="globalTaskSelect">当前任务</label>
        <select id="globalTaskSelect"></select>
        <div class="mini-actions">
          <button id="refreshGlobalTaskButton" class="ghost" type="button">刷新任务</button>
          <button id="openDocsButton" class="ghost" type="button">API Docs</button>
        </div>
      </div>

      <div class="sidebar-group">
        <label class="field-label">导航</label>
        <div class="nav-list">
          {_render_nav()}
        </div>
      </div>

      <div class="sidebar-group">
        <label class="field-label">部署状态</label>
        <div class="status-pill-grid">
          <span class="status-pill" id="healthBadge">检查中</span>
          <span class="status-pill muted" id="envBadge">{escape(settings.app_env)}</span>
        </div>
        <p class="sidebar-note" id="topStatusMessage">正在初始化网页端控制台。</p>
      </div>
    </aside>

    <main class="workspace">
      <header class="topbar">
        <div>
          <p class="topbar-kicker">Streamlit Parity Console</p>
          <h2 id="pageTitle">首页 / 仪表盘</h2>
        </div>
        <div class="topbar-actions">
          <span class="status-pill muted" id="userBadge">未登录</span>
          <button id="quickRefreshButton" class="ghost" type="button">刷新当前页</button>
        </div>
      </header>

      <section class="hero-panel">
        <div>
          <p class="hero-kicker">完整网页端</p>
          <h3>网页端与 Streamlit 使用同一套后端能力</h3>
          <p class="hero-copy">
            这个页面现在承接任务上传、分析查看、LLM 诊断、方案库、主动学习、配置维护和导出能力。
            目标是让 Vercel 上的网页端与本地 Streamlit 保持功能一致。
          </p>
        </div>
        <div class="hero-metrics">
          <div class="metric-card">
            <span class="metric-label">运行环境</span>
            <span class="metric-value" id="heroEnvironment">{escape(settings.app_env)}</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">当前任务</span>
            <span class="metric-value" id="heroTask">未选择</span>
          </div>
          <div class="metric-card">
            <span class="metric-label">当前用户</span>
            <span class="metric-value" id="heroUser">Guest</span>
          </div>
        </div>
      </section>

      <section class="panel auth-panel">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">账户</p>
            <h3>登录、注册与密码管理</h3>
          </div>
        </div>
        <div class="auth-grid">
          <div class="subpanel">
            <h4>注册账号</h4>
            <form id="registerStartForm" class="form-grid">
              <label>用户名<input id="registerUsername" /></label>
              <label>邮箱<input id="registerEmail" type="email" /></label>
              <label>密码<input id="registerPassword" type="password" /></label>
              <label>确认密码<input id="registerPasswordConfirm" type="password" /></label>
              <label>注册备注（可选）<textarea id="registerNote" rows="3" placeholder="可填写部门、使用场景或补充说明"></textarea></label>
              <div class="button-row">
                <button type="submit">提交注册申请</button>
              </div>
            </form>
            <p class="inline-message">提交后会进入管理员审核队列，审核通过后即可使用该账号登录。</p>
          </div>
          <div class="subpanel">
            <h4>修改密码</h4>
            <form id="changePasswordForm" class="form-grid">
              <label>当前密码<input id="currentPassword" type="password" /></label>
              <label>新密码<input id="newPassword" type="password" /></label>
              <label>确认新密码<input id="confirmNewPassword" type="password" /></label>
              <div class="button-row">
                <button type="submit">修改密码</button>
              </div>
            </form>
          </div>
        </div>
        <p class="inline-message" id="authMessage"></p>
      </section>

      <section id="pageMount" class="page-mount"></section>
    </main>
  </div>
</body>
</html>
"""
