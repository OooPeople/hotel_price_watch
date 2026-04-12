"""Windows 本機桌面通知實作。"""

from __future__ import annotations

import subprocess
from typing import Callable

from app.notifiers.models import NotificationMessage

CommandRunner = Callable[[list[str]], None]


class DesktopNotifier:
    """用 PowerShell balloon tip 發送本機桌面通知。"""

    channel_name = "desktop"

    def __init__(self, command_runner: CommandRunner | None = None) -> None:
        self._command_runner = command_runner or _run_command

    def send(self, message: NotificationMessage) -> None:
        """把訊息轉成 PowerShell 命令並發送本機通知。"""
        self._command_runner(_build_desktop_command(message))


def _build_desktop_command(message: NotificationMessage) -> list[str]:
    """建立 PowerShell 桌面通知命令列。"""
    title = message.title.replace("'", "''")
    body = message.body.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "Add-Type -AssemblyName System.Drawing; "
        "$notify = New-Object System.Windows.Forms.NotifyIcon; "
        "$notify.Icon = [System.Drawing.SystemIcons]::Information; "
        f"$notify.BalloonTipTitle = '{title}'; "
        f"$notify.BalloonTipText = '{body}'; "
        "$notify.Visible = $true; "
        "$notify.ShowBalloonTip(5000); "
        "Start-Sleep -Milliseconds 1000; "
        "$notify.Dispose();"
    )
    return [
        "powershell",
        "-NoProfile",
        "-Command",
        script,
    ]


def _run_command(command: list[str]) -> None:
    """執行實際桌面通知命令。"""
    subprocess.run(command, check=True)
