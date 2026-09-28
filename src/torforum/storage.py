"""Saved forums and settings, persisted as one JSON document in a key-value store."""

import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Protocol

from torforum.config import PRESET_FORUMS

STATE_KEY = "torforum.state.v1"


class KeyValueStore(Protocol):
    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str) -> None: ...


class MemoryStore:
    """Dict-backed store for tests and for platforms without persistent storage."""

    def __init__(self):
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> str | None:
        return self.data.get(key)

    async def set(self, key: str, value: str) -> None:
        self.data[key] = value


@dataclass
class SavedForum:
    name: str
    url: str
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    username: str | None = None
    token: str | None = None

    @property
    def logged_in(self) -> bool:
        return bool(self.token)


@dataclass
class AppState:
    forums: list[SavedForum] = field(default_factory=list)
    socks_port: int | None = None  # None = find it automatically

    def forum(self, forum_id: str) -> SavedForum | None:
        return next((f for f in self.forums if f.id == forum_id), None)

    def find_by_url(self, url: str) -> SavedForum | None:
        return next((f for f in self.forums if f.url == url), None)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> "AppState":
        data = json.loads(raw)
        forums = [SavedForum(**f) for f in data.get("forums", [])]
        return cls(forums=forums, socks_port=data.get("socks_port"))

    @classmethod
    def first_run(cls) -> "AppState":
        return cls(forums=[SavedForum(name=f["name"], url=f["url"]) for f in PRESET_FORUMS])


class StateRepository:
    def __init__(self, store: KeyValueStore):
        self.store = store

    async def load(self) -> AppState:
        raw = await self.store.get(STATE_KEY)
        if not raw:
            return AppState.first_run()
        try:
            return AppState.from_json(raw)
        except (ValueError, TypeError, KeyError):
            # Corrupt or from an incompatible version: start over rather than crash on launch.
            return AppState.first_run()

    async def save(self, state: AppState) -> None:
        await self.store.set(STATE_KEY, state.to_json())
