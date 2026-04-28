"""watch detail 頁面的 client-side script renderer。"""

from __future__ import annotations

from app.web.client_script_helpers import replace_script_constants
from app.web.watch_fragment_contracts import (
    WATCH_DETAIL_FRAGMENT_SECTIONS,
    WATCH_DETAIL_PAYLOAD_KEYS,
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
        const sections = __SECTIONS__;
        const payloadKeys = {
          version: __VERSION_KEY__
        };
        const fragmentsUrl = __FRAGMENTS_URL__;
        const versionUrl = __VERSION_URL__;
        const minFragmentRefreshMs = 1000;
        let currentVersion = __INITIAL_VERSION__;
        let pendingVersion = null;
        let lastFragmentRefreshAt = 0;
        let scheduledFragmentRefresh = null;
        const sectionElements = sections.map((section) => ({
          ...section,
          element: document.getElementById(section.domId)
        }));
        if (sectionElements.some((section) => !section.element)) {
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
          sectionElements.forEach((section) => {
            const html = payload[section.payloadKey];
            if (typeof html === "string") {
              section.element.innerHTML = html;
            }
          });
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
    return replace_script_constants(
        script,
        {
            "__FRAGMENTS_URL__": fragments_url,
            "__VERSION_URL__": version_url,
            "__INITIAL_VERSION__": initial_fragment_version,
            "__SECTIONS__": [
                section.to_client_config()
                for section in WATCH_DETAIL_FRAGMENT_SECTIONS
            ],
            "__VERSION_KEY__": WATCH_DETAIL_PAYLOAD_KEYS.version,
        },
    )
