"""本機 GUI 的 AppShell 與頁面框架 renderer。"""

from __future__ import annotations

from html import escape

from app.web.ui_behaviors import render_app_shell_script
from app.web.ui_icons import icon_svg
from app.web.ui_styles import (
    APP_SHELL_STYLE,
    BODY_STYLE,
    PAGE_MAIN_STYLE,
    SIDEBAR_BRAND_STYLE,
    SIDEBAR_NAV_STYLE,
    SIDEBAR_STYLE,
    color_token,
    nav_link_style,
)


def page_layout(*, title: str, body: str) -> str:
    """輸出 GUI 共用頁面框架，集中 AppShell 與主要導覽。"""
    app_shell_html = _render_app_shell(title=title, body=body)
    return f"""
    <!doctype html>
    <html lang="zh-Hant">
      <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)}</title>
        {_global_style()}
      </head>
      <body style="{BODY_STYLE}">
        {app_shell_html}
      </body>
    </html>
    """


def _render_app_shell(*, title: str, body: str) -> str:
    """渲染全站 AppShell，讓導覽與主內容區寬度保持一致。"""
    return f"""
    <div class="app-shell" style="{APP_SHELL_STYLE}">
      <aside class="app-sidebar" style="{SIDEBAR_STYLE}">
        <button
          id="sidebar-toggle"
          class="sidebar-toggle"
          type="button"
          aria-label="收合側邊選單"
          aria-expanded="true"
        >
          <span data-sidebar-expanded-icon>{icon_svg("chevron-left", size=18)}</span>
          <span data-sidebar-collapsed-icon style="display:none;">
            {icon_svg("chevron-right", size=18)}
          </span>
        </button>
        <div class="sidebar-content" style="display:grid;gap:28px;align-content:start;">
          <a
            class="app-brand"
            href="/"
            aria-label="Hotel Price Watch"
            style="{SIDEBAR_BRAND_STYLE}"
          >
            {_brand_mark()}
            <span>IKYU 價格監視</span>
          </a>
          <nav aria-label="主要導覽" style="{SIDEBAR_NAV_STYLE}">
            {_render_nav_link(href="/", label="總覽", title=title, icon_name="home")}
            {_render_nav_link(
                href="/watches/new",
                label="新增監視",
                title=title,
                icon_name="plus-circle",
            )}
            {_render_nav_link(href="/settings", label="通知設定", title=title, icon_name="bell")}
            {_render_nav_link(
                href="/debug/captures",
                label="進階診斷",
                title=title,
                icon_name="activity",
            )}
          </nav>
        </div>
      </aside>
      <main style="{PAGE_MAIN_STYLE}">
        {body}
      </main>
    </div>
    {render_app_shell_script()}
    """


def _brand_mark() -> str:
    """渲染 AppShell 品牌圖示，避免導覽只靠文字辨識。"""
    return f"""
    <span
      aria-hidden="true"
      style="
        width:38px;height:38px;display:grid;place-items:center;border-radius:8px;
        color:#fff;background:linear-gradient(135deg,{color_token("primary")},{color_token("primary_hover")});
        box-shadow:0 10px 22px rgba(8,122,95,0.2);
      "
    >
      {icon_svg("bell", size=20)}
    </span>
    """


def _global_style() -> str:
    """輸出少量全站 CSS，補足 inline style 不易處理的 responsive 規則。"""
    border_color = color_token("border")
    return f"""
    <style>
      * {{ box-sizing: border-box; }}
      .table-scroll table {{
        min-width: 640px;
      }}
      .action-row {{
        align-items: center;
      }}
      svg {{
        max-width: 100%;
      }}
      .watch-list-view-toggle button {{
        padding: 8px 12px;
        border: 1px solid {border_color};
        border-radius: 999px;
        background: #fff;
        color: {color_token("secondary")};
        cursor: pointer;
        font-weight: 700;
      }}
      .watch-list-view-toggle button.is-active {{
        background: {color_token("primary_soft")};
        color: {color_token("primary")};
        border-color: {color_token("border_strong")};
      }}
      .app-shell {{
        --sidebar-width: 248px;
        --main-max-width: 1320px;
        --main-gutter: 28px;
        transition: padding-left 220ms ease;
      }}
      .app-shell > main {{
        transition: padding 220ms ease;
      }}
      #runtime-status-section {{
        min-height: 132px;
      }}
      .runtime-status-dock {{
        position: fixed;
        left: max(
          var(--main-gutter),
          calc(
            var(--sidebar-width) +
            ((100vw - var(--sidebar-width) - var(--main-max-width)) / 2) +
            var(--main-gutter)
          )
        );
        right: max(
          var(--main-gutter),
          calc(
            ((100vw - var(--sidebar-width) - var(--main-max-width)) / 2) +
            var(--main-gutter)
          )
        );
        bottom: 18px;
        z-index: 50;
        transition: width 220ms ease, left 220ms ease, right 220ms ease;
      }}
      .runtime-status-dock.is-collapsed {{
        left: auto;
        width: min(260px, calc(100vw - 32px));
      }}
      .runtime-status-dock.is-collapsed .runtime-status-header {{
        border-bottom: 0 !important;
        padding: 10px 12px !important;
      }}
      .runtime-status-dock.is-collapsed .runtime-status-panel {{
        display: none !important;
      }}
      .app-shell.sidebar-collapsed .runtime-status-dock.is-collapsed {{
        left: auto;
      }}
      .app-sidebar {{
        overflow: visible;
        transition:
          width 220ms ease,
          padding 220ms ease,
          background-color 220ms ease,
          border-color 220ms ease;
      }}
      .sidebar-content {{
        height: 100%;
        align-content: space-between;
        overflow-y: auto;
        overflow-x: visible;
        transition: opacity 160ms ease;
      }}
      .sidebar-toggle {{
        position: absolute;
        top: 28px;
        right: -15px;
        z-index: 80;
        width: 30px;
        height: 30px;
        display: grid;
        place-items: center;
        padding: 0;
        border: 1px solid {color_token("border_strong")};
        border-radius: 999px;
        background: {color_token("surface")};
        color: {color_token("primary")};
        box-shadow: 0 8px 18px rgba(15, 23, 42, 0.12);
        cursor: pointer;
        font-size: 20px;
        font-weight: 800;
        line-height: 1;
      }}
      .sidebar-toggle:hover {{
        background: {color_token("primary_soft")};
      }}
      .app-shell.sidebar-collapsed {{
        --sidebar-width: 40px;
        padding-left: var(--sidebar-width) !important;
      }}
      .app-shell.sidebar-collapsed .app-sidebar {{
        width: var(--sidebar-width) !important;
        padding: 0 !important;
        border-right: 1px solid {border_color} !important;
        background: transparent !important;
      }}
      .app-shell.sidebar-collapsed .sidebar-content {{
        opacity: 0;
        display: none !important;
      }}
      .app-shell.sidebar-collapsed .sidebar-toggle {{
        right: 5px;
      }}
      @media (prefers-reduced-motion: reduce) {{
        .app-shell,
        .app-shell > main,
        .app-sidebar,
        .sidebar-content,
        .runtime-status-dock {{
          transition: none !important;
        }}
      }}
      @media (max-width: 820px) {{
        .app-shell {{
          display: block !important;
          padding-left: 0 !important;
        }}
        .app-sidebar {{
          position: sticky !important;
          top: 0;
          bottom: auto !important;
          left: auto !important;
          z-index: 10;
          width: auto !important;
          border-right: none !important;
          border-bottom: 1px solid {border_color};
        }}
        .sidebar-content {{
          height: auto;
        }}
        .app-sidebar nav {{
          grid-template-columns: repeat(2, minmax(0, 1fr));
        }}
        .sidebar-toggle {{
          top: 18px;
          right: 14px;
        }}
        .app-shell.sidebar-collapsed .app-sidebar {{
          min-height: 54px;
          width: auto !important;
          border-bottom: 1px solid {border_color} !important;
          background: {color_token("surface")} !important;
        }}
        .app-shell.sidebar-collapsed .sidebar-toggle {{
          right: 14px;
        }}
        .add-watch-stepper {{
          grid-template-columns: 1fr 1fr !important;
        }}
        .add-watch-preview-layout,
        .chrome-tab-selection-layout {{
          grid-template-columns: 1fr !important;
        }}
        .add-watch-summary {{
          position: static !important;
        }}
        #runtime-status-section {{
          min-height: 112px;
        }}
        .runtime-status-dock {{
          left: 14px !important;
          right: 14px !important;
          bottom: 12px;
        }}
        .runtime-status-dock.is-collapsed {{
          left: auto !important;
          width: min(220px, calc(100vw - 28px));
        }}
        .runtime-status-panel {{
          grid-template-columns: 1fr !important;
        }}
        .runtime-status-panel > div {{
          border-right: none !important;
          border-bottom: 1px solid {border_color};
          padding: 8px 0 !important;
        }}
      }}
      @media (max-width: 640px) {{
        main {{
          padding: 20px 14px 144px !important;
        }}
        .page-header {{
          display: grid !important;
          gap: 14px !important;
        }}
        .page-header .action-row {{
          width: 100%;
        }}
        .page-header .action-row > a,
        .page-header .action-row > form,
        .page-header .action-row button {{
          width: 100%;
          text-align: center;
        }}
        .app-sidebar {{
          padding: 18px 14px !important;
        }}
        .app-sidebar nav {{
          grid-template-columns: 1fr !important;
        }}
        .watch-detail-hero {{
          display: grid !important;
        }}
        .watch-detail-hero-price {{
          min-width: 0 !important;
          text-align: left !important;
        }}
        .watch-card-header,
        .watch-card-footer {{
          display: grid !important;
        }}
        .add-watch-stepper {{
          grid-template-columns: 1fr !important;
        }}
        .chrome-tab-card {{
          grid-template-columns: 1fr !important;
        }}
      }}
    </style>
    """


def _render_nav_link(*, href: str, label: str, title: str, icon_name: str) -> str:
    """依目前頁面標題渲染 sidebar 導覽連結。"""
    active = _nav_link_is_active(label=label, title=title)
    icon_html = icon_svg(icon_name, size=19)
    return (
        f'<a href="{escape(href)}" style="{nav_link_style(active=active)}">'
        f'<span aria-hidden="true" style="display:grid;place-items:center;">{icon_html}</span>'
        f"<span>{escape(label)}</span></a>"
    )


def _nav_link_is_active(*, label: str, title: str) -> bool:
    """用頁面標題推斷目前導覽位置，避免每個 renderer 額外傳 context。"""
    if label == "總覽":
        return title.startswith("我的價格監視") or title.startswith("監視詳情")
    if label == "新增監視":
        return "新增監視" in title or "選擇 Chrome 分頁" in title
    if label == "通知設定":
        return title == "設定" or title == "通知設定"
    if label == "進階診斷":
        return "進階診斷" in title
    return False
