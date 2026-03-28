"""
Architecture change audit log — append-only record of every mutation.

Stored in .archmap/audit.json as a list of entries:
  {
    "id":          "audit_abc123",
    "timestamp":   "2026-03-15T06:00:00+00:00",
    "actor":       "claude-code",     # agent or user identifier
    "tool":        "add_component",   # MCP tool or REST endpoint name
    "entity_type": "component",       # component | dependency | file | plan_item
    "entity_id":   "comp_abc123",
    "change_type": "create",          # create | update | delete
    "summary":     "Added 'Auth' backend component",
    "data":        {...}              # full new state (or diff for update)
  }
"""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path

from archmap.repo import require_init as _require_init
from archmap.models import _short_id

AUDIT_FILE = "audit.json"
MAX_ENTRIES = 1000   # rotate after this many entries


def _audit_path(project_path: str) -> Path:
    return _require_init(project_path) / AUDIT_FILE


def append_audit(
    project_path: str,
    *,
    actor: str = "unknown",
    tool: str = "",
    entity_type: str = "",
    entity_id: str = "",
    change_type: str = "",
    summary: str = "",
    data: dict | None = None,
) -> dict:
    """Append one entry to the audit log. Thread-safe via simple file rewrite."""
    p = _audit_path(project_path)
    entries: list[dict] = []
    if p.exists():
        try:
            entries = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            entries = []

    entry = {
        "id": _short_id("audit"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "tool": tool,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "change_type": change_type,
        "summary": summary,
        "data": data or {},
    }
    entries.append(entry)

    # Rotate: keep only the most recent MAX_ENTRIES
    if len(entries) > MAX_ENTRIES:
        entries = entries[-MAX_ENTRIES:]

    p.write_text(json.dumps(entries, indent=2), encoding="utf-8")
    return entry


def get_audit_log(
    project_path: str,
    last_n: int = 50,
    entity_type: str = "",
    entity_id: str = "",
    actor: str = "",
) -> list[dict]:
    """
    Return recent audit log entries, newest first.
    Optional filters: entity_type, entity_id, actor.
    """
    p = _audit_path(project_path)
    if not p.exists():
        return []
    try:
        entries: list[dict] = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return []

    if entity_type:
        entries = [e for e in entries if e.get("entity_type") == entity_type]
    if entity_id:
        entries = [e for e in entries if e.get("entity_id") == entity_id]
    if actor:
        entries = [e for e in entries if e.get("actor") == actor]

    return list(reversed(entries[-last_n:] if last_n else entries))
