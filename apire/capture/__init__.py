"""Capture transports.

This is the only package in the engine permitted to touch I/O machinery
(ADR-003): listeners *accept or observe*, they never originate
application-semantic requests. Anything not implemented raises
UnsupportedError — refusal over guessing.
"""

from __future__ import annotations

from ..errors import UnsupportedError

TRANSPORTS = {
    "file_ingest": "apire.capture.file_ingest:FileIngestListener",
    "udp_observe": "apire.capture.udp_observe:UdpObserveListener",
    "process_meta": "apire.capture.process_meta:ProcessMetaListener",
    "devtools_attach": "apire.capture.devtools_attach:DevtoolsAttachListener",
    # M2/M6: loopback passthrough proxy, named-pipe server, log tailing.
    # Registered here only with their ADR-003 review done.
    "http_proxy": None,
    "pipe_listen": None,
    "log_tail": None,
}


def create_listener(transport: str):
    target = TRANSPORTS.get(transport)
    if target is None:
        raise UnsupportedError(
            f"transport '{transport}' is not implemented yet",
            implemented=sorted(k for k, v in TRANSPORTS.items() if v),
            hint="file_ingest works today: point it at a .har or .log file",
        )
    module_name, class_name = target.split(":")
    import importlib

    module = importlib.import_module(module_name)
    return getattr(module, class_name)()
