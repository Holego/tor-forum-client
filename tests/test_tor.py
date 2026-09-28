import asyncio

from fake_socks import FakeSocks5
from torforum.tor import find_socks_port, is_socks5_proxy, socks_proxy_url


async def test_detects_socks5_proxy():
    async with FakeSocks5() as proxy:
        assert await is_socks5_proxy(proxy.port)


async def test_rejects_something_that_is_not_socks():
    async def http_server(reader, writer):
        await reader.read(10)
        writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(http_server, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    try:
        assert not await is_socks5_proxy(port)
    finally:
        server.close()
        await server.wait_closed()


async def test_closed_port_is_not_a_proxy():
    server = await asyncio.start_server(lambda r, w: None, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    server.close()
    await server.wait_closed()
    assert not await is_socks5_proxy(port)
    assert await find_socks_port([port]) is None


async def test_find_socks_port_picks_the_first_working_one():
    async with FakeSocks5() as proxy:
        dead = proxy.port + 1 if proxy.port < 65535 else proxy.port - 1
        assert await find_socks_port([dead, proxy.port]) == proxy.port


def test_isolation_key_gives_each_site_its_own_credentials():
    a = socks_proxy_url(9050, isolation_key="a.onion")
    b = socks_proxy_url(9050, isolation_key="b.onion")
    assert a != b
    assert a == socks_proxy_url(9050, isolation_key="a.onion")
    assert a.startswith("socks5://") and a.endswith("@127.0.0.1:9050")
    assert socks_proxy_url(9150) == "socks5://127.0.0.1:9150"
