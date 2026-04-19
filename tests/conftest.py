"""pytest 測試環境的 Windows 暫存目錄修補。"""

from __future__ import annotations

import os

_ORIGINAL_OS_MKDIR = os.mkdir


def _patched_os_mkdir(
    path: str | bytes | os.PathLike[str] | os.PathLike[bytes],
    mode: int = 0o777,
    *,
    dir_fd: int | None = None,
) -> None:
    """避開 Windows 上 `mode=0o700` 會建立出不可讀目錄的行為。"""
    actual_mode = 0o777 if mode == 0o700 else mode
    if dir_fd is None:
        _ORIGINAL_OS_MKDIR(path, actual_mode)
        return
    _ORIGINAL_OS_MKDIR(path, actual_mode, dir_fd=dir_fd)


if os.name == "nt":
    os.mkdir = _patched_os_mkdir
