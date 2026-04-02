"""
Low-level atomic JSON persistence for the purpose tree and task stack.

Files: .archmap/tree.json, .archmap/tasks.json
Locking: in-process threading lock + OS-level advisory lock.
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

from archmap.core.models import TreeNode, Task, ProjectNotInitializedError

_locks: dict[str, threading.Lock] = {}
_locks_meta = threading.Lock()

ARCHMAP_DIR = ".archmap"
META_FILE = "meta.json"
TREE_FILE = "tree.json"
TASKS_FILE = "tasks.json"

_LOCK_TIMEOUT = 10.0
_LOCK_RETRY_MS = 50


# ─── OS-level cross-process file lock ────────────────────────────────────────

@contextmanager
def os_lock(lock_path: Path):
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
            raise TimeoutError(f"Could not acquire lock on {lock_path}")
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


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _get_lock(project_path: str) -> threading.Lock:
    with _locks_meta:
        if project_path not in _locks:
            _locks[project_path] = threading.Lock()
        return _locks[project_path]


def archmap_dir(project_path: str) -> Path:
    return Path(project_path) / ARCHMAP_DIR


def require_init(project_path: str) -> Path:
    d = archmap_dir(project_path)
    if not d.exists():
        raise ProjectNotInitializedError(project_path)
    return d


def is_initialized(project_path: str) -> bool:
    return archmap_dir(project_path).exists()


def _load(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _save(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    for attempt in range(6):
        try:
            tmp.replace(path)
            return
        except PermissionError:
            if attempt == 5:
                raise
            time.sleep(0.05 * (attempt + 1))


def normalize_path(project_path: str, file_path: str) -> str:
    p = Path(file_path)
    root = Path(project_path)
    try:
        rel = p.relative_to(root)
    except ValueError:
        rel = p
    return rel.as_posix()


# ─── Meta ────────────────────────────────────────────────────────────────────

def load_meta(project_path: str) -> dict:
    d = require_init(project_path)
    return _load(d / META_FILE, {})


def save_meta(project_path: str, data: dict) -> None:
    d = require_init(project_path)
    lock_path = d / (META_FILE + ".lock")
    with _get_lock(project_path), os_lock(lock_path):
        _save(d / META_FILE, data)


# ─── Tree ────────────────────────────────────────────────────────────────────

def load_tree(project_path: str) -> TreeNode | None:
    """Load the purpose tree. Returns None if no tree exists yet."""
    d = require_init(project_path)
    raw = _load(d / TREE_FILE, None)
    if raw is None:
        return None
    return TreeNode.from_dict(raw)


def save_tree(project_path: str, tree: TreeNode) -> None:
    d = require_init(project_path)
    lock_path = d / (TREE_FILE + ".lock")
    with _get_lock(project_path), os_lock(lock_path):
        _save(d / TREE_FILE, tree.to_dict())


def mutate_tree(project_path: str, fn) -> Any:
    """Load tree, apply fn(tree) -> result, save, return result."""
    d = require_init(project_path)
    lock_path = d / (TREE_FILE + ".lock")
    with _get_lock(project_path), os_lock(lock_path):
        path = d / TREE_FILE
        raw = _load(path, None)
        tree = TreeNode.from_dict(raw) if raw else None
        result = fn(tree)
        if tree is not None:
            _save(path, tree.to_dict())
        return result


# ─── Tasks ───────────────────────────────────────────────────────────────────

def load_tasks(project_path: str) -> list[Task]:
    """Load all tasks. Returns empty list if no tasks file."""
    d = require_init(project_path)
    raw = _load(d / TASKS_FILE, [])
    return [Task.from_dict(t) for t in raw]


def save_tasks(project_path: str, tasks: list[Task]) -> None:
    d = require_init(project_path)
    lock_path = d / (TASKS_FILE + ".lock")
    with _get_lock(project_path), os_lock(lock_path):
        _save(d / TASKS_FILE, [t.to_dict() for t in tasks])


def mutate_tasks(project_path: str, fn) -> Any:
    """Load tasks, apply fn(tasks) -> result, save, return result."""
    d = require_init(project_path)
    lock_path = d / (TASKS_FILE + ".lock")
    with _get_lock(project_path), os_lock(lock_path):
        path = d / TASKS_FILE
        raw = _load(path, [])
        tasks = [Task.from_dict(t) for t in raw]
        result = fn(tasks)
        _save(path, [t.to_dict() for t in tasks])
        return result


# ─── Reset ───────────────────────────────────────────────────────────────────

def reset_tree(project_path: str) -> None:
    """Delete tree.json. Meta is preserved."""
    d = require_init(project_path)
    tree_path = d / TREE_FILE
    lock_path = d / (TREE_FILE + ".lock")
    with _get_lock(project_path), os_lock(lock_path):
        if tree_path.exists():
            tree_path.unlink()


# ─── Init ────────────────────────────────────────────────────────────────────

def init_project(project_path: str, name: str = "") -> dict:
    """Create .archmap/ directory and meta.json."""
    d = archmap_dir(project_path)
    d.mkdir(parents=True, exist_ok=True)
    meta_path = d / META_FILE
    if not meta_path.exists():
        from datetime import datetime, timezone
        meta = {
            "name": name or Path(project_path).name,
            "initialized_at": datetime.now(timezone.utc).isoformat(),
        }
        _save(meta_path, meta)
    return _load(meta_path, {})
