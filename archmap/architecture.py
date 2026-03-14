"""
Component and dependency CRUD.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Optional

from archmap.models import Component, Dependency, NotFoundError, _now
from archmap.store import load_arch, mutate_arch


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
    metadata: Optional[dict] = None,
) -> dict:
    comp = Component.new(
        name=name,
        description=description,
        layer=layer,
        tags=tags or [],
        color=color,
        confidence=confidence,
        metadata=metadata or {},
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
    updatable = {"name", "description", "layer", "tags", "color", "confidence", "metadata"}
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
) -> dict:
    # Validate both components exist
    arch = load_arch(project_path)
    ids = {c["id"] for c in arch.get("components", [])}
    if from_component not in ids:
        raise NotFoundError(f"Component not found: {from_component}")
    if to_component not in ids:
        raise NotFoundError(f"Component not found: {to_component}")

    dep = Dependency.new(from_component=from_component, to_component=to_component, label=label, kind=kind)
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
