"""
Low-level atomic JSON read/write for .archmap/ storage.
Per-project threading locks prevent concurrent write corruption.
"""
from __future__ import annotations
import json
import threading
from pathlib import Path
from typing import Any

from archmap.models import ProjectNotInitializedError

# Global per-project lock registry
_locks: dict[str, threading.Lock] = {}
_locks_meta = threading.Lock()

ARCHMAP_DIR = ".archmap"
META_FILE = "meta.json"
ARCH_FILE = "architecture.json"
MAPPINGS_FILE = "mappings.json"
PLAN_FILE = "plan.json"

_ARCH_DEFAULT: dict = {"components": [], "dependencies": []}
_MAPPINGS_DEFAULT: dict = {"files": {}}
_PLAN_DEFAULT: dict = {"items": []}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _get_lock(project_path: str) -> threading.Lock:
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
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    tmp.replace(path)


# ─── Meta ─────────────────────────────────────────────────────────────────────

def load_meta(project_path: str) -> dict:
    d = _require_init(project_path)
    return _load(d / META_FILE, {})


def save_meta(project_path: str, data: dict) -> None:
    d = _require_init(project_path)
    with _get_lock(project_path):
        _save(d / META_FILE, data)


def is_initialized(project_path: str) -> bool:
    return archmap_dir(project_path).exists()


# ─── Architecture ─────────────────────────────────────────────────────────────

def load_arch(project_path: str) -> dict[str, Any]:
    d = _require_init(project_path)
    return _load(d / ARCH_FILE, _ARCH_DEFAULT)


def save_arch(project_path: str, data: dict) -> None:
    d = _require_init(project_path)
    with _get_lock(project_path):
        _save(d / ARCH_FILE, data)


def mutate_arch(project_path: str, fn) -> Any:
    """Load arch, apply fn(data) -> result, save, return result."""
    d = _require_init(project_path)
    with _get_lock(project_path):
        path = d / ARCH_FILE
        data = _load(path, _ARCH_DEFAULT)
        result = fn(data)
        _save(path, data)
        return result


# ─── Mappings ─────────────────────────────────────────────────────────────────

def load_mappings(project_path: str) -> dict[str, Any]:
    d = _require_init(project_path)
    return _load(d / MAPPINGS_FILE, _MAPPINGS_DEFAULT)


def mutate_mappings(project_path: str, fn) -> Any:
    d = _require_init(project_path)
    with _get_lock(project_path):
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
    with _get_lock(project_path):
        path = d / PLAN_FILE
        data = _load(path, _PLAN_DEFAULT)
        result = fn(data)
        _save(path, data)
        return result


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
