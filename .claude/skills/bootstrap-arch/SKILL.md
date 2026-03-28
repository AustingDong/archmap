---
name: bootstrap-arch
description: Agent-driven architecture bootstrap. Reads the project from scratch and builds a structured multi-level knowledge graph — domains, services, components, file mappings, dependencies, and contracts — using ArchMap MCP tools. Run this on a fresh project or after reset_graph().
triggers:
  - bootstrap architecture
  - rebuild graph
  - regenerate architecture
  - map the architecture
  - analyse project structure
  - bootstrap-arch
---

# ArchMap — Agent-Driven Architecture Bootstrap

You are acting as an architecture analyst. Your job is to read this project from
scratch and populate the ArchMap knowledge graph with a structured, multi-level
model of its architecture.

Work through the phases below **in order**. After each phase, write results to the
graph using ArchMap MCP tools before moving to the next phase. Do not batch all
phases into one step — each phase builds on the previous one.

Project path: use the `project_path` from CLAUDE.md or ask the user if not set.

---

## Phase 0 — Reset (if rebuilding)

If there is an existing graph and the user wants a clean rebuild:

```
reset_graph(project_path="<path>")
```

This clears components, dependencies, contracts, and file mappings.
Plan items, ADRs, and project metadata are preserved.

---

## Phase 1 — Orient: read the project

Read these files to understand the project before creating anything:

1. **Entry points**: `README.md`, `README.rst`, any top-level `*.md`
2. **Package manifests**: `package.json`, `pyproject.toml`, `requirements.txt`,
   `go.mod`, `Cargo.toml`, `pom.xml`, `build.gradle` — whichever exist
3. **Runtime config**: `Dockerfile`, `docker-compose.yml`, `.env.example`,
   `Makefile`, `justfile`
4. **Directory structure**: list the top 2 levels of directories (use Glob)
5. **CI config**: `.github/workflows/*.yml` or `.gitlab-ci.yml` if present

From this, determine:
- What does this system do? (one sentence)
- What language(s) / frameworks are used?
- How many distinct runtime processes are there? (one process = one L3 node)
- Is there a clear layered structure (frontend/backend/database)?
- Are there multiple bounded contexts / teams?

Do not create any graph nodes yet. Just build your understanding.

---

## Phase 2 — Create L1 System node

Create exactly one L1 node representing the whole system:

```
add_component(
    project_path="<path>",
    name="<ProductName>",           # from README or package.json "name"
    description="<one sentence>",   # what the system does
    layer="other",                  # L1 is always "other"
    level=1,
    confidence="confirmed"
)
```

Save the returned `id` as `SYSTEM_ID`.

---

## Phase 3 — Identify and create L2 Domain nodes

Domains are **bounded contexts** — cohesive areas of the system with clear
ownership boundaries. Think: what would be separate teams in a large org?
Aim for 2–5 domains. Examples:

- A web app might have: `User Interface`, `API`, `Data`
- A microservices system might have: `Auth`, `Payments`, `Notifications`, `Core`
- A CLI tool might have just: `Core`, `I/O`

For each domain:

```
add_component(
    project_path="<path>",
    name="<Domain Name>",
    description="<what this domain owns and is responsible for>",
    layer="<frontend|backend|database|infra|shared>",
    level=2,
    parent_id="<SYSTEM_ID>",
    data_owned=["<DataType1>", "<DataType2>"],   # what data this domain owns
    stability="stable",
    confidence="confirmed"
)
```

Save each domain `id` for use in Phase 4.

---

## Phase 4 — Identify and create L3 Service nodes

Services are **deployable units** — distinct runtime processes, containers,
or lambdas. Look for:
- Separate `Dockerfile` or `docker-compose` services
- Separate entry-point scripts (`main.py`, `server.js`, `cmd/`, `bin/`)
- Separate `package.json` workspaces or monorepo packages

For each service, assign it to a domain (its `parent_id`):

```
add_component(
    project_path="<path>",
    name="<Service Name>",          # e.g. "REST API", "Worker", "React Frontend"
    description="<what it does>",
    layer="<backend|frontend|infra>",
    level=3,
    parent_id="<DOMAIN_ID>",
    protocol="<http|grpc|stdio|websocket|>",   # how it communicates
    port=<8080>,                    # null if not a server
    deploy_unit=True,
    stability="stable",
    confidence="confirmed"
)
```

---

## Phase 5 — Identify and create L4 Component nodes

Components are **logical modules within a service** — not files, but groups of
related files that implement a single concern. Think: repositories, handlers,
services, adapters, stores, routers.

Read the directory structure of each service. Group related files by concern:

```
add_component(
    project_path="<path>",
    name="<Component Name>",        # e.g. "Auth Handler", "User Repository"
    description="<responsibility>",
    layer="<backend|frontend|shared|database|testing>",
    level=4,
    parent_id="<SERVICE_ID>",
    public_api=["<fn1>", "<fn2>"],  # key exported symbols if known
    stability="<stable|beta|internal>",
    confidence="confirmed"
)
```

Aim for 2–8 components per service. Don't create a component per file —
group by concept.

---

## Phase 6 — Map files to components

**Only map source code files.** The graph should contain code, not documentation or config.

Files to skip — do NOT call `map_file` on these:
- Documentation: `README.md`, `CHANGELOG.md`, `LICENSE`, `*.txt`, `*.rst`
- Config/lock: `package.json`, `requirements.txt`, `pyproject.toml`, `*.lock`,
  `tsconfig.json`, `vite.config.*`, `.eslintrc`, `.prettierrc`, `.gitignore`,
  `Makefile`, `Dockerfile`, `docker-compose.*`, `.env*`, `CLAUDE.md`
- Compiled/generated: `*.pyc`, `*.d.ts`, `*.min.js`, `dist/`, `build/`
- Binary assets: images, fonts, audio, video

Files to map — source code only:
- `*.py`, `*.ts`, `*.tsx`, `*.js`, `*.jsx` — application logic
- `*.go`, `*.rs`, `*.java`, `*.cs`, `*.rb`, `*.swift` — other languages
- `*.css`, `*.scss`, `*.html`, `*.vue`, `*.svelte` — web templates
- `*.sql`, `*.graphql`, `*.proto`, `*.tf` — schema / IaC

For each L4 component, map its source files:

```
map_file(
    project_path="<path>",
    file_path="<relative/path/to/file.py>",   # source code only
    component_id="<COMPONENT_ID>"
)
```

Guidelines:
- Test files → map to the component they test (or a dedicated Testing component)
- Shared utilities → map to a shared L4 component
- Skip: `node_modules/`, `__pycache__/`, `dist/`, `build/`, `.archmap/`

After mapping, run cleanup to remove any non-source files that slipped through:

```
cleanup_non_source_mappings(project_path="<path>")
```

Then sync symbols for key files:

```
post_edit_sync(
    project_path="<path>",
    file_paths=["<key_file_1>", "<key_file_2>"],
    reinfer_dependencies=True
)
```

---

## Phase 7 — Add dependencies

Add the key cross-component dependencies. Focus on boundaries — not every
internal call, but the important structural connections:

```
add_dependency(
    project_path="<path>",
    from_component="<FROM_ID>",
    to_component="<TO_ID>",
    label="<short description>",
    kind="<runtime|build|test>",    # usually "runtime"
    edge_type="<command|query|event|import|data_read|data_write|invoke>",
    crosses_boundary=<True|False>   # True if crossing L2 domain boundary
)
```

Edge type guide:
- `command` — caller triggers a state change (write, create, delete)
- `query` — caller requests data (read only)
- `event` — async notification (fire and forget)
- `import` — static code import (same process)
- `data_read` / `data_write` — storage access
- `invoke` — generic call (use when unsure)

---

## Phase 8 — Declare contracts for L2 and L3 nodes

For each L2 domain and L3 service, declare its public interface:

```
declare_contract(
    project_path="<path>",
    node_id="<ID>",
    node_level=<2 or 3>,
    commands=[
        {"name": "<op>", "description": "<what it does>",
         "input_type": "<Type>", "output_type": "<Type>", "stability": "stable"}
    ],
    queries=[
        {"name": "<op>", "description": "<what it returns>",
         "input_type": "<Type>", "output_type": "<Type>", "stability": "stable"}
    ],
    events_emitted=[
        {"name": "<Event>", "description": "<when emitted>",
         "payload_type": "<Type>", "stability": "stable"}
    ],
    data_owned=[
        {"type_name": "<Type>", "description": "<what it represents>",
         "schema": "", "stability": "stable", "authoritative": True}
    ],
    sla="<e.g. p99 < 200ms | best-effort>",
    declared_by="claude-code"
)
```

Only declare contracts for nodes where you can infer the interface from the code.
Leave undeclared if uncertain — it's better to omit than to declare incorrectly.

---

## Phase 9 — Verify

After all phases:

```
describe_architecture(project_path="<path>", level=2)   # domains overview
describe_architecture(project_path="<path>", level=3)   # services overview
```

Check:
- Every L3 service has a parent L2 domain
- Every L4 component has a parent L3 service
- Key files are mapped to a component
- Major cross-service dependencies are captured

Report a summary to the user:
- How many nodes at each level
- How many files mapped
- How many dependencies captured
- Any areas where the structure was unclear (flag for human review)

---

## Principles to follow

**Top-down, not bottom-up.** Start from the system boundary and work inward.
Don't create components per file and then try to group them.

**Bounded contexts over layers.** Group by *what the code owns*, not just its
technical layer. An "Auth Service" is better than a "Backend Module".

**Fewer, meaningful nodes.** 10 well-named components > 50 auto-detected folders.
Merge small related files into one component.

**Honest confidence.** If you are unsure which domain a component belongs to,
use `confidence="auto"`. The user can confirm or correct it in the UI.

**Preserve ADRs.** If `list_decisions` returns existing decisions, do not
overwrite them. The architectural history is valuable context.
