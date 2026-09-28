"""App-wide constants."""

from torforum import __version__

APP_NAME = "Tor Forum Client"
USER_AGENT = f"TorForumClient/{__version__}"

# Where a Tor SOCKS proxy usually listens: Orbot / the tor daemon, then Tor Browser (desktop).
DEFAULT_SOCKS_PORTS = (9050, 9150)
SOCKS_HOST = "127.0.0.1"

# Forums added to the list on first launch.
PRESET_FORUMS = [
    {
        "name": "Jo Pirat Forum",
        "url": "http://zd6yotzjhndh5u26oc6ya6ygw4nrmtruyezxbfeyvkbqdgc63qnfugid.onion",
    },
]

# Onion circuits take a while to build, so be generous.
CONNECT_TIMEOUT = 90.0
READ_TIMEOUT = 90.0

MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_CACHE_BYTES = 48 * 1024 * 1024

ORBOT_URL = "https://orbot.app/"
ORBOT_FDROID_URL = "https://f-droid.org/packages/org.torproject.android/"
