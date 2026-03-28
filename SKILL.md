---
name: archmap
description: Architecture-aware code generation scaffold. Queries the ArchMap knowledge graph before generating code — components, symbols, dependencies, impact, tasks, and rules — so generated code is consistent with the existing architecture.
triggers:
  - archmap
  - architecture context
  - before generating code
  - before adding a component
  - before refactoring
  - check architecture
  - what component owns
  - who owns
  - blast radius
  - impact analysis
  - architectural rules
  - export architecture
  - architecture diff
  - snapshot architecture
---

# ArchMap — Architecture-Aware Code Generation

ArchMap maintains a live knowledge graph of the codebase. Use its MCP tools to
ground code generation in the real architecture — not just file text.

---

## Collaborating with other agents and humans

When multiple agents or humans share the same project:

```
# 1. Check who is working on what
list_active_work(project_path="<path>")

# 2. Claim your component before working on it
claim_component(
    project_path="<path>",
    component_id="<comp_id>",
    actor="claude-code",          # your stable identity
    task="adding OAuth endpoints"
)

# 3. ... do your work ...

# 4. Release when done
release_component(project_path="<path>", component_id="<comp_id>", actor="claude-code")
```

To stay in sync with changes made by others:
```
get_changes_since(project_path="<path>", since="<last_timestamp>")
```
Poll this every ~60 seconds during active collaborative sessions. Use the
`timestamp` field from any previous tool response as the `since` value.

---

## Starting a new project (intent-driven)

Describe what you want to build. The agent proposes the architecture, you confirm,
ArchMap persists it. No manual component definitions needed.

```
bootstrap_architecture(
    project_path="<path>",
    components_json='[
        {"name": "API Server",    "layer": "backend",  "description": "FastAPI REST endpoints"},
        {"name": "Database",      "layer": "database", "description": "PostgreSQL via SQLAlchemy"},
        {"name": "Auth Service",  "layer": "backend",  "description": "JWT authentication"},
        {"name": "Frontend",      "layer": "frontend", "description": "React SPA"}
    ]',
    dependencies_json='[
        {"from": "Frontend",    "to": "API Server",   "label": "HTTP calls"},
        {"from": "API Server",  "to": "Database",     "label": "reads/writes"},
        {"from": "API Server",  "to": "Auth Service", "label": "verifies tokens"}
    ]',
    rules_json='[
        {"type": "no_dep", "from_layer": "frontend", "to_layer": "database",
         "message": "Frontend must not access DB directly"}
    ]',
    tasks_json='[
        {"title": "Set up database schema",     "component": "Database",     "priority": "high"},
        {"title": "Implement JWT login",        "component": "Auth Service", "priority": "high"},
        {"title": "Build user CRUD endpoints",  "component": "API Server",   "priority": "medium"}
    ]'
)
```

The agent generates this proposal from your description. You review and adjust.
Architecture then evolves dynamically as code is written — components are not
locked; they grow with the project.

---

## Pre-generation (always run this first)

```
get_generation_context(
    project_path="<path>",
    component_id="<comp_id>",
    task="<what you are about to generate>"
)
```

This single call returns everything needed to generate architecture-consistent code:
- Component layer, description, confidence
- Files with their public symbols and signatures
- Full interface: what this component exports and what it imports
- Upstream impact: which components break if this one changes
- Open tasks tied to this component
- Active architectural rules that apply to this layer
- A `generation_brief` — a ready-to-inject system prompt excerpt

The `generation_brief` field is designed to be prepended directly to your code
generation prompt. It encodes architectural constraints in a compact, structured form.

---

## Finding what exists before generating

```
# Search by name
search_symbol(project_path="<path>", query="<function or class name>")

# Find by domain concept
find_related(project_path="<path>", query="<keyword>")

# Read exactly one function — no whole-file reads needed
read_function(project_path="<path>", file_path="<file>", symbol="<name>")
```

Never read a whole file to find a function. Symbol-first lookup uses far less context.

---

## Understanding the full architecture before a large change

```
describe_architecture(project_path="<path>")
```

Returns a Markdown document: all components by layer, files, symbols, dependency
flow, entry points, hotspots. Use before any multi-component change.

---

## Checking blast radius before touching a component

```
get_component_impact(project_path="<path>", component_id="<comp_id>")
```

- `upstream`: components that depend on this — they break if you change it
- `downstream`: what this component depends on
- `impact_score`: count of upstream components (higher = riskier)
- `cycles`: circular dependencies (design smell — fix before changing)

---

## After generating and writing files

```
post_edit_sync(
    project_path="<path>",
    file_paths=["<edited_file.py>"],
    reinfer_dependencies=True,    # if you added/removed imports
    validate=True                 # checks new deps against architectural rules
)
```

Response fields:
- `synced`: files whose symbols were updated ✓
- `unmapped`: new files not yet in the graph → call map_file() for each
- `errors`: extraction failures
- `deps_added`: new auto-inferred dependencies
- `rule_violations`: architectural rule violations introduced by new code

Fix any `rule_violations` before committing. They mean the generated code broke
an explicit architectural constraint.

---

## When you create a new file

```
# 1. Decide which component it belongs to
find_related(project_path="<path>", query="<what the file does>")

# 2. Map it to that component
map_file(project_path="<path>", file_path="<new_file>", component_id="<comp_id>")

# 3. Sync symbols and validate
post_edit_sync(project_path="<path>", file_paths=["<new_file>"], validate=True)
```

---

## Architecture compliance check before committing

```
validate_architecture(project_path="<path>")
check_integrity(project_path="<path>")
```

- `validate_architecture`: checks all dependencies against layer rules
- `check_integrity`: stale files, missing files, dangling deps, orphaned tasks

---

## Architecture export (for PR descriptions and README diagrams)

```
export_architecture(project_path="<path>", format="mermaid")
```

Paste the output into a ` ```mermaid ` code block in any Markdown file for a live
rendered diagram — works on GitHub, GitLab, Notion, and most wikis.

---

## Tracking what this PR changed architecturally

```
# Before your change (once per PR branch):
snapshot_architecture(project_path="<path>", label="before-<feature-name>")

# After your change:
diff_architecture(project_path="<path>", snapshot_label="before-<feature-name>")
```

Include the diff output in your PR description to make architectural intent explicit.

---

## Architecture Decision Records (ADRs)

ADRs capture *why* a design choice was made — context, trade-offs, alternatives rejected.
They prevent re-litigation of settled decisions and onboard new contributors instantly.

```
# Record a decision linked to a component
add_decision(
    project_path="<path>",
    component_id="<comp_id>",
    title="Use OS-level file locks for cross-process safety",
    context="Multiple MCP server instances can write concurrently ...",
    decision="Use msvcrt.locking (Windows) and fcntl.flock (Unix) ...",
    consequences="Lock files accumulate in .archmap/ — ignore in .gitignore",
    alternatives="Redis lock, database-backed lock, single-writer process",
    status="accepted"   # proposed | accepted | deprecated | superseded
)

# List decisions for a component (included in get_generation_context automatically)
list_decisions(project_path="<path>", component_id="<comp_id>", status="accepted")

# Supersede an outdated decision
update_decision(
    project_path="<path>",
    decision_id="adr_abc123",
    status="superseded",
    superseded_by="adr_xyz456"
)
```

ADRs are automatically injected into `get_generation_context` briefs — agents see
the *why* behind each component before generating code.

Prefer `status='deprecated'` or `status='superseded'` over deleting — decision
history is the institutional memory that prevents repeating past mistakes.

---

## Component ownership & operational metadata

```
# Set during add_component or update_component:
update_component(
    project_path="<path>",
    component_id="<comp_id>",
    owner="team:platform",        # who is responsible long-term
    tier="p0",                    # p0=pages on-call | p1 | p2 | p3
    onboarding_notes="Clone, run `make dev`, see README#auth for JWT setup.",
    runbook_url="https://wiki.internal/runbooks/auth-service",
    slack_channel="#platform-alerts"
)
```

- `owner` — team or person (e.g. `"team:security"`, `"dev:alice"`). Used for
  impact routing: "this change affects a P0 component owned by team:security".
- `tier` — operational criticality. P0 = paged on-call. P3 = best-effort.
- `onboarding_notes` — plain text injected into generation briefs for new agents/humans.
- `runbook_url` — link to the ops runbook or monitoring dashboard.
- `slack_channel` — alert destination.

All fields are optional and backwards-compatible with existing projects.

---

## Component layers reference

| Layer | What belongs here |
|-------|------------------|
| `frontend` | UI, React pages, stores, assets |
| `backend` | API servers, route handlers, business logic |
| `database` | Models, migrations, DB clients, ORMs |
| `infra` | Docker, CI/CD, Terraform, deployment config |
| `shared` | Utilities, types, helpers used across layers |
| `testing` | Test files, fixtures, test helpers |
| `other` | Anything that doesn't fit above |

---

## Code generation quality checklist

Before finalizing generated code, verify:

- [ ] `rule_violations` in `post_edit_sync` response is empty
- [ ] New imports only cross layer boundaries that the architecture allows
- [ ] New files are mapped to the correct component
- [ ] If a new public function was added, it appears in `get_component_interface` exports
- [ ] If component dependencies changed, `reinfer_dependencies=True` was passed
- [ ] `check_integrity` shows no new issues

---

## Why this matters (research basis)

Graph-grounded code generation outperforms flat RAG because it preserves relational
structure: which component owns which symbol, which components would break, which
rules apply. The *Knowledge Graph Based Repository-Level Code Generation* paper
(ICSE 2025) shows graph-based retrieval substantially outperforms semantic search
alone on benchmark recall. The *Codified Context* paper (arXiv:2602.20478) found
that MCP-served structured memory scales to 100K+ LOC where flat CLAUDE.md files
do not.

ArchMap is the human-curated layer that captures design intent — what the
architecture is supposed to be, not just what the code happens to do today.
