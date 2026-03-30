"""
Progressive knowledge navigation tools.

  drill_into        — given a task description, suggest the L2→L4 component path
  get_knowledge_gaps — surface underdocumented nodes, unmapped files, stale symbols
"""
from __future__ import annotations

import re
from archmap.repo import load_arch, load_mappings, load_contracts
from archmap.completeness import score_component, score_all_components
from archmap.context import _collect_descendants


# ─── drill_into ───────────────────────────────────────────────────────────────

def _tokenize(text: str) -> set[str]:
    """Lower-case words of length ≥3 from text."""
    return {w for w in re.split(r"[^a-z0-9]+", text.lower()) if len(w) >= 3}


def _keyword_score(node: dict, contracts: dict, query_tokens: set[str]) -> int:
    """Count keyword hits against node name, description, and contract public_api."""
    text_parts = [
        node.get("name", ""),
        node.get("description", ""),
        " ".join(node.get("public_api", [])),
        " ".join(node.get("data_owned", [])),
    ]
    contract = contracts.get(node["id"], {})
    text_parts += contract.get("public_api", [])
    text_parts += contract.get("commands", [])
    text_parts += contract.get("queries", [])

    node_tokens = _tokenize(" ".join(text_parts))
    return len(query_tokens & node_tokens)


def drill_into(
    project_path: str,
    task: str,
    start_id: str = "",
) -> dict:
    """
    Navigate from a task description to the right component.

    Uses keyword matching against component names, descriptions, and declared
    contracts to suggest the best L2 → L3 → L4 path for the given task.

    Args:
        project_path: Path to the ArchMap project root.
        task:         Free-text description of what you want to work on.
        start_id:     Optional — constrain search to descendants of this node.

    Returns:
        {
          path: [{id, name, level, layer, score, why}],
          suggested_component: {id, name, level, layer},
          alternatives: [{id, name, level, layer, score}],
          query_tokens: [str]
        }
    """
    arch = load_arch(project_path)
    contracts = load_contracts(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}

    query_tokens = _tokenize(task)
    if not query_tokens:
        return {"error": "task description is empty or too short"}

    # Scope to subtree if start_id given
    if start_id:
        scope_ids = {start_id} | _collect_descendants(arch, start_id)
        candidates = [c for c in arch.get("components", []) if c["id"] in scope_ids]
    else:
        candidates = arch.get("components", [])

    # Score every node
    scored = [
        {**c, "_score": _keyword_score(c, contracts, query_tokens)}
        for c in candidates
    ]

    def _best_at_level(level: int, parent_id: str | None = None) -> dict | None:
        pool = [n for n in scored if n.get("level", 4) == level]
        if parent_id is not None:
            pool = [n for n in pool if n.get("parent_id") == parent_id]
        if not pool:
            return None
        return max(pool, key=lambda n: n["_score"])

    # Build L2 → L3 → L4 path
    path = []
    best_l2 = _best_at_level(2)
    if best_l2:
        path.append({
            "id": best_l2["id"],
            "name": best_l2.get("name", ""),
            "level": 2,
            "layer": best_l2.get("layer", ""),
            "score": best_l2["_score"],
            "why": f"Best L2 domain match ({best_l2['_score']} keyword hits)",
        })
        best_l3 = _best_at_level(3, parent_id=best_l2["id"])
        if best_l3:
            path.append({
                "id": best_l3["id"],
                "name": best_l3.get("name", ""),
                "level": 3,
                "layer": best_l3.get("layer", ""),
                "score": best_l3["_score"],
                "why": f"Best L3 service under {best_l2.get('name', '')} ({best_l3['_score']} hits)",
            })
            best_l4 = _best_at_level(4, parent_id=best_l3["id"])
            if best_l4:
                path.append({
                    "id": best_l4["id"],
                    "name": best_l4.get("name", ""),
                    "level": 4,
                    "layer": best_l4.get("layer", ""),
                    "score": best_l4["_score"],
                    "why": f"Best L4 component under {best_l3.get('name', '')} ({best_l4['_score']} hits)",
                })

    suggested = path[-1] if path else {}
    leaf_level = suggested.get("level", 4)

    # Alternatives at leaf level (exclude suggested)
    suggested_id = suggested.get("id", "")
    alternatives = sorted(
        [n for n in scored if n.get("level", 4) == leaf_level and n["id"] != suggested_id],
        key=lambda n: -n["_score"],
    )[:3]

    return {
        "path": path,
        "suggested_component": {
            "id": suggested.get("id", ""),
            "name": suggested.get("name", ""),
            "level": suggested.get("level", 4),
            "layer": suggested.get("layer", ""),
        },
        "alternatives": [
            {"id": n["id"], "name": n.get("name", ""), "level": n.get("level", 4),
             "layer": n.get("layer", ""), "score": n["_score"]}
            for n in alternatives
        ],
        "query_tokens": sorted(query_tokens),
    }


# ─── get_knowledge_gaps ───────────────────────────────────────────────────────

def get_knowledge_gaps(project_path: str, min_score: int = 70) -> dict:
    """
    Surface underdocumented components, unmapped files, and stale symbols.

    Args:
        project_path: Path to the ArchMap project root.
        min_score:    Components scoring below this threshold are reported as gaps.

    Returns:
        {
          total_components: int,
          below_threshold: int,
          threshold: int,
          gaps: [{component_id, name, level, layer, score, missing}],
          unmapped_source_files: [str],
          stale_symbols: [{file_path, issue}]
        }
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)

    all_scores = score_all_components(project_path)
    gaps = [s for s in all_scores if s["score"] < min_score]

    # Unmapped source files: mapped files list vs. files that exist in the project
    mapped_files = set(mappings.get("files", {}).keys())
    # Files in archmap/ and ui/src/ that are source code but not in the graph
    import os
    from pathlib import Path
    project_root = Path(project_path)
    source_extensions = {".py", ".ts", ".tsx", ".js", ".jsx"}
    skip_dirs = {"node_modules", ".archmap", "__pycache__", ".git", "dist", "build", ".venv"}

    discovered: list[str] = []
    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for f in files:
            if Path(f).suffix in source_extensions:
                rel = str(Path(root) / f).replace(str(project_root) + os.sep, "").replace("\\", "/")
                discovered.append(rel)

    unmapped = [f for f in discovered if f not in mapped_files]

    # Stale symbols: mapped files with zero symbols extracted
    stale: list[dict] = []
    for fp, rec in mappings.get("files", {}).items():
        if not rec.get("symbols"):
            stale.append({
                "file_path": fp,
                "issue": "mapped but no symbols extracted — run post_edit_sync",
            })

    return {
        "total_components": len(all_scores),
        "below_threshold": len(gaps),
        "threshold": min_score,
        "gaps": gaps,
        "unmapped_source_files": sorted(unmapped),
        "stale_symbols": stale,
    }
