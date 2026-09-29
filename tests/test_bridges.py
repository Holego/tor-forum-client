import pytest

from torforum.bridges import SNOWFLAKE_BRIDGES, BridgeError, ConnectionMode, bridges_for, parse_bridge_lines

OBFS4 = "obfs4 192.0.2.10:443 0123456789ABCDEF0123456789ABCDEF01234567 cert=AAAA iat-mode=0"
WEBTUNNEL = (
    "webtunnel [2001:db8::1]:443 0123456789ABCDEF0123456789ABCDEF01234567 url=https://example.com/x ver=0.0.1"
)


def test_parses_obfs4_webtunnel_and_torrc_style_lines():
    text = f"\n# from the bot\nBridge {OBFS4}\n  {WEBTUNNEL}  \n\n"
    assert parse_bridge_lines(text) == [OBFS4, WEBTUNNEL]


def test_vanilla_bridge_without_transport():
    line = "192.0.2.20:9001 0123456789ABCDEF0123456789ABCDEF01234567"
    assert parse_bridge_lines(line) == [line]


def test_meek_without_fingerprint_is_fine():
    line = "meek_lite 192.0.2.20:80 url=https://example.cdn77.org front=www.example.com"
    assert parse_bridge_lines(line) == [line]


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("scramblesuit 192.0.2.1:443 AAAA", "неизвестный тип"),
        ("obfs4 not-an-address cert=x", "нет адреса"),
        ("obfs4 192.0.2.10:443 cert=AAAA", "нет отпечатка"),
        (f"{OBFS4}\nhello", "Строка 2"),
    ],
)
def test_bad_lines_are_reported_with_line_number(text, message):
    with pytest.raises(BridgeError, match=message):
        parse_bridge_lines(text)


def test_bridges_for_each_mode():
    assert bridges_for(ConnectionMode.DIRECT, [OBFS4]) == []
    assert bridges_for(ConnectionMode.AUTO, [OBFS4]) == []
    assert bridges_for(ConnectionMode.CUSTOM, [OBFS4]) == [OBFS4]
    assert bridges_for(ConnectionMode.SNOWFLAKE, []) == SNOWFLAKE_BRIDGES


def test_builtin_snowflake_lines_pass_our_own_validation():
    assert parse_bridge_lines("\n".join(SNOWFLAKE_BRIDGES)) == SNOWFLAKE_BRIDGES
