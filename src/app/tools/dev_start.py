"""整合專用 Chrome 檢查與 GUI 啟動的一鍵入口。"""

from __future__ import annotations

import json
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen
from uuid import uuid4

import uvicorn

from app.bootstrap.site_wiring import build_default_browser_page_strategy
from app.infrastructure.browser.chrome_cdp_fetcher import ChromeCdpHtmlFetcher
from app.monitor.single_instance import (
    SingleInstanceAction,
    create_lock_record,
    decide_single_instance_startup,
    read_lock_record,
    remove_lock_record,
    write_lock_record,
)


def main() -> None:
    """先做單實例檢查與 Chrome 檢查，再啟動本機 GUI。"""
    host = os.getenv("HOTEL_PRICE_WATCH_HOST", "127.0.0.1")
    port = int(os.getenv("HOTEL_PRICE_WATCH_PORT", "8000"))
    reload_enabled = os.getenv("HOTEL_PRICE_WATCH_RELOAD", "1") != "0"
    lock_path = Path(
        os.getenv("HOTEL_PRICE_WATCH_LOCK_PATH", str(Path("data") / "app_instance.lock"))
    )

    lock_record = read_lock_record(lock_path)
    port_in_use = _is_port_in_use(host=host, port=port)
    pid_exists = _pid_exists(lock_record.pid) if lock_record is not None else None
    pid_matches_app = True if lock_record is not None and pid_exists else None
    decision = decide_single_instance_startup(
        port_in_use=port_in_use,
        lock_record=lock_record,
        pid_exists=pid_exists,
        pid_matches_app=pid_matches_app,
    )

    if decision.action is SingleInstanceAction.REUSE_EXISTING:
        health_payload = _probe_existing_instance_health(host=host, port=port)
        if health_payload is None:
            raise RuntimeError(
                "偵測到既有執行個體，但無法從 /health 取得有效回應。"
                f" 請先確認 http://{host}:{port} 是否仍為可用的 hotel_price_watch 實例。"
            )
        health_instance_id = _extract_health_instance_id(health_payload)
        if lock_record is None or health_instance_id != lock_record.instance_id:
            raise RuntimeError(
                "偵測到既有執行個體，但 lock file 與 /health 回報的 instance_id 不一致。"
                " 請確認舊執行個體狀態，或先停止既有實例後再重試。"
            )
        runtime_running = _format_runtime_health_flag(
            health_payload,
            "is_running",
        )
        chrome_debuggable = _format_runtime_health_flag(
            health_payload,
            "chrome_debuggable",
        )
        print(
            "已偵測到既有執行個體，直接沿用："
            f"http://{host}:{port} "
            f"（status={health_payload.get('status', 'unknown')}；"
            f" runtime_running={runtime_running}；"
            f" chrome_debuggable={chrome_debuggable}）"
        )
        return
    if decision.action is SingleInstanceAction.ERROR_PORT_CONFLICT:
        raise RuntimeError(
            f"無法啟動新的執行個體：{decision.reason}。"
            f" 請先確認 http://{host}:{port} 是否已被其他程式占用。"
        )
    if decision.action is SingleInstanceAction.CLEAN_STALE_LOCK_AND_START:
        remove_lock_record(lock_path)

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    instance_id = f"hotel-price-watch-{uuid4().hex[:12]}"
    write_lock_record(
        lock_path,
        create_lock_record(
            pid=os.getpid(),
            started_at=datetime.now(UTC),
            instance_id=instance_id,
        ),
    )
    os.environ["HOTEL_PRICE_WATCH_INSTANCE_ID"] = instance_id

    fetcher = ChromeCdpHtmlFetcher(page_strategy=build_default_browser_page_strategy())
    if fetcher.is_debuggable_chrome_running():
        print("已偵測到可附著的專用 Chrome，直接啟動 GUI。")
    else:
        print("尚未偵測到可附著的專用 Chrome，先啟動專用 Chrome profile。")
        fetcher.open_profile_window()
        print("已啟動專用 Chrome profile，接著啟動 GUI。")

    try:
        uvicorn.run(
            "app.main:app",
            host=host,
            port=port,
            reload=reload_enabled,
        )
    finally:
        remove_lock_record(lock_path)


def _is_port_in_use(*, host: str, port: int) -> bool:
    """檢查本機 GUI port 是否已被既有程序占用。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        return sock.connect_ex((host, port)) == 0


def _pid_exists(pid: int) -> bool:
    """以最小成本檢查指定 PID 是否仍存在。"""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _probe_existing_instance_health(*, host: str, port: int) -> dict[str, object] | None:
    """探測既有實例的 `/health`，確認它仍是可用的 hotel_price_watch。"""
    try:
        with urlopen(f"http://{host}:{port}/health", timeout=1.0) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _format_runtime_health_flag(
    payload: dict[str, object],
    key: str,
) -> str:
    """把 `/health` 內的 runtime 布林欄位整理成可讀字串。"""
    runtime = payload.get("runtime")
    if not isinstance(runtime, dict):
        return "unknown"
    value = runtime.get(key)
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unknown"


def _extract_health_instance_id(payload: dict[str, object]) -> str | None:
    """從 `/health` 回應中取出目前 app instance_id。"""
    value = payload.get("instance_id")
    return value if isinstance(value, str) and value else None


if __name__ == "__main__":
    main()
