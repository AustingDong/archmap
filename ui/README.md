# ArchMap

**A software architecture knowledge graph for AI agents and humans.**

ArchMap lets you map your codebase into a queryable graph of components, files, and symbols. AI agents (Claude Code, Cursor, Copilot) can navigate this graph instead of reading source files — reducing context usage dramatically and enabling accurate, architecture-aware coding.

---

## Why ArchMap?

AI agents navigate codebases by reading files. On a 500-file project this burns most of the context window before any code is written. ArchMap solves this:

| Without ArchMap | With ArchMap |
|---|---|
| Agent reads 30 files to understand auth flow | `describe_architecture()` → full picture in 1 call |
| Agent greps across the whole repo for a function | `find_related("authenticate")` → exact file + component |
| Agent edits blindly, breaks downstream component | `get_component_impact()` → see blast radius first |
| Agent re-discovers same context every session | `get_coding_context(id)` → pre-packaged snapshot |

The core agent loop:
```
1. describe_architecture()       → understand the full landscape
2. find_related("token validate") → locate which file owns the symbol  
3. read_function("auth.py", "validate_token") → read only that function
```

---

## Features

- **Interactive architecture graph** — component nodes expand into file and symbol nodes
- **MCP server** — 50+ tools for Claude Code, Cursor, and any MCP client
- **Auto-detection** — scan project structure to bootstrap components automatically
- **Dependency inference** — parse Python/TS/JS imports to auto-discover cross-component deps
- **Symbol extraction** — extract functions/classes with signatures and docstrings
- **Intelligence layer** — search, trace paths, describe architecture without reading files
- **Architectural rules** — enforce constraints (e.g. "frontend cannot depend on database")
- **Impact analysis** — BFS upstream/downstream/cycle detection before making changes
- **Code metrics** — line count, complexity, git churn, hotspot detection per component
- **Audit log** — append-only change history for multi-agent accountability
- **Plan board** — Kanban task board tied to components, with live SSE updates
- **File watcher** — auto-syncs symbol index when mapped files change on disk

---

## Installation

**Requirements:** Python 3.11+, Node.js 18+

```bash
git clone https://github.com/yourname/archmap
cd archmap

# Python backend
pip install -r requirements.txt
# Optional: auto-sync symbols on file save
pip install watchdog

# React frontend
cd ui && npm install
```

---

## Quick Start

```bash
# 1. Initialize ArchMap in your project
python cli.py init /path/to/your/project

# 2. Auto-detect components from directory structure
python cli.py scan /path/to/your/project

# 3. Start the backend
python api_server.py

# 4. Start the frontend (separate terminal)
cd ui && npm run dev
# Open http://localhost:5173
```

---

## MCP Setup (Claude Code)

Add ArchMap to your Claude Code MCP config:

```bash
claude mcp add archmap -- python /path/to/archmap/mcp_server.py
```

Or edit your MCP config file (Claude Desktop):

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

Then agents can immediately navigate:

```
describe_architecture(project_path="/path/to/project")
find_related(project_path="...", query="authentication")
read_function(project_path="...", file_path="auth/handler.py", symbol="authenticate")
get_component_impact(project_path="...", component_id="comp_abc123")
```

---

## MCP Tools Reference

### Navigation
| Tool | Description |
|---|---|
| `describe_architecture` | Full markdown overview — components, files, symbols, deps, entry points |
| `find_related(query)` | Search across component names, file paths, and symbol names |
| `get_symbol_index` | Every function/class mapped to its file and component |
| `get_coding_context(component_id)` | Pre-work snapshot: files, deps, open tasks |
| `trace_path(from_id, to_id)` | BFS shortest dependency path between two components |

### Reading Code
| Tool | Description |
|---|---|
| `read_function(file_path, symbol)` | Source of one named function or class |
| `read_file(file_path)` | Full file content with optional line range |
| `search_symbol(query)` | Find functions/classes by name with signature and docstring |

### Architecture Management
| Tool | Description |
|---|---|
| `list_components` | All components, filterable by layer/confidence |
| `add_component` | Create a new component |
| `update_component` | Edit name, description, layer, tags |
| `delete_component` | Remove component and all its dependencies |
| `add_dependency` | Create a directed dependency edge |
| `remove_dependency` | Remove a dependency |

### File & Symbol Management
| Tool | Description |
|---|---|
| `map_file(file_path, component_id)` | Associate a file with a component |
| `sync_file_symbols(file_path)` | Extract and store all top-level symbols |
| `annotate_file(file_path, description)` | Manually enrich file metadata |
| `bulk_map(mappings)` | Map many files at once |

### Analysis & Quality
| Tool | Description |
|---|---|
| `get_component_metrics(component_id)` | Lines, complexity, git churn, hotspots |
| `get_component_impact(component_id)` | Upstream/downstream BFS + cycle detection |
| `list_cycles` | All dependency cycles in the architecture |
| `validate_architecture` | Check deps against configured rules |
| `add_architecture_rule` | Add constraint rule |

### Planning & Audit
| Tool | Description |
|---|---|
| `list_plan_items` | Tasks, filterable by component/status/priority |
| `create_plan_item` | Create a task tied to a component |
| `update_plan_item` | Change status, priority, description |
| `get_audit_log` | Recent architecture change history |

---

## Data Storage

Stored in `.archmap/` inside your project — plain JSON, git-friendly, no database:

```
.archmap/
  architecture.json  # components + dependencies
  mappings.json      # file → component index with symbol metadata
  plan.json          # tasks
  rules.json         # architectural constraint rules
  audit.json         # append-only change history
```

---

## Running Tests

```bash
pip install pytest
pytest tests/test_smoke.py -v
```

---

## License

MIT
