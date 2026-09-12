"""apire stdio MCP client — the dogfooding driver.

Modes:
  tools                                  list registered tools
  call <tool> '<json args>'              one call, one server process
  run '<json list>'                      one server process, many calls
                                         [{"tool":..., "args":{...}, "delay": seconds}, ...]

`run` exists because listeners live in the server process: an observation
span (start udp listener -> human acts -> stop) needs one process to survive
the whole span.
"""

from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class Client:
    def __init__(self) -> None:
        self.p = subprocess.Popen(
            [sys.executable, str(ROOT / "server.py")],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            cwd=str(ROOT),
        )
        self.q: queue.Queue = queue.Queue()
        self.err: queue.Queue = queue.Queue()
        threading.Thread(target=self._pump, args=(self.p.stdout, self.q), daemon=True).start()
        threading.Thread(target=self._pump, args=(self.p.stderr, self.err), daemon=True).start()
        self._id = 0

    @staticmethod
    def _pump(stream, q) -> None:
        for line in stream:
            q.put(line)
        q.put(None)

    def send(self, obj: dict) -> None:
        self.p.stdin.write(json.dumps(obj) + "\n")
        self.p.stdin.flush()

    def recv(self, timeout: float = 120.0):
        try:
            line = self.q.get(timeout=timeout)
        except queue.Empty:
            return "<TIMEOUT>"
        if line is None:
            return "<STDOUT CLOSED>"
        return json.loads(line)

    def handshake(self) -> dict:
        self._id += 1
        self.send(
            {
                "jsonrpc": "2.0",
                "id": self._id,
                "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "apire-dogfood", "version": "1"}},
            }
        )
        r = self.recv()
        self.send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        return r

    def list_tools(self) -> list[str]:
        self._id += 1
        self.send({"jsonrpc": "2.0", "id": self._id, "method": "tools/list", "params": {}})
        r = self.recv()
        return [t["name"] for t in r["result"]["tools"]]

    def call(self, name: str, args: dict, timeout: float = 300.0):
        self._id += 1
        self.send({"jsonrpc": "2.0", "id": self._id, "method": "tools/call", "params": {"name": name, "arguments": args}})
        r = self.recv(timeout)
        if not isinstance(r, dict):
            return r
        if "error" in r:
            return {"mcp_error": r["error"]}
        try:
            return json.loads(r["result"]["content"][0]["text"])
        except (KeyError, IndexError, json.JSONDecodeError):
            return r

    def close(self) -> None:
        try:
            self.p.terminate()
        except OSError:
            pass


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    mode = argv[1]
    c = Client()
    c.handshake()
    try:
        if mode == "tools":
            for name in c.list_tools():
                print(name)
            return 0
        if mode == "call":
            out = c.call(argv[2], json.loads(argv[3]) if len(argv) > 3 else {})
            print(json.dumps(out, indent=1, default=str))
            return 0 if not (isinstance(out, dict) and out.get("ok") is False) else 1
        if mode == "run":
            script = json.loads(argv[2])
            failed = False
            for step in script:
                delay = float(step.get("delay", 0))
                if delay:
                    time.sleep(delay)
                out = c.call(step["tool"], step.get("args", {}))
                label = step.get("label") or f"{step['tool']}"
                print(f"===== {label} =====")
                print(json.dumps(out, indent=1, default=str))
                if isinstance(out, dict) and out.get("ok") is False:
                    failed = True
            return 1 if failed else 0
        print(f"unknown mode '{mode}'")
        return 2
    finally:
        c.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
