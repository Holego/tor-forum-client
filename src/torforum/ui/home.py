"""Start screen: Tor status and the list of saved forums."""

import flet as ft

from torforum.bridges import BridgeError, ConnectionMode, parse_bridge_lines
from torforum.config import DEFAULT_SOCKS_PORTS
from torforum.onion import AddressError, normalize_address, short_host
from torforum.storage import SavedForum
from torforum.ui.base import Screen

MODE_LABELS = {
    ConnectionMode.AUTO: "автоматически",
    ConnectionMode.DIRECT: "напрямую",
    ConnectionMode.SNOWFLAKE: "через Snowflake",
    ConnectionMode.CUSTOM: "через ваши мосты",
}


class ForumsScreen(Screen):
    route = "/"

    def build(self) -> ft.View:
        self.tor_card = ft.Container()
        self.forum_list = ft.Column(spacing=4)
        self.render_tor_status()
        self.render_forums()
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(
                title=ft.Text("Tor Forum"),
                actions=[
                    ft.IconButton(
                        ft.Icons.VPN_LOCK,
                        tooltip="Подключение к Tor",
                        on_click=self.open_connection,
                    )
                ],
            ),
            floating_action_button=ft.FloatingActionButton(
                icon=ft.Icons.ADD, content="Форум", on_click=self.add_forum_dialog
            ),
            controls=[
                ft.ListView(
                    [self.tor_card, ft.Container(height=4), self.forum_list, ft.Container(height=80)],
                    expand=True,
                    padding=12,
                )
            ],
            padding=0,
        )

    async def on_resume(self) -> None:
        self.render_forums()
        self.refresh(self.forum_list)

    def on_tor_status(self) -> None:
        self.render_tor_status()
        self.refresh(self.tor_card)

    # --- Tor status ---

    def render_tor_status(self) -> None:
        app = self.app
        actions: list[ft.Control] = []
        progress = None
        extra = None
        if app.embedded and app.tor_error:
            icon = ft.Icon(ft.Icons.WIFI_OFF, color=ft.Colors.ERROR)
            color = ft.Colors.ERROR_CONTAINER
            title, subtitle = "Не удалось подключиться к Tor", app.tor_error
            actions = [
                ft.TextButton("Настройки", on_click=self.open_connection),
                ft.FilledButton("Повторить", on_click=self.recheck_tor),
            ]
        elif app.embedded and not app.tor_ready.is_set():
            status = app.tor_status
            icon = ft.Icon(ft.Icons.VPN_LOCK, color=ft.Colors.PRIMARY)
            color = ft.Colors.SURFACE_CONTAINER_HIGH
            title = f"Подключение к Tor · {status.progress}%"
            subtitle = status.phase_name
            if app.tor_mode:
                subtitle += f" ({MODE_LABELS[app.tor_mode]})"
            progress = ft.ProgressBar(value=max(status.progress, 2) / 100, border_radius=4)
            if status.warning:
                extra = ft.Text(f"Tor: {status.warning}", size=12, color=ft.Colors.ON_SURFACE_VARIANT)
            actions = [ft.TextButton("Настройки подключения", on_click=self.open_connection)]
        elif app.tor_checking:
            icon = ft.ProgressRing(width=22, height=22, stroke_width=3)
            color = ft.Colors.SURFACE_CONTAINER_HIGH
            title, subtitle = "Ищу Tor…", "Проверяю tor и Tor Browser на этом компьютере"
        elif app.socks_port:
            icon = ft.Icon(ft.Icons.VPN_LOCK, color=ft.Colors.GREEN_700)
            color = ft.Colors.with_opacity(0.12, ft.Colors.GREEN)
            title = "Tor подключён"
            if app.embedded:
                subtitle = f"Встроенный Tor, {MODE_LABELS[app.tor_mode or ConnectionMode.DIRECT]}"
            else:
                subtitle = f"Все запросы идут через Tor (SOCKS-порт {app.socks_port})"
        else:
            icon = ft.Icon(ft.Icons.WIFI_OFF, color=ft.Colors.ERROR)
            color = ft.Colors.ERROR_CONTAINER
            title = "Tor не найден"
            subtitle = "Запустите tor или Tor Browser и проверьте снова"
            actions = [
                ft.TextButton("Подробнее", on_click=self.open_connection),
                ft.FilledButton("Проверить снова", on_click=self.recheck_tor),
            ]

        rows: list[ft.Control] = [
            ft.Row(
                [
                    icon,
                    ft.Column(
                        [ft.Text(title, weight=ft.FontWeight.BOLD), ft.Text(subtitle, size=13)],
                        spacing=2,
                        expand=True,
                    ),
                ],
                spacing=14,
            )
        ]
        if progress:
            rows.append(progress)
        if extra:
            rows.append(extra)
        if actions:
            rows.append(ft.Row(actions, alignment=ft.MainAxisAlignment.END, wrap=True))
        self.tor_card.content = ft.Container(
            content=ft.Column(rows, spacing=8),
            bgcolor=color,
            border_radius=16,
            padding=16,
        )

    async def recheck_tor(self, _=None) -> None:
        await self.app.detect_tor()
        if not self.app.embedded and not self.app.socks_port:
            self.app.toast("Tor пока не отвечает")

    async def open_connection(self, _=None) -> None:
        await self.app.open(ConnectionScreen(self.app))

    # --- forums ---

    def render_forums(self) -> None:
        forums = self.app.state.forums
        if not forums:
            self.forum_list.controls = [
                ft.Container(
                    ft.Text(
                        "Список пуст. Нажмите «+ Форум» и вставьте .onion-адрес.",
                        color=ft.Colors.ON_SURFACE_VARIANT,
                    ),
                    padding=24,
                )
            ]
            return
        self.forum_list.controls = [self._forum_tile(f) for f in forums]

    def _forum_tile(self, forum: SavedForum) -> ft.Control:
        subtitle = short_host(forum.url)
        if forum.logged_in:
            subtitle += f" · {forum.username}"
        return ft.Card(
            content=ft.ListTile(
                leading=ft.CircleAvatar(
                    content=ft.Icon(ft.Icons.FORUM),
                    bgcolor=ft.Colors.PRIMARY_CONTAINER,
                    color=ft.Colors.ON_PRIMARY_CONTAINER,
                ),
                title=ft.Text(forum.name, weight=ft.FontWeight.W_600),
                subtitle=ft.Text(subtitle, size=12),
                trailing=ft.PopupMenuButton(
                    items=[
                        ft.PopupMenuItem(
                            content="Скопировать адрес",
                            icon=ft.Icons.CONTENT_COPY,
                            on_click=lambda _, f=forum: self.app.copy_link(f.url),
                        ),
                        ft.PopupMenuItem(
                            content="Удалить",
                            icon=ft.Icons.DELETE_OUTLINE,
                            on_click=lambda _, f=forum: self.confirm_delete(f),
                        ),
                    ]
                ),
                on_click=lambda _, f=forum: self.page.run_task(self.open_forum, f),
            )
        )

    async def open_forum(self, forum: SavedForum) -> None:
        from torforum.ui.forum import ForumScreen

        await self.app.open(ForumScreen(self.app, forum))

    def confirm_delete(self, forum: SavedForum) -> None:
        async def delete(_):
            self.page.pop_dialog()
            await self.app.forget_forum(forum)
            self.render_forums()
            self.refresh(self.forum_list)

        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Удалить форум?"),
                content=ft.Text(f"«{forum.name}» пропадёт из списка, вход на нём будет забыт."),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Удалить", on_click=delete),
                ],
            )
        )

    def add_forum_dialog(self, _=None) -> None:
        address = ft.TextField(
            label="Адрес форума",
            hint_text="xxxxxxxx….onion",
            autofocus=True,
            prefix_icon=ft.Icons.LINK,
        )
        name = ft.TextField(label="Название (необязательно)")

        async def add(_=None):
            try:
                url = normalize_address(address.value or "")
            except AddressError as e:
                address.error = str(e)
                address.update()
                return
            if self.app.state.find_by_url(url):
                address.error = "Этот форум уже есть в списке"
                address.update()
                return
            forum = SavedForum(name=(name.value or "").strip() or short_host(url), url=url)
            self.app.state.forums.append(forum)
            await self.app.save_state()
            self.page.pop_dialog()
            self.render_forums()
            self.refresh(self.forum_list)
            await self.open_forum(forum)

        address.on_submit = add
        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Добавить форум"),
                content=ft.Column([address, name], tight=True, width=420),
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Добавить", on_click=add),
                ],
            )
        )


class ConnectionScreen(Screen):
    """How the app reaches Tor: built-in Tor settings on Android, tor / Tor Browser on desktop."""

    route = "/connection"

    def build(self) -> ft.View:
        body = self._embedded_settings() if self.app.embedded else self._desktop_help()
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(title=ft.Text("Подключение к Tor")),
            controls=[ft.ListView(body, expand=True, padding=16, spacing=12)],
            padding=0,
        )

    def on_tor_status(self) -> None:
        if self.app.embedded:
            self.status.content = self._status_row()
            self.refresh(self.status)

    def _status_row(self) -> ft.Control:
        app = self.app
        if app.tor_error:
            icon, color, text = ft.Icons.ERROR_OUTLINE, ft.Colors.ERROR, app.tor_error
        elif app.tor_ready.is_set():
            icon, color = ft.Icons.CHECK_CIRCLE, ft.Colors.GREEN_700
            text = f"Tor подключён ({MODE_LABELS[app.tor_mode or ConnectionMode.DIRECT]})"
        else:
            icon, color = ft.Icons.HOURGLASS_TOP, ft.Colors.PRIMARY
            mode = f", {MODE_LABELS[app.tor_mode]}" if app.tor_mode else ""
            text = f"{app.tor_status.progress}% — {app.tor_status.phase_name}{mode}"
        return ft.Row(
            [ft.Icon(icon, color=color), ft.Text(text, weight=ft.FontWeight.W_600, expand=True)],
            spacing=10,
        )

    # --- Android: the Tor built into the app ---

    def _embedded_settings(self) -> list[ft.Control]:
        state = self.app.state
        self.status = ft.Container(self._status_row(), padding=16)

        def option(mode: ConnectionMode, title: str, text: str) -> ft.Control:
            return ft.Container(
                ft.Column(
                    [
                        ft.Radio(value=mode, label=title),
                        ft.Container(
                            ft.Text(text, size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                            padding=ft.Padding.only(left=48),
                        ),
                    ],
                    spacing=0,
                ),
                padding=ft.Padding.only(bottom=6),
            )

        self.mode = ft.RadioGroup(
            value=state.connection_mode,
            on_change=self._mode_changed,
            content=ft.Column(
                [
                    option(
                        ConnectionMode.AUTO,
                        "Автоматически (рекомендуется)",
                        "Сначала напрямую. Если Tor заблокирован провайдером — "
                        "сам переключится на Snowflake.",
                    ),
                    option(
                        ConnectionMode.DIRECT,
                        "Напрямую",
                        "Быстрее всего, если Tor в вашей сети не блокируют.",
                    ),
                    option(
                        ConnectionMode.SNOWFLAKE,
                        "Snowflake",
                        "Встроенный мост через добровольцев-посредников. "
                        "Помогает при блокировках, но медленнее.",
                    ),
                    option(
                        ConnectionMode.CUSTOM,
                        "Свои мосты (obfs4, WebTunnel)",
                        "Если ничего не помогает: вставьте свежие мосты ниже.",
                    ),
                ],
                spacing=0,
            ),
        )
        self.bridges = ft.TextField(
            label="Мосты — по одному в строке",
            value="\n".join(state.custom_bridges),
            multiline=True,
            min_lines=4,
            max_lines=8,
            text_size=12,
            visible=state.connection_mode == ConnectionMode.CUSTOM,
        )
        self.bridges_help = ft.Text(
            "Свежие мосты obfs4 и WebTunnel выдаёт Telegram-бот @GetBridgesBot и сайт bridges.torproject.org "
            "(его можно открыть в любом браузере). Скопируйте строки целиком.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=state.connection_mode == ConnectionMode.CUSTOM,
        )
        return [
            ft.Text(
                "Tor встроен в приложение: .onion-сайты открываются без Orbot и Tor Browser, "
                "а все запросы, включая картинки, идут только через Tor."
            ),
            ft.Card(content=self.status),
            self.mode,
            self.bridges,
            self.bridges_help,
            ft.Row(
                [ft.FilledButton("Подключиться", icon=ft.Icons.VPN_LOCK, on_click=self.apply)],
                alignment=ft.MainAxisAlignment.END,
            ),
        ]

    def _mode_changed(self, _=None) -> None:
        custom = self.mode.value == ConnectionMode.CUSTOM
        self.bridges.visible = self.bridges_help.visible = custom
        self.refresh(self.bridges, self.bridges_help)

    async def apply(self, _=None) -> None:
        mode = ConnectionMode(self.mode.value or ConnectionMode.AUTO)
        bridges: list[str] = []
        if mode == ConnectionMode.CUSTOM:
            try:
                bridges = parse_bridge_lines(self.bridges.value or "")
            except BridgeError as e:
                self.bridges.error = str(e)
                self.refresh(self.bridges)
                return
            if not bridges:
                self.bridges.error = "Вставьте хотя бы один мост"
                self.refresh(self.bridges)
                return
        self.bridges.error = None
        self.refresh(self.bridges)
        self.app.state.connection_mode = mode
        if mode == ConnectionMode.CUSTOM:
            self.app.state.custom_bridges = bridges
        await self.app.save_state()
        self.app.connect_embedded()
        self.app.toast("Подключаюсь к Tor…")

    # --- desktop: tor or Tor Browser running on the computer ---

    def _desktop_help(self) -> list[ft.Control]:
        self.port_field = ft.TextField(
            label="SOCKS-порт Tor",
            hint_text=" или ".join(map(str, DEFAULT_SOCKS_PORTS)) + " (автоматически)",
            value=str(self.app.state.socks_port or ""),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=260,
        )
        self.result = ft.Text()
        return [
            ft.Text(
                "На компьютере приложение ходит через уже запущенный Tor: службу tor (порт 9050) "
                "или Tor Browser (порт 9150). Запустите одно из них — приложение найдёт его само. "
                "Мимо Tor приложение ничего не отправляет."
            ),
            ft.Row([self.port_field], wrap=True),
            ft.Row(
                [ft.FilledButton("Проверить подключение", on_click=self.check), self.result],
                wrap=True,
            ),
        ]

    async def check(self, _=None) -> None:
        raw = (self.port_field.value or "").strip()
        if raw and not (raw.isdigit() and 0 < int(raw) < 65536):
            self.port_field.error = "Порт — число от 1 до 65535"
            self.port_field.update()
            return
        self.port_field.error = None
        self.port_field.update()
        self.app.state.socks_port = int(raw) if raw else None
        await self.app.save_state()
        self.result.value = "Проверяю…"
        self.result.update()
        port = await self.app.detect_tor()
        self.result.value = f"Tor найден на порту {port}" if port else "Tor не отвечает"
        self.refresh(self.result)
