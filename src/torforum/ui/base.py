"""Screen base class: one ft.View plus the logic to fill it."""

from typing import TYPE_CHECKING

import flet as ft

if TYPE_CHECKING:
    from torforum.ui.app import App


class Screen:
    route = "/"

    def __init__(self, app: "App"):
        self.app = app
        self.view: ft.View | None = None
        self.body = ft.Container(expand=True)

    @property
    def page(self) -> ft.Page:
        return self.app.page

    @property
    def active(self) -> bool:
        """Still on the navigation stack (the user may have gone back while we were loading)."""
        return self.view is not None and self.view in self.page.views

    def build(self) -> ft.View:
        raise NotImplementedError

    async def load(self) -> None:
        """Fetch data and fill the view. Called right after the screen is shown."""

    async def on_resume(self) -> None:
        """The user came back to this screen from one opened on top of it."""

    def set_body(self, control: ft.Control) -> None:
        self.body.content = control
        if self.active:
            self.body.update()

    def refresh(self, *controls: ft.Control) -> None:
        if self.active:
            for control in controls:
                control.update()
