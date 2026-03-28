"""
Repository layer — the single public interface to persistent storage.

Structure:
  store.py  — low-level atomic JSON I/O with two-tier locking (private)
  repo.py   — this file: public data-access API used by all modules above it
  domain modules (architecture, mapping, planning, contracts) — CRUD logic
  analysis modules (intelligence, inference, context, …) — read-only queries

Rule: import from ``archmap.repo``, not ``archmap.store``.
``archmap.store`` is an implementation detail of the persistence layer.
"""
from __future__ import annotations

from archmap.store import (
    # Architecture graph
    load_arch,
    save_arch,
    mutate_arch,
    # Mappings
    load_mappings,
    mutate_mappings,
    # Plan
    load_plan,
    mutate_plan,
    # Meta
    load_meta,
    save_meta,
    # Contracts (stored inside architecture.json)
    load_contracts,
    mutate_contracts,
    # Project lifecycle
    is_initialized,
    archmap_dir,
    normalize_path,
    reset_graph,
)

__all__ = [
    # Architecture
    "load_arch",
    "save_arch",
    "mutate_arch",
    # Mappings
    "load_mappings",
    "mutate_mappings",
    # Plan
    "load_plan",
    "mutate_plan",
    # Meta
    "load_meta",
    "save_meta",
    # Contracts
    "load_contracts",
    "mutate_contracts",
    # Utilities
    "is_initialized",
    "archmap_dir",
    "normalize_path",
    "reset_graph",
    # Helpers
    "require_init",
    "os_lock",
    "get_lock",
]


def require_init(project_path: str):
    """
    Return the .archmap/ Path, or raise ProjectNotInitializedError.
    Use instead of importing the private ``_require_init`` from store.
    """
    from archmap.store import _require_init
    return _require_init(project_path)


def os_lock(lock_path):
    """
    Context manager: acquire an exclusive OS-level advisory lock.
    Use instead of importing the private ``_os_lock`` from store.
    """
    from archmap.store import _os_lock
    return _os_lock(lock_path)


def get_lock(project_path: str):
    """
    Return the in-process threading.Lock for this project path.
    Use instead of importing the private ``_get_lock`` from store.
    """
    from archmap.store import _get_lock
    return _get_lock(project_path)
