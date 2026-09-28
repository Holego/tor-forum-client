"""Browsing a forum: categories → topics → posts, replying and starting topics."""

import asyncio
import contextlib

import flet as ft

from torforum.api import AuthRequired, ForumError, NotSupported, TorNotRunning
from torforum.models import Category, Page, Post, Topic
from torforum.onion import short_host
from torforum.storage import SavedForum
from torforum.text import plural
from torforum.ui.base import Screen
from torforum.ui.widgets import composer, loading, message_box, post_card, when


class ForumScreenBase(Screen):
    """Shared plumbing for screens that talk to one forum."""

    def __init__(self, app, forum: SavedForum):
        super().__init__(app)
        self.forum = forum

    @property
    def client(self):
        return self.app.client_for(self.forum)

    def show_error(self, error: Exception, retry) -> None:
        """Replace the screen body with an explanation and a way forward."""
        actions: list[ft.Control] = [ft.FilledButton("Повторить", icon=ft.Icons.REFRESH, on_click=retry)]
        icon = ft.Icons.ERROR_OUTLINE
        text = str(error)
        if isinstance(error, TorNotRunning):
            icon = ft.Icons.WIFI_OFF
            self.page.run_task(self.app.detect_tor)  # keep the status on the start screen truthful

            async def help_and_recheck(_):
                from torforum.ui.home import TorHelpScreen

                await self.app.open(TorHelpScreen(self.app))

            actions.insert(0, ft.OutlinedButton("Как подключить Tor", on_click=help_and_recheck))
        elif isinstance(error, NotSupported):
            icon = ft.Icons.PUBLIC
            text += "\n\nЭтот сайт можно открыть в Tor Browser."
            actions = [
                ft.OutlinedButton(
                    "Скопировать адрес",
                    icon=ft.Icons.CONTENT_COPY,
                    on_click=lambda _: self.app.copy_link(self.forum.url),
                )
            ]
        elif not isinstance(error, ForumError):
            text = "Что-то пошло не так. Попробуйте ещё раз."
        self.set_body(message_box(text, icon=icon, actions=actions))

    async def handle_auth_expired(self) -> None:
        """The token was revoked (logout elsewhere, password change): forget it and ask to log in again."""
        await self.app.remember_login(self.forum, None, None)
        self.app.toast("Сессия истекла — войдите снова")
        await self.open_login()

    async def open_login(self, _=None) -> None:
        from torforum.ui.account import LoginScreen

        await self.app.open(LoginScreen(self.app, self.forum))


class ForumScreen(ForumScreenBase):
    """Categories of one forum."""

    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}"
        self.title = ft.Text(self.forum.name)
        self.appbar = ft.AppBar(title=self.title, actions=self._actions())
        return ft.View(route=self.route, appbar=self.appbar, controls=[self.body], padding=0)

    def _actions(self, unread: int = 0) -> list[ft.Control]:
        if not self.forum.logged_in:
            return [ft.TextButton("Войти", icon=ft.Icons.LOGIN, on_click=self.open_login)]
        mail = ft.IconButton(
            ft.Icons.MAIL_OUTLINE,
            tooltip="Личные сообщения",
            on_click=self.open_messages,
            badge=ft.Badge(label=str(unread)) if unread else None,
        )
        account = ft.PopupMenuButton(
            icon=ft.Icons.ACCOUNT_CIRCLE,
            items=[
                ft.PopupMenuItem(content=f"Вы вошли как {self.forum.username}", icon=ft.Icons.PERSON),
                ft.PopupMenuItem(content="Выйти", icon=ft.Icons.LOGOUT, on_click=self.logout),
            ],
        )
        return [mail, account]

    def _update_appbar(self, unread: int = 0) -> None:
        self.appbar.actions = self._actions(unread)
        self.refresh(self.appbar)

    async def load(self, _=None) -> None:
        self.set_body(loading())
        try:
            client = self.client
            info, categories = await asyncio.gather(client.info(), client.categories())
            unread = 0
            if self.forum.logged_in:
                try:
                    unread = (await client.me()).unread_messages
                except AuthRequired:
                    await self.app.remember_login(self.forum, None, None)
        except Exception as e:
            self.show_error(e, self.load)
            return

        if info.name and self.forum.name == short_host(self.forum.url):
            # Added by address only: use the name the forum gives itself.
            self.forum.name = info.name
            self.title.value = info.name
            await self.app.save_state()
        self._update_appbar(unread)
        self.set_body(
            ft.ListView(
                [self._category_tile(c) for c in categories]
                or [message_box("На форуме пока нет разделов", icon=ft.Icons.INBOX)],
                expand=True,
                padding=12,
                spacing=4,
            )
        )

    async def on_resume(self) -> None:
        # Login state or unread count may have changed; the categories themselves rarely do.
        unread = 0
        if self.forum.logged_in:
            with contextlib.suppress(ForumError):
                unread = (await self.client.me()).unread_messages
        self._update_appbar(unread)

    def _category_tile(self, category: Category) -> ft.Control:
        return ft.Card(
            content=ft.ListTile(
                title=ft.Text(category.name, weight=ft.FontWeight.W_600),
                subtitle=ft.Text(category.description) if category.description else None,
                trailing=ft.Column(
                    [
                        ft.Text(str(category.topic_count), weight=ft.FontWeight.BOLD),
                        ft.Text("тем", size=11, color=ft.Colors.ON_SURFACE_VARIANT),
                    ],
                    spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER,
                    alignment=ft.MainAxisAlignment.CENTER,
                ),
                on_click=lambda _, c=category: self.page.run_task(
                    self.app.open, TopicsScreen(self.app, self.forum, c)
                ),
            )
        )

    async def open_messages(self, _=None) -> None:
        from torforum.ui.messages import ConversationsScreen

        await self.app.open(ConversationsScreen(self.app, self.forum))

    async def logout(self, _=None) -> None:
        with contextlib.suppress(ForumError):  # offline: still forget the token locally
            await self.client.logout()
        await self.app.remember_login(self.forum, None, None)
        self._update_appbar()
        self.app.toast("Вы вышли")


class TopicsScreen(ForumScreenBase):
    def __init__(self, app, forum: SavedForum, category: Category):
        super().__init__(app, forum)
        self.category = category
        self.pages_loaded: Page[Topic] | None = None

    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}/c/{self.category.slug}"
        self.list = ft.ListView(expand=True, padding=12, spacing=4)
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(
                title=ft.Text(self.category.name),
                actions=[ft.IconButton(ft.Icons.REFRESH, tooltip="Обновить", on_click=self.load)],
            ),
            floating_action_button=ft.FloatingActionButton(
                icon=ft.Icons.EDIT, content="Новая тема", on_click=self.new_topic
            ),
            controls=[self.body],
            padding=0,
        )

    async def load(self, _=None, *, silent: bool = False) -> None:
        if not silent:
            self.set_body(loading())
        try:
            page = await self.client.topics(self.category.slug)
        except Exception as e:
            if silent:
                return
            self.show_error(e, self.load)
            return
        self.list.controls = [self._topic_tile(t) for t in page.items] or [
            message_box("Тем пока нет — начните первую!", icon=ft.Icons.FORUM)
        ]
        self._add_more_button(page)
        self.set_body(self.list)

    def _add_more_button(self, page: Page[Topic]) -> None:
        self.pages_loaded = page
        if page.next_number:
            self.list.controls.append(
                ft.Container(ft.OutlinedButton("Показать ещё", on_click=self.load_more), padding=12)
            )

    async def load_more(self, e) -> None:
        assert self.pages_loaded and self.pages_loaded.next_number
        e.control.disabled = True
        e.control.update()
        try:
            page = await self.client.topics(self.category.slug, page=self.pages_loaded.next_number)
        except ForumError as err:
            e.control.disabled = False
            e.control.update()
            self.app.toast(str(err))
            return
        self.list.controls.pop()  # the button
        self.list.controls.extend(self._topic_tile(t) for t in page.items)
        self._add_more_button(page)
        self.refresh(self.list)

    async def on_resume(self) -> None:
        await self.load(silent=True)  # keep the list on screen while fetching new replies/topics

    def _topic_tile(self, topic: Topic) -> ft.Control:
        if topic.is_pinned:
            icon = ft.Icon(ft.Icons.PUSH_PIN, color=ft.Colors.ERROR)
        elif topic.is_locked:
            icon = ft.Icon(ft.Icons.LOCK_OUTLINE, color=ft.Colors.ON_SURFACE_VARIANT)
        else:
            icon = ft.Icon(ft.Icons.CHAT_BUBBLE_OUTLINE, color=ft.Colors.PRIMARY)
        meta = f"{topic.author.username} · {plural(topic.reply_count, 'ответ', 'ответа', 'ответов')}"
        if topic.last_post_at:
            meta += f" · {when(topic.last_post_at)}"
        return ft.Card(
            content=ft.ListTile(
                leading=icon,
                title=ft.Text(topic.title, weight=ft.FontWeight.W_600, max_lines=2),
                subtitle=ft.Text(meta, size=12),
                on_click=lambda _, t=topic: self.page.run_task(
                    self.app.open, TopicScreen(self.app, self.forum, t.id, t.title)
                ),
            )
        )

    async def new_topic(self, _=None) -> None:
        if not self.forum.logged_in:
            self.app.toast("Чтобы создать тему, войдите")
            await self.open_login()
            return
        await self.app.open(NewTopicScreen(self.app, self.forum, self.category))


class TopicScreen(ForumScreenBase):
    def __init__(self, app, forum: SavedForum, topic_id: int, title: str):
        super().__init__(app, forum)
        self.topic_id = topic_id
        self.title = title
        self.topic: Topic | None = None
        self.last_page: Page[Post] | None = None
        self.loaded_as_member = forum.logged_in

    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}/t/{self.topic_id}"
        self.list = ft.ListView(expand=True, padding=12, spacing=6)
        self.bottom = ft.Container()
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(
                title=ft.Text(self.title, max_lines=1, overflow=ft.TextOverflow.ELLIPSIS),
                actions=[ft.IconButton(ft.Icons.REFRESH, tooltip="Обновить", on_click=self.load)],
            ),
            controls=[ft.Column([self.body, self.bottom], expand=True, spacing=0)],
            padding=0,
        )

    def _card(self, post: Post) -> ft.Control:
        return post_card(
            post.author,
            post.body,
            post.created_at,
            embeds=post.embeds,
            images=post.images,
            on_link=self.app.copy_link,
        )

    async def load(self, _=None) -> None:
        self.loaded_as_member = self.forum.logged_in
        self.set_body(loading())
        try:
            self.topic, page = await asyncio.gather(
                self.client.topic(self.topic_id), self.client.posts(self.topic_id)
            )
        except AuthRequired:
            self.set_body(
                message_box(
                    "Темы на этом форуме видны только участникам",
                    icon=ft.Icons.LOCK_OUTLINE,
                    actions=[ft.FilledButton("Войти", icon=ft.Icons.LOGIN, on_click=self.open_login)],
                )
            )
            if self.forum.logged_in:
                await self.handle_auth_expired()
            return
        except Exception as e:
            self.show_error(e, self.load)
            return
        self.list.controls = [self._card(p) for p in page.items]
        self._add_more_button(page)
        self.set_body(self.list)
        self._render_bottom()

    def _add_more_button(self, page: Page[Post]) -> None:
        self.last_page = page
        if page.next_number:
            self.list.controls.append(
                ft.Container(ft.OutlinedButton("Показать ещё", on_click=self.load_more), padding=12)
            )

    async def load_more(self, e) -> None:
        assert self.last_page and self.last_page.next_number
        e.control.disabled = True
        e.control.update()
        try:
            page = await self.client.posts(self.topic_id, page=self.last_page.next_number)
        except ForumError as err:
            e.control.disabled = False
            e.control.update()
            self.app.toast(str(err))
            return
        self.list.controls.pop()
        self.list.controls.extend(self._card(p) for p in page.items)
        self._add_more_button(page)
        self.refresh(self.list)

    def _render_bottom(self) -> None:
        if self.topic and self.topic.is_locked:
            self.bottom.content = ft.Container(
                ft.Row([ft.Icon(ft.Icons.LOCK_OUTLINE), ft.Text("Тема закрыта для ответов")]),
                padding=14,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
            )
        elif not self.forum.logged_in:
            self.bottom.content = ft.Container(
                ft.FilledButton("Войти, чтобы ответить", icon=ft.Icons.LOGIN, on_click=self.open_login),
                padding=10,
                alignment=ft.Alignment.CENTER,
                bgcolor=ft.Colors.SURFACE_CONTAINER,
            )
        else:
            self.bottom.content = composer("Ваш ответ…", self.send_reply)
        self.refresh(self.bottom)

    async def send_reply(self, text: str) -> bool:
        try:
            post = await self.client.reply(self.topic_id, text)
        except AuthRequired:
            await self.handle_auth_expired()
            return False
        except ForumError as e:
            self.app.toast(str(e))
            return False
        if self.last_page and self.last_page.next_number:
            self.app.toast("Ответ отправлен")  # it's on a page we haven't loaded yet
        else:
            self.list.controls.append(self._card(post))
            self.refresh(self.list)
            await asyncio.sleep(0.3)  # let the client lay the new card out, or the scroll stops short of it
            await self.list.scroll_to(offset=-1, duration=300)
        return True

    async def on_resume(self) -> None:
        if self.forum.logged_in != self.loaded_as_member:
            await self.load()  # just logged in (or out): posts may be visible now
        else:
            self._render_bottom()


class NewTopicScreen(ForumScreenBase):
    def __init__(self, app, forum: SavedForum, category: Category):
        super().__init__(app, forum)
        self.category = category

    def build(self) -> ft.View:
        self.route = f"/forum/{self.forum.id}/c/{self.category.slug}/new"
        self.title_field = ft.TextField(label="Заголовок", max_length=200, autofocus=True)
        self.body_field = ft.TextField(
            label="Сообщение",
            multiline=True,
            min_lines=8,
            max_lines=16,
            hint_text="Картинку или гифку вставьте прямой ссылкой (…/pic.png, .gif, .mp4) — "
            "она раскроется под постом",
        )
        self.submit = ft.FilledButton("Опубликовать", icon=ft.Icons.SEND, on_click=self.publish)
        return ft.View(
            route=self.route,
            appbar=ft.AppBar(title=ft.Text(f"Новая тема · {self.category.name}")),
            controls=[
                ft.ListView(
                    [
                        self.title_field,
                        self.body_field,
                        ft.Row([self.submit], alignment=ft.MainAxisAlignment.END),
                    ],
                    expand=True,
                    padding=16,
                    spacing=12,
                )
            ],
            padding=0,
        )

    async def publish(self, _=None) -> None:
        title, body = (self.title_field.value or "").strip(), (self.body_field.value or "").strip()
        self.title_field.error = None if title else "Введите заголовок"
        self.body_field.error = None if body else "Напишите сообщение"
        self.refresh(self.title_field, self.body_field)
        if not (title and body):
            return
        self.submit.disabled = True
        self.refresh(self.submit)
        try:
            topic = await self.client.new_topic(self.category.slug, title, body)
        except AuthRequired:
            await self.handle_auth_expired()
            return
        except ForumError as e:
            self.app.toast(str(e))
            self.submit.disabled = False
            self.refresh(self.submit)
            return
        await self.app.replace(TopicScreen(self.app, self.forum, topic.id, topic.title))
