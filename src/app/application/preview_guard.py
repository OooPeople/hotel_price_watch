"""管理 GUI preview 嘗試頻率，避免短時間內反覆觸發站方風控。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from app.sites.base import LookupDiagnostic


class PreviewCooldownError(ValueError):
    """表示目前 preview 仍在冷卻中，暫時不可再次嘗試。"""

    def __init__(
        self,
        message: str,
        *,
        diagnostics: tuple[LookupDiagnostic, ...],
    ) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


@dataclass(slots=True)
class _PreviewCooldownState:
    """保存單一 site 的 preview 冷卻狀態。"""

    next_allowed_at: datetime | None = None
    cooldown_reason: str | None = None


@dataclass(slots=True)
class PreviewAttemptGuard:
    """限制 GUI preview 的嘗試頻率，降低短時間重複打站的風險。"""

    min_interval_seconds: float = 20.0
    blocked_page_cooldown_seconds: float = 1800.0
    generic_failure_cooldown_seconds: float = 120.0
    _states_by_site: dict[str, _PreviewCooldownState] = field(
        default_factory=dict,
        init=False,
    )

    def ensure_allowed(self, *, site_name: str = "ikyu", now: datetime | None = None) -> None:
        """若 preview 仍在冷卻中，直接阻止本次嘗試。"""
        current_time = now or datetime.now(UTC)
        state = self._states_by_site.get(site_name)
        if (
            state is None
            or state.next_allowed_at is None
            or current_time >= state.next_allowed_at
        ):
            return

        retry_after_seconds = max(
            0.0,
            (state.next_allowed_at - current_time).total_seconds(),
        )
        raise PreviewCooldownError(
            f"目前 {site_name} preview 仍在冷卻中；請稍後再重試，避免持續觸發站方風控。",
            diagnostics=(
                LookupDiagnostic(
                    stage="preview_rate_guard",
                    status="cooldown_active",
                    detail=state.cooldown_reason or "上一輪 preview 已進入冷卻。",
                    cooldown_seconds=retry_after_seconds,
                ),
            ),
        )

    def register_result(
        self,
        *,
        diagnostics: tuple[LookupDiagnostic, ...],
        site_name: str = "ikyu",
        now: datetime | None = None,
    ) -> None:
        """依本次 preview 的實際結果更新下一次可嘗試時間。"""
        current_time = now or datetime.now(UTC)
        cooldown_seconds, reason = self._decide_cooldown(
            diagnostics,
            site_name=site_name,
        )
        self._states_by_site[site_name] = _PreviewCooldownState(
            next_allowed_at=current_time + timedelta(seconds=cooldown_seconds),
            cooldown_reason=reason,
        )

    def reset(self, *, site_name: str | None = None) -> None:
        """清掉目前冷卻狀態，供測試或明確重置時使用。"""
        if site_name is None:
            self._states_by_site.clear()
            return
        self._states_by_site.pop(site_name, None)

    def _decide_cooldown(
        self,
        diagnostics: tuple[LookupDiagnostic, ...],
        *,
        site_name: str,
    ) -> tuple[float, str]:
        """依診斷資訊決定應套用哪一種冷卻時間。"""
        if any(
            diagnostic.status == "http_403" or "阻擋頁面" in diagnostic.detail
            for diagnostic in diagnostics
        ):
            return (
                self.blocked_page_cooldown_seconds,
                f"上一輪 {site_name} preview 已命中阻擋頁或 403；先做較長冷卻。",
            )

        if any(diagnostic.status == "failed" for diagnostic in diagnostics):
            return (
                self.generic_failure_cooldown_seconds,
                "上一輪 preview 發生失敗；先做短冷卻後再重試。",
            )

        return (
            self.min_interval_seconds,
            "上一輪 preview 剛執行完成；先做最小冷卻避免過度頻繁查詢。",
        )
