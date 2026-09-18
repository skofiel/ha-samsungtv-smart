"""Bug 1: 2025 Frame reports REST PowerState=standby while Art Mode is ON."""


async def test_in_artmode_true_when_rest_standby_but_artws_on(art_client, monkeypatch):
    # REST says the TV is off/standby (the live bug on TQ50LS03FAUXXC)...
    async def fake_on():
        return False

    # ...but the Art WebSocket authoritatively reports art mode on.
    async def fake_get_artmode():
        return "on"

    monkeypatch.setattr(art_client, "on", fake_on)
    monkeypatch.setattr(art_client, "get_artmode", fake_get_artmode)

    assert await art_client.in_artmode() is True


async def test_in_artmode_true_when_rest_on(art_client, monkeypatch):
    async def fake_on():
        return True

    async def fake_get_artmode():
        return "off"

    monkeypatch.setattr(art_client, "on", fake_on)
    monkeypatch.setattr(art_client, "get_artmode", fake_get_artmode)

    assert await art_client.in_artmode() is True


async def test_in_artmode_false_when_both_off(art_client, monkeypatch):
    async def fake_on():
        return False

    async def fake_get_artmode():
        return "off"

    monkeypatch.setattr(art_client, "on", fake_on)
    monkeypatch.setattr(art_client, "get_artmode", fake_get_artmode)

    assert await art_client.in_artmode() is False
