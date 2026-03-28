# ArchMap — Agent Workflow Guide

ArchMap maintains a live knowledge graph of this codebase: components, dependencies,
file-to-component mappings, symbols, tasks, and architectural rules. **Use the MCP
tools below instead of reading source files directly wherever possible.** The graph
gives faster, structured answers than grepping.

Project path for all tool calls: `C:/Users/a7don/my_projects/archmap`

---

## Multi-agent collaboration (when sharing the project)

```
# Check who is working on what — always do this first
list_active_work(project_path="C:/Users/a7don/my_projects/archmap")

# Claim before working
claim_component(project_path="...", component_id="<comp_id>",
                actor="claude-code", task="<what you are doing>")

# Poll for changes from other agents/humans (~every 60s)
get_changes_since(project_path="...", since="<last_response_timestamp>")

# Release when done
release_component(project_path="...", component_id="<comp_id>", actor="claude-code")
```

---

## Before generating or editing code (primary entry point)

```
get_generation_context(
    project_path="C:/Users/a7don/my_projects/archmap",
    component_id="<comp_id>",
    task="<what you are about to generate>"
)
```
One call returns: files + symbols, public interface, blast radius, open tasks,
applicable architectural rules, and a `generation_brief` field ready to inject
directly into a code generation prompt. Use this before touching any file.

For broad orientation first:
```
describe_architecture(project_path="C:/Users/a7don/my_projects/archmap")
find_related(project_path="...", query="<keyword>")
```

---

## Before reading a file — locate the symbol first

```
search_symbol(project_path="...", query="<function or class name>")
```
Returns file path, component, signature, and doc. Jump directly to the right file.

Once you know the file, read only the function you need:
```
read_function(project_path="...", file_path="archmap/store.py", symbol="mutate_arch")
```
Only fall back to `Read` / `Grep` if the symbol isn't in the index yet.

---

## Before modifying a heavily-used component

```
get_component_impact(project_path="...", component_id="<comp_id>")
```
Shows upstream (breaks if you change this) and downstream (what this depends on).
`impact_score` = number of upstream components — higher means riskier change.

---

## Code quality — check before and after every edit

```
check_code_quality(project_path="...", component_id="<comp_id>")
# include_types=True to also run mypy type checking
```

Returns: `score` (0–100), `lint_issues` (ruff), `format_issues`, `type_issues`,
`fix_priority` (files ordered by severity), `hotspots` (complex + dirty files).

**Agent workflow for quality:**
1. `check_code_quality` before starting — understand the baseline
2. Fix errors in `fix_priority` order before adding new code
3. `post_edit_sync` after each fix to keep the graph current
4. `check_code_quality` again at the end — score must not decrease

**For TypeScript files**, run `npm run lint` in `ui/` (uses ESLint):
```bash
cd C:/Users/a7don/my_projects/archmap/ui && npm run lint
```

**Augmenting code quality** — agents are authorized to proactively fix:
- Ruff lint errors (E/W codes) — always fix
- Unused imports, undefined names — always fix
- Formatting (`ruff format`) — fix if touching the file anyway
- Type errors (mypy) — fix if the fix is local and non-breaking
- Do NOT change public APIs or restructure modules without an ADR

---

## Checking architectural health before a large change

```
check_integrity(project_path="...")
validate_architecture(project_path="...")
```
- `check_integrity` — stale files, missing files, dangling deps, unmapped source files
- `validate_architecture` — checks all deps against layer rules (no frontend→db, etc.)

Fix violations before adding new code on top of broken foundations.

---

## After editing files — REQUIRED

Call `post_edit_sync` immediately after any file edit or creation:
```
post_edit_sync(
    project_path="...",
    file_paths=["archmap/store.py", "archmap/models.py"],
    reinfer_dependencies=True,   # set True if you added/removed imports
    validate=True                # checks new deps against architectural rules
)
```

Check the response:
- `synced`           → symbols updated ✓
- `unmapped`         → new file not in graph yet; call `map_file()` then sync again
- `errors`           → extraction failed; inspect the file
- `rule_violations`  → architectural rules broken by new code → fix before committing
- `architecture_clean: true` → generation passed all architectural constraints ✓

---

## When you create a new file

```
# 1. Decide which component it belongs to
find_related(project_path="...", query="<what the file does>")

# 2. Map it
map_file(project_path="...", file_path="archmap/newmodule.py", component_id="comp_...")

# 3. Sync its symbols
post_edit_sync(project_path="...", file_paths=["archmap/newmodule.py"])
```

---

## When you add/remove imports between components

```
post_edit_sync(
    project_path="...",
    file_paths=["archmap/changed_file.py"],
    reinfer_dependencies=True   # re-scans all imports → updates dependency graph
)
```

---

## Exporting the architecture (for docs, CI, PR review)

```
export_architecture(project_path="...", format="mermaid")
# → Mermaid flowchart — paste into GitHub README or PR description

export_architecture(project_path="...", format="dot")
# → Graphviz DOT — render with `dot -Tpng` or paste into diagrams.net
```

---

## Tracking architectural drift (CI/CD, PR review)

```
# Save a baseline before your change
snapshot_architecture(project_path="...", label="before-my-feature")

# ... make your changes ...

# Compare against it
diff_architecture(project_path="...", snapshot_label="before-my-feature")
```
Returns added/removed/changed components and dependencies. Use in PR descriptions
to make architectural intent explicit.

---

## Architecture Decision Records (ADRs)

Record *why* decisions were made — context, trade-offs, alternatives rejected.
ADRs are automatically injected into `get_generation_context` briefs.

```
add_decision(project_path="...", component_id="<comp_id>",
             title="Use JWT for auth sessions",
             context="Need stateless auth across multiple API replicas",
             decision="Sign JWTs with RS256; validate on every request",
             consequences="No server-side session storage; token revocation is hard",
             alternatives="Redis sessions, database-backed sessions",
             status="accepted")   # proposed | accepted | deprecated | superseded

list_decisions(project_path="...", component_id="<comp_id>", status="accepted")

# Supersede an outdated decision (prefer this over delete)
update_decision(project_path="...", decision_id="adr_abc123",
                status="superseded", superseded_by="adr_xyz456")
```

---

## Component ownership & operational metadata

```
update_component(project_path="...", component_id="<comp_id>",
    owner="team:platform",        # who is responsible long-term
    tier="p0",                    # p0=pages on-call | p1 | p2 | p3
    onboarding_notes="Clone repo, run make dev. See README#auth for JWT setup.",
    runbook_url="https://wiki.internal/runbooks/auth",
    slack_channel="#platform-alerts")
```

These fields are surfaced in `get_generation_context` briefs so agents know
who owns the component and how critical it is before making changes.

---

## Component layers

| Layer | What belongs here |
|-------|------------------|
| `frontend` | UI, React pages, stores, CSS |
| `backend` | API servers, route handlers, business logic |
| `database` | Models, migrations, DB clients |
| `infra` | Docker, CI, Terraform, deployment |
| `shared` | Utilities, types, helpers used across layers |
| `testing` | Test files, fixtures, test helpers |
| `other` | Anything that doesn't fit above |

---

## Key component IDs (ArchMap's own architecture)

Run `list_components` to get current IDs — they change when components are recreated.
Use `find_related(query="store")` to locate the right ID by name.

---

## Automatic vs manual sync

| What | Automatic | Manual |
|------|-----------|--------|
| Symbol sync for existing files | File watcher (when UI open) | `post_edit_sync` |
| Symbol sync via MCP | Never | `post_edit_sync` — always call |
| New file mapping | Never | `map_file` + `post_edit_sync` |
| Dependency re-inference | Never | `post_edit_sync(reinfer_dependencies=True)` |
| Architecture description | Always current | — |

**Always call `post_edit_sync` after editing via MCP.** The file watcher only updates
the UI graph, not the MCP symbol index.

---

## Running ArchMap itself

```bash
# Terminal 1 — API server (port 8765)
conda run -n archmap python api_server.py

# Terminal 2 — React UI (port 5174)
cd ui && npm run dev

# MCP server (add to claude config, runs via stdio)
python mcp_server.py
```

Tests:
```bash
conda run -n archmap python -m pytest tests/ -v
```
