---
name: work-task
description: This skill should be used when an agent session begins, when the user asks to "work on the next task", "check tasks", "continue working", "what should I do next", or when the agent needs guidance on the ArchMap orient-work-report loop. Provides the core workflow for interacting with the ArchMap purpose tree via MCP tools.
---

# ArchMap — Work Task

Core workflow for agents interacting with the ArchMap purpose tree.
ArchMap uses a depth-first stack: tasks decompose until they reach implementation leaves where code is written and files are attached.

Project path for all tool calls: read from CLAUDE.md, or ask the user.

---

## The Loop

Every session follows four steps. No exceptions.

### Step 1 — Orient

```
orient(project_path="<path>", depth=2)
```

Read the tree and check for an active task. This must be the first action.

### Step 2 — Get Task

```
get_task(project_path="<path>")
```

If an active task exists, this is the assignment. The response includes:
- Breadcrumb path (where in the tree)
- Sibling nodes (what else exists at this level)
- Children (what's already been decomposed)
- Hints (childless nodes that need deepening)

### Step 3 — Do the Work

Two modes, determined by the task description:

**Decomposition task** ("Propose children for X"):
- Read the target node's files and context
- Identify 2-6 sub-purposes that partition the node's responsibility
- Propose grey nodes via `report()` with `proposed_nodes`
- Do NOT write code — this is a planning step

**Implementation task** (specific work like "Add auth middleware"):
- Write the code
- Attach files to leaf nodes via `proposed_nodes[].files`
- If the scope is too large, decompose into subtasks instead

Decision rule: if the task requires more than ~3 files, decompose further. If it maps to a single focused change, implement it.

### Step 4 — Report

```
report(
    project_path="<path>",
    files_touched=["...files edited..."],
    proposed_nodes=[{"parent_id": "...", "name": "...", "description": "...", "files": [...]}],
)
```

Always call report before responding. Include:
- `files_touched` — files created or modified (for tracking)
- `proposed_nodes` — new tree nodes to propose (grey until user approves)
- `proposed_removals` — node IDs to remove
- `new_task` / `new_task_target` — create follow-up tasks if needed

---

## Stack-Based Pacing

Tasks use LIFO (stack) ordering. When a task creates subtasks, those subtasks activate next (depth-first). The workflow:

1. Planning task proposes grey children for a node
2. User approves grey nodes -> they become confirmed
3. Confirmed childless nodes auto-create "Propose children for" tasks
4. Those tasks land on top of the stack, solved before sibling branches
5. Eventually a leaf is reached -> implementation task writes code + attaches files
6. Branch complete -> stack unwinds to next sibling

Files only attach at leaf nodes during implementation. Intermediate nodes own no files — they represent purpose, not code.

---

## Proposing Nodes

When decomposing, each proposed node needs:

| Field | Required | Purpose |
|-------|----------|---------|
| `parent_id` | yes | ID of the node being decomposed |
| `name` | yes | Short purpose name (2-4 words) |
| `description` | yes | One sentence: what this sub-purpose owns |
| `files` | no | Only for implementation leaves — source files this node owns |

Aim for 2-6 children per node. Each child should be:
- **Cohesive** — one clear responsibility
- **Disjoint** — no overlap with siblings
- **Named by purpose** — "Auth Middleware", not "auth.py"

---

## Node Statuses

| Status | Meaning | Who sets it |
|--------|---------|-------------|
| `confirmed` | Reviewed and approved | User (via UI) |
| `proposed` | Grey/ghost, awaiting review | Agent (via report) |
| `removing` | Marked for deletion, awaiting review | Agent (via report) |

---

## Additional Resources

### Reference Files

For detailed guidance, consult:
- **`references/workflow.md`** — Depth-first stack workflow explained with examples
- **`references/tree-model.md`** — Node lifecycle, status transitions, file attachment rules
- **`references/mcp-tools.md`** — Complete MCP tool reference (orient, get_task, report)
