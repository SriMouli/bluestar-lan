"""Exercise capability mapping and multi-unit routing with synthetic frames."""

import asyncio
import base64
import json
import unittest

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from custom_components.bluestar_lan.account import parse_units
from custom_components.bluestar_lan.lan import LanClient


FIRST = "001122334455"
SECOND = "aabbccddeeff"
TOKEN_A = "0123456789abcdef-test-unit-a"
TOKEN_B = "fedcba9876543210-test-unit-b"


def thing(unit_id, token, mode_code, mode_name):
    return {
        "thing_id": unit_id,
        "user_config": {"name": "Test AC", "uat": token},
        "model_config": {
            "mode": {str(mode_code): {"name": mode_name}},
            "min_temp": 16,
            "max_temp": 30,
            "display_digit": 2,
        },
    }


def packet(unit_id, token, timestamp, temperature=24):
    status = {"ts": timestamp, "pow": 1, "mode": 2, "stemp": str(temperature),
              "ctemp": "27.5", "displayunit": 0}
    iv = bytes(range(16))
    padder = padding.PKCS7(128).padder()
    body = padder.update(json.dumps(status).encode()) + padder.finalize()
    cipher = Cipher(algorithms.AES(token[:16].encode()), modes.CBC(iv)).encryptor()
    encrypted = base64.b64encode(iv + cipher.update(body) + cipher.finalize())
    return b"(" + unit_id.encode() + b"|" + encrypted + b")"


class AccountTest(unittest.TestCase):
    def test_capabilities_come_from_each_model_and_exclude_unusable_units(self):
        units = parse_units({"things": [
            thing(FIRST.upper(), TOKEN_A, 2, "cool"),
            thing(SECOND, TOKEN_B, 8, "heat"),
            thing("123456abcdef", "", 1, "heat"),
        ]})
        self.assertEqual(set(units), {FIRST, SECOND})
        self.assertEqual(units[FIRST]["modes"], {"cool": 2})
        self.assertEqual(units[SECOND]["modes"], {"heat": 8})
        self.assertEqual(units[FIRST]["step"], 1)


class LanTest(unittest.IsolatedAsyncioTestCase):
    async def test_tracks_units_separately_and_relearns_ip_from_fresh_status(self):
        client = LanClient({FIRST: {"token": TOKEN_A}, SECOND: {"token": TOKEN_B}})
        self.addCleanup(client.close)
        seen = []
        client.subscribe(FIRST, lambda: seen.append(client.units[FIRST].state["stemp"]))
        client.receive(packet(FIRST, TOKEN_A, 10), "192.0.2.1")
        client.receive(packet(SECOND, TOKEN_B, 10), "192.0.2.2")
        client.receive(packet(FIRST, TOKEN_A, 9, 25), "192.0.2.5")
        client.receive(packet(FIRST, TOKEN_B, 11, 25), "192.0.2.5")
        self.assertEqual(client.units[FIRST].host, "192.0.2.1")
        client.receive(packet(FIRST, TOKEN_A, 11, 23), "192.0.2.9")
        self.assertEqual(client.units[FIRST].host, "192.0.2.9")
        self.assertEqual(client.units[SECOND].host, "192.0.2.2")
        self.assertEqual(seen, [24, 23])

    async def test_unavailable_units_do_not_send_commands(self):
        client = LanClient({FIRST: {"token": TOKEN_A}})
        self.addCleanup(client.close)
        with self.assertRaisesRegex(RuntimeError, "No recent"):
            await asyncio.wait_for(client.command(FIRST, {"pow": 0}, {"pow": 0}), 1)
