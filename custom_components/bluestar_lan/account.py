"""Use the Blue Star account API only during setup or reconfiguration."""

import asyncio
import re

import aiohttp

from .protocol import numeric_value


API_ORIGIN = "https://api-smart.bluestarindia.com"
APP_HEADERS = {
    "User-Agent": "com.bluestarindia.bluesmart",
    "X-APP-VER": "v5.1.2-183",
    "X-OS-NAME": "Android",
    "X-OS-VER": "v16-36",
}
MODE_NAMES = {"cool": "cool", "heat": "heat", "dry": "dry", "fan": "fan_only",
              "auto": "auto", "aipro": "auto"}


class AccountError(Exception):
    """Blue Star could not provide the account's device inventory."""


class InvalidAuth(AccountError):
    """Blue Star rejected the credentials."""


def parse_units(response):
    """Keep units with a LAN key and a recognized climate profile."""
    if not isinstance(response, dict) or not isinstance(response.get("things"), list):
        raise AccountError("Unexpected device inventory response")
    units = {}
    for thing in response["things"]:
        if not isinstance(thing, dict):
            continue
        unit_id = thing.get("thing_id")
        user_config, model = thing.get("user_config"), thing.get("model_config")
        if not isinstance(unit_id, str) or not re.fullmatch(r"[0-9a-fA-F]{12}", unit_id):
            continue
        if not isinstance(user_config, dict) or not isinstance(model, dict):
            continue
        token = user_config.get("uat")
        if not isinstance(token, str) or not token.isascii() or len(token) < 16:
            continue
        minimum = numeric_value(model.get("min_temp"))
        maximum = numeric_value(model.get("max_temp"))
        modes = parse_modes(model.get("mode"))
        if not modes or minimum is None or maximum is None or not 10 <= minimum < maximum <= 40:
            continue
        unit_id = unit_id.lower()
        name = user_config.get("name")
        units[unit_id] = {
            "token": token,
            "name": name.strip() if isinstance(name, str) and name.strip() else "Blue Star Air Conditioner",
            "modes": modes,
            "min_temp": minimum,
            "max_temp": maximum,
            "step": 1 if numeric_value(model.get("display_digit")) in (None, 2) else 0.5,
        }
    return units


def parse_modes(profile):
    if not isinstance(profile, dict):
        return {}
    modes = {}
    for code, attributes in profile.items():
        if not isinstance(attributes, dict) or not isinstance(attributes.get("name"), str):
            continue
        mode = MODE_NAMES.get(attributes["name"].strip().lower())
        if mode is not None and isinstance(code, str) and code.isascii() and code.isdecimal():
            modes.setdefault(mode, int(code))
    return modes


async def fetch_units(client, username, password):
    """Sign in over HTTPS and return the supported units without the session."""
    try:
        async with client.post(
            f"{API_ORIGIN}/auth/login",
            json={"auth_id": username, "auth_type": int(username.isdecimal()), "password": password},
            headers=APP_HEADERS, timeout=aiohttp.ClientTimeout(total=15), allow_redirects=False,
        ) as response:
            if response.status in (401, 403):
                raise InvalidAuth
            if response.status != 200:
                raise AccountError("Blue Star login endpoint returned an error")
            session = (await response.json()).get("session")
            if not isinstance(session, str) or not session:
                raise InvalidAuth
        async with client.get(
            f"{API_ORIGIN}/things", headers={**APP_HEADERS, "X-APP-SESSION": session},
            timeout=aiohttp.ClientTimeout(total=15), allow_redirects=False,
        ) as response:
            if response.status in (401, 403):
                raise InvalidAuth
            if response.status != 200:
                raise AccountError("Blue Star device inventory endpoint returned an error")
            return parse_units(await response.json())
    except (aiohttp.ClientError, asyncio.TimeoutError, AttributeError, ValueError) as error:
        raise AccountError("Could not read Blue Star account data") from error
