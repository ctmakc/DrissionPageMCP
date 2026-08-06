from __future__ import annotations

from datetime import date, datetime, time, timezone
from typing import Any

import httpx

from google_photos_bridge.models import AlbumResult, PhotoResult
from google_photos_bridge.providers.base import PhotoProvider


class ImmichProvider(PhotoProvider):
    name = "immich"

    def __init__(self, base_url: str, api_key: str, timeout: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        if not self.base_url.endswith("/api"):
            self.base_url += "/api"
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"x-api-key": api_key, "accept": "application/json"},
            timeout=timeout,
            follow_redirects=True,
        )

    async def health(self) -> dict:
        response = await self.client.get("/server/ping")
        response.raise_for_status()
        return {
            "provider": self.name,
            "ok": True,
            "base_url": self.base_url,
            "response": self._json_or_text(response),
        }

    async def search(
        self,
        query: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
    ) -> list[PhotoResult]:
        payload: dict[str, Any] = {
            "size": max(1, min(limit, 100)),
            "withExif": True,
        }
        if query.strip():
            payload["query"] = query
        if start_date:
            payload["takenAfter"] = datetime.combine(
                start_date, time.min, tzinfo=timezone.utc
            ).isoformat()
        if end_date:
            payload["takenBefore"] = datetime.combine(
                end_date, time.max, tzinfo=timezone.utc
            ).isoformat()

        endpoint = "/search/smart" if query.strip() else "/search/metadata"
        response = await self.client.post(endpoint, json=payload)
        response.raise_for_status()
        data = response.json()
        items = self._extract_asset_items(data)
        return [self._to_photo(item) for item in items[:limit]]

    async def get_info(self, photo_id: str) -> PhotoResult:
        response = await self.client.get(f"/assets/{photo_id}")
        response.raise_for_status()
        return self._to_photo(response.json())

    async def get_preview(self, photo_id: str) -> tuple[bytes, str]:
        response = await self.client.get(
            f"/assets/{photo_id}/thumbnail", params={"size": "preview"}
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "image/jpeg").split(";", 1)[0]
        return response.content, self._format_from_content_type(content_type)

    async def list_albums(self, limit: int = 50) -> list[AlbumResult]:
        response = await self.client.get("/albums")
        response.raise_for_status()
        raw = response.json()
        items = raw if isinstance(raw, list) else raw.get("items", [])
        albums: list[AlbumResult] = []
        for item in items[:limit]:
            album_id = str(item.get("id", ""))
            albums.append(
                AlbumResult(
                    id=album_id,
                    provider=self.name,
                    title=item.get("albumName") or item.get("name") or "Untitled album",
                    item_count=item.get("assetCount"),
                    product_url=f"{self.base_url.removesuffix('/api')}/albums/{album_id}",
                    thumbnail_url=(
                        f"{self.base_url}/assets/{item['albumThumbnailAssetId']}/thumbnail?size=thumbnail"
                        if item.get("albumThumbnailAssetId")
                        else None
                    ),
                )
            )
        return albums

    @staticmethod
    def _extract_asset_items(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return data
        assets = data.get("assets", data) if isinstance(data, dict) else {}
        if isinstance(assets, list):
            return assets
        if isinstance(assets, dict):
            for key in ("items", "assets", "results"):
                value = assets.get(key)
                if isinstance(value, list):
                    return value
        return []

    def _to_photo(self, item: dict[str, Any]) -> PhotoResult:
        exif = item.get("exifInfo") or {}
        people = [
            person["name"]
            for person in item.get("people") or []
            if person.get("name")
        ]
        photo_id = str(item.get("id", ""))
        return PhotoResult(
            id=photo_id,
            provider=self.name,
            title=item.get("originalFileName") or item.get("description"),
            taken_at=self._parse_dt(
                item.get("fileCreatedAt")
                or item.get("localDateTime")
                or item.get("createdAt")
            ),
            mime_type=item.get("originalMimeType") or item.get("mimeType"),
            product_url=f"{self.base_url.removesuffix('/api')}/photos/{photo_id}",
            thumbnail_url=f"{self.base_url}/assets/{photo_id}/thumbnail?size=preview",
            width=item.get("width") or exif.get("exifImageWidth"),
            height=item.get("height") or exif.get("exifImageHeight"),
            city=exif.get("city"),
            country=exif.get("country"),
            people=people,
            metadata={
                "type": item.get("type"),
                "is_favorite": item.get("isFavorite"),
                "is_archived": item.get("isArchived"),
                "camera_make": exif.get("make"),
                "camera_model": exif.get("model"),
                "latitude": exif.get("latitude"),
                "longitude": exif.get("longitude"),
                "description": exif.get("description") or item.get("description"),
            },
        )

    @staticmethod
    def _parse_dt(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    @staticmethod
    def _json_or_text(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError:
            return response.text

    @staticmethod
    def _format_from_content_type(content_type: str) -> str:
        return {
            "image/jpeg": "jpeg",
            "image/jpg": "jpeg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }.get(content_type.lower(), "jpeg")
