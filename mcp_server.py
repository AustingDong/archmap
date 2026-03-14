"""
ArchMap MCP Server — exposes all ArchMap tools via Model Context Protocol.
Transport: stdio (works with Claude Code, Cursor, OpenClaw, any MCP client).

Usage:
    python mcp_server.py

Configure in Claude Code:
    claude mcp add archmap -- python /path/to/archmap/mcp_server.py
"""
import sys
import os
import json
from pathlib import Path

# Ensure archmap package is importable
sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP

import archmap.architecture as arch_mod
import archmap.mapping as map_mod
import archmap.planning as plan_mod
import archmap.project as proj_mod
import archmap.scanner as scan_mod
from archmap.models import ArchMapError, NotFoundError


mcp = FastMCP("ArchMap")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ok(data) -> str:
    return json.dumps(data, indent=2, default=str)


def _err(msg: str) -> str:
    return json.dumps({"error": msg})


# ─── Project tools ────────────────────────────────────────────────────────────

@mcp.tool()
def init_project(project_path: str, name: str = "") -> str:
    """
    Initialize ArchMap in a project directory.
    Creates .archmap/ with empty architecture, mappings, and plan files.
    Safe to call on an already-initialized project — returns existing meta.
    """
    try:
        result = proj_mod.init_project(project_path, name=name or None)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def project_status(project_path: str) -> str:
    """
    Get a summary of ArchMap data for a project:
    component count, dependency count, mapped files, open plan items.
    """
    try:
        return _ok(proj_mod.project_status(project_path))
    except Exception as e:
        return _err(str(e))


# ─── Architecture tools ───────────────────────────────────────────────────────

@mcp.tool()
def get_architecture(project_path: str) -> str:
    """
    Get the full architecture: all components and dependencies as JSON.
    Use this to understand the overall structure of a project before editing code.
    """
    try:
        from archmap.store import load_arch
        return _ok(load_arch(project_path))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_components(project_path: str, layer: str = "", confidence: str = "") -> str:
    """
    List all architecture components, optionally filtered by layer or confidence.
    layer: frontend | backend | database | infra | shared | testing | other
    confidence: auto | confirmed
    """
    try:
        return _ok(arch_mod.list_components(
            project_path,
            layer=layer or None,
            confidence=confidence or None,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_component(project_path: str, component_id: str) -> str:
    """Get a single component by ID, including all its metadata."""
    try:
        return _ok(arch_mod.get_component(project_path, component_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def add_component(
    project_path: str,
    name: str,
    description: str = "",
    layer: str = "other",
    tags: str = "",
    color: str = "#6366f1",
) -> str:
    """
    Add a new architecture component.
    tags: comma-separated string (e.g. "python,fastapi,rest")
    layer: frontend | backend | database | infra | shared | testing | other
    """
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        return _ok(arch_mod.add_component(
            project_path, name=name, description=description,
            layer=layer, tags=tag_list, color=color,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def update_component(
    project_path: str,
    component_id: str,
    name: str = "",
    description: str = "",
    layer: str = "",
    tags: str = "",
    color: str = "",
    confidence: str = "",
) -> str:
    """
    Update fields on an existing component. Only non-empty arguments are applied.
    Use confidence='confirmed' to promote an auto-detected component.
    """
    try:
        kwargs = {}
        if name: kwargs["name"] = name
        if description: kwargs["description"] = description
        if layer: kwargs["layer"] = layer
        if tags: kwargs["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        if color: kwargs["color"] = color
        if confidence: kwargs["confidence"] = confidence
        return _ok(arch_mod.update_component(project_path, component_id, **kwargs))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def delete_component(project_path: str, component_id: str) -> str:
    """
    Delete a component and all its dependencies.
    File mappings pointing to this component are NOT removed (files stay, just unmapped).
    """
    try:
        return _ok(arch_mod.delete_component(project_path, component_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def add_dependency(
    project_path: str,
    from_component: str,
    to_component: str,
    label: str = "uses",
    kind: str = "runtime",
) -> str:
    """
    Add a directed dependency between two components.
    kind: runtime | build | test | dev
    label: human-readable verb (e.g. "calls", "imports", "reads from")
    """
    try:
        return _ok(arch_mod.add_dependency(
            project_path, from_component, to_component, label=label, kind=kind,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def remove_dependency(project_path: str, dependency_id: str) -> str:
    """Remove a dependency edge by its ID."""
    try:
        return _ok(arch_mod.remove_dependency(project_path, dependency_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_dependency_graph(project_path: str) -> str:
    """
    Get the full dependency graph as {nodes, edges, adjacency}.
    - nodes/edges: ReactFlow-compatible format for the UI
    - adjacency: compact human/agent-readable summary
    """
    try:
        return _ok(arch_mod.get_dependency_graph(project_path))
    except Exception as e:
        return _err(str(e))


# ─── Mapping tools ────────────────────────────────────────────────────────────

@mcp.tool()
def map_file(project_path: str, file_path: str, component_id: str) -> str:
    """
    Associate a file (relative or absolute path) with a component.
    Use this when you are about to edit a file so agents understand the context.
    """
    try:
        return _ok(map_mod.map_file(project_path, file_path, component_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def unmap_file(project_path: str, file_path: str) -> str:
    """Remove the component mapping for a file."""
    try:
        return _ok(map_mod.unmap_file(project_path, file_path))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_file_component(project_path: str, file_path: str) -> str:
    """
    Look up which component a file belongs to.
    Returns null if the file is not mapped.
    Useful before editing a file to understand its architectural role.
    """
    try:
        result = map_mod.get_file_component(project_path, file_path)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_component_files(project_path: str, component_id: str) -> str:
    """List all files mapped to a specific component."""
    try:
        return _ok(map_mod.list_component_files(project_path, component_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def bulk_map(project_path: str, mappings_json: str) -> str:
    """
    Map multiple files at once.
    mappings_json: JSON array of {file_path, component_id} objects.
    Example: '[{"file_path": "backend/main.py", "component_id": "comp_abc123"}]'
    """
    try:
        mappings = json.loads(mappings_json)
        return _ok(map_mod.bulk_map(project_path, mappings))
    except json.JSONDecodeError as e:
        return _err(f"Invalid JSON: {e}")
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_all_mappings(project_path: str) -> str:
    """List all file-to-component mappings in the project."""
    try:
        return _ok(map_mod.list_all_mappings(project_path))
    except Exception as e:
        return _err(str(e))


# ─── Planning tools ───────────────────────────────────────────────────────────

@mcp.tool()
def list_plan_items(
    project_path: str,
    component_id: str = "",
    status: str = "",
    priority: str = "",
) -> str:
    """
    List plan items. Optionally filter by component, status, or priority.
    status: todo | in_progress | done | blocked | cancelled
    priority: low | medium | high | critical
    """
    try:
        return _ok(plan_mod.list_plan_items(
            project_path,
            component_id=component_id or None,
            status=status or None,
            priority=priority or None,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def create_plan_item(
    project_path: str,
    title: str,
    description: str = "",
    component_id: str = "",
    priority: str = "medium",
    tags: str = "",
) -> str:
    """
    Create a new plan item (task), optionally tied to a component.
    priority: low | medium | high | critical
    tags: comma-separated string
    """
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        return _ok(plan_mod.create_plan_item(
            project_path,
            title=title,
            description=description,
            component_id=component_id or None,
            priority=priority,
            tags=tag_list,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def update_plan_item(
    project_path: str,
    item_id: str,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    component_id: str = "",
    tags: str = "",
) -> str:
    """
    Update a plan item. Only non-empty arguments are applied.
    status: todo | in_progress | done | blocked | cancelled
    """
    try:
        kwargs = {}
        if title: kwargs["title"] = title
        if description: kwargs["description"] = description
        if status: kwargs["status"] = status
        if priority: kwargs["priority"] = priority
        if component_id: kwargs["component_id"] = component_id
        if tags: kwargs["tags"] = [t.strip() for t in tags.split(",") if t.strip()]
        return _ok(plan_mod.update_plan_item(project_path, item_id, **kwargs))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def delete_plan_item(project_path: str, item_id: str) -> str:
    """Delete a plan item by ID."""
    try:
        return _ok(plan_mod.delete_plan_item(project_path, item_id))
    except Exception as e:
        return _err(str(e))


# ─── Scanner tool ─────────────────────────────────────────────────────────────

@mcp.tool()
def scan_project(
    project_path: str,
    overwrite_auto: bool = False,
    depth: int = 2,
) -> str:
    """
    Auto-scan a project directory to detect architecture components from folder structure.
    Creates components with confidence='auto' and maps files to them.

    overwrite_auto: if True, re-detect and replace existing auto components
    depth: how many folder levels to scan (default 2)

    Run this after init_project to get a starting architecture map.
    """
    try:
        return _ok(scan_mod.scan_project(project_path, overwrite_auto=overwrite_auto, depth=depth))
    except Exception as e:
        return _err(str(e))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
