from __future__ import annotations

from datetime import date

from google_photos_bridge.config import Settings
from google_photos_bridge.models import AlbumResult, PhotoResult, SearchResponse
from google_photos_bridge.providers.base import PhotoProvider
from google_photos_bridge.providers.google_web import GooglePhotosWebProvider
from google_photos_bridge.providers.immich import ImmichProvider


class PhotoService:
    def __init__(self, settings: Settings, provider: PhotoProvider | None = None) -> None:
        self.settings = settings
        self.provider = provider or self._build_provider(settings)

    @staticmethod
    def _build_provider(settings: Settings) -> PhotoProvider:
        provider = settings.photo_provider
        if provider == "auto":
            provider = "immich" if settings.immich_api_key else "google_web"

        if provider == "immich":
            if not settings.immich_api_key:
                raise ValueError("IMMICH_API_KEY is required when PHOTO_PROVIDER=immich")
            return ImmichProvider(
                settings.immich_url,
                settings.immich_api_key,
                settings.immich_request_timeout,
            )

        return GooglePhotosWebProvider(
            debug_port=settings.google_photos_debug_port,
            browser_path=settings.google_photos_browser_path,
            headless=settings.google_photos_headless,
            cache_dir=settings.google_photos_cache_dir,
            scroll_rounds=settings.google_photos_scroll_rounds,
            wait_seconds=settings.google_photos_wait_seconds,
        )

    async def health(self) -> dict:
        return await self.provider.health()

    async def search(
        self,
        query: str,
        *,
        start_date: date | None,
        end_date: date | None,
        limit: int,
    ) -> SearchResponse:
        results = await self.provider.search(
            query,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        warning = None
        if self.provider.name == "google_web":
            warning = (
                "Google web result IDs are valid only for the current server session. "
                "The adapter is read-only and depends on the current Google Photos UI."
            )
        return SearchResponse(
            provider=self.provider.name,
            query=query,
            start_date=start_date.isoformat() if start_date else None,
            end_date=end_date.isoformat() if end_date else None,
            count=len(results),
            results=results,
            warning=warning,
        )

    async def get_info(self, photo_id: str) -> PhotoResult:
        return await self.provider.get_info(photo_id)

    async def get_preview(self, photo_id: str) -> tuple[bytes, str]:
        return await self.provider.get_preview(photo_id)

    async def list_albums(self, limit: int) -> list[AlbumResult]:
        return await self.provider.list_albums(limit)
