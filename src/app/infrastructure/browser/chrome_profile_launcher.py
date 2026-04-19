"""專用 Chrome profile 啟動與 CDP readiness 檢查。"""

from __future__ import annotations

import json
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ChromeProfileLauncher:
    """負責啟動可附著的專用 Chrome profile。"""

    cdp_endpoint: str
    launch_timeout_seconds: float
    chrome_candidates: tuple[str, ...]
    user_data_dir: Path
    profile_start_url: str | None

    def ensure_debuggable_chrome(self, start_url: str | None = None) -> None:
        """若 CDP 尚未可用，則啟動一個可附著的 Chrome 視窗。"""
        if self.is_cdp_ready():
            return

        chrome_path = self.find_chrome_path()
        if chrome_path is None:
            raise ValueError(
                "找不到可用的 Chrome 可執行檔；"
                "請安裝 Chrome，或手動以 remote debugging 模式啟動後再重試。"
            )

        self.user_data_dir.mkdir(parents=True, exist_ok=True)
        prepare_chrome_profile(self.user_data_dir)
        subprocess.Popen(
            build_chrome_launch_command(
                chrome_path=chrome_path,
                user_data_dir=self.user_data_dir,
                url=start_url or self.profile_start_url,
            ),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        deadline = time.monotonic() + self.launch_timeout_seconds
        while time.monotonic() < deadline:
            if self.is_cdp_ready():
                return
            time.sleep(0.5)

        raise ValueError(
            "已嘗試啟動可附著的 Chrome 視窗，但 CDP 端點仍未就緒；"
            "請確認 Chrome 未被安全軟體或系統政策攔下。"
        )

    def is_cdp_ready(self) -> bool:
        """檢查本機 CDP 端點是否已可連線。"""
        try:
            with urllib.request.urlopen(
                f"{self.cdp_endpoint}/json/version",
                timeout=2.0,
            ) as response:
                return response.status == 200
        except (urllib.error.URLError, TimeoutError, OSError):
            return False

    def find_chrome_path(self) -> str | None:
        """找出本機可用的 Chrome 可執行檔。"""
        for path in self.chrome_candidates:
            if Path(path).exists():
                return path
        return None


def build_chrome_launch_command(
    *,
    chrome_path: str,
    user_data_dir: Path,
    url: str | None,
) -> list[str]:
    """建立啟動可附著 Chrome instance 的命令列參數。"""
    return [
        chrome_path,
        "--remote-debugging-port=9222",
        f"--user-data-dir={user_data_dir.resolve()}",
        "--new-window",
        "--disable-animations",
        "--disable-background-networking",
        "--disable-component-update",
        "--disable-default-apps",
        "--disable-dev-shm-usage",
        "--disable-domain-reliability",
        "--disable-infobars",
        "--disable-logging",
        "--disable-notifications",
        "--disable-popup-blocking",
        "--disable-renderer-backgrounding",
        "--disable-sync",
        "--disable-translate",
        "--disable-features=TranslateUI",
        "--homepage=about:blank",
        "--lang=zh-TW",
        "--no-default-browser-check",
        "--no-first-run",
        "--no-pings",
        "--no-service-autorun",
        "--password-store=basic",
        url or "about:blank",
    ]


def prepare_chrome_profile(user_data_dir: Path) -> None:
    """預先寫入偏好設定，減少第一次啟動的多餘干擾。"""
    default_dir = user_data_dir / "Default"
    default_dir.mkdir(parents=True, exist_ok=True)

    preferences = {
        "credentials_enable_service": False,
        "ack_existing_ntp_extensions": False,
        "translate": {"enabled": False},
        "profile": {
            "default_content_setting_values": {
                "notifications": 2,
                "sound": 2,
            },
            "password_manager_enabled": False,
            "name": "hotel_price_watch",
        },
        "privacy_sandbox": {"first_party_sets_enabled": False},
        "safebrowsing": {"enabled": False, "enhanced": False},
        "sync": {"autofill_wallet_import_enabled_migrated": False},
        "net": {"network_prediction_options": 3},
    }
    preferences_path = default_dir / "Preferences"
    if not preferences_path.exists():
        preferences_path.write_text(
            json.dumps(preferences),
            encoding="utf-8",
        )

    local_state = {
        "performance_tuning": {"high_efficiency_mode": {"state": 1}},
        "browser": {
            "enabled_labs_experiments": [
                "history-journeys@4",
                "memory-saver-multi-state-mode@1",
                "modal-memory-saver@1",
                "read-anything@2",
            ]
        },
        "dns_over_https": {"mode": "off"},
    }
    local_state_path = user_data_dir / "Local State"
    if not local_state_path.exists():
        local_state_path.write_text(
            json.dumps(local_state),
            encoding="utf-8",
        )
