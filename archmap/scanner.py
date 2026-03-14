"""
Heuristic project scanner.
Walks directory tree, detects components from folder structure,
and bulk-maps files to detected components.
"""
from __future__ import annotations
from pathlib import Path
from typing import Optional

from archmap.store import load_arch, normalize_path
from archmap.architecture import add_component, list_components
from archmap.mapping import bulk_map

# Directories to always skip
SKIP_DIRS = {
    ".git", ".archmap", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".env", "dist", "build", ".next", ".nuxt", "out", "coverage",
    ".pytest_cache", ".mypy_cache", ".ruff_cache", ".tox", "eggs",
    "*.egg-info", "__snapshots__", ".cache",
}

# Heuristic: folder name patterns → (layer, suggested color)
LAYER_RULES: list[tuple[set[str], str, str]] = [
    ({"frontend", "ui", "web", "client", "app", "pages", "views", "components"}, "frontend", "#10b981"),
    ({"backend", "server", "api", "service", "services", "routes", "handlers"}, "backend", "#3b82f6"),
    ({"db", "database", "migrations", "models", "schemas", "prisma"}, "database", "#f59e0b"),
    ({"infra", "infrastructure", "deploy", "deployment", "docker", "k8s",
      "kubernetes", "terraform", "helm", ".github", "ci", "cd"}, "infra", "#8b5cf6"),
    ({"lib", "libs", "shared", "common", "utils", "util", "core", "helpers",
      "packages", "pkg"}, "shared", "#6366f1"),
    ({"tests", "test", "spec", "specs", "__tests__", "e2e", "integration"}, "testing", "#ec4899"),
    ({"docs", "doc", "documentation", "wiki"}, "other", "#64748b"),
    ({"scripts", "bin", "tools", "tooling"}, "other", "#64748b"),
    ({"asr", "tts", "ml", "ai", "models", "training"}, "backend", "#3b82f6"),
    ({"memory", "knowledge", "kb", "embeddings", "vector"}, "backend", "#3b82f6"),
]

LAYER_COLORS = {
    "frontend": "#10b981",
    "backend": "#3b82f6",
    "database": "#f59e0b",
    "infra": "#8b5cf6",
    "shared": "#6366f1",
    "testing": "#ec4899",
    "other": "#64748b",
}


def _match_layer(folder_name: str) -> tuple[str, str]:
    """Return (layer, color) for a folder name."""
    lower = folder_name.lower().lstrip(".")
    for patterns, layer, color in LAYER_RULES:
        if lower in patterns:
            return layer, color
    return "other", "#64748b"


def _should_skip(name: str) -> bool:
    return name in SKIP_DIRS or name.startswith(".") and name not in {".github"}


def scan_project(
    project_path: str,
    overwrite_auto: bool = False,
    depth: int = 2,
    max_files_per_component: int = 2000,
) -> dict:
    """
    Walk project_path up to `depth` levels, detect components from folder structure.
    Creates auto-confidence components + bulk-maps files.

    If overwrite_auto=False (default): confirmed components are untouched; auto
    components are skipped if they already exist by name.
    Returns summary dict.
    """
    root = Path(project_path)
    if not root.exists():
        raise FileNotFoundError(f"Project path does not exist: {project_path}")

    # Load existing components to avoid duplicates
    existing = list_components(project_path)
    existing_names = {c["name"].lower() for c in existing}
    existing_auto_ids = {c["id"] for c in existing if c.get("confidence") == "auto"}

    if overwrite_auto:
        # Remove auto components to re-detect
        from archmap.architecture import delete_component
        for cid in list(existing_auto_ids):
            try:
                delete_component(project_path, cid)
            except Exception:
                pass
        existing_names = {c["name"].lower() for c in existing if c.get("confidence") == "confirmed"}

    created_components: list[dict] = []
    file_mappings: list[dict] = []

    def _walk(path: Path, current_depth: int, parent_component: Optional[dict]):
        if current_depth > depth:
            return

        try:
            entries = sorted(path.iterdir())
        except PermissionError:
            return

        for entry in entries:
            if _should_skip(entry.name):
                continue

            if entry.is_dir():
                layer, color = _match_layer(entry.name)
                comp_name = entry.name

                # Check if we should create this component
                comp = None
                if comp_name.lower() not in existing_names:
                    comp = add_component(
                        project_path,
                        name=comp_name,
                        description=f"Auto-detected from folder: {entry.name}/",
                        layer=layer,
                        color=color,
                        confidence="auto",
                    )
                    created_components.append(comp)
                    existing_names.add(comp_name.lower())
                else:
                    # Find existing component to map files to
                    for ec in existing:
                        if ec["name"].lower() == comp_name.lower():
                            comp = ec
                            break

                # Map files inside this folder to the component
                if comp and current_depth <= depth:
                    _collect_files(entry, comp["id"])

            elif entry.is_file() and parent_component:
                rel = normalize_path(project_path, str(entry))
                file_mappings.append({"file_path": rel, "component_id": parent_component["id"]})

    def _collect_files(folder: Path, component_id: str):
        """Recursively collect all files in folder using os.walk (more robust on Windows)."""
        import os
        count = 0
        try:
            for dirpath, dirnames, filenames in os.walk(str(folder), followlinks=False):
                if count >= max_files_per_component:
                    break
                # Prune skipped dirs in-place so os.walk doesn't descend
                dirnames[:] = [d for d in dirnames if not _should_skip(d)]
                for fname in filenames:
                    if count >= max_files_per_component:
                        break
                    try:
                        full = os.path.join(dirpath, fname)
                        rel = normalize_path(project_path, full)
                        file_mappings.append({"file_path": rel, "component_id": component_id})
                        count += 1
                    except (PermissionError, OSError):
                        continue
        except (PermissionError, OSError):
            pass

    _walk(root, 1, None)

    # Bulk map all collected files
    result = bulk_map(project_path, file_mappings, mapped_by="scanner")

    return {
        "components_created": len(created_components),
        "components": [c["name"] for c in created_components],
        "files_mapped": result["mapped"],
        "mapping_errors": len(result["errors"]),
        "message": (
            f"Detected {len(created_components)} components, "
            f"mapped {result['mapped']} files."
        ),
    }
