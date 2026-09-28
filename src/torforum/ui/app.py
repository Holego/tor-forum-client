"""Application shell: state, Tor detection, forum clients and screen navigation."""

import logging

import flet as ft

from torforum.api import ForumClient
from torforum.config import APP_NAME, DEFAULT_SOCKS_PORTS
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
        page.views.clear()
        await self.open(ForumsScreen(self))
        await self.detect_tor()

    # --- Tor ---

    async def detect_tor(self) -> int | None:
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

    def _notify_tor_status(self) -> None:
        for screen in self.screens:
            handler = getattr(screen, "on_tor_status", None)
            if handler:
                handler()

    async def _on_lifecycle(self, e: ft.AppLifecycleStateChangeEvent) -> None:
        # Coming back from Orbot after tapping "Connect": look for Tor again.
        if e.state == ft.AppLifecycleState.RESUME and self.socks_port is None and not self.tor_checking:
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
