from torforum.storage import STATE_KEY, AppState, MemoryStore, SavedForum, StateRepository


async def test_first_run_has_the_preset_forum():
    state = await StateRepository(MemoryStore()).load()
    assert [f.name for f in state.forums] == ["Jo Pirat Forum"]
    assert state.forums[0].url.endswith(".onion")


async def test_roundtrip_keeps_login_and_settings():
    repo = StateRepository(MemoryStore())
    state = AppState(
        forums=[SavedForum(name="Тест", url="http://x.onion", username="me", token="t")], socks_port=9150
    )
    await repo.save(state)

    loaded = await repo.load()
    assert loaded == state
    assert loaded.forums[0].logged_in


async def test_deleting_every_forum_is_remembered():
    repo = StateRepository(MemoryStore())
    await repo.save(AppState(forums=[]))
    assert (await repo.load()).forums == []


async def test_corrupt_state_falls_back_to_first_run():
    store = MemoryStore()
    await store.set(STATE_KEY, "{not json")
    state = await StateRepository(store).load()
    assert state.forums and state.forums[0].name == "Jo Pirat Forum"


def test_lookup_helpers():
    forum = SavedForum(name="A", url="http://a.onion")
    state = AppState(forums=[forum])
    assert state.forum(forum.id) is forum
    assert state.find_by_url("http://a.onion") is forum
    assert state.forum("nope") is None


async def test_connection_settings_roundtrip_and_old_state_gets_defaults():
    repo = StateRepository(MemoryStore())
    bridge = "obfs4 192.0.2.10:443 0123456789ABCDEF0123456789ABCDEF01234567 cert=A iat-mode=0"
    await repo.save(AppState(forums=[], connection_mode="custom", custom_bridges=[bridge]))
    loaded = await repo.load()
    assert (loaded.connection_mode, loaded.custom_bridges) == ("custom", [bridge])

    store = MemoryStore()
    await store.set(STATE_KEY, '{"forums": [], "socks_port": null}')  # saved by version 0.1
    old = await StateRepository(store).load()
    assert (old.connection_mode, old.custom_bridges) == ("auto", [])


async def test_unknown_mode_falls_back_to_auto():
    store = MemoryStore()
    await store.set(STATE_KEY, '{"forums": [], "connection_mode": "teleport"}')
    assert (await StateRepository(store).load()).connection_mode == "auto"
