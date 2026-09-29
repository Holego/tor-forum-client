# flet-tor

A small [Flet](https://flet.dev) extension that runs Tor inside an Android app, so users don't need
Orbot or Tor Browser.

- Tor itself: Guardian Project's [tor-android](https://github.com/guardianproject/tor-android) (`TorService`).
- Bridges: [IPtProxy](https://github.com/tladesignz/IPtProxy) (Snowflake, obfs4, WebTunnel, meek) wired in as
  `ClientTransportPlugin`s.
- Tor starts with the network disabled; bridges are applied over the control connection (`SETCONF`) and
  can be changed at runtime without restarting Tor — the same approach Tor Browser uses.

```python
from flet_tor import TorManager

tor = TorManager()
await tor.start(bridges=[])  # [] = connect directly, or pass "snowflake ..." / "obfs4 ..." lines
status = await tor.status()  # {"running", "phase", "socks_port", "error"}
```

`phase` is Tor's raw `status/bootstrap-phase`; the SOCKS port is usable once it reports `PROGRESS=100`.
Android only; on other platforms the calls raise.
