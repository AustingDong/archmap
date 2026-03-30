
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
import archmap.audit as audit_mod
import archmap.cognition as cognition_mod
import archmap.context as ctx_mod
import archmap.contracts as contracts_mod
import archmap.impact as impact_mod
import archmap.inference as infer_mod
import archmap.intelligence as intel_mod
import archmap.mapping as map_mod
import archmap.quality as quality_mod
import archmap.migration as migration_mod
import archmap.planning as plan_mod
import archmap.rules as rules_mod
import archmap.decisions as decisions_mod
import archmap.session as session_mod
import archmap.symbols as symbols_mod
from archmap.models import ArchMapError, NotFoundError


mcp = FastMCP("ArchMap")

# ─── Helpers ──────────────────────────────────────────────────────────────────

from datetime import datetime, timezone

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()

def _ok(data, warnings: list[str] | None = None, sync_status: dict | None = None) -> str:
    """Standard MCP response envelope — all tools return this shape."""
    envelope: dict = {
        "ok": True,
        "data": data,
        "warnings": warnings or [],
        "timestamp": _ts(),
    }
    if sync_status is not None:
        envelope["sync_status"] = sync_status
    return json.dumps(envelope, indent=2, default=str)


def _err(
    message: str,
    error_code: str = "ERROR",
    entity_type: str = "",
    entity_id: str = "",
    suggestion: str = "",
) -> str:
    """Structured error envelope — agents branch on error_code, not message text."""
    return json.dumps({
        "ok": False,
        "error": {
            "code": error_code,
            "message": message,
            "entity_type": entity_type,
            "entity_id": entity_id,
            "suggestion": suggestion,
        },
        "warnings": [],
        "timestamp": _ts(),
    }, default=str)


# ─── Project tools ────────────────────────────────────────────────────────────

# ─── Intent-driven bootstrap ──────────────────────────────────────────────────

@mcp.tool()
def bootstrap_architecture(
    project_path: str,
    components_json: str,
    dependencies_json: str = "[]",
    rules_json: str = "[]",
    tasks_json: str = "[]",
    actor: str = "",
) -> str:
    """
    Bootstrap a project's architecture from a structured proposal in one call.

    This is the RECOMMENDED starting point for new projects. Instead of calling
    add_component() many times, the agent proposes the full architecture as JSON
    and this tool creates everything atomically.

    Intended workflow:
      1. User describes what they want to build in plain language.
      2. Agent (Claude Code) thinks about what components, dependencies, rules,
         and initial tasks are needed — then calls this tool with the proposal.
      3. Review the response (what was created) and adjust with add_component /
         update_component if needed.
      4. Start coding. Components grow and evolve as the project does.

    Args:
        components_json:   JSON array of component proposals:
            [{
                "name": "API Server",
                "layer": "backend",
                "description": "FastAPI REST endpoints",
                "tags": "python,fastapi",     # optional, comma-separated
                "color": "#34d399"            # optional hex color
            }]
            layer must be one of: frontend | backend | database | infra | shared | testing | other

        dependencies_json: JSON array of dependency proposals (uses component NAMES, not IDs):
            [{
                "from": "Frontend",
                "to": "API Server",
                "label": "HTTP calls",
                "kind": "runtime"             # runtime | build | test | dev
            }]

        rules_json:        JSON array of architectural rules:
            [{
                "type": "no_dep",             # no_dep | no_cycles | required_dep
                "from_layer": "frontend",
                "to_layer": "database",
                "message": "Frontend must not access DB directly"
            }]

        tasks_json:        JSON array of initial plan items (linked to component names):
            [{
                "title": "Set up database schema",
                "component": "Database",
                "priority": "high",           # low | medium | high | critical
                "description": ""             # optional
            }]

        actor:  Identity of who is bootstrapping (e.g. "claude-code").

    Returns:
        {
          created_components:  [{id, name, layer}],
          created_deps:        [{id, from, to, label}],
          created_rules:       [{id, type, message}],
          created_tasks:       [{id, title, component}],
          warnings:            [str]   ← skipped items with reasons
        }
    """
    try:
        proposals   = json.loads(components_json)
        dep_props   = json.loads(dependencies_json)
        rule_props  = json.loads(rules_json)
        task_props  = json.loads(tasks_json)
    except json.JSONDecodeError as e:
        return _err(f"Invalid JSON in arguments: {e}",
                    suggestion="Wrap each argument in a JSON array []")

    warnings: list[str] = []
    created_comps: list[dict] = []
    created_deps:  list[dict] = []
    created_rules: list[dict] = []
    created_tasks: list[dict] = []

    # ── Create components ──────────────────────────────────────────────────────
    name_to_id: dict[str, str] = {}

    # Index existing components to avoid duplicates
    try:
        existing = arch_mod.list_components(project_path)
        for c in existing:
            name_to_id[c["name"].lower()] = c["id"]
    except Exception:
        pass

    for p in proposals:
        name = p.get("name", "").strip()
        if not name:
            warnings.append("Skipped component with empty name.")
            continue
        if name.lower() in name_to_id:
            warnings.append(f"Component '{name}' already exists — skipped.")
            continue
        try:
            tag_list = [t.strip() for t in p.get("tags", "").split(",") if t.strip()]
            comp = arch_mod.add_component(
                project_path,
                name=name,
                description=p.get("description", ""),
                layer=p.get("layer", "other"),
                tags=tag_list,
                color=p.get("color", "#6366f1"),
            )
            name_to_id[name.lower()] = comp["id"]
            created_comps.append({"id": comp["id"], "name": comp["name"], "layer": comp.get("layer")})
            if actor:
                audit_mod.append_audit(project_path, actor=actor, tool="bootstrap_architecture",
                                       entity_type="component", entity_id=comp["id"],
                                       change_type="create", summary=f"Bootstrapped component '{name}'")
        except Exception as e:
            warnings.append(f"Failed to create component '{name}': {e}")

    # ── Create dependencies (resolve names → IDs) ──────────────────────────────
    for d in dep_props:
        from_name = d.get("from", "").strip()
        to_name   = d.get("to",   "").strip()
        from_id   = name_to_id.get(from_name.lower())
        to_id     = name_to_id.get(to_name.lower())
        if not from_id:
            warnings.append(f"Dependency skipped — unknown component '{from_name}'.")
            continue
        if not to_id:
            warnings.append(f"Dependency skipped — unknown component '{to_name}'.")
            continue
        try:
            dep = arch_mod.add_dependency(
                project_path, from_id, to_id,
                label=d.get("label", "uses"),
                kind=d.get("kind", "runtime"),
            )
            created_deps.append({
                "id": dep["id"], "from": from_name, "to": to_name,
                "label": dep.get("label", "uses"),
            })
        except Exception as e:
            warnings.append(f"Dependency '{from_name}' → '{to_name}' failed: {e}")

    # ── Create rules ───────────────────────────────────────────────────────────
    for r in rule_props:
        try:
            rule = rules_mod.add_rule(
                project_path,
                rule_type=r.get("type", "no_dep"),
                from_layer=r.get("from_layer", ""),
                to_layer=r.get("to_layer", ""),
                message=r.get("message", ""),
            )
            created_rules.append({"id": rule["id"], "type": rule["type"], "message": rule.get("message", "")})
        except Exception as e:
            warnings.append(f"Rule failed: {e}")

    # ── Create initial tasks ───────────────────────────────────────────────────
    for t in task_props:
        comp_name = t.get("component", "").strip()
        comp_id   = name_to_id.get(comp_name.lower()) if comp_name else None
        if comp_name and not comp_id:
            warnings.append(f"Task '{t.get('title','')}' skipped — unknown component '{comp_name}'.")
            continue
        try:
            item = plan_mod.create_plan_item(
                project_path,
                title=t.get("title", ""),
                description=t.get("description", ""),
                component_id=comp_id,
                priority=t.get("priority", "medium"),
            )
            created_tasks.append({
                "id": item["id"], "title": item["title"],
                "component": comp_name or "(unlinked)",
            })
        except Exception as e:
            warnings.append(f"Task '{t.get('title','')}' failed: {e}")

    return _ok({
        "created_components": created_comps,
        "created_deps":       created_deps,
        "created_rules":      created_rules,
        "created_tasks":      created_tasks,
        "summary": (
            f"Created {len(created_comps)} component(s), "
            f"{len(created_deps)} dependency(ies), "
            f"{len(created_rules)} rule(s), "
            f"{len(created_tasks)} task(s)."
        ),
    }, warnings=warnings)


# ─── Architecture tools ───────────────────────────────────────────────────────

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
    owner: str = "",
    tier: str = "",
    onboarding_notes: str = "",
    runbook_url: str = "",
    slack_channel: str = "",
    actor: str = "",
    # Hierarchy & interface fields
    level: int = 4,
    parent_id: str = "",
    protocol: str = "",
    port: int = 0,
    deploy_unit: bool = False,
    public_api: str = "",
    data_owned: str = "",
    stability: str = "stable",
    confidence: str = "confirmed",
) -> str:
    """
    Add a new architecture component.
    tags:             comma-separated string (e.g. "python,fastapi,rest")
    layer:            frontend | backend | database | infra | shared | testing | other
    owner:            team or person responsible (e.g. "team:platform", "dev:alice")
    tier:             criticality — p0 (pages on-call) | p1 | p2 | p3
    onboarding_notes: "Here's how to get started with this component ..."
    runbook_url:      link to operational runbook or monitoring dashboard
    slack_channel:    "#platform-alerts"
    actor:            identity making this change — used in audit log

    Hierarchy & interface fields:
    level:       1=System 2=Domain 3=Service 4=Component 5=Module (default 4)
    parent_id:   ID of the parent node
    protocol:    http | grpc | stdio | websocket
    port:        listening port (0 = not a server)
    deploy_unit: True if separately deployable (process/container)
    public_api:  comma-separated exported symbol names
    data_owned:  comma-separated data types this node is authoritative for
    stability:   stable | beta | internal | deprecated
    confidence:  confirmed | auto
    """
    try:
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else []
        api_list = [s.strip() for s in public_api.split(",") if s.strip()] if public_api else []
        data_list = [s.strip() for s in data_owned.split(",") if s.strip()] if data_owned else []
        result = arch_mod.add_component(
            project_path, name=name, description=description,
            layer=layer, tags=tag_list, color=color,
            owner=owner, tier=tier, onboarding_notes=onboarding_notes,
            runbook_url=runbook_url, slack_channel=slack_channel,
            level=level, parent_id=parent_id, protocol=protocol,
            port=port if port else None, deploy_unit=deploy_unit,
            public_api=api_list, data_owned=data_list,
            stability=stability, confidence=confidence,
        )
        if actor:
            audit_mod.append_audit(project_path, actor=actor, tool="add_component",
                                   entity_type="component", entity_id=result.get("id", ""),
                                   change_type="create", summary=f"Added component '{name}'")
        return _ok(result)
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
    owner: str = "",
    tier: str = "",
    onboarding_notes: str = "",
    runbook_url: str = "",
    slack_channel: str = "",
    # Hierarchy & interface fields
    level: int = 0,
    parent_id: str = "",
    protocol: str = "",
    port: int = 0,
    deploy_unit: bool = False,
    public_api: str = "",
    data_owned: str = "",
    stability: str = "",
) -> str:
    """
    Update fields on an existing component. Only non-empty/non-zero arguments are applied.
    Use confidence='confirmed' to promote an auto-detected component.

    Hierarchy fields:
    level:       1=System 2=Domain 3=Service 4=Component 5=Module
    parent_id:   ID of the parent node (L2 parent is L1 system, etc.)
    protocol:    http | grpc | stdio | websocket
    port:        listening port number (0 = not a server)
    deploy_unit: True if this node is a separately deployable process/container
    public_api:  comma-separated list of exported symbol names
    data_owned:  comma-separated list of data types this node is authoritative for
    stability:   stable | beta | internal | deprecated

    Operational fields:
    owner:            team or person responsible (e.g. "team:platform", "dev:alice")
    tier:             p0 | p1 | p2 | p3  (p0 = most critical, pages on-call)
    onboarding_notes: plain text for new contributors / agents
    runbook_url:      link to ops runbook / monitoring dashboard
    slack_channel:    "#channel-name"
    """
    try:
        kwargs: dict = {}
        if name:             kwargs["name"]             = name
        if description:      kwargs["description"]      = description
        if layer:            kwargs["layer"]            = layer
        if tags:             kwargs["tags"]             = [t.strip() for t in tags.split(",") if t.strip()]
        if color:            kwargs["color"]            = color
        if confidence:       kwargs["confidence"]       = confidence
        if owner:            kwargs["owner"]            = owner
        if tier:             kwargs["tier"]             = tier
        if onboarding_notes: kwargs["onboarding_notes"] = onboarding_notes
        if runbook_url:      kwargs["runbook_url"]      = runbook_url
        if slack_channel:    kwargs["slack_channel"]    = slack_channel
        if level:            kwargs["level"]            = level
        if parent_id:        kwargs["parent_id"]        = parent_id
        if protocol:         kwargs["protocol"]         = protocol
        if port:             kwargs["port"]             = port
        if deploy_unit:      kwargs["deploy_unit"]      = deploy_unit
        if public_api:       kwargs["public_api"]       = [s.strip() for s in public_api.split(",") if s.strip()]
        if data_owned:       kwargs["data_owned"]       = [s.strip() for s in data_owned.split(",") if s.strip()]
        if stability:        kwargs["stability"]        = stability
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
def cleanup_non_source_mappings(project_path: str) -> str:
    """
    Remove all mapped files that are not source code — docs, config files,
    lock files, compiled artefacts, and binary assets.

    Safe to run at any time. Only removes non-source entries; confirmed source
    file mappings are untouched.

    Call this after an initial scan or bootstrap to clean up noise:
        cleanup_non_source_mappings(project_path="...")

    Returns {removed: [file_path], kept: int}.
    """
    try:
        return _ok(map_mod.cleanup_non_source_mappings(project_path))
    except Exception as e:
        return _err(str(e))


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


def list_component_files(project_path: str, component_id: str) -> str:
    """List all files mapped to a specific component."""
    try:
        return _ok(map_mod.list_component_files(project_path, component_id))
    except Exception as e:
        return _err(str(e))


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
def search(project_path: str, query: str) -> str:
    """
    Full-text search across ALL architecture entities: component names and
    descriptions, file paths and descriptions, and symbol names.
    Returns ranked results grouped into components, files, and symbols.

    Use this to answer "where does X live?" before reading any source files.
    Examples: search("auth"), search("database"), search("validate")
    Returns: {query, summary, components[], files[], symbols[]}
    """
    try:
        return _ok(intel_mod.find_related(project_path, query))
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
            symbols = rec.get("symbols", [])
            if symbols:
                # New format: rich symbol objects
                for sym in symbols:
                    sym_display = sym.get("display_name", sym.get("name", ""))
                    if not q or q in sym_display.lower():
                        results.append({
                            "symbol": sym_display,
                            "kind": sym.get("kind", "function"),
                            "visibility": sym.get("visibility", "public"),
                            "is_entry_point": sym.get("is_entry_point", False),
                            "file_path": rec["file_path"],
                            "component_id": rec.get("component_id", ""),
                            "signature": sym.get("signature", ""),
                            "doc": sym.get("doc", ""),
                        })
            else:
                # Legacy fallback: metadata.functions strings
                meta = rec.get("metadata", {})
                detail_map = {d["name"]: d for d in meta.get("symbol_details", [])}
                for fn in meta.get("functions", []):
                    if not q or q in fn.lower():
                        detail = detail_map.get(fn, {})
                        results.append({
                            "symbol": fn,
                            "kind": "function",
                            "visibility": "public",
                            "is_entry_point": False,
                            "file_path": rec["file_path"],
                            "component_id": rec.get("component_id", ""),
                            "signature": detail.get("signature", ""),
                            "doc": detail.get("doc", ""),
                        })
        return _ok(results)
    except Exception as e:
        return _err(str(e))


# ─── Unified agent context ────────────────────────────────────────────────────

@mcp.tool()
def get_context(
    project_path: str,
    component_id: str,
    task: str = "",
    depth: str = "implement",
) -> str:
    """
    Primary pre-edit context for agents — call this before touching any component.

    depth controls how much context is returned (use smaller values to save context window):
      "orient"    — component metadata + impact summary + first 3 open tasks (~300 tokens)
      "plan"      — orient + i_consume (contracts) + rules + decisions (~800 tokens)
      "implement" — full detail: files+symbols, quality, coordination_needed (~2000 tokens)

    Returns at "implement" depth:
      component:          id, name, layer, description, owner, tier
      i_own:              files + symbols at full detail (owned + descendants)
      i_consume:          upstream nodes as contracts only (no source)
      impact:             upstream_names, impact_score, cycles, step_size
      open_tasks:         tasks for this component
      applicable_rules:   layer rules (e.g. no frontend→database)
      decisions:          accepted ADRs for this component
      quality:            score 0-100, error_count, warning_count, fix_priority
      coordination_needed: callers that break if public interface changes
      adr_recommended:    whether an ADR is warranted

    After editing: call post_edit_sync, then check_code_quality to confirm score
    did not decrease.
    """
    try:
        return _ok(ctx_mod.get_context(project_path, component_id, task, depth))
    except NotFoundError as e:
        return _err(str(e), error_code="NOT_FOUND",
                    suggestion="Run list_components() to get valid component IDs.")
    except Exception as e:
        return _err(str(e))


# ─── Metrics & impact ─────────────────────────────────────────────────────────

@mcp.tool()
def check_code_quality(
    project_path: str,
    component_id: str,
    include_types: bool = False,
) -> str:
    """
    Run lint (ruff) and optional type-check (mypy) on all Python files in a
    component and return a structured quality report.

    Returns:
      score          — 0-100, 100 = no issues
      lint_issues    — ruff violations with file, line, code, message
      format_issues  — files that need ruff format
      type_issues    — mypy errors (only if include_types=True)
      hotspots       — files that are both complex AND have lint errors
      fix_priority   — ordered list of files to fix first
      summary        — one-line text: "N file(s), score X/100 — N error(s)"

    Agent workflow:
      1. check_code_quality(component_id) before starting work
      2. Fix any errors in fix_priority order
      3. post_edit_sync after each fix
      4. check_code_quality again to confirm clean

    Note: Only Python files are linted. TypeScript files need eslint (run
    `npm run lint` in the ui/ directory).
    """
    try:
        return _ok(quality_mod.get_quality_report(
            project_path, component_id, include_types=include_types
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_component_impact(project_path: str, component_id: str) -> str:
    """
    BFS impact analysis for a component. Returns upstream/downstream components
    and any dependency cycles.

    - upstream:     components that depend ON this one — they break if you change this
    - downstream:   components this one depends on
    - cycles:       dependency cycles involving this component
    - impact_score: count of upstream components (higher = riskier to change)

    Use before modifying a component to understand the blast radius of your change.
    Also use to find architectural problems: cycles indicate a design issue.
    """
    try:
        return _ok(impact_mod.get_component_impact(project_path, component_id))
    except NotFoundError as e:
        return _err(str(e))
    except Exception as e:
        return _err(str(e))


# ─── Post-edit sync ───────────────────────────────────────────────────────────

@mcp.tool()
def post_edit_sync(
    project_path: str,
    file_paths: list[str],
    reinfer_dependencies: bool = False,
    validate: bool = False,
) -> str:
    """
    Call this after editing or creating any source files. Keeps the ArchMap
    knowledge graph in sync with actual code.

    What it does for each file:
      - If the file is already mapped: re-extracts all symbols + signatures
      - If the file is NOT mapped: returns it in 'unmapped' list so you can
        decide which component it belongs to and call map_file()

    Args:
        file_paths:            List of files you just edited (relative paths).
        reinfer_dependencies:  If True, also re-scans all mapped files for
                               import changes and updates the dependency graph.
                               Use after adding/removing imports between components.
        validate:              If True, run architectural rule validation after
                               sync and return any violations in 'rule_violations'.
                               Use together with reinfer_dependencies=True to catch
                               newly introduced cross-layer dependency violations.

    Returns:
      {
        synced:          [file_path, ...],
        unmapped:        [{                  # files not yet in the graph
                            file_path,
                            suggested_component_id,    # best-guess component (or null)
                            suggested_component_name,
                            action                     # ready-to-call map_file() string
                          }],
        errors:          {file_path: msg},
        deps_added:      int,
        rule_violations: [...],              # if validate=True
        architecture_clean: bool             # if validate=True
      }

    For each item in 'unmapped': if suggested_component_id is not null, the agent
    can call map_file() with the suggested ID immediately. If null, the agent should
    choose the correct component or create a new one with add_component().

    Agent workflow:
      1. get_context(component_id, task="...")  ← before generating
      2. generate + edit files (Read / Edit / Write)
      3. post_edit_sync(file_paths=[...],                  ← after generating
                        reinfer_dependencies=True,
                        validate=True)
      4. For each item in 'unmapped': call map_file() with suggested or chosen component
      5. If rule_violations: fix generated code, repeat from step 2
    """
    synced: list[str] = []
    unmapped: list[str] = []
    errors: dict[str, str] = {}
    deps_added = 0
    rule_violations: list[dict] = []

    # Build component index once for suggestion heuristics
    try:
        _all_comps = arch_mod.list_components(project_path)
    except Exception:
        _all_comps = []

    def _suggest_component(file_path: str) -> dict | None:
        """
        Suggest the best-match component for an unmapped file based on path
        segments matching component names, descriptions, layers, and tags.
        Returns the best-match component dict or None if no confident match.
        """
        if not _all_comps:
            return None
        parts = file_path.lower().replace("\\", "/").split("/")
        # Layer keywords to component layer mapping
        layer_hints = {
            "frontend": "frontend", "ui": "frontend", "web": "frontend",
            "client": "frontend", "app": "frontend", "pages": "frontend",
            "components": "frontend", "views": "frontend", "src": "frontend",
            "backend": "backend", "server": "backend", "api": "backend",
            "routes": "backend", "handlers": "backend", "services": "backend",
            "controllers": "backend", "middleware": "backend",
            "db": "database", "database": "database", "models": "database",
            "migrations": "database", "schema": "database", "repos": "database",
            "infra": "infra", "docker": "infra", "k8s": "infra",
            "deploy": "infra", "ci": "infra", "terraform": "infra",
            "shared": "shared", "common": "shared", "utils": "shared",
            "lib": "shared", "helpers": "shared", "core": "shared",
            "test": "testing", "tests": "testing", "spec": "testing",
            "e2e": "testing", "__tests__": "testing",
        }
        best_comp: dict | None = None
        best_score = 0
        for comp in _all_comps:
            score = 0
            cname = comp.get("name", "").lower()
            clayer = comp.get("layer", "other")
            ctags  = [t.lower() for t in comp.get("tags", [])]
            for part in parts:
                if part in cname or cname in part:
                    score += 3
                if part in ctags:
                    score += 2
                inferred_layer = layer_hints.get(part)
                if inferred_layer and inferred_layer == clayer:
                    score += 1
            if score > best_score:
                best_score = score
                best_comp = comp
        return best_comp if best_score >= 2 else None

    for fp in file_paths:
        try:
            mapping = map_mod.get_file_component(project_path, fp)
            if not mapping:
                suggestion = _suggest_component(fp)
                unmapped.append({
                    "file_path": fp,
                    "suggested_component_id":   suggestion["id"]   if suggestion else None,
                    "suggested_component_name": suggestion["name"] if suggestion else None,
                    "suggested_layer":          suggestion.get("layer") if suggestion else None,
                    "action": (
                        f"map_file(file_path='{fp}', component_id='{suggestion['id']}')"
                        if suggestion else
                        f"map_file(file_path='{fp}', component_id='<choose>')"
                    ),
                })
                continue
            extracted = symbols_mod.extract_all_symbols(project_path, fp)
            metadata: dict = {
                "functions": extracted["symbols"],
                "symbol_details": extracted.get("details", []),
            }
            if extracted["language"]:
                metadata["language"] = extracted["language"]
            map_mod.update_file_metadata(project_path, fp, metadata)
            synced.append(fp)
        except Exception as e:
            errors[fp] = str(e)

    if reinfer_dependencies:
        try:
            result = infer_mod.infer_dependencies(project_path, overwrite_auto=False)
            deps_added = result.get("added", 0)
        except Exception as e:
            errors["__infer__"] = str(e)

    if validate:
        try:
            validation = rules_mod.validate_architecture(project_path)
            rule_violations = validation.get("violations", [])
        except Exception as e:
            errors["__validate__"] = str(e)

    response: dict = {
        "synced":   synced,
        "unmapped": unmapped,
        "errors":   errors,
        "deps_added": deps_added,
    }
    if validate:
        response["rule_violations"]    = rule_violations
        response["architecture_clean"] = len(rule_violations) == 0

    warnings: list[str] = []
    if rule_violations:
        warnings.append(
            f"{len(rule_violations)} architectural rule violation(s) introduced. "
            "Fix before committing: " + "; ".join(v.get("message", "") for v in rule_violations[:3])
        )

    return _ok(response, warnings=warnings)


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
      2. search_symbol()  — locate which file owns the symbol
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


# ─── Architectural rules ──────────────────────────────────────────────────────

@mcp.tool()
def validate_architecture(project_path: str) -> str:
    """
    Check all current dependencies against the configured architectural rules.
    Returns a list of violations — or confirms the architecture is clean.

    Rules are stored in .archmap/rules.json. Add rules with add_architecture_rule().
    Rule types:
      - no_dep:       from_layer cannot depend on to_layer
      - no_cycles:    no circular dependencies allowed
      - required_dep: from_layer must have at least one dep on to_layer

    Returns: {valid, rule_count, violation_count, violations[]}
    """
    try:
        return _ok(rules_mod.validate_architecture(project_path))
    except Exception as e:
        return _err(str(e))


def add_architecture_rule(
    project_path: str,
    rule_type: str,
    from_layer: str = "",
    to_layer: str = "",
    message: str = "",
) -> str:
    """
    Add an architectural constraint rule.

    rule_type options:
      - "no_dep"       — from_layer must not depend on to_layer
      - "no_cycles"    — no circular dependencies anywhere
      - "required_dep" — from_layer must have a dep on to_layer

    Example: add_architecture_rule("no_dep", "frontend", "database",
                                   "Frontend must not access DB directly")
    """
    try:
        kwargs: dict = {}
        if from_layer: kwargs["from_layer"] = from_layer
        if to_layer:   kwargs["to_layer"]   = to_layer
        if message:    kwargs["message"]     = message
        rule = rules_mod.add_rule(project_path, rule_type, **kwargs)
        return _ok(rule)
    except Exception as e:
        return _err(str(e))


def list_architecture_rules(project_path: str) -> str:
    """List all configured architectural rules for the project."""
    try:
        return _ok(rules_mod.load_rules(project_path))
    except Exception as e:
        return _err(str(e))


def delete_architecture_rule(project_path: str, rule_id: str) -> str:
    """Remove an architectural rule by ID."""
    try:
        deleted = rules_mod.delete_rule(project_path, rule_id)
        return _ok({"deleted": deleted, "rule_id": rule_id})
    except Exception as e:
        return _err(str(e))


# ─── Audit log ────────────────────────────────────────────────────────────────

@mcp.tool()
def check_integrity(project_path: str) -> str:
    """
    Health check of the architecture model against the actual repository.

    Run at session start to verify the knowledge graph is trustworthy before
    making architectural decisions based on it.

    Detects:
      stale_files:      Files whose content changed since last symbol sync
      missing_files:    Files in the graph that no longer exist on disk
      dangling_deps:    Dependencies pointing to non-existent component IDs
      unmapped_files:   Source files in the repo not yet mapped to any component
      orphan_plan_items: Plan items whose component was deleted

    When healthy=false, remediation:
      - stale_files   → post_edit_sync(file_paths=[...])
      - missing_files → unmap_file(file_path) for each
      - dangling_deps → remove_dependency(dep_id) for each
      - unmapped_files → map_file(file_path, component_id) for each
      - orphan_plans  → delete_plan_item or update_plan_item with valid component_id
    """
    try:
        result = cognition_mod.check_integrity(project_path)
        warnings: list[str] = []
        s = result.get("summary", {})
        if s.get("stale", 0):
            warnings.append(f"{s['stale']} file(s) are stale — call post_edit_sync.")
        if s.get("missing", 0):
            warnings.append(f"{s['missing']} mapped file(s) no longer exist on disk.")
        if s.get("dangling_deps", 0):
            warnings.append(f"{s['dangling_deps']} dependency(ies) reference deleted components.")
        if s.get("orphan_plans", 0):
            warnings.append(f"{s['orphan_plans']} plan item(s) reference deleted components.")
        return _ok(result, warnings=warnings)
    except Exception as e:
        return _err(str(e), error_code="ERROR",
                    suggestion="Ensure project is initialized with init_project.")


# ─── Architecture export ──────────────────────────────────────────────────────

import archmap.export as export_mod


@mcp.tool()
def export_architecture(project_path: str, format: str = "mermaid") -> str:
    """
    Export the architecture graph to a standard diagram format.

    Formats:
      mermaid  — Mermaid flowchart (paste into GitHub README, Notion, GitLab wikis)
      dot      — Graphviz DOT source (render: dot -Tpng -o arch.png arch.dot)
      c4       — Structurizr DSL approximation (C4 Container diagram)

    The Mermaid output is the most universally useful: paste it into a
    ```mermaid code block in any Markdown file for a live diagram.

    Returns: {format, diagram} where diagram is the raw diagram source string.
    """
    try:
        diagram = export_mod.export_architecture(project_path, format=format)
        return _ok({"format": format, "diagram": diagram})
    except ValueError as e:
        return _err(str(e), error_code="INVALID_FORMAT",
                    suggestion="Supported formats: mermaid, dot, c4")
    except Exception as e:
        return _err(str(e))


# ─── Architecture snapshot + diff ─────────────────────────────────────────────

import archmap.diff as diff_mod


@mcp.tool()
def snapshot_architecture(project_path: str, label: str = "") -> str:
    """
    Save a named snapshot of the current architecture state.

    Use this before making changes so you can diff later:
      1. snapshot_architecture(label="before-my-feature")
      2. ... make your changes ...
      3. diff_architecture(snapshot_label="before-my-feature")

    Snapshots are stored in .archmap/snapshots/ and survive across sessions.
    A snapshot captures: all components, all dependencies, and the timestamp.

    Args:
        label: Human-readable name for this snapshot (e.g. "main", "v1.2", "before-refactor").
               Defaults to "snapshot-<ISO timestamp>" if omitted.

    Returns: {snapshot_id, label, created_at, component_count, dependency_count}
    """
    try:
        result = diff_mod.snapshot_architecture(project_path, label=label or None)
        return _ok(result)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def diff_architecture(project_path: str, snapshot_label: str, snapshot_id: str = "") -> str:
    """
    Compare the current architecture against a previously saved snapshot.

    Shows what changed architecturally:
      - added_components:   new components not in the snapshot
      - removed_components: components that existed in snapshot but are gone now
      - changed_components: components whose name, layer, or description changed
      - added_deps:         new dependency edges
      - removed_deps:       dependency edges that were removed
      - changed_deps:       deps whose label, kind, or confidence changed

    Use this for:
      - PR descriptions: "Here is what this PR changed architecturally"
      - Code reviews: verify a change didn't add unexpected cross-layer dependencies
      - CI gates: fail the build if frontend unexpectedly gained a database dependency

    Args:
        snapshot_label: Label of the snapshot to compare against.
        snapshot_id:    Snapshot ID (alternative to label — use if labels are not unique).

    Returns: {snapshot, current, summary, added_components, removed_components,
              changed_components, added_deps, removed_deps, changed_deps, clean}
    """
    try:
        result = diff_mod.diff_architecture(
            project_path,
            snapshot_label=snapshot_label or None,
            snapshot_id=snapshot_id or None,
        )
        warnings: list[str] = []
        s = result.get("summary", {})
        if s.get("added_components", 0):
            warnings.append(f"{s['added_components']} new component(s) added since snapshot.")
        if s.get("removed_components", 0):
            warnings.append(f"{s['removed_components']} component(s) removed since snapshot.")
        if s.get("added_deps", 0):
            warnings.append(f"{s['added_deps']} new dependency(ies) added since snapshot.")
        if s.get("removed_deps", 0):
            warnings.append(f"{s['removed_deps']} dependency(ies) removed since snapshot.")
        return _ok(result, warnings=warnings)
    except FileNotFoundError as e:
        return _err(str(e), error_code="SNAPSHOT_NOT_FOUND",
                    suggestion="Run snapshot_architecture first to create a baseline.")
    except Exception as e:
        return _err(str(e))


# ─── Multi-agent collaboration ────────────────────────────────────────────────

@mcp.tool()
def claim_component(
    project_path: str,
    component_id: str,
    actor: str,
    task: str = "",
    ttl_minutes: int = 30,
) -> str:
    """
    Claim a component before working on it. Notifies other agents and humans
    that this component is being modified so they can coordinate.

    Claims are advisory (not hard locks). Other agents CAN still work on a
    claimed component, but SHOULD check list_active_work() first to avoid
    conflicts.

    Call release_component() when done. Claims expire automatically after
    ttl_minutes (default 30) if not released or refreshed via agent_heartbeat().

    Args:
        actor:       Your identity. Use a stable name: "claude-code", "dev:alice",
                     "agent:refactor-bot". Shows up in list_active_work().
        task:        What you are doing, in plain text. Visible to all collaborators.
        ttl_minutes: How long to hold the claim. Default 30 minutes.

    Workflow:
      1. list_active_work()            ← check if anyone else is working here
      2. claim_component(actor, task)  ← announce your intent
      3. get_context()      ← get full context
      4. ... generate and edit code ...
      5. post_edit_sync(validate=True)
      6. release_component(actor)      ← done

    Returns: {claim_id, component_id, actor, task, claimed_at, expires_at}
    """
    try:
        result = session_mod.claim_component(
            project_path, component_id, actor,
            task=task, ttl_minutes=ttl_minutes,
        )
        return _ok(result)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def release_component(project_path: str, component_id: str, actor: str) -> str:
    """
    Release your claim on a component when you are done working on it.
    Other agents/humans will see this component as available again.

    Args:
        actor: Must match the actor you used in claim_component().

    Returns: {released: bool, claim_id: str | None}
    """
    try:
        return _ok(session_mod.release_component(project_path, component_id, actor))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_active_work(project_path: str) -> str:
    """
    Show what every agent and human is currently working on across this project.

    Call this BEFORE starting work on any component to avoid conflicts.
    Returns all non-expired claims with time remaining until expiry.

    Returns:
      {
        claims:       [{claim_id, component_id, component_name, actor, task,
                        claimed_at, expires_at, minutes_remaining}],
        by_component: {component_id: [actors]},   ← who owns what
        by_actor:     {actor: [component_ids]}    ← what each agent owns
      }

    A claim means "I am currently modifying this component."
    No claims means the project is idle — safe to start work anywhere.
    """
    try:
        result = session_mod.list_active_work(project_path)
        warnings: list[str] = []
        if not result["claims"]:
            warnings.append("No active work claims — project is idle.")
        return _ok(result, warnings=warnings)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_changes_since(
    project_path: str,
    since: str,
    actor: str = "",
    entity_type: str = "",
) -> str:
    """
    Get all architecture changes made since a given timestamp.

    Use this to stay in sync when sharing a project with other agents or humans:
    poll this tool periodically to detect changes made by others, then update
    your understanding of the architecture accordingly.

    Args:
        since:       ISO 8601 timestamp — return only changes after this point.
                     Example: "2026-03-26T10:00:00+00:00"
                     Use the `timestamp` field from any previous tool response as input.
        actor:       Filter to changes by a specific actor. Empty = all actors.
        entity_type: Filter by entity type: component | dependency | file | plan_item

    Returns:
      {
        since:    str,
        changes:  [{id, timestamp, actor, tool, entity_type, entity_id,
                    change_type, summary}],
        count:    int,
        actors:   [str]   ← unique list of who made changes in this window
      }

    Suggested polling interval: every 60 seconds when actively collaborating.
    """
    try:
        all_changes = audit_mod.get_audit_log(
            project_path,
            last_n=500,
            entity_type=entity_type or None,
            actor=actor or None,
        )
        # Filter to changes after `since`
        try:
            from datetime import datetime, timezone
            since_dt = datetime.fromisoformat(since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            filtered = [
                c for c in all_changes
                if datetime.fromisoformat(c["timestamp"]) > since_dt
            ]
        except (ValueError, KeyError):
            filtered = all_changes

        actors = sorted({c.get("actor", "") for c in filtered if c.get("actor")})
        return _ok({
            "since":   since,
            "changes": filtered,
            "count":   len(filtered),
            "actors":  actors,
        })
    except Exception as e:
        return _err(str(e))


# ─── Architecture Decision Records (ADRs) ────────────────────────────────────

@mcp.tool()
def add_decision(
    project_path: str,
    component_id: str,
    title: str,
    context: str = "",
    decision: str = "",
    consequences: str = "",
    alternatives: str = "",
    links: str = "",
    status: str = "proposed",
) -> str:
    """
    Record an Architecture Decision Record (ADR) linked to a component.

    ADRs capture *why* a design choice was made — context, decision, trade-offs,
    and alternatives considered. They prevent re-litigation of settled decisions
    and dramatically reduce the onboarding cost for new engineers and AI agents.

    Args:
        component_id:  Component this decision belongs to.
        title:         Short title: "Use OS-level locks for multi-process safety"
        context:       Problem / forces that required a decision.
        decision:      What was decided and why.
        consequences:  Trade-offs, risks, positive outcomes.
        alternatives:  Other options that were considered and rejected.
        links:         Comma-separated URLs (issues, RFCs, docs).
        status:        proposed | accepted | deprecated | superseded

    ADR lifecycle: proposed → accepted → deprecated | superseded
    Prefer deprecated/superseded over delete — decision history is valuable.
    """
    try:
        link_list = [l.strip() for l in links.split(",") if l.strip()] if links else []
        result = decisions_mod.add_decision(
            project_path,
            component_id=component_id,
            title=title,
            context=context,
            decision=decision,
            consequences=consequences,
            alternatives=alternatives,
            links=link_list,
            status=status,
        )
        return _ok(result)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_decisions(
    project_path: str,
    component_id: str = "",
    status: str = "",
) -> str:
    """
    List Architecture Decision Records, optionally filtered.

    Args:
        component_id: Filter to a specific component. Empty = all components.
        status:       Filter by status: proposed | accepted | deprecated | superseded.
                      Empty = all statuses.

    Returns list of full ADR records.
    """
    try:
        results = decisions_mod.list_decisions(
            project_path,
            component_id=component_id,
            status=status,
        )
        return _ok({"decisions": results, "count": len(results)})
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def update_decision(
    project_path: str,
    decision_id: str,
    title: str = "",
    status: str = "",
    context: str = "",
    decision: str = "",
    consequences: str = "",
    alternatives: str = "",
    links: str = "",
    superseded_by: str = "",
) -> str:
    """
    Update an existing ADR. Only non-empty arguments are applied.

    To mark as superseded: set status='superseded' and superseded_by='<new_adr_id>'.
    To mark as accepted:   set status='accepted'.
    To mark as deprecated: set status='deprecated'.

    links: comma-separated URLs (replaces existing links if provided).
    """
    try:
        link_list = [l.strip() for l in links.split(",") if l.strip()] if links else None
        result = decisions_mod.update_decision(
            project_path,
            decision_id=decision_id,
            title=title,
            status=status,
            context=context,
            decision=decision,
            consequences=consequences,
            alternatives=alternatives,
            links=link_list,
            superseded_by=superseded_by,
        )
        return _ok(result)
    except KeyError as e:
        return _err(str(e), error_code="NOT_FOUND", entity_type="decision", entity_id=decision_id)
    except Exception as e:
        return _err(str(e))


# ─── Multi-level graph tools ──────────────────────────────────────────────────

@mcp.tool()
def get_domain_map(project_path: str) -> str:
    """
    L1/L2 orientation view — system node + all domain nodes + cross-domain edges.
    Returns each domain's contract and child count.

    This is the recommended FIRST call at the start of any agent session.
    It tells you: what domains exist, what data each owns, how they connect.
    After this, drill into a domain with describe_node() or get_context().
    """
    try:
        return _ok(ctx_mod.get_domain_map(project_path))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def describe_node(
    project_path: str,
    node_id: str,
    show_files: bool = False,
) -> str:
    """
    Drill-down view of a node at any level (1=system, 2=domain, 3=service, 4=component, 5=module).
    Returns: node metadata, declared contract, direct children, outgoing/incoming edges.
    Set show_files=True to also list files owned by this node and its descendants.

    Use this to navigate the hierarchy: domain → service → component → module.
    """
    try:
        return _ok(ctx_mod.describe_node(project_path, node_id, show_files))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_children(project_path: str, parent_id: str) -> str:
    """
    List the direct child nodes of a parent in the hierarchy.
    Use to navigate: domain → services, service → components, component → modules.
    """
    try:
        return _ok(arch_mod.list_children(project_path, parent_id))
    except Exception as e:
        return _err(str(e))


# ─── Contract tools ───────────────────────────────────────────────────────────

@mcp.tool()
def declare_contract(
    project_path: str,
    node_id: str,
    node_level: int = 4,
    commands: list[dict] | None = None,
    queries: list[dict] | None = None,
    events_emitted: list[dict] | None = None,
    events_consumed: list[dict] | None = None,
    data_owned: list[dict] | None = None,
    data_read: list[dict] | None = None,
    api_spec_url: str = "",
    sla: str = "",
) -> str:
    """
    Declare or replace the formal contract for a node.

    A contract specifies:
      commands        — mutations this node accepts (changes state)
      queries         — reads this node accepts (returns data)
      events_emitted  — facts this node publishes asynchronously
      events_consumed — events this node subscribes to
      data_owned      — data types this node is the authoritative source for
      data_read       — data types this node reads but does not own
      api_spec_url    — link to OpenAPI spec or proto file (L3 services)
      sla             — service-level agreement string

    Each command/query is a dict: {name, description, input_type, output_type, stability}
    Each event is a dict: {name, description, payload_type, stability}
    Each data type is a dict: {type_name, description, schema, stability, authoritative}

    Once declared, callers see this contract instead of source code — enabling
    context isolation during multi-agent development.
    """
    try:
        return _ok(contracts_mod.declare_contract(
            project_path, node_id, node_level,
            commands or [], queries or [],
            events_emitted or [], events_consumed or [],
            data_owned or [], data_read or [],
            api_spec_url, sla,
        ))
    except NotFoundError as e:
        return _err(str(e), "NOT_FOUND", "node", node_id)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_contract(project_path: str, node_id: str) -> str:
    """
    Get the declared contract for a node.
    Returns an empty structure (declared=false) if no contract has been declared yet.
    """
    try:
        return _ok(contracts_mod.get_contract(project_path, node_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_contracts(project_path: str, node_level: int | None = None) -> str:
    """
    List all declared contracts. Optionally filter by node_level (1-5).
    Returns the full contract for each node that has one.
    """
    try:
        return _ok(contracts_mod.list_contracts(project_path, node_level))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def check_contract_break(
    project_path: str,
    node_id: str,
    operation_name: str,
    new_input_type: str = "",
    new_output_type: str = "",
) -> str:
    """
    Check whether changing an operation's signature would break the declared contract.

    Returns:
      breaking          — True if the change conflicts with the declared contract
      reason            — what specifically conflicts
      callers           — dependency edges that reference this operation (would break)
      caller_count      — number of callers

    Use BEFORE changing any symbol that is in a component's public_api list.
    Example: check_contract_break(node_id, "create_plan_item", new_input_type="CreatePlanReqV2")
    """
    try:
        return _ok(contracts_mod.check_contract_break(
            project_path, node_id, operation_name, new_input_type, new_output_type
        ))
    except Exception as e:
        return _err(str(e))


# ─── Semantic dependency annotation ──────────────────────────────────────────

@mcp.tool()
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
) -> str:
    """
    Enrich an existing dependency edge with semantic metadata.
    Only the fields you provide are updated; others remain unchanged.

    edge_type:       command | query | event | import | data_read | data_write | invoke | stream
    edge_level:      domain | service | component | module
    interface_points: specific operations/endpoints/functions used across this edge
                      e.g. ["POST /api/components", "GET /api/architecture"]
                      e.g. ["create_plan_item", "list_plan_items"]
    payload_types:   data types that flow across this edge (e.g. ["PlanItem", "Component[]"])
    stability:       stable | internal | experimental | deprecated
    async_flag:      True for events/queues, False for synchronous calls
    crosses_boundary: True if this edge crosses a level boundary (service or domain)
    """
    try:
        return _ok(arch_mod.annotate_dependency(
            project_path, dependency_id,
            edge_type=edge_type, edge_level=edge_level,
            crosses_boundary=crosses_boundary, async_flag=async_flag,
            direction=direction, interface_points=interface_points,
            payload_types=payload_types, stability=stability, label=label,
        ))
    except NotFoundError as e:
        return _err(str(e), "NOT_FOUND", "dependency", dependency_id)
    except Exception as e:
        return _err(str(e))


# ─── Public API management ────────────────────────────────────────────────────

@mcp.tool()
def promote_to_contract(
    project_path: str,
    component_id: str,
    symbol_names: list[str],
) -> str:
    """
    Mark symbols as part of a component's stable public API.

    Once promoted:
    - Future changes to these symbols trigger contract-break warnings
    - Other agents see these symbols in get_context() as the component's interface
    - check_contract_break() will detect signature changes against these symbols

    Use after implementing a feature to declare its public surface.
    """
    try:
        return _ok(arch_mod.promote_to_contract(project_path, component_id, symbol_names))
    except NotFoundError as e:
        return _err(str(e), "NOT_FOUND", "component", component_id)
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def remap_files_to_node(
    project_path: str,
    file_paths: list[str],
    target_component_id: str,
) -> str:
    """
    Move files from one component to a different component.
    Used when splitting a large component into sub-components.

    Returns {remapped: [file_paths], not_found: [file_paths], target}.
    After remapping, call post_edit_sync on the moved files to update the symbol index.
    """
    try:
        return _ok(arch_mod.remap_files_to_node(project_path, file_paths, target_component_id))
    except NotFoundError as e:
        return _err(str(e), "NOT_FOUND", "component", target_component_id)
    except Exception as e:
        return _err(str(e))


# ─── Migration ────────────────────────────────────────────────────────────────

@mcp.tool()
def bootstrap_multilevel_graph(project_path: str) -> str:
    """
    One-shot migration: transform the flat component graph into a 5-level hierarchy.

    Creates:
      L1 System node (ArchMap)
      L2 Domain nodes (User Interface, Access Protocol, Architecture Graph, Persistence)
      Promotes existing components to their correct levels with parent_id
      Splits "Core Engine" into 4 L4 components (Architecture CRUD, Planning Engine,
        Mapping Engine, Scanner)
      Annotates all existing dependency edges with semantic types (edge_type,
        interface_points, payload_types, stability, crosses_boundary)
      Declares contracts for Storage Layer, REST API, and Data Models

    SAFE TO RE-RUN: nodes/edges already annotated are skipped.

    Call this once after upgrading ArchMap to the multi-level graph version.
    """
    try:
        return _ok(migration_mod.bootstrap_multilevel_graph(project_path))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def reset_graph(project_path: str) -> str:
    """
    Wipe the architecture graph and file mappings back to empty defaults.

    Clears:
      - All components and dependencies (architecture.json)
      - All file-to-component mappings and symbols (mappings.json)
      - All interface contracts (stored inside architecture.json)

    Preserves:
      - meta.json  (project name, init timestamp)
      - plan.json  (plan items / tasks — these belong to the project, not the graph)
      - decisions.json  (ADRs — historical record, keep across rebuilds)

    Use this before running a full agent-driven bootstrap so you start from a
    clean slate without losing project metadata.

    Returns a summary of what was cleared.
    """
    try:
        from archmap.store import reset_graph as _reset
        return _ok(_reset(project_path))
    except Exception as e:
        return _err(str(e))


# ─── Progressive knowledge tools ─────────────────────────────────────────────

import archmap.completeness as completeness_mod
import archmap.navigation as navigation_mod


@mcp.tool()
def get_knowledge_completeness(project_path: str, component_id: str = "") -> str:
    """
    Score how well-documented a component is in the knowledge graph (0–100).

    The score reflects how much structural knowledge has been captured —
    not code quality, but graph completeness:
      description, declared contract, public_api, data_owned, mapped files,
      synced symbols, quality score ≥80, accepted ADRs.

    When quality_score is not yet fetched, the quality signal is omitted and
    the remaining signals are renormalized to 100.

    Args:
        component_id: Component to score. Omit (or pass "") to score ALL nodes,
                      sorted by score ascending (gaps first).

    Returns (single):
        {score, component_id, name, signals: {...}, missing: [...]}

    Returns (all):
        [{score, component_id, name, level, layer, missing}, ...]
    """
    try:
        if component_id:
            return _ok(completeness_mod.score_component(project_path, component_id))
        return _ok(completeness_mod.score_all_components(project_path))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def drill_into(project_path: str, task: str, start_id: str = "") -> str:
    """
    Navigate from a task description to the right component.

    Uses keyword matching against component names, descriptions, and declared
    contracts to suggest the best L2 → L3 → L4 path for the given task.
    No ML — pure keyword overlap scoring.

    Args:
        task:     Free-text description of what you want to work on.
                  Example: "add OAuth login", "fix cycle in graph store"
        start_id: Optional — constrain search to descendants of this node
                  (e.g. an L2 domain ID to narrow within one domain).

    Returns:
        {
          path:                [{id, name, level, layer, score, why}],
          suggested_component: {id, name, level, layer},
          alternatives:        [{id, name, level, layer, score}],
          query_tokens:        [str]
        }
    """
    try:
        return _ok(navigation_mod.drill_into(project_path, task, start_id))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_knowledge_gaps(project_path: str, min_score: int = 70) -> str:
    """
    Surface underdocumented components, unmapped files, and stale symbols.

    Use this to find where the knowledge graph is thin before starting a new
    feature or onboarding a new agent. Gaps cause context truncation and
    inaccurate impact analysis.

    Args:
        min_score: Components scoring below this completeness threshold are
                   reported as gaps. Default 70.

    Returns:
        {
          total_components:    int,
          below_threshold:     int,
          threshold:           int,
          gaps:                [{component_id, name, level, layer, score, missing}],
          unmapped_source_files: [str],
          stale_symbols:       [{file_path, issue}]
        }
    """
    try:
        return _ok(navigation_mod.get_knowledge_gaps(project_path, min_score))
    except Exception as e:
        return _err(str(e))


# ─── Hierarchical task tools ──────────────────────────────────────────────────

@mcp.tool()
def add_task(
    project_path: str,
    title: str,
    description: str = "",
    component_id: str = "",
    parent_task_id: str = "",
    priority: str = "medium",
    created_by: str = "agent",
    expects_files_added: list[str] = [],
    expects_files_modified: list[str] = [],
    expects_symbols_added: list[str] = [],
    expects_symbols_removed: list[str] = [],
    expects_dependencies_added: list[str] = [],
    tags: list[str] = [],
) -> str:
    """
    Create a task, optionally as a child of an existing task.

    Tasks mirror the node hierarchy: root tasks are user requirements; agents
    decompose them into sub-tasks scoped to progressively finer components.
    The depth is not hardcoded — agents decide how deep to go.

    Args:
        title:                      Short imperative description.
        description:                Full context, acceptance criteria, design notes.
        component_id:               Node this task is scoped to. Empty = unlinked.
        parent_task_id:             Parent task ID. Empty = root requirement.
        priority:                   low | medium | high | critical
        created_by:                 Actor identity (orchestrator, worker agent name, human).
        expects_files_added:        Files that should exist in graph when done.
        expects_files_modified:     Files that should be updated in graph when done.
        expects_symbols_added:      Symbol names that should appear in graph when done.
        expects_symbols_removed:    Symbol names that should be gone when done.
        expects_dependencies_added: "comp_a → comp_b" pairs to add.
        tags:                       Arbitrary labels.

    Returns the full task record including its generated ID.
    """
    try:
        expects = {
            "files_added":        expects_files_added,
            "files_modified":     expects_files_modified,
            "symbols_added":      expects_symbols_added,
            "symbols_removed":    expects_symbols_removed,
            "dependencies_added": expects_dependencies_added,
            "contract_changes":   {},
        }
        return _ok(plan_mod.add_task(
            project_path,
            title=title,
            description=description,
            component_id=component_id or None,
            parent_task_id=parent_task_id or None,
            priority=priority,
            created_by=created_by,
            expects=expects,
            tags=tags,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def decompose_task(
    project_path: str,
    parent_task_id: str,
    subtasks: list[dict],
    created_by: str = "agent",
) -> str:
    """
    Decompose a task into subtasks in a single call — the core orchestration primitive.

    Each subtask dict may contain:
      title (required), description, component_id, priority,
      tags, expects (same structure as add_task expects_* fields but as a nested dict).

    Typical orchestrator pattern:
      1. Receive high-level task from user
      2. Call get_domain_map() to understand the architecture
      3. Call decompose_task() to create worker-level subtasks on specific components
      4. Workers call get_context(component_id=...) + implement + complete_task()

    Multi-agent pattern:
      - Orchestrator calls decompose_task() to create one subtask per worker
      - Each worker claims its subtask via claim_component(), does the work, completes it
      - Orchestrator polls get_task_tree() to track overall progress
      - When all subtasks done, parent auto-completes

    Args:
        parent_task_id: Task to break down.
        subtasks:       List of subtask descriptors.
        created_by:     Actor performing decomposition (usually "orchestrator").

    Returns:
        {parent: task_record, created: [task_record, ...]}
    """
    try:
        return _ok(plan_mod.decompose_task(project_path, parent_task_id, subtasks, created_by))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def complete_task(
    project_path: str,
    task_id: str,
    completed_by: str = "agent",
    note: str = "",
) -> str:
    """
    Mark a task done and propagate progress up the task tree.

    When all subtasks of a parent are done, the parent is auto-completed.
    Call this after post_edit_sync confirms the graph is up to date.

    Recommended workflow:
      1. Implement the change
      2. post_edit_sync(file_paths=[...])
      3. check_task_drift(task_id)     ← verify expects were met
      4. complete_task(task_id)        ← close and propagate

    Args:
        task_id:      Task to complete.
        completed_by: Actor identity (worker agent name, human).
        note:         Optional completion note appended to description.

    Returns:
        {task, parent_updated: bool, parents_auto_completed: [task_id]}
    """
    try:
        return _ok(plan_mod.complete_task(project_path, task_id, completed_by, note))
    except KeyError as e:
        return _err(str(e), error_code="NOT_FOUND")
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def get_task_tree(
    project_path: str,
    task_id: str,
) -> str:
    """
    Return a task and all its descendants as a nested tree.

    Use this for orchestrators to track overall progress across all workers,
    or for users to see the full decomposition of a requirement.

    Returns:
        {task fields..., children: [{task fields..., children: [...]}, ...]}
    """
    try:
        return _ok(plan_mod.get_task_tree(project_path, task_id))
    except KeyError as e:
        return _err(str(e), error_code="NOT_FOUND")
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def check_task_drift(
    project_path: str,
    task_id: str,
) -> str:
    """
    Compare a task's `expects` specification against actual graph state.

    Run this after post_edit_sync to confirm implementation matches the promise.
    If drift=true, the expected symbols/files/deps are not yet in the graph —
    either the sync is incomplete or the implementation didn't match the plan.

    Returns:
        {
          task_id, title, expects, drift: bool,
          drift_items: ["symbols not found: login, logout", ...],
          actual: {symbols_found, symbols_missing, files_found, files_missing,
                   deps_found, deps_missing}
        }
    """
    try:
        return _ok(plan_mod.check_task_drift(project_path, task_id))
    except KeyError as e:
        return _err(str(e), error_code="NOT_FOUND")
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def list_tasks(
    project_path: str,
    component_id: str = "",
    parent_task_id: str = "_root_",
    status: str = "",
    priority: str = "",
    include_subtasks: bool = False,
) -> str:
    """
    List tasks with optional filtering.

    Args:
        component_id:    Filter to tasks scoped to this component.
        parent_task_id:  "_root_" (default) = only top-level requirements.
                         "" = all tasks regardless of depth.
                         A task_id = direct children of that task.
        status:          todo | in_progress | done | blocked | cancelled
        priority:        low | medium | high | critical
        include_subtasks: When parent_task_id is a task ID, also include all
                          descendants (not just direct children).
    """
    try:
        return _ok(plan_mod.list_tasks(
            project_path,
            component_id=component_id or None,
            parent_task_id=parent_task_id if parent_task_id != "" else None,
            status=status or None,
            priority=priority or None,
            include_subtasks=include_subtasks,
        ))
    except Exception as e:
        return _err(str(e))


@mcp.tool()
def update_task(
    project_path: str,
    task_id: str,
    title: str = "",
    description: str = "",
    status: str = "",
    priority: str = "",
    component_id: str = "",
) -> str:
    """
    Update mutable task fields.

    Status values: todo | in_progress | done | blocked | cancelled
    Use complete_task() instead of setting status=done manually — it propagates
    progress to parent tasks.
    """
    try:
        kwargs = {}
        if title:        kwargs["title"]        = title
        if description:  kwargs["description"]   = description
        if status:       kwargs["status"]        = status
        if priority:     kwargs["priority"]      = priority
        if component_id: kwargs["component_id"]  = component_id
        return _ok(plan_mod.update_task(project_path, task_id, **kwargs))
    except KeyError as e:
        return _err(str(e), error_code="NOT_FOUND")
    except Exception as e:
        return _err(str(e))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run(transport="stdio")
