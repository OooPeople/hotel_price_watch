"""Chrome profile 啟動與 profile 檔案準備測試。"""

from __future__ import annotations

import json

import pytest

from app.infrastructure.browser.chrome_cdp_fetcher import (
    ChromeCdpHtmlFetcher,
    _build_chrome_launch_command,
    _prepare_chrome_profile,
)
from app.infrastructure.browser.chrome_profile_launcher import ChromeProfileLauncher

from .helpers import _build_ikyu_fetcher


def test_ensure_debuggable_chrome_raises_when_chrome_is_missing(monkeypatch) -> None:
    """找不到 Chrome 時，應回清楚訊息而不是靜默失敗。"""
    fetcher = ChromeCdpHtmlFetcher()

    monkeypatch.setattr(ChromeProfileLauncher, "is_cdp_ready", lambda self: False)
    monkeypatch.setattr(ChromeProfileLauncher, "find_chrome_path", lambda self: None)

    with pytest.raises(ValueError, match="找不到可用的 Chrome"):
        fetcher._ensure_debuggable_chrome()

def test_build_chrome_launch_command_contains_hardening_flags(tmp_path) -> None:
    """啟動命令應包含降低第一次啟動雜訊的核心參數。"""
    command = _build_chrome_launch_command(
        chrome_path=r"C:\Chrome\chrome.exe",
        user_data_dir=tmp_path / "profile",
        url="https://www.ikyu.com/",
    )

    assert "--remote-debugging-port=9222" in command
    assert "--no-default-browser-check" in command
    assert "--no-first-run" in command
    assert "--disable-background-networking" in command
    assert "--disable-sync" in command
    assert "--lang=zh-TW" in command

def test_prepare_chrome_profile_writes_preferences_files(tmp_path) -> None:
    """建立 profile 時應先寫出 Preferences 與 Local State。"""
    profile_dir = tmp_path / "profile"

    _prepare_chrome_profile(profile_dir)

    assert (profile_dir / "Default" / "Preferences").exists()
    assert (profile_dir / "Local State").exists()

def test_prepare_chrome_profile_preserves_existing_preferences(tmp_path) -> None:
    """已存在的專用 profile 設定不應在每次啟動時被覆寫。"""
    profile_dir = tmp_path / "profile"
    default_dir = profile_dir / "Default"
    default_dir.mkdir(parents=True)
    preferences_path = default_dir / "Preferences"
    local_state_path = profile_dir / "Local State"
    preferences_path.write_text(
        json.dumps({"profile": {"name": "custom-profile"}}),
        encoding="utf-8",
    )
    local_state_path.write_text(
        json.dumps({"browser": {"enabled_labs_experiments": ["custom@1"]}}),
        encoding="utf-8",
    )

    _prepare_chrome_profile(profile_dir)

    assert json.loads(preferences_path.read_text(encoding="utf-8")) == {
        "profile": {"name": "custom-profile"}
    }
    assert json.loads(local_state_path.read_text(encoding="utf-8")) == {
        "browser": {"enabled_labs_experiments": ["custom@1"]}
    }

def test_open_profile_window_uses_bootstrap_homepage(monkeypatch, tmp_path) -> None:
    """手動建立 session 時，應先從 `ikyu` 首頁啟動專用 Chrome。"""
    fetcher = _build_ikyu_fetcher(
        user_data_dir=tmp_path / "profile",
        launch_timeout_seconds=0.0,
    )
    launched: list[list[str]] = []

    monkeypatch.setattr(ChromeProfileLauncher, "is_cdp_ready", lambda self: False)
    monkeypatch.setattr(
        ChromeProfileLauncher,
        "find_chrome_path",
        lambda self: r"C:\Chrome\chrome.exe",
    )
    monkeypatch.setattr(
        "subprocess.Popen",
        lambda command, stdout=None, stderr=None: launched.append(command),
    )

    with pytest.raises(ValueError, match="CDP 端點仍未就緒"):
        fetcher.open_profile_window()

    assert launched
    assert launched[0][-1] == "https://www.ikyu.com/"
