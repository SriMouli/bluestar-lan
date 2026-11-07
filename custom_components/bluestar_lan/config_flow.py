"""Provision LAN keys and model capabilities through Blue Star sign-in."""

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import TextSelector, TextSelectorConfig, TextSelectorType

from . import DOMAIN
from .account import AccountError, InvalidAuth, fetch_units


SIGN_IN = vol.Schema({
    vol.Required(CONF_USERNAME): TextSelector(),
    vol.Required(CONF_PASSWORD): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
})


class BlueStarLanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await self._async_sign_in("user", user_input)

    async def async_step_reconfigure(self, user_input=None):
        return await self._async_sign_in("reconfigure", user_input, self._get_reconfigure_entry())

    async def async_step_reauth(self, entry_data):
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        return await self._async_sign_in("reauth_confirm", user_input, self._get_reauth_entry())

    async def _async_sign_in(self, step_id, user_input, entry=None):
        errors = {}
        if user_input is not None:
            username = user_input[CONF_USERNAME].strip()
            password = user_input[CONF_PASSWORD]
            try:
                units = await fetch_units(async_get_clientsession(self.hass), username, password)
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except AccountError:
                errors["base"] = "cannot_connect"
            else:
                if not units:
                    errors["base"] = "no_supported_units"
                elif entry is None:
                    return self.async_create_entry(title="Blue Star LAN", data={"units": units})
                elif not units.keys() & entry.data["units"].keys():
                    errors["base"] = "different_account"
                else:
                    return self.async_update_reload_and_abort(entry, data={"units": units})
        return self.async_show_form(step_id=step_id, data_schema=SIGN_IN, errors=errors)
