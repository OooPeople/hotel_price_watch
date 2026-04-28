from datetime import date

from app.application.watch_creation_cache import WatchCreationPreviewCache
from app.application.watch_editor import WatchCreationPreview
from app.domain.value_objects import SearchDraft
from app.sites.base import CandidateBundle


def test_watch_creation_preview_cache_evicts_oldest_entry() -> None:
    """preview cache 超過容量時應移除最舊項目，避免無界成長。"""
    cache = WatchCreationPreviewCache(max_size=1)
    first_key = cache.store(_build_preview("https://example.test/first"))
    second_preview = _build_preview("https://example.test/second")
    second_key = cache.store(second_preview)

    assert cache.get(first_key) is None
    assert cache.get(second_key) == second_preview


def test_watch_creation_preview_cache_can_discard_entry() -> None:
    """建立完成後可移除已使用的 preview cache。"""
    cache = WatchCreationPreviewCache()
    cache_key = cache.store(_build_preview("https://example.test/watch"))

    cache.discard(cache_key)

    assert cache.get(cache_key) is None


def _build_preview(seed_url: str) -> WatchCreationPreview:
    """建立 cache 測試用的最小 preview。"""
    return WatchCreationPreview(
        draft=SearchDraft(
            seed_url=seed_url,
            hotel_id="hotel-1",
            check_in_date=date(2026, 5, 1),
            check_out_date=date(2026, 5, 2),
            people_count=2,
            room_count=1,
        ),
        candidate_bundle=CandidateBundle(
            hotel_id="hotel-1",
            hotel_name="Hotel",
            canonical_url=seed_url,
            candidates=(),
        ),
        preselected_room_id=None,
        preselected_plan_id=None,
        preselected_still_valid=False,
    )
