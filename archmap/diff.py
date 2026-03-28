"""
Architecture snapshot and diff — track architectural drift over time.

Use case 1 — PR review transparency:
    snapshot_architecture(path, label="before-feature-x")
    # ... make changes ...
    diff_architecture(path, snapshot_label="before-feature-x")
    # → shows exactly which components and deps changed

Use case 2 — CI gate:
    baseline = diff_architecture(path, snapshot_label="main")
    if any dep in baseline["added_deps"] crosses frontend→database: fail

Snapshots are stored in .archmap/snapshots/<id>.json and persist across sessions.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from archmap.repo import load_arch, load_meta, require_init


# ── Snapshot storage ───────────────────────────────────────────────────────────

def _snapshots_dir(project_path: str) -> Path:
    d = Path(project_path) / ".archmap" / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_path(project_path: str, snapshot_id: str) -> Path:
    return _snapshots_dir(project_path) / f"{snapshot_id}.json"


def snapshot_architecture(project_path: str, label: str | None = None) -> dict:
    """
    Save the current architecture state as a named snapshot.

    Returns:
        {snapshot_id, label, created_at, component_count, dependency_count}
    """
    require_init(project_path)
    arch = load_arch(project_path)

    snapshot_id = "snap_" + uuid.uuid4().hex[:12]
    created_at  = datetime.now(timezone.utc).isoformat()
    label       = label or f"snapshot-{created_at[:19].replace(':', '-')}"

    components   = arch.get("components", [])
    dependencies = arch.get("dependencies", [])

    record = {
        "snapshot_id":       snapshot_id,
        "label":             label,
        "created_at":        created_at,
        "component_count":   len(components),
        "dependency_count":  len(dependencies),
        "components":        components,
        "dependencies":      dependencies,
    }

    _snapshot_path(project_path, snapshot_id).write_text(
        json.dumps(record, indent=2, default=str), encoding="utf-8"
    )
    return {
        "snapshot_id":      snapshot_id,
        "label":            label,
        "created_at":       created_at,
        "component_count":  len(components),
        "dependency_count": len(dependencies),
    }


def list_snapshots(project_path: str) -> list[dict]:
    """
    List all snapshots for this project, newest first.
    """
    require_init(project_path)
    snaps_dir = _snapshots_dir(project_path)
    results: list[dict] = []
    for p in snaps_dir.glob("snap_*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            results.append({
                "snapshot_id":      data["snapshot_id"],
                "label":            data.get("label", ""),
                "created_at":       data.get("created_at", ""),
                "component_count":  data.get("component_count", 0),
                "dependency_count": data.get("dependency_count", 0),
            })
        except Exception:
            pass
    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return results


def _load_snapshot(project_path: str, snapshot_label: str | None, snapshot_id: str | None) -> dict:
    """Load a snapshot by label or ID. Raises FileNotFoundError if not found."""
    require_init(project_path)
    snaps_dir = _snapshots_dir(project_path)

    if snapshot_id:
        p = _snapshot_path(project_path, snapshot_id)
        if not p.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot_id}")
        return json.loads(p.read_text(encoding="utf-8"))

    if snapshot_label:
        for p in snaps_dir.glob("snap_*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                if data.get("label") == snapshot_label:
                    return data
            except Exception:
                pass
        raise FileNotFoundError(
            f"No snapshot found with label '{snapshot_label}'. "
            "Run list_snapshots() to see available snapshots."
        )

    raise ValueError("Provide either snapshot_label or snapshot_id.")


# ── Diff logic ─────────────────────────────────────────────────────────────────

def _comp_key(c: dict) -> tuple:
    return (c.get("name", ""), c.get("layer", ""), c.get("description", ""))


def _dep_key(d: dict) -> tuple:
    return (d.get("from_component", ""), d.get("to_component", ""),
            d.get("label", ""), d.get("kind", ""), d.get("confidence", ""))


def diff_architecture(
    project_path: str,
    snapshot_label: str | None = None,
    snapshot_id: str | None = None,
) -> dict:
    """
    Compare the current architecture against a saved snapshot.

    Returns a structured diff:
    {
        snapshot:            {snapshot_id, label, created_at},
        current:             {created_at, component_count, dependency_count},
        summary:             {added_components, removed_components, changed_components,
                              added_deps, removed_deps, changed_deps},
        added_components:    [{id, name, layer, description}],
        removed_components:  [{id, name, layer, description}],
        changed_components:  [{id, name, field, old, new}],
        added_deps:          [{id, from_component, from_name, to_component, to_name, label, kind}],
        removed_deps:        [{id, from_component, from_name, to_component, to_name, label, kind}],
        changed_deps:        [{id, from_name, to_name, field, old, new}],
        clean:               bool  — True if nothing changed
    }
    """
    snap   = _load_snapshot(project_path, snapshot_label, snapshot_id)
    arch   = load_arch(project_path)

    snap_comps = {c["id"]: c for c in snap.get("components", [])}
    curr_comps = {c["id"]: c for c in arch.get("components", [])}
    snap_deps  = {d["id"]: d for d in snap.get("dependencies", [])}
    curr_deps  = {d["id"]: d for d in arch.get("dependencies", [])}

    # Name maps for human-readable output
    curr_names = {c["id"]: c.get("name", c["id"]) for c in arch.get("components", [])}
    snap_names = {c["id"]: c.get("name", c["id"]) for c in snap.get("components", [])}
    all_names  = {**snap_names, **curr_names}

    # ── Components ──────────────────────────────────────────────────────────
    added_comps   = [c for cid, c in curr_comps.items() if cid not in snap_comps]
    removed_comps = [c for cid, c in snap_comps.items() if cid not in curr_comps]

    changed_comps: list[dict] = []
    for cid in set(snap_comps) & set(curr_comps):
        old, new = snap_comps[cid], curr_comps[cid]
        for field in ("name", "layer", "description"):
            ov, nv = old.get(field, ""), new.get(field, "")
            if ov != nv:
                changed_comps.append({
                    "id":    cid,
                    "name":  new.get("name", cid),
                    "field": field,
                    "old":   ov,
                    "new":   nv,
                })

    # ── Dependencies ────────────────────────────────────────────────────────
    added_deps   = [d for did, d in curr_deps.items() if did not in snap_deps]
    removed_deps = [d for did, d in snap_deps.items() if did not in curr_deps]

    changed_deps: list[dict] = []
    for did in set(snap_deps) & set(curr_deps):
        old, new = snap_deps[did], curr_deps[did]
        for field in ("label", "kind", "confidence"):
            ov, nv = old.get(field, ""), new.get(field, "")
            if ov != nv:
                changed_deps.append({
                    "id":        did,
                    "from_name": all_names.get(new.get("from_component", ""), "?"),
                    "to_name":   all_names.get(new.get("to_component", ""), "?"),
                    "field":     field,
                    "old":       ov,
                    "new":       nv,
                })

    def _enrich_dep(d: dict, names: dict) -> dict:
        return {
            **d,
            "from_name": names.get(d.get("from_component", ""), d.get("from_component", "?")),
            "to_name":   names.get(d.get("to_component",   ""), d.get("to_component",   "?")),
        }

    added_deps_rich   = [_enrich_dep(d, curr_names) for d in added_deps]
    removed_deps_rich = [_enrich_dep(d, all_names)  for d in removed_deps]

    summary = {
        "added_components":   len(added_comps),
        "removed_components": len(removed_comps),
        "changed_components": len(changed_comps),
        "added_deps":         len(added_deps),
        "removed_deps":       len(removed_deps),
        "changed_deps":       len(changed_deps),
    }
    clean = all(v == 0 for v in summary.values())

    return {
        "snapshot": {
            "snapshot_id": snap["snapshot_id"],
            "label":       snap.get("label", ""),
            "created_at":  snap.get("created_at", ""),
        },
        "current": {
            "created_at":       datetime.now(timezone.utc).isoformat(),
            "component_count":  len(curr_comps),
            "dependency_count": len(curr_deps),
        },
        "summary":             summary,
        "added_components":    added_comps,
        "removed_components":  removed_comps,
        "changed_components":  changed_comps,
        "added_deps":          added_deps_rich,
        "removed_deps":        removed_deps_rich,
        "changed_deps":        changed_deps,
        "clean":               clean,
    }
