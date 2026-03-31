---
name: bootstrap-arch
description: This skill should be used when the user asks to "bootstrap the architecture", "map this project", "build the purpose tree", "start from scratch", or when working with a fresh ArchMap project that has no tree yet. Reads the project and proposes the initial purpose tree structure using ArchMap MCP tools.
triggers:
  - bootstrap architecture
  - rebuild tree
  - map the architecture
  - build purpose tree
  - start from scratch
  - bootstrap-arch
---

# ArchMap — Bootstrap Purpose Tree

Read a project from scratch and propose the initial purpose tree structure.
This is a planning-only skill — propose grey nodes for user review, do not write code.

Project path: read from CLAUDE.md, or ask the user.

---

## Phase 1 — Orient

```
orient(project_path="<path>", depth=2)
```

If a tree already exists, confirm with the user before resetting.
If no tree exists, proceed to Phase 2.

---

## Phase 2 — Read the Project

Read these files to understand the project:

1. **Entry points**: `README.md`, top-level `*.md` files
2. **Package manifests**: `package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, etc.
3. **Runtime config**: `Dockerfile`, `docker-compose.yml`, `Makefile`
4. **Directory structure**: top 2 levels (use Glob)
5. **Key source files**: entry points, main modules

Determine:
- What does this system do? (one sentence)
- What language(s) / frameworks?
- What are the 3-5 major subsystems?
- How do they relate to each other?

Do not create any nodes yet.

---

## Phase 3 — Create Root

If no root exists:

```
report(
    project_path="<path>",
    new_task="Bootstrap purpose tree",
    new_task_target="",
)
```

Then propose the root structure. The root node should be created via the UI or API first, then use report to propose L1 children.

---

## Phase 4 — Propose L1 Purpose Branches

Propose 3-6 top-level purpose branches. These should be **bounded contexts** — cohesive areas with clear responsibility boundaries.

```
report(
    project_path="<path>",
    proposed_nodes=[
        {"parent_id": "<root_id>", "name": "<Branch>", "description": "<responsibility>"},
        ...
    ],
)
```

Guidelines:
- Name by purpose, not technology ("Auth System" not "JWT Module")
- Each branch should own distinct files with minimal overlap
- Aim for 3-6 branches — fewer is better than more
- Do NOT attach files yet — files attach at leaf nodes during implementation

---

## Phase 5 — Stop

After proposing L1 branches, **stop**. Do not deepen further in this session.

The user reviews and approves/rejects proposals in the UI. Approved nodes auto-create "Propose children for" tasks. The stack-based task system ensures depth-first deepening happens naturally in subsequent sessions.

Report a summary:
- How many L1 branches proposed
- What each branch is responsible for
- Suggested next steps (approve in UI, then run next task)

---

## Principles

**Top-down, not bottom-up.** Start from the system boundary and work inward. Do not create nodes per file.

**Purpose over structure.** Name nodes by what they do, not where they live in the directory tree.

**Fewer, meaningful nodes.** 4 well-named L1 branches > 10 auto-detected folders.

**No files at L1.** Files attach during implementation at leaf nodes. L1 branches are pure purpose — they represent responsibility boundaries, not code.

**Honest proposals.** Propose grey nodes. The user decides what's real. If uncertain about a boundary, propose it and let the user judge.

---

## Additional Resources

For detailed workflow guidance after bootstrap:
- **`../work-task/SKILL.md`** — The core orient-work-report loop
- **`../work-task/references/workflow.md`** — Stack-based depth-first workflow
- **`../work-task/references/tree-model.md`** — Node statuses and file ownership rules
