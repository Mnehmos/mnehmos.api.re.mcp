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
    "http_proxy": "apire.capture.http_proxy:HttpProxyListener",
    "log_tail": "apire.capture.log_tail:LogTailListener",
}
# Named pipes have no passive listener: a pipe can only be read by its
# server, and becoming the server would require the target to be
# reconfigured (or injection). Presence and naming are observed through
# process_meta instead — see ADR-008.


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
