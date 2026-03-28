"""
Component impact analysis — BFS upstream/downstream/cycle detection,
plus symbol-level contract-break analysis.
"""
from __future__ import annotations
from archmap.architecture import get_architecture
from archmap.repo import load_mappings
from archmap.models import NotFoundError


def _bfs(adjacency: dict[str, list[str]], start: str) -> set[str]:
    visited: set[str] = set()
    queue = [start]
    while queue:
        cur = queue.pop(0)
        for nxt in adjacency.get(cur, []):
            if nxt not in visited and nxt != start:
                visited.add(nxt)
                queue.append(nxt)
    return visited


def get_component_impact(project_path: str, component_id: str) -> dict:
    """
    BFS impact analysis for a component. Returns:
      - upstream:     components that depend ON this one (would break if it changes)
      - downstream:   components this one depends on
      - cycles:       dependency cycles involving this component
      - is_leaf:      no outgoing deps
      - is_root:      no incoming deps
      - impact_score: number of upstream components affected by a change here
    """
    arch = get_architecture(project_path)
    comp_ids = {c["id"] for c in arch.get("components", [])}

    if component_id not in comp_ids:
        raise NotFoundError(f"Component not found: {component_id!r}")

    deps = arch.get("dependencies", [])
    outgoing: dict[str, list[str]] = {cid: [] for cid in comp_ids}
    incoming: dict[str, list[str]] = {cid: [] for cid in comp_ids}
    for d in deps:
        f, t = d["from_component"], d["to_component"]
        if f in outgoing:
            outgoing[f].append(t)
        if t in incoming:
            incoming[t].append(f)

    downstream = _bfs(outgoing, component_id)
    upstream   = _bfs(incoming, component_id)
    cycles     = [cid for cid in downstream if component_id in _bfs(outgoing, cid)]

    name_map = {c["id"]: c["name"] for c in arch.get("components", [])}
    arch_comps_by_id = {c["id"]: c for c in arch.get("components", [])}

    # ── Symbol-level breakdown ─────────────────────────────────────────────────
    # Which specific symbols in this component are referenced by upstream callers
    comp = next((c for c in arch.get("components", []) if c["id"] == component_id), {})
    public_api_set = set(comp.get("public_api", []))

    # Find edges where upstream comps reference specific interface_points
    breaking_symbols: list[dict] = []
    for dep in deps:
        if dep.get("to_component") == component_id:
            pts = dep.get("interface_points", [])
            if pts:
                fc = dep["from_component"]
                breaking_symbols.append({
                    "from_component": fc,
                    "from_name": name_map.get(fc, fc),
                    "interface_points": pts,
                    "in_public_api": [p for p in pts if p in public_api_set],
                    "not_in_public_api": [p for p in pts if p not in public_api_set],
                    "edge_type": dep.get("edge_type", "invoke"),
                    "stability": dep.get("stability", "stable"),
                    "will_break_on_change": dep.get("stability") == "stable",
                })

    # Compute effective step size for changes to this component
    upstream_levels = {
        arch_comps_by_id.get(cid, {}).get("level", 4)
        for cid in upstream
    } if upstream else set()

    if any(lv <= 2 for lv in upstream_levels):
        step_size = "cross"
    elif any(lv == 3 for lv in upstream_levels):
        step_size = "service"
    elif len(upstream) > 2:
        step_size = "bounded"
    elif upstream:
        step_size = "local"
    else:
        step_size = "atomic"

    return {
        "component_id":   component_id,
        "component_name": name_map.get(component_id, component_id),
        "level":          comp.get("level", 4),
        "stability":      comp.get("stability", "stable"),
        "public_api":     comp.get("public_api", []),
        "upstream":       sorted(upstream),
        "upstream_names": [name_map.get(c, c) for c in sorted(upstream)],
        "downstream":     sorted(downstream),
        "downstream_names": [name_map.get(c, c) for c in sorted(downstream)],
        "cycles":         sorted(cycles),
        "cycle_names":    [name_map.get(c, c) for c in sorted(cycles)],
        "is_leaf":        len(outgoing.get(component_id, [])) == 0,
        "is_root":        len(incoming.get(component_id, [])) == 0,
        "impact_score":   len(upstream),
        "step_size":      step_size,
        "breaking_symbols": breaking_symbols,
        "breaking_symbol_count": len(breaking_symbols),
    }
