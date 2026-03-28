"""
Architecture Decision Records (ADRs) — per-component decision history.

Each ADR captures *why* a design choice was made, not just *what* was built.
This prevents re-litigation of settled decisions and accelerates onboarding for
new engineers and AI agents.

ADR lifecycle:
  proposed → accepted  (decision taken)
  accepted → deprecated (abandoned, no replacement)
  accepted → superseded (replaced by a newer ADR — link via superseded_by)

Storage: .archmap/decisions.json
  {
    "decisions": [
      {
        "id":            "adr_abc12345",
        "component_id":  "comp_xyz",
        "title":         "Use OS-level file locks for cross-process safety",
        "status":        "accepted",
        "context":       "Multiple MCP server instances can write concurrently ...",
        "decision":      "Use msvcrt.locking on Windows and fcntl.flock on Unix ...",
        "consequences":  "Lock files accumulate in .archmap/ ...",
        "alternatives":  "Redis lock, database lock, single-writer ...",
        "links":         ["https://..."],
        "superseded_by": null,
        "created_at":    "2026-03-26T...",
        "updated_at":    "2026-03-26T..."
      }
    ]
  }
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

from archmap.repo import require_init as _require_init, os_lock as _os_lock, get_lock as _get_lock

DECISIONS_FILE = "decisions.json"
_DEFAULT: dict = {"decisions": []}

DecisionStatus = Literal["proposed", "accepted", "deprecated", "superseded"]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _decisions_path(project_path: str) -> Path:
    return _require_init(project_path) / DECISIONS_FILE


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return "adr_" + uuid.uuid4().hex[:8]


def _load(path: Path) -> dict:
    if not path.exists():
        return {"decisions": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"decisions": []}


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _mutate(project_path: str, fn):
    d = _require_init(project_path)
    path = d / DECISIONS_FILE
    lock_path = d / (DECISIONS_FILE + ".lock")
    with _get_lock(project_path), _os_lock(lock_path):
        data = _load(path)
        result = fn(data)
        _save(path, data)
        return result


# ─── Public API ───────────────────────────────────────────────────────────────

def add_decision(
    project_path: str,
    component_id: str,
    title: str,
    context: str = "",
    decision: str = "",
    consequences: str = "",
    alternatives: str = "",
    links: list[str] | None = None,
    status: DecisionStatus = "proposed",
) -> dict:
    """
    Record a new Architecture Decision Record linked to a component.

    Args:
        component_id:  Component this decision applies to.
        title:         Short title, e.g. "Use OS-level file locks for multi-process safety".
        context:       Problem/forces that required a decision.
        decision:      What was decided and why.
        consequences:  Trade-offs, risks, positive outcomes.
        alternatives:  Other options that were considered.
        links:         URLs to related issues, RFCs, docs.
        status:        proposed | accepted | deprecated | superseded

    Returns: The full ADR record.
    """
    def _fn(data: dict) -> dict:
        rec = {
            "id":            _short_id(),
            "component_id":  component_id,
            "title":         title,
            "status":        status,
            "context":       context,
            "decision":      decision,
            "consequences":  consequences,
            "alternatives":  alternatives,
            "links":         links or [],
            "superseded_by": None,
            "created_at":    _now(),
            "updated_at":    _now(),
        }
        data.setdefault("decisions", []).append(rec)
        return rec

    return _mutate(project_path, _fn)


def list_decisions(
    project_path: str,
    component_id: str = "",
    status: str = "",
) -> list[dict]:
    """
    Return all ADRs, optionally filtered by component and/or status.

    Returns list of ADR records (full detail).
    """
    path = _decisions_path(project_path)
    data = _load(path)
    records = data.get("decisions", [])

    if component_id:
        records = [r for r in records if r.get("component_id") == component_id]
    if status:
        records = [r for r in records if r.get("status") == status]

    return records


def get_decision(project_path: str, decision_id: str) -> dict:
    """Return a single ADR by ID. Raises KeyError if not found."""
    path = _decisions_path(project_path)
    data = _load(path)
    for rec in data.get("decisions", []):
        if rec["id"] == decision_id:
            return rec
    raise KeyError(f"Decision '{decision_id}' not found.")


def update_decision(
    project_path: str,
    decision_id: str,
    title: str = "",
    status: str = "",
    context: str = "",
    decision: str = "",
    consequences: str = "",
    alternatives: str = "",
    links: list[str] | None = None,
    superseded_by: str = "",
) -> dict:
    """
    Update fields on an existing ADR. Only non-empty arguments are applied.

    To mark as superseded: set status='superseded' and superseded_by='<new_adr_id>'.

    Returns the updated record.
    """
    def _fn(data: dict) -> dict:
        for rec in data.get("decisions", []):
            if rec["id"] == decision_id:
                if title:         rec["title"]         = title
                if status:        rec["status"]        = status
                if context:       rec["context"]       = context
                if decision:      rec["decision"]      = decision
                if consequences:  rec["consequences"]  = consequences
                if alternatives:  rec["alternatives"]  = alternatives
                if links is not None:
                                  rec["links"]         = links
                if superseded_by: rec["superseded_by"] = superseded_by
                rec["updated_at"] = _now()
                return rec
        raise KeyError(f"Decision '{decision_id}' not found.")

    return _mutate(project_path, _fn)


def delete_decision(project_path: str, decision_id: str) -> dict:
    """
    Delete an ADR permanently. Prefer deprecating or superseding over deleting.

    Returns {deleted: bool, id: str}.
    """
    def _fn(data: dict) -> dict:
        before = len(data.get("decisions", []))
        data["decisions"] = [r for r in data.get("decisions", []) if r["id"] != decision_id]
        after = len(data["decisions"])
        return {"deleted": before != after, "id": decision_id}

    return _mutate(project_path, _fn)


def get_decisions_for_context(project_path: str, component_id: str) -> list[dict]:
    """
    Return accepted ADRs for a component as a compact list for injection into
    code generation context. Only includes: id, title, decision, consequences.
    """
    records = list_decisions(project_path, component_id=component_id, status="accepted")
    return [
        {
            "id":           r["id"],
            "title":        r["title"],
            "decision":     r["decision"],
            "consequences": r["consequences"],
        }
        for r in records
    ]
