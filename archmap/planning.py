"""
Hierarchical task management for ArchMap.

Tasks mirror the node hierarchy: a top-level task represents a user requirement;
agents decompose it into sub-tasks linked to progressively finer-grained components.
The decomposition depth is not hardcoded — agents determine how many levels make sense
for the work at hand.

Key operations:
  add_task          — create a root or child task
  decompose_task    — create multiple subtasks under a parent in one call
  complete_task     — close a task; auto-propagates progress to parent
  get_task_tree     — return a full subtree from any node
  check_task_drift  — compare a task's `expects` against actual graph state
  list_tasks        — flat list with filtering

Task schema:
  {
    id:              str
    parent_task_id:  str | None      # None = root requirement
    component_id:    str | None      # node this task is scoped to
    title:           str
    description:     str
    status:          todo | in_progress | done | blocked | cancelled
    priority:        low | medium | high | critical
    created_by:      str             # actor who created this task
    completed_by:    str | None      # actor who closed it
    created_at:      ISO str
    updated_at:      ISO str
    completed_at:    ISO str | None
    subtask_ids:     [str]           # direct children
    subtasks_done:   int
    subtasks_total:  int
    expects: {                       # specification: what this task promises
      files_added:        [str]
      files_modified:     [str]
      symbols_added:      [str]
      symbols_removed:    [str]
      dependencies_added: [str]      # "comp_a → comp_b"
      contract_changes:   dict       # partial contract update expected
    }
    tags: [str]
  }
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from archmap.store import load_plan, mutate_plan, load_mappings


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return "task_" + uuid.uuid4().hex[:10]


def _empty_expects() -> dict:
    return {
        "files_added": [],
        "files_modified": [],
        "symbols_added": [],
        "symbols_removed": [],
        "dependencies_added": [],
        "contract_changes": {},
    }


def _get_task(items: list[dict], task_id: str) -> dict | None:
    return next((i for i in items if i["id"] == task_id), None)


# ─── Public API ───────────────────────────────────────────────────────────────

def add_task(
    project_path: str,
    title: str,
    description: str = "",
    component_id: Optional[str] = None,
    parent_task_id: Optional[str] = None,
    priority: str = "medium",
    created_by: str = "agent",
    expects: Optional[dict] = None,
    tags: Optional[list[str]] = None,
) -> dict:
    """
    Create a new task, optionally as a child of an existing task.

    The task level is implicit — it matches the component it is linked to,
    or is determined by position in the task tree. No hardcoded levels.

    Args:
        title:          Short imperative description ("Add login endpoint").
        description:    Full context, acceptance criteria, design notes.
        component_id:   Node this task is scoped to. May be None for a root requirement.
        parent_task_id: Parent task. When set, this task is a subtask.
        priority:       low | medium | high | critical
        created_by:     Actor identity (e.g. "claude-code", "orchestrator", "alice").
        expects:        Specification of expected graph changes when this task is done.
        tags:           Arbitrary labels.

    Returns the task record.
    """
    task: dict = {
        "id":             _new_id(),
        "parent_task_id": parent_task_id,
        "component_id":   component_id,
        "title":          title,
        "description":    description,
        "status":         "todo",
        "priority":       priority,
        "created_by":     created_by,
        "completed_by":   None,
        "created_at":     _ts(),
        "updated_at":     _ts(),
        "completed_at":   None,
        "subtask_ids":    [],
        "subtasks_done":  0,
        "subtasks_total": 0,
        "expects":        {**_empty_expects(), **(expects or {})},
        "tags":           tags or [],
    }

    def _mutate(data: dict) -> None:
        items: list = data.setdefault("items", [])
        items.append(task)
        # Register as child in parent
        if parent_task_id:
            parent = _get_task(items, parent_task_id)
            if parent is not None:
                parent.setdefault("subtask_ids", []).append(task["id"])
                parent["subtasks_total"] = len(parent["subtask_ids"])
                parent["updated_at"] = _ts()

    mutate_plan(project_path, _mutate)
    return task


def decompose_task(
    project_path: str,
    parent_task_id: str,
    subtasks: list[dict],
    created_by: str = "agent",
) -> dict:
    """
    Create multiple subtasks under a parent task in a single atomic operation.

    Each entry in `subtasks` is passed to add_task() as kwargs. The parent
    task is automatically set.

    Args:
        parent_task_id: Task to decompose.
        subtasks:       List of dicts, each with at minimum a "title" key.
                        Other keys: description, component_id, priority, expects, tags.
        created_by:     Actor performing the decomposition.

    Returns:
        {parent: task_record, created: [task_record, ...]}

    Typical orchestrator workflow:
        # Agent receives high-level task, decomposes into worker tasks
        decompose_task(parent_task_id="task_abc", subtasks=[
            {"title": "Add /auth endpoint", "component_id": "comp_api",
             "expects": {"symbols_added": ["login", "logout"]}},
            {"title": "Add token store", "component_id": "comp_store"},
        ])
    """
    created: list[dict] = []
    for st in subtasks:
        t = add_task(
            project_path,
            title=st.get("title", ""),
            description=st.get("description", ""),
            component_id=st.get("component_id"),
            parent_task_id=parent_task_id,
            priority=st.get("priority", "medium"),
            created_by=created_by,
            expects=st.get("expects"),
            tags=st.get("tags"),
        )
        created.append(t)

    data = load_plan(project_path)
    parent = _get_task(data.get("items", []), parent_task_id)
    return {"parent": parent, "created": created}


def complete_task(
    project_path: str,
    task_id: str,
    completed_by: str = "agent",
    note: str = "",
) -> dict:
    """
    Mark a task done and propagate progress to its parent.

    If all of a parent's subtasks are done, the parent is also marked done
    automatically (recursive propagation up the tree).

    Args:
        task_id:      Task to complete.
        completed_by: Actor closing the task.
        note:         Optional completion note (stored in description suffix).

    Returns:
        {task: task_record, parent_updated: bool, parents_auto_completed: [task_id]}
    """
    now = _ts()
    parent_updated = False
    auto_completed: list[str] = []

    def _mutate(data: dict) -> None:
        nonlocal parent_updated
        items: list = data.get("items", [])
        task = _get_task(items, task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")

        task["status"]       = "done"
        task["completed_by"] = completed_by
        task["completed_at"] = now
        task["updated_at"]   = now
        if note:
            task["description"] = (task.get("description", "") + f"\n\nCompletion note: {note}").strip()

        # Propagate up
        pid = task.get("parent_task_id")
        while pid:
            parent = _get_task(items, pid)
            if parent is None:
                break
            done_children = sum(
                1 for cid in parent.get("subtask_ids", [])
                if (_get_task(items, cid) or {}).get("status") == "done"
            )
            parent["subtasks_done"] = done_children
            parent["updated_at"]    = now
            parent_updated = True
            # Auto-complete parent if all subtasks are done
            total = parent.get("subtasks_total", 0)
            if total > 0 and done_children >= total and parent.get("status") != "done":
                parent["status"]       = "done"
                parent["completed_by"] = f"auto ({completed_by})"
                parent["completed_at"] = now
                auto_completed.append(pid)
            pid = parent.get("parent_task_id")

    mutate_plan(project_path, _mutate)

    data = load_plan(project_path)
    task = _get_task(data.get("items", []), task_id)
    return {
        "task":                 task,
        "parent_updated":       parent_updated,
        "parents_auto_completed": auto_completed,
    }


def get_task_tree(
    project_path: str,
    task_id: str,
    max_depth: int = 10,
) -> dict:
    """
    Return a task and all its descendants as a nested tree.

    Args:
        task_id:   Root of the subtree (any task_id).
        max_depth: Recursion guard (default 10).

    Returns:
        {task fields..., children: [{task fields..., children: [...]}, ...]}
    """
    data = load_plan(project_path)
    by_id = {i["id"]: i for i in data.get("items", [])}

    def _build(tid: str, depth: int) -> dict | None:
        t = by_id.get(tid)
        if t is None or depth > max_depth:
            return None
        node = {**t, "children": []}
        for cid in t.get("subtask_ids", []):
            child = _build(cid, depth + 1)
            if child:
                node["children"].append(child)
        return node

    tree = _build(task_id, 0)
    if tree is None:
        raise KeyError(f"Task not found: {task_id}")
    return tree


def check_task_drift(
    project_path: str,
    task_id: str,
) -> dict:
    """
    Compare a task's `expects` specification against actual graph state.

    Checks whether the work promised by the task has been reflected in the
    graph (symbols synced, files mapped, dependencies added). Intended to
    run after post_edit_sync to confirm the task's implementation is complete.

    Returns:
        {
          task_id:       str,
          title:         str,
          expects:       dict,
          actual:        {symbols_found, symbols_missing, files_found,
                          files_missing, deps_found, deps_missing},
          drift:         bool,
          drift_items:   [str]   # human-readable list of what's missing
        }
    """
    data = load_plan(project_path)
    task = _get_task(data.get("items", []), task_id)
    if task is None:
        raise KeyError(f"Task not found: {task_id}")

    expects = task.get("expects", _empty_expects())
    mappings = load_mappings(project_path)

    # All symbols currently in the graph
    all_symbols: set[str] = set()
    all_files: set[str] = set()
    for fp, rec in mappings.get("files", {}).items():
        all_files.add(fp)
        for sym in rec.get("symbols", []):
            all_symbols.add(sym.get("name", ""))
            all_symbols.add(sym.get("display_name", ""))

    # Check symbols
    expected_symbols = set(expects.get("symbols_added", []))
    symbols_found    = expected_symbols & all_symbols
    symbols_missing  = expected_symbols - all_symbols

    # Check files
    expected_files  = set(expects.get("files_added", []) + expects.get("files_modified", []))
    files_found     = expected_files & all_files
    files_missing   = expected_files - all_files

    # Check dependencies (stored as "comp_a → comp_b" strings)
    from archmap.store import load_arch
    arch = load_arch(project_path)
    existing_dep_pairs = {
        f"{d['from_component']} → {d['to_component']}"
        for d in arch.get("dependencies", [])
    }
    expected_deps = set(expects.get("dependencies_added", []))
    deps_found    = expected_deps & existing_dep_pairs
    deps_missing  = expected_deps - existing_dep_pairs

    drift_items: list[str] = []
    if symbols_missing:
        drift_items.append(f"symbols not found: {', '.join(sorted(symbols_missing))}")
    if files_missing:
        drift_items.append(f"files not in graph: {', '.join(sorted(files_missing))}")
    if deps_missing:
        drift_items.append(f"dependencies not added: {', '.join(sorted(deps_missing))}")

    return {
        "task_id": task_id,
        "title":   task.get("title", ""),
        "expects": expects,
        "actual": {
            "symbols_found":   sorted(symbols_found),
            "symbols_missing": sorted(symbols_missing),
            "files_found":     sorted(files_found),
            "files_missing":   sorted(files_missing),
            "deps_found":      sorted(deps_found),
            "deps_missing":    sorted(deps_missing),
        },
        "drift":       len(drift_items) > 0,
        "drift_items": drift_items,
    }


def list_tasks(
    project_path: str,
    component_id: Optional[str] = None,
    parent_task_id: Optional[str] = "_root_",  # special: only root tasks
    status: Optional[str] = None,
    priority: Optional[str] = None,
    include_subtasks: bool = False,
) -> list[dict]:
    """
    List tasks with optional filtering.

    Args:
        component_id:    Filter to tasks linked to this component.
        parent_task_id:  "_root_" = only root tasks (no parent).
                         None = all tasks regardless of parent.
                         A task_id = only direct children of that task.
        status:          Filter by status.
        priority:        Filter by priority.
        include_subtasks: When True and parent_task_id is set, also return all
                         descendants (not just direct children).
    """
    data = load_plan(project_path)
    items = data.get("items", [])

    if parent_task_id == "_root_":
        items = [i for i in items if not i.get("parent_task_id")]
    elif parent_task_id is not None:
        if include_subtasks:
            # Collect all descendants
            by_id = {i["id"]: i for i in items}
            desc: set[str] = set()
            queue = [parent_task_id]
            while queue:
                cur = queue.pop()
                for cid in by_id.get(cur, {}).get("subtask_ids", []):
                    if cid not in desc:
                        desc.add(cid)
                        queue.append(cid)
            items = [i for i in items if i["id"] in desc]
        else:
            items = [i for i in items if i.get("parent_task_id") == parent_task_id]

    if component_id is not None:
        items = [i for i in items if i.get("component_id") == component_id]
    if status:
        items = [i for i in items if i.get("status") == status]
    if priority:
        items = [i for i in items if i.get("priority") == priority]

    return items


def update_task(
    project_path: str,
    task_id: str,
    **kwargs,
) -> dict:
    """Update mutable task fields: title, description, status, priority, component_id, expects, tags."""
    updatable = {"title", "description", "status", "priority", "component_id", "expects", "tags"}
    result: dict = {}

    def _mutate(data: dict) -> None:
        nonlocal result
        items = data.get("items", [])
        task = _get_task(items, task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        for k, v in kwargs.items():
            if k in updatable and v is not None:
                task[k] = v
        task["updated_at"] = _ts()
        result = task

    mutate_plan(project_path, _mutate)
    return result


def delete_task(project_path: str, task_id: str) -> dict:
    """
    Delete a task and remove it from its parent's subtask_ids.
    Does not recursively delete subtasks — orphaned children remain.
    """
    def _mutate(data: dict) -> None:
        items: list = data.get("items", [])
        task = _get_task(items, task_id)
        if task is None:
            raise KeyError(f"Task not found: {task_id}")
        pid = task.get("parent_task_id")
        if pid:
            parent = _get_task(items, pid)
            if parent:
                parent["subtask_ids"] = [x for x in parent.get("subtask_ids", []) if x != task_id]
                parent["subtasks_total"] = len(parent["subtask_ids"])
                parent["updated_at"] = _ts()
        data["items"] = [i for i in items if i["id"] != task_id]

    mutate_plan(project_path, _mutate)
    return {"deleted": task_id}


def tasks_completed_since_sync(
    project_path: str,
    component_id: str,
    synced_at: str,
) -> int:
    """
    Count tasks completed on a component after a given sync timestamp.
    Used by the completeness scorer to detect graph drift.
    """
    data = load_plan(project_path)
    count = 0
    for item in data.get("items", []):
        if item.get("component_id") != component_id:
            continue
        if item.get("status") != "done":
            continue
        completed_at = item.get("completed_at") or ""
        if completed_at > synced_at:
            count += 1
    return count


# ─── Backward-compatibility shims (old flat API still works) ──────────────────

def create_plan_item(project_path: str, title: str, **kwargs) -> dict:
    """Alias for add_task() — keeps bootstrap_architecture working."""
    return add_task(project_path, title=title, **kwargs)


def list_plan_items(project_path: str, **kwargs) -> list[dict]:
    """Alias for list_tasks() with all=True (no parent filter)."""
    return list_tasks(project_path, parent_task_id=None, **{
        k: v for k, v in kwargs.items()
        if k in {"component_id", "status", "priority"}
    })


def update_plan_item(project_path: str, item_id: str, **kwargs) -> dict:
    return update_task(project_path, item_id, **kwargs)


def delete_plan_item(project_path: str, item_id: str) -> str:
    delete_task(project_path, item_id)
    return "deleted"
