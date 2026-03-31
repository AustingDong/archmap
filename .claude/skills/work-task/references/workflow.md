# Depth-First Stack Workflow

## Why a Stack

ArchMap uses LIFO task ordering to drive depth-first tree construction. The alternative — a FIFO queue — produces breadth-first construction where all nodes at one level are decomposed before any node is deepened further. This causes two problems:

1. **Files land at the wrong level.** Breadth-first means intermediate nodes accumulate files because deeper structure doesn't exist yet.
2. **Context is wasted.** By the time the agent returns to deepen a node, it has lost context from the planning phase.

With a stack, each branch is fully resolved before the next begins. Files naturally land at leaf nodes during implementation.

## Example Walkthrough

Starting state: root node "MyApp" with no children.

```
Task: "Propose children for: MyApp"           ← active

Agent proposes: Auth, Storage, API
User approves all three → auto-creates:
  Task: "Propose children for: API"            ← stack top (most recent)
  Task: "Propose children for: Storage"
  Task: "Propose children for: Auth"

Next active: "Propose children for: API"       ← LIFO picks most recent
Agent proposes: Routes, Middleware
User approves → auto-creates:
  Task: "Propose children for: Middleware"     ← stack top
  Task: "Propose children for: Routes"

Next active: "Propose children for: Middleware"
Agent decides: this is a leaf → implements it
  → writes middleware.py, attaches to Middleware node
  → branch done

Next active: "Propose children for: Routes"
Agent implements → writes routes.py, attaches to Routes node

Next active: "Propose children for: Storage"   ← unwinds to next branch
...continues depth-first
```

## Decision: Decompose or Implement?

At each task, the agent decides:

**Decompose** when:
- The node represents multiple distinct concerns
- Implementation would require 4+ files
- The name is abstract (e.g., "Data Layer", "Core Logic")
- Sub-responsibilities can be cleanly separated

**Implement** when:
- The node maps to a single focused concern
- Implementation is 1-3 files
- The name is concrete (e.g., "JWT Validation", "SQLite Store")
- Further decomposition would be artificial

When unsure, prefer decomposition — it's easier to merge nodes later than to split them.

## File Attachment Rules

1. **Files attach to leaf nodes only** — during implementation tasks
2. **Global uniqueness** — each file appears on exactly one node
3. **Migration on propose** — proposing a child with `files` moves those files from the parent
4. **Barrel/re-export files** — may stay on intermediate nodes (e.g., `__init__.py`, `index.ts`)

## Auto-Deepening Chain

When a node becomes confirmed and has no children, the system automatically creates a "Propose children for" task targeting that node. This happens in two places:

1. **`approve_proposal()`** — user approves a grey node in the UI
2. **`complete_task()`** — task completion promotes proposed nodes to confirmed

Both paths include a dedup guard: if a deepening task already exists for that node (queued or active), no duplicate is created.
