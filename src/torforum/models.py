"""Typed views of the forum API's JSON (see the jo-pirat-forum README for the API)."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any
from urllib.parse import parse_qs, urlsplit


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value) if value else None


@dataclass(frozen=True)
class ForumInfo:
    name: str
    api: str
    version: int
    registration: bool = True

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "ForumInfo":
        return cls(
            name=data.get("name") or "",
            api=data["api"],
            version=int(data["version"]),
            registration=bool(data.get("registration", True)),
        )


@dataclass(frozen=True)
class User:
    username: str
    status: str = ""
    status_display: str = ""
    avatar: str | None = None

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "User":
        return cls(
            username=data["username"],
            status=data.get("status") or "",
            status_display=data.get("status_display") or "",
            avatar=data.get("avatar"),
        )


@dataclass(frozen=True)
class Me:
    user: User
    unread_messages: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Me":
        return cls(user=User.from_json(data), unread_messages=int(data.get("unread_messages", 0)))


@dataclass(frozen=True)
class Embed:
    kind: str  # "image" | "video" | "audio"
    url: str

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Embed":
        return cls(kind=data["kind"], url=data["url"])


@dataclass(frozen=True)
class Category:
    slug: str
    name: str
    description: str
    topic_count: int
    post_count: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Category":
        return cls(
            slug=data["slug"],
            name=data["name"],
            description=data.get("description") or "",
            topic_count=int(data.get("topic_count", 0)),
            post_count=int(data.get("post_count", 0)),
        )


@dataclass(frozen=True)
class Topic:
    id: int
    title: str
    category: str
    author: User
    created_at: datetime
    reply_count: int = 0
    last_post_at: datetime | None = None
    is_pinned: bool = False
    is_locked: bool = False
    project_url: str = ""

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Topic":
        return cls(
            id=int(data["id"]),
            title=data["title"],
            category=data.get("category") or "",
            author=User.from_json(data["author"]),
            created_at=_dt(data["created_at"]),
            reply_count=int(data.get("reply_count", 0)),
            last_post_at=_dt(data.get("last_post_at")),
            is_pinned=bool(data.get("is_pinned")),
            is_locked=bool(data.get("is_locked")),
            project_url=data.get("project_url") or "",
        )


@dataclass(frozen=True)
class Post:
    id: int
    author: User
    body: str
    created_at: datetime
    embeds: list[Embed] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    audio: list[str] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Post":
        return cls(
            id=int(data["id"]),
            author=User.from_json(data["author"]),
            body=data.get("body") or "",
            created_at=_dt(data["created_at"]),
            embeds=[Embed.from_json(e) for e in data.get("embeds", [])],
            images=list(data.get("images", [])),
            audio=list(data.get("audio", [])),
        )


@dataclass(frozen=True)
class Message:
    id: int
    sender: str
    recipient: str
    body: str
    created_at: datetime
    is_read: bool = False
    embeds: list[Embed] = field(default_factory=list)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Message":
        return cls(
            id=int(data["id"]),
            sender=data["sender"],
            recipient=data["recipient"],
            body=data.get("body") or "",
            created_at=_dt(data["created_at"]),
            is_read=bool(data.get("is_read")),
            embeds=[Embed.from_json(e) for e in data.get("embeds", [])],
        )


@dataclass(frozen=True)
class Conversation:
    user: User
    last_message: Message
    unread_count: int

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "Conversation":
        return cls(
            user=User.from_json(data["user"]),
            last_message=Message.from_json(data["last_message"]),
            unread_count=int(data.get("unread_count", 0)),
        )


def _page_number(link: str | None) -> int | None:
    """Page number from a DRF `next`/`previous` link (page 1 has no `page` parameter)."""
    if not link:
        return None
    values = parse_qs(urlsplit(link).query).get("page")
    return int(values[0]) if values and values[0].isdigit() else 1


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    count: int
    number: int
    next_number: int | None
    previous_number: int | None

    @classmethod
    def from_json(cls, data: dict[str, Any], parse) -> "Page[T]":
        next_number = _page_number(data.get("next"))
        previous_number = _page_number(data.get("previous"))
        if next_number is not None:
            number = next_number - 1
        elif previous_number is not None:
            number = previous_number + 1
        else:
            number = 1
        return cls(
            items=[parse(item) for item in data.get("results", [])],
            count=int(data.get("count", 0)),
            number=number,
            next_number=next_number,
            previous_number=previous_number,
        )
