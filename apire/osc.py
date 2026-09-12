"""Minimal OSC 1.0 decoding.

The FL Studio hypothesis (targets/fl-studio/README.md H1) is that FL Studio's
built-in OSC server emits observable UDP traffic. This module turns OSC
datagrams into frames; it never sends anything. Decoding is total: garbage in,
None out — a malformed datagram is a dropped warning, never a crashed listener.
"""

from __future__ import annotations

import struct


def _read_blob(data: bytes, offset: int) -> tuple[bytes, int]:
    end = data.find(b"\x00", offset)
    if end < 0:
        raise ValueError("unterminated string")
    raw = data[offset:end]
    step = end - offset + 1
    pad = (4 - step % 4) % 4
    return raw, offset + step + pad


def decode(data: bytes) -> dict | None:
    """Decode one OSC message. Returns None for anything that is not one."""
    if not data or len(data) < 8:
        return None
    try:
        data = bytes(data)
        address, offset = _read_blob(data, 0)
        if not address.startswith(b"/"):
            return None
        tags_blob, offset = _read_blob(data, offset)
        if not tags_blob.startswith(b","):
            return None
        tags = tags_blob[1:].decode("ascii", errors="strict")
        args: list = []
        for tag in tags:
            if tag == "i":
                args.append(int.from_bytes(data[offset : offset + 4], "big", signed=True))
                offset += 4
            elif tag == "f":
                (val,) = struct.unpack(">f", data[offset : offset + 4])
                args.append(round(val, 6))
                offset += 4
            elif tag == "s":
                s, offset = _read_blob(data, offset)
                args.append(s.decode("utf-8", errors="replace"))
            elif tag == "b":
                n = int.from_bytes(data[offset : offset + 4], "big", signed=True)
                offset += 4
                blob = data[offset : offset + n]
                offset += n + ((4 - n % 4) % 4)
                args.append({"blob_hex": blob.hex()[:64]})
            elif tag == "T":
                args.append(True)
            elif tag == "F":
                args.append(False)
            elif tag in ("N",):
                args.append(None)
            else:
                args.append(None)
        return {"address": address.decode("utf-8", errors="replace"), "types": "," + tags, "args": args}
    except (ValueError, IndexError, struct.error):
        return None


def frame_from_message(msg: dict, channel: str) -> dict:
    """Normalize a decoded OSC message into a frame payload (pre-redaction;
    the store's redaction gate still runs on it)."""
    return {
        "kind_hint": "osc_message",
        "transport": "udp_observe",
        "direction": "server_to_client",
        "channel": channel,
        "payload": {"address": msg["address"], "types": msg["types"], "args": msg["args"]},
    }
