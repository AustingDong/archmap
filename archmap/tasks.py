"""Task stack — create, list, activate, complete, reject tasks. Controls pacing.

Tasks use LIFO (stack) ordering: the most recently created task activates next.
This drives depth-first tree construction — deepening tasks get solved before
moving to sibling branches. Files naturally land at leaf nodes."""
from __future__ import annotations
from archmap.core.models import TreeNode, Task, NotFoundError, _now
from archmap.core.store import load_tree, save_tree, load_tasks, mutate_tasks


def _maybe_create_deepening_task(project_path: str, node_id: str, node_name: str) -> None:
    """Create a 'Propose children for' task if the node has no children and no such task exists."""
    existing = load_tasks(project_path)
    already_has = any(
        t.target_node_id == node_id
        and t.status in ("queued", "active")
        and "Propose children for" in t.description
        for t in existing
    )
    if not already_has:
        try:
            create_task(project_path, f"Propose children for: {node_name}", target_node_id=node_id)
        except Exception:
            pass


def list_tasks(project_path: str) -> list[Task]:
    return load_tasks(project_path)


def get_active_task(project_path: str) -> Task | None:
    for t in load_tasks(project_path):
        if t.status == "active":
            return t
    return None


def create_task(
    project_path: str,
    description: str,
    target_node_id: str = "",
    parent_task_id: str = "",
) -> Task:
    task = Task.new(description, target_node_id=target_node_id, parent_task_id=parent_task_id)

    def _add(tasks: list[Task]) -> Task:
        has_active = any(t.status == "active" for t in tasks)
        if not has_active:
            task.status = "active"
        tasks.append(task)
        return task

    return mutate_tasks(project_path, _add)


def activate_next_task(project_path: str) -> Task | None:
    """Activate the most recently created queued task (LIFO/stack order).
    This ensures depth-first tree construction — deepening subtasks
    are solved before sibling branches."""
    def _activate(tasks: list[Task]) -> Task | None:
        for t in reversed(tasks):
            if t.status == "queued":
                t.status = "active"
                return t
        return None

    return mutate_tasks(project_path, _activate)


def complete_task(project_path: str, task_id: str, auto_advance: bool = False) -> Task:
    """Mark a task as done. Proposed nodes become provisional; unconfirmed removals revert."""
    def _complete(tasks: list[Task]) -> Task:
        for t in tasks:
            if t.id == task_id:
                t.status = "done"
                return t
        raise NotFoundError(f"Task '{task_id}' not found")

    result = mutate_tasks(project_path, _complete)

    tree = load_tree(project_path)
    newly_confirmed: list[TreeNode] = []
    if tree is not None:
        changed = False
        for node in tree.walk():
            if node.status == "proposed" and node.id in result.proposed_additions:
                node.status = "confirmed"
                changed = True
                if not node.children:
                    newly_confirmed.append(node)
            elif node.status == "removing" and node.id in result.proposed_removals:
                node.status = "confirmed"
                changed = True
        if changed:
            save_tree(project_path, tree)

    # Auto-deepen: create tasks for childless nodes that just became confirmed
    for node in newly_confirmed:
        _maybe_create_deepening_task(project_path, node.id, node.name)

    if auto_advance:
        activate_next_task(project_path)

    return result


def reject_task(project_path: str, task_id: str, auto_advance: bool = False) -> Task:
    """Reject a task. Remove all its proposed nodes, revert removals."""
    def _reject(tasks: list[Task]) -> Task:
        for t in tasks:
            if t.id == task_id:
                t.status = "rejected"
                return t
        raise NotFoundError(f"Task '{task_id}' not found")

    result = mutate_tasks(project_path, _reject)

    tree = load_tree(project_path)
    if tree is not None and (result.proposed_additions or result.proposed_removals):
        additions_set = set(result.proposed_additions)

        def _prune(node: TreeNode):
            node.children = [c for c in node.children if c.id not in additions_set]
            for c in node.children:
                _prune(c)

        _prune(tree)
        for node in tree.walk():
            if node.status == "removing" and node.id in result.proposed_removals:
                node.status = "confirmed"
        save_tree(project_path, tree)

    if auto_advance:
        activate_next_task(project_path)

    return result
