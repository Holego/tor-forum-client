"""Logging in to / registering on a forum."""

import flet as ft

from torforum.api import ForumError
from torforum.storage import SavedForum
from torforum.ui.base import Screen


class LoginScreen(Screen):
    def __init__(self, app, forum: SavedForum):
        super().__init__(app)
        self.forum = forum

    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}/login"
        self.mode = ft.SegmentedButton(
            segments=[
                ft.Segment(value="login", label=ft.Text("Вход"), icon=ft.Icon(ft.Icons.LOGIN)),
                ft.Segment(value="register", label=ft.Text("Регистрация"), icon=ft.Icon(ft.Icons.PERSON_ADD)),
            ],
            selected=["login"],
            on_change=self.mode_changed,
        )
        self.username = ft.TextField(label="Имя пользователя", autofocus=True, prefix_icon=ft.Icons.PERSON)
        self.password = ft.TextField(
            label="Пароль",
            password=True,
            can_reveal_password=True,
            prefix_icon=ft.Icons.KEY,
            on_submit=self.submit,
        )
        self.hint = ft.Text(
            "Пароль — от 8 символов, не только цифры и не похожий на имя. "
            "Почта не нужна: восстановления пароля нет, запомните его.",
            size=12,
            color=ft.Colors.ON_SURFACE_VARIANT,
            visible=False,
        )
        self.error = ft.Text(color=ft.Colors.ERROR, visible=False)
        self.button = ft.FilledButton("Войти", icon=ft.Icons.LOGIN, on_click=self.submit)
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(title=ft.Text(self.forum.name)),
            controls=[
                ft.ListView(
                    [
                        ft.Row([self.mode], alignment=ft.MainAxisAlignment.CENTER),
                        self.username,
                        self.password,
                        self.hint,
                        self.error,
                        ft.Row([self.button], alignment=ft.MainAxisAlignment.END),
                    ],
                    expand=True,
                    padding=20,
                    spacing=14,
                )
            ],
            padding=0,
        )

    @property
    def registering(self) -> bool:
        return self.mode.selected == ["register"]

    def mode_changed(self, _=None) -> None:
        self.hint.visible = self.registering
        self.button.content = "Зарегистрироваться" if self.registering else "Войти"
        self.error.visible = False
        self.refresh(self.hint, self.button, self.error)

    async def submit(self, _=None) -> None:
        username = (self.username.value or "").strip()
        password = self.password.value or ""
        if not username or not password:
            self._show_error("Введите имя и пароль")
            return
        self.button.disabled = True
        self.error.visible = False
        self.refresh(self.button, self.error)
        client = None
        try:
            client = self.app.client_for(self.forum)
            if self.registering:
                user = await client.register(username, password)
            else:
                user = await client.login(username, password)
        except ForumError as e:
            self._show_error(str(e))
            return
        finally:
            self.button.disabled = False
            self.refresh(self.button)
        await self.app.remember_login(self.forum, user.username, client.token)
        self.app.toast(f"Добро пожаловать, {user.username}!")
        await self.app.back()

    def _show_error(self, text: str) -> None:
        self.error.value = text
        self.error.visible = True
        self.refresh(self.error)
