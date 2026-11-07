"""Standalone Python entry point for Blue Star LAN."""

import argparse
import asyncio
import getpass
import json
import os
from pathlib import Path
import stat
import sys

import aiohttp

from .account import AccountError, InvalidAuth, fetch_units
from .lan import LanClient
from .protocol import setpoint_command


def credentials(path):
    if path is None:
        if not sys.stdin.isatty():
            raise ValueError("Use a terminal to sign in, or supply a private credentials file")
        return input("Blue Star email or phone number: ").strip(), getpass.getpass("Blue Star password: ")
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), encoding="utf-8") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("Use a credentials file owned by you with mode 0600")
        try:
            data = json.load(source)
            username, password = data["username"], data["password"]
        except (ValueError, KeyError, TypeError):
            raise ValueError("Credentials file must contain a JSON username and password") from None
    if not isinstance(username, str) or not username.strip() or not isinstance(password, str) or not password:
        raise ValueError("Credentials file must contain a nonempty username and password")
    return username.strip(), password


async def run(args):
    username, password = credentials(args.credentials_file)
    async with aiohttp.ClientSession() as http:
        units = await fetch_units(http, username, password)
    del password
    if not units:
        raise ValueError("No supported LAN units were found in the account")
    if args.action == "list":
        for unit_id, profile in units.items():
            print(f"{unit_id}  {profile['name']}  {', '.join(profile['modes'])}")
        return
    if args.unit not in units:
        raise ValueError("Select a registered unit ID from the list command")
    client = LanClient(units)
    seen = asyncio.Event()
    unit = client.units[args.unit]
    client.subscribe(args.unit, lambda: seen.set() if unit.available else None)
    try:
        await client.start()
        await asyncio.wait_for(seen.wait(), 20)
        if args.action == "set-temperature":
            profile = units[args.unit]
            changes, expected = setpoint_command(
                args.temperature, profile["min_temp"], profile["max_temp"], profile["step"],
            )
            await client.command(args.unit, changes, expected)
        print(json.dumps(unit.state))
    finally:
        client.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials-file", type=Path, help="Private JSON with username and password")
    actions = parser.add_subparsers(dest="action", required=True)
    actions.add_parser("list", help="List supported units on your Blue Star account")
    actions.add_parser("status", help="Read a live LAN report").add_argument("unit", type=str.lower)
    set_temperature = actions.add_parser("set-temperature", help="Set the Celsius setpoint over LAN")
    set_temperature.add_argument("unit", type=str.lower)
    set_temperature.add_argument("temperature", type=float)
    args = parser.parse_args()
    try:
        asyncio.run(run(args))
    except InvalidAuth:
        parser.exit(1, "Blue Star rejected the credentials.\n")
    except AccountError:
        parser.exit(1, "Could not read the Blue Star account inventory.\n")
    except asyncio.TimeoutError:
        parser.exit(1, "No live Celsius status arrived from the selected unit.\n")
    except OSError as error:
        parser.exit(1, f"Could not open the credentials file or LAN listener (code {error.errno}).\n")
    except (ValueError, RuntimeError) as error:
        parser.exit(1, f"{error}\n")
    except KeyboardInterrupt:
        parser.exit(130)


if __name__ == "__main__":
    main()
