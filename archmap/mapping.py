"""
File-to-component mapping operations.
All file paths stored as relative posix strings.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from archmap.models import NotFoundError
from archmap.store import load_mappings, mutate_mappings, normalize_path


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def map_file(
    project_path: str,
    file_path: str,
    component_id: str,
    mapped_by: str = "user",
) -> dict:
    rel = normalize_path(project_path, file_path)
    record = {
        "component_id": component_id,
        "mapped_at": _ts(),
        "mapped_by": mapped_by,
    }

    def _mutate(data):
        data.setdefault("files", {})[rel] = record

    mutate_mappings(project_path, _mutate)
    return {"file_path": rel, **record}


def unmap_file(project_path: str, file_path: str) -> str:
    rel = normalize_path(project_path, file_path)

    def _mutate(data):
        files = data.get("files", {})
        if rel not in files:
            raise NotFoundError(f"No mapping for: {rel}")
        del files[rel]

    mutate_mappings(project_path, _mutate)
    return "unmapped"


def get_file_component(project_path: str, file_path: str) -> Optional[dict]:
    rel = normalize_path(project_path, file_path)
    data = load_mappings(project_path)
    record = data.get("files", {}).get(rel)
    if record is None:
        return None
    return {"file_path": rel, **record}


def list_component_files(project_path: str, component_id: str) -> list[str]:
    data = load_mappings(project_path)
    return [
        fp for fp, rec in data.get("files", {}).items()
        if rec.get("component_id") == component_id
    ]


def bulk_map(
    project_path: str,
    mappings: list[dict],  # [{file_path, component_id}]
    mapped_by: str = "user",
) -> dict:
    """Map multiple files at once. Returns {mapped, errors}."""
    mapped = 0
    errors = []
    for entry in mappings:
        try:
            map_file(
                project_path,
                entry["file_path"],
                entry["component_id"],
                mapped_by=mapped_by,
            )
            mapped += 1
        except Exception as e:
            errors.append({"file_path": entry.get("file_path"), "error": str(e)})
    return {"mapped": mapped, "errors": errors}


def list_all_mappings(project_path: str) -> list[dict]:
    data = load_mappings(project_path)
    return [
        {"file_path": fp, **rec}
        for fp, rec in data.get("files", {}).items()
    ]
