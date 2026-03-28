"""
Component and dependency CRUD.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional

from archmap.models import Component, Dependency, NotFoundError, _now
from archmap.store import load_arch, mutate_arch, mutate_mappings


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─── Components ───────────────────────────────────────────────────────────────

def list_components(
    project_path: str,
    layer: Optional[str] = None,
    confidence: Optional[str] = None,
) -> list[dict]:
    arch = load_arch(project_path)
    comps = arch.get("components", [])
    if layer:
        comps = [c for c in comps if c.get("layer") == layer]
    if confidence:
        comps = [c for c in comps if c.get("confidence") == confidence]
    return comps


def get_component(project_path: str, component_id: str) -> dict:
    arch = load_arch(project_path)
    for c in arch.get("components", []):
        if c["id"] == component_id:
            return c
    raise NotFoundError(f"Component not found: {component_id}")


def add_component(
    project_path: str,
    name: str,
    description: str = "",
    layer: str = "other",
    tags: Optional[list[str]] = None,
    color: str = "#6366f1",
    confidence: str = "confirmed",
    owner: str = "",
    tier: str = "",
    onboarding_notes: str = "",
    runbook_url: str = "",
    slack_channel: str = "",
    metadata: Optional[dict] = None,
    # Multi-level hierarchy
    level: int = 4,
    parent_id: str = "",
    protocol: str = "",
    port: Optional[int] = None,
    deploy_unit: bool = False,
    public_api: Optional[list[str]] = None,
    data_owned: Optional[list[str]] = None,
    stability: str = "stable",
) -> dict:
    comp = Component.new(
        name=name,
        description=description,
        layer=layer,
        tags=tags or [],
        color=color,
        confidence=confidence,
        owner=owner,
        tier=tier,
        onboarding_notes=onboarding_notes,
        runbook_url=runbook_url,
        slack_channel=slack_channel,
        metadata=metadata or {},
        level=level,
        parent_id=parent_id,
        protocol=protocol,
        port=port,
        deploy_unit=deploy_unit,
        public_api=public_api or [],
        data_owned=data_owned or [],
        stability=stability,
    )
    comp_dict = comp.to_dict()

    def _mutate(data):
        data.setdefault("components", []).append(comp_dict)

    mutate_arch(project_path, _mutate)
    return comp_dict


def update_component(
    project_path: str,
    component_id: str,
    **kwargs,
) -> dict:
    updatable = {
        "name", "description", "layer", "tags", "color", "confidence", "metadata",
        "owner", "tier", "onboarding_notes", "runbook_url", "slack_channel",
        # hierarchy + interface fields
        "level", "parent_id", "protocol", "port", "deploy_unit",
        "public_api", "data_owned", "stability",
    }
    result: dict = {}

    def _mutate(data):
        nonlocal result
        for c in data.get("components", []):
            if c["id"] == component_id:
                for k, v in kwargs.items():
                    if k in updatable and v is not None:
                        c[k] = v
                c["updated_at"] = _ts()
                result = c
                return
        raise NotFoundError(f"Component not found: {component_id}")

    mutate_arch(project_path, _mutate)
    return result


def delete_component(project_path: str, component_id: str) -> str:
    def _mutate(data):
        before = len(data.get("components", []))
        data["components"] = [c for c in data.get("components", []) if c["id"] != component_id]
        # Also remove related dependencies
        data["dependencies"] = [
            d for d in data.get("dependencies", [])
            if d["from_component"] != component_id and d["to_component"] != component_id
        ]
        if len(data["components"]) == before:
            raise NotFoundError(f"Component not found: {component_id}")

    mutate_arch(project_path, _mutate)
    return "deleted"


# ─── Dependencies ─────────────────────────────────────────────────────────────

def add_dependency(
    project_path: str,
    from_component: str,
    to_component: str,
    label: str = "uses",
    kind: str = "runtime",
    confidence: str = "confirmed",
) -> dict:
    # Validate both components exist
    arch = load_arch(project_path)
    ids = {c["id"] for c in arch.get("components", [])}
    if from_component not in ids:
        raise NotFoundError(f"Component not found: {from_component}")
    if to_component not in ids:
        raise NotFoundError(f"Component not found: {to_component}")

    dep = Dependency.new(
        from_component=from_component, to_component=to_component,
        label=label, kind=kind, confidence=confidence,
    )
    dep_dict = dep.to_dict()

    def _mutate(data):
        data.setdefault("dependencies", []).append(dep_dict)

    mutate_arch(project_path, _mutate)
    return dep_dict


def remove_dependency(project_path: str, dependency_id: str) -> str:
    def _mutate(data):
        before = len(data.get("dependencies", []))
        data["dependencies"] = [d for d in data.get("dependencies", []) if d["id"] != dependency_id]
        if len(data["dependencies"]) == before:
            raise NotFoundError(f"Dependency not found: {dependency_id}")

    mutate_arch(project_path, _mutate)
    return "removed"


def get_architecture(project_path: str) -> dict:
    """Return {components, dependencies} together."""
    arch = load_arch(project_path)
    return {
        "components": arch.get("components", []),
        "dependencies": arch.get("dependencies", []),
    }


def get_dependency_graph(project_path: str) -> dict:
    """
    Returns {nodes, edges} suitable for ReactFlow / graph renderers.
    Also returns adjacency_list for agent consumption.
    """
    arch = load_arch(project_path)
    components = arch.get("components", [])
    dependencies = arch.get("dependencies", [])

    nodes = [
        {
            "id": c["id"],
            "label": c["name"],
            "layer": c["layer"],
            "color": c.get("color", "#6366f1"),
            "confidence": c.get("confidence", "confirmed"),
        }
        for c in components
    ]

    edges = [
        {
            "id": d["id"],
            "source": d["from_component"],
            "target": d["to_component"],
            "label": d.get("label", "uses"),
            "kind": d.get("kind", "runtime"),
            "confidence": d.get("confidence", "confirmed"),
        }
        for d in dependencies
    ]

    # Build adjacency list for agents (more readable)
    adj: dict[str, list[str]] = {}
    name_map = {c["id"]: c["name"] for c in components}
    for dep in dependencies:
        src = name_map.get(dep["from_component"], dep["from_component"])
        tgt = name_map.get(dep["to_component"], dep["to_component"])
        adj.setdefault(src, []).append(f"{dep.get('label','uses')} → {tgt}")

    return {"nodes": nodes, "edges": edges, "adjacency": adj}


# ─── Semantic edge annotation ─────────────────────────────────────────────────

def annotate_dependency(
    project_path: str,
    dependency_id: str,
    edge_type: str | None = None,
    edge_level: str | None = None,
    crosses_boundary: bool | None = None,
    async_flag: bool | None = None,
    direction: str | None = None,
    interface_points: list[str] | None = None,
    payload_types: list[str] | None = None,
    stability: str | None = None,
    label: str | None = None,
) -> dict:
    """
    Enrich an existing dependency edge with semantic metadata.
    Only provided fields are updated; others remain unchanged.
    """
    result: dict = {}

    def _mutate(data):
        nonlocal result
        for d in data.get("dependencies", []):
            if d["id"] == dependency_id:
                if edge_type is not None:       d["edge_type"] = edge_type
                if edge_level is not None:      d["edge_level"] = edge_level
                if crosses_boundary is not None: d["crosses_boundary"] = crosses_boundary
                if async_flag is not None:       d["async_flag"] = async_flag
                if direction is not None:        d["direction"] = direction
                if interface_points is not None: d["interface_points"] = interface_points
                if payload_types is not None:    d["payload_types"] = payload_types
                if stability is not None:        d["stability"] = stability
                if label is not None:            d["label"] = label
                result = d
                return
        raise NotFoundError(f"Dependency not found: {dependency_id!r}")

    mutate_arch(project_path, _mutate)
    return result


# ─── Public API management ────────────────────────────────────────────────────

def promote_to_contract(
    project_path: str,
    component_id: str,
    symbol_names: list[str],
) -> dict:
    """
    Mark symbols as part of the component's stable public_api.
    Once promoted, changing these symbols triggers contract-break warnings.
    """
    result: dict = {}

    def _mutate(data):
        nonlocal result
        for c in data.get("components", []):
            if c["id"] == component_id:
                existing = set(c.get("public_api", []))
                existing.update(symbol_names)
                c["public_api"] = sorted(existing)
                c["updated_at"] = _ts()
                result = c
                return
        raise NotFoundError(f"Component not found: {component_id!r}")

    mutate_arch(project_path, _mutate)
    return result


def demote_from_contract(
    project_path: str,
    component_id: str,
    symbol_names: list[str],
) -> dict:
    """Remove symbols from the public_api list (mark as internal)."""
    result: dict = {}
    to_remove = set(symbol_names)

    def _mutate(data):
        nonlocal result
        for c in data.get("components", []):
            if c["id"] == component_id:
                c["public_api"] = [s for s in c.get("public_api", []) if s not in to_remove]
                c["updated_at"] = _ts()
                result = c
                return
        raise NotFoundError(f"Component not found: {component_id!r}")

    mutate_arch(project_path, _mutate)
    return result


# ─── File remapping ───────────────────────────────────────────────────────────

def remap_files_to_node(
    project_path: str,
    file_paths: list[str],
    target_component_id: str,
) -> dict:
    """
    Move a set of files to a different component.
    Used when splitting a large component into sub-components.
    Returns {remapped: [file_paths], not_found: [file_paths]}.
    """
    # Validate target exists
    arch = load_arch(project_path)
    ids = {c["id"] for c in arch.get("components", [])}
    if target_component_id not in ids:
        raise NotFoundError(f"Component not found: {target_component_id!r}")

    from archmap.store import normalize_path
    normalized = [normalize_path(project_path, fp) for fp in file_paths]
    remapped: list[str] = []
    not_found: list[str] = []

    def _mutate(data):
        files = data.get("files", {})
        for fp in normalized:
            if fp in files:
                files[fp]["component_id"] = target_component_id
                remapped.append(fp)
            else:
                not_found.append(fp)

    mutate_mappings(project_path, _mutate)
    return {"remapped": remapped, "not_found": not_found, "target": target_component_id}


# ─── List children (hierarchy navigation) ────────────────────────────────────

def list_children(project_path: str, parent_id: str) -> list[dict]:
    """Return all nodes whose parent_id matches the given id."""
    arch = load_arch(project_path)
    return [c for c in arch.get("components", []) if c.get("parent_id") == parent_id]


def get_ancestors(project_path: str, component_id: str) -> list[dict]:
    """Walk up the parent chain and return all ancestor nodes (nearest first)."""
    arch = load_arch(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}
    ancestors: list[dict] = []
    current = by_id.get(component_id)
    seen: set[str] = {component_id}
    while current:
        pid = current.get("parent_id", "")
        if not pid or pid in seen:
            break
        parent = by_id.get(pid)
        if not parent:
            break
        ancestors.append(parent)
        seen.add(pid)
        current = parent
    return ancestors
