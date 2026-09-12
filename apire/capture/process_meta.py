"""Process / module / socket metadata listener (read-only psutil snapshot).

This is the FL Studio inventory instrument: what processes exist, what they
are, what is listening where, what modules the DAW and its plugin bridges
load. Pure snapshot — it does not inject, suspend, or alter anything.

Granularity matters for differential work: alongside the bulk summary frames
(one process_inventory for architecture projections), the listener emits one
frame per *entity* — process_present, module_loaded, socket_listening,
connection — so the correlator's canonical keys can say "FL64.exe appeared
only in captures where FL Studio was running" instead of "a process list
appeared again".
"""

from __future__ import annotations

import os

import psutil

from ..errors import TransportError

_MAX_MODULE_ENTRIES = 400
_MAX_CONNECTIONS = 600
_MAX_PER_ENTITY = 900


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:
        return default


def _basename(path: str) -> str:
    return os.path.basename(path).lower() if path else ""


class ProcessMetaListener:
    transport = "process_meta"
    # v1 emitted summary frames only; v2 adds per-entity frames
    # (process_present / module_loaded / socket_listening / connection).
    # Captures taken under different versions are NOT comparable: the
    # correlator warns when they are mixed.
    version = 2

    def __init__(self):
        self._done = False
        self._stats = {"frames": 0, "processes": 0, "sockets": 0, "connections": 0, "module_scans": 0, "modules": 0}

    def start(self, store, capture_id: str, hint: str = "", **_) -> dict:
        if self._done:
            raise TransportError("process_meta is a one-shot snapshot; start a new capture for another")

        frames: list[dict] = []

        # --- processes: summary + one frame per entity
        processes = []
        for proc in psutil.process_iter(["pid", "ppid", "name", "exe"]):
            info = proc.info
            processes.append(
                {"pid": info["pid"], "ppid": info["ppid"], "name": info["name"] or "", "exe": info["exe"] or ""}
            )
        self._stats["processes"] = len(processes)
        frames.append(self._meta({"event": "process_inventory", "count": len(processes), "processes": processes}))
        for p in processes[:_MAX_PER_ENTITY]:
            frames.append(
                self._meta(
                    {
                        "event": "process_present",
                        "name": p["name"],
                        "exe": p["exe"],
                        "pid": p["pid"],
                        "ppid": p["ppid"],
                    }
                )
            )

        # --- inet connections: listening and established (pid attribution
        # needs elevation for other users' processes; degradation is a warning)
        listening, established, udp_count = [], [], 0
        try:
            for conn in psutil.net_connections(kind="inet"):
                pid = conn.pid or 0
                name = _safe(lambda: psutil.Process(pid).name(), "") if pid else ""
                laddr = f"{conn.laddr.ip}:{conn.laddr.port}" if conn.laddr else ""
                raddr = f"{conn.raddr.ip}:{conn.raddr.port}" if conn.raddr else ""
                proto = "udp" if conn.type == 2 else "tcp"
                if proto == "udp":
                    udp_count += 1
                    continue
                if conn.status == psutil.CONN_LISTEN:
                    entry = {"proto": proto, "local": laddr, "pid": pid, "process": name}
                    listening.append(entry)
                    frames.append(self._meta({"event": "socket_listening", **entry}))
                elif raddr and conn.status == psutil.CONN_ESTABLISHED:
                    entry = {
                        "proto": proto,
                        "local_port": conn.laddr.port if conn.laddr else 0,
                        "remote": raddr,
                        "remote_port": conn.raddr.port if conn.raddr else 0,
                        "pid": pid,
                        "process": name,
                    }
                    established.append(entry)
                    frames.append(self._meta({"event": "connection", **entry}))
                    if len(established) >= _MAX_CONNECTIONS:
                        break
        except psutil.AccessDenied:
            frames.append(
                self._meta(
                    {
                        "event": "listening_sockets_warning",
                        "detail": "system-wide socket table denied; run elevated for pid attribution",
                    }
                )
            )
        self._stats["sockets"] = len(listening)
        self._stats["connections"] = len(established)
        frames.append(
            self._meta(
                {
                    "event": "listening_sockets",
                    "count": len(listening),
                    "sockets": listening,
                    "established_count": len(established),
                    "udp_datagram_sockets": udp_count,
                }
            )
        )

        # --- modules for hinted processes (the DAW and its bridges)
        targets = [p for p in processes if not hint or hint.lower() in (p["name"] or "").lower()]
        for proc_info in targets[:12]:
            try:
                proc = psutil.Process(proc_info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
            maps = _safe(lambda: proc.memory_maps(), []) or []
            modules = sorted({m.path for m in maps if m.path})
            self._stats["module_scans"] += 1
            self._stats["modules"] += len(modules)
            frames.append(
                self._meta(
                    {
                        "event": "module_scan",
                        "pid": proc_info["pid"],
                        "process": proc_info["name"],
                        "module_count": len(modules),
                        "modules": modules[:_MAX_MODULE_ENTRIES],
                        "truncated": len(modules) > _MAX_MODULE_ENTRIES,
                    }
                )
            )
            for module in modules[:_MAX_MODULE_ENTRIES]:
                frames.append(
                    self._meta(
                        {"event": "module_loaded", "process": proc_info["name"], "module": _basename(module), "path": module}
                    )
                )

        store.append_frames(capture_id, frames)
        self._stats["frames"] = len(frames)
        self._done = True
        return {**self._stats, "one_shot": True}

    @staticmethod
    def _meta(payload: dict) -> dict:
        return {"kind_hint": "process_meta", "transport": "process_meta", "payload": payload}

    def stop(self) -> dict:
        return dict(self._stats)

    def status(self) -> dict:
        return {**self._stats, "listening": False, "one_shot": True}
