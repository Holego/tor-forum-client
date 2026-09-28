"""Finding the local Tor SOCKS proxy (Orbot on Android, tor / Tor Browser on desktop)."""

import asyncio
import contextlib
import hashlib
from collections.abc import Iterable

from torforum.config import DEFAULT_SOCKS_PORTS, SOCKS_HOST

SOCKS5_NO_AUTH_GREETING = b"\x05\x01\x00"  # version 5, one method offered: "no authentication"
SOCKS5_NO_AUTH_REPLY = b"\x05\x00"


async def is_socks5_proxy(port: int, host: str = SOCKS_HOST, wait: float = 2.0) -> bool:
    """Open a TCP connection and do the first step of a SOCKS5 handshake.

    Just checking that *something* listens on the port isn't enough — a web
    server or another app could be sitting on 9050 — so we make sure it
    actually answers like a SOCKS5 proxy.
    """
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection(host, port), wait)
    except (OSError, TimeoutError):
        return False
    try:
        writer.write(SOCKS5_NO_AUTH_GREETING)
        await writer.drain()
        reply = await asyncio.wait_for(reader.readexactly(2), wait)
        return reply == SOCKS5_NO_AUTH_REPLY
    except (OSError, TimeoutError, asyncio.IncompleteReadError):
        return False
    finally:
        writer.close()
        with contextlib.suppress(OSError):
            await writer.wait_closed()


async def find_socks_port(candidates: Iterable[int] = DEFAULT_SOCKS_PORTS) -> int | None:
    """The first port with a working SOCKS5 proxy, or ``None`` if Tor isn't running."""
    for port in candidates:
        if await is_socks5_proxy(port):
            return port
    return None


def socks_proxy_url(port: int, isolation_key: str | None = None) -> str:
    """Proxy URL for httpx.

    Tor puts connections with different SOCKS credentials on different
    circuits (IsolateSOCKSAuth is on by default), so giving each forum its own
    made-up username keeps one site from being linked to another by exit
    relays or onion services seeing the same circuit.
    """
    if isolation_key is None:
        return f"socks5://{SOCKS_HOST}:{port}"
    user = hashlib.sha256(isolation_key.encode()).hexdigest()[:16]
    return f"socks5://{user}:x@{SOCKS_HOST}:{port}"
