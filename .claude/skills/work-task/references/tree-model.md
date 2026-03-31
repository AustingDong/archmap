# Purpose Tree Model

## Core Concept

The tree is a hierarchy where **depth = abstraction level**. The root is the most abstract (the whole system), leaves are the most concrete (individual concerns backed by files).

Each node represents a **purpose** — what a part of the system is responsible for — not a file or directory.

## Node Structure

```
TreeNode:
  id            — 8-char hex, auto-generated
  name          — Short purpose name (2-4 words)
  description   — One sentence: what this node owns
  status        — confirmed | proposed | removing
  files         — List of relative file paths owned by this node
  children      — Child nodes (sub-purposes)
  user_notes    — Optional notes from the user
  cross_references — Links to related nodes
  created_at    — ISO timestamp
  updated_at    — ISO timestamp
```

## Status Lifecycle

```
[Agent proposes]     →  proposed (grey)
[User approves]      →  confirmed (solid)
[Agent proposes del] →  removing (strikethrough)
[User approves del]  →  removed from tree
[User rejects]       →  reverts (proposed→deleted, removing→confirmed)
```

### Status Transitions

| From | To | Triggered by |
|------|----|-------------|
| (new) | proposed | `propose_addition()` via report |
| proposed | confirmed | `approve_proposal()` in UI |
| proposed | (deleted) | `reject_proposal()` in UI |
| proposed | confirmed | `complete_task()` auto-promotes |
| confirmed | removing | `propose_removal()` via report |
| removing | (deleted) | `approve_proposal()` in UI |
| removing | confirmed | `reject_proposal()` in UI |

## File Ownership

### Rules

1. **Global uniqueness** — each file path appears on at most one node in the entire tree
2. **Leaf attachment** — files should be attached during implementation, at the deepest node level
3. **Migration** — when a child is proposed with `files`, those files move from their current owner to the new node
4. **Barrel files** — re-export files (e.g., `__init__.py`) may stay on intermediate nodes

### What Counts as a File

Source code only:
- `.py`, `.ts`, `.tsx`, `.js`, `.jsx`, `.go`, `.rs`, `.java`
- `.css`, `.scss`, `.html`, `.vue`, `.svelte`
- `.sql`, `.graphql`, `.proto`, `.tf`

Test files map to the node they test.

Skip: `node_modules/`, `__pycache__/`, `dist/`, `.git/`, config files, documentation, binaries.

## Tree Operations

### User Operations (via UI)
- Add child node (confirmed immediately)
- Edit node name/description/notes
- Remove node
- Move node to different parent
- Attach/detach files
- Approve/reject proposals

### Agent Operations (via MCP report tool)
- Propose new nodes (grey until approved)
- Propose removals (strikethrough until approved)
- Attach files to proposed nodes
- Create new tasks

Agents cannot directly modify confirmed nodes — they can only propose changes that the user reviews.

## Depth Guidelines

| Level | Abstraction | Example |
|-------|------------|---------|
| 0 (root) | The whole system | "ArchMap" |
| 1 | Major subsystems | "Persistence", "Agent Interface" |
| 2 | Functional areas | "Tree CRUD", "Task Queue" |
| 3 | Specific concerns | "Stack Ordering", "Dedup Guard" |
| 4+ | Implementation leaves | "LIFO Activation" (owns `tasks.py`) |

Not every branch needs the same depth. Some concerns are simple (2 levels), others are complex (4+ levels). Let the complexity of the code drive the depth.
