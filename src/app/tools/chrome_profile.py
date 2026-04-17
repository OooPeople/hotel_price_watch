"""手動啟動專用 Chrome profile，供 `ikyu` preview 附著使用。"""

from __future__ import annotations

import sys

from app.bootstrap.site_wiring import build_default_browser_page_strategy
from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher


def main() -> None:
    """啟動專用 Chrome profile，讓使用者先建立長期可重用的 `ikyu` session。"""
    start_url = sys.argv[1] if len(sys.argv) > 1 else None
    fetcher = ChromeCdpHtmlFetcher(page_strategy=build_default_browser_page_strategy())
    fetcher.open_profile_window(start_url=start_url)

    print("已啟動可附著的專用 Chrome profile。")
    print(f"Profile 目錄：{fetcher.user_data_dir.resolve()}")
    print(f"CDP 端點：{fetcher.cdp_endpoint}")
    print("建議先在此 Chrome 視窗內正常瀏覽 ikyu、切換語系、接受 cookie，")
    print("必要時也可先完成登入；之後再回到 GUI 進行 seed URL preview。")


if __name__ == "__main__":
    main()
