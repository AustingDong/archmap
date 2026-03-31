"""Proposals — agent proposes additions/removals, user approves/rejects."""
from __future__ import annotations
from pathlib import Path
from archmap.core.models import TreeNode, NotFoundError, _now
from archmap.core.store import mutate_tree, normalize_path, mutate_tasks
from archmap.tree_crud import _file_index


def propose_addition(
    project_path: str,
    task_id: str,
    parent_id: str,
    name: str,
    description: str = "",
    files: list[str] | None = None,
) -> TreeNode:
    """Agent proposes a new node under parent_id. Creates a grey (proposed) node.
    Files are migrated from wherever they currently exist (global uniqueness)."""
    new_node = TreeNode.new(name, description=description, status="proposed")

    def _add_to_tree(tree: TreeNode) -> TreeNode:
        parent = tree.find(parent_id)
        if parent is None:
            raise NotFoundError(f"Parent node '{parent_id}' not found")
        if files:
            index = _file_index(tree)
            for f in files:
                norm = normalize_path(project_path, f)
                # Move from old owner if exists (including parent)
                if norm in index:
                    old_owner = tree.find(index[norm])
                    if old_owner:
                        old_owner.files.remove(norm)
                        old_owner.file_snapshots.pop(norm, None)
                        old_owner.updated_at = _now()
                new_node.files.append(norm)
                # Snapshot mtime for drift detection
                full = Path(project_path) / norm
                if full.exists():
                    new_node.file_snapshots[norm] = full.stat().st_mtime
        parent.children.append(new_node)
        parent.updated_at = _now()
        return new_node

    mutate_tree(project_path, _add_to_tree)

    def _link(tasks: list) -> None:
        for t in tasks:
            if t.id == task_id:
                t.proposed_additions.append(new_node.id)
                return
        raise NotFoundError(f"Task '{task_id}' not found")

    mutate_tasks(project_path, _link)
    return new_node


def propose_removal(project_path: str, task_id: str, node_id: str) -> TreeNode:
    """Agent proposes removing an existing node. Marks it as 'removing'."""
    def _mark(tree: TreeNode) -> TreeNode:
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        node.status = "removing"
        node.updated_at = _now()
        return node

    result = mutate_tree(project_path, _mark)

    def _link(tasks: list) -> None:
        for t in tasks:
            if t.id == task_id:
                t.proposed_removals.append(node_id)
                return

    mutate_tasks(project_path, _link)
    return result


def approve_proposal(project_path: str, node_id: str) -> TreeNode:
    """User approves a proposed node (proposed -> confirmed directly).
    Auto-creates a deepening task if the confirmed node has no children."""
    from archmap.tasks import _maybe_create_deepening_task

    def _approve(tree: TreeNode) -> TreeNode:
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        if node.status == "proposed":
            node.status = "confirmed"
        elif node.status == "removing":
            for parent in tree.walk():
                for i, child in enumerate(parent.children):
                    if child.id == node_id:
                        parent.children.pop(i)
                        return child
        node.updated_at = _now()
        return node

    result = mutate_tree(project_path, _approve)

    # Auto-deepen: confirmed childless node gets a deepening task
    if result.status == "confirmed" and not result.children:
        _maybe_create_deepening_task(project_path, node_id, result.name)

    return result


def reject_proposal(project_path: str, node_id: str) -> str:
    """User rejects a proposed node — remove it, or revert a removal."""
    def _reject(tree: TreeNode) -> str:
        node = tree.find(node_id)
        if node is None:
            raise NotFoundError(f"Node '{node_id}' not found")
        if node.status == "proposed":
            for parent in tree.walk():
                for i, child in enumerate(parent.children):
                    if child.id == node_id:
                        parent.children.pop(i)
                        return child.name
        elif node.status == "removing":
            node.status = "confirmed"
            node.updated_at = _now()
            return node.name
        return node.name

    return mutate_tree(project_path, _reject)
