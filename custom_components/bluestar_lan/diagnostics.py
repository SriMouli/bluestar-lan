"""Export a small set of non-identifying fields when an owner requests diagnostics."""

from .account import MODE_NAMES


async def async_get_config_entry_diagnostics(hass, entry):
    """Describe configured capabilities and whether the LAN listener sees each unit."""
    client = getattr(entry, "runtime_data", None)
    units = []
    for unit_id, profile in entry.data["units"].items():
        unit = client.units.get(unit_id) if client is not None else None
        state = unit.state if unit is not None else {}
        units.append({
            "supported_modes": {
                mode: code for mode, code in profile["modes"].items()
                if mode in MODE_NAMES.values() and type(code) is int
            },
            "min_temp_c": profile["min_temp"],
            "max_temp_c": profile["max_temp"],
            "temperature_step_c": profile["step"],
            "available": unit is not None and unit.available,
            "received_status": bool(state),
            "reported_display_unit": {0: "celsius", 1: "fahrenheit"}.get(state.get("displayunit")),
            "reported_mode_code": state.get("mode"),
        })
    return {"units": units}
