"""
Multi-agent session management — work ownership and presence awareness.

Enables multiple humans and agents to share one ArchMap project without
stepping on each other:

  claim_component()    — "I am working on this component" (with TTL)
  release_component()  — "I am done with this component"
  heartbeat()          — "I am still alive" (refreshes TTL)
  list_active_work()   — "What is everyone else working on right now?"

Stored in .archmap/sessions.json as:
  {
    "claims": [
      {
        "claim_id":     "clm_abc123",
        "component_id": "comp_xyz",
        "actor":        "claude-code-session-1",
        "task":         "adding OAuth endpoints",
        "claimed_at":   "2026-03-26T10:00:00+00:00",
        "expires_at":   "2026-03-26T10:30:00+00:00",
        "last_seen":    "2026-03-26T10:05:00+00:00"
      }
    ]
  }

Claims expire automatically — a crashed agent or closed session will not
permanently block others. Default TTL is 30 minutes, refreshed by heartbeat().

Design principles:
  - Advisory locks only: a claim is a notification, not a hard block.
    Agents CAN proceed on a claimed component but SHOULD check first.
  - Atomic writes via the same store-level OS locks as all other mutations.
  - Expiry enforced lazily: expired claims are removed on any read/write.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path

from archmap.repo import require_init as _require_init, os_lock as _os_lock

SESSIONS_FILE = "sessions.json"
_DEFAULT_TTL_MINUTES = 30


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _sessions_path(project_path: str) -> Path:
    return _require_init(project_path) / SESSIONS_FILE


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _ts(dt: datetime) -> str:
    return dt.isoformat()


def _load(path: Path) -> dict:
    if not path.exists():
        return {"claims": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {"claims": []}


def _save(path: Path, data: dict) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, default=str), encoding="utf-8")
    tmp.replace(path)


def _purge_expired(claims: list[dict]) -> list[dict]:
    """Remove claims whose expires_at is in the past."""
    now = _now()
    return [
        c for c in claims
        if datetime.fromisoformat(c["expires_at"]) > now
    ]


# ─── Public API ───────────────────────────────────────────────────────────────

def claim_component(
    project_path: str,
    component_id: str,
    actor: str,
    task: str = "",
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
) -> dict:
    """
    Register that `actor` is working on `component_id`.

    If the actor already has a claim on this component, the existing claim is
    refreshed (TTL reset, task updated). Returns the claim record.

    Args:
        component_id: Component being worked on.
        actor:        Identity of the agent or human (e.g. "claude-code", "dev:alice").
        task:         Short description of what is being done.
        ttl_minutes:  How long the claim is valid. Refresh via heartbeat().

    Returns:
        The claim record: {claim_id, component_id, actor, task, claimed_at, expires_at}
    """
    path = _sessions_path(project_path)
    lock_path = path.parent / (SESSIONS_FILE + ".lock")

    with _os_lock(lock_path):
        data   = _load(path)
        claims = _purge_expired(data.get("claims", []))

        now        = _now()
        expires_at = now + timedelta(minutes=ttl_minutes)

        # Update existing claim from same actor on same component
        existing = next(
            (c for c in claims if c["component_id"] == component_id and c["actor"] == actor),
            None,
        )
        if existing:
            existing["task"]       = task or existing.get("task", "")
            existing["expires_at"] = _ts(expires_at)
            existing["last_seen"]  = _ts(now)
            claim = existing
        else:
            claim = {
                "claim_id":     "clm_" + uuid.uuid4().hex[:12],
                "component_id": component_id,
                "actor":        actor,
                "task":         task,
                "claimed_at":   _ts(now),
                "expires_at":   _ts(expires_at),
                "last_seen":    _ts(now),
            }
            claims.append(claim)

        data["claims"] = claims
        _save(path, data)

    return claim


def release_component(
    project_path: str,
    component_id: str,
    actor: str,
) -> dict:
    """
    Release a claim on a component. Call when done working on it.

    Returns: {released: bool, claim_id: str | None}
    """
    path      = _sessions_path(project_path)
    lock_path = path.parent / (SESSIONS_FILE + ".lock")

    with _os_lock(lock_path):
        data   = _load(path)
        claims = _purge_expired(data.get("claims", []))

        removed = [c for c in claims if c["component_id"] == component_id and c["actor"] == actor]
        claims  = [c for c in claims if not (c["component_id"] == component_id and c["actor"] == actor)]

        data["claims"] = claims
        _save(path, data)

    if removed:
        return {"released": True, "claim_id": removed[0]["claim_id"]}
    return {"released": False, "claim_id": None}


def heartbeat(
    project_path: str,
    actor: str,
    ttl_minutes: int = _DEFAULT_TTL_MINUTES,
) -> dict:
    """
    Refresh all active claims for `actor`. Prevents claims from expiring during
    long-running operations. Should be called every ~10 minutes.

    Returns: {refreshed: int}  — number of claims extended.
    """
    path      = _sessions_path(project_path)
    lock_path = path.parent / (SESSIONS_FILE + ".lock")

    with _os_lock(lock_path):
        data   = _load(path)
        claims = _purge_expired(data.get("claims", []))

        now        = _now()
        expires_at = now + timedelta(minutes=ttl_minutes)
        refreshed  = 0

        for c in claims:
            if c["actor"] == actor:
                c["expires_at"] = _ts(expires_at)
                c["last_seen"]  = _ts(now)
                refreshed += 1

        data["claims"] = claims
        _save(path, data)

    return {"refreshed": refreshed}


def list_active_work(project_path: str) -> dict:
    """
    Return all active (non-expired) work claims across all agents and humans.

    Use this before starting work on a component to check if someone else is
    already working on it.

    Returns:
      {
        claims: [
          {claim_id, component_id, component_name, actor, task,
           claimed_at, expires_at, minutes_remaining}
        ],
        by_component: {component_id: [actors]},
        by_actor:     {actor: [component_ids]}
      }
    """
    from archmap.repo import load_arch

    path   = _sessions_path(project_path)
    data   = _load(path)
    claims = _purge_expired(data.get("claims", []))

    # Enrich with component names
    arch     = load_arch(project_path)
    name_map = {c["id"]: c["name"] for c in arch.get("components", [])}

    now = _now()
    enriched: list[dict] = []
    for c in claims:
        expires = datetime.fromisoformat(c["expires_at"])
        mins_remaining = max(0, int((expires - now).total_seconds() / 60))
        enriched.append({
            **c,
            "component_name":  name_map.get(c["component_id"], c["component_id"]),
            "minutes_remaining": mins_remaining,
        })

    # Index views
    by_component: dict[str, list[str]] = {}
    by_actor:     dict[str, list[str]] = {}
    for c in enriched:
        by_component.setdefault(c["component_id"], []).append(c["actor"])
        by_actor.setdefault(c["actor"], []).append(c["component_id"])

    return {
        "claims":       enriched,
        "by_component": by_component,
        "by_actor":     by_actor,
    }


