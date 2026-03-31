# ArchMap — Purpose Tree

ArchMap is a progressive comprehension tool: a purpose tree where depth = abstraction.
Agents propose grey nodes; users review and approve. Tasks use a stack (LIFO) for depth-first pacing.

**Project path**: Use the absolute path to this repository for all tool calls.

---

## REQUIRED: Agent workflow

Every session MUST follow the orient → get_task → work → report loop.
See `.claude/skills/work-task/SKILL.md` for the full workflow, or use `/work-task`.

**Quick reference:**

1. `orient(project_path="<this repo>")` — first action, always
2. `get_task(project_path="<this repo>")` — get your assignment
3. Do the work: decompose (propose children) or implement (write code + attach files)
4. `report(project_path="<this repo>", ...)` — last action, always

If the user asks for something else, do that instead. But still orient first, report last.

---

## MCP Tools (3 tools)

| Tool | What it does |
|------|-------------|
| `orient` | See the purpose tree + active task info |
| `get_task` | Get active task with scoped context (breadcrumb, siblings, children) |
| `report` | Report work done: propose grey nodes, propose removals, create tasks |

Full tool reference: `.claude/skills/work-task/references/mcp-tools.md`

---

## Skills

| Skill | When to use |
|-------|------------|
| `/work-task` | Core workflow: orient, get task, decompose or implement, report |
| `/bootstrap-arch` | Fresh project: read codebase and propose initial tree structure |

Detailed references in `.claude/skills/work-task/references/`:
- `workflow.md` — Stack-based depth-first pacing explained
- `tree-model.md` — Node statuses, file ownership, depth guidelines
- `mcp-tools.md` — orient, get_task, report parameter reference

---

## Architecture

```
archmap/
  core/
    models.py      TreeNode + Task dataclasses
    store.py       Atomic JSON persistence (tree.json, tasks.json)
  tree_crud.py     Node CRUD + file attachment
  tasks.py         Task stack (LIFO create, activate, complete, reject)
  proposals.py     Propose/approve/reject (agent gate)
  context.py       Agent context serialization + ASCII rendering + hooks
  tree.py          Barrel re-export

api_server.py      FastAPI REST server (port 8765)
mcp_server.py      3-tool MCP server for agent interaction

ui/src/
  App.tsx          Collapsible tree UI + task panel
  api/archMapApi.ts  API client
  types.ts         TypeScript types
  store.ts         Zustand store
```

---

## Node statuses

| Status | Visual | Meaning |
|--------|--------|---------|
| `confirmed` | solid | User reviewed and approved |
| `proposed` | grey/ghost | Proposed by agent, awaiting review |
| `removing` | strikethrough | Agent proposes deletion, awaiting review |

---

## Running

```bash
# Install
pip install -e .

# API server (port 8765)
python api_server.py

# React UI (port 5174)
cd ui && npm install && npm run dev

# MCP server (stdio, configured in .mcp.json)
python mcp_server.py

# Tests
python -m pytest tests/ -v
```
