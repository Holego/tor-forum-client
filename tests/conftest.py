import pytest

JO_PIRAT = "http://zd6yotzjhndh5u26oc6ya6ygw4nrmtruyezxbfeyvkbqdgc63qnfugid.onion"
LOCAL = "http://127.0.0.1:8000"


@pytest.fixture
def onion_url() -> str:
    return JO_PIRAT
