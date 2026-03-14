# ArchMap

Architecture mapping + planning with MCP support.

Maps your codebase to an architecture diagram, ties tasks to components, and exposes everything via MCP so AI agents (Claude Code, Cursor, OpenClaw, etc.) can read and write it.

## What it does

- **Architecture Canvas** — define components (frontend, backend, db, etc.) and their dependencies
- **Code Mapping** — associate files/folders with components so agents understand context before editing
- **Planning** — tasks tied to specific components, readable by agents
- **MCP Server** — all of the above accessible to any agent framework via Model Context Protocol

## Setup

```bash
pip install mcp[cli]
```

## Quick Start

```bash
# Initialize in your project
python cli.py init --path /your/project

# Auto-detect components from folder structure
python cli.py scan --path /your/project

# View what was found
python cli.py list --path /your/project
python cli.py status --path /your/project
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

### Project
| Tool | Description |
|------|-------------|
| `init_project` | Initialize `.archmap/` in a project |
| `project_status` | Summary stats (component count, open tasks, etc.) |

### Architecture
| Tool | Description |
|------|-------------|
| `get_architecture` | Full component + dependency JSON |
| `list_components` | List components, filter by layer/confidence |
| `get_component` | Single component by ID |
| `add_component` | Add a new component |
| `update_component` | Update component fields |
| `delete_component` | Remove component + its dependencies |
| `add_dependency` | Add directed edge between components |
| `remove_dependency` | Remove edge by ID |
| `get_dependency_graph` | Graph as `{nodes, edges, adjacency}` |

### Mapping
| Tool | Description |
|------|-------------|
| `map_file` | Associate a file with a component |
| `unmap_file` | Remove a file's mapping |
| `get_file_component` | Which component owns this file? |
| `list_component_files` | All files in a component |
| `bulk_map` | Map many files at once (JSON array) |
| `list_all_mappings` | Full file→component index |

### Planning
| Tool | Description |
|------|-------------|
| `list_plan_items` | List tasks, filter by component/status/priority |
| `create_plan_item` | Create a task, tie to a component |
| `update_plan_item` | Update status, priority, etc. |
| `delete_plan_item` | Remove a task |

### Scanner
| Tool | Description |
|------|-------------|
| `scan_project` | Auto-detect components from folder structure |

## Storage

Data lives in `.archmap/` inside your project:

```
your-project/
└── .archmap/
    ├── meta.json          # Project name, version
    ├── architecture.json  # Components + dependencies
    ├── mappings.json      # File path → component index
    └── plan.json          # Tasks
```

JSON files — portable, git-diffable, human-readable.

## UI

```bash
cd ui
npm install
npm run dev  # http://localhost:5174
```

Dashboard, Architecture (component list + dependency view), Plan pages.

## Component Layers

`frontend` | `backend` | `database` | `infra` | `shared` | `testing` | `other`

## Component Confidence

- `auto` — detected by scanner, not yet confirmed
- `confirmed` — human or agent verified

Use `update_component` with `confidence=confirmed` to promote auto-detected components.
