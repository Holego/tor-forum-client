"""Private messages."""

import flet as ft

from torforum.api import AuthRequired, ForumError
from torforum.models import Conversation, Message
from torforum.storage import SavedForum
from torforum.ui.forum import ForumScreenBase
from torforum.ui.widgets import avatar, chat_bubble, composer, loading, message_box, when


class ConversationsScreen(ForumScreenBase):
    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}/messages"
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(
                title=ft.Text("Сообщения"),
                actions=[ft.IconButton(ft.Icons.REFRESH, tooltip="Обновить", on_click=self.load)],
            ),
            floating_action_button=ft.FloatingActionButton(
                icon=ft.Icons.EDIT, content="Написать", on_click=self.new_conversation
            ),
            controls=[self.body],
            padding=0,
        )

    async def load(self, _=None) -> None:
        if not await self.wait_for_tor():
            return
        self.set_body(loading())
        try:
            conversations = await self.client.conversations()
        except AuthRequired:
            await self.handle_auth_expired()
            return
        except Exception as e:
            self.show_error(e, self.load)
            return
        self.set_body(
            ft.ListView(
                [self._tile(c) for c in conversations]
                or [message_box("Переписок пока нет", icon=ft.Icons.MAIL_OUTLINE)],
                expand=True,
                padding=12,
                spacing=4,
            )
        )

    async def on_resume(self) -> None:
        await self.load()

    def _tile(self, conversation: Conversation) -> ft.Control:
        last = conversation.last_message
        prefix = "Вы: " if last.sender == self.forum.username else ""
        name = conversation.user.username
        return ft.Card(
            content=ft.ListTile(
                leading=avatar(name),
                title=ft.Text(name, weight=ft.FontWeight.W_600),
                subtitle=ft.Text(prefix + last.body, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, size=13),
                trailing=ft.Column(
                    [
                        ft.Text(when(last.created_at), size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Badge(label=str(conversation.unread_count))
                        if conversation.unread_count
                        else ft.Container(),
                    ],
                    horizontal_alignment=ft.CrossAxisAlignment.END,
                    alignment=ft.MainAxisAlignment.CENTER,
                    spacing=4,
                ),
                on_click=lambda _, n=name: self.page.run_task(self.open_thread, n),
            )
        )

    async def open_thread(self, username: str) -> None:
        await self.app.open(ThreadScreen(self.app, self.forum, username))

    def new_conversation(self, _=None) -> None:
        username = ft.TextField(label="Кому (имя пользователя)", autofocus=True)

        async def go(_=None):
            name = (username.value or "").strip()
            if not name:
                return
            if name == self.forum.username:
                username.error = "Нельзя написать самому себе"
                username.update()
                return
            self.page.pop_dialog()
            await self.open_thread(name)

        username.on_submit = go
        self.page.show_dialog(
            ft.AlertDialog(
                title=ft.Text("Новое сообщение"),
                content=username,
                actions=[
                    ft.TextButton("Отмена", on_click=lambda _: self.page.pop_dialog()),
                    ft.FilledButton("Дальше", on_click=go),
                ],
            )
        )


class ThreadScreen(ForumScreenBase):
    def __init__(self, app, forum: SavedForum, username: str):
        super().__init__(app, forum)
        self.username = username

    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}/messages/{self.username}"
        self.list = ft.ListView(expand=True, padding=12, spacing=8, auto_scroll=True)
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(
                title=ft.Row([avatar(self.username, radius=14), ft.Text(self.username)], spacing=10),
                actions=[ft.IconButton(ft.Icons.REFRESH, tooltip="Обновить", on_click=self.load)],
            ),
            controls=[
                ft.Column(
                    [self.body, composer("Сообщение…", self.send)],
                    expand=True,
                    spacing=0,
                )
            ],
            padding=0,
        )

    def _bubble(self, message: Message) -> ft.Control:
        return chat_bubble(
            message.body,
            message.created_at,
            mine=message.sender == self.forum.username,
            embeds=message.embeds,
            on_link=self.app.copy_link,
        )

    async def load(self, _=None) -> None:
        if not await self.wait_for_tor():
            return
        self.set_body(loading())
        try:
            messages = await self.client.thread(self.username)
        except AuthRequired:
            await self.handle_auth_expired()
            return
        except Exception as e:
            self.show_error(e, self.load)
            return
        self.list.controls = [self._bubble(m) for m in messages] or [
            message_box(f"Напишите {self.username} первым", icon=ft.Icons.WAVING_HAND)
        ]
        self.set_body(self.list)

    async def send(self, text: str) -> bool:
        try:
            message = await self.client.send_message(self.username, text)
        except AuthRequired:
            await self.handle_auth_expired()
            return False
        except ForumError as e:
            self.app.toast(str(e))
            return False
        if self.list.controls and not isinstance(self.list.controls[0], ft.Row):
            self.list.controls.clear()  # drop the "write first" placeholder
        self.list.controls.append(self._bubble(message))
        if self.body.content is not self.list:
            self.set_body(self.list)
        else:
            self.refresh(self.list)
        return True
