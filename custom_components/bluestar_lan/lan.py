"""Listen once for all registered ACs and confirm commands from fresh status."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import socket
import time

from .protocol import LAN_PORT, decode_status, encode_command, split_frame


STALE_AFTER = 15
COMMAND_TIMEOUT = 10


@dataclass
class UnitState:
    token: str = field(repr=False)
    host: str | None = None
    state: dict = field(default_factory=dict)
    expiry: asyncio.TimerHandle | None = None
    listeners: list = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    pending: tuple | None = None

    @property
    def available(self):
        return self.expiry is not None and self.state.get("displayunit") == 0

    def notify(self):
        for listener in tuple(self.listeners):
            listener()

    def expire(self):
        self.expiry = None
        self.notify()


class LanClient(asyncio.DatagramProtocol):
    def __init__(self, units):
        self.units = {unit_id: UnitState(profile["token"]) for unit_id, profile in units.items()}
        self.transport = None
        self.closed = False
        self.socket_closed = asyncio.Event()

    async def start(self):
        self.transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            lambda: self, local_addr=("0.0.0.0", LAN_PORT),
        )

    def close(self):
        self.closed = True
        if self.transport is not None:
            self.transport.close()
        for unit in self.units.values():
            if unit.expiry is not None:
                unit.expiry.cancel()
                unit.expiry = None
            if unit.pending is not None:
                unit.pending[2].cancel()

    async def stop(self):
        """Wait until asyncio has released the port before an entry reload."""
        self.close()
        if self.transport is not None:
            await self.socket_closed.wait()

    def connection_lost(self, exc):
        self.socket_closed.set()

    def subscribe(self, unit_id, listener):
        listeners = self.units[unit_id].listeners
        listeners.append(listener)
        return lambda: listeners.remove(listener)

    def datagram_received(self, data, address):
        self.receive(data, address[0])

    def receive(self, packet, host):
        if self.closed or len(packet) > 4096:
            return
        try:
            unit_id, ciphertext = split_frame(packet)
            unit = self.units[unit_id.lower()]
            state = decode_status(ciphertext, unit.token)
        except (KeyError, ValueError, OverflowError):
            return
        timestamp = state["ts"]
        if unit.state and timestamp <= unit.state["ts"]:
            return
        unit.host = host
        unit.state = state
        if unit.expiry is not None:
            unit.expiry.cancel()
        loop = asyncio.get_running_loop()
        unit.expiry = loop.call_later(STALE_AFTER, unit.expire)
        if unit.pending is not None:
            since, expected, response = unit.pending
            if (timestamp >= since and not response.done()
                    and all(state.get(key) == value for key, value in expected.items())):
                response.set_result(None)
        unit.notify()

    async def command(self, unit_id, changes, expected):
        unit = self.units[unit_id]
        async with unit.lock:
            if self.closed or not unit.available or unit.host is None:
                raise RuntimeError("No recent Celsius status from the AC")
            if all(unit.state.get(key) == value for key, value in expected.items()):
                return
            loop = asyncio.get_running_loop()
            timestamp = time.time_ns() // 1_000_000
            response = loop.create_future()
            unit.pending = (timestamp, expected, response)
            try:
                wire = encode_command(unit.token, changes, timestamp)
                with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sender:
                    sender.setblocking(False)
                    for _ in range(25):
                        if response.done():
                            break
                        await loop.sock_sendto(sender, wire, (unit.host, LAN_PORT))
                        await asyncio.sleep(0.1)
                await asyncio.wait_for(response, COMMAND_TIMEOUT)
            except (TimeoutError, asyncio.TimeoutError) as error:
                raise RuntimeError("AC did not report the requested state") from error
            except OSError as error:
                raise RuntimeError("Could not send command to AC") from error
            finally:
                unit.pending = None
                if not response.done():
                    response.cancel()
