"""Start screen: Tor status and the list of saved forums."""

import flet as ft

from torforum.config import DEFAULT_SOCKS_PORTS, ORBOT_FDROID_URL, ORBOT_URL
from torforum.onion import AddressError, normalize_address, short_host
from torforum.storage import SavedForum
from torforum.ui.base import Screen


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
                        ft.Icons.HELP_OUTLINE,
                        tooltip="Как подключиться к Tor",
                        on_click=self.open_help,
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
        if app.tor_checking:
            icon, color = (
                ft.ProgressRing(width=22, height=22, stroke_width=3),
                ft.Colors.SURFACE_CONTAINER_HIGH,
            )
            title, subtitle, actions = "Ищу Tor…", "Проверяю Orbot / tor на этом устройстве", []
        elif app.socks_port:
            icon = ft.Icon(ft.Icons.VPN_LOCK, color=ft.Colors.GREEN_700)
            color = ft.Colors.with_opacity(0.12, ft.Colors.GREEN)
            title = "Tor подключён"
            subtitle = f"Все запросы идут через Tor (SOCKS-порт {app.socks_port})"
            actions = []
        else:
            icon = ft.Icon(ft.Icons.WIFI_OFF, color=ft.Colors.ERROR)
            color = ft.Colors.ERROR_CONTAINER
            title = "Tor не найден"
            subtitle = "Запустите Orbot и нажмите «Подключиться», затем проверьте снова"
            actions = [
                ft.TextButton("Как подключить", on_click=self.open_help),
                ft.FilledButton("Проверить снова", on_click=self.recheck_tor),
            ]
        self.tor_card.content = ft.Container(
            content=ft.Column(
                [
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
                    ),
                    ft.Row(actions, alignment=ft.MainAxisAlignment.END) if actions else ft.Container(),
                ],
                spacing=8,
            ),
            bgcolor=color,
            border_radius=16,
            padding=16,
        )

    async def recheck_tor(self, _=None) -> None:
        await self.app.detect_tor()
        if not self.app.socks_port:
            self.app.toast("Tor пока не отвечает")

    async def open_help(self, _=None) -> None:
        await self.app.open(TorHelpScreen(self.app))

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


class TorHelpScreen(Screen):
    route = "/tor-help"

    def build(self) -> ft.View:
        self.port_field = ft.TextField(
            label="SOCKS-порт Tor",
            hint_text=" или ".join(map(str, DEFAULT_SOCKS_PORTS)) + " (автоматически)",
            value=str(self.app.state.socks_port or ""),
            keyboard_type=ft.KeyboardType.NUMBER,
            width=260,
        )
        self.result = ft.Text()

        def step(number: int, title: str, text: str, *actions: ft.Control) -> ft.Control:
            return ft.Card(
                content=ft.Container(
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.CircleAvatar(content=ft.Text(str(number)), radius=14),
                                    ft.Text(title, weight=ft.FontWeight.BOLD, expand=True),
                                ]
                            ),
                            ft.Text(text),
                            ft.Row(list(actions), wrap=True) if actions else ft.Container(),
                        ],
                        spacing=10,
                    ),
                    padding=16,
                )
            )

        return ft.View(
            route=self.route,
            appbar=ft.AppBar(title=ft.Text("Подключение к Tor")),
            controls=[
                ft.ListView(
                    [
                        ft.Text(
                            "Приложение само не выходит в интернет напрямую: все запросы идут через Tor, "
                            "который на Android обеспечивает приложение Orbot. Без Tor .onion-сайты "
                            "не открываются, а приложение ничего не отправит мимо него.",
                        ),
                        step(
                            1,
                            "Установите Orbot",
                            "Официальное приложение Tor для Android от Guardian Project.",
                            ft.OutlinedButton(
                                "Сайт Orbot",
                                on_click=lambda _: self.page.run_task(self.app.open_external, ORBOT_URL),
                            ),
                            ft.OutlinedButton(
                                "F-Droid",
                                on_click=lambda _: self.page.run_task(
                                    self.app.open_external, ORBOT_FDROID_URL
                                ),
                            ),
                        ),
                        step(
                            2,
                            "Подключитесь",
                            "Откройте Orbot и нажмите «Подключиться». Если Tor заблокирован провайдером "
                            "(например, в России), в Orbot откройте выбор подключения и включите мосты: "
                            "Snowflake, obfs4 или WebTunnel. Свежие мосты выдаёт Telegram-бот @GetBridgesBot "
                            "и сайт bridges.torproject.org.",
                        ),
                        step(
                            3,
                            "Вернитесь сюда",
                            "Приложение найдёт Tor на порту 9050 (Orbot, tor) или 9150 (Tor Browser на "
                            "компьютере). Если у вас другой порт — укажите его ниже.",
                        ),
                        ft.Row([self.port_field], wrap=True),
                        ft.Row(
                            [ft.FilledButton("Проверить подключение", on_click=self.check), self.result],
                            wrap=True,
                        ),
                    ],
                    expand=True,
                    padding=16,
                    spacing=12,
                )
            ],
            padding=0,
        )

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
        self.result.value = f"✅ Tor найден на порту {port}" if port else "❌ Tor не отвечает"
        self.refresh(self.result)
