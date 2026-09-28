"""Formatting helpers for post text and timestamps."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

URL_RE = re.compile(r"https?://[^\s<>\"'`]+", re.IGNORECASE)
TRAILING_PUNCTUATION = ".,;:!?)]}»…"

MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]


@dataclass(frozen=True)
class Segment:
    text: str
    url: str | None = None  # set for links


def split_links(text: str) -> list[Segment]:
    """Split message text into plain pieces and links, so links can be made tappable."""
    segments: list[Segment] = []
    pos = 0
    for match in URL_RE.finditer(text):
        url = match.group(0).rstrip(TRAILING_PUNCTUATION)
        start, end = match.start(), match.start() + len(url)
        if start > pos:
            segments.append(Segment(text[pos:start]))
        segments.append(Segment(url, url=url))
        pos = end
    if pos < len(text):
        segments.append(Segment(text[pos:]))
    return segments


def relative_time(moment: datetime, now: datetime) -> str:
    """'только что', '5 мин назад', 'сегодня 14:03', 'вчера 09:15', '3 сен', '3 сен 2025'."""
    moment = moment.astimezone(now.tzinfo) if now.tzinfo else moment
    delta = now - moment
    if delta < timedelta(minutes=1):
        return "только что"
    if delta < timedelta(hours=1):
        return f"{int(delta.total_seconds() // 60)} мин назад"
    clock = moment.strftime("%H:%M")
    if moment.date() == now.date():
        return f"сегодня {clock}"
    if moment.date() == (now - timedelta(days=1)).date():
        return f"вчера {clock}"
    day = f"{moment.day} {MONTHS[moment.month - 1]}"
    return day if moment.year == now.year else f"{day} {moment.year}"


def plural(n: int, one: str, few: str, many: str) -> str:
    """Russian plural form: plural(5, 'ответ', 'ответа', 'ответов') -> '5 ответов'."""
    n_abs = abs(n)
    if n_abs % 10 == 1 and n_abs % 100 != 11:
        word = one
    elif 2 <= n_abs % 10 <= 4 and not 12 <= n_abs % 100 <= 14:
        word = few
    else:
        word = many
    return f"{n} {word}"
