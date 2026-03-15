"""
Architecture intelligence — read-only analytical tools that let agents
understand a codebase through its knowledge graph without reading source files.

All functions aggregate across architecture.json + mappings.json + plan.json.
"""
from __future__ import annotations

import re
from collections import deque

from archmap.store import load_arch, load_mappings, load_plan, load_meta

_LAYER_ORDER = ["frontend", "backend", "database", "infra", "shared", "testing", "other"]


# ── describe_architecture ──────────────────────────────────────────────────────

def describe_architecture(project_path: str) -> str:
    """
    Return a comprehensive markdown document describing the full architecture.
    Reads components, files, dependencies, and plan items — no source files needed.
    """
    meta     = load_meta(project_path)
    arch     = load_arch(project_path)
    mappings = load_mappings(project_path)
    plan     = load_plan(project_path)

    components   = arch.get("components", [])
    dependencies = arch.get("dependencies", [])
    files_data   = mappings.get("files", {})
    plan_items   = plan.get("items", [])

    if not components:
        return "# Architecture\n\nNo components mapped yet. Run `init_project` then `scan_project` to get started."

    # ── Build indexes ──────────────────────────────────────────────────────────
    name_map  = {c["id"]: c["name"]            for c in components}
    layer_map = {c["id"]: c.get("layer", "other") for c in components}

    # component_id → [(file_path, metadata)]
    comp_files: dict[str, list[tuple[str, dict]]] = {c["id"]: [] for c in components}
    for fp, rec in files_data.items():
        cid = rec.get("component_id")
        if cid in comp_files:
            comp_files[cid].append((fp, rec.get("metadata", {})))

    # outgoing / incoming adjacency
    outgoing: dict[str, list[dict]] = {c["id"]: [] for c in components}
    incoming: dict[str, list[dict]] = {c["id"]: [] for c in components}
    for d in dependencies:
        fc, tc = d.get("from_component", ""), d.get("to_component", "")
        if fc in outgoing: outgoing[fc].append(d)
        if tc in incoming: incoming[tc].append(d)

    # component_id → open plan items
    comp_plans: dict[str, list[dict]] = {c["id"]: [] for c in components}
    for item in plan_items:
        cid = item.get("component_id")
        if cid and cid in comp_plans and item.get("status") not in ("done", "cancelled"):
            comp_plans[cid].append(item)

    # layer → components (ordered)
    by_layer: dict[str, list[dict]] = {l: [] for l in _LAYER_ORDER}
    for c in components:
        by_layer.setdefault(c.get("layer", "other"), []).append(c)

    # ── Build markdown ─────────────────────────────────────────────────────────
    proj_name     = meta.get("name") or "this project"
    layer_names   = [l for l in _LAYER_ORDER if by_layer.get(l)]
    confirmed_dep = [d for d in dependencies if d.get("confidence") == "confirmed"]

    lines: list[str] = []
    lines += [
        f"# Architecture: {proj_name}",
        "",
        "## Overview",
        f"{len(components)} component(s) across {len(layer_names)} layer(s). "
        f"{len(files_data)} file(s) mapped, "
        f"{len(confirmed_dep)} confirmed / {len(dependencies) - len(confirmed_dep)} auto-inferred dependencies.",
        "",
        "## Components by Layer",
        "",
    ]

    for layer in _LAYER_ORDER:
        comps_in_layer = by_layer.get(layer, [])
        if not comps_in_layer:
            continue
        lines.append(f"### {layer.capitalize()}")
        lines.append("")
        for c in comps_in_layer:
            cid = c["id"]
            conf_tag = "" if c.get("confidence") == "confirmed" else " [auto-detected]"
            lines.append(f"**{c['name']}**{conf_tag}  `{cid}`")

            desc = c.get("description", "").strip()
            if desc:
                lines.append(f"  {desc}")

            cf = comp_files.get(cid, [])
            if cf:
                file_parts = []
                for fp, meta_f in cf:
                    lang = meta_f.get("language", "")
                    file_parts.append(f"`{fp}`" + (f" [{lang}]" if lang else ""))
                lines.append(f"  Files ({len(cf)}): {', '.join(file_parts)}")

                all_syms: list[str] = []
                for _, meta_f in cf:
                    all_syms.extend(meta_f.get("functions", []))
                if all_syms:
                    lines.append(f"  Symbols: {', '.join(all_syms)}")

            out = outgoing.get(cid, [])
            if out:
                dep_parts = [
                    f"{name_map.get(d['to_component'], d['to_component'])} ({d.get('label', 'uses')})"
                    for d in out
                ]
                lines.append(f"  Depends on: {', '.join(dep_parts)}")

            inc = incoming.get(cid, [])
            if inc:
                caller_parts = [name_map.get(d["from_component"], d["from_component"]) for d in inc]
                lines.append(f"  Used by: {', '.join(caller_parts)}")

            cp = comp_plans.get(cid, [])
            if cp:
                lines.append(f"  Open tasks ({len(cp)}): " + "; ".join(i["title"] for i in cp))

            lines.append("")

    # ── Dependency flow ────────────────────────────────────────────────────────
    lines += ["## Dependency Flow", ""]
    if dependencies:
        for d in dependencies:
            fn    = name_map.get(d.get("from_component", ""), d.get("from_component", "?"))
            tn    = name_map.get(d.get("to_component", ""),   d.get("to_component", "?"))
            label = d.get("label", "uses")
            conf  = " [auto]" if d.get("confidence") == "auto" else ""
            lines.append(f"  {fn} --[{label}]--> {tn}{conf}")
    else:
        lines.append("  (no dependencies mapped yet)")
    lines.append("")

    # ── Entry points ───────────────────────────────────────────────────────────
    lines += ["## Entry Points", "Components with no upstream callers (start reading here):"]
    roots = [c for c in components if not incoming.get(c["id"])]
    if roots:
        for c in roots:
            lines.append(f"- **{c['name']}** ({c.get('layer','other')}) — {c.get('description','')}")
    else:
        lines.append("- (every component has at least one upstream caller)")
    lines.append("")

    # ── Hotspots ───────────────────────────────────────────────────────────────
    lines += ["## Hotspots", "Components with the most dependency connections:"]
    hotspot = sorted(
        [(c, len(incoming.get(c["id"], [])), len(outgoing.get(c["id"], []))) for c in components],
        key=lambda x: x[1] + x[2], reverse=True,
    )
    printed = 0
    for c, inc_n, out_n in hotspot:
        if inc_n + out_n == 0 or printed >= 5:
            break
        lines.append(f"- **{c['name']}** ({inc_n} upstream, {out_n} downstream)")
        printed += 1
    if printed == 0:
        lines.append("- (no dependencies yet)")

    return "\n".join(lines)


# ── find_related ───────────────────────────────────────────────────────────────

def _score(text: str, q: str) -> int:
    """Score how closely text matches query (case-insensitive). Higher = better."""
    t = text.lower()
    if t == q:           return 4
    if t.startswith(q):  return 3
    if re.search(r'(?<![a-z0-9])' + re.escape(q) + r'(?![a-z0-9])', t): return 2
    if q in t:           return 1
    return 0


def find_related(project_path: str, query: str) -> dict:
    """
    Full-text search across all graph entities: component names/descriptions,
    file paths/descriptions, and symbol names. Returns ranked results.
    """
    arch     = load_arch(project_path)
    mappings = load_mappings(project_path)

    q = query.lower().strip()
    if not q:
        return {"query": query, "summary": "Empty query — provide a search term.", "components": [], "files": [], "symbols": []}

    components = arch.get("components", [])
    files_data = mappings.get("files", {})
    name_map   = {c["id"]: c["name"] for c in components}

    # Components
    comp_results: list[dict] = []
    for c in components:
        score = (
            _score(c.get("name", ""), q) * 3
            + _score(c.get("description", ""), q)
            + max((_score(t, q) for t in c.get("tags", [])), default=0) * 2
        )
        if score > 0:
            comp_results.append({"score": score, "id": c["id"], "name": c["name"],
                                  "layer": c.get("layer", "other"), "description": c.get("description", ""),
                                  "confidence": c.get("confidence", "confirmed")})
    comp_results.sort(key=lambda x: x["score"], reverse=True)

    # Files
    file_results: list[dict] = []
    for fp, rec in files_data.items():
        meta_f = rec.get("metadata", {})
        cid    = rec.get("component_id", "")
        score  = (
            _score(fp, q) * 3
            + _score(meta_f.get("description", ""), q)
            + _score(name_map.get(cid, ""), q)
        )
        if score > 0:
            file_results.append({"score": score, "file_path": fp, "component_id": cid,
                                  "component_name": name_map.get(cid, ""),
                                  "language": meta_f.get("language", ""),
                                  "description": meta_f.get("description", "")})
    file_results.sort(key=lambda x: x["score"], reverse=True)

    # Symbols
    sym_results: list[dict] = []
    for fp, rec in files_data.items():
        meta_f = rec.get("metadata", {})
        cid    = rec.get("component_id", "")
        for sym in meta_f.get("functions", []):
            score = _score(sym, q) * 4 + _score(fp, q)
            if score > 0:
                sym_results.append({"score": score, "symbol": sym, "file_path": fp,
                                     "component_id": cid, "component_name": name_map.get(cid, "")})
    sym_results.sort(key=lambda x: x["score"], reverse=True)

    def drop_score(lst: list[dict]) -> list[dict]:
        return [{k: v for k, v in item.items() if k != "score"} for item in lst]

    summary_parts: list[str] = []
    if comp_results:
        summary_parts.append(f"{len(comp_results)} component(s): " + ", ".join(r["name"] for r in comp_results[:3]))
    if file_results:
        summary_parts.append(f"{len(file_results)} file(s): " + ", ".join(r["file_path"] for r in file_results[:3]))
    if sym_results:
        summary_parts.append(f"{len(sym_results)} symbol(s): " + ", ".join(r["symbol"] for r in sym_results[:3]))

    return {
        "query":      query,
        "summary":    "; ".join(summary_parts) if summary_parts else f"No results found for '{query}'",
        "components": drop_score(comp_results),
        "files":      drop_score(file_results[:20]),
        "symbols":    drop_score(sym_results[:50]),
    }


# ── get_symbol_index ───────────────────────────────────────────────────────────

def get_symbol_index(project_path: str) -> list[dict]:
    """
    Return every symbol in the project mapped to its file and component.
    Sorted by (component_name, file_path, symbol) for consistent reading order.
    """
    arch     = load_arch(project_path)
    mappings = load_mappings(project_path)

    name_map  = {c["id"]: c["name"]               for c in arch.get("components", [])}
    layer_map = {c["id"]: c.get("layer", "other")  for c in arch.get("components", [])}

    index: list[dict] = []
    for fp, rec in mappings.get("files", {}).items():
        meta_f = rec.get("metadata", {})
        cid    = rec.get("component_id", "")
        for sym in meta_f.get("functions", []):
            index.append({
                "symbol":          sym,
                "file_path":       fp,
                "language":        meta_f.get("language", ""),
                "component_id":    cid,
                "component_name":  name_map.get(cid, ""),
                "component_layer": layer_map.get(cid, ""),
            })

    index.sort(key=lambda x: (x["component_name"], x["file_path"], x["symbol"]))
    return index


# ── trace_path ─────────────────────────────────────────────────────────────────

def trace_path(project_path: str, from_component_id: str, to_component_id: str) -> dict:
    """
    BFS shortest dependency path between two components.
    Returns path nodes with labels and file hints at each hop.
    """
    arch     = load_arch(project_path)
    mappings = load_mappings(project_path)

    components   = arch.get("components", [])
    dependencies = arch.get("dependencies", [])

    comp_ids  = {c["id"] for c in components}
    name_map  = {c["id"]: c["name"]               for c in components}
    layer_map = {c["id"]: c.get("layer", "other")  for c in components}

    if from_component_id not in comp_ids:
        return {"found": False, "error": f"Component not found: {from_component_id}"}
    if to_component_id not in comp_ids:
        return {"found": False, "error": f"Component not found: {to_component_id}"}

    # Files index for enriching path hops
    comp_files: dict[str, list[str]] = {}
    for fp, rec in mappings.get("files", {}).items():
        cid = rec.get("component_id")
        if cid:
            comp_files.setdefault(cid, []).append(fp)

    # Trivial case
    if from_component_id == to_component_id:
        return {
            "found": True, "length": 0, "text": name_map[from_component_id],
            "path": [{"component_id": from_component_id,
                      "component_name": name_map[from_component_id],
                      "layer": layer_map[from_component_id],
                      "via_dependency": None,
                      "files": comp_files.get(from_component_id, [])[:5]}],
        }

    # Build adjacency: from → [(to, dep_dict)]
    adj: dict[str, list[tuple[str, dict]]] = {cid: [] for cid in comp_ids}
    for d in dependencies:
        fc, tc = d.get("from_component", ""), d.get("to_component", "")
        if fc in adj:
            adj[fc].append((tc, d))

    # BFS with predecessor tracking
    predecessor: dict[str, tuple[str, dict] | None] = {from_component_id: None}
    queue: deque[str] = deque([from_component_id])
    found = False

    while queue:
        cur = queue.popleft()
        if cur == to_component_id:
            found = True
            break
        for neighbor, dep in adj.get(cur, []):
            if neighbor not in predecessor:
                predecessor[neighbor] = (cur, dep)
                queue.append(neighbor)

    from_name = name_map.get(from_component_id, from_component_id)
    to_name   = name_map.get(to_component_id,   to_component_id)

    if not found:
        return {"found": False, "from_component": from_component_id, "from_name": from_name,
                "to_component": to_component_id, "to_name": to_name,
                "text": f"No dependency path from '{from_name}' to '{to_name}'",
                "path": []}

    # Reconstruct path (backward from target)
    path_nodes: list[dict] = []
    cursor: str | None = to_component_id
    while cursor is not None:
        entry = predecessor[cursor]
        node: dict = {
            "component_id":   cursor,
            "component_name": name_map.get(cursor, cursor),
            "layer":          layer_map.get(cursor, "other"),
            "files":          comp_files.get(cursor, [])[:5],
        }
        if entry is None:
            node["via_dependency"] = None
        else:
            _, dep = entry
            node["via_dependency"] = {
                "id":         dep["id"],
                "label":      dep.get("label", "uses"),
                "kind":       dep.get("kind", "runtime"),
                "confidence": dep.get("confidence", "confirmed"),
            }
            cursor = entry[0]
            path_nodes.append(node)
            continue
        path_nodes.append(node)
        cursor = None
    path_nodes.reverse()

    # Human-readable text
    text_parts: list[str] = []
    for i, node in enumerate(path_nodes):
        if i == 0:
            text_parts.append(node["component_name"])
        else:
            dep = node["via_dependency"]
            label = dep["label"] if dep else "uses"
            text_parts.append(f"--[{label}]--> {node['component_name']}")

    return {
        "found": True,
        "from_component": from_component_id, "from_name": from_name,
        "to_component":   to_component_id,   "to_name":   to_name,
        "length": len(path_nodes) - 1,
        "path":   path_nodes,
        "text":   " ".join(text_parts),
    }
