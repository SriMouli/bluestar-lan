"""Create one native climate entity per provisioned unit."""

from homeassistant.components.climate import ClimateEntity, ClimateEntityFeature, HVACMode
from homeassistant.components.climate.const import ATTR_HVAC_MODE
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo

from . import DOMAIN
from .protocol import setpoint_command


PARALLEL_UPDATES = 0


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(
        BlueStarClimate(entry.runtime_data, unit_id, profile)
        for unit_id, profile in entry.data["units"].items()
    )


class BlueStarClimate(ClimateEntity):
    _attr_should_poll = False
    _attr_has_entity_name = True
    _attr_name = None
    _attr_native_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_supported_features = (
        ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.TURN_ON | ClimateEntityFeature.TURN_OFF
    )

    def __init__(self, client, unit_id, profile):
        self._client = client
        self._unit_id = unit_id
        self._unit = client.units[unit_id]
        self._codes = {HVACMode(mode): code for mode, code in profile["modes"].items()}
        self._modes = {code: mode for mode, code in self._codes.items()}
        self._attr_hvac_modes = [HVACMode.OFF, *self._codes]
        self._attr_unique_id = unit_id
        self._attr_min_temp = profile["min_temp"]
        self._attr_max_temp = profile["max_temp"]
        self._attr_target_temperature_step = profile["step"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, unit_id)}, name=profile["name"], manufacturer="Blue Star",
        )

    async def async_added_to_hass(self):
        self.async_on_remove(self._client.subscribe(self._unit_id, self.async_write_ha_state))

    @property
    def available(self):
        return self._unit.available

    @property
    def hvac_mode(self):
        state = self._unit.state
        if not state:
            return None
        return self._modes.get(state.get("mode")) if state["pow"] else HVACMode.OFF

    @property
    def native_current_temperature(self):
        return self._unit.state.get("ctemp") if self.available else None

    @property
    def native_target_temperature(self):
        return self._unit.state.get("stemp") if self.available else None

    async def async_set_temperature(self, **kwargs):
        changes, expected = {}, {}
        if (temperature := kwargs.get(ATTR_TEMPERATURE)) is not None:
            try:
                changes, expected = setpoint_command(
                    temperature, self.min_temp, self.max_temp, self.target_temperature_step,
                )
            except ValueError as error:
                raise HomeAssistantError(str(error)) from error
        if (mode := kwargs.get(ATTR_HVAC_MODE)) is not None:
            mode_changes, mode_expected = self._mode_command(mode)
            changes.update(mode_changes)
            expected.update(mode_expected)
        if changes:
            await self._async_command(changes, expected)

    async def async_set_hvac_mode(self, hvac_mode):
        await self._async_command(*self._mode_command(hvac_mode))

    def _mode_command(self, mode):
        if mode == HVACMode.OFF:
            return {"pow": 0}, {"pow": 0}
        if mode not in self._codes:
            raise HomeAssistantError("This unit does not support the requested operating mode")
        code = self._codes[mode]
        return {"pow": 1, "mode": {"value": code}}, {"pow": 1, "mode": code}

    async def async_turn_on(self):
        await self._async_command({"pow": 1}, {"pow": 1})

    async def async_turn_off(self):
        await self._async_command({"pow": 0}, {"pow": 0})

    async def _async_command(self, changes, expected):
        try:
            await self._client.command(self._unit_id, changes, expected)
        except RuntimeError as error:
            raise HomeAssistantError(str(error)) from error
