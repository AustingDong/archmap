# ArchMap

**A purpose tree that makes AI agents understand your codebase before they edit it.**

ArchMap builds a hierarchical map of *why* your code exists, not just *where* it lives. Agents propose structure as grey nodes; humans review and approve. When agents later edit files, ArchMap automatically injects the relevant architectural context -- which branch this file belongs to, what its purpose is, and what else might be affected.

```
[ArchMap] price_fetcher.py -> Market Data
Branch: Stock Alerts > Market Data
Purpose: Connect to market data APIs, stream real-time prices, normalize into internal format
Siblings: Alert Engine, Notification Delivery, Persistence, API & Dashboard
Active task: Implement price fetcher module
```

This appears automatically before every file edit. The agent writes better code because it knows where it is.

---

## The Problem

AI coding agents are good at writing code but bad at understanding architecture. They grep for context, read too many files or too few, and make changes that work locally but break the broader design. They don't know that `tasks.py` uses LIFO ordering on purpose, or that changing `store.py` affects three other modules.

## How ArchMap Solves It

**Two phases:**

1. **Plan phase** (deliberate) -- Build the purpose tree through agent proposals + human review. The tree captures *why* each part of the system exists, not just what files are in which directory.

2. **Code phase** (automatic) -- The tree passively informs every coding session. Pre-edit hooks inject architectural context. Post-edit hooks track file changes. The agent never calls a tool -- it just knows more.

The tree is built once, updated occasionally, and consumed continuously.

---

## Installation

```bash
git clone <repo-url>
cd archmap

# Install as a Python package
pip install -e .

# Install UI dependencies
cd ui && npm install && cd ..
```

**Requirements:** Python 3.11+, Node.js 18+

---

## Quick Start

### 1. Initialize ArchMap in your project

```bash
python -c "from archmap.core.store import init_project; init_project('/path/to/your/project')"
```

This creates a `.archmap/` directory in your project. Add it to your `.gitignore`.

### 2. Connect the MCP server

**Claude Code:**
```bash
claude mcp add archmap -- python /path/to/archmap/mcp_server.py
```

**Cursor / Windsurf / any MCP client:**
```json
{
  "mcpServers": {
    "archmap": {
      "command": "python",
      "args": ["/path/to/archmap/mcp_server.py"]
    }
  }
}
```

### 3. Bootstrap the tree

Tell the agent:
> "Bootstrap the architecture for this project"

The agent reads your codebase, proposes top-level purpose branches as grey nodes, then stops. You review them in the UI.

### 4. Review in the UI

```bash
# Start the API server (in one terminal)
python api_server.py

# Start the React UI (in another terminal)
cd ui && npm run dev
```

Open `http://localhost:5174`, enter your project path, and you'll see the proposed tree. Approve or reject each grey node. Approved nodes auto-create deepening tasks -- the stack-based system handles the rest.

### 5. Code with context

Once your tree has files mapped to nodes, agents automatically see architectural context before every edit. No extra steps needed.

---

## Core Concepts

### Purpose Tree

A hierarchy where **depth = abstraction level**:

```
Stock Alerts                         (root: the whole system)
  |-- Market Data                    (L1: major subsystem)
  |   |-- Price Fetcher              (L2: specific concern)
  |   |-- WebSocket Stream           (L2: specific concern)
  |-- Alert Engine
  |-- Notification Delivery
  |-- Persistence
  |-- API & Dashboard
```

Each node has:
- **name** -- short purpose (2-4 words)
- **description** -- one sentence: what this node is responsible for
- **files** -- source files owned by this node (leaf nodes only)
- **status** -- `confirmed`, `proposed`, or `removing`
- **user_notes** -- your corrections or constraints for agents

### Node Statuses

| Status | Visual in UI | Meaning |
|--------|-------------|---------|
| `confirmed` | Solid | Human reviewed and approved |
| `proposed` | Grey/ghost | Agent proposed, awaiting review |
| `removing` | Strikethrough | Agent proposes deletion, awaiting review |

Agents can only propose changes. Humans decide what's real.

### Stack-Based Tasks (LIFO)

Tasks control what agents work on. They use **stack ordering** -- the most recently created task activates next. This drives **depth-first tree construction**:

```
1. "Propose children for API & Dashboard"   <- activated (most recent)
2. "Propose children for Persistence"       <- queued
3. "Propose children for Market Data"       <- queued (oldest)
```

Each branch is fully resolved before the next begins. Files land at leaf nodes during implementation, not at intermediate levels.

**Auto-deepening:** When a childless node is confirmed, the system auto-creates a "Propose children for X" task. This keeps the tree growing depth-first without manual task creation.

### File Ownership

- Each file belongs to **exactly one node** (global uniqueness)
- Files should be attached at **leaf nodes** during implementation
- When a child is proposed with files, those files **migrate** from the parent
- Barrel/re-export files (e.g., `__init__.py`) may stay on intermediate nodes

---

## MCP Tools

ArchMap exposes 3 tools via the Model Context Protocol. Any MCP-compatible agent can use them.

### `orient(project_path, depth=2)`

See the purpose tree and active task. **Call at session start.**

Returns an ASCII tree with node statuses, plus the active task description. If the project isn't initialized, auto-initializes it.

### `get_task(project_path)`

Get the active task with scoped context.

Returns:
- Task description and status
- Breadcrumb path in the tree (e.g., `Root > Backend > Auth`)
- Target node details (description, files, user notes)
- Sibling nodes at the same level
- Children already under the target
- Hints: childless confirmed nodes that could be deepened

### `report(project_path, ...)`

Report work done and propose tree changes. **Call after completing work.**

Parameters:
- `files_touched` -- files you created or modified (for tracking)
- `proposed_nodes` -- new grey nodes: `[{parent_id, name, description, files?}]`
- `proposed_removals` -- node IDs to propose for deletion
- `new_task` / `new_task_target` -- create a follow-up task

### Agent Workflow

Every session follows this loop:

```
orient()    -> see the tree, check for active task
get_task()  -> get scoped context for the assignment
... work ...
report()    -> propose tree changes, track files
```

---

## Context Injection (Hooks)

The most impactful feature: **agents get architectural context before every file edit, automatically.**

### How It Works

Claude Code hooks intercept Edit/Write tool calls:

1. **Pre-edit** (`context_inject.py`): Looks up which node owns the file. Prints a concise briefing -- branch path, purpose, siblings, user notes, active task.
2. **Post-edit** (`snapshot_update.py`): Updates the file's mtime snapshot so drift detection stays accurate.

### What Agents See

When editing `archmap/tasks.py`:

```
[ArchMap] tasks.py -> Task Queue
Branch: ArchMap > Tree & Task Operations > Task Queue
Purpose: Create, list, activate (LIFO/stack), complete, reject tasks
Siblings: Tree CRUD (tree_crud.py), Proposals (proposals.py), Context & Rendering (context.py)
Notes: Stack model is deliberate -- LIFO for depth-first pacing
Active task: Add rate limiting to API endpoints
```

For unmapped files: no output (silent).

### Setup

The hooks are configured in `.claude/settings.local.json`:

```json
{
  "hooks": {
    "PreToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "python .claude/hooks/context_inject.py"
      }]
    }],
    "PostToolUse": [{
      "matcher": "Edit|Write",
      "hooks": [{
        "type": "command",
        "command": "python .claude/hooks/snapshot_update.py"
      }]
    }]
  }
}
```

Hooks read the project path from Claude Code's stdin JSON (`cwd` field), so they work on any project that has `.archmap/` initialized.

---

## Drift Detection

ArchMap tracks file modification times. When a file changes after being mapped to a node, `orient()` shows a drift warning:

```
## Drift Detected

- **Task Queue**: changed: archmap/tasks.py
```

This tells agents (and humans) that the tree structure may be stale for that node. Post-edit hooks auto-update snapshots, so drift only appears for changes made outside of ArchMap-aware sessions.

---

## REST API

The FastAPI server (`api_server.py`, port 8765) exposes endpoints for the UI and external tools.

### Project
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/init` | Initialize ArchMap in a project |
| GET | `/api/status` | Project stats (node count, confirmed count) |

### Tree
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tree` | Full tree as JSON |
| GET | `/api/tree/render` | ASCII-rendered tree |
| POST | `/api/tree/root` | Create root node |
| POST | `/api/tree/reset` | Delete the tree |

### Nodes
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/node` | Add a child node |
| PATCH | `/api/node` | Update name, description, or notes |
| DELETE | `/api/node` | Remove a node |
| POST | `/api/node/move` | Move a node to a different parent |
| POST | `/api/node/approve` | Approve a proposed node |
| POST | `/api/node/reject-proposal` | Reject a proposed node |

### Files
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/node/files` | Attach files to a node |
| DELETE | `/api/node/file` | Detach a file from a node |
| GET | `/api/suggest-files` | List unmapped source files |
| GET | `/api/drift` | Detect files changed since last snapshot |

### Tasks
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/tasks` | List all tasks |
| GET | `/api/task/active` | Get the active task |
| POST | `/api/task` | Create a new task |
| POST | `/api/task/complete` | Complete a task (+ optional auto-advance) |
| POST | `/api/task/reject` | Reject a task (removes its proposals) |
| POST | `/api/task/propose` | Propose a new node (agent-facing) |
| POST | `/api/task/propose-removal` | Propose removing a node (agent-facing) |

---

## Review UI

A React app for browsing the tree and managing proposals.

```bash
python api_server.py          # API server on port 8765
cd ui && npm run dev           # UI on port 5174
```

Features:
- Collapsible tree view with status indicators
- Inline editing of node names, descriptions, and notes
- Approve/reject buttons on proposed and removing nodes
- Task panel with create, complete, and reject actions
- File attachment via point-and-click
- Search and filter across the tree
- Light/dark theme toggle
- Progress ring showing confirmed vs total nodes
- English and Chinese (i18n)

---

## Storage

Data lives in `.archmap/` inside the target project:

```
your-project/
  .archmap/
    meta.json     # Project name
    tree.json     # Purpose tree (nodes, files, snapshots)
    tasks.json    # Task stack
```

JSON files -- portable, git-diffable, human-readable. Add `.archmap/` to your `.gitignore`.

---

## Project Structure

```
archmap/
  core/
    models.py        TreeNode + Task dataclasses
    store.py         Atomic JSON persistence (tree.json, tasks.json)
  tree_crud.py       Node CRUD + file attachment
  tasks.py           Task stack (LIFO create, activate, complete, reject)
  proposals.py       Propose/approve/reject (agent gate)
  context.py         Context serialization, brief context, drift detection
  tree.py            Barrel re-export

api_server.py        FastAPI REST server (port 8765)
mcp_server.py        3-tool MCP server (stdio)

ui/src/
  App.tsx            Collapsible tree UI + task panel
  api/archMapApi.ts  API client
  types.ts           TypeScript types
  store.ts           Zustand store

.claude/
  skills/
    work-task/       Agent workflow guidance + reference docs
    bootstrap-arch/  Initial tree bootstrap guidance
  hooks/
    context_inject.py   Pre-edit: inject architectural briefing
    snapshot_update.py  Post-edit: update file mtime snapshot
```

---

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Lint
ruff check archmap/ tests/

# Type check UI
cd ui && npx tsc --noEmit
```

---

## License

MIT
