"""
ArchMap v2 MCP server — 3 tools for agent interaction.

Tools:
  orient  — See the purpose tree + active task info
  get_task — Get the active task with scoped context
  report  — Report work done: propose tree changes
"""
from __future__ import annotations
from mcp.server.fastmcp import FastMCP

from archmap.core.store import is_initialized, init_project, normalize_path
from archmap.tree import (
    get_tree, render_tree, get_context, detect_drift, get_active_task, list_tasks,
    create_task, propose_addition, propose_removal, _file_index,
)

mcp = FastMCP("archmap")


@mcp.tool()
def orient(project_path: str, depth: int = 2) -> str:
    """See the purpose tree and active task.

    Call this at the start of a session to understand the project structure
    and what you're supposed to be working on.

    Args:
        project_path: Path to the project root
        depth: How many levels deep to show (default 2)
    """
    if not is_initialized(project_path):
        init_project(project_path)
        return (
            "ArchMap initialized for this project.\n"
            "No tree yet. Ask the user what this project is about, "
            "then use report() to propose the root structure."
        )

    parts: list[str] = []

    # Tree
    tree_text = render_tree(project_path, depth)
    parts.append("## Purpose Tree\n")
    parts.append(tree_text)

    # Active task
    active = get_active_task(project_path)
    if active:
        parts.append(f"\n\n## Active Task\n")
        parts.append(f"**{active.description}**")
        if active.target_node_id:
            tree = get_tree(project_path)
            if tree:
                target = tree.find(active.target_node_id)
                if target:
                    parts.append(f"Target: {target.name}")
    else:
        queued = [t for t in list_tasks(project_path) if t.status == "queued"]
        if queued:
            parts.append(f"\n\nNo active task. {len(queued)} task(s) queued.")
        else:
            parts.append("\n\nNo tasks.")

    # Drift detection
    drift = detect_drift(project_path)
    if drift:
        parts.append("\n\n## Drift Detected\n")
        for d in drift:
            changed = ", ".join(d["changed_files"])
            missing = ", ".join(d["missing_files"])
            detail = []
            if changed:
                detail.append(f"changed: {changed}")
            if missing:
                detail.append(f"missing: {missing}")
            parts.append(f"- **{d['node_name']}**: {'; '.join(detail)}")

    return "\n".join(parts)


@mcp.tool()
def get_task(project_path: str) -> str:
    """Get the active task with scoped context.

    Returns the task description plus the tree context around the target node
    (breadcrumb path, siblings, children). This tells you exactly what to work
    on and what scope you're in.

    Args:
        project_path: Path to the project root
    """
    active = get_active_task(project_path)
    if active is None:
        return "No active task. Ask the user what they want to do, then use `report` to create a task."

    parts: list[str] = []
    parts.append(f"## Task: {active.description}")
    parts.append(f"Status: {active.status}")

    if active.target_node_id:
        try:
            ctx = get_context(project_path, active.target_node_id)
            parts.append(f"\n{ctx}")
        except Exception:
            parts.append(f"\nTarget node: {active.target_node_id}")

    if active.proposed_additions:
        parts.append(f"\nAlready proposed: {len(active.proposed_additions)} node(s)")
    if active.proposed_removals:
        parts.append(f"Proposed removals: {len(active.proposed_removals)} node(s)")

    # Drift on target node
    if active.target_node_id:
        drift = detect_drift(project_path)
        target_drift = [d for d in drift if d["node_id"] == active.target_node_id]
        if target_drift:
            d = target_drift[0]
            detail = []
            if d["changed_files"]:
                detail.append(f"changed: {', '.join(d['changed_files'])}")
            if d["missing_files"]:
                detail.append(f"missing: {', '.join(d['missing_files'])}")
            parts.append(f"\n**Drift warning**: {'; '.join(detail)}")

    return "\n".join(parts)


@mcp.tool()
def report(
    project_path: str,
    files_touched: list[str] | None = None,
    proposed_nodes: list[dict] | None = None,
    proposed_removals: list[str] | None = None,
    new_task: str | None = None,
    new_task_target: str | None = None,
) -> str:
    """Report work done and propose tree changes.

    Call this after completing work to update the tree. You can:
    - Propose new nodes (they appear as grey/ghost in the UI for user review)
    - Propose removing existing nodes
    - Create a new task (if the user asked for something)

    Files are attached via proposed_nodes[].files, NOT via files_touched.
    files_touched only reports which files you edited (for tracking).

    Args:
        project_path: Path to the project root
        files_touched: List of file paths you created or modified (for tracking)
        proposed_nodes: List of {parent_id, name, description, files?} to propose as new tree nodes
        proposed_removals: List of node IDs to propose for removal
        new_task: Description for a new task to create (optional)
        new_task_target: Target node ID for the new task (optional)
    """
    parts: list[str] = []

    # Get or create task context
    active = get_active_task(project_path)

    # Create new task if requested
    if new_task:
        task = create_task(project_path, new_task, new_task_target or "")
        parts.append(f"Created task: {task.description} ({task.status})")
        if active is None:
            active = task

    if active is None:
        return "No active task and no new task created. Nothing to report against."

    # Propose additions
    if proposed_nodes:
        for pn in proposed_nodes:
            parent_id = pn.get("parent_id", "")
            name = pn.get("name", "")
            desc = pn.get("description", "")
            files = pn.get("files")
            if not parent_id or not name:
                parts.append(f"Skipped invalid proposal: {pn}")
                continue
            node = propose_addition(project_path, active.id, parent_id, name, desc, files)
            parts.append(f"Proposed: {name} (id: {node.id})")
            if files:
                parts.append(f"  Files migrated to this node: {', '.join(files)}")

    # Propose removals
    if proposed_removals:
        for node_id in proposed_removals:
            try:
                node = propose_removal(project_path, active.id, node_id)
                parts.append(f"Proposed removal: {node.name}")
            except Exception as e:
                parts.append(f"Failed to propose removal of {node_id}: {e}")

    # Report files_touched status (no auto-attach)
    if files_touched:
        tree = get_tree(project_path)
        if tree:
            index = _file_index(tree)
            tracked = []
            new_files = []
            for fp in files_touched:
                norm = normalize_path(project_path, fp)
                if norm in index:
                    owner = tree.find(index[norm])
                    owner_name = owner.name if owner else "?"
                    tracked.append(f"{fp} (on: {owner_name})")
                else:
                    new_files.append(fp)
            if tracked:
                parts.append(f"\nFiles already tracked: {', '.join(tracked)}")
            if new_files:
                parts.append(f"\nNew files not in tree: {', '.join(new_files)}")
                parts.append("Propose a node with these files, or attach them in the UI.")

    if not parts:
        parts.append("Report received. No tree changes proposed.")

    parts.append("\nUser will review proposals in the UI.")
    return "\n".join(parts)


if __name__ == "__main__":
    mcp.run()
