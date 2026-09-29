import pytest

from torforum.bridges import SNOWFLAKE_BRIDGES, ConnectionMode
from torforum.embedded import BootstrapStatus, EmbeddedTor, EmbeddedTorError


def phase(progress, tag, summary="x", warning=None):
    text = f'NOTICE BOOTSTRAP PROGRESS={progress} TAG={tag} SUMMARY="{summary}"'
    if warning:
        text = text.replace("NOTICE", "WARN") + f' WARNING="{warning}" REASON=TIMEOUT'
    return text


class FakeTor:
    """Scripted TorManager: each status() call returns the next phase."""

    def __init__(self, phases, port=9050, error=None):
        self.phases = list(phases)
        self.port = port
        self.error = error
        self.started_with = []

    async def start(self, bridges):
        self.started_with.append(bridges)

    async def status(self):
        current = self.phases.pop(0) if len(self.phases) > 1 else self.phases[0]
        return {"running": True, "phase": current, "socks_port": self.port, "error": self.error}


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    async def sleep(self, seconds):
        self.now += seconds


def make(tor):
    clock = FakeClock()
    return EmbeddedTor(tor, clock=clock, sleep=clock.sleep)


def test_parses_bootstrap_phase():
    status = BootstrapStatus.from_backend(
        {"phase": phase(50, "loading_descriptors", "Loading relay descriptors"), "socks_port": 9050}
    )
    assert (status.progress, status.tag, status.summary) == (
        50,
        "loading_descriptors",
        "Loading relay descriptors",
    )
    assert status.phase_name == "Загрузка списка узлов"
    assert not status.ready


def test_parses_warnings_and_exit_circuit_phases():
    status = BootstrapStatus.from_backend(
        {"phase": phase(5, "ap_conn", "Connecting", warning="Connection timed out"), "socks_port": -1}
    )
    assert status.warning == "Connection timed out"
    assert status.phase_name == "Подключение к сети Tor"
    assert status.socks_port is None


def test_missing_phase_means_starting():
    status = BootstrapStatus.from_backend({"running": False, "phase": None, "socks_port": -1})
    assert (status.progress, status.phase_name) == (0, "Запуск Tor")


async def test_direct_connection_returns_port_when_done():
    tor = FakeTor([phase(10, "conn_done"), phase(50, "loading_descriptors"), phase(100, "done")], port=9150)
    seen = []
    port = await make(tor).connect(ConnectionMode.DIRECT, [], lambda s, m: seen.append((s.progress, m)))
    assert port == 9150
    assert tor.started_with == [[]]
    assert seen[-1] == (100, ConnectionMode.DIRECT)


async def test_auto_falls_back_to_snowflake_when_direct_is_blocked():
    tor = FakeTor([phase(5, "conn")] * 45 + [phase(100, "done")])
    modes = []
    await make(tor).connect(ConnectionMode.AUTO, [], lambda s, m: modes.append(m))
    assert tor.started_with == [[], SNOWFLAKE_BRIDGES]
    assert modes[0] == ConnectionMode.DIRECT and modes[-1] == ConnectionMode.SNOWFLAKE


async def test_auto_keeps_a_slow_but_working_direct_connection():
    tor = FakeTor([phase(5, "conn")] * 10 + [phase(40, "loading_keys")] * 60 + [phase(100, "done")])
    await make(tor).connect(ConnectionMode.AUTO, [], lambda s, m: None)
    assert tor.started_with == [[]]


async def test_explicit_direct_mode_never_switches():
    tor = FakeTor([phase(5, "conn")] * 100 + [phase(100, "done")])
    await make(tor).connect(ConnectionMode.DIRECT, [], lambda s, m: None)
    assert tor.started_with == [[]]


async def test_custom_bridges_are_passed_through():
    bridges = ["obfs4 192.0.2.10:443 0123456789ABCDEF0123456789ABCDEF01234567 cert=A iat-mode=0"]
    tor = FakeTor([phase(100, "done")])
    await make(tor).connect(ConnectionMode.CUSTOM, bridges, lambda s, m: None)
    assert tor.started_with == [bridges]


async def test_backend_error_is_raised():
    tor = FakeTor([None], error="Cannot bind TorService")
    with pytest.raises(EmbeddedTorError, match="bind"):
        await make(tor).connect(ConnectionMode.DIRECT, [], lambda s, m: None)


async def test_async_status_callback_is_awaited():
    tor = FakeTor([phase(100, "done")])
    calls = []

    async def on_status(status, mode):
        calls.append(status.progress)

    await make(tor).connect(ConnectionMode.DIRECT, [], on_status)
    assert calls == [100]
