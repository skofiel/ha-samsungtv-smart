"""On-demand resized-thumbnail HTTP view for the folder gallery card.

A folder of full-size originals (several MB each, many of them) made the gallery
download and decode the whole set at full resolution just to show a grid. The
card now points its grid `<img>` tags at this endpoint, which returns a small
cached JPEG instead, so only kilobytes per tile travel to the browser.
"""

from __future__ import annotations

import hashlib
import logging
import os

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

THUMBNAIL_URL = "/api/samsungtv_smart/thumbnail"
_CACHE_SUBDIR = ("frame_art", ".thumb_cache")
_MIN_W = 64
_MAX_W = 1024
_DEFAULT_W = 400
# Requested widths are snapped to this step before anything is encoded or
# cached. The endpoint is unauthenticated (see the class docstring), and a
# free-running width would let any caller on the network mint 961 distinct
# cache entries per source image — each one a Pillow decode and a file
# written under <config>/www. Snapping leaves 16, and raises the hit rate
# for the grid, which asks for a handful of sizes.
_WIDTH_STEP = 64

# The cache is pruned back to these bounds after each write. Entries are
# keyed by (path, width, mtime), so editing a folder's images leaves the old
# renditions behind forever; nothing else ever deletes them.
_MAX_CACHE_FILES = 600
_MAX_CACHE_BYTES = 64 * 1024 * 1024


class SamsungTVThumbnailView(HomeAssistantView):
    """Serve a downscaled JPEG thumbnail of an image stored under ``<config>/www``.

    Unauthenticated on purpose: plain ``<img>`` requests carry no HA auth, and
    this only ever reads files under ``<config>/www`` — which Home Assistant
    already serves publicly at ``/local/`` — so it exposes nothing new. The
    requested path is strictly validated to stay within that directory
    (realpath containment check) to prevent traversal.
    """

    url = THUMBNAIL_URL
    name = "api:samsungtv_smart:thumbnail"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize the view."""
        self._hass = hass
        self._www = os.path.realpath(hass.config.path("www"))
        self._cache_dir = os.path.join(hass.config.path("www"), *_CACHE_SUBDIR)

    async def get(self, request: web.Request) -> web.StreamResponse:
        """Return a resized JPEG for ``?path=<url>&w=<width>``."""
        raw_path = request.query.get("path")
        if not raw_path:
            return web.Response(status=400, text="missing path")

        try:
            width = int(request.query.get("w", _DEFAULT_W))
        except (TypeError, ValueError):
            width = _DEFAULT_W
        width = _snap_width(width)

        src = self._resolve(raw_path)
        if src is None:
            return web.Response(status=404, text="not found")

        try:
            data = await self._hass.async_add_executor_job(
                self._build_thumbnail, src, width
            )
        except FileNotFoundError:
            return web.Response(status=404, text="not found")
        except Exception as ex:  # noqa: BLE001 - never 500 the whole grid
            _LOGGER.debug("Thumbnail build failed for %s: %s", src, ex)
            # Fall back to the original so the tile still shows something.
            raise web.HTTPFound(self._local_url(src)) from None

        if data is None:
            # Pillow unavailable → serve the original (un-resized) instead.
            raise web.HTTPFound(self._local_url(src))

        return web.Response(
            body=data,
            content_type="image/jpeg",
            headers={"Cache-Control": "max-age=86400"},
        )

    def _resolve(self, raw_path: str) -> str | None:
        """Map a ``/local/...`` URL (or www-relative path) to a file under www."""
        path = raw_path.split("?", 1)[0]
        if path.startswith("/local/"):
            rel = path[len("/local/") :]
        elif path.startswith("/config/www/"):
            rel = path[len("/config/www/") :]
        else:
            rel = path.lstrip("/")

        candidate = os.path.realpath(os.path.join(self._www, rel))
        # Strict containment: candidate must be the www dir or below it.
        if candidate != self._www and not candidate.startswith(self._www + os.sep):
            return None
        if not os.path.isfile(candidate):
            return None
        return candidate

    def _local_url(self, abs_path: str) -> str:
        """Build the public ``/local/...`` URL for an absolute www path."""
        rel = os.path.relpath(abs_path, self._www).replace(os.sep, "/")
        return f"/local/{rel}"

    def _build_thumbnail(self, src: str, width: int) -> bytes | None:
        """Return resized JPEG bytes (runs in executor). None if Pillow missing.

        Results are cached on disk keyed by (path, width, mtime), so a file is
        only re-encoded when it actually changes.
        """
        try:
            from PIL import Image, ImageOps  # noqa: PLC0415 - optional, lazy
        except ImportError:
            return None

        mtime = int(os.path.getmtime(src))
        key = hashlib.sha1(f"{src}|{width}|{mtime}".encode()).hexdigest()
        os.makedirs(self._cache_dir, exist_ok=True)
        cache_file = os.path.join(self._cache_dir, f"{key}.jpg")

        if os.path.isfile(cache_file):
            with open(cache_file, "rb") as fh:
                return fh.read()

        tmp_file = f"{cache_file}.{os.getpid()}.tmp"
        try:
            with Image.open(src) as image:
                # Honour EXIF orientation; cap to width (allow tall portraits).
                image = ImageOps.exif_transpose(image)
                image.thumbnail((width, width * 4))
                if image.mode not in ("RGB", "L"):
                    image = image.convert("RGB")
                image.save(tmp_file, format="JPEG", quality=78, optimize=True)
            os.replace(tmp_file, cache_file)
        finally:
            # A failed encode used to leave the temp file behind for good.
            if os.path.exists(tmp_file):
                try:
                    os.remove(tmp_file)
                except OSError:
                    pass

        _prune_cache(self._cache_dir)

        with open(cache_file, "rb") as fh:
            return fh.read()


def _snap_width(width: int) -> int:
    """Clamp to the served range and snap up to the next _WIDTH_STEP."""
    width = max(_MIN_W, min(_MAX_W, width))
    snapped = -(-width // _WIDTH_STEP) * _WIDTH_STEP
    return min(snapped, _MAX_W)


def _prune_cache(cache_dir: str) -> None:
    """Drop the oldest renditions until the cache is back inside its bounds.

    Runs in the executor, right after a write. Best-effort throughout: this is
    a cache, and failing to prune it must never fail the request that
    triggered the prune.
    """
    try:
        entries = []
        total = 0
        with os.scandir(cache_dir) as it:
            for item in it:
                if not item.name.endswith(".jpg"):
                    continue
                try:
                    stat = item.stat()
                except OSError:
                    continue
                entries.append((stat.st_mtime, stat.st_size, item.path))
                total += stat.st_size

        count = len(entries)
        if count <= _MAX_CACHE_FILES and total <= _MAX_CACHE_BYTES:
            return

        entries.sort()  # oldest first
        for _mtime, size, path in entries:
            if count <= _MAX_CACHE_FILES and total <= _MAX_CACHE_BYTES:
                break
            try:
                os.remove(path)
            except OSError:
                continue
            count -= 1
            total -= size
    except OSError as ex:
        _LOGGER.debug("Thumbnail cache prune failed in %s: %s", cache_dir, ex)
