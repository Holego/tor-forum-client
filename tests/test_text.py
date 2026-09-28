from datetime import UTC, datetime, timedelta, timezone

import pytest

from torforum.text import Segment, plural, relative_time, split_links

TZ = timezone(timedelta(hours=5))
NOW = datetime(2026, 9, 28, 15, 30, tzinfo=TZ)


def test_split_links():
    assert split_links("см. https://x.com/a.gif, круто") == [
        Segment("см. "),
        Segment("https://x.com/a.gif", url="https://x.com/a.gif"),
        Segment(", круто"),
    ]


def test_split_links_without_links():
    assert split_links("просто текст") == [Segment("просто текст")]
    assert split_links("") == []


@pytest.mark.parametrize(
    ("moment", "expected"),
    [
        (NOW - timedelta(seconds=10), "только что"),
        (NOW - timedelta(minutes=5), "5 мин назад"),
        (NOW - timedelta(hours=3), "сегодня 12:30"),
        (NOW - timedelta(days=1), "вчера 15:30"),
        (datetime(2026, 9, 3, 10, 0, tzinfo=TZ), "3 сен"),
        (datetime(2025, 1, 15, 10, 0, tzinfo=TZ), "15 янв 2025"),
    ],
)
def test_relative_time(moment, expected):
    assert relative_time(moment, NOW) == expected


def test_relative_time_converts_timezones():
    utc_moment = datetime(2026, 9, 28, 7, 0, tzinfo=UTC)  # 12:00 at UTC+5
    assert relative_time(utc_moment, NOW) == "сегодня 12:00"


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (1, "1 ответ"),
        (2, "2 ответа"),
        (5, "5 ответов"),
        (11, "11 ответов"),
        (21, "21 ответ"),
        (112, "112 ответов"),
    ],
)
def test_plural(n, expected):
    assert plural(n, "ответ", "ответа", "ответов") == expected
