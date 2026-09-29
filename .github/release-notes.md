Tor Forum is a Python client for forums hosted on Tor. Tor is built into the app — no Orbot or Tor Browser
needed — and it can connect through Snowflake or your own obfs4/WebTunnel bridges where Tor is blocked.

**Which file to download**

| File | For |
|---|---|
| `tor-forum-client-arm64-v8a.apk` | almost all phones from the last ~8 years |
| `tor-forum-client-armeabi-v7a.apk` | older 32-bit phones |
| `tor-forum-client-x86_64.apk` | emulators and x86 devices |

Open the app and it connects to Tor by itself (the first start takes up to a minute). If Tor is blocked
where you are, pick Snowflake or paste bridges from @GetBridgesBot under *Подключение к Tor*.

Every build is checked in CI: tests, then the APK is installed on an Android emulator and must reach
`Bootstrapped 100%` through the built-in Tor.
