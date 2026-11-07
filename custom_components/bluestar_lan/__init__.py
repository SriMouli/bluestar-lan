"""Blue Star LAN integration and standalone client."""

from .lan import LanClient

DOMAIN = "bluestar_lan"


async def async_setup_entry(hass, entry):
    """Open the local listener from the saved unit inventory."""
    from homeassistant.const import Platform
    from homeassistant.exceptions import ConfigEntryNotReady

    client = LanClient(entry.data["units"])
    try:
        await client.start()
    except OSError as error:
        raise ConfigEntryNotReady("Could not bind the Blue Star LAN listener on UDP 44542") from error
    entry.runtime_data = client
    entry.async_on_unload(client.stop)
    await hass.config_entries.async_forward_entry_setups(entry, [Platform.CLIMATE])
    return True


async def async_unload_entry(hass, entry):
    """Remove the climate platform before releasing the listener."""
    from homeassistant.const import Platform

    return await hass.config_entries.async_unload_platforms(entry, [Platform.CLIMATE])
