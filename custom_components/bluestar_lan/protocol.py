"""Blue Star LAN status and command wire format."""

import base64
import json
import math
import os

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

LAN_PORT = 44542
STATE_FIELDS = ("ts", "pow", "mode", "stemp", "ctemp", "displayunit")


def split_frame(packet):
    """Return the unit identifier and encoded encrypted state."""
    frame = packet.strip().decode("ascii")
    if not frame.startswith("(") or not frame.endswith(")"):
        raise ValueError("Invalid status envelope")
    unit_id, delimiter, ciphertext = frame[1:-1].partition("|")
    if not delimiter or not unit_id or not ciphertext or "|" in ciphertext:
        raise ValueError("Invalid status envelope")
    return unit_id, ciphertext


def decode_status(ciphertext, unit_token):
    """Decode a status broadcast using the account's token for that unit."""
    try:
        payload = base64.b64decode(ciphertext, validate=True)
    except ValueError:
        raise ValueError("Invalid base64 in status frame") from None
    key = unit_token[:16].encode("utf-8")
    if len(key) != 16 or len(payload) < 32 or len(payload) % 16:
        raise ValueError("Invalid encrypted status frame or key")
    decryptor = Cipher(algorithms.AES(key), modes.CBC(payload[:16])).decryptor()
    plaintext = decryptor.update(payload[16:]) + decryptor.finalize()
    padding = plaintext[-1]
    if 1 <= padding <= 16 and plaintext.endswith(bytes([padding]) * padding):
        plaintext = plaintext[:-padding]
    try:
        state = json.loads(plaintext.rstrip(b"\x00").decode("ascii"))
    except ValueError:
        raise ValueError("Decrypted payload is not valid JSON") from None
    if not isinstance(state, dict):
        raise ValueError("Decrypted JSON is not a status object")
    numbers = {field: numeric_value(state.get(field)) for field in STATE_FIELDS}
    if numbers["pow"] not in (0, 1):
        raise ValueError(f"Invalid power field ({field_type(state, 'pow')})")
    for field in ("ts", "stemp"):
        if numbers[field] is None:
            raise ValueError(f"Invalid {field} field ({field_type(state, field)})")
    return {field: value for field, value in numbers.items() if value is not None}


def numeric_value(value):
    if isinstance(value, str):
        try:
            value = int(value)
        except ValueError:
            try:
                value = float(value)
            except ValueError:
                return None
    if type(value) in (int, float) and math.isfinite(value):
        return value
    return None


def field_type(state, field):
    return type(state[field]).__name__ if field in state else "missing"


def setpoint_command(temperature, minimum, maximum, step):
    """Validate a Celsius setpoint and prepare its desired and reported values."""
    if not minimum <= temperature <= maximum:
        raise ValueError("The setpoint is outside this unit's supported range")
    steps = (temperature - minimum) / step
    if not math.isclose(steps, round(steps)):
        raise ValueError("The setpoint is outside this unit's supported temperature step")
    return {"stemp": f"{temperature:.1f}"}, {"stemp": temperature}


def encode_command(unit_token, changes, timestamp):
    """Encode a desired-state patch using the app's LAN command envelope."""
    body = {
        "type": 1,
        "uat": unit_token,
        "state": {"desired": {**changes, "ts": timestamp, "src": "anlan"}},
    }
    iv = os.urandom(16)
    plaintext = iv + json.dumps(body, separators=(",", ":")).encode("ascii")
    padder = padding.PKCS7(128).padder()
    padded = padder.update(plaintext) + padder.finalize()
    encryptor = Cipher(algorithms.AES(unit_token[:16].encode("utf-8")), modes.CBC(iv)).encryptor()
    return base64.b64encode(encryptor.update(padded) + encryptor.finalize())
