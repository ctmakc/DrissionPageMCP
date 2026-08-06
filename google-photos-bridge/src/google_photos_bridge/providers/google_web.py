from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import httpx
from dateutil.parser import parse as parse_date

from google_photos_bridge.models import AlbumResult, PhotoResult
from google_photos_bridge.providers.base import PhotoProvider


class GooglePhotosWebProvider(PhotoProvider):
    """Read-only Google Photos adapter using an authenticated Chrome session."""

    name = "google_web"
    PHOTOS_URL = "https://photos.google.com/"
    ALBUMS_URL = "https://photos.google.com/albums"

    def __init__(
        self,
        *,
        debug_port: int = 9222,
        browser_path: str | None = None,
        headless: bool = False,
        cache_dir: Path,
        scroll_rounds: int = 12,
        wait_seconds: float = 3.0,
    ) -> None:
        self.debug_port = debug_port
        self.browser_path = browser_path
        self.headless = headless
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.scroll_rounds = scroll_rounds
        self.wait_seconds = wait_seconds
        self._browser: Any = None
        self._results: dict[str, PhotoResult] = {}
        self._lock = asyncio.Lock()

    async def health(self) -> dict:
        async with self._lock:
            tab = await asyncio.to_thread(self._ensure_tab)
            logged_in = await asyncio.to_thread(self._is_logged_in, tab)
            return {
                "provider": self.name,
                "ok": logged_in,
                "url": tab.url,
                "title": tab.title,
                "debug_port": self.debug_port,
                "message": (
                    "Connected to an authenticated Google Photos session."
                    if logged_in
                    else "Chrome is reachable, but Google Photos is not authenticated."
                ),
            }

    async def search(
        self,
        query: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 20,
    ) -> list[PhotoResult]:
        limit = max(1, min(limit, 100))
        async with self._lock:
            if start_date and end_date and end_date < start_date:
                raise ValueError("end_date must not be earlier than start_date")

            if start_date and end_date and (end_date - start_date).days <= 31:
                aggregated: dict[str, PhotoResult] = {}
                current = start_date
                while current <= end_date and len(aggregated) < limit:
                    daily_query = self._join_query(query, self._date_phrase(current))
                    batch = await asyncio.to_thread(self._search_once, daily_query, limit)
                    for item in batch:
                        aggregated[item.id] = item
                        if len(aggregated) >= limit:
                            break
                    current += timedelta(days=1)
                results = list(aggregated.values())[:limit]
            else:
                effective_query = query.strip()
                if start_date and end_date:
                    effective_query = self._join_query(
                        effective_query,
                        f"{self._date_phrase(start_date)} to {self._date_phrase(end_date)}",
                    )
                elif start_date:
                    effective_query = self._join_query(effective_query, self._date_phrase(start_date))
                results = await asyncio.to_thread(self._search_once, effective_query, limit)

            self._results.update({item.id: item for item in results})
            return results

    async def get_info(self, photo_id: str) -> PhotoResult:
        item = self._results.get(photo_id)
        if not item:
            raise KeyError(
                "Unknown photo_id. Run search_photos first; Google web result IDs are session-local."
            )
        return item

    async def get_preview(self, photo_id: str) -> tuple[bytes, str]:
        item = await self.get_info(photo_id)
        async with self._lock:
            return await asyncio.to_thread(self._download_preview_sync, item)

    async def list_albums(self, limit: int = 50) -> list[AlbumResult]:
        async with self._lock:
            return await asyncio.to_thread(self._list_albums_sync, max(1, min(limit, 100)))

    def _ensure_tab(self):
        from DrissionPage import Chromium, ChromiumOptions

        if self._browser is None:
            options = ChromiumOptions()
            options.set_local_port(self.debug_port)
            if self.browser_path:
                options.set_browser_path(self.browser_path)
            if self.headless:
                options.headless(True)
            self._browser = Chromium(options)

        tab = self._browser.latest_tab
        if "photos.google.com" not in (tab.url or ""):
            tab.get(self.PHOTOS_URL)
            tab.wait(self.wait_seconds)
        return tab

    @staticmethod
    def _is_logged_in(tab) -> bool:
        url = (tab.url or "").lower()
        if "accounts.google.com" in url:
            return False
        result = tab.run_js(
            """
            const body = (document.body?.innerText || '').toLowerCase();
            const hasSearch = [...document.querySelectorAll('input')].some(el => {
              const label = `${el.getAttribute('aria-label') || ''} ${el.placeholder || ''}`.toLowerCase();
              return label.includes('search') || label.includes('поиск') || label.includes('recherche');
            });
            return hasSearch && !body.includes('sign in to google photos');
            """
        )
        return bool(result)

    def _search_once(self, query: str, limit: int) -> list[PhotoResult]:
        tab = self._ensure_tab()
        if not self._is_logged_in(tab):
            raise RuntimeError(
                "Google Photos is not signed in. Open the Chrome profile attached to the debug port "
                "and authenticate once."
            )

        input_element = self._find_search_input(tab)
        input_element.input(query, clear=True)
        from DrissionPage.common import Keys

        tab.actions.type(Keys.ENTER)
        tab.wait(self.wait_seconds)

        collected: dict[str, PhotoResult] = {}
        stagnant_rounds = 0
        previous_count = 0
        for _ in range(self.scroll_rounds):
            raw_items = tab.run_js(self._result_collector_js()) or []
            for raw in raw_items:
                item = self._raw_to_photo(raw)
                if item:
                    collected[item.id] = item
                    if len(collected) >= limit:
                        break
            if len(collected) >= limit:
                break

            if len(collected) == previous_count:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0
                previous_count = len(collected)
            if stagnant_rounds >= 3:
                break

            tab.run_js("window.scrollBy(0, Math.max(window.innerHeight * 0.85, 700));")
            tab.wait(0.8)

        return list(collected.values())[:limit]

    @staticmethod
    def _find_search_input(tab):
        selectors = [
            'css:input[aria-label*="Search"]',
            'css:input[aria-label*="search"]',
            'css:input[aria-label*="Поиск"]',
            'css:input[placeholder*="Search"]',
            'css:input[placeholder*="search"]',
            'css:input[type="text"]',
        ]
        for selector in selectors:
            element = tab.ele(selector, timeout=1)
            if element:
                return element
        raise RuntimeError("Could not locate the Google Photos search field.")

    @staticmethod
    def _result_collector_js() -> str:
        return """
        return [...document.querySelectorAll('a[href*="/photo/"]')]
          .map((a) => {
            const images = [...a.querySelectorAll('img')];
            const img = images.sort((x, y) =>
              ((y.naturalWidth || y.width || 0) * (y.naturalHeight || y.height || 0)) -
              ((x.naturalWidth || x.width || 0) * (x.naturalHeight || x.height || 0))
            )[0];
            const container = a.closest('[aria-label], [data-tooltip], [role="button"]') || a;
            const label = container.getAttribute('aria-label') ||
                          container.getAttribute('data-tooltip') ||
                          img?.alt || a.textContent || '';
            return {
              href: a.href,
              thumbnail_url: img?.currentSrc || img?.src || null,
              title: label.trim() || null,
              width: img?.naturalWidth || img?.width || null,
              height: img?.naturalHeight || img?.height || null,
            };
          })
          .filter((x) => x.href && x.thumbnail_url);
        """

    def _raw_to_photo(self, raw: dict[str, Any]) -> PhotoResult | None:
        href = raw.get("href")
        if not href:
            return None
        photo_id = hashlib.sha256(href.encode("utf-8")).hexdigest()[:24]
        title = self._clean_title(raw.get("title"))
        return PhotoResult(
            id=photo_id,
            provider=self.name,
            title=title,
            taken_at=self._extract_date(title),
            mime_type="image/jpeg",
            product_url=href,
            thumbnail_url=raw.get("thumbnail_url"),
            width=self._as_int(raw.get("width")),
            height=self._as_int(raw.get("height")),
            metadata={"session_local_id": True},
        )

    def _download_preview_sync(self, item: PhotoResult) -> tuple[bytes, str]:
        candidate_urls = [item.thumbnail_url]
        tab = self._ensure_tab()
        if item.product_url:
            tab.get(item.product_url)
            tab.wait(self.wait_seconds)
            largest = tab.run_js(
                """
                const imgs = [...document.querySelectorAll('img')].filter(i => i.currentSrc || i.src);
                imgs.sort((a,b) =>
                  ((b.naturalWidth||0)*(b.naturalHeight||0))-((a.naturalWidth||0)*(a.naturalHeight||0))
                );
                return imgs[0]?.currentSrc || imgs[0]?.src || null;
                """
            )
            if largest:
                candidate_urls.insert(0, largest)

        headers = {"User-Agent": "Mozilla/5.0", "Referer": "https://photos.google.com/"}
        with httpx.Client(timeout=30, follow_redirects=True, headers=headers) as client:
            for url in candidate_urls:
                if not url:
                    continue
                response = client.get(url)
                content_type = response.headers.get("content-type", "")
                if response.is_success and content_type.startswith("image/"):
                    return response.content, self._format_from_content_type(content_type)
        raise RuntimeError("Could not retrieve the selected Google Photos preview image.")

    def _list_albums_sync(self, limit: int) -> list[AlbumResult]:
        tab = self._ensure_tab()
        tab.get(self.ALBUMS_URL)
        tab.wait(self.wait_seconds)
        raw = tab.run_js(
            """
            return [...document.querySelectorAll('a[href*="/album/"]')].map((a) => {
              const img = a.querySelector('img');
              const title = a.getAttribute('aria-label') || img?.alt || a.textContent || '';
              return {href: a.href, title: title.trim(), thumbnail_url: img?.currentSrc || img?.src || null};
            }).filter(x => x.href && x.title);
            """
        ) or []

        albums: dict[str, AlbumResult] = {}
        for item in raw:
            href = item.get("href")
            if not href:
                continue
            album_id = hashlib.sha256(href.encode("utf-8")).hexdigest()[:24]
            albums[album_id] = AlbumResult(
                id=album_id,
                provider=self.name,
                title=item.get("title") or "Untitled album",
                product_url=href,
                thumbnail_url=item.get("thumbnail_url"),
            )
            if len(albums) >= limit:
                break
        return list(albums.values())

    @staticmethod
    def _join_query(*parts: str) -> str:
        return " ".join(part.strip() for part in parts if part and part.strip()).strip()

    @staticmethod
    def _date_phrase(value: date) -> str:
        return value.strftime("%B %d %Y")

    @staticmethod
    def _clean_title(value: str | None) -> str | None:
        if not value:
            return None
        value = re.sub(r"\s+", " ", value).strip()
        return value[:500] or None

    @staticmethod
    def _extract_date(value: str | None):
        if not value:
            return None
        try:
            parsed = parse_date(value, fuzzy=True)
            if parsed.year < 1990 or parsed.year > 2100:
                return None
            return parsed
        except (ValueError, OverflowError):
            return None

    @staticmethod
    def _as_int(value: Any) -> int | None:
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _format_from_content_type(content_type: str) -> str:
        media_type = content_type.split(";", 1)[0].lower()
        return {
            "image/jpeg": "jpeg",
            "image/jpg": "jpeg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }.get(media_type, "jpeg")
