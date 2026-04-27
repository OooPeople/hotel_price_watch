"""watch list / detail 頁面共用的 client-side script renderer。"""

from __future__ import annotations

import json

from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_DOM_IDS,
    WATCH_DETAIL_PAYLOAD_KEYS,
    WATCH_LIST_DOM_IDS,
    WATCH_LIST_PAYLOAD_KEYS,
)


def render_watch_list_polling_script(initial_fragment_version: str | None = None) -> str:
    """在首頁啟用版本 polling，只在資料變更時同步 fragment。"""
    script = """
    <script>
      (() => {
        const summaryContainer = document.getElementById(__SUMMARY_DOM_ID__);
        const flashContainer = document.getElementById(__FLASH_DOM_ID__);
        const runtimeContainer = document.getElementById(__RUNTIME_DOM_ID__);
        const tableBody = document.getElementById(__WATCH_LIST_DOM_ID__);
        const payloadKeys = {
          version: __VERSION_KEY__,
          flashHtml: __FLASH_HTML_KEY__,
          summaryHtml: __SUMMARY_HTML_KEY__,
          runtimeHtml: __RUNTIME_HTML_KEY__,
          tableBodyHtml: __TABLE_BODY_HTML_KEY__
        };
        const viewModeButtons = document.querySelectorAll("[data-watch-view-mode-button]");
        if (!summaryContainer || !runtimeContainer || !tableBody) {
          return;
        }
        const storageKey = "hotelPriceWatch.watchListViewMode";
        const runtimeDockStorageKey = "hotelPriceWatch.runtimeStatusCollapsed";
        const minFragmentRefreshMs = 1000;
        let currentVersion = __INITIAL_VERSION__;
        let pendingVersion = null;
        let lastFragmentRefreshAt = 0;
        let scheduledFragmentRefresh = null;

        const applyViewMode = (mode) => {
          const safeMode = mode === "list" ? "list" : "cards";
          document.querySelectorAll("[data-watch-list-view]").forEach((element) => {
            element.style.display =
              element.dataset.watchListView === safeMode ? "" : "none";
          });
          viewModeButtons.forEach((button) => {
            button.classList.toggle(
              "is-active",
              button.dataset.watchViewModeButton === safeMode
            );
          });
        };

        const currentViewMode = () =>
          window.localStorage.getItem(storageKey) === "list" ? "list" : "cards";

        const applyWatchListPayload = (payload) => {
          if (typeof payload[payloadKeys.flashHtml] === "string" && flashContainer) {
            flashContainer.innerHTML = payload[payloadKeys.flashHtml];
          }
          summaryContainer.innerHTML = payload[payloadKeys.summaryHtml];
          runtimeContainer.innerHTML = payload[payloadKeys.runtimeHtml];
          tableBody.innerHTML = payload[payloadKeys.tableBodyHtml];
          applyViewMode(currentViewMode());
          applyRuntimeDockState();
          updateClientTimeText();
          if (typeof payload[payloadKeys.version] === "string") {
            currentVersion = payload[payloadKeys.version];
            pendingVersion = null;
          }
        };

        const applyRuntimeDockState = () => {
          const collapsed = window.localStorage.getItem(runtimeDockStorageKey) === "1";
          runtimeContainer
            .querySelectorAll("[data-runtime-status-dock]")
            .forEach((dock) => {
              dock.classList.toggle("is-collapsed", collapsed);
              const toggle = dock.querySelector("[data-runtime-status-toggle]");
              if (!toggle) {
                return;
              }
              const expandedIcon = toggle.querySelector("[data-runtime-expanded-icon]");
              const collapsedIcon = toggle.querySelector("[data-runtime-collapsed-icon]");
              if (expandedIcon && collapsedIcon) {
                expandedIcon.style.display = collapsed ? "none" : "";
                collapsedIcon.style.display = collapsed ? "" : "none";
              }
              toggle.setAttribute(
                "aria-label",
                collapsed ? "展開系統狀態" : "收合系統狀態"
              );
              toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
            });
        };

        const formatRelativeTime = (targetDate) => {
          const elapsedSeconds = Math.max(
            Math.floor((Date.now() - targetDate.getTime()) / 1000),
            0
          );
          if (elapsedSeconds < 60) {
            return "剛剛";
          }
          const elapsedMinutes = Math.floor(elapsedSeconds / 60);
          if (elapsedMinutes < 60) {
            return `${elapsedMinutes} 分鐘前`;
          }
          const elapsedHours = Math.floor(elapsedMinutes / 60);
          if (elapsedHours < 24) {
            return `${elapsedHours} 小時前`;
          }
          return `${Math.floor(elapsedHours / 24)} 天前`;
        };

        const formatCountdownTime = (targetDate) => {
          const remainingSeconds = Math.ceil(
            (targetDate.getTime() - Date.now()) / 1000
          );
          if (remainingSeconds <= 60) {
            return "預計 1 分鐘內自動重試";
          }
          return `預計 ${Math.ceil(remainingSeconds / 60)} 分鐘後自動重試`;
        };

        const updateClientTimeText = () => {
          document.querySelectorAll("[data-relative-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.relativeTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatRelativeTime(targetDate);
            }
          });
          document.querySelectorAll("[data-countdown-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.countdownTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatCountdownTime(targetDate);
            }
          });
        };

        viewModeButtons.forEach((button) => {
          button.addEventListener("click", () => {
            const mode = button.dataset.watchViewModeButton === "list" ? "list" : "cards";
            window.localStorage.setItem(storageKey, mode);
            applyViewMode(mode);
          });
        });
        runtimeContainer.addEventListener("click", (event) => {
          const toggle = event.target.closest("[data-runtime-status-toggle]");
          if (!toggle) {
            return;
          }
          const collapsed = window.localStorage.getItem(runtimeDockStorageKey) === "1";
          window.localStorage.setItem(runtimeDockStorageKey, collapsed ? "0" : "1");
          applyRuntimeDockState();
        });
        tableBody.addEventListener("submit", async (event) => {
          const form = event.target.closest("form[data-watch-list-action]");
          if (!form || event.defaultPrevented) {
            return;
          }
          event.preventDefault();
          const buttons = form.querySelectorAll("button");
          buttons.forEach((button) => {
            button.disabled = true;
          });
          try {
            const response = await fetch(form.action, {
              method: "POST",
              body: new FormData(form),
              headers: {
                "Accept": "application/json",
                "X-Requested-With": "fetch",
              },
              credentials: "same-origin",
            });
            if (!response.ok) {
              buttons.forEach((button) => {
                button.disabled = false;
              });
              return;
            }
            applyWatchListPayload(await response.json());
          } catch {
            buttons.forEach((button) => {
              button.disabled = false;
            });
          }
        });
        applyViewMode(currentViewMode());
        applyRuntimeDockState();
        updateClientTimeText();

        const refreshFragments = async () => {
          try {
            const response = await fetch("/fragments/watch-list", {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            lastFragmentRefreshAt = Date.now();
            applyWatchListPayload(await response.json());
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        const scheduleFragmentRefresh = () => {
          if (scheduledFragmentRefresh !== null) {
            return;
          }
          const elapsed = Date.now() - lastFragmentRefreshAt;
          const delay = Math.max(minFragmentRefreshMs - elapsed, 0);
          scheduledFragmentRefresh = window.setTimeout(() => {
            scheduledFragmentRefresh = null;
            refreshFragments();
          }, delay);
        };

        const checkVersion = async () => {
          try {
            const response = await fetch("/fragments/watch-list/version", {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            const payload = await response.json();
            if (typeof payload[payloadKeys.version] !== "string") {
              return;
            }
            if (currentVersion === null) {
              currentVersion = payload[payloadKeys.version];
              return;
            }
            if (payload[payloadKeys.version] !== currentVersion) {
              pendingVersion = payload[payloadKeys.version];
              scheduleFragmentRefresh();
            }
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        window.setInterval(checkVersion, 1000);
        window.setInterval(updateClientTimeText, 30000);
      })();
    </script>
    """
    return _replace_script_constants(
        script,
        {
            "__INITIAL_VERSION__": initial_fragment_version,
            "__FLASH_DOM_ID__": WATCH_LIST_DOM_IDS.flash,
            "__SUMMARY_DOM_ID__": WATCH_LIST_DOM_IDS.summary,
            "__RUNTIME_DOM_ID__": WATCH_LIST_DOM_IDS.runtime,
            "__WATCH_LIST_DOM_ID__": WATCH_LIST_DOM_IDS.watch_list,
            "__VERSION_KEY__": WATCH_LIST_PAYLOAD_KEYS.version,
            "__FLASH_HTML_KEY__": WATCH_LIST_PAYLOAD_KEYS.flash_html,
            "__SUMMARY_HTML_KEY__": WATCH_LIST_PAYLOAD_KEYS.summary_html,
            "__RUNTIME_HTML_KEY__": WATCH_LIST_PAYLOAD_KEYS.runtime_html,
            "__TABLE_BODY_HTML_KEY__": WATCH_LIST_PAYLOAD_KEYS.table_body_html,
        },
    )


def render_watch_detail_polling_script(
    watch_item_id: str,
    *,
    initial_fragment_version: str | None = None,
) -> str:
    """在 watch 詳細頁啟用版本 polling，只在資料變更時同步 fragment。"""
    fragments_url = f"/watches/{watch_item_id}/fragments"
    version_url = f"/watches/{watch_item_id}/fragments/version"
    script = """
    <script>
      (() => {
        const heroSection = document.getElementById(__HERO_DOM_ID__);
        const checkEventsSection = document.getElementById(__CHECK_EVENTS_DOM_ID__);
        const priceSummarySection = document.getElementById(__PRICE_SUMMARY_DOM_ID__);
        const priceTrendSection = document.getElementById(__PRICE_TREND_DOM_ID__);
        const runtimeStateEventsSection = document.getElementById(
          __RUNTIME_STATE_EVENTS_DOM_ID__
        );
        const debugArtifactsSection = document.getElementById(__DEBUG_ARTIFACTS_DOM_ID__);
        const payloadKeys = {
          version: __VERSION_KEY__,
          heroHtml: __HERO_HTML_KEY__,
          priceSummaryHtml: __PRICE_SUMMARY_HTML_KEY__,
          priceTrendHtml: __PRICE_TREND_HTML_KEY__,
          checkEventsHtml: __CHECK_EVENTS_HTML_KEY__,
          runtimeStateEventsHtml: __RUNTIME_STATE_EVENTS_HTML_KEY__,
          debugArtifactsHtml: __DEBUG_ARTIFACTS_HTML_KEY__
        };
        const fragmentsUrl = __FRAGMENTS_URL__;
        const versionUrl = __VERSION_URL__;
        const minFragmentRefreshMs = 1000;
        let currentVersion = __INITIAL_VERSION__;
        let pendingVersion = null;
        let lastFragmentRefreshAt = 0;
        let scheduledFragmentRefresh = null;
        if (
          !heroSection ||
          !priceSummarySection ||
          !priceTrendSection ||
          !runtimeStateEventsSection ||
          !checkEventsSection ||
          !debugArtifactsSection
        ) {
          return;
        }

        const formatRelativeTime = (targetDate) => {
          const elapsedSeconds = Math.max(
            Math.floor((Date.now() - targetDate.getTime()) / 1000),
            0
          );
          if (elapsedSeconds < 60) {
            return "剛剛";
          }
          const elapsedMinutes = Math.floor(elapsedSeconds / 60);
          if (elapsedMinutes < 60) {
            return `${elapsedMinutes} 分鐘前`;
          }
          const elapsedHours = Math.floor(elapsedMinutes / 60);
          if (elapsedHours < 24) {
            return `${elapsedHours} 小時前`;
          }
          return `${Math.floor(elapsedHours / 24)} 天前`;
        };

        const formatCountdownTime = (targetDate) => {
          const remainingSeconds = Math.ceil(
            (targetDate.getTime() - Date.now()) / 1000
          );
          if (remainingSeconds <= 60) {
            return "預計 1 分鐘內自動重試";
          }
          return `預計 ${Math.ceil(remainingSeconds / 60)} 分鐘後自動重試`;
        };

        const updateClientTimeText = () => {
          document.querySelectorAll("[data-relative-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.relativeTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatRelativeTime(targetDate);
            }
          });
          document.querySelectorAll("[data-countdown-time]").forEach((element) => {
            const targetDate = new Date(element.dataset.countdownTime);
            if (!Number.isNaN(targetDate.getTime())) {
              element.textContent = formatCountdownTime(targetDate);
            }
          });
        };

        const applyWatchDetailPayload = (payload) => {
          heroSection.innerHTML = payload[payloadKeys.heroHtml];
          priceSummarySection.innerHTML = payload[payloadKeys.priceSummaryHtml];
          priceTrendSection.innerHTML = payload[payloadKeys.priceTrendHtml];
          runtimeStateEventsSection.innerHTML = payload[payloadKeys.runtimeStateEventsHtml];
          checkEventsSection.innerHTML = payload[payloadKeys.checkEventsHtml];
          debugArtifactsSection.innerHTML = payload[payloadKeys.debugArtifactsHtml];
          updateClientTimeText();
          if (typeof payload[payloadKeys.version] === "string") {
            currentVersion = payload[payloadKeys.version];
            pendingVersion = null;
          }
        };

        const refreshFragments = async () => {
          try {
            const response = await fetch(fragmentsUrl, {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            lastFragmentRefreshAt = Date.now();
            applyWatchDetailPayload(await response.json());
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        const scheduleFragmentRefresh = () => {
          if (scheduledFragmentRefresh !== null) {
            return;
          }
          const elapsed = Date.now() - lastFragmentRefreshAt;
          const delay = Math.max(minFragmentRefreshMs - elapsed, 0);
          scheduledFragmentRefresh = window.setTimeout(() => {
            scheduledFragmentRefresh = null;
            refreshFragments();
          }, delay);
        };

        const checkVersion = async () => {
          try {
            const response = await fetch(versionUrl, {
              headers: { "X-Requested-With": "fetch" },
            });
            if (!response.ok) {
              return;
            }
            const payload = await response.json();
            if (typeof payload[payloadKeys.version] !== "string") {
              return;
            }
            if (currentVersion === null) {
              currentVersion = payload[payloadKeys.version];
              return;
            }
            if (payload[payloadKeys.version] !== currentVersion) {
              pendingVersion = payload[payloadKeys.version];
              scheduleFragmentRefresh();
            }
          } catch {
            // 保持靜默，避免本機 GUI 因暫時失敗反覆噴錯。
          }
        };

        updateClientTimeText();
        window.setInterval(checkVersion, 1000);
        window.setInterval(updateClientTimeText, 30000);
      })();
    </script>
    """
    return _replace_script_constants(
        script,
        {
            "__FRAGMENTS_URL__": fragments_url,
            "__VERSION_URL__": version_url,
            "__INITIAL_VERSION__": initial_fragment_version,
            "__HERO_DOM_ID__": WATCH_DETAIL_DOM_IDS.hero,
            "__CHECK_EVENTS_DOM_ID__": WATCH_DETAIL_DOM_IDS.check_events,
            "__PRICE_SUMMARY_DOM_ID__": WATCH_DETAIL_DOM_IDS.price_summary,
            "__PRICE_TREND_DOM_ID__": WATCH_DETAIL_DOM_IDS.price_trend,
            "__RUNTIME_STATE_EVENTS_DOM_ID__": WATCH_DETAIL_DOM_IDS.runtime_state_events,
            "__DEBUG_ARTIFACTS_DOM_ID__": WATCH_DETAIL_DOM_IDS.debug_artifacts,
            "__VERSION_KEY__": WATCH_DETAIL_PAYLOAD_KEYS.version,
            "__HERO_HTML_KEY__": WATCH_DETAIL_PAYLOAD_KEYS.hero_section_html,
            "__PRICE_SUMMARY_HTML_KEY__": (
                WATCH_DETAIL_PAYLOAD_KEYS.price_summary_section_html
            ),
            "__PRICE_TREND_HTML_KEY__": WATCH_DETAIL_PAYLOAD_KEYS.price_trend_section_html,
            "__CHECK_EVENTS_HTML_KEY__": (
                WATCH_DETAIL_PAYLOAD_KEYS.check_events_section_html
            ),
            "__RUNTIME_STATE_EVENTS_HTML_KEY__": (
                WATCH_DETAIL_PAYLOAD_KEYS.runtime_state_events_section_html
            ),
            "__DEBUG_ARTIFACTS_HTML_KEY__": (
                WATCH_DETAIL_PAYLOAD_KEYS.debug_artifacts_section_html
            ),
        },
    )


def _replace_script_constants(script: str, replacements: dict[str, object]) -> str:
    """把 Python contract 常數安全注入 inline script。"""
    for placeholder, value in replacements.items():
        script = script.replace(placeholder, json.dumps(value))
    return script
