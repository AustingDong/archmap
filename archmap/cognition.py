"""
Architecture cognition queries — agent-oriented tools for ownership, interfaces,
and integrity checking. Operates on the knowledge graph without reading source files.
"""
from __future__ import annotations
import hashlib
from pathlib import Path

from archmap.repo import load_arch, load_mappings, load_plan


def _sym_name_match(sym_dict: dict, query: str) -> bool:
    """Match a symbol dict against a query name (strips parens, case-sensitive)."""
    clean = query.rstrip("()")
    return sym_dict.get("name", "") == clean or sym_dict.get("display_name", "").rstrip("()") == clean


def who_owns_symbol(project_path: str, symbol_name: str) -> list[dict]:
    """
    Find which file and component owns a named symbol.
    Searches new-format symbols and falls back to legacy metadata.functions.
    Returns a list (may have multiple matches if symbol is defined in several files).
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)

    name_map = {c["id"]: c for c in arch.get("components", [])}
    results: list[dict] = []

    for fp, rec in mappings.get("files", {}).items():
        comp_id = rec.get("component_id", "")
        comp = name_map.get(comp_id, {})

        # New-format symbols
        for sym in rec.get("symbols", []):
            if _sym_name_match(sym, symbol_name):
                results.append({
                    "symbol_id": sym.get("id", ""),
                    "name": sym.get("name", ""),
                    "display_name": sym.get("display_name", sym.get("name", "")),
                    "kind": sym.get("kind", "function"),
                    "visibility": sym.get("visibility", "public"),
                    "is_entry_point": sym.get("is_entry_point", False),
                    "signature": sym.get("signature", ""),
                    "doc": sym.get("doc", ""),
                    "file_path": fp,
                    "language": rec.get("language", rec.get("metadata", {}).get("language", "")),
                    "component_id": comp_id,
                    "component_name": comp.get("name", ""),
                    "layer": comp.get("layer", ""),
                    "synced_at": rec.get("synced_at", ""),
                    "is_stale": not rec.get("content_hash", ""),  # no hash = not yet synced
                })

        # Legacy fallback: metadata.functions (strings)
        if not rec.get("symbols"):
            meta = rec.get("metadata", {})
            for fn in meta.get("functions", []):
                raw = fn.rstrip("()")
                if raw == symbol_name.rstrip("()"):
                    # Find matching detail if available
                    detail = next(
                        (d for d in meta.get("symbol_details", []) if d.get("name", "").rstrip("()") == raw),
                        {}
                    )
                    results.append({
                        "symbol_id": "",
                        "name": raw,
                        "display_name": fn,
                        "kind": "class" if fn == raw else "function",
                        "visibility": "private" if raw.startswith("_") else "public",
                        "is_entry_point": raw in {"main", "run", "app", "start", "cli"},
                        "signature": detail.get("signature", ""),
                        "doc": detail.get("doc", ""),
                        "file_path": fp,
                        "language": meta.get("language", ""),
                        "component_id": comp_id,
                        "component_name": comp.get("name", ""),
                        "layer": comp.get("layer", ""),
                        "synced_at": rec.get("synced_at", ""),
                        "is_stale": True,  # legacy = not yet upgraded
                    })

    return results


def get_component_interface(project_path: str, component_id: str) -> dict:
    """
    Return the public interface of a component:
    - exports: public symbols this component makes available
    - used_by: which components depend on this one (upstream)
    - imports_from: which components this one depends on, with their exported symbols
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)

    comp_name_map = {c["id"]: c.get("name", c["id"]) for c in arch.get("components", [])}
    comp_map = {c["id"]: c for c in arch.get("components", [])}
    deps = arch.get("dependencies", [])

    if component_id not in comp_map:
        return {"error": f"Component not found: {component_id}"}

    comp = comp_map[component_id]

    # Files belonging to this component
    component_files = {fp: rec for fp, rec in mappings.get("files", {}).items()
                       if rec.get("component_id") == component_id}

    # Public exports: public symbols in this component's files
    exports: list[dict] = []
    for fp, rec in component_files.items():
        for sym in rec.get("symbols", []):
            if sym.get("visibility", "public") == "public":
                exports.append({
                    "symbol_id": sym.get("id", ""),
                    "name": sym.get("name", ""),
                    "display_name": sym.get("display_name", sym.get("name", "")),
                    "kind": sym.get("kind", "function"),
                    "signature": sym.get("signature", ""),
                    "doc": sym.get("doc", ""),
                    "file_path": fp,
                    "is_entry_point": sym.get("is_entry_point", False),
                })
        # Legacy fallback
        if not rec.get("symbols"):
            meta = rec.get("metadata", {})
            for fn in meta.get("functions", []):
                raw = fn.rstrip("()")
                if not raw.startswith("_"):
                    exports.append({
                        "symbol_id": "",
                        "name": raw,
                        "display_name": fn,
                        "kind": "class" if fn == raw else "function",
                        "signature": "",
                        "doc": "",
                        "file_path": fp,
                        "is_entry_point": False,
                    })

    # Upstream: components that depend ON this component
    upstream_deps = [d for d in deps if d.get("to_component") == component_id]
    used_by = [
        {
            "component_id": d["from_component"],
            "component_name": comp_name_map.get(d["from_component"], d["from_component"]),
            "dependency_id": d["id"],
            "label": d.get("label", "uses"),
            "confidence": d.get("confidence", "confirmed"),
            "via_symbols": d.get("via_symbols", []),
        }
        for d in upstream_deps
    ]

    # Downstream: components this one depends on, with what's available to import
    downstream_deps = [d for d in deps if d.get("from_component") == component_id]
    imports_from: list[dict] = []
    for d in downstream_deps:
        to_id = d.get("to_component", "")
        to_files = {fp: rec for fp, rec in mappings.get("files", {}).items()
                    if rec.get("component_id") == to_id}
        available: list[str] = []
        for fp, rec in to_files.items():
            for sym in rec.get("symbols", []):
                if sym.get("visibility", "public") == "public":
                    available.append(sym.get("display_name", sym.get("name", "")))
            if not rec.get("symbols"):
                for fn in rec.get("metadata", {}).get("functions", []):
                    if not fn.startswith("_"):
                        available.append(fn)
        imports_from.append({
            "component_id": to_id,
            "component_name": comp_name_map.get(to_id, to_id),
            "dependency_id": d["id"],
            "label": d.get("label", "uses"),
            "confidence": d.get("confidence", "confirmed"),
            "via_symbols": d.get("via_symbols", []),
            "available_exports": available[:20],  # cap to keep response lean
        })

    return {
        "component_id": component_id,
        "component_name": comp.get("name", ""),
        "layer": comp.get("layer", ""),
        "exports": exports,
        "export_count": len(exports),
        "used_by": used_by,
        "imports_from": imports_from,
        "file_count": len(component_files),
    }


def check_integrity(project_path: str) -> dict:
    """
    Comprehensive health check of the architecture model against the actual repo.
    Detects: stale files, missing files, dangling deps, unmapped source files,
    orphan plan items.
    """
    arch = load_arch(project_path)
    mappings = load_mappings(project_path)
    plan = load_plan(project_path)

    root = Path(project_path)
    component_ids = {c["id"] for c in arch.get("components", [])}
    files_data = mappings.get("files", {})

    # ── Stale and missing files ──────────────────────────────────────────────
    stale_files: list[dict] = []
    missing_files: list[dict] = []

    for fp, rec in files_data.items():
        full = root / fp
        if not full.exists():
            missing_files.append({
                "path": fp,
                "component_id": rec.get("component_id", ""),
                "mapped_at": rec.get("mapped_at", ""),
            })
        else:
            stored_hash = rec.get("content_hash", "")
            if not stored_hash:
                stale_files.append({
                    "path": fp,
                    "component_id": rec.get("component_id", ""),
                    "synced_at": rec.get("synced_at", "never"),
                    "reason": "no content_hash — call post_edit_sync to initialize",
                })
            else:
                current = hashlib.sha256(full.read_bytes()).hexdigest()
                if current != stored_hash:
                    stale_files.append({
                        "path": fp,
                        "component_id": rec.get("component_id", ""),
                        "synced_at": rec.get("synced_at", "unknown"),
                        "reason": "content changed since last sync",
                    })

    # ── Dangling dependencies ────────────────────────────────────────────────
    dangling_deps: list[dict] = []
    for d in arch.get("dependencies", []):
        if d.get("from_component") not in component_ids:
            dangling_deps.append({
                "dep_id": d["id"],
                "from_component": d.get("from_component", ""),
                "to_component": d.get("to_component", ""),
                "reason": f"from_component '{d.get('from_component')}' not found",
            })
        elif d.get("to_component") not in component_ids:
            dangling_deps.append({
                "dep_id": d["id"],
                "from_component": d.get("from_component", ""),
                "to_component": d.get("to_component", ""),
                "reason": f"to_component '{d.get('to_component')}' not found",
            })

    # ── Unmapped source files ────────────────────────────────────────────────
    mapped_paths = set(files_data.keys())
    source_exts = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs"}
    ignore_dirs = {
        ".archmap", ".git", "node_modules", "__pycache__", ".venv", "venv",
        "dist", "build", ".next", "coverage", ".pytest_cache", "env",
    }
    unmapped: list[str] = []
    try:
        for entry in root.rglob("*"):
            if not entry.is_file():
                continue
            if entry.suffix.lower() not in source_exts:
                continue
            # Skip ignored directories
            parts = set(entry.relative_to(root).parts[:-1])
            if parts & ignore_dirs:
                continue
            rel = entry.relative_to(root).as_posix()
            if rel not in mapped_paths:
                unmapped.append(rel)
                if len(unmapped) >= 100:  # cap to avoid huge responses
                    break
    except Exception:
        pass

    # ── Orphan plan items ────────────────────────────────────────────────────
    orphan_plans: list[dict] = []
    for item in plan.get("items", []):
        cid = item.get("component_id")
        if cid and cid not in component_ids:
            orphan_plans.append({
                "plan_id": item["id"],
                "title": item.get("title", ""),
                "component_id": cid,
                "status": item.get("status", ""),
            })

    total_issues = (
        len(stale_files) + len(missing_files) +
        len(dangling_deps) + len(orphan_plans)
    )

    return {
        "healthy": total_issues == 0,
        "stale_files": stale_files,
        "missing_files": missing_files,
        "dangling_deps": dangling_deps,
        "unmapped_files": unmapped,
        "unmapped_count": len(unmapped),
        "orphan_plan_items": orphan_plans,
        "summary": {
            "stale": len(stale_files),
            "missing": len(missing_files),
            "dangling_deps": len(dangling_deps),
            "unmapped": len(unmapped),
            "orphan_plans": len(orphan_plans),
            "total_issues": total_issues,
        },
    }
