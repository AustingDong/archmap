"""Tree CRUD — create, read, update, remove, move nodes + file attachment."""
from __future__ import annotations
from pathlib import Path
from archmap.core.models import TreeNode, NotFoundError, _now
from archmap.core.store import load_tree, save_tree, mutate_tree, normalize_path


def _file_index(tree: TreeNode) -> dict[str, str]:
    """Return {file_path: node_id} for every file in the entire tree.
    Each file appears on exactly one node — this is the global index."""
    index: dict[str, str] = {}
    for node in tree.walk():
        for f in node.files:
            index[f] = node.id
    return index


def get_tree(project_path: str) -> TreeNode | None:
    return load_tree(project_path)


def create_root(project_path: str, name: str, description: str = "") -> TreeNode:
    existing = load_tree(project_path)
    if existing is not None:
        raise ValueError("Tree already exists. Reset first.")
    root = TreeNode.new(name, description=description, status="confirmed")
    save_tree(project_path, root)
    return root


def add_node(
    project_path: str,
    parent_id: str,
    name: str,
    description: str = "",
) -> TreeNode:
    """Add a child node. User-created nodes are confirmed immediately."""
    new_node = TreeNode.new(name, description=description, status="confirmed")

    def _add(tree: TreeNode) -> TreeNode:
        parent = tree.find(parent_id)
        if parent is None:
            raise NotFoundError(f"Parent node '{parent_id}' not found")
        parent.children.append(new_node)
        parent.updated_at = _now()
        return new_node

    mutate_tree(project_path, _add)
    return new_node


def update_node(
    project_path: str,
    node_id: str,
    name: str | None = None,
    description: str | None = None,
    user_notes: str | None = None,
) -> TreeNode:
    def _update(tree: TreeNode) -> TreeNode:
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        if name is not None:
            node.name = name
        if description is not None:
            node.description = description
        if user_notes is not None:
            node.user_notes = user_notes
        node.updated_at = _now()
        return node

    return mutate_tree(project_path, _update)


def remove_node(project_path: str, node_id: str) -> str:
    def _remove(tree: TreeNode) -> str:
        if tree.id == node_id:
            raise ValueError("Cannot remove the root node. Use reset_tree instead.")
        for node in tree.walk():
            for i, child in enumerate(node.children):
                if child.id == node_id:
                    removed = node.children.pop(i)
                    node.updated_at = _now()
                    return removed.name
        raise NotFoundError(f"Node '{node_id}' not found")

    return mutate_tree(project_path, _remove)


def move_node(project_path: str, node_id: str, new_parent_id: str) -> TreeNode:
    def _move(tree: TreeNode) -> TreeNode:
        if node_id == new_parent_id:
            raise ValueError("Cannot move a node under itself")
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        if node.find(new_parent_id) is not None:
            raise ValueError("Cannot move a node under its own descendant")
        new_parent = tree.find(new_parent_id)
        if new_parent is None:
            raise NotFoundError(f"New parent '{new_parent_id}' not found")
        for n in tree.walk():
            for i, child in enumerate(n.children):
                if child.id == node_id:
                    n.children.pop(i)
                    n.updated_at = _now()
                    break
        new_parent.children.append(node)
        new_parent.updated_at = _now()
        return node

    return mutate_tree(project_path, _move)


# ─── File attachment (global uniqueness) ─────────────────────────────────────

def attach_files(project_path: str, node_id: str, file_paths: list[str]) -> TreeNode:
    """Attach files to a node. Enforces global uniqueness:
    - If file is already on this node → skip
    - If file is on another node → MOVE it (detach old, attach new)
    - If new file → attach
    """
    def _attach(tree: TreeNode) -> TreeNode:
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        index = _file_index(tree)
        for fp in file_paths:
            norm = normalize_path(project_path, fp)
            if norm in node.files:
                continue
            # Move from old owner if exists
            if norm in index:
                old_owner = tree.find(index[norm])
                if old_owner and old_owner.id != node_id:
                    old_owner.files.remove(norm)
                    old_owner.file_snapshots.pop(norm, None)
                    old_owner.updated_at = _now()
            node.files.append(norm)
            # Snapshot mtime for drift detection
            full = Path(project_path) / norm
            if full.exists():
                node.file_snapshots[norm] = full.stat().st_mtime
        node.updated_at = _now()
        return node

    return mutate_tree(project_path, _attach)


def detach_file(project_path: str, node_id: str, file_path: str) -> TreeNode:
    def _detach(tree: TreeNode) -> TreeNode:
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        norm = normalize_path(project_path, file_path)
        if norm in node.files:
            node.files.remove(norm)
            node.file_snapshots.pop(norm, None)
        node.updated_at = _now()
        return node

    return mutate_tree(project_path, _detach)
