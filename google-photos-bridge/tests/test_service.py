from datetime import date

import pytest

from google_photos_bridge.config import Settings
from google_photos_bridge.models import AlbumResult, PhotoResult
from google_photos_bridge.providers.base import PhotoProvider
from google_photos_bridge.service import PhotoService


class FakeProvider(PhotoProvider):
    name = "immich"

    async def health(self) -> dict:
        return {"provider": self.name, "ok": True}

    async def search(self, query, *, start_date=None, end_date=None, limit=20):
        return [
            PhotoResult(
                id="photo-1",
                provider="immich",
                title=query,
                taken_at=None,
            )
        ][:limit]

    async def get_info(self, photo_id: str) -> PhotoResult:
        return PhotoResult(id=photo_id, provider="immich", title="test")

    async def get_preview(self, photo_id: str) -> tuple[bytes, str]:
        return b"image", "jpeg"

    async def list_albums(self, limit: int = 50):
        return [AlbumResult(id="album-1", provider="immich", title="Test")][:limit]


@pytest.mark.asyncio
async def test_search_response_is_structured():
    service = PhotoService(Settings(), provider=FakeProvider())
    response = await service.search(
        "canoe club",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 6),
        limit=10,
    )
    assert response.provider == "immich"
    assert response.count == 1
    assert response.results[0].title == "canoe club"


@pytest.mark.asyncio
async def test_preview_passthrough():
    service = PhotoService(Settings(), provider=FakeProvider())
    data, image_format = await service.get_preview("photo-1")
    assert data == b"image"
    assert image_format == "jpeg"
