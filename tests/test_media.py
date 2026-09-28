import httpx
import pytest

from torforum.media import ImageCache, MediaError, MediaLoader, looks_like_image

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
LOCAL_IMG = "http://127.0.0.1:8000/media/a.png"


@pytest.mark.parametrize("head", [PNG, b"\xff\xd8\xff\xe0", b"GIF89a....", b"RIFF\x00\x00\x00\x00WEBPVP8 "])
def test_recognises_images(head):
    assert looks_like_image(head)


@pytest.mark.parametrize("head", [b"<!DOCTYPE html>", b"\x00\x00\x00\x18ftypmp42", b""])
def test_rejects_non_images(head):
    assert not looks_like_image(head)


async def test_downloads_and_caches(respx_mock):
    route = respx_mock.get(LOCAL_IMG).respond(content=PNG)
    loader = MediaLoader(socks_port=None)
    assert await loader.load(LOCAL_IMG) == PNG
    assert await loader.load(LOCAL_IMG) == PNG
    assert route.call_count == 1
    await loader.aclose()


async def test_html_pretending_to_be_an_image_is_rejected(respx_mock):
    respx_mock.get(LOCAL_IMG).respond(content=b"<html>nope</html>", headers={"Content-Type": "image/png"})
    loader = MediaLoader(socks_port=None)
    with pytest.raises(MediaError, match="не картинка"):
        await loader.load(LOCAL_IMG)


async def test_too_big_by_header(respx_mock):
    respx_mock.get(LOCAL_IMG).respond(content=PNG, headers={"Content-Length": str(10**9)})
    loader = MediaLoader(socks_port=None, max_bytes=1000)
    with pytest.raises(MediaError, match="большая"):
        await loader.load(LOCAL_IMG)


async def test_too_big_while_streaming(respx_mock):
    # no Content-Length: the limit must still hold while reading the body
    respx_mock.get(LOCAL_IMG).mock(
        return_value=httpx.Response(200, stream=httpx.ByteStream(PNG + b"\x00" * 5000))
    )
    loader = MediaLoader(socks_port=None, max_bytes=1000)
    with pytest.raises(MediaError, match="большая"):
        await loader.load(LOCAL_IMG)


async def test_http_error_status(respx_mock):
    respx_mock.get(LOCAL_IMG).respond(404)
    loader = MediaLoader(socks_port=None)
    with pytest.raises(MediaError, match="404"):
        await loader.load(LOCAL_IMG)


def test_cache_evicts_least_recently_used():
    cache = ImageCache(max_bytes=10)
    cache.put("a", b"12345")
    cache.put("b", b"12345")
    cache.get("a")  # "a" is now fresher than "b"
    cache.put("c", b"123")
    assert cache.get("b") is None
    assert cache.get("a") == b"12345"
    assert cache.get("c") == b"123"


def test_cache_ignores_items_bigger_than_itself():
    cache = ImageCache(max_bytes=4)
    cache.put("a", b"12345")
    assert cache.get("a") is None
