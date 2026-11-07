"""Ensure diagnostics export only the data needed to diagnose LAN setup."""

import json
from types import SimpleNamespace
import unittest

from custom_components.bluestar_lan.diagnostics import async_get_config_entry_diagnostics


class DiagnosticsTest(unittest.IsolatedAsyncioTestCase):
    async def test_export_excludes_identifiers_and_credentials(self):
        profile = {"token": "fixture-token", "name": "fixture-household-name", "modes": {"cool": 2},
                   "min_temp": 16, "max_temp": 30, "step": 1}
        entry = SimpleNamespace(
            data={"units": {"fixture-unit-id": profile}, "password": "fixture-password"},
            runtime_data=SimpleNamespace(units={"fixture-unit-id": SimpleNamespace(
                host="192.0.2.10", available=True,
                state={"ts": 12345, "displayunit": 0, "mode": 2, "ctemp": 27.5},
            )}),
        )
        result = await async_get_config_entry_diagnostics(None, entry)
        self.assertEqual(result, {"units": [{
            "supported_modes": {"cool": 2}, "min_temp_c": 16, "max_temp_c": 30,
            "temperature_step_c": 1, "available": True, "received_status": True,
            "reported_display_unit": "celsius", "reported_mode_code": 2,
        }]})
        for private_value in ("fixture-token", "fixture-household-name", "fixture-unit-id",
                              "fixture-password", "192.0.2.10", "12345", "27.5"):
            self.assertNotIn(private_value, json.dumps(result))

    async def test_export_works_without_a_loaded_lan_client(self):
        entry = SimpleNamespace(data={"units": {"fixture-id": {
            "modes": {"cool": 2}, "min_temp": 16, "max_temp": 30, "step": 1,
        }}})
        unit = (await async_get_config_entry_diagnostics(None, entry))["units"][0]
        self.assertFalse(unit["available"])
        self.assertFalse(unit["received_status"])
        self.assertIsNone(unit["reported_display_unit"])
