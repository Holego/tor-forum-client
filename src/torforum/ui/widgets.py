"""Reusable UI pieces."""

import contextlib
from collections.abc import Awaitable, Callable
from datetime import datetime
from typing import ClassVar

import flet as ft

from torforum.media import MediaError, MediaLoader
from torforum.models import Embed, User
from torforum.text import relative_time, split_links

STATUS_COLORS = {
    "newbie": ft.Colors.BLUE_GREY_400,
    "member": ft.Colors.BLUE_600,
    "veteran": ft.Colors.GREEN_700,
    "moderator": ft.Colors.AMBER_800,
    "banned": ft.Colors.RED_700,
}

Action = Callable[[], Awaitable[None] | None]


def safe_update(*controls: ft.Control) -> None:
    """Update controls that may have left the screen meanwhile (user went back mid-request)."""
    for control in controls:
        with contextlib.suppress(RuntimeError):  # not on the page any more: nothing to redraw
            control.update()


def now() -> datetime:
    return datetime.now().astimezone()


def when(moment: datetime | None) -> str:
    return relative_time(moment, now()) if moment else ""


def avatar(username: str, radius: int = 18) -> ft.CircleAvatar:
    return ft.CircleAvatar(
        content=ft.Text(username[:1].upper(), weight=ft.FontWeight.BOLD),
        radius=radius,
        bgcolor=ft.Colors.PRIMARY_CONTAINER,
        color=ft.Colors.ON_PRIMARY_CONTAINER,
    )


def status_badge(user: User) -> ft.Control:
    if not user.status_display:
        return ft.Container()
    return ft.Container(
        content=ft.Text(
            user.status_display.upper(), size=9, weight=ft.FontWeight.BOLD, color=ft.Colors.WHITE
        ),
        bgcolor=STATUS_COLORS.get(user.status, ft.Colors.BLUE_GREY_400),
        padding=ft.Padding.symmetric(horizontal=6, vertical=2),
        border_radius=4,
    )


def loading(text: str = "Загрузка через Tor…") -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [ft.ProgressRing(), ft.Text(text, color=ft.Colors.ON_SURFACE_VARIANT)],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=16,
        ),
        alignment=ft.Alignment.CENTER,
        padding=40,
    )


def message_box(
    text: str,
    *,
    icon: ft.IconData = ft.Icons.ERROR_OUTLINE,
    actions: list[ft.Control] | None = None,
) -> ft.Control:
    return ft.Container(
        content=ft.Column(
            [
                ft.Icon(icon, size=40, color=ft.Colors.ON_SURFACE_VARIANT),
                ft.Text(text, text_align=ft.TextAlign.CENTER),
                ft.Row(actions or [], alignment=ft.MainAxisAlignment.CENTER, wrap=True),
            ],
            horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            spacing=12,
        ),
        alignment=ft.Alignment.CENTER,
        padding=32,
    )


class LinkText:
    """Message text with links shown as tappable spans.

    Tapping a link copies it rather than opening a browser: an ordinary
    browser would load it outside Tor (and couldn't open .onion anyway).
    """

    @staticmethod
    def build(text: str, on_link: Callable[[str], None]) -> ft.Text:
        spans = []
        for segment in split_links(text):
            if segment.url:
                url = segment.url
                spans.append(
                    ft.TextSpan(
                        segment.text,
                        style=ft.TextStyle(color=ft.Colors.PRIMARY, decoration=ft.TextDecoration.UNDERLINE),
                        on_click=lambda _, url=url: on_link(url),
                    )
                )
            else:
                spans.append(ft.TextSpan(segment.text))
        return ft.Text(spans=spans, selectable=True, size=15)


@ft.control
class RemoteImage(ft.Container):
    """An image/GIF from a link in a post, downloaded through Tor once it's on screen."""

    url: str = ""
    loader: ClassVar[MediaLoader | None] = None

    def init(self):
        self._mounted = False
        self.border_radius = 8
        self.clip_behavior = ft.ClipBehavior.ANTI_ALIAS
        self.content = ft.Container(
            content=ft.Row(
                [ft.ProgressRing(width=16, height=16, stroke_width=2), ft.Text("картинка…", size=12)],
                spacing=8,
            ),
            padding=8,
        )

    def did_mount(self):
        self._mounted = True
        self.page.run_task(self._load)

    def will_unmount(self):
        self._mounted = False

    async def _load(self):
        try:
            assert self.loader is not None
            data = await self.loader.load(self.url)
        except (MediaError, AssertionError) as e:
            self.content = ft.Container(
                content=ft.Row(
                    [
                        ft.Icon(ft.Icons.BROKEN_IMAGE_OUTLINED, size=18, color=ft.Colors.ON_SURFACE_VARIANT),
                        ft.Text(
                            str(e) or "Не удалось загрузить", size=12, color=ft.Colors.ON_SURFACE_VARIANT
                        ),
                    ],
                    spacing=6,
                ),
                padding=8,
                bgcolor=ft.Colors.SURFACE_CONTAINER_HIGHEST,
            )
        else:
            self.content = ft.Image(src=data, fit=ft.BoxFit.CONTAIN, gapless_playback=True)
        if self._mounted:
            safe_update(self)


def embed_control(embed: Embed, on_link: Callable[[str], None]) -> ft.Control:
    if embed.kind == "image":
        return ft.Container(RemoteImage(url=embed.url), height=None, width=None)
    icon = ft.Icons.PLAY_CIRCLE_OUTLINE if embed.kind == "video" else ft.Icons.AUDIOTRACK
    label = "Видео" if embed.kind == "video" else "Аудио"
    return ft.ListTile(
        leading=ft.Icon(icon),
        title=ft.Text(label),
        subtitle=ft.Text(embed.url, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS, size=12),
        trailing=ft.Icon(ft.Icons.CONTENT_COPY, size=18),
        dense=True,
        on_click=lambda _: on_link(embed.url),
    )


def media_column(
    embeds: list[Embed], image_urls: list[str], on_link: Callable[[str], None]
) -> ft.Control | None:
    items = [Embed("image", url) for url in image_urls] + list(embeds)
    if not items:
        return None
    return ft.Column([embed_control(e, on_link) for e in items], spacing=8)


def post_card(
    author: User,
    body: str,
    created_at: datetime,
    *,
    embeds: list[Embed],
    images: list[str] | None = None,
    on_link: Callable[[str], None],
) -> ft.Control:
    header = ft.Row(
        [
            avatar(author.username),
            ft.Column(
                [
                    ft.Row(
                        [ft.Text(author.username, weight=ft.FontWeight.BOLD), status_badge(author)],
                        spacing=8,
                    ),
                    ft.Text(when(created_at), size=12, color=ft.Colors.ON_SURFACE_VARIANT),
                ],
                spacing=2,
                expand=True,
            ),
        ],
        spacing=10,
    )
    parts: list[ft.Control] = [header, LinkText.build(body, on_link)]
    media = media_column(embeds, images or [], on_link)
    if media:
        parts.append(media)
    return ft.Card(content=ft.Container(ft.Column(parts, spacing=10), padding=14))


def chat_bubble(body: str, created_at: datetime, *, mine: bool, embeds: list[Embed], on_link) -> ft.Control:
    content: list[ft.Control] = [LinkText.build(body, on_link)]
    media = media_column(embeds, [], on_link)
    if media:
        content.append(media)
    content.append(ft.Text(when(created_at), size=11, color=ft.Colors.ON_SURFACE_VARIANT))
    bubble = ft.Container(
        content=ft.Column(content, spacing=6, tight=True),
        bgcolor=ft.Colors.PRIMARY_CONTAINER if mine else ft.Colors.SURFACE_CONTAINER_HIGHEST,
        padding=12,
        border_radius=ft.BorderRadius(
            top_left=16, top_right=16, bottom_left=4 if not mine else 16, bottom_right=4 if mine else 16
        ),
        width=300,
    )
    return ft.Row([bubble], alignment=ft.MainAxisAlignment.END if mine else ft.MainAxisAlignment.START)


def composer(hint: str, on_send: Callable[[str], Awaitable[bool]], *, min_lines: int = 1) -> ft.Control:
    """Text box + send button. `on_send` returns True if the text was sent (then the box is cleared)."""
    field = ft.TextField(
        hint_text=hint,
        multiline=True,
        min_lines=min_lines,
        max_lines=5,
        expand=True,
        shift_enter=True,
        border_radius=20,
        dense=True,
    )
    button = ft.IconButton(ft.Icons.SEND, tooltip="Отправить")

    async def send(_=None):
        text = (field.value or "").strip()
        if not text:
            return
        field.disabled = button.disabled = True
        safe_update(field, button)
        try:
            if await on_send(text):
                field.value = ""
        finally:
            field.disabled = button.disabled = False
            safe_update(field, button)

    button.on_click = send
    field.on_submit = send
    return ft.Container(
        content=ft.Row([field, button], vertical_alignment=ft.CrossAxisAlignment.END),
        padding=ft.Padding.only(left=12, right=4, top=6, bottom=10),
        bgcolor=ft.Colors.SURFACE_CONTAINER,
    )
