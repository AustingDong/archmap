# ArchMap

Progressive architecture comprehension via a purpose tree.

Agents propose grey nodes; users review and approve. A stack-based task system drives depth-first deepening — files land at leaf nodes during implementation.

## What it does

- **Purpose Tree** — hierarchical map where depth = abstraction level
- **Agent Workflow** — orient → get task → decompose or implement → report
- **Stack Pacing** — LIFO task ordering ensures depth-first tree construction
- **MCP Server** — 3 tools (`orient`, `get_task`, `report`) for any agent framework

## Setup

```bash
# Python dependencies
conda create -n archmap python=3.12
conda activate archmap
pip install fastapi uvicorn mcp[cli]

# UI
cd ui && npm install
```

## MCP Integration

### Claude Code

```bash
claude mcp add archmap -- python /path/to/archmap/mcp_server.py
```

### Cursor / Windsurf / any MCP client

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

## MCP Tools

All tools accept `project_path` (absolute path to the target project).

| Tool | Description |
|------|-------------|
| `orient` | See the purpose tree + active task info |
| `get_task` | Get active task with scoped context (breadcrumb, siblings, children) |
| `report` | Report work done: propose grey nodes, propose removals, create tasks |

## Running

```bash
# API server (port 8765)
conda run -n archmap python api_server.py

# React UI (port 5174)
cd ui && npm run dev

# MCP server (stdio, configured in .mcp.json)
python mcp_server.py

# Tests
conda run -n archmap python -m pytest tests/ -v
```

## Storage

Data lives in `.archmap/` inside your project:

```
your-project/
└── .archmap/
    ├── meta.json    # Project name, version
    ├── tree.json    # Purpose tree (nodes, statuses, files)
    └── tasks.json   # Task stack (LIFO ordering)
```

JSON files — portable, git-diffable, human-readable.

## Agent Guidance

Skills in `.claude/skills/` provide structured workflow guidance:

| Skill | Purpose |
|-------|---------|
| `work-task` | Core orient → work → report loop |
| `bootstrap-arch` | Initial tree setup from a fresh project |

See `CLAUDE.md` for quick reference.
