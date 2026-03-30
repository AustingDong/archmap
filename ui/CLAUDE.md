# ArchMap — Agent Workflow

ArchMap maintains a knowledge graph of this codebase. Use the MCP tools below
instead of reading source files directly wherever possible.

## Before starting any coding task

```
describe_architecture(project_path="C:/Users/a7don/my_projects/archmap")
```
→ Shows all components, files, symbols, and dependencies. Read this first.

Then narrow down:
```
find_related(project_path="...", query="<what you're working on>")
get_coding_context(project_path="...", component_id="<comp_id>")
```

## Before reading a file

Use the graph to locate the exact function first:
```
search_symbol(project_path="...", query="<function name>")
read_function(project_path="...", file_path="...", symbol="<name>")
```
Only fall back to Read/Grep if the symbol isn't in the index yet.

## After editing files — REQUIRED

Call `post_edit_sync` immediately after any file edit or creation:
```
post_edit_sync(
    project_path="...",
    file_paths=["path/to/edited_file.py", "path/to/other.py"],
    reinfer_dependencies=False   # set True if you added/removed imports
)
```

Check the response:
- `synced` → symbols updated ✓
- `unmapped` → new files not yet in the graph; call `map_file()` for each
- `errors` → something went wrong

## When you create a new file

```
# 1. Map it to the right component
map_file(project_path="...", file_path="new_file.py", component_id="comp_...")

# 2. Sync its symbols
post_edit_sync(project_path="...", file_paths=["new_file.py"])
```

## When you add imports between components

```
post_edit_sync(
    project_path="...",
    file_paths=["changed_file.py"],
    reinfer_dependencies=True   # re-scans all imports → updates dependency graph
)
```

## Before modifying a heavily-used component

```
get_component_impact(project_path="...", component_id="<comp_id>")
```
→ Shows what breaks upstream if you change this component.

## Exporting the architecture

```
export_architecture(project_path="...", format="mermaid")  # for READMEs / PR descriptions
export_architecture(project_path="...", format="dot")      # for Graphviz rendering
```

## Architecture drift tracking

```
snapshot_architecture(project_path="...", label="before-my-change")
# ... make changes ...
diff_architecture(project_path="...", snapshot_label="before-my-change")
```

## Sync is always explicit — nothing is automatic

| What | How |
|---|---|
| Symbol sync | `post_edit_sync(file_paths=[...])` — required after every edit |
| New file mapping | `post_edit_sync` returns `unmapped` list → call `map_file` for each |
| Dependency re-inference | `post_edit_sync(reinfer_dependencies=True)` — when imports changed |
| Architecture description | Always current |

Always call `post_edit_sync` after editing. There is no background sync.
