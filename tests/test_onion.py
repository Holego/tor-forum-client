import pytest

from torforum.onion import (
    AddressError,
    is_local_host,
    is_valid_onion_v3,
    normalize_address,
    onion_problem,
    short_host,
)

ONION = "zd6yotzjhndh5u26oc6ya6ygw4nrmtruyezxbfeyvkbqdgc63qnfugid.onion"


def test_valid_v3_address_passes_checksum():
    assert is_valid_onion_v3(ONION)


def test_single_typo_is_caught_by_checksum():
    typo = ONION.replace("zd6y", "zd7y", 1)
    assert not is_valid_onion_v3(typo)
    assert onion_problem(typo) == "Опечатка в .onion-адресе"


def test_problems_are_short_enough_for_a_form_field():
    for host in ["expyuzz4wqqyqhjn.onion", "abc.onion", ONION.replace("zd6y", "zd7y", 1)]:
        problem = onion_problem(host)
        assert problem and len(problem) <= 32


@pytest.mark.parametrize(
    "host",
    [
        "short.onion",
        "expyuzz4wqqyqhjn.onion",  # old v2 addresses are no longer supported by Tor
        ONION.replace(".onion", ".com"),
        ONION[:-6] + "1.onion",  # '1' is not in base32
    ],
)
def test_invalid_onions(host):
    assert not is_valid_onion_v3(host)


@pytest.mark.parametrize(
    "raw",
    [
        ONION,
        f"  {ONION.upper()}  ",
        f"http://{ONION}",
        f"http://{ONION}/c/flood/t/1/#post-3",
        f"{ONION}/",
    ],
)
def test_pasted_onion_addresses_are_normalized(raw):
    assert normalize_address(raw) == f"http://{ONION}"


def test_https_onion_is_kept():
    assert normalize_address(f"https://{ONION}") == f"https://{ONION}"


def test_clearnet_defaults_to_https_and_local_keeps_http():
    assert normalize_address("example.com/forum") == "https://example.com"
    assert normalize_address("http://127.0.0.1:8000/") == "http://127.0.0.1:8000"
    assert normalize_address("localhost:8000") == "http://localhost:8000"


@pytest.mark.parametrize(
    "raw", ["", "   ", "ftp://example.com", "not a url", "abc.onion", "http://x.com:99999"]
)
def test_bad_addresses_raise_readable_errors(raw):
    with pytest.raises(AddressError) as err:
        normalize_address(raw)
    assert str(err.value)


def test_local_hosts():
    assert is_local_host("localhost")
    assert is_local_host("127.0.0.1")
    assert is_local_host("::1")
    assert not is_local_host(ONION)
    assert not is_local_host("192.168.1.10")


def test_short_host():
    assert short_host(f"http://{ONION}") == "zd6yotzj…nfugid.onion"
    assert short_host("https://example.com") == "example.com"
