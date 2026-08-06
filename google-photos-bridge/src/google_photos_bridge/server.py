from __future__ import annotations

import hmac
from datetime import date
from typing import Any

import uvicorn
from mcp.server.fastmcp import FastMCP, Image
from starlette.types import ASGIApp, Receive, Scope, Send

from google_photos_bridge.config import Settings
from google_photos_bridge.service import PhotoService

settings = Settings()
service = PhotoService(settings)

mcp = FastMCP(
    "Private Photo Library",
    instructions=(
        "Read-only access to the user's private photo library. Search before requesting an image. "
        "Use dates and descriptive queries to narrow results. Never imply that Google Photos itself "
        "offers full-library API access; the active provider is either Immich or browser automation."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
async def photo_health() -> dict[str, Any]:
    """Check whether the configured photo provider is reachable and authenticated."""
    return await service.health()


@mcp.tool()
async def search_photos(
    query: str = "",
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """Search the private photo library.

    Args:
        query: Natural-language description, OCR text, place, object, event, or person.
        start_date: Optional inclusive capture date.
        end_date: Optional inclusive capture date.
        limit: Maximum number of results, from 1 to 100.
    """
    response = await service.search(
        query,
        start_date=start_date,
        end_date=end_date,
        limit=max(1, min(limit, 100)),
    )
    return response.model_dump(mode="json")


@mcp.tool()
async def get_photo_info(photo_id: str) -> dict[str, Any]:
    """Get metadata for a photo returned by search_photos."""
    result = await service.get_info(photo_id)
    return result.model_dump(mode="json")


@mcp.tool(structured_output=False)
async def get_photo_preview(photo_id: str) -> Image:
    """Return an image preview for visual analysis. Call search_photos first."""
    data, image_format = await service.get_preview(photo_id)
    return Image(data=data, format=image_format)


@mcp.tool()
async def list_photo_albums(limit: int = 50) -> list[dict[str, Any]]:
    """List photo albums available through the active provider."""
    albums = await service.list_albums(max(1, min(limit, 100)))
    return [album.model_dump(mode="json") for album in albums]


class BearerAuthMiddleware:
    def __init__(self, app: ASGIApp, token: str | None) -> None:
        self.app = app
        self.token = token

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self.token or scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        supplied = headers.get(b"authorization", b"").decode("latin-1")
        expected = f"Bearer {self.token}"
        if not hmac.compare_digest(supplied, expected):
            await send(
                {
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                }
            )
            await send(
                {
                    "type": "http.response.body",
                    "body": b'{"error":"unauthorized"}',
                }
            )
            return
        await self.app(scope, receive, send)


app = BearerAuthMiddleware(mcp.streamable_http_app(), settings.mcp_bearer_token)


def main() -> None:
    uvicorn.run(app, host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
