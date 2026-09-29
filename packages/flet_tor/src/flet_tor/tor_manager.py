from typing import Any

from flet.controls.base_control import control
from flet.controls.services.service import Service


@control("TorManager")
class TorManager(Service):
    """Tor running inside the app (Android only)."""

    async def start(self, bridges: list[str]) -> None:
        """Start Tor if needed and (re)connect with these bridge lines; an empty list means no bridges."""
        await self._invoke_method("start", {"bridges": list(bridges)})

    async def status(self) -> dict[str, Any]:
        """{"running": bool, "phase": str | None, "socks_port": int, "error": str | None}"""
        return await self._invoke_method("status") or {}
