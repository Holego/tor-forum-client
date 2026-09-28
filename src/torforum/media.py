"""Downloading images/GIFs linked in posts — through Tor, size-capped, cached in memory."""

import asyncio
from collections import OrderedDict

import httpx

from torforum.config import IMAGE_CACHE_BYTES, MAX_IMAGE_BYTES
from torforum.onion import host_of, is_local_host
from torforum.tor import socks_proxy_url

# Magic numbers of the formats Flutter can decode. Checking the bytes rather
# than trusting Content-Type means a link to an HTML page or a huge video
# that merely *claims* to be an image never gets handed to the decoder.
IMAGE_SIGNATURES = (
    b"\x89PNG\r\n\x1a\n",
    b"\xff\xd8\xff",  # JPEG
    b"GIF87a",
    b"GIF89a",
    b"BM",  # BMP
)


class MediaError(Exception):
    pass


def looks_like_image(head: bytes) -> bool:
    if head.startswith(IMAGE_SIGNATURES):
        return True
    return head[:4] == b"RIFF" and head[8:12] == b"WEBP"


class ImageCache:
    """LRU cache bounded by total size in bytes."""

    def __init__(self, max_bytes: int = IMAGE_CACHE_BYTES):
        self.max_bytes = max_bytes
        self._items: OrderedDict[str, bytes] = OrderedDict()
        self._size = 0

    def get(self, url: str) -> bytes | None:
        data = self._items.get(url)
        if data is not None:
            self._items.move_to_end(url)
        return data

    def put(self, url: str, data: bytes) -> None:
        if len(data) > self.max_bytes:
            return
        if url in self._items:
            self._size -= len(self._items.pop(url))
        self._items[url] = data
        self._size += len(data)
        while self._size > self.max_bytes:
            _, evicted = self._items.popitem(last=False)
            self._size -= len(evicted)


class MediaLoader:
    def __init__(
        self,
        socks_port: int | None,
        *,
        max_bytes: int = MAX_IMAGE_BYTES,
        cache: ImageCache | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.socks_port = socks_port
        self.max_bytes = max_bytes
        self.cache = cache or ImageCache()
        self._transport = transport
        self._clients: dict[str, httpx.AsyncClient] = {}
        self._inflight: dict[str, asyncio.Task[bytes]] = {}

    def _client_for(self, url: str) -> httpx.AsyncClient:
        host = host_of(url)
        if is_local_host(host):
            key, proxy = "direct", None
        elif self.socks_port is None:
            raise MediaError("Tor не запущен")
        else:
            # One circuit per image host, separate from the forums' circuits.
            key, proxy = host, socks_proxy_url(self.socks_port, isolation_key=f"media:{host}")
        if key not in self._clients:
            self._clients[key] = httpx.AsyncClient(
                proxy=proxy,
                transport=self._transport,
                timeout=httpx.Timeout(90.0),
                # Redirects stay on the same (Tor) route; a local-only client must not be
                # bounced to some outside host, which it would then reach directly.
                follow_redirects=proxy is not None,
                headers={"Accept": "image/*"},
            )
        return self._clients[key]

    async def load(self, url: str) -> bytes:
        cached = self.cache.get(url)
        if cached is not None:
            return cached
        # Several posts often link the same GIF: share one download.
        task = self._inflight.get(url)
        if task is None:
            task = asyncio.ensure_future(self._download(url))
            self._inflight[url] = task
            task.add_done_callback(lambda _: self._inflight.pop(url, None))
        return await asyncio.shield(task)

    async def _download(self, url: str) -> bytes:
        if not url.startswith(("http://", "https://")):
            raise MediaError("Неподдерживаемая ссылка")
        client = self._client_for(url)
        chunks: list[bytes] = []
        size = 0
        try:
            async with client.stream("GET", url) as response:
                if response.status_code != 200:
                    raise MediaError(f"Картинка недоступна ({response.status_code})")
                declared = response.headers.get("Content-Length")
                if declared and declared.isdigit() and int(declared) > self.max_bytes:
                    raise MediaError("Картинка слишком большая")
                async for chunk in response.aiter_bytes():
                    size += len(chunk)
                    if size > self.max_bytes:
                        raise MediaError("Картинка слишком большая")
                    chunks.append(chunk)
        except httpx.HTTPError as e:
            raise MediaError("Не удалось загрузить картинку") from e
        data = b"".join(chunks)
        if not looks_like_image(data[:16]):
            raise MediaError("По ссылке не картинка")
        self.cache.put(url, data)
        return data

    async def set_socks_port(self, socks_port: int | None) -> None:
        """Tor appeared, went away or moved: drop clients bound to the old proxy."""
        if socks_port != self.socks_port:
            await self.aclose()
            self.socks_port = socks_port

    async def aclose(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()
