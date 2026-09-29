"""Driving the Tor built into the Android app (flet_tor.TorManager) through bootstrap."""

import asyncio
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Protocol

from torforum.bridges import ConnectionMode, bridges_for

PHASE_RE = re.compile(r'(\w+)=("(?:[^"\\]|\\.)*"|\S+)')

# Russian names for Tor's bootstrap phases (the TAG= in status/bootstrap-phase).
PHASE_NAMES = {
    "starting": "Запуск Tor",
    "conn_pt": "Подключение к мосту",
    "conn_done_pt": "Мост подключён",
    "conn_proxy": "Подключение к прокси",
    "conn_done_proxy": "Прокси подключён",
    "conn": "Подключение к сети Tor",
    "conn_done": "Подключено к узлу Tor",
    "handshake": "Установка защищённого соединения",
    "handshake_done": "Соединение установлено",
    "onehop_create": "Связь с каталогом сети",
    "requesting_status": "Запрос состояния сети",
    "loading_status": "Загрузка состояния сети",
    "loading_keys": "Загрузка ключей",
    "requesting_descriptors": "Запрос списка узлов",
    "loading_descriptors": "Загрузка списка узлов",
    "enough_dirinfo": "Сведений о сети достаточно",
    "circuit_create": "Построение цепочки",
    "done": "Готово",
}


@dataclass(frozen=True)
class BootstrapStatus:
    progress: int = 0
    tag: str = "starting"
    summary: str = ""
    warning: str = ""
    socks_port: int | None = None
    error: str | None = None

    @property
    def ready(self) -> bool:
        return self.progress >= 100 and self.socks_port is not None

    @property
    def phase_name(self) -> str:
        tag = self.tag.removeprefix("ap_")  # "ap_conn" etc. repeat the early phases for exit circuits
        return PHASE_NAMES.get(tag, self.summary or tag)

    @classmethod
    def from_backend(cls, data: dict[str, Any]) -> "BootstrapStatus":
        """Parse TorManager.status(), whose "phase" is Tor's raw status/bootstrap-phase, e.g.
        NOTICE BOOTSTRAP PROGRESS=50 TAG=loading_descriptors SUMMARY="Loading relay descriptors"."""
        fields = {k: v.strip('"') for k, v in PHASE_RE.findall(data.get("phase") or "")}
        port = data.get("socks_port")
        progress = fields.get("PROGRESS", "0")
        return cls(
            progress=int(progress) if progress.isdigit() else 0,
            tag=fields.get("TAG", "starting"),
            summary=fields.get("SUMMARY", ""),
            warning=fields.get("WARNING", ""),
            socks_port=port if isinstance(port, int) and port > 0 else None,
            error=data.get("error") or None,
        )


class TorBackend(Protocol):
    async def start(self, bridges: list[str]) -> None: ...

    async def status(self) -> dict[str, Any]: ...


class EmbeddedTorError(Exception):
    pass


StatusCallback = Callable[[BootstrapStatus, ConnectionMode], Awaitable[None] | None]


class EmbeddedTor:
    # In AUTO mode a direct connection that hasn't got past these within this time is
    # treated as blocked (typical in Russia, Iran, China...) and Snowflake is tried instead.
    FALLBACK_AFTER_SECONDS = 40.0
    FALLBACK_BELOW_PROGRESS = 25
    POLL_SECONDS = 1.0

    def __init__(
        self,
        backend: TorBackend,
        *,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ):
        self.backend = backend
        self.clock = clock
        self.sleep = sleep

    async def connect(
        self, mode: ConnectionMode, custom_bridges: list[str], on_status: StatusCallback
    ) -> int:
        """Start/reconfigure Tor and wait until it's bootstrapped; returns the SOCKS port."""
        active = ConnectionMode.DIRECT if mode == ConnectionMode.AUTO else mode
        await self.backend.start(bridges_for(active, custom_bridges))
        started = self.clock()
        while True:
            status = BootstrapStatus.from_backend(await self.backend.status())
            result = on_status(status, active)
            if asyncio.iscoroutine(result):
                await result
            if status.error:
                raise EmbeddedTorError(status.error)
            if status.ready:
                return status.socks_port
            if (
                mode == ConnectionMode.AUTO
                and active == ConnectionMode.DIRECT
                and status.progress < self.FALLBACK_BELOW_PROGRESS
                and self.clock() - started > self.FALLBACK_AFTER_SECONDS
            ):
                active = ConnectionMode.SNOWFLAKE
                await self.backend.start(bridges_for(active, custom_bridges))
                started = self.clock()
            await self.sleep(self.POLL_SECONDS)
