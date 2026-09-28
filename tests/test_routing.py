"""The privacy-critical part: remote sites are only ever reached through Tor."""

import json

import pytest

from fake_socks import FakeSocks5
from torforum.api import ForumClient, ForumUnreachable, TorNotRunning, build_http_client
from torforum.media import MediaError, MediaLoader

ROOT = json.dumps({"api": "tor-forum", "version": 1, "name": "Jo Pirat Forum"}).encode()
GIF = b"GIF89a\x01\x00\x01\x00\x00\x00\x00;"


async def test_onion_requests_go_through_socks_with_remote_dns(onion_url):
    async with FakeSocks5(body=ROOT) as tor, ForumClient(onion_url, socks_port=tor.port) as client:
        info = await client.info()

    assert info.name == "Jo Pirat Forum"
    [request] = tor.requests
    # The .onion name itself is handed to Tor — it can't be resolved locally anyway,
    # and resolving any hostname locally would leak it to the DNS server.
    assert request.host == onion_url.removeprefix("http://")
    assert request.port == 80
    assert request.request_line == "GET /api/ HTTP/1.1"
    assert request.username  # per-site stream isolation


async def test_no_tor_means_no_connection_at_all(onion_url):
    with pytest.raises(TorNotRunning):
        build_http_client(onion_url, socks_port=None)


async def test_tor_down_is_reported_as_tor_problem(onion_url):
    async with FakeSocks5() as tor:
        port = tor.port  # the proxy is gone once we leave this block
    async with ForumClient(onion_url, socks_port=port) as client:
        with pytest.raises(TorNotRunning):
            await client.info()


async def test_offline_onion_is_reported_as_unreachable(onion_url):
    async with FakeSocks5(reply_code=4) as tor, ForumClient(onion_url, socks_port=tor.port) as client:
        with pytest.raises(ForumUnreachable):
            await client.info()


async def test_media_from_different_hosts_uses_different_circuits():
    async with FakeSocks5(body=GIF, content_type="image/gif") as tor:
        loader = MediaLoader(socks_port=tor.port)
        try:
            # plain http: the fake proxy plays the web server itself and doesn't speak TLS
            assert await loader.load("http://i.imgur.com/a.gif") == GIF
            assert await loader.load("http://media.tenor.com/b.gif") == GIF
        finally:
            await loader.aclose()

    first, second = tor.requests
    assert (first.host, second.host) == ("i.imgur.com", "media.tenor.com")
    assert first.username != second.username


async def test_media_without_tor_is_refused():
    loader = MediaLoader(socks_port=None)
    with pytest.raises(MediaError):
        await loader.load("https://i.imgur.com/a.gif")
