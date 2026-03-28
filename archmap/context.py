"""
Agent work-context engine — level-aware, scope-isolating context queries.

Core principle: agents should see their own node at full resolution and
every other node only as the contract it exposes. This prevents agents from
accidentally depending on implementation details across boundaries.

Key tools:
  get_work_context   — full-detail self + contract-only others + step_size
  get_change_surface — which nodes/levels are affected by changing a symbol
  get_domain_map     — L2 domain overview (entry point for all agent sessions)
  describe_node      — drill-down from any level into its children
"""
from __future__ import annotations
from archmap.repo import load_arch, load_mappings, load_plan
from archmap.contracts import get_contract


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

def get_change_surface(
    project_path: str,
    symbol_names: list[str],
) -> dict:
    """
    Given a list of symbol names, determine the full change surface:
    - which components own these symbols
    - which edges reference them in interface_points
    - which components will break (stable edges)
    - recommended update order
    - step_size classification
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}

    query_set = set(symbol_names)

    # ── Find owning components ─────────────────────────────────────────────────
    owners: dict[str, dict] = {}   # symbol → {component_id, file_path, in_public_api}
    for fp, rec in mappings.get("files", {}).items():
        cid = rec.get("component_id", "")
        comp = by_id.get(cid, {})
        public_api = set(comp.get("public_api", []))
        for sym in rec.get("symbols", []):
            name = sym.get("name", "")
            if name in query_set:
                owners[name] = {
                    "symbol": name,
                    "component_id": cid,
                    "component_name": comp.get("name", cid),
                    "component_level": comp.get("level", 4),
                    "file_path": fp,
                    "in_public_api": name in public_api,
                    "visibility": sym.get("visibility", "public"),
                }

    # ── Find edges that reference these symbols ────────────────────────────────
    affected_edges: list[dict] = []
    for dep in arch.get("dependencies", []):
        pts = set(dep.get("interface_points", []))
        matched = list(pts & query_set)
        if matched:
            from_node = by_id.get(dep["from_component"], {})
            to_node = by_id.get(dep["to_component"], {})
            affected_edges.append({
                "dep_id": dep["id"],
                "from_component": dep["from_component"],
                "from_name": from_node.get("name", dep["from_component"]),
                "from_level": from_node.get("level", 4),
                "to_component": dep["to_component"],
                "to_name": to_node.get("name", dep["to_component"]),
                "to_level": to_node.get("level", 4),
                "matched_symbols": matched,
                "edge_type": dep.get("edge_type", "invoke"),
                "stability": dep.get("stability", "stable"),
                "crosses_boundary": dep.get("crosses_boundary", False),
                "will_break": dep.get("stability") == "stable",
            })

    # ── Components that need updating ─────────────────────────────────────────
    touched_comp_ids: set[str] = set()
    for o in owners.values():
        touched_comp_ids.add(o["component_id"])
    for e in affected_edges:
        touched_comp_ids.add(e["from_component"])
        touched_comp_ids.add(e["to_component"])

    touched_levels = {by_id.get(cid, {}).get("level", 4) for cid in touched_comp_ids}
    crosses_service = any(lv <= 3 for lv in touched_levels)
    crosses_domain  = any(lv <= 2 for lv in touched_levels)
    step = _classify_step(touched_levels, touched_comp_ids, crosses_service, crosses_domain)

    # ── Build recommended update order (topological: owners first, then callers) ──
    order: list[str] = []
    ordered_ids: set[str] = set()

    def _push(cid: str, reason: str):
        if cid not in ordered_ids:
            c = by_id.get(cid, {})
            order.append(f"{c.get('name', cid)} [{reason}]")
            ordered_ids.add(cid)

    for sym, info in owners.items():
        _push(info["component_id"], f"owns {sym}")
    for e in sorted(affected_edges, key=lambda x: x.get("to_level", 4)):
        _push(e["to_component"], f"caller via {e['edge_type']}")
        _push(e["from_component"], f"uses {','.join(e['matched_symbols'])}")

    return {
        "symbols_queried": symbol_names,
        "owners": list(owners.values()),
        "affected_edges": affected_edges,
        "breaking_edge_count": sum(1 for e in affected_edges if e["will_break"]),
        "touched_components": [
            {"id": cid, "name": by_id.get(cid, {}).get("name", cid),
             "level": by_id.get(cid, {}).get("level", 4)}
            for cid in sorted(touched_comp_ids)
        ],
        "step_size": step,
        "step_explanation": _STEP_LABELS.get(step, ""),
        "adr_recommended": step in ("cross",),
        "recommended_update_order": order,
    }


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
