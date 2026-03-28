"""
Low-level atomic JSON read/write for .archmap/ storage.

Locking strategy — two-tier for multi-agent safety:
  1. In-process:    threading.Lock per project  (protects same-process threads)
  2. Cross-process: OS-level lock file          (protects concurrent MCP instances)

The OS lock uses a .lock file per data file with exclusive advisory locking.
On Windows: msvcrt.locking  |  On Unix: fcntl.flock
Both are non-blocking with a short retry loop so agents degrade gracefully
under contention rather than deadlocking.
"""
from __future__ import annotations
import json
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from archmap.models import ProjectNotInitializedError

# Global per-project threading lock registry (same-process safety)
_locks: dict[str, threading.Lock] = {}
_locks_meta = threading.Lock()

ARCHMAP_DIR = ".archmap"
META_FILE = "meta.json"
ARCH_FILE = "architecture.json"
MAPPINGS_FILE = "mappings.json"
PLAN_FILE = "plan.json"

_ARCH_DEFAULT: dict = {"components": [], "dependencies": [], "contracts": {}}
_MAPPINGS_DEFAULT: dict = {"files": {}}
_PLAN_DEFAULT: dict = {"items": []}

_LOCK_TIMEOUT  = 10.0   # seconds to wait for OS lock before giving up
_LOCK_RETRY_MS = 50     # milliseconds between retries


# ─── OS-level cross-process file lock ─────────────────────────────────────────

@contextmanager
def _os_lock(lock_path: Path):
    """
    Acquire an exclusive advisory lock on `lock_path` (created if absent).
    Blocks up to _LOCK_TIMEOUT seconds, then raises TimeoutError.
    Works on Windows (msvcrt) and Unix (fcntl).
    """
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "a+b")
    deadline = time.monotonic() + _LOCK_TIMEOUT
    acquired = False
    try:
        while time.monotonic() < deadline:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except (OSError, IOError):
                time.sleep(_LOCK_RETRY_MS / 1000)
        if not acquired:
            raise TimeoutError(
                f"Could not acquire file lock on {lock_path} within "
                f"{_LOCK_TIMEOUT}s — another process may be holding it."
            )
        yield
    finally:
        if acquired:
            try:
                if sys.platform == "win32":
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh, fcntl.LOCK_UN)
            except Exception:
                pass
        fh.close()


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_lock(project_path: str) -> threading.Lock:
    """Return the in-process threading lock for this project path."""
    with _locks_meta:
        if project_path not in _locks:
            _locks[project_path] = threading.Lock()
        return _locks[project_path]


def archmap_dir(project_path: str) -> Path:
    return Path(project_path) / ARCHMAP_DIR


def _require_init(project_path: str) -> Path:
    d = archmap_dir(project_path)
    if not d.exists():
        raise ProjectNotInitializedError(project_path)
    return d


def _load(path: Path, default: dict) -> dict:
    if not path.exists():
        return dict(default)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: dict) -> None:
    """Write data atomically via a temp file. Caller must hold locks."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    # On Windows, os.replace() can transiently fail with PermissionError if
    # another process (file watcher, antivirus) briefly holds the target open.
    # Retry with short backoff before propagating.
    for attempt in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


# ─── Meta ─────────────────────────────────────────────────────────────────────

def load_meta(project_path: str) -> dict:
    d = _require_init(project_path)
    return _load(d / META_FILE, {})


def save_meta(project_path: str, data: dict) -> None:
    d = _require_init(project_path)
    lock_path = d / (META_FILE + ".lock")
    with _get_lock(project_path), _os_lock(lock_path):
        _save(d / META_FILE, data)


def is_initialized(project_path: str) -> bool:
    return archmap_dir(project_path).exists()


# ─── Architecture ─────────────────────────────────────────────────────────────

def load_arch(project_path: str) -> dict[str, Any]:
    d = _require_init(project_path)
    return _load(d / ARCH_FILE, _ARCH_DEFAULT)


def save_arch(project_path: str, data: dict) -> None:
    d = _require_init(project_path)
    lock_path = d / (ARCH_FILE + ".lock")
    with _get_lock(project_path), _os_lock(lock_path):
        _save(d / ARCH_FILE, data)


def mutate_arch(project_path: str, fn) -> Any:
    """Load arch, apply fn(data) -> result, save, return result. Multi-process safe."""
    d = _require_init(project_path)
    lock_path = d / (ARCH_FILE + ".lock")
    with _get_lock(project_path), _os_lock(lock_path):
        path = d / ARCH_FILE
        data = _load(path, _ARCH_DEFAULT)
        # Ensure contracts key exists in older stored files
        data.setdefault("contracts", {})
        result = fn(data)
        _save(path, data)
        return result


def load_contracts(project_path: str) -> dict:
    """Return the contracts dict from architecture.json. Keys are node_ids."""
    arch = load_arch(project_path)
    return arch.get("contracts", {})


def mutate_contracts(project_path: str, fn) -> Any:
    """Mutate the contracts sub-dict inside architecture.json atomically."""
    def _wrap(data):
        data.setdefault("contracts", {})
        return fn(data["contracts"])
    return mutate_arch(project_path, _wrap)


# ─── Mappings ─────────────────────────────────────────────────────────────────

def load_mappings(project_path: str) -> dict[str, Any]:
    d = _require_init(project_path)
    return _load(d / MAPPINGS_FILE, _MAPPINGS_DEFAULT)


def mutate_mappings(project_path: str, fn) -> Any:
    d = _require_init(project_path)
    lock_path = d / (MAPPINGS_FILE + ".lock")
    with _get_lock(project_path), _os_lock(lock_path):
        path = d / MAPPINGS_FILE
        data = _load(path, _MAPPINGS_DEFAULT)
        result = fn(data)
        _save(path, data)
        return result


# ─── Plan ─────────────────────────────────────────────────────────────────────

def load_plan(project_path: str) -> dict[str, Any]:
    d = _require_init(project_path)
    return _load(d / PLAN_FILE, _PLAN_DEFAULT)


def mutate_plan(project_path: str, fn) -> Any:
    d = _require_init(project_path)
    lock_path = d / (PLAN_FILE + ".lock")
    with _get_lock(project_path), _os_lock(lock_path):
        path = d / PLAN_FILE
        data = _load(path, _PLAN_DEFAULT)
        result = fn(data)
        _save(path, data)
        return result


# ─── Reset ────────────────────────────────────────────────────────────────────

def reset_graph(project_path: str) -> dict:
    """
    Wipe architecture.json and mappings.json back to empty defaults.
    meta.json (project name, init timestamp) and plan.json are preserved.
    Returns counts of what was cleared.
    """
    d = _require_init(project_path)
    arch_lock = d / (ARCH_FILE + ".lock")
    map_lock  = d / (MAPPINGS_FILE + ".lock")

    with _get_lock(project_path):
        with _os_lock(arch_lock):
            arch_path = d / ARCH_FILE
            old = _load(arch_path, _ARCH_DEFAULT)
            comp_count = len(old.get("components", []))
            dep_count  = len(old.get("dependencies", []))
            _save(arch_path, dict(_ARCH_DEFAULT))

        with _os_lock(map_lock):
            map_path = d / MAPPINGS_FILE
            old_map = _load(map_path, _MAPPINGS_DEFAULT)
            file_count = len(old_map.get("files", {}))
            _save(map_path, dict(_MAPPINGS_DEFAULT))

    return {
        "cleared_components": comp_count,
        "cleared_dependencies": dep_count,
        "cleared_file_mappings": file_count,
    }


# ─── File path normalization ──────────────────────────────────────────────────

def normalize_path(project_path: str, file_path: str) -> str:
    """Convert absolute or relative path to relative posix string."""
    p = Path(file_path)
    root = Path(project_path)
    try:
        rel = p.relative_to(root)
    except ValueError:
        rel = p  # already relative
    return rel.as_posix()
