"""ForumClient against a mocked API (a forum on localhost is reached directly, so respx can intercept)."""

from datetime import UTC, datetime

import httpx
import pytest

from torforum.api import ApiError, AuthRequired, ForumClient, ForumUnreachable, NotSupported

BASE = "http://127.0.0.1:8000"
API = f"{BASE}/api"

USER = {"username": "pirate", "status": "newbie", "status_display": "Новичок", "avatar": None}
POST = {
    "id": 1,
    "author": USER,
    "body": "лол https://x.com/cat.gif",
    "created_at": "2026-09-28T20:47:00+05:00",
    "embeds": [{"kind": "image", "url": "https://x.com/cat.gif"}],
    "images": [],
    "audio": [],
}
TOPIC = {
    "id": 7,
    "title": "Мемы",
    "category": "flood",
    "author": USER,
    "project_url": "",
    "is_pinned": False,
    "is_locked": False,
    "created_at": "2026-09-28T20:00:00+05:00",
    "reply_count": 3,
    "last_post_at": "2026-09-28T21:00:00+05:00",
}


@pytest.fixture
async def client():
    async with ForumClient(BASE, socks_port=None) as c:
        yield c


async def test_info(client, respx_mock):
    respx_mock.get(f"{API}/").respond(json={"api": "tor-forum", "version": 1, "name": "Jo Pirat Forum"})
    info = await client.info()
    assert info.name == "Jo Pirat Forum"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(404, html="<h1>Not Found</h1>"),
        httpx.Response(200, html="<html>phpBB</html>"),
        httpx.Response(200, json={"something": "else"}),
    ],
)
async def test_sites_without_the_api_are_not_supported(client, respx_mock, response):
    respx_mock.get(f"{API}/").mock(return_value=response)
    with pytest.raises(NotSupported):
        await client.info()


async def test_newer_api_version_asks_to_update(client, respx_mock):
    respx_mock.get(f"{API}/").respond(json={"api": "tor-forum", "version": 99})
    with pytest.raises(NotSupported, match="обновите"):
        await client.info()


async def test_login_stores_token_and_sends_it(client, respx_mock):
    respx_mock.post(f"{API}/auth/login/").respond(json={"token": "abc123", "user": USER})
    me = respx_mock.get(f"{API}/me/").respond(json={**USER, "unread_messages": 2})

    user = await client.login("pirate", "secret")
    assert user.username == "pirate"
    assert (await client.me()).unread_messages == 2
    assert me.calls.last.request.headers["Authorization"] == "Token abc123"


async def test_error_detail_is_passed_to_the_user(client, respx_mock):
    respx_mock.post(f"{API}/auth/login/").respond(
        400, json={"detail": "Неверное имя пользователя или пароль."}
    )
    with pytest.raises(ApiError, match="Неверное имя"):
        await client.login("pirate", "wrong")


async def test_field_errors_become_a_message(client, respx_mock):
    respx_mock.post(f"{API}/topics/7/posts/").respond(400, json={"body": ["Это поле не может быть пустым."]})
    with pytest.raises(ApiError, match="не может быть пустым"):
        await client.reply(7, "")


async def test_401_means_login_needed(client, respx_mock):
    respx_mock.get(f"{API}/topics/7/posts/").respond(
        401, json={"detail": "Учетные данные не были предоставлены."}
    )
    with pytest.raises(AuthRequired):
        await client.posts(7)


async def test_logout_forgets_token_even_if_request_fails(client, respx_mock):
    client.token = "abc"
    respx_mock.post(f"{API}/auth/logout/").mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(ForumUnreachable):
        await client.logout()
    assert client.token is None


async def test_topics_page_and_parsing(client, respx_mock):
    respx_mock.get(f"{API}/categories/flood/topics/", params={"page": "2"}).respond(
        json={
            "count": 61,
            "next": f"{API}/categories/flood/topics/?page=3",
            "previous": f"{API}/categories/flood/topics/",
            "results": [TOPIC],
        }
    )
    page = await client.topics("flood", page=2)
    assert (page.number, page.next_number, page.previous_number, page.count) == (2, 3, 1, 61)
    topic = page.items[0]
    assert topic.title == "Мемы" and topic.reply_count == 3
    assert topic.last_post_at == datetime(2026, 9, 28, 16, 0, tzinfo=UTC)


async def test_last_page_number_is_derived_from_previous_link(client, respx_mock):
    respx_mock.get(f"{API}/topics/7/posts/", params={"page": "last"}).respond(
        json={
            "count": 65,
            "next": None,
            "previous": f"{API}/topics/7/posts/?page=2",
            "results": [POST],
        }
    )
    page = await client.posts(7, page="last")
    assert page.number == 3
    assert page.items[0].embeds[0].url == "https://x.com/cat.gif"


async def test_unicode_slugs_and_usernames_are_url_encoded(client, respx_mock):
    route = respx_mock.get(f"{API}/categories/%D1%84%D0%BB%D1%83%D0%B4/topics/").respond(
        json={"count": 0, "next": None, "previous": None, "results": []}
    )
    await client.topics("флуд")
    assert route.called


async def test_messages(client, respx_mock):
    message = {
        "id": 1,
        "sender": "matey",
        "recipient": "pirate",
        "body": "Йо-хо-хо",
        "created_at": "2026-09-28T20:00:00+05:00",
        "is_read": False,
        "embeds": [],
    }
    respx_mock.get(f"{API}/messages/").respond(
        json=[{"user": {**USER, "username": "matey"}, "last_message": message, "unread_count": 1}]
    )
    respx_mock.post(f"{API}/messages/matey/").respond(
        201, json={**message, "sender": "pirate", "recipient": "matey"}
    )

    [conversation] = await client.conversations()
    assert conversation.user.username == "matey" and conversation.unread_count == 1
    sent = await client.send_message("matey", "Йо-хо-хо")
    assert sent.recipient == "matey"
