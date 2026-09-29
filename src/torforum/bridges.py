"""Connection modes for the built-in Tor and parsing of user-supplied bridge lines."""

import re
from enum import StrEnum


class ConnectionMode(StrEnum):
    AUTO = "auto"  # direct first, Snowflake if Tor looks blocked
    DIRECT = "direct"
    SNOWFLAKE = "snowflake"
    CUSTOM = "custom"  # bridges the user got from @GetBridgesBot / bridges.torproject.org


# Official Snowflake bridge lines, as shipped in snowflake v2.14.1 (client/torrc).
SNOWFLAKE_BRIDGES = [
    "snowflake 192.0.2.3:80 2B280B23E1107BB62ABFC40DDCC8824814F80A72 "
    "fingerprint=2B280B23E1107BB62ABFC40DDCC8824814F80A72 url=https://1098762253.rsc.cdn77.org/ "
    "fronts=www.cdn77.com,www.phpmyadmin.net "
    "ice=stun:stun.antisip.com:3478,stun:stun.epygi.com:3478,stun:stun.uls.co.za:3478,"
    "stun:stun.voipgate.com:3478,stun:stun.mixvoip.com:3478,stun:stun.nextcloud.com:3478,"
    "stun:stun.bethesda.net:3478,stun:stun.nextcloud.com:443 utls-imitate=hellorandomizedalpn",
    "snowflake 192.0.2.4:80 8838024498816A039FCBBAB14E6F40A0843051FA "
    "fingerprint=8838024498816A039FCBBAB14E6F40A0843051FA url=https://1098762253.rsc.cdn77.org/ "
    "fronts=www.cdn77.com,www.phpmyadmin.net "
    "ice=stun:stun.antisip.com:3478,stun:stun.epygi.com:3478,stun:stun.uls.co.za:3478,"
    "stun:stun.voipgate.com:3478,stun:stun.mixvoip.com:3478,stun:stun.nextcloud.com:3478,"
    "stun:stun.bethesda.net:3478,stun:stun.nextcloud.com:443 utls-imitate=hellorandomizedalpn",
]

# Transports the app bundles (IPtProxy); a bridge line may also have no transport ("vanilla" bridge).
TRANSPORTS = {"obfs4", "webtunnel", "snowflake", "meek_lite"}
ADDRESS = re.compile(r"^(\d{1,3}(\.\d{1,3}){3}|\[[0-9a-fA-F:]+\]):\d{1,5}$")
FINGERPRINT = re.compile(r"^[0-9A-Fa-f]{40}$")


class BridgeError(ValueError):
    pass


def parse_bridge_lines(text: str) -> list[str]:
    """Validate pasted bridges (one per line); accepts torrc-style "Bridge ..." lines too."""
    bridges = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("bridge "):
            line = line[len("bridge ") :].strip()
        parts = line.split()
        if parts[0] in TRANSPORTS:
            address_index = 1
        elif ADDRESS.match(parts[0]):
            address_index = 0
        else:
            raise BridgeError(f"Строка {number}: неизвестный тип моста «{parts[0]}»")
        if len(parts) <= address_index or not ADDRESS.match(parts[address_index]):
            raise BridgeError(f"Строка {number}: нет адреса моста (IP:порт)")
        needs_fingerprint = address_index == 0 or parts[0] == "obfs4"
        if needs_fingerprint and (
            len(parts) <= address_index + 1 or not FINGERPRINT.match(parts[address_index + 1])
        ):
            raise BridgeError(f"Строка {number}: нет отпечатка моста (40 символов)")
        bridges.append(" ".join(parts))
    return bridges


def bridges_for(mode: ConnectionMode, custom: list[str]) -> list[str]:
    """Bridge lines to hand to Tor for a mode; an empty list means connecting directly."""
    if mode == ConnectionMode.SNOWFLAKE:
        return list(SNOWFLAKE_BRIDGES)
    if mode == ConnectionMode.CUSTOM:
        return list(custom)
    return []
