
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
import archmap.inference as infer_mod
import archmap.intelligence as intel_mod
import archmap.mapping as map_mod
import archmap.planning as plan_mod
import archmap.project as proj_mod
import archmap.scanner as scan_mod
import archmap.symbols as symbols_mod
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


@mcp.tool()
def annotate_file(
    project_path: str,
    file_path: str,
    description: str = "",
    functions: str = "",
    language: str = "",
) -> str:
    """
    Annotate a mapped file with description, key functions/classes, and language.
    Call after map_file to enrich the architecture with implementation details.

    functions: comma-separated list of key functions/classes (e.g. "authenticate(), UserModel, validate_token()")
    language: programming language (e.g. "python", "typescript")
    """
    try:
        metadata: dict = {}
        if description:
            metadata["description"] = description
        if functions:
            metadata["functions"] = [f.strip() for f in functions.split(",") if f.strip()]
        if language:
            metadata["language"] = language
        return _ok(map_mod.update_file_metadata(project_path, file_path, metadata))
    except NotFoundError as e:
        return _err(str(e))
    except Exception as e:
        return _err(str(e))


# ─── Inference tools ──────────────────────────────────────────────────────────

@mcp.tool()
def infer_dependencies(project_path: str, overwrite_auto: bool = False) -> str:
    """
    Scan all mapped files for import statements and auto-detect cross-component
    dependencies. Adds inferred deps with confidence='auto' (shown as dashed
    edges in the UI). Confirmed deps are never overwritten.

    overwrite_auto: if True, refresh previously auto-inferred deps.

    Returns: {added, skipped, unmapped, dependencies}
    - added       — new deps written to architecture.json
    - skipped     — pairs that already had a confirmed dep
    - unmapped    — files that are imported but not yet mapped to a component
    - dependencies — the dep objects that were added
    """
    try:
        return _ok(infer_mod.infer_dependencies(project_path, overwrite_auto=overwrite_auto))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def confirm_dependency(project_path: str, dependency_id: str) -> str:
    """
    Promote an auto-inferred dependency to confirmed.
    Use this after reviewing an inferred dep to mark it as intentional.
    """
    try:
        return _ok(infer_mod.confirm_dependency(project_path, dependency_id))
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


# ─── Architecture intelligence ────────────────────────────────────────────────

@mcp.tool()
def describe_architecture(project_path: str) -> str:
    """
    Generate a comprehensive markdown document of the full architecture:
    all components grouped by layer with their files, symbols, dependencies,
    entry points, and hotspots. Returns human+agent-readable markdown.

    Use this FIRST when starting work on any project to understand the codebase
    without reading source files. Replaces manually grepping files to understand
    what components exist and how they connect.
    """
    try:
        return intel_mod.describe_architecture(project_path)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def find_related(project_path: str, query: str) -> str:
    """
    Full-text search across ALL architecture entities: component names and
    descriptions, file paths and descriptions, and symbol names.
    Returns ranked results grouped into components, files, and symbols.

    Use this to answer "where does X live?" before reading any source files.
    Examples: find_related("auth"), find_related("database"), find_related("validate")
    Returns: {query, summary, components[], files[], symbols[]}
    """
    try:
        return _ok(intel_mod.find_related(project_path, query))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_symbol_index(project_path: str) -> str:
    """
    Return the complete symbol index: every function and class name in the
    project mapped to its source file and component.
    Sorted by (component, file, symbol) for easy scanning.

    Use this to locate any function or class without reading source files.
    Each entry: {symbol, file_path, language, component_id, component_name, component_layer}
    """
    try:
        return _ok(intel_mod.get_symbol_index(project_path))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def trace_path(project_path: str, from_component_id: str, to_component_id: str) -> str:
    """
    Find the shortest dependency path between two components using BFS.
    Returns each hop with the dependency label and key files at that component.

    Use this to understand data flow: "how does the frontend reach the database?"
    or to assess blast radius: "what chain of components do I cross to reach X?"
    Returns: {found, length, text, path[{component_id, component_name, layer, via_dependency, files}]}
    """
    try:
        return _ok(intel_mod.trace_path(project_path, from_component_id, to_component_id))
    except Exception as e:
        return _err(str(e))


# ─── Symbol sync + search + coding context ────────────────────────────────────

@mcp.tool()
def sync_file_symbols(project_path: str, file_path: str) -> str:
    """
    Scan the actual source file and auto-extract all top-level functions and classes,
    then update the file's mapping metadata. Call this after editing a file to keep
    the architecture graph in sync with the real code.

    Returns the updated FileMapping with the refreshed symbol list.
    """
    try:
        extracted = symbols_mod.extract_all_symbols(project_path, file_path)
        metadata: dict = {"functions": extracted["symbols"]}
        if extracted["language"]:
            metadata["language"] = extracted["language"]
        result = map_mod.update_file_metadata(project_path, file_path, metadata)
        return _ok(result)
    except NotFoundError as e:
        return _err(f"File not mapped: {e}")
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def search_symbol(project_path: str, query: str = "") -> str:
    """
    Search for a function or class name across all mapped files in the project.
    Returns a list of matches: [{symbol, file_path, component_id}].

    Leave query empty to list every symbol in the project.
    Useful for finding where a function lives before editing it.
    """
    try:
        mappings = map_mod.list_all_mappings(project_path)
        q = query.lower()
        results = []
        for rec in mappings:
            for fn in rec.get("metadata", {}).get("functions", []):
                if not q or q in fn.lower():
                    results.append({
                        "symbol": fn,
                        "file_path": rec["file_path"],
                        "component_id": rec["component_id"],
                    })
        return _ok(results)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_coding_context(project_path: str, component_id: str) -> str:
    """
    Get everything needed to code in a component: its files with symbols,
    related dependencies (with component names), and open plan items.

    Call this before starting work on a component so you know:
    - which files belong to it and what functions they export
    - what other components it depends on (and what depends on it)
    - what tasks are planned or in-progress for it

    Returns both a human-readable summary and the raw data.
    """
    try:
        comp = arch_mod.get_component(project_path, component_id)
        files = map_mod.list_component_files(project_path, component_id)
        arch = arch_mod.get_architecture(project_path)
        items = plan_mod.list_plan_items(project_path, component_id=component_id)

        name_map = {c["id"]: c["name"] for c in arch.get("components", [])}
        enriched_deps = []
        for d in arch.get("dependencies", []):
            if d["from_component"] == component_id or d["to_component"] == component_id:
                enriched_deps.append({
                    **d,
                    "from_name": name_map.get(d["from_component"], d["from_component"]),
                    "to_name": name_map.get(d["to_component"], d["to_component"]),
                })

        # Human-readable summary
        lines = [
            f"## Component: {comp['name']} ({comp['layer']})",
            f"{comp.get('description', '(no description)')}",
            "",
            f"### Files ({len(files)})",
        ]
        for f in files:
            meta = f.get("metadata", {})
            desc = meta.get("description", "")
            lang = meta.get("language", "")
            fns = meta.get("functions", [])
            lang_tag = f"  [{lang}]" if lang else ""
            lines.append(f"- {f['file_path']}{lang_tag}" + (f"  — {desc}" if desc else ""))
            if fns:
                lines.append(f"  Symbols: {', '.join(fns)}")

        lines += ["", f"### Dependencies ({len(enriched_deps)})"]
        for d in enriched_deps:
            direction = "→" if d["from_component"] == component_id else "←"
            other = d["to_name"] if d["from_component"] == component_id else d["from_name"]
            lines.append(f"- {d['label']} {direction} {other} ({d['confidence']})")

        open_items = [it for it in items if it.get("status") not in ("done", "cancelled")]
        lines += ["", f"### Open Plan Items ({len(open_items)})"]
        for it in open_items:
            lines.append(f"- [{it['priority']}] {it['title']} ({it['status']})")

        return _ok({
            "text": "\n".join(lines),
            "component": comp,
            "files": files,
            "dependencies": enriched_deps,
            "plan_items": items,
        })
    except NotFoundError as e:
        return _err(f"Component not found: {e}")
    except Exception as e:
        return _err(str(e))


# ─── File & symbol reading ────────────────────────────────────────────────────
# These complete the "read architecture → locate node → read function" loop.
# Without them agents must fall back to raw filesystem reads, defeating the
# purpose of the knowledge graph.

@mcp.tool()
def read_function(project_path: str, file_path: str, symbol: str) -> str:
    """
    Extract the source code of a specific named function or class from a file.

    This is the final step of the agent navigation loop:
      1. describe_architecture()  — understand the landscape
      2. find_related() / get_symbol_index()  — locate which file owns the symbol
      3. read_function(file_path, symbol)  — read exactly that function, nothing else

    Returns: {symbol, file_path, code, start_line, end_line, language}
    Supports Python (AST-exact) and TypeScript/JavaScript (regex + brace scan).
    Falls back to surrounding-context search for other languages.

    Prefer this over get_file_content() when you only need one function — it uses
    far less context and is faster.
    """
    try:
        result = symbols_mod.extract_symbol(project_path, file_path, symbol)
        return _ok(result)
    except FileNotFoundError:
        return _err(f"File not found: {file_path}")
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def read_file(project_path: str, file_path: str, start_line: int = 0, end_line: int = 0) -> str:
    """
    Read the full content of a mapped file (or a line range of it).

    Use this when you need to read more than one function, or when the file is
    short and reading it whole is the simplest approach. For reading a single
    named function use read_function() instead — it uses less context.

    Args:
        file_path: Path relative to project_path (forward slashes).
        start_line: First line to return (1-based). 0 = from beginning.
        end_line:   Last line to return (inclusive, 1-based). 0 = to end.

    Returns: {file_path, content, lines, start_line, end_line}
    """
    try:
        result = symbols_mod.get_file_content(project_path, file_path)
        if start_line > 0 or end_line > 0:
            all_lines = result["content"].splitlines(keepends=True)
            s = max(0, start_line - 1)
            e = end_line if end_line > 0 else len(all_lines)
            result["content"] = "".join(all_lines[s:e])
            result["start_line"] = s + 1
            result["end_line"] = min(e, len(all_lines))
        return _ok(result)
    except FileNotFoundError:
        return _err(f"File not found: {file_path}")
    except Exception as e:
        return _err(str(e))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
