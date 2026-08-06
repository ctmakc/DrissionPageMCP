from abc import ABC, abstractmethod
from datetime import date

from google_photos_bridge.models import AlbumResult, PhotoResult


class PhotoProvider(ABC):
    name: str

    @abstractmethod
    async def health(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    async def search(
        self,
        query: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
    ) -> list[PhotoResult]:
        raise NotImplementedError

    @abstractmethod
    async def get_info(self, photo_id: str) -> PhotoResult:
        raise NotImplementedError

    @abstractmethod
    async def get_preview(self, photo_id: str) -> tuple[bytes, str]:
        """Return image bytes and an MCP-supported image format, e.g. jpeg/png/webp."""
        raise NotImplementedError

    @abstractmethod
    async def list_albums(self, limit: int = 50) -> list[AlbumResult]:
        raise NotImplementedError
