"""Append-only audit trail (output/audit_trail.json).

The file is one JSON array. Each append takes an exclusive lock, reads the array, adds the entry,
writes a temp file, fsyncs it and swaps it in with os.replace, so a crash mid-write leaves the old
file intact and simultaneous writers (threads or processes) never interleave. The file is never wiped:
if it can't be parsed, it is copied aside untouched and a new array is started that says so.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import HW5_DIR, MODEL_NAME
from .models import AuditEntry

MAX_FIELD_CHARS = 300
_thread_lock = threading.Lock()

_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|authorization|bearer|token|secret|password)\s*[:=]\s*\S+"),
    re.compile(r"\b(sk|pk)-[A-Za-z0-9_\-]{8,}"),
]


def _redact(text: str) -> str:
    key = os.environ.get("PORTKEY_API_KEY", "").strip()
    if key and key in text:
        text = text.replace(key, "[REDACTED]")
    for pat in _SECRET_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


def short(value: Any, limit: int = MAX_FIELD_CHARS) -> str | None:
    """Compact, redacted, length-capped text for the audit file."""
    if value is None:
        return None
    text = value if isinstance(value, str) else json.dumps(value, default=str, separators=(",", ":"))
    text = _redact(" ".join(text.split()))
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _allowed(path: Path) -> Path:
    path = path.resolve()
    allowed_roots = [(HW5_DIR / "output").resolve(), (HW5_DIR / "data" / "scratch").resolve()]
    if not any(root == path.parent or root in path.parents for root in allowed_roots):
        raise RuntimeError(f"Audit file must live in output/ or data/scratch/, not {path}")
    return path


def append(path: Path, **fields: Any) -> None:
    """Append one audit entry under an exclusive lock, replacing the file atomically."""
    path = _allowed(path)
    entry = AuditEntry(time=datetime.now(timezone.utc).isoformat(timespec="milliseconds"), **fields)
    record = {k: (short(v) if isinstance(v, str) and k in ("args", "result") else v) for k, v in entry.model_dump().items()}
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with _thread_lock, open(lock_path, "a") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            entries: list = []
            if path.exists() and path.stat().st_size > 0:
                try:
                    entries = json.loads(path.read_text())
                    if not isinstance(entries, list):
                        raise ValueError("audit file is not a JSON array")
                except ValueError:
                    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
                    kept = path.with_name(f"{path.stem}.unreadable-{stamp}{path.suffix}")
                    shutil.copy2(path, kept)
                    entries = [{"time": entry.time, "ticket": "-", "agent": "audit", "step_type": "error",
                                "result": f"Previous file could not be parsed; kept as {kept.name}", "model": None}]
            entries.append(record)
            fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
            try:
                with os.fdopen(fd, "w") as f:
                    json.dump(entries, f, indent=1)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp, path)
            except BaseException:
                if os.path.exists(tmp):
                    os.unlink(tmp)
                raise
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


# Portkey reports the same model as a dated release ("<MODEL_NAME>-2026-09-22") on chat completions and as
# its Azure global deployment ("<MODEL_NAME>-global") on the Responses API. Anything else is a substitution.
_SAME_MODEL = re.compile(re.escape(MODEL_NAME) + r"(-\d{4}-\d{2}-\d{2}|-global)?")


def model_matches(reply_model: str | None) -> bool:
    """True only for the configured model, a dated release of it, or its global deployment label."""
    return bool(reply_model) and _SAME_MODEL.fullmatch(reply_model) is not None
