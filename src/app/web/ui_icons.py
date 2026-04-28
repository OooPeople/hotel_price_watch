"""本機 GUI 使用的 inline SVG icon registry。"""

from __future__ import annotations


def icon_svg(name: str, *, size: int = 18) -> str:
    """渲染少量 inline SVG icon，避免為 AppShell 引入前端打包工具。"""
    common_attrs = (
        f'width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
        'stroke="currentColor" stroke-width="2" stroke-linecap="round" '
        'stroke-linejoin="round"'
    )
    paths = {
        "activity": '<path d="M22 12h-4l-3 8-6-16-3 8H2"/>',
        "alert-circle": (
            '<circle cx="12" cy="12" r="10"/>'
            '<path d="M12 8v4"/><path d="M12 16h.01"/>'
        ),
        "arrow-up-down": (
            '<path d="m21 16-4 4-4-4"/><path d="M17 20V4"/>'
            '<path d="m3 8 4-4 4 4"/><path d="M7 4v16"/>'
        ),
        "bell": (
            '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/>'
            '<path d="M13.73 21a2 2 0 0 1-3.46 0"/>'
        ),
        "calendar": (
            '<path d="M8 2v4"/><path d="M16 2v4"/>'
            '<rect width="18" height="18" x="3" y="4" rx="2"/>'
            '<path d="M3 10h18"/>'
        ),
        "check-circle": '<path d="M9 12l2 2 4-4"/><circle cx="12" cy="12" r="10"/>',
        "chevron-down": '<path d="m6 9 6 6 6-6"/>',
        "chevron-left": '<path d="m15 18-6-6 6-6"/>',
        "chevron-right": '<path d="m9 18 6-6-6-6"/>',
        "chevron-up": '<path d="m18 15-6-6-6 6"/>',
        "chrome": (
            '<circle cx="12" cy="12" r="10"/>'
            '<circle cx="12" cy="12" r="4"/>'
            '<path d="M21.17 8H12"/><path d="M3.95 6.06 8.54 14"/>'
            '<path d="M10.88 21.94 15.46 14"/>'
        ),
        "clock": '<circle cx="12" cy="12" r="10"/><path d="M12 6v6l4 2"/>',
        "home": '<path d="m3 10 9-7 9 7"/><path d="M5 10v10h14V10"/>',
        "plus-circle": '<circle cx="12" cy="12" r="10"/><path d="M12 8v8"/><path d="M8 12h8"/>',
        "trend-up": '<path d="M3 17 9 11l4 4 8-8"/><path d="M14 7h7v7"/>',
        "users": (
            '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/>'
            '<circle cx="9" cy="7" r="4"/>'
            '<path d="M22 21v-2a4 4 0 0 0-3-3.87"/>'
            '<path d="M16 3.13a4 4 0 0 1 0 7.75"/>'
        ),
    }
    return f"<svg {common_attrs}>{paths.get(name, paths['activity'])}</svg>"
