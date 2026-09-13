"""Log tail: follows from the end, emits appended lines, survives truncation."""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from apire.capture.log_tail import LogTailListener
from apire.store import Store

AUTH = "fixture: synthetic log file, authorized"


def test_follows_appended_lines_not_history(tmp_path):
    log = tmp_path / "app.log"
    log.write_text("old line 1\nold line 2\n", encoding="utf-8")

    store = Store(root=tmp_path / "kb")
    cap = store.start_capture(transport="log_tail", authorization_statement=AUTH)
    listener = LogTailListener()
    listener.start(store, cap["capture_id"], path=str(log), poll_seconds=0.05)
    try:
        time.sleep(0.2)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("new line A\nnew line B\n")
        time.sleep(0.4)
        with open(log, "a", encoding="utf-8") as fh:
            fh.write("new line C\n")
        time.sleep(0.4)
    finally:
        stats = listener.stop()
        store.stop_capture(cap["capture_id"])

    frames = store.frames(cap["capture_id"])
    lines = [f["payload"]["line"] for f in frames]
    assert lines == ["new line A", "new line B", "new line C"], "only appended lines, in order"
    assert stats["frames"] == 3


def test_truncation_resets_offset(tmp_path):
    log = tmp_path / "rotate.log"
    log.write_text("padding line long enough to matter\nsecond line\n", encoding="utf-8")
    store = Store(root=tmp_path / "kb")
    cap = store.start_capture(transport="log_tail", authorization_statement=AUTH)
    listener = LogTailListener()
    listener.start(store, cap["capture_id"], path=str(log), poll_seconds=0.05)
    try:
        time.sleep(0.2)
        # truncate-in-place with less content than the previous size
        log.write_text("after-rotation\n", encoding="utf-8")
        time.sleep(0.4)
    finally:
        stats = listener.stop()
        store.stop_capture(cap["capture_id"])
    lines = [f["payload"]["line"] for f in store.frames(cap["capture_id"])]
    assert lines == ["after-rotation"]
    assert stats["rotations"] >= 1
