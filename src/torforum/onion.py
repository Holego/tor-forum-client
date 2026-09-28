"""Parsing and validating forum addresses, with extra care for v3 onion addresses."""

import base64
import binascii
import hashlib
import ipaddress
import re
from urllib.parse import urlsplit

ONION_V3_LABEL = re.compile(r"^[a-z2-7]{56}$")
LOCAL_HOSTS = {"localhost"}


class AddressError(ValueError):
    """The text the user entered can't be used as a forum address."""


def onion_problem(host: str) -> str | None:
    """Why ``host`` isn't a usable v3 onion address (short, for a form field), or None if it is.

    Also verifies the checksum built into v3 addresses, which catches typos.
    Layout (rend-spec-v3): base32(pubkey[32] | checksum[2] | version[1]) + ".onion",
    checksum = SHA3-256(".onion checksum" | pubkey | version)[:2], version = 3.
    """
    host = host.lower()
    if not host.endswith(".onion"):
        return "Это не .onion-адрес"
    label = host.removesuffix(".onion").rsplit(".", 1)[-1]  # allow subdomains like www.<addr>.onion
    if len(label) == 16:
        return "v2-адреса больше не работают"
    if not ONION_V3_LABEL.match(label):
        return "Нужно 56 символов: a–z и 2–7"
    try:
        raw = base64.b32decode(label.upper())
    except binascii.Error:
        return "Нужно 56 символов: a–z и 2–7"
    pubkey, checksum, version = raw[:32], raw[32:34], raw[34:]
    if version != b"\x03" or hashlib.sha3_256(b".onion checksum" + pubkey + version).digest()[:2] != checksum:
        return "Опечатка в .onion-адресе"
    return None


def is_valid_onion_v3(host: str) -> bool:
    return onion_problem(host) is None


def is_local_host(host: str) -> bool:
    """True for this device itself, e.g. a forum you run locally while developing."""
    host = host.lower().strip("[]")
    if host in LOCAL_HOSTS:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def normalize_address(text: str) -> str:
    """Turn whatever the user pasted into a base URL like ``http://<56 chars>.onion``.

    Accepts bare hosts, full URLs with paths, stray whitespace and upper case.
    Onion services are plain ``http`` (Tor already encrypts end to end);
    other hosts default to ``https``, except this device itself.
    """
    text = text.strip()
    if not text:
        raise AddressError("Введите адрес форума")
    explicit_scheme = "://" in text
    parts = urlsplit(text if explicit_scheme else "http://" + text)
    if parts.scheme not in ("http", "https"):
        raise AddressError("Поддерживаются только адреса http:// и https://")
    host = (parts.hostname or "").lower()
    if not host or ("." not in host and not is_local_host(host)):
        raise AddressError("Не похоже на адрес сайта")

    if host.endswith(".onion") and (problem := onion_problem(host)):
        raise AddressError(problem)
    keep_scheme = explicit_scheme or host.endswith(".onion") or is_local_host(host)
    scheme = parts.scheme if keep_scheme else "https"

    try:
        port = f":{parts.port}" if parts.port else ""
    except ValueError as e:
        raise AddressError("Неверный номер порта") from e
    display_host = f"[{host}]" if ":" in host else host
    return f"{scheme}://{display_host}{port}"


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def short_host(url: str) -> str:
    """``abcdefgh…wxyz.onion`` — enough to recognise an address at a glance."""
    host = host_of(url)
    if host.endswith(".onion"):
        label = host.removesuffix(".onion")
        if len(label) > 16:
            return f"{label[:8]}…{label[-6:]}.onion"
    return host
