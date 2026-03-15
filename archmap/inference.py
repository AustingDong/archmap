"""
Auto dependency inference — scans mapped files for import statements and
derives cross-component dependencies from them.

Supported languages:
  - Python  : stdlib ast (exact, handles relative imports)
  - TypeScript / JavaScript : regex (handles relative imports only)

Only relative / project-local imports are considered.
Third-party packages are ignored — we only care about which component
imports from which other component.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path
from typing import Optional

from archmap.models import Dependency, _short_id
from archmap.store import load_arch, load_mappings, mutate_arch


# ─── Language detectors ────────────────────────────────────────────────────────

_TS_IMPORT_RE = re.compile(
    r"""(?:import|export)\s[^'"]*?['"]([^'"]+)['"]\s*;?|"""
    r"""(?:import|require)\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)


def _ext(path: Path) -> str:
    return path.suffix.lower()


def _is_python(path: Path) -> bool:
    return _ext(path) == ".py"


def _is_ts_js(path: Path) -> bool:
    return _ext(path) in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}


# ─── Python import resolution ──────────────────────────────────────────────────

def _python_module_to_rel(module: str, project_root: Path) -> Optional[str]:
    """Try to resolve a dotted module name to a relative posix path."""
    parts = module.split(".")
    # Try foo/bar/baz.py then foo/bar/baz/__init__.py
    as_file = Path(*parts).with_suffix(".py")
    if (project_root / as_file).exists():
        return as_file.as_posix()
    as_pkg = Path(*parts) / "__init__.py"
    if (project_root / as_pkg).exists():
        return as_pkg.as_posix()
    # Try just the top-level package
    top = Path(parts[0]) / "__init__.py"
    if (project_root / top).exists():
        return top.as_posix()
    return None


def _python_relative_module(
    module: Optional[str], level: int, file_path: Path, project_root: Path
) -> Optional[str]:
    """Resolve a relative `from .foo import bar` import."""
    # level=1 → same package, level=2 → parent package, etc.
    anchor = file_path.parent
    for _ in range(level - 1):
        anchor = anchor.parent
    if module:
        parts = module.split(".")
        candidate = anchor / Path(*parts)
    else:
        candidate = anchor  # `from . import x`

    for suffix in [".py", "/__init__.py"]:
        p = Path(str(candidate) + suffix)
        if p.exists():
            try:
                return p.relative_to(project_root).as_posix()
            except ValueError:
                pass
    return None


def _python_imports(file_path: Path, project_root: Path) -> list[str]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except SyntaxError:
        return []

    results: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                r = _python_module_to_rel(alias.name, project_root)
                if r:
                    results.append(r)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                r = _python_relative_module(node.module, node.level, file_path, project_root)
                if r:
                    results.append(r)
            elif node.module:
                r = _python_module_to_rel(node.module, project_root)
                if r:
                    results.append(r)
    return results


# ─── TS/JS import resolution ───────────────────────────────────────────────────

_TS_EXTENSIONS = [".ts", ".tsx", ".js", ".jsx", ".mjs"]
_TS_INDEX = ["index.ts", "index.tsx", "index.js", "index.jsx"]


def _resolve_ts_specifier(spec: str, file_path: Path, project_root: Path) -> Optional[str]:
    if not spec.startswith("."):
        return None  # node_modules or aliased path — skip
    base = (file_path.parent / spec).resolve()
    # Try exact extensions
    for ext in _TS_EXTENSIONS:
        candidate = base.with_suffix(ext)
        if candidate.exists():
            try:
                return candidate.relative_to(project_root).as_posix()
            except ValueError:
                pass
    # Try as directory with index file
    for idx in _TS_INDEX:
        candidate = base / idx
        if candidate.exists():
            try:
                return candidate.relative_to(project_root).as_posix()
            except ValueError:
                pass
    return None


def _ts_imports(file_path: Path, project_root: Path) -> list[str]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    results: list[str] = []
    for m in _TS_IMPORT_RE.finditer(source):
        spec = m.group(1) or m.group(2)
        if not spec:
            continue
        r = _resolve_ts_specifier(spec, file_path, project_root)
        if r:
            results.append(r)
    return results


# ─── Core inference ────────────────────────────────────────────────────────────

def infer_dependencies(
    project_path: str,
    overwrite_auto: bool = False,
) -> dict:
    """
    Scan all mapped files for imports, derive cross-component dependencies.

    Returns:
      added          — number of new inferred deps written
      skipped        — deps that already existed (confirmed or auto)
      unmapped       — import targets that exist in the project but aren't mapped
      dependencies   — list of dep dicts that were added
    """
    root = Path(project_path)
    mappings = load_mappings(project_path)
    file_map: dict[str, str] = {
        fp: rec["component_id"]
        for fp, rec in mappings.get("files", {}).items()
    }

    arch = load_arch(project_path)
    existing_deps = arch.get("dependencies", [])

    # Build set of already-known (from, to) pairs
    existing_pairs: set[tuple[str, str]] = {
        (d["from_component"], d["to_component"])
        for d in existing_deps
        if d.get("confidence", "confirmed") == "confirmed"
    }
    existing_auto: set[tuple[str, str]] = {
        (d["from_component"], d["to_component"])
        for d in existing_deps
        if d.get("confidence") == "auto"
    }

    # Scan each mapped file
    # inferred_pairs: {(from_comp, to_comp) -> set of source files (for labelling)}
    inferred: dict[tuple[str, str], set[str]] = {}
    unmapped: set[str] = set()

    for rel_path, from_comp in file_map.items():
        abs_path = root / rel_path
        if not abs_path.exists():
            continue

        if _is_python(abs_path):
            imported = _python_imports(abs_path, root)
        elif _is_ts_js(abs_path):
            imported = _ts_imports(abs_path, root)
        else:
            continue

        for imp_rel in imported:
            if imp_rel == rel_path:
                continue  # self-import
            to_comp = file_map.get(imp_rel)
            if to_comp is None:
                # Check if the file exists in the project at all
                if (root / imp_rel).exists():
                    unmapped.add(imp_rel)
                continue
            if to_comp == from_comp:
                continue  # same component — not a cross-boundary dep
            pair = (from_comp, to_comp)
            inferred.setdefault(pair, set()).add(rel_path)

    # Write new deps
    added_deps: list[dict] = []
    skipped = 0

    def _mutate(data: dict) -> None:
        deps = data.setdefault("dependencies", [])
        # Index current auto deps by pair for removal if overwrite_auto
        auto_by_pair: dict[tuple[str, str], dict] = {
            (d["from_component"], d["to_component"]): d
            for d in deps
            if d.get("confidence") == "auto"
        }

        for (from_comp, to_comp), source_files in inferred.items():
            pair = (from_comp, to_comp)

            if pair in existing_pairs:
                # Confirmed dep already covers this — skip regardless
                nonlocal skipped
                skipped += 1
                continue

            if pair in existing_auto:
                if overwrite_auto:
                    # Remove old auto dep and re-add fresh
                    old = auto_by_pair.get(pair)
                    if old:
                        deps.remove(old)
                else:
                    skipped += 1
                    continue

            dep = Dependency.new(
                from_component=from_comp,
                to_component=to_comp,
                label="imports",
                kind="runtime",
                confidence="auto",
            )
            dep_dict = dep.to_dict()
            deps.append(dep_dict)
            added_deps.append(dep_dict)

    mutate_arch(project_path, _mutate)

    return {
        "added": len(added_deps),
        "skipped": skipped,
        "unmapped": sorted(unmapped),
        "dependencies": added_deps,
    }


def confirm_dependency(project_path: str, dependency_id: str) -> dict:
    """Promote an auto-inferred dependency to confirmed."""
    result: dict = {}

    def _mutate(data: dict) -> None:
        for d in data.get("dependencies", []):
            if d["id"] == dependency_id:
                d["confidence"] = "confirmed"
                result.update(d)
                return
        from archmap.models import NotFoundError
        raise NotFoundError(f"Dependency not found: {dependency_id}")

    mutate_arch(project_path, _mutate)
    return result
