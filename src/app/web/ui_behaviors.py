"""跨頁共用的 client-side behavior script renderer。"""

from __future__ import annotations

import json


def render_app_shell_script() -> str:
    """渲染 AppShell 側邊選單收合腳本，並記住使用者偏好。"""
    return """
    <script>
      (() => {
        const shell = document.querySelector(".app-shell");
        const toggle = document.getElementById("sidebar-toggle");
        if (!shell || !toggle) {
          return;
        }

        const storageKey = "hotelPriceWatch.sidebarCollapsed";
        const applyCollapsedState = (collapsed) => {
          const expandedIcon = toggle.querySelector("[data-sidebar-expanded-icon]");
          const collapsedIcon = toggle.querySelector("[data-sidebar-collapsed-icon]");
          shell.classList.toggle("sidebar-collapsed", collapsed);
          if (expandedIcon && collapsedIcon) {
            expandedIcon.style.display = collapsed ? "none" : "";
            collapsedIcon.style.display = collapsed ? "" : "none";
          }
          toggle.setAttribute("aria-label", collapsed ? "展開側邊選單" : "收合側邊選單");
          toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
        };

        applyCollapsedState(window.localStorage.getItem(storageKey) === "1");
        toggle.addEventListener("click", () => {
          const nextCollapsed = !shell.classList.contains("sidebar-collapsed");
          window.localStorage.setItem(storageKey, nextCollapsed ? "1" : "0");
          applyCollapsedState(nextCollapsed);
        });
      })();
    </script>
    """


def render_unsaved_changes_script(
    *,
    form_id: str,
    indicator_id: str = "unsaved-changes-indicator",
) -> str:
    """渲染表單異動追蹤腳本，提供提示與離頁前防呆。"""
    script = """
    <script>
      (() => {
        const form = document.getElementById(__FORM_ID__);
        const indicator = document.getElementById(__INDICATOR_ID__);
        if (!form || !indicator) {
          return;
        }

        let hasUnsavedChanges = false;

        const markUnsaved = () => {
          hasUnsavedChanges = true;
          indicator.style.display = "inline-block";
        };

        form.addEventListener("input", markUnsaved);
        form.addEventListener("change", markUnsaved);
        form.addEventListener("submit", () => {
          hasUnsavedChanges = false;
        });

        window.addEventListener("beforeunload", (event) => {
          if (!hasUnsavedChanges) {
            return;
          }
          event.preventDefault();
          event.returnValue = "";
        });
      })();
    </script>
    """
    return _replace_script_constants(
        script,
        {
            "__FORM_ID__": form_id,
            "__INDICATOR_ID__": indicator_id,
        },
    )


def render_select_visibility_script(
    *,
    select_id: str,
    wrapper_id: str,
    hidden_value: str,
    hidden_display: str = "none",
    visible_display: str = "grid",
) -> str:
    """渲染 select 控制目標區塊顯示 / 隱藏的共用腳本。"""
    script = """
    <script>
      (() => {
        const select = document.getElementById(__SELECT_ID__);
        const wrapper = document.getElementById(__WRAPPER_ID__);
        if (!select || !wrapper) {
          return;
        }

        const syncVisibility = () => {
          wrapper.style.display =
            select.value === __HIDDEN_VALUE__ ? __HIDDEN_DISPLAY__ : __VISIBLE_DISPLAY__;
        };

        syncVisibility();
        select.addEventListener("change", syncVisibility);
      })();
    </script>
    """
    return _replace_script_constants(
        script,
        {
            "__SELECT_ID__": select_id,
            "__WRAPPER_ID__": wrapper_id,
            "__HIDDEN_VALUE__": hidden_value,
            "__HIDDEN_DISPLAY__": hidden_display,
            "__VISIBLE_DISPLAY__": visible_display,
        },
    )


def render_checkbox_visibility_script(*, checkbox_id: str, wrapper_id: str) -> str:
    """渲染 checkbox 控制目標區塊顯示 / 隱藏的共用腳本。"""
    script = """
    <script>
      (() => {
        const checkbox = document.getElementById(__CHECKBOX_ID__);
        const wrapper = document.getElementById(__WRAPPER_ID__);
        if (!checkbox || !wrapper) {
          return;
        }

        const syncVisibility = () => {
          wrapper.style.display = checkbox.checked ? "grid" : "none";
        };

        syncVisibility();
        checkbox.addEventListener("change", syncVisibility);
      })();
    </script>
    """
    return _replace_script_constants(
        script,
        {
            "__CHECKBOX_ID__": checkbox_id,
            "__WRAPPER_ID__": wrapper_id,
        },
    )


def render_exclusive_checkbox_pair_script(
    *,
    first_checkbox_id: str,
    second_checkbox_id: str,
) -> str:
    """渲染兩個 checkbox 互斥且至少保留一個勾選的共用腳本。"""
    script = """
    <script>
      (() => {
        const first = document.getElementById(__FIRST_CHECKBOX_ID__);
        const second = document.getElementById(__SECOND_CHECKBOX_ID__);
        if (!first || !second) {
          return;
        }

        const bindExclusivePair = (changed, other) => {
          changed.addEventListener("change", () => {
            if (changed.checked) {
              other.checked = false;
              return;
            }
            other.checked = true;
          });
        };

        bindExclusivePair(first, second);
        bindExclusivePair(second, first);
      })();
    </script>
    """
    return _replace_script_constants(
        script,
        {
            "__FIRST_CHECKBOX_ID__": first_checkbox_id,
            "__SECOND_CHECKBOX_ID__": second_checkbox_id,
        },
    )


def _replace_script_constants(script: str, replacements: dict[str, object]) -> str:
    """把 Python 字串常數安全注入 inline script。"""
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, json.dumps(value))
    return script
