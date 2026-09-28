"""A tiny SOCKS5 server standing in for Tor in tests.

It records what the client asked the proxy for (credentials, target host)
and then plays the target web server itself, returning a canned response.
"""

import asyncio
import socket
from dataclasses import dataclass, field


@dataclass
class ProxiedRequest:
    username: str | None
    host: str
    port: int
    request_line: str


@dataclass
class FakeSocks5:
    body: bytes = b"{}"
    content_type: str = "application/json"
    reply_code: int = 0  # 0 = succeeded; 4 = host unreachable (what Tor says for an offline onion)
    requests: list[ProxiedRequest] = field(default_factory=list)
    port: int = 0

    async def __aenter__(self) -> "FakeSocks5":
        self._server = await asyncio.start_server(self._handle, "127.0.0.1", 0)
        self.port = self._server.sockets[0].getsockname()[1]
        return self

    async def __aexit__(self, *exc_info) -> None:
        self._server.close()
        await self._server.wait_closed()

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            await self._serve(reader, writer)
        except (asyncio.IncompleteReadError, ConnectionError):
            pass
        finally:
            writer.close()

    async def _serve(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        _version, n_methods = await reader.readexactly(2)
        methods = await reader.readexactly(n_methods)
        username = None
        if 2 in methods:  # username/password (RFC 1929)
            writer.write(b"\x05\x02")
            await reader.readexactly(1)
            username = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
            await reader.readexactly((await reader.readexactly(1))[0])  # password
            writer.write(b"\x01\x00")
        else:
            writer.write(b"\x05\x00")

        _version, _cmd, _reserved, address_type = await reader.readexactly(4)
        if address_type == 3:  # domain name: the proxy resolves it, not the client
            host = (await reader.readexactly((await reader.readexactly(1))[0])).decode()
        elif address_type == 1:
            host = socket.inet_ntoa(await reader.readexactly(4))
        else:
            host = socket.inet_ntop(socket.AF_INET6, await reader.readexactly(16))
        port = int.from_bytes(await reader.readexactly(2), "big")

        writer.write(bytes([5, self.reply_code, 0, 1]) + b"\x00" * 6)
        await writer.drain()
        if self.reply_code != 0:
            return

        head = await reader.readuntil(b"\r\n\r\n")
        request_line = head.split(b"\r\n", 1)[0].decode()
        self.requests.append(ProxiedRequest(username, host, port, request_line))
        writer.write(
            b"HTTP/1.1 200 OK\r\n"
            + f"Content-Type: {self.content_type}\r\nContent-Length: {len(self.body)}\r\n".encode()
            + b"Connection: close\r\n\r\n"
            + self.body
        )
        await writer.drain()
