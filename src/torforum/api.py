"""Async client for the forum JSON API, always routed through Tor."""

from typing import Any
from urllib.parse import quote

import httpx

from torforum.config import CONNECT_TIMEOUT, READ_TIMEOUT, USER_AGENT
from torforum.models import (
    Category,
    Conversation,
    ForumInfo,
    Me,
    Message,
    Page,
    Post,
    Topic,
    User,
)
from torforum.onion import host_of, is_local_host
from torforum.tor import socks_proxy_url

API_NAME = "tor-forum"
SUPPORTED_API_VERSION = 1
NOT_SUPPORTED_MESSAGE = "Этот сайт не поддерживает приложение (у него нет API форума)"


class ForumError(Exception):
    """Something went wrong talking to a forum; ``str(error)`` is shown to the user."""


class TorNotRunning(ForumError):
    pass


class ForumUnreachable(ForumError):
    pass


class NotSupported(ForumError):
    """The site is up but doesn't speak this API (e.g. an ordinary phpBB forum)."""


class AuthRequired(ForumError):
    pass


class ApiError(ForumError):
    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def _error_message(response: httpx.Response) -> str:
    """Pull a human-readable message out of a DRF error response."""
    try:
        data = response.json()
    except ValueError:
        return f"Ошибка сервера ({response.status_code})"
    if isinstance(data, dict):
        if isinstance(data.get("detail"), str):
            return data["detail"]
        for value in data.values():
            if isinstance(value, list) and value:
                return str(value[0])
            if isinstance(value, str):
                return value
    if isinstance(data, list) and data:
        return str(data[0])
    return f"Ошибка сервера ({response.status_code})"


def build_http_client(
    base_url: str, socks_port: int | None, *, transport: httpx.AsyncBaseTransport | None = None
) -> httpx.AsyncClient:
    """An httpx client that can only reach ``base_url``'s host through Tor.

    The one exception is a forum on this very device (localhost), which is
    reached directly. For anything else there is deliberately no fallback to
    a direct connection: that would reveal the user's IP address.
    """
    host = host_of(base_url)
    if is_local_host(host):
        proxy = None
    elif socks_port is None:
        raise TorNotRunning("Tor не запущен — запустите Orbot (или tor) и попробуйте снова")
    else:
        proxy = socks_proxy_url(socks_port, isolation_key=host)
    return httpx.AsyncClient(
        proxy=proxy,
        transport=transport,
        timeout=httpx.Timeout(READ_TIMEOUT, connect=CONNECT_TIMEOUT),
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=False,
    )


class ForumClient:
    def __init__(
        self,
        base_url: str,
        socks_port: int | None,
        token: str | None = None,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._via_tor = not is_local_host(host_of(self.base_url))
        self._http = build_http_client(self.base_url, socks_port, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> "ForumClient":
        return self

    async def __aexit__(self, *exc_info) -> None:
        await self.aclose()

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        headers = {"Authorization": f"Token {self.token}"} if self.token else {}
        url = f"{self.base_url}/api/{path}"
        try:
            response = await self._http.request(method, url, headers=headers, **kwargs)
        except httpx.ProxyError as e:
            raise ForumUnreachable(
                "Tor не смог соединиться с сайтом. Возможно, он сейчас выключен — попробуйте позже"
            ) from e
        except httpx.ConnectError as e:
            if self._via_tor:
                raise TorNotRunning("Не удалось подключиться к Tor — проверьте, что Orbot запущен") from e
            raise ForumUnreachable("Сайт не отвечает") from e
        except httpx.TimeoutException as e:
            raise ForumUnreachable(
                "Сайт не ответил вовремя — сеть Tor бывает медленной, попробуйте ещё раз"
            ) from e
        except httpx.HTTPError as e:
            raise ForumUnreachable(f"Ошибка соединения: {e}") from e

        if response.status_code == 401:
            raise AuthRequired(_error_message(response))
        if response.status_code >= 400:
            raise ApiError(_error_message(response), response.status_code)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise NotSupported("Сайт ответил не в формате API форума") from e

    # --- forum ---

    async def info(self) -> ForumInfo:
        """Check the site speaks our API; raises NotSupported for ordinary websites."""
        try:
            data = await self._request("GET", "")
        except (ApiError, NotSupported) as e:
            raise NotSupported(NOT_SUPPORTED_MESSAGE) from e
        if not isinstance(data, dict) or data.get("api") != API_NAME:
            raise NotSupported(NOT_SUPPORTED_MESSAGE)
        info = ForumInfo.from_json(data)
        if info.version > SUPPORTED_API_VERSION:
            raise NotSupported("Форум использует более новую версию API — обновите приложение")
        return info

    async def categories(self) -> list[Category]:
        return [Category.from_json(c) for c in await self._request("GET", "categories/")]

    async def topics(self, category_slug: str, page: int = 1) -> Page[Topic]:
        data = await self._request(
            "GET", f"categories/{quote(category_slug, safe='')}/topics/", params={"page": page}
        )
        return Page.from_json(data, Topic.from_json)

    async def topic(self, topic_id: int) -> Topic:
        return Topic.from_json(await self._request("GET", f"topics/{topic_id}/"))

    async def posts(self, topic_id: int, page: int | str = 1) -> Page[Post]:
        data = await self._request("GET", f"topics/{topic_id}/posts/", params={"page": page})
        return Page.from_json(data, Post.from_json)

    async def reply(self, topic_id: int, body: str) -> Post:
        return Post.from_json(await self._request("POST", f"topics/{topic_id}/posts/", json={"body": body}))

    async def new_topic(self, category_slug: str, title: str, body: str) -> Topic:
        data = await self._request(
            "POST", f"categories/{quote(category_slug, safe='')}/topics/", json={"title": title, "body": body}
        )
        return Topic.from_json(data)

    # --- account ---

    async def login(self, username: str, password: str) -> User:
        data = await self._request("POST", "auth/login/", json={"username": username, "password": password})
        self.token = data["token"]
        return User.from_json(data["user"])

    async def register(self, username: str, password: str) -> User:
        data = await self._request(
            "POST", "auth/register/", json={"username": username, "password": password}
        )
        self.token = data["token"]
        return User.from_json(data["user"])

    async def logout(self) -> None:
        try:
            await self._request("POST", "auth/logout/")
        finally:
            self.token = None

    async def me(self) -> Me:
        return Me.from_json(await self._request("GET", "me/"))

    # --- private messages ---

    async def conversations(self) -> list[Conversation]:
        return [Conversation.from_json(c) for c in await self._request("GET", "messages/")]

    async def thread(self, username: str) -> list[Message]:
        return [
            Message.from_json(m) for m in await self._request("GET", f"messages/{quote(username, safe='')}/")
        ]

    async def send_message(self, username: str, body: str) -> Message:
        return Message.from_json(
            await self._request("POST", f"messages/{quote(username, safe='')}/", json={"body": body})
        )
