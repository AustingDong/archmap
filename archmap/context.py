"""Context & rendering — serialize tree for agents, ASCII rendering, file scanning."""
from __future__ import annotations
from pathlib import Path
from archmap.core.models import TreeNode, NotFoundError
from archmap.core.store import load_tree, mutate_tree, normalize_path
from archmap.tree_crud import _file_index


def get_context(project_path: str, node_id: str) -> str:
    """Serialize a node's context: breadcrumb path + siblings + children.
    This is what the agent receives to understand its working scope.
    """
    tree = load_tree(project_path)
    if tree is None:
        return "No tree exists yet."

    path = tree.path_to(node_id)
    if path is None:
        raise NotFoundError(f"Node '{node_id}' not found")

    node = path[-1]
    lines = []

    # Breadcrumb
    breadcrumb = " > ".join(n.name for n in path)
    lines.append(f"## Location: {breadcrumb}")
    lines.append("")

    # Current node
    lines.append(f"**{node.name}** ({node.id}) [{node.status}]")
    if node.description:
        lines.append(node.description)
    if node.user_notes:
        lines.append(f"User notes: {node.user_notes}")
    if node.files:
        root = Path(project_path)
        existing = [f for f in node.files if (root / f).exists()]
        stale = [f for f in node.files if not (root / f).exists()]
        if existing:
            lines.append(f"Files: {', '.join(existing)}")
        if stale:
            lines.append(f"STALE files (no longer exist): {', '.join(stale)}")
    if node.cross_references:
        lines.append(f"See also: {', '.join(node.cross_references)}")
    lines.append("")

    # Siblings
    if len(path) >= 2:
        parent = path[-2]
        siblings = [c for c in parent.children if c.id != node_id]
        if siblings:
            lines.append("Siblings:")
            for s in siblings:
                status_mark = "+" if s.status == "confirmed" else "?"
                lines.append(f"  [{status_mark}] {s.name} ({s.id}) -- {s.description}")
            lines.append("")

    # Children
    if node.children:
        lines.append("Children:")
        for c in node.children:
            status_mark = "+" if c.status == "confirmed" else "?"
            lines.append(f"  [{status_mark}] {c.name} ({c.id}) -- {c.description}")
        lines.append("")

    # Hints for agent
    shallow = [c for c in node.children if c.status == "confirmed" and not c.children]
    if shallow:
        lines.append("Hint: These confirmed nodes have no children yet and could be deepened:")
        for c in shallow:
            lines.append(f"  - {c.name} ({c.id})")
        lines.append("")

    return "\n".join(lines)


def render_tree(project_path: str, max_depth: int = 2) -> str:
    """Render the tree as indented plain text up to max_depth levels."""
    tree = load_tree(project_path)
    if tree is None:
        return "No tree exists yet."

    lines: list[str] = []

    def _render(node: TreeNode, depth: int, prefix: str, is_last: bool):
        if depth > max_depth:
            return
        connector = "-- " if is_last else "|-- "
        status = "+" if node.status == "confirmed" else "?"
        if depth == 0:
            lines.append(f"[{status}] {node.name} ({node.id}) -- {node.description}")
        else:
            lines.append(f"{prefix}{connector}[{status}] {node.name} ({node.id}) -- {node.description}")

        child_prefix = prefix + ("    " if is_last else "|   ")
        for i, child in enumerate(node.children):
            _render(child, depth + 1, child_prefix, i == len(node.children) - 1)

    _render(tree, 0, "", True)
    return "\n".join(lines)


# ─── Brief context for hooks ───────────────────────────────────────────────

def get_brief_context(project_path: str, file_path: str) -> str:
    """Return a concise architectural briefing for a file being edited.
    Designed for pre-edit hook injection — 4-6 lines max.
    Returns empty string if the file isn't in the tree."""
    from archmap.tasks import get_active_task

    tree = load_tree(project_path)
    if tree is None:
        return ""

    norm = normalize_path(project_path, file_path)
    index = _file_index(tree)
    node_id = index.get(norm)
    if not node_id:
        return ""

    path = tree.path_to(node_id)
    if not path:
        return ""

    node = path[-1]
    filename = Path(norm).name
    breadcrumb = " > ".join(n.name for n in path)

    lines = [f"[ArchMap] {filename} -> {node.name}"]
    lines.append(f"Branch: {breadcrumb}")

    if node.description:
        lines.append(f"Purpose: {node.description}")

    # Sibling summary: name + primary file
    if len(path) >= 2:
        parent = path[-2]
        siblings = [c for c in parent.children if c.id != node_id]
        if siblings:
            parts = []
            for s in siblings:
                if s.files:
                    primary = Path(s.files[0]).name
                    parts.append(f"{s.name} ({primary})")
                else:
                    parts.append(s.name)
            lines.append(f"Siblings: {', '.join(parts)}")

    if node.user_notes:
        lines.append(f"Notes: {node.user_notes}")

    active = get_active_task(project_path)
    if active:
        lines.append(f"Active task: {active.description}")

    return "\n".join(lines)


def update_file_snapshot(project_path: str, file_path: str) -> bool:
    """Update a file's mtime snapshot in the tree. Returns False if file not in tree."""
    norm = normalize_path(project_path, file_path)
    full = Path(project_path) / norm

    if not full.exists():
        return False

    current_mtime = full.stat().st_mtime

    def _update(tree: TreeNode) -> bool:
        idx = _file_index(tree)
        nid = idx.get(norm)
        if not nid:
            return False
        node = tree.find(nid)
        if node:
            node.file_snapshots[norm] = current_mtime
            return True
        return False

    return mutate_tree(project_path, _update)


# ─── On-demand file scanning ────────────────────────────────────────────────

_SOURCE_EXTS = {
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java",
    ".cs", ".rb", ".swift", ".css", ".scss", ".html", ".vue",
    ".svelte", ".sql", ".graphql", ".proto", ".tf",
}

_SKIP_DIRS = {
    "node_modules", "__pycache__", ".git", ".archmap", "dist",
    "build", ".next", ".venv", "venv", "env", ".tox",
}


def detect_drift(project_path: str) -> list[dict]:
    """Return nodes whose tracked files have changed since last snapshot.
    Compares current file mtime against file_snapshots recorded at attach time."""
    tree = load_tree(project_path)
    if tree is None:
        return []

    root = Path(project_path)
    results: list[dict] = []

    for node in tree.walk():
        if not node.file_snapshots:
            continue
        changed: list[str] = []
        missing: list[str] = []
        for fp, snapshot_mtime in node.file_snapshots.items():
            full = root / fp
            if not full.exists():
                missing.append(fp)
            elif full.stat().st_mtime != snapshot_mtime:
                changed.append(fp)
        if changed or missing:
            results.append({
                "node_id": node.id,
                "node_name": node.name,
                "changed_files": changed,
                "missing_files": missing,
            })

    return results


def suggest_files(project_path: str) -> list[str]:
    """Scan the project and return all unmapped source files."""
    tree = load_tree(project_path)
    mapped: set[str] = set()
    if tree is not None:
        for node in tree.walk():
            mapped.update(node.files)

    root = Path(project_path)
    suggestions: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _SOURCE_EXTS:
            continue
        parts = path.relative_to(root).parts
        if any(p in _SKIP_DIRS for p in parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel not in mapped:
            suggestions.append(rel)

    return suggestions
