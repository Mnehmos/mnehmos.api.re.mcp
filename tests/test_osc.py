"""OSC decoding: the FL Studio hypothesis depends on reading UDP OSC traffic.

Real captured bytes are synthetic encodings of realistic FL-style addresses,
not recordings of real sessions (fixtures are synthetic rule).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apire import osc


def _enc_str(s: str) -> bytes:
    return s.encode("utf-8") + b"\x00" * (4 - len(s) % 4 if len(s) % 4 else 4)


def test_decode_volume_message():
    blob = _enc_str("/mixer/track/volume") + _enc_str(",if") + (127).to_bytes(4, "big") + bytes.fromhex("3f800000")
    msg = osc.decode(blob)
    assert msg["address"] == "/mixer/track/volume"
    assert msg["types"] == ",if"
    assert msg["args"] == [127, 1.0]


def test_decode_string_and_bool_tags():
    blob = _enc_str("/plugin/catalog") + _enc_str(",sTF")
    blob += _enc_str("Fruity Limiter")
    msg = osc.decode(blob)
    assert msg["args"][0] == "Fruity Limiter"
    assert msg["types"] == ",sTF"


def test_garbage_is_none_not_a_crash():
    assert osc.decode(b"") is None
    assert osc.decode(b"\xff\xff\xff\xff garbage") is None
    assert osc.decode(_enc_str("/no/tags")) is None


def test_frame_from_osc_message():
    frame = osc.frame_from_message(
        osc.decode(_enc_str("/mixer/track/volume") + _enc_str(",f") + bytes.fromhex("3f000000")),
        channel="osc:127.0.0.1:9000",
    )
    assert frame["kind_hint"] == "osc_message"
    assert frame["payload"]["address"] == "/mixer/track/volume"
    assert frame["payload"]["args"] == [0.5]
    assert frame["direction"] == "server_to_client"
