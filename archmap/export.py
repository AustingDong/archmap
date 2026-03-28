"""
Architecture export — render the component graph to standard diagram formats.

Supported formats:
  mermaid  — Mermaid flowchart (paste into GitHub Markdown or Notion)
  dot      — Graphviz DOT language (render with `dot -Tpng`, import into diagrams.net)
  c4       — C4 Context diagram in Structurizr DSL (component-level)
"""
from __future__ import annotations

from archmap.repo import load_arch, load_meta

# Layer colours (hex) used in Mermaid and DOT node styling
_LAYER_COLOR: dict[str, str] = {
    "frontend":  "#60a5fa",   # blue-400
    "backend":   "#34d399",   # emerald-400
    "database":  "#a78bfa",   # violet-400
    "infra":     "#f59e0b",   # amber-400
    "shared":    "#94a3b8",   # slate-400
    "testing":   "#f472b6",   # pink-400
    "other":     "#cbd5e1",   # slate-300
}

# Mermaid shape per layer
_LAYER_SHAPE: dict[str, tuple[str, str]] = {
    "frontend":  ("[", "]"),
    "backend":   ("[", "]"),
    "database":  ("[(", ")]"),
    "infra":     ("[/", "/]"),
    "shared":    ("((", "))"),
    "testing":   ("[/", "/]"),
    "other":     ("[", "]"),
}


def _mermaid_id(component_id: str) -> str:
    """Convert a component ID to a Mermaid-safe node identifier."""
    return component_id.replace("-", "_").replace(" ", "_")


def export_mermaid(project_path: str, direction: str = "LR") -> str:
    """
    Export the architecture as a Mermaid flowchart.

    Args:
        direction: LR (left-right), TD (top-down), RL, BT
    Returns:
        Mermaid source string ready to paste into a ```mermaid code block.
    """
    arch = load_arch(project_path)
    meta = load_meta(project_path)

    components   = arch.get("components", [])
    dependencies = arch.get("dependencies", [])

    if not components:
        return "```mermaid\nflowchart LR\n    EMPTY[No components mapped yet]\n```"

    comp_map = {c["id"]: c for c in components}
    lines: list[str] = [f"flowchart {direction}"]

    # Group nodes by layer using Mermaid subgraphs
    from collections import defaultdict
    by_layer: dict[str, list[dict]] = defaultdict(list)
    for c in components:
        by_layer[c.get("layer", "other")].append(c)

    layer_order = ["frontend", "backend", "database", "infra", "shared", "testing", "other"]

    for layer in layer_order:
        comps = by_layer.get(layer, [])
        if not comps:
            continue
        lines.append(f"    subgraph {layer.upper()}")
        for c in comps:
            mid   = _mermaid_id(c["id"])
            label = c["name"].replace('"', "'")
            open_, close_ = _LAYER_SHAPE.get(layer, ("[", "]"))
            lines.append(f'        {mid}{open_}"{label}"{close_}')
        lines.append("    end")

    # Edges
    for d in dependencies:
        fc = _mermaid_id(d.get("from_component", ""))
        tc = _mermaid_id(d.get("to_component", ""))
        if not fc or not tc:
            continue
        label   = d.get("label", "uses")
        is_auto = d.get("confidence", "confirmed") == "auto"
        arrow   = "-.->" if is_auto else "-->"
        lines.append(f'    {fc} {arrow}|"{label}"| {tc}')

    # Layer colour styles
    lines.append("")
    added_classes: set[str] = set()
    for c in components:
        layer = c.get("layer", "other")
        cls   = f"layer_{layer}"
        if cls not in added_classes:
            color = _LAYER_COLOR.get(layer, "#cbd5e1")
            lines.append(f"    classDef {cls} fill:{color},stroke:#334155,color:#0f172a")
            added_classes.add(cls)

    for c in components:
        layer = c.get("layer", "other")
        lines.append(f"    class {_mermaid_id(c['id'])} layer_{layer}")

    title = meta.get("name", "Architecture")
    header = f"---\ntitle: {title}\n---\n"
    return header + "\n".join(lines)


def export_dot(project_path: str) -> str:
    """
    Export the architecture as a Graphviz DOT graph.
    Render with: dot -Tpng -o arch.png arch.dot

    Returns:
        DOT source string.
    """
    arch = load_arch(project_path)
    meta = load_meta(project_path)

    components   = arch.get("components", [])
    dependencies = arch.get("dependencies", [])

    title    = meta.get("name", "Architecture")
    lines: list[str] = [
        f'digraph "{title}" {{',
        "    rankdir=LR;",
        '    node [fontname="Helvetica", fontsize=11, style=filled, shape=box];',
        '    edge [fontname="Helvetica", fontsize=9];',
        "",
    ]

    # Subgraphs per layer
    from collections import defaultdict
    by_layer: dict[str, list[dict]] = defaultdict(list)
    for c in components:
        by_layer[c.get("layer", "other")].append(c)

    layer_order = ["frontend", "backend", "database", "infra", "shared", "testing", "other"]
    cluster_idx = 0

    for layer in layer_order:
        comps = by_layer.get(layer, [])
        if not comps:
            continue
        color = _LAYER_COLOR.get(layer, "#cbd5e1")
        lines.append(f"    subgraph cluster_{cluster_idx} {{")
        lines.append(f'        label="{layer.upper()}";')
        lines.append(f'        style=filled; fillcolor="{color}22"; color="{color}";')
        for c in comps:
            node_id   = c["id"].replace("-", "_")
            label     = c["name"].replace('"', '\\"')
            node_color = _LAYER_COLOR.get(layer, "#cbd5e1")
            lines.append(f'        "{node_id}" [label="{label}", fillcolor="{node_color}"];')
        lines.append("    }")
        cluster_idx += 1

    lines.append("")

    # Edges
    for d in dependencies:
        fc      = d.get("from_component", "").replace("-", "_")
        tc      = d.get("to_component",   "").replace("-", "_")
        if not fc or not tc:
            continue
        label   = d.get("label", "uses").replace('"', '\\"')
        is_auto = d.get("confidence", "confirmed") == "auto"
        style   = 'style=dashed, color="#94a3b8"' if is_auto else 'color="#475569"'
        lines.append(f'    "{fc}" -> "{tc}" [label="{label}", {style}];')

    lines.append("}")
    return "\n".join(lines)


def export_c4(project_path: str) -> str:
    """
    Export the architecture as a C4 Context diagram in Structurizr DSL.
    Approximation: each ArchMap component → C4 Container.

    Returns:
        Structurizr DSL string.
    """
    arch = load_arch(project_path)
    meta = load_meta(project_path)

    components   = arch.get("components", [])
    dependencies = arch.get("dependencies", [])
    title        = meta.get("name", "System")

    def safe_id(cid: str) -> str:
        return cid.replace("-", "_").replace("comp_", "c_")

    lines: list[str] = [
        "workspace {",
        f'    name "{title}"',
        "",
        "    model {",
        f'        {safe_id("system")} = softwareSystem "{title}" {{',
    ]

    for c in components:
        cid   = safe_id(c["id"])
        name  = c["name"].replace('"', "'")
        desc  = c.get("description", "").replace('"', "'") or c.get("layer", "")
        tech  = c.get("layer", "").capitalize()
        lines.append(f'            {cid} = container "{name}" "{desc}" "{tech}"')

    lines.append("        }")
    lines.append("")

    for d in dependencies:
        fc    = safe_id(d.get("from_component", ""))
        tc    = safe_id(d.get("to_component", ""))
        label = d.get("label", "uses").replace('"', "'")
        if fc and tc:
            lines.append(f'        {fc} -> {tc} "{label}"')

    lines += [
        "    }",
        "",
        "    views {",
        f'        container {safe_id("system")} {{',
        "            include *",
        "            autoLayout lr",
        "        }",
        "    }",
        "}",
    ]
    return "\n".join(lines)


def export_architecture(project_path: str, format: str = "mermaid") -> str:
    """
    Export the architecture graph to the requested format.

    Args:
        format: "mermaid" | "dot" | "c4"
    Returns:
        Diagram source as a string.
    Raises:
        ValueError if format is unsupported.
    """
    fmt = format.lower().strip()
    if fmt == "mermaid":
        return export_mermaid(project_path)
    if fmt in ("dot", "graphviz"):
        return export_dot(project_path)
    if fmt in ("c4", "structurizr"):
        return export_c4(project_path)
    raise ValueError(f"Unsupported export format: '{format}'. Use: mermaid, dot, c4")
