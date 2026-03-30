"""
Agent work-context engine — level-aware, scope-isolating context queries.

Core principle: agents should see their own node at full resolution and
every other node only as the contract it exposes. This prevents agents from
accidentally depending on implementation details across boundaries.

Key tools:
  get_context      — unified pre-edit context (self + contracts + quality + tasks + rules)
  get_domain_map   — L2 domain overview (entry point for all agent sessions)
  describe_node    — drill-down from any level into its children
"""
from __future__ import annotations
from archmap.repo import load_arch, load_mappings, load_plan
from archmap.contracts import get_contract
import archmap.impact as impact_mod
import archmap.planning as plan_mod
import archmap.quality as quality_mod
import archmap.rules as rules_mod
import archmap.decisions as decisions_mod


# ─── Step-size classification ─────────────────────────────────────────────────
#
# atomic    — 1 file, 0 interface changes
# local     — ≤1 component, no cross-component interface changes
# bounded   — 2-3 components, touches a stable interface
# service   — crosses a service (L3) boundary
# cross     — crosses a domain (L2) boundary; ADR likely required

_STEP_LABELS = {
    "atomic": "Change stays inside one file, zero interface impact.",
    "local":  "Change stays inside one component, no callers need updating.",
    "bounded": "Touches a stable interface; callers in 2-3 components must be updated.",
    "service": "Crosses a service boundary — network contract may need versioning.",
    "cross":   "Crosses a domain boundary — data ownership or event schema changes. ADR recommended.",
}


def _classify_step(
    unique_levels: set[int],
    unique_components: set[str],
    crosses_service: bool,
    crosses_domain: bool,
) -> str:
    if crosses_domain:
        return "cross"
    if crosses_service:
        return "service"
    if len(unique_components) > 2:
        return "bounded"
    if len(unique_components) == 2:
        return "bounded"
    if len(unique_components) == 1:
        return "local"
    return "atomic"


# ─── get_work_context ─────────────────────────────────────────────────────────

def get_work_context(
    project_path: str,
    node_id: str,
    task: str = "",
) -> dict:
    """
    Return a scope-isolated context for an agent about to work on `node_id`.

    Response structure:
      working_on        — node metadata
      i_own             — files + symbols at full detail
      i_consume         — sibling/upstream nodes shown as contracts only
      step_size         — atomic | local | bounded | service | cross
      coordination_needed — other nodes that must be notified of interface changes
      adr_recommended   — whether this warrants an Architecture Decision Record
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)

    by_id = {c["id"]: c for c in arch.get("components", [])}
    node = by_id.get(node_id)
    if not node:
        return {"error": f"Node not found: {node_id!r}"}

    node_level = node.get("level", 4)
    parent_id = node.get("parent_id", "")

    # ── Owned files + symbols ──────────────────────────────────────────────────
    # Collect all descendant node IDs (children, grandchildren) to gather their files too
    descendant_ids = _collect_descendants(arch, node_id)
    owned_node_ids = {node_id} | descendant_ids

    owned_files: list[dict] = []
    for fp, rec in mappings.get("files", {}).items():
        if rec.get("component_id") in owned_node_ids:
            syms = [
                {
                    "name": s.get("display_name", s.get("name", "")),
                    "kind": s.get("kind", "function"),
                    "signature": s.get("signature", ""),
                    "visibility": s.get("visibility", "public"),
                    "is_entry_point": s.get("is_entry_point", False),
                    "in_public_api": s.get("name", "") in node.get("public_api", []),
                }
                for s in rec.get("symbols", [])
            ]
            owned_files.append({
                "file_path": fp,
                "component_id": rec.get("component_id"),
                "language": rec.get("language", ""),
                "symbols": syms,
                "symbol_count": len(syms),
            })

    # ── Dependencies outgoing from this node ───────────────────────────────────
    deps = arch.get("dependencies", [])
    outgoing = [d for d in deps if d.get("from_component") in owned_node_ids]
    incoming = [d for d in deps if d.get("to_component") in owned_node_ids]

    # ── consumed contracts — other nodes as black boxes ────────────────────────
    consumed_ids = {d["to_component"] for d in outgoing if d["to_component"] not in owned_node_ids}
    consumed: list[dict] = []
    for cid in consumed_ids:
        dep = next((d for d in outgoing if d["to_component"] == cid), {})
        contract = get_contract(project_path, cid)
        cnode = by_id.get(cid, {})
        consumed.append({
            "node_id": cid,
            "node_name": cnode.get("name", cid),
            "level": cnode.get("level", 4),
            "protocol": cnode.get("protocol", ""),
            "port": cnode.get("port"),
            "edge_type": dep.get("edge_type", "invoke"),
            "interface_points": dep.get("interface_points", []),
            "payload_types": dep.get("payload_types", []),
            "stability": dep.get("stability", "stable"),
            "contract": {
                "commands": contract.get("commands", []),
                "queries": contract.get("queries", []),
                "events_emitted": contract.get("events_emitted", []),
                "data_owned": contract.get("data_owned", []),
                "api_spec_url": contract.get("api_spec_url", ""),
                "sla": contract.get("sla", ""),
                "declared": contract.get("declared", False),
            },
        })

    # ── coordination: who depends on this node (would break if interface changes) ──
    coordination: list[dict] = []
    for d in incoming:
        caller_id = d["from_component"]
        if caller_id in owned_node_ids:
            continue
        caller = by_id.get(caller_id, {})
        coordination.append({
            "node_id": caller_id,
            "node_name": caller.get("name", caller_id),
            "level": caller.get("level", 4),
            "owner": caller.get("owner", ""),
            "interface_points_used": d.get("interface_points", []),
            "stability": d.get("stability", "stable"),
            "reason": "Depends on this node — must be updated if public interface changes",
        })

    # ── step size ──────────────────────────────────────────────────────────────
    touched_levels = {node.get("level", 4)}
    touched_comps = set(owned_node_ids)
    for d in outgoing:
        tc = by_id.get(d["to_component"])
        if tc:
            touched_levels.add(tc.get("level", 4))
            touched_comps.add(d["to_component"])

    crosses_service = any(by_id.get(d["to_component"], {}).get("level", 4) <= 3 for d in outgoing)
    crosses_domain  = any(by_id.get(d["to_component"], {}).get("level", 4) <= 2 for d in outgoing)
    step = _classify_step(touched_levels, touched_comps, crosses_service, crosses_domain)

    return {
        "working_on": {
            "node_id": node_id,
            "name": node.get("name"),
            "level": node_level,
            "layer": node.get("layer"),
            "description": node.get("description"),
            "public_api": node.get("public_api", []),
            "data_owned": node.get("data_owned", []),
            "stability": node.get("stability", "stable"),
            "owner": node.get("owner", ""),
            "task": task,
        },
        "i_own": {
            "files": owned_files,
            "file_count": len(owned_files),
            "descendant_nodes": list(descendant_ids),
        },
        "i_consume": consumed,
        "coordination_needed": coordination,
        "step_size": step,
        "step_explanation": _STEP_LABELS.get(step, ""),
        "adr_recommended": step in ("cross",),
    }


# ─── get_change_surface ───────────────────────────────────────────────────────

# ─── get_domain_map ───────────────────────────────────────────────────────────

def get_domain_map(project_path: str) -> dict:
    """
    L1/L2 orientation view — system and domains only.
    Shows inter-domain dependencies as high-level contracts, not component internals.
    This is the recommended first call at the start of any agent session.
    """
    arch = load_arch(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}
    deps = arch.get("dependencies", [])

    system_nodes = [c for c in arch.get("components", []) if c.get("level", 4) == 1]
    domain_nodes = [c for c in arch.get("components", []) if c.get("level", 4) == 2]

    # Child counts per domain
    child_counts: dict[str, int] = {}
    for c in arch.get("components", []):
        pid = c.get("parent_id", "")
        if pid:
            child_counts[pid] = child_counts.get(pid, 0) + 1

    # Cross-domain edges only
    def _domain_of(node_id: str) -> str:
        node = by_id.get(node_id)
        if not node:
            return ""
        if node.get("level", 4) <= 2:
            return node_id
        pid = node.get("parent_id", "")
        while pid:
            p = by_id.get(pid)
            if not p:
                break
            if p.get("level", 4) <= 2:
                return pid
            pid = p.get("parent_id", "")
        return node_id

    domain_edges: list[dict] = []
    seen_pairs: set[tuple] = set()
    for d in deps:
        fd = _domain_of(d["from_component"])
        td = _domain_of(d["to_component"])
        if fd and td and fd != td:
            pair = (fd, td)
            if pair not in seen_pairs:
                seen_pairs.add(pair)
                domain_edges.append({
                    "from_domain": fd,
                    "from_name": by_id.get(fd, {}).get("name", fd),
                    "to_domain": td,
                    "to_name": by_id.get(td, {}).get("name", td),
                    "edge_types": list({
                        dep.get("edge_type", "invoke")
                        for dep in deps
                        if _domain_of(dep["from_component"]) == fd
                        and _domain_of(dep["to_component"]) == td
                    }),
                })

    return {
        "system": system_nodes,
        "domains": [
            {
                **d,
                "child_count": child_counts.get(d["id"], 0),
                "contract": get_contract(project_path, d["id"]),
            }
            for d in domain_nodes
        ],
        "cross_domain_edges": domain_edges,
        "summary": (
            f"{len(system_nodes)} system node(s), {len(domain_nodes)} domain(s), "
            f"{len(domain_edges)} cross-domain integration(s)"
        ),
    }


# ─── describe_node ────────────────────────────────────────────────────────────

def describe_node(
    project_path: str,
    node_id: str,
    show_files: bool = False,
) -> dict:
    """
    Drill-down view of a node: its metadata, direct children, contract,
    and edges to/from sibling nodes (not grandchildren).
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}

    node = by_id.get(node_id)
    if not node:
        return {"error": f"Node not found: {node_id!r}"}

    # Direct children
    children = [c for c in arch.get("components", []) if c.get("parent_id") == node_id]

    # Edges where from or to is this node (not a descendant)
    deps = arch.get("dependencies", [])
    desc_ids = _collect_descendants(arch, node_id) | {node_id}
    outgoing = [d for d in deps if d["from_component"] in desc_ids
                and d["to_component"] not in desc_ids]
    incoming = [d for d in deps if d["to_component"] in desc_ids
                and d["from_component"] not in desc_ids]

    result = {
        "node": node,
        "contract": get_contract(project_path, node_id),
        "children": children,
        "child_count": len(children),
        "outgoing_edges": [_edge_summary(d, by_id) for d in outgoing],
        "incoming_edges": [_edge_summary(d, by_id) for d in incoming],
    }

    if show_files:
        files = [
            {"file_path": fp, "language": rec.get("language", ""),
             "symbol_count": len(rec.get("symbols", []))}
            for fp, rec in mappings.get("files", {}).items()
            if rec.get("component_id") in desc_ids
        ]
        result["files"] = files

    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _collect_descendants(arch: dict, node_id: str) -> set[str]:
    """BFS to find all descendant node IDs."""
    result: set[str] = set()
    queue = [node_id]
    while queue:
        cur = queue.pop(0)
        for c in arch.get("components", []):
            if c.get("parent_id") == cur and c["id"] not in result:
                result.add(c["id"])
                queue.append(c["id"])
    return result


def get_context(
    project_path: str,
    component_id: str,
    task: str = "",
    depth: str = "implement",
) -> dict:
    """
    Unified pre-edit context for agents — replaces get_generation_context and get_work_context.

    depth controls how much context is returned (use smaller values to save context window):
      "orient"     — component metadata + impact summary + first 3 open tasks
      "plan"       — orient + i_consume (contracts) + applicable_rules + decisions
      "implement"  — full detail: all of the above + i_own (files+symbols) + quality + coordination

    Returns (at implement depth):
      component:          metadata (id, name, layer, description, owner, tier)
      i_own:              files + symbols at full detail (owned + descendants)
      i_consume:          upstream nodes as contracts only (no source)
      impact:             upstream_names, impact_score, cycles, step_size
      open_tasks:         [{title, priority, status}]
      applicable_rules:   layer rules that apply to this component
      decisions:          accepted ADRs for this component
      quality:            {score, error_count, warning_count, fix_priority}
      coordination_needed: callers that break if public interface changes
      adr_recommended:    whether an ADR is warranted for this change
    """
    arch = load_arch(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}
    node = by_id.get(component_id, {})
    if not node:
        return {"error": f"Node not found: {component_id!r}"}
    layer = node.get("layer", "other")

    try:
        impact_data = impact_mod.get_component_impact(project_path, component_id)
    except Exception:
        impact_data = {}

    try:
        all_tasks = plan_mod.list_plan_items(project_path, component_id=component_id)
        open_tasks = [t for t in all_tasks if t.get("status") not in ("done", "cancelled")]
    except Exception:
        open_tasks = []

    component_meta = {
        "id": component_id,
        "name": node.get("name", ""),
        "layer": layer,
        "description": node.get("description", ""),
        "owner": node.get("owner", ""),
        "tier": node.get("tier", ""),
    }
    impact_summary = {
        "upstream_names": impact_data.get("upstream_names", []),
        "impact_score": impact_data.get("impact_score", 0),
        "cycles": impact_data.get("cycles", []),
        "step_size": "local",
    }

    # ── orient: bare minimum ───────────────────────────────────────────────────
    if depth == "orient":
        return {
            "depth": "orient",
            "component": component_meta,
            "impact": impact_summary,
            "open_tasks": open_tasks[:3],
        }

    # ── plan: + contracts + rules + decisions ──────────────────────────────────
    try:
        all_rules = rules_mod.load_rules(project_path)
        applicable_rules = [
            r for r in all_rules
            if r.get("from_layer") == layer
            or r.get("to_layer") == layer
            or r.get("type") == "no_cycles"
        ]
    except Exception:
        applicable_rules = []

    try:
        decisions = decisions_mod.get_decisions_for_context(project_path, component_id)
    except Exception:
        decisions = []

    # i_consume: outgoing deps as contracts only (shared by plan + implement)
    deps = arch.get("dependencies", [])
    descendant_ids = _collect_descendants(arch, component_id)
    owned_node_ids = {component_id} | descendant_ids
    outgoing = [d for d in deps if d.get("from_component") in owned_node_ids]
    consumed_ids = {d["to_component"] for d in outgoing if d["to_component"] not in owned_node_ids}
    consumed: list[dict] = []
    for cid in consumed_ids:
        dep = next((d for d in outgoing if d["to_component"] == cid), {})
        contract = get_contract(project_path, cid)
        cnode = by_id.get(cid, {})
        consumed.append({
            "node_id": cid,
            "node_name": cnode.get("name", cid),
            "level": cnode.get("level", 4),
            "edge_type": dep.get("edge_type", "invoke"),
            "contract": {
                "commands": contract.get("commands", []),
                "queries": contract.get("queries", []),
                "events_emitted": contract.get("events_emitted", []),
                "data_owned": contract.get("data_owned", []),
                "declared": contract.get("declared", False),
            },
        })

    if depth == "plan":
        return {
            "depth": "plan",
            "component": component_meta,
            "impact": impact_summary,
            "open_tasks": open_tasks,
            "i_consume": consumed,
            "applicable_rules": applicable_rules,
            "decisions": decisions,
        }

    # ── implement: full detail ─────────────────────────────────────────────────
    work = get_work_context(project_path, component_id, task)
    impact_summary["step_size"] = work.get("step_size", "local")

    try:
        quality_report = quality_mod.get_quality_report(project_path, component_id)
        quality = {
            "score": quality_report.get("score", 100),
            "error_count": quality_report.get("error_count", 0),
            "warning_count": quality_report.get("warning_count", 0),
            "fix_priority": quality_report.get("fix_priority", []),
            "summary": quality_report.get("summary", ""),
        }
    except Exception:
        quality = {"score": 100, "error_count": 0, "warning_count": 0, "fix_priority": [], "summary": ""}

    return {
        "depth": "implement",
        "component": component_meta,
        "i_own": work.get("i_own", {}),
        "i_consume": work.get("i_consume", []),
        "impact": impact_summary,
        "open_tasks": open_tasks,
        "applicable_rules": applicable_rules,
        "decisions": decisions,
        "quality": quality,
        "coordination_needed": work.get("coordination_needed", []),
        "adr_recommended": work.get("adr_recommended", False),
    }


def _edge_summary(dep: dict, by_id: dict) -> dict:
    fc = by_id.get(dep["from_component"], {})
    tc = by_id.get(dep["to_component"], {})
    return {
        "dep_id": dep["id"],
        "from_component": dep["from_component"],
        "from_name": fc.get("name", dep["from_component"]),
        "from_level": fc.get("level", 4),
        "to_component": dep["to_component"],
        "to_name": tc.get("name", dep["to_component"]),
        "to_level": tc.get("level", 4),
        "edge_type": dep.get("edge_type", "invoke"),
        "interface_points": dep.get("interface_points", []),
        "payload_types": dep.get("payload_types", []),
        "stability": dep.get("stability", "stable"),
        "async_flag": dep.get("async_flag", False),
        "crosses_boundary": dep.get("crosses_boundary", False),
    }
