from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


ProviderName = Literal["immich", "google_web"]


class PhotoResult(BaseModel):
    id: str
    provider: ProviderName
    title: str | None = None
    taken_at: datetime | None = None
    mime_type: str | None = None
    product_url: str | None = None
    thumbnail_url: str | None = None
    width: int | None = None
    height: int | None = None
    city: str | None = None
    country: str | None = None
    people: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SearchResponse(BaseModel):
    provider: ProviderName
    query: str
    start_date: str | None = None
    end_date: str | None = None
    count: int
    results: list[PhotoResult]
    warning: str | None = None


class AlbumResult(BaseModel):
    id: str
    provider: ProviderName
    title: str
    item_count: int | None = None
    product_url: str | None = None
    thumbnail_url: str | None = None
