# ArchMap

Progressive architecture comprehension via a purpose tree.

Agents propose grey nodes; users review and approve. A stack-based task system drives depth-first deepening — files land at leaf nodes during implementation. Pre-edit hooks automatically inject architectural context so agents write better code.

## How it works

1. **Purpose tree** — hierarchical map where depth = abstraction level. Upper nodes describe *why*, leaf nodes point to *where* in the code.
2. **Stack-based tasks** — LIFO ordering ensures depth-first construction. Each branch is fully resolved before the next begins.
3. **Agent workflow** — `orient` → `get_task` → work → `report`. Three MCP tools, that's it.
4. **Context injection** — pre-edit hooks automatically show the agent which branch a file belongs to, its purpose, and its siblings. No explicit tool calls needed during coding.
5. **Human review** — agents propose grey nodes, users approve/reject in the UI. The tree stays accurate because humans curate it.

## Quick start

```bash
# Install
pip install -e .

# Initialize ArchMap in your project
python -c "from archmap.core.store import init_project; init_project('/path/to/your/project')"

# Start the API server (port 8765)
python api_server.py

# Start the React UI (port 5174)
cd ui && npm install && npm run dev
```

## MCP integration

### Claude Code

```bash
claude mcp add archmap -- python /path/to/archmap/mcp_server.py
```

### Cursor / Windsurf / any MCP client

Add to your MCP config (`.mcp.json`, `mcp_settings.json`, etc.):

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

## MCP tools

All tools accept `project_path` — the absolute path to the project being mapped.

| Tool | Description |
|------|-------------|
| `orient` | See the purpose tree + active task. Call at session start. |
| `get_task` | Get active task with scoped context (breadcrumb, siblings, children, hints). |
| `report` | Report work done: propose grey nodes, propose removals, create follow-up tasks. |

## Pre-edit context injection

When configured with Claude Code hooks, ArchMap automatically injects a briefing before each file edit:

```
[ArchMap] tasks.py → Task Queue
Branch: ArchMap > Tree & Task Operations > Task Queue
Purpose: Create, list, activate (LIFO/stack), complete, reject tasks
Siblings: Tree CRUD (tree_crud.py), Proposals (proposals.py)
Active task: Add rate limiting to API endpoints
```

This happens silently — no MCP calls needed. See `.claude/settings.local.json` for hook configuration.

## Storage

Data lives in `.archmap/` inside the target project:

```
your-project/
└── .archmap/
    ├── meta.json    # Project name, version
    ├── tree.json    # Purpose tree (nodes, statuses, files, snapshots)
    └── tasks.json   # Task stack (LIFO ordering)
```

JSON files — portable, git-diffable, human-readable. Add `.archmap/` to your `.gitignore` — tree data is project-specific.

## Running the development server

```bash
# API server (port 8765)
python api_server.py

# React UI (port 5174)
cd ui && npm install && npm run dev

# Tests
python -m pytest tests/ -v
```

## Agent guidance (skills)

Skills in `.claude/skills/` provide structured workflow guidance for agents:

| Skill | Purpose |
|-------|---------|
| `work-task` | Core orient → work → report loop |
| `bootstrap-arch` | Initial tree setup from a fresh project |

Reference docs in `.claude/skills/work-task/references/`:
- `workflow.md` — Stack-based depth-first pacing explained
- `tree-model.md` — Node statuses, file ownership, depth guidelines
- `mcp-tools.md` — orient, get_task, report parameter reference

## Node statuses

| Status | Visual | Meaning |
|--------|--------|---------|
| `confirmed` | solid | User reviewed and approved |
| `proposed` | grey/ghost | Proposed by agent, awaiting review |
| `removing` | strikethrough | Agent proposes deletion, awaiting review |

## License

MIT
