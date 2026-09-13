"""Operator GUI driver — the HUMAN role, automated.

apire never touches the target (Observe applications, never impersonate
them). This script is the other half of the observation protocol: the
operator's hands, moving a mouse and pressing keys exactly as the human
would. It is NOT part of the engine: nothing in apire imports it, and it
holds no capability the engine's no-egress scan guards. The observed
application still only ever sees a user at the keyboard.

Requires `pyautogui` (operator tooling only — deliberately NOT a server
dependency). `ocr.ps1` in this directory supplies perception via the
built-in Windows OCR engine for agents without vision.

Subcommands:
  windows | activate <substr> | shot <path> | click x y | dclick x y |
  rclick x y | key <name> | type <text> | drag x1 y1 x2 y2 | move x y | pos
"""

from __future__ import annotations

import ctypes
import sys
import time
from pathlib import Path

import pyautogui
import pygetwindow as gw

pyautogui.FAILSAFE = True  # slam the cursor to a corner to abort


def _windows() -> list:
    out = []
    for w in gw.getAllWindows():
        if w.visible and w.width > 100 and w.height > 100 and w.title.strip():
            out.append(w)
    return out


def cmd_windows() -> None:
    for w in sorted(_windows(), key=lambda w: -w.width * w.height):
        print(f"{w.left:>5},{w.top:>5} {w.width:>5}x{w.height:<5} {w.title[:90]}")


def cmd_activate(substr: str) -> None:
    matches = [w for w in _windows() if substr.lower() in w.title.lower()]
    if not matches:
        print(f"no window matching '{substr}'")
        return
    win = max(matches, key=lambda w: w.width * w.height)
    user32 = ctypes.windll.user32
    hwnd = win._hWnd
    try:
        if win.isMinimized:
            user32.ShowWindow(hwnd, 9)  # SW_RESTORE
            time.sleep(0.3)
    except Exception:
        pass
    # Windows foreground lock: an ALT tap releases it for SetForegroundWindow.
    pyautogui.press("alt")
    time.sleep(0.1)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.4)
    fg = user32.GetForegroundWindow()
    if fg != hwnd:
        # last resort: click the title bar strip of the target window
        pyautogui.click(win.left + win.width // 2, win.top + 6)
        time.sleep(0.3)
        fg = user32.GetForegroundWindow()
    print(f"activated: {win.title[:90]} @ {win.left},{win.top} {win.width}x{win.height} foreground={'yes' if fg == hwnd else 'NO'}")


def cmd_shot(path: str) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    pyautogui.screenshot(str(p))
    print(f"saved {p} ({p.stat().st_size} bytes)")


def cmd_do(spec_json: str) -> None:
    """One process: activate -> verify foreground -> act -> screenshot -> OCR.
    Focus is stolen back by the IDE within a second or two, so everything
    must happen without process boundaries in between."""
    import json
    import subprocess

    spec = json.loads(Path(spec_json[1:]).read_text(encoding="utf-8") if spec_json.startswith("@") else spec_json)
    user32 = ctypes.windll.user32
    target = spec.get("activate", "FL Studio")

    def foreground_ok() -> bool:
        matches = [w for w in _windows() if target.lower() in w.title.lower()]
        if not matches:
            return False
        win = max(matches, key=lambda w: w.width * w.height)
        pyautogui.press("alt")
        time.sleep(0.05)
        user32.SetForegroundWindow(win._hWnd)
        time.sleep(float(spec.get("activate_wait", 0.35)))
        return user32.GetForegroundWindow() == win._hWnd

    ok = foreground_ok()
    print(f"activate: foreground={'yes' if ok else 'NO'}")
    if not ok and not spec.get("proceed_anyway"):
        print("refusing to act without foreground; retry or set proceed_anyway")
        return

    for step in spec.get("steps", []):
        delay = float(step.get("delay", 0.6))
        time.sleep(delay)
        if "key" in step:
            pyautogui.press(step["key"])
            print(f"key {step['key']}")
        elif "hotkey" in step:
            pyautogui.hotkey(*step["hotkey"])
            print(f"hotkey {step['hotkey']}")
        elif "click" in step:
            pyautogui.click(step["click"][0], step["click"][1])
            print(f"click {step['click']}")
        elif "dclick" in step:
            pyautogui.doubleClick(step["dclick"][0], step["dclick"][1])
            print(f"dclick {step['dclick']}")
        elif "type" in step:
            pyautogui.typewrite(step["type"], interval=0.02)
            print(f"type {step['type']!r}")
        elif "move" in step:
            pyautogui.moveTo(step["move"][0], step["move"][1])
            print(f"move {step['move']}")
        if "shot" in step:
            p = Path(step["shot"])
            p.parent.mkdir(parents=True, exist_ok=True)
            pyautogui.screenshot(str(p))
            print(f"shot {p}")

    time.sleep(float(spec.get("settle", 1.4)))
    shot = spec.get("shot")
    if shot:
        p = Path(shot)
        p.parent.mkdir(parents=True, exist_ok=True)
        pyautogui.screenshot(str(p))
        print(f"shot {p}")
        if spec.get("ocr", True):
            script = Path(__file__).parent / "ocr.ps1"
            r = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), str(p)],
                capture_output=True, text=True, timeout=120,
            )
            for line in r.stdout.splitlines():
                if "FL Studio" in line or line.strip():
                    print("OCR", line)
            if r.returncode != 0:
                print("OCR failed:", r.stderr[-400:])


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 2
    cmd, rest = argv[1], argv[2:]
    if cmd == "do":
        cmd_do(rest[0])
        return 0
    if cmd == "windows":
        cmd_windows()
    elif cmd == "activate":
        cmd_activate(rest[0])
    elif cmd == "shot":
        cmd_shot(rest[0])
    elif cmd == "click":
        pyautogui.click(int(rest[0]), int(rest[1]))
        print(f"clicked {rest[0]},{rest[1]}")
    elif cmd == "dclick":
        pyautogui.doubleClick(int(rest[0]), int(rest[1]))
        print(f"double-clicked {rest[0]},{rest[1]}")
    elif cmd == "rclick":
        pyautogui.rightClick(int(rest[0]), int(rest[1]))
        print(f"right-clicked {rest[0]},{rest[1]}")
    elif cmd == "key":
        pyautogui.press(rest[0])
        print(f"pressed {rest[0]}")
    elif cmd == "type":
        pyautogui.typewrite(rest[0], interval=0.02)
        print(f"typed {len(rest[0])} chars")
    elif cmd == "drag":
        pyautogui.moveTo(int(rest[0]), int(rest[1]))
        pyautogui.dragTo(int(rest[2]), int(rest[3]), duration=0.4)
        print("dragged")
    elif cmd == "move":
        pyautogui.moveTo(int(rest[0]), int(rest[1]))
        print("moved")
    elif cmd == "pos":
        print(pyautogui.position())
    else:
        print(f"unknown command '{cmd}'")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
