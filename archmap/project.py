"""
Project lifecycle — init, meta access.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path

from archmap import __version__
from archmap.models import ArchMapError
from archmap.store import (
    ARCHMAP_DIR, META_FILE, ARCH_FILE, MAPPINGS_FILE, PLAN_FILE,
    archmap_dir, is_initialized, save_meta, load_meta,
)

_ARCH_DEFAULT = {"components": [], "dependencies": []}
_MAPPINGS_DEFAULT = {"files": {}}
_PLAN_DEFAULT = {"items": []}


def init_project(project_path: str, name: str | None = None) -> dict:
    """
    Initialize .archmap/ in project_path.
    Safe to call again — returns existing meta if already initialized.
    """
    root = Path(project_path)
    if not root.exists():
        raise ArchMapError(f"Project path does not exist: {project_path}")

    d = archmap_dir(project_path)
    if d.exists():
        return load_meta(project_path)

    d.mkdir(parents=True, exist_ok=True)

    project_name = name or root.name
    meta = {
        "name": project_name,
        "project_path": str(root.resolve()),
        "archmap_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    import json
    for fname, default in [
        (META_FILE, meta),
        (ARCH_FILE, _ARCH_DEFAULT),
        (MAPPINGS_FILE, _MAPPINGS_DEFAULT),
        (PLAN_FILE, _PLAN_DEFAULT),
    ]:
        path = d / fname
        if not path.exists():
            with open(path, "w", encoding="utf-8") as f:
                json.dump(default, f, indent=2)

    return meta


def project_status(project_path: str) -> dict:
    """Summary stats for a project."""
    from archmap.store import load_arch, load_mappings, load_plan
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)
    plan = load_plan(project_path)
    meta = load_meta(project_path)
    return {
        "name": meta.get("name", ""),
        "initialized": is_initialized(project_path),
        "components": len(arch.get("components", [])),
        "dependencies": len(arch.get("dependencies", [])),
        "mapped_files": len(mappings.get("files", {})),
        "plan_items": len(plan.get("items", [])),
        "plan_open": sum(
            1 for item in plan.get("items", [])
            if item.get("status") in ("todo", "in_progress", "blocked")
        ),
    }
