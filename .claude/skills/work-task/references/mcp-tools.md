# MCP Tool Reference

ArchMap exposes 3 MCP tools via `mcp_server.py` (stdio transport).

## orient

See the purpose tree and active task. Call at session start.

**Parameters:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `project_path` | string | yes | — | Path to the project root |
| `depth` | int | no | 2 | How many tree levels to render |

**Returns:** ASCII tree + active task summary. If no tree exists, initializes the project and prompts for root creation.

**When to call:** First action in every session. Also useful to re-check tree state after changes.

---

## get_task

Get the active task with scoped context.

**Parameters:**
| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `project_path` | string | yes | Path to the project root |

**Returns:**
- Task description and status
- Location in tree (breadcrumb path)
- Target node details (name, description, files, status)
- Sibling nodes at the same level
- Children already under the target node
- Hints: confirmed childless nodes that could be deepened
- Count of already-proposed additions/removals

**When to call:** After orient confirms an active task exists. The scoped context tells the agent exactly what to work on and what's already in scope.

---

## report

Report work done and propose tree changes.

**Parameters:**
| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `project_path` | string | yes | — | Path to the project root |
| `files_touched` | list[str] | no | null | Files created or modified (tracking only) |
| `proposed_nodes` | list[dict] | no | null | Nodes to propose as grey additions |
| `proposed_removals` | list[str] | no | null | Node IDs to propose for removal |
| `new_task` | string | no | null | Description for a new task |
| `new_task_target` | string | no | null | Target node ID for the new task |

**`proposed_nodes` entry format:**
```json
{
  "parent_id": "abc123",
  "name": "Node Name",
  "description": "What this node is responsible for",
  "files": ["path/to/file.py"]
}
```

**Key behaviors:**
- `files_touched` is for tracking only — does NOT auto-attach files to nodes
- `proposed_nodes[].files` DOES attach files to the proposed node (with global uniqueness migration)
- If no active task exists and no `new_task` is given, report returns an error
- Proposed nodes appear as grey/ghost in the UI until the user approves them

**When to call:** Last action before responding to the user. Always call after any code changes.

---

## Common Patterns

### Decomposition (planning task)

```python
report(
    project_path="<path>",
    proposed_nodes=[
        {"parent_id": "<target>", "name": "Auth Handler", "description": "JWT validation and session management"},
        {"parent_id": "<target>", "name": "Rate Limiter", "description": "Request throttling per client"},
        {"parent_id": "<target>", "name": "CORS Config", "description": "Cross-origin request policy"},
    ],
)
```

### Implementation (coding task)

```python
report(
    project_path="<path>",
    files_touched=["src/auth.py", "tests/test_auth.py"],
    proposed_nodes=[
        {
            "parent_id": "<target>",
            "name": "JWT Validation",
            "description": "Token verification and claims extraction",
            "files": ["src/auth.py", "tests/test_auth.py"],
        },
    ],
)
```

### Creating a follow-up task

```python
report(
    project_path="<path>",
    files_touched=["src/api.py"],
    new_task="Add rate limiting to API endpoints",
    new_task_target="<api_node_id>",
)
```
