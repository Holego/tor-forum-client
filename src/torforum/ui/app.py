"""Application shell: state, Tor detection, forum clients and screen navigation."""

import asyncio
import logging

import flet as ft

from torforum.api import ForumClient
from torforum.bridges import ConnectionMode
from torforum.config import APP_NAME, DEFAULT_SOCKS_PORTS
from torforum.embedded import BootstrapStatus, EmbeddedTor
from torforum.media import MediaLoader
from torforum.storage import AppState, SavedForum, StateRepository
from torforum.tor import find_socks_port
from torforum.ui.base import Screen
from torforum.ui.widgets import RemoteImage

log = logging.getLogger(__name__)

TOR_PURPLE = "#7D4698"


class FletStore:
    """Key-value storage on the device (SharedPreferences / NSUserDefaults / localStorage)."""

    def __init__(self):
        self.prefs = ft.SharedPreferences()

    async def get(self, key: str) -> str | None:
        value = await self.prefs.get(key)
        return value if isinstance(value, str) else None

    async def set(self, key: str, value: str) -> None:
        await self.prefs.set(key, value)


class App:
    def __init__(self, page: ft.Page):
        self.page = page
        self.repo = StateRepository(FletStore())
        self.state = AppState()
        self.socks_port: int | None = None
        self.tor_checking = False
        # Built-in Tor (Android): set up in start(); None on desktop, where tor/Tor Browser is used.
        self.embedded: EmbeddedTor | None = None
        self.tor_status = BootstrapStatus()
        self.tor_mode: ConnectionMode | None = None
        self.tor_error: str | None = None
        self.tor_ready = asyncio.Event()
        self._tor_task: asyncio.Task | None = None
        self.media = MediaLoader(socks_port=None)
        RemoteImage.loader = self.media
        self.clipboard = ft.Clipboard()
        self.launcher = ft.UrlLauncher()
        self.screens: list[Screen] = []
        self._clients: dict[str, ForumClient] = {}

    async def start(self) -> None:
        from torforum.ui.home import ForumsScreen

        page = self.page
        page.title = APP_NAME
        page.theme = ft.Theme(color_scheme_seed=TOR_PURPLE)
        page.dark_theme = ft.Theme(color_scheme_seed=TOR_PURPLE)
        page.theme_mode = ft.ThemeMode.SYSTEM
        page.on_view_pop = self._on_view_pop
        page.on_app_lifecycle_state_change = self._on_lifecycle

        self.state = await self.repo.load()
        if page.platform == ft.PagePlatform.ANDROID and not page.web:
            from flet_tor import TorManager  # only bundled into the Android build

            self.embedded = EmbeddedTor(TorManager())
        page.views.clear()
        await self.open(ForumsScreen(self))
        await self.detect_tor()

    # --- Tor ---

    async def detect_tor(self) -> int | None:
        """(Re)connect: start the built-in Tor on Android, look for tor / Tor Browser on desktop."""
        if self.embedded:
            self.connect_embedded()
            return None
        self.tor_checking = True
        self._notify_tor_status()
        ports = [self.state.socks_port] if self.state.socks_port else list(DEFAULT_SOCKS_PORTS)
        try:
            port = await find_socks_port(ports)
        finally:
            self.tor_checking = False
        if port != self.socks_port:
            await self._close_clients()
            await self.media.set_socks_port(port)
            self.socks_port = port
        self._notify_tor_status()
        return port

    def connect_embedded(self) -> None:
        """Start the built-in Tor with the saved connection settings, replacing any attempt in progress."""
        if self._tor_task and not self._tor_task.done():
            self._tor_task.cancel()
        self.tor_ready.clear()
        self.tor_error = None
        self.tor_status = BootstrapStatus()
        self._tor_task = asyncio.ensure_future(self._run_embedded())

    async def _run_embedded(self) -> None:
        assert self.embedded
        mode = ConnectionMode(self.state.connection_mode)
        try:
            port = await self.embedded.connect(mode, self.state.custom_bridges, self._on_bootstrap)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # the plugin's error text, or a channel failure
            log.exception("Built-in Tor failed")
            self.tor_error = str(e) or "Не удалось запустить Tor"
            self._notify_tor_status()
            return
        if port != self.socks_port:
            await self._close_clients()
            await self.media.set_socks_port(port)
            self.socks_port = port
        log.info("Tor ready on SOCKS port %s (%s)", port, self.tor_mode)
        self.tor_ready.set()
        self._notify_tor_status()

    def _on_bootstrap(self, status: BootstrapStatus, mode: ConnectionMode) -> None:
        changed = (status.progress, status.tag, mode) != (
            self.tor_status.progress,
            self.tor_status.tag,
            self.tor_mode,
        )
        self.tor_status, self.tor_mode = status, mode
        if changed:
            self._notify_tor_status()

    @property
    def tor_connecting(self) -> bool:
        return bool(self.embedded) and not self.tor_ready.is_set() and not self.tor_error

    def _notify_tor_status(self) -> None:
        for screen in self.screens:
            handler = getattr(screen, "on_tor_status", None)
            if handler:
                handler()

    async def _on_lifecycle(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        # Desktop: tor / Tor Browser may have been started while the app was in the background.
        if (
            not self.embedded
            and e.state == ft.AppLifecycleState.RESUME
            and self.socks_port is None
            and not self.tor_checking
        ):
            await self.detect_tor()

    # --- forums ---

    def client_for(self, forum: SavedForum) -> ForumClient:
        """Raises TorNotRunning when the forum needs Tor and it isn't available."""
        client = self._clients.get(forum.id)
        if client is None:
            client = ForumClient(forum.url, socks_port=self.socks_port, token=forum.token)
            self._clients[forum.id] = client
        client.token = forum.token
        return client

    async def _close_clients(self) -> None:
        for client in self._clients.values():
            await client.aclose()
        self._clients.clear()

    async def save_state(self) -> None:
        try:
            await self.repo.save(self.state)
        except Exception:  # storage failing must not take the UI down with it
            log.exception("Could not save state")

    async def remember_login(self, forum: SavedForum, username: str | None, token: str | None) -> None:
        forum.username, forum.token = username, token
        await self.save_state()

    async def forget_forum(self, forum: SavedForum) -> None:
        self.state.forums = [f for f in self.state.forums if f.id != forum.id]
        client = self._clients.pop(forum.id, None)
        if client:
            await client.aclose()
        await self.save_state()

    # --- navigation ---

    async def open(self, screen: Screen) -> None:
        self.screens.append(screen)
        screen.view = screen.build()
        self.page.views.append(screen.view)
        self.page.update()
        await screen.load()

    async def replace(self, screen: Screen) -> None:
        """Open `screen` in place of the current one (e.g. a finished form)."""
        if len(self.screens) > 1:
            self.screens.pop()
            self.page.views.pop()
        await self.open(screen)

    async def back(self) -> None:
        if len(self.screens) <= 1:
            return
        self.screens.pop()
        self.page.views.pop()
        self.page.update()
        await self.screens[-1].on_resume()

    async def _on_view_pop(self, e: ft.ViewPopEvent) -> None:
        await self.back()

    # --- small helpers used by screens ---

    def toast(self, text: str) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(text), duration=2500))

    def copy_link(self, url: str) -> None:
        async def copy():
            await self.clipboard.set(url)
            self.toast("Ссылка скопирована — откройте её в Tor Browser")

        self.page.run_task(copy)

    async def open_external(self, url: str) -> None:
        """Only for ordinary public pages like app store links — never for forum content."""
        await self.launcher.launch_url(url)


async def main(page: ft.Page) -> None:
    await App(page).start()
