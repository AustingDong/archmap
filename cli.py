"""
ArchMap CLI — full-featured interface for humans and terminal-based agents.

Covers all ArchMap operations. Use --json for machine-readable output (e.g., when
called by Claude Code via Bash). JSON output is always structured; human output
is formatted tables and prose.

Usage:
    archmap init [--path <dir>] [--name <name>]
    archmap scan [--path <dir>] [--depth <n>] [--overwrite]
    archmap status [--path <dir>]

    archmap component list   [--layer <layer>] [--json]
    archmap component get    <id>             [--json]
    archmap component add    <name> --layer <layer> [--description ...] [--owner ...] [--tier p0|p1|p2|p3]
    archmap component update <id> [--name ...] [--description ...] [--owner ...] [--tier ...]
                                  [--onboarding-notes ...] [--runbook-url ...] [--slack ...]
    archmap component delete <id>

    archmap dep list   [--json]
    archmap dep add    <from-id> <to-id> [--label uses] [--kind runtime]
    archmap dep remove <dep-id>

    archmap file list    [--component <id>] [--json]
    archmap file map     <file-path> <component-id>
    archmap file unmap   <file-path>
    archmap file who     <file-path>
    archmap file bulk    <component-id> <file1> [<file2> ...]

    archmap plan list   [--component <id>] [--status <status>] [--json]
    archmap plan add    <title> [--component <id>] [--priority medium] [--description ...]
    archmap plan update <id> [--status <status>] [--title ...] [--priority ...]
    archmap plan delete <id>

    archmap decision list   [--component <id>] [--status accepted] [--json]
    archmap decision get    <id>                                    [--json]
    archmap decision add    <component-id> <title> [--context ...] [--decision ...] [--consequences ...]
                                                   [--alternatives ...] [--status proposed]
    archmap decision update <id> [--status accepted] [--superseded-by <id>]
    archmap decision delete <id>

    archmap rule list   [--json]
    archmap rule add    --type no_dep --from-layer <layer> --to-layer <layer> --message <msg>
    archmap rule delete <rule-id>

    archmap sync <file> [<file2> ...] [--reinfer] [--validate] [--json]
    archmap health      [--json]
    archmap impact      <component-id> [--json]
    archmap export      [--format mermaid|dot|c4] [--out <file>]
    archmap snapshot    [--label <label>]
    archmap diff        --snapshot <label> [--json]

    archmap collab list    [--json]
    archmap collab claim   <component-id> --actor <actor> [--task ...]
    archmap collab release <component-id> --actor <actor>
    archmap collab changes --since <timestamp> [--json]

    archmap audit [--last <n>] [--actor <actor>] [--json]
    archmap validate [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _cwd() -> str:
    return str(Path.cwd())


# ─── Output helpers ────────────────────────────────────────────────────────────

def _out(data, as_json: bool) -> None:
    if as_json:
        print(json.dumps(data, indent=2, default=str))
    # Human output handled inline per command


def _ok(msg: str) -> None:
    print(f"[OK] {msg}")


def _err(msg: str) -> None:
    print(f"[ERROR] {msg}", file=sys.stderr)
    sys.exit(1)


def _table(rows: list[list], headers: list[str]) -> None:
    if not rows:
        return
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(widths):
                widths[i] = max(widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("─" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(c)[:widths[i]] for i, c in enumerate(row)]))


# ─── init / scan / status ──────────────────────────────────────────────────────

def cmd_init(args):
    from archmap.project import init_project
    path = args.path or _cwd()
    meta = init_project(path, name=args.name or None)
    if args.json:
        print(json.dumps(meta, indent=2, default=str))
    else:
        _ok(f"Initialized ArchMap in: {path}")
        print(f"  Project name : {meta.get('name')}")
        print(f"  Data stored  : {path}/.archmap/")


def cmd_scan(args):
    from archmap.scanner import scan_project
    from archmap.store import is_initialized
    from archmap.project import init_project
    path = args.path or _cwd()
    if not is_initialized(path):
        init_project(path)
    result = scan_project(path, overwrite_auto=args.overwrite, depth=args.depth)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(result["message"])
        if result.get("components"):
            for name in result["components"]:
                print(f"  + {name}")
        print(f"Files mapped: {result['files_mapped']}")


def cmd_status(args):
    from archmap.project import project_status
    path = args.path or _cwd()
    s = project_status(path)
    if args.json:
        print(json.dumps(s, indent=2, default=str))
    else:
        print(f"Project      : {s['name']}")
        print(f"Components   : {s['components']}")
        print(f"Dependencies : {s['dependencies']}")
        print(f"Mapped files : {s['mapped_files']}")
        print(f"Plan items   : {s['plan_items']} total, {s['plan_open']} open")


# ─── component ────────────────────────────────────────────────────────────────

def cmd_component(args):
    from archmap import architecture as arch
    path = args.path or _cwd()
    action = args.component_action

    if action == "list":
        comps = arch.list_components(path, layer=getattr(args, "layer", None) or None)
        if args.json:
            print(json.dumps(comps, indent=2, default=str))
        else:
            rows = [[c["id"], c["name"], c["layer"],
                     c.get("owner", ""), c.get("tier", ""), c.get("confidence", ""),
                     c.get("description", "")[:40]]
                    for c in comps]
            _table(rows, ["ID", "Name", "Layer", "Owner", "Tier", "Conf", "Description"])

    elif action == "get":
        try:
            c = arch.get_component(path, args.id)
        except Exception as e:
            _err(str(e))
        if args.json:
            print(json.dumps(c, indent=2, default=str))
        else:
            for k, v in c.items():
                if v:
                    print(f"  {k:<20} {v}")

    elif action == "add":
        tag_list = [t.strip() for t in args.tags.split(",") if t.strip()] if getattr(args, "tags", None) else []
        c = arch.add_component(
            path, name=args.name, description=getattr(args, "description", "") or "",
            layer=getattr(args, "layer", "other") or "other",
            tags=tag_list,
            owner=getattr(args, "owner", "") or "",
            tier=getattr(args, "tier", "") or "",
            onboarding_notes=getattr(args, "onboarding_notes", "") or "",
            runbook_url=getattr(args, "runbook_url", "") or "",
            slack_channel=getattr(args, "slack", "") or "",
        )
        if args.json:
            print(json.dumps(c, indent=2, default=str))
        else:
            _ok(f"Added component '{c['name']}' ({c['id']})")

    elif action == "update":
        kwargs = {}
        for field in ("name", "description", "layer", "owner", "tier",
                      "onboarding_notes", "runbook_url"):
            v = getattr(args, field.replace("-", "_"), None)
            if v:
                kwargs[field] = v
        if getattr(args, "slack", None):
            kwargs["slack_channel"] = args.slack
        if getattr(args, "confidence", None):
            kwargs["confidence"] = args.confidence
        if getattr(args, "tags", None):
            kwargs["tags"] = [t.strip() for t in args.tags.split(",") if t.strip()]
        result = arch.update_component(path, args.id, **kwargs)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Updated component '{result['name']}' ({result['id']})")

    elif action == "delete":
        arch.delete_component(path, args.id)
        if args.json:
            print(json.dumps({"deleted": True, "id": args.id}))
        else:
            _ok(f"Deleted component {args.id}")


# ─── dep ──────────────────────────────────────────────────────────────────────

def cmd_dep(args):
    from archmap import architecture as arch
    path = args.path or _cwd()
    action = args.dep_action

    if action == "list":
        data = arch.get_architecture(path)
        deps = data.get("dependencies", [])
        if args.json:
            print(json.dumps(deps, indent=2, default=str))
        else:
            name_map = {c["id"]: c["name"] for c in data.get("components", [])}
            rows = [[d["id"], name_map.get(d["from_component"], d["from_component"]),
                     d.get("label", "uses"),
                     name_map.get(d["to_component"], d["to_component"]),
                     d.get("kind", "runtime"), d.get("confidence", "")]
                    for d in deps]
            _table(rows, ["ID", "From", "Label", "To", "Kind", "Conf"])

    elif action == "add":
        result = arch.add_dependency(
            path, args.from_id, args.to_id,
            label=getattr(args, "label", "uses") or "uses",
            kind=getattr(args, "kind", "runtime") or "runtime",
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Added dependency {result['id']}: {args.from_id} → {args.to_id}")

    elif action == "remove":
        arch.remove_dependency(path, args.dep_id)
        if args.json:
            print(json.dumps({"deleted": True, "id": args.dep_id}))
        else:
            _ok(f"Removed dependency {args.dep_id}")


# ─── file ─────────────────────────────────────────────────────────────────────

def cmd_file(args):
    from archmap import mapping as map_mod
    path = args.path or _cwd()
    action = args.file_action

    if action == "list":
        comp_id = getattr(args, "component", None)
        if comp_id:
            files = map_mod.list_component_files(path, comp_id)
        else:
            from archmap.store import load_mappings
            raw = load_mappings(path).get("files", {})
            files = [{"file_path": fp, **v} for fp, v in raw.items()]
        if args.json:
            print(json.dumps(files, indent=2, default=str))
        else:
            rows = [[f["file_path"], f.get("component_id", ""), f.get("language", ""),
                     str(len(f.get("symbols", [])))]
                    for f in files]
            _table(rows, ["File", "Component", "Lang", "Symbols"])

    elif action == "map":
        from archmap.store import normalize_path
        fp = normalize_path(path, args.file_path)
        result = map_mod.map_file(path, fp, args.component_id)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Mapped {fp} → {args.component_id}")

    elif action == "unmap":
        from archmap.store import normalize_path
        fp = normalize_path(path, args.file_path)
        map_mod.unmap_file(path, fp)
        if args.json:
            print(json.dumps({"unmapped": fp}))
        else:
            _ok(f"Unmapped {fp}")

    elif action == "who":
        from archmap.store import normalize_path
        from archmap.cognition import who_owns
        fp = normalize_path(path, args.file_path)
        result = who_owns(path, fp)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result.get("component_name"):
                print(f"{fp} → {result['component_name']} ({result['component_id']})")
            else:
                print(f"{fp} → (unmapped)")

    elif action == "bulk":
        from archmap.store import normalize_path
        mapped = 0
        for fp in args.files:
            rel = normalize_path(path, fp)
            map_mod.map_file(path, rel, args.component_id)
            mapped += 1
        if args.json:
            print(json.dumps({"mapped": mapped, "component_id": args.component_id}))
        else:
            _ok(f"Mapped {mapped} files → {args.component_id}")


# ─── plan ─────────────────────────────────────────────────────────────────────

def cmd_plan(args):
    from archmap import planning as plan_mod
    path = args.path or _cwd()
    action = args.plan_action

    if action == "list":
        items = plan_mod.list_plan_items(
            path,
            component_id=getattr(args, "component", None),
            status=getattr(args, "status", None),
        )
        if args.json:
            print(json.dumps(items, indent=2, default=str))
        else:
            rows = [[i["id"], i["status"], i["priority"],
                     i.get("component_id", "")[:12], i["title"][:50]]
                    for i in items]
            _table(rows, ["ID", "Status", "Priority", "Component", "Title"])

    elif action == "add":
        result = plan_mod.create_plan_item(
            path,
            title=args.title,
            description=getattr(args, "description", "") or "",
            component_id=getattr(args, "component", None),
            priority=getattr(args, "priority", "medium") or "medium",
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Created plan item '{result['title']}' ({result['id']})")

    elif action == "update":
        kwargs = {}
        for field in ("title", "status", "priority", "description"):
            v = getattr(args, field, None)
            if v:
                kwargs[field] = v
        result = plan_mod.update_plan_item(path, args.id, **kwargs)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Updated plan item {args.id}")

    elif action == "delete":
        plan_mod.delete_plan_item(path, args.id)
        if args.json:
            print(json.dumps({"deleted": True, "id": args.id}))
        else:
            _ok(f"Deleted plan item {args.id}")


# ─── decision ─────────────────────────────────────────────────────────────────

def cmd_decision(args):
    from archmap import decisions as dec_mod
    path = args.path or _cwd()
    action = args.decision_action

    if action == "list":
        records = dec_mod.list_decisions(
            path,
            component_id=getattr(args, "component", None) or "",
            status=getattr(args, "status", None) or "",
        )
        if args.json:
            print(json.dumps(records, indent=2, default=str))
        else:
            rows = [[r["id"], r["status"], r.get("component_id", "")[:12], r["title"][:55]]
                    for r in records]
            _table(rows, ["ID", "Status", "Component", "Title"])

    elif action == "get":
        try:
            r = dec_mod.get_decision(path, args.id)
        except KeyError as e:
            _err(str(e))
        if args.json:
            print(json.dumps(r, indent=2, default=str))
        else:
            for k in ("id", "title", "status", "context", "decision", "consequences",
                      "alternatives", "superseded_by", "created_at"):
                v = r.get(k, "")
                if v:
                    print(f"  {k:<16} {v}")

    elif action == "add":
        result = dec_mod.add_decision(
            path,
            component_id=args.component_id,
            title=args.title,
            context=getattr(args, "context", "") or "",
            decision=getattr(args, "decision", "") or "",
            consequences=getattr(args, "consequences", "") or "",
            alternatives=getattr(args, "alternatives", "") or "",
            status=getattr(args, "status", "proposed") or "proposed",
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Recorded ADR '{result['title']}' ({result['id']})")

    elif action == "update":
        kwargs = {}
        for field in ("title", "status", "context", "decision", "consequences", "alternatives"):
            v = getattr(args, field, None)
            if v:
                kwargs[field] = v
        if getattr(args, "superseded_by", None):
            kwargs["superseded_by"] = args.superseded_by
        result = dec_mod.update_decision(path, args.id, **kwargs)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Updated ADR {args.id} (status: {result['status']})")

    elif action == "delete":
        result = dec_mod.delete_decision(path, args.id)
        if args.json:
            print(json.dumps(result))
        else:
            _ok(f"Deleted ADR {args.id}")


# ─── rule ─────────────────────────────────────────────────────────────────────

def cmd_rule(args):
    from archmap import rules as rules_mod
    path = args.path or _cwd()
    action = args.rule_action

    if action == "list":
        records = rules_mod.load_rules(path)
        if args.json:
            print(json.dumps(records, indent=2, default=str))
        else:
            rows = [[r.get("id", ""), r["type"],
                     r.get("from_layer", ""), r.get("to_layer", ""), r.get("message", "")]
                    for r in records]
            _table(rows, ["ID", "Type", "From", "To", "Message"])

    elif action == "add":
        result = rules_mod.add_rule(
            path,
            rule_type=args.type,
            from_layer=getattr(args, "from_layer", "") or "",
            to_layer=getattr(args, "to_layer", "") or "",
            message=getattr(args, "message", "") or "",
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"Added rule {result.get('id', '')} ({args.type})")

    elif action == "delete":
        rules_mod.delete_rule(path, args.rule_id)
        if args.json:
            print(json.dumps({"deleted": True, "id": args.rule_id}))
        else:
            _ok(f"Deleted rule {args.rule_id}")


# ─── sync ─────────────────────────────────────────────────────────────────────

def cmd_sync(args):
    from archmap import mapping as map_mod
    path = args.path or _cwd()
    result = map_mod.post_edit_sync(
        path,
        file_paths=args.files,
        reinfer_dependencies=args.reinfer,
    )
    if args.validate:
        from archmap import rules as rules_mod
        val = rules_mod.validate_architecture(path)
        result["rule_violations"] = val.get("violations", [])
        result["architecture_clean"] = val.get("valid", True)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        synced = result.get("synced", [])
        unmapped = result.get("unmapped", [])
        errors = result.get("errors", {})
        for f in synced:
            print(f"  ✓  {f}")
        for f in unmapped:
            print(f"  ?  {f}  (unmapped — run: archmap file map {f} <component-id>)")
        for f, msg in errors.items():
            print(f"  ✗  {f}: {msg}", file=sys.stderr)
        if args.validate:
            viols = result.get("rule_violations", [])
            if viols:
                print(f"\n  {len(viols)} architectural rule violation(s):")
                for v in viols:
                    print(f"  ✗  {v}")
            else:
                print("  Architecture clean ✓")


# ─── health ───────────────────────────────────────────────────────────────────

def cmd_health(args):
    from archmap import cognition as cog_mod
    from archmap import rules as rules_mod
    from archmap import architecture as arch_mod
    from archmap.impact import get_component_impact
    path = args.path or _cwd()

    integrity = cog_mod.check_integrity(path)
    val_result = rules_mod.validate_architecture(path)
    violations = val_result.get("violations", [])

    cycles = []
    try:
        comps = arch_mod.list_components(path)
        for comp in comps:
            impact = get_component_impact(path, comp["id"])
            if impact.get("cycles"):
                cycles.append({"component": comp["name"], "cycles": impact.get("cycle_names", impact["cycles"])})
    except Exception:
        pass

    result = {
        "integrity": integrity,
        "rule_violations": violations,
        "rule_check": val_result,
        "cycles": cycles,
        "clean": (
            val_result.get("valid", True)
            and not integrity.get("issues")
            and len(cycles) == 0
        ),
    }
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        issues = integrity.get("issues", [])
        if issues:
            print(f"Integrity issues ({len(issues)}):")
            for iss in issues:
                print(f"  ! {iss}")
        if violations:
            print(f"Rule violations ({len(violations)}):")
            for v in violations:
                print(f"  ! {v}")
        if cycles:
            print(f"Circular dependencies ({len(cycles)}):")
            for c in cycles:
                print(f"  ~ {c['component']}: {c['cycles']}")
        if result["clean"]:
            print("Architecture clean")


# ─── impact ───────────────────────────────────────────────────────────────────

def cmd_impact(args):
    from archmap.impact import get_component_impact
    path = args.path or _cwd()
    result = get_component_impact(path, args.component_id)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        print(f"Component    : {result['component_name']} ({args.component_id})")
        print(f"Impact score : {result['impact_score']}")
        print(f"Is root      : {result['is_root']}  |  Is leaf: {result['is_leaf']}")
        if result.get("upstream_names"):
            print(f"Upstream     : {', '.join(result['upstream_names'])}")
        if result.get("downstream_names"):
            print(f"Downstream   : {', '.join(result.get('downstream_names', []))}")
        if result.get("cycles"):
            print(f"Cycles       : {result['cycles']}")


# ─── export ───────────────────────────────────────────────────────────────────

def cmd_export(args):
    from archmap.export import export_architecture
    path = args.path or _cwd()
    fmt = getattr(args, "format", "mermaid") or "mermaid"
    output = export_architecture(path, format=fmt)
    out_file = getattr(args, "out", None)
    if out_file:
        Path(out_file).write_text(output, encoding="utf-8")
        _ok(f"Exported {fmt} to {out_file}")
    else:
        print(output)


# ─── snapshot / diff ──────────────────────────────────────────────────────────

def cmd_snapshot(args):
    from archmap.diff import snapshot_architecture
    path = args.path or _cwd()
    label = getattr(args, "label", None) or None
    result = snapshot_architecture(path, label=label)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _ok(f"Snapshot saved: {result.get('label')} ({result.get('snapshot_id')})")


def cmd_diff(args):
    from archmap.diff import diff_architecture
    path = args.path or _cwd()
    result = diff_architecture(path, snapshot_label=args.snapshot)
    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        added = result.get("components_added", [])
        removed = result.get("components_removed", [])
        changed = result.get("components_changed", [])
        deps_added = result.get("dependencies_added", [])
        deps_removed = result.get("dependencies_removed", [])
        for c in added:
            print(f"  +component  {c.get('name', c)}")
        for c in removed:
            print(f"  -component  {c.get('name', c)}")
        for c in changed:
            print(f"  ~component  {c.get('name', c)}")
        for d in deps_added:
            print(f"  +dep        {d}")
        for d in deps_removed:
            print(f"  -dep        {d}")
        if not any([added, removed, changed, deps_added, deps_removed]):
            print("No architectural changes since snapshot.")


# ─── collab ───────────────────────────────────────────────────────────────────

def cmd_collab(args):
    from archmap import session as session_mod
    path = args.path or _cwd()
    action = args.collab_action

    if action == "list":
        result = session_mod.list_active_work(path)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            claims = result.get("claims", [])
            if not claims:
                print("No active work claims.")
            else:
                rows = [[c["actor"], c.get("component_name", c["component_id"]),
                         c.get("task", ""), f"{c.get('minutes_remaining', 0)}m"]
                        for c in claims]
                _table(rows, ["Actor", "Component", "Task", "Remaining"])

    elif action == "claim":
        result = session_mod.claim_component(
            path, args.component_id, args.actor,
            task=getattr(args, "task", "") or "",
        )
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            _ok(f"{args.actor} claimed {args.component_id} ({result['claim_id']})")

    elif action == "release":
        result = session_mod.release_component(path, args.component_id, args.actor)
        if args.json:
            print(json.dumps(result, indent=2, default=str))
        else:
            if result["released"]:
                _ok(f"Released claim on {args.component_id}")
            else:
                print(f"No active claim found for {args.actor} on {args.component_id}")

    elif action == "changes":
        from archmap import audit as audit_mod
        all_changes = audit_mod.get_audit_log(path, last_n=500)
        try:
            from datetime import datetime, timezone
            since_dt = datetime.fromisoformat(args.since)
            if since_dt.tzinfo is None:
                since_dt = since_dt.replace(tzinfo=timezone.utc)
            changes = [c for c in all_changes
                       if datetime.fromisoformat(c["timestamp"]) > since_dt]
        except (ValueError, AttributeError):
            changes = all_changes
        if args.json:
            print(json.dumps({"changes": changes, "count": len(changes)}, indent=2, default=str))
        else:
            for c in changes:
                print(f"  {c['timestamp'][:19]}  {c.get('actor','?'):<20} {c.get('tool','')} {c.get('summary','')}")


# ─── audit ────────────────────────────────────────────────────────────────────

def cmd_audit(args):
    from archmap import audit as audit_mod
    path = args.path or _cwd()
    records = audit_mod.get_audit_log(
        path,
        last_n=getattr(args, "last", 50) or 50,
        actor=getattr(args, "actor", None) or None,
    )
    if args.json:
        print(json.dumps(records, indent=2, default=str))
    else:
        rows = [[r["timestamp"][:19], r.get("actor", ""), r.get("tool", ""),
                 r.get("change_type", ""), r.get("summary", "")[:50]]
                for r in records]
        _table(rows, ["Timestamp", "Actor", "Tool", "Change", "Summary"])


# ─── validate ─────────────────────────────────────────────────────────────────

def cmd_validate(args):
    from archmap import rules as rules_mod
    path = args.path or _cwd()
    val = rules_mod.validate_architecture(path)
    violations = val.get("violations", [])
    if args.json:
        print(json.dumps(val, indent=2))
    else:
        if violations:
            for v in violations:
                print(f"  ! {v}")
            sys.exit(1)
        else:
            print("Architecture clean")


# ─── Parser construction ──────────────────────────────────────────────────────

def _add_path_json(p):
    p.add_argument("--path", help="Project path (default: cwd)")
    p.add_argument("--json", action="store_true", help="Output as JSON")


# Shared parent parser for sub-subcommands (lets --path/--json appear anywhere)
_COMMON = argparse.ArgumentParser(add_help=False)
_COMMON.add_argument("--path", help="Project path (default: cwd)")
_COMMON.add_argument("--json", action="store_true", help="Output as JSON")


def main():
    parser = argparse.ArgumentParser(
        prog="archmap",
        description="ArchMap — architecture knowledge graph for humans and AI agents",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--path", help="Project path (default: cwd)")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    sub = parser.add_subparsers(dest="command", required=True)

    # ── init ──
    p = sub.add_parser("init", help="Initialize ArchMap in a project directory")
    p.add_argument("--path"); p.add_argument("--name"); p.add_argument("--json", action="store_true")

    # ── scan ──
    p = sub.add_parser("scan", help="Auto-detect components from folder structure")
    p.add_argument("--path"); p.add_argument("--depth", type=int, default=2)
    p.add_argument("--overwrite", action="store_true"); p.add_argument("--json", action="store_true")

    # ── status ──
    p = sub.add_parser("status", help="Show project summary")
    _add_path_json(p)

    # ── component ──
    pc = sub.add_parser("component", help="Manage architecture components", aliases=["comp"])
    pc.add_argument("--path"); pc.add_argument("--json", action="store_true")
    csc = pc.add_subparsers(dest="component_action", required=True)

    p = csc.add_parser("list", parents=[_COMMON]); p.add_argument("--layer")
    p = csc.add_parser("get", parents=[_COMMON]); p.add_argument("id")
    p = csc.add_parser("add", parents=[_COMMON])
    p.add_argument("name"); p.add_argument("--layer", default="other")
    p.add_argument("--description", default=""); p.add_argument("--tags", default="")
    p.add_argument("--owner", default=""); p.add_argument("--tier", default="")
    p.add_argument("--onboarding-notes", dest="onboarding_notes", default="")
    p.add_argument("--runbook-url", dest="runbook_url", default="")
    p.add_argument("--slack", default="")
    p = csc.add_parser("update", parents=[_COMMON])
    p.add_argument("id"); p.add_argument("--name"); p.add_argument("--description")
    p.add_argument("--layer"); p.add_argument("--tags"); p.add_argument("--confidence")
    p.add_argument("--owner"); p.add_argument("--tier")
    p.add_argument("--onboarding-notes", dest="onboarding_notes")
    p.add_argument("--runbook-url", dest="runbook_url"); p.add_argument("--slack")
    p = csc.add_parser("delete", parents=[_COMMON]); p.add_argument("id")

    # ── dep ──
    pd = sub.add_parser("dep", help="Manage dependencies", aliases=["dependency"])
    pd.add_argument("--path"); pd.add_argument("--json", action="store_true")
    dsc = pd.add_subparsers(dest="dep_action", required=True)
    dsc.add_parser("list", parents=[_COMMON])
    p = dsc.add_parser("add", parents=[_COMMON])
    p.add_argument("from_id"); p.add_argument("to_id")
    p.add_argument("--label", default="uses"); p.add_argument("--kind", default="runtime")
    p = dsc.add_parser("remove", parents=[_COMMON]); p.add_argument("dep_id")

    # ── file ──
    pf = sub.add_parser("file", help="Manage file-to-component mappings")
    pf.add_argument("--path"); pf.add_argument("--json", action="store_true")
    fsc = pf.add_subparsers(dest="file_action", required=True)
    p = fsc.add_parser("list", parents=[_COMMON]); p.add_argument("--component")
    p = fsc.add_parser("map", parents=[_COMMON]); p.add_argument("file_path"); p.add_argument("component_id")
    p = fsc.add_parser("unmap", parents=[_COMMON]); p.add_argument("file_path")
    p = fsc.add_parser("who", parents=[_COMMON]); p.add_argument("file_path")
    p = fsc.add_parser("bulk", parents=[_COMMON]); p.add_argument("component_id"); p.add_argument("files", nargs="+")

    # ── plan ──
    pp = sub.add_parser("plan", help="Manage plan items / tasks")
    pp.add_argument("--path"); pp.add_argument("--json", action="store_true")
    psc = pp.add_subparsers(dest="plan_action", required=True)
    p = psc.add_parser("list", parents=[_COMMON]); p.add_argument("--component"); p.add_argument("--status")
    p = psc.add_parser("add", parents=[_COMMON])
    p.add_argument("title"); p.add_argument("--component"); p.add_argument("--description", default="")
    p.add_argument("--priority", default="medium")
    p = psc.add_parser("update", parents=[_COMMON])
    p.add_argument("id"); p.add_argument("--title"); p.add_argument("--status")
    p.add_argument("--priority"); p.add_argument("--description")
    p = psc.add_parser("delete", parents=[_COMMON]); p.add_argument("id")

    # ── decision ──
    pde = sub.add_parser("decision", help="Manage Architecture Decision Records (ADRs)", aliases=["adr"])
    pde.add_argument("--path"); pde.add_argument("--json", action="store_true")
    desc = pde.add_subparsers(dest="decision_action", required=True)
    p = desc.add_parser("list", parents=[_COMMON]); p.add_argument("--component"); p.add_argument("--status")
    p = desc.add_parser("get", parents=[_COMMON]); p.add_argument("id")
    p = desc.add_parser("add", parents=[_COMMON])
    p.add_argument("component_id"); p.add_argument("title")
    p.add_argument("--context", default=""); p.add_argument("--decision", default="")
    p.add_argument("--consequences", default=""); p.add_argument("--alternatives", default="")
    p.add_argument("--status", default="proposed")
    p = desc.add_parser("update", parents=[_COMMON])
    p.add_argument("id"); p.add_argument("--title"); p.add_argument("--status")
    p.add_argument("--context"); p.add_argument("--decision"); p.add_argument("--consequences")
    p.add_argument("--alternatives"); p.add_argument("--superseded-by", dest="superseded_by")
    p = desc.add_parser("delete", parents=[_COMMON]); p.add_argument("id")

    # ── rule ──
    pr = sub.add_parser("rule", help="Manage architectural rules")
    pr.add_argument("--path"); pr.add_argument("--json", action="store_true")
    rsc = pr.add_subparsers(dest="rule_action", required=True)
    rsc.add_parser("list", parents=[_COMMON])
    p = rsc.add_parser("add", parents=[_COMMON])
    p.add_argument("--type", required=True, choices=["no_dep", "no_cycles", "required_dep"])
    p.add_argument("--from-layer", dest="from_layer", default="")
    p.add_argument("--to-layer", dest="to_layer", default="")
    p.add_argument("--message", default="")
    p = rsc.add_parser("delete", parents=[_COMMON]); p.add_argument("rule_id")

    # ── sync ──
    p = sub.add_parser("sync", help="Sync symbols after editing files")
    p.add_argument("files", nargs="+"); p.add_argument("--path")
    p.add_argument("--reinfer", action="store_true", help="Re-infer dependencies")
    p.add_argument("--validate", action="store_true", help="Check architectural rules after sync")
    p.add_argument("--json", action="store_true")

    # ── health ──
    p = sub.add_parser("health", help="Integrity check + validation + cycle detection")
    _add_path_json(p)

    # ── impact ──
    p = sub.add_parser("impact", help="Blast radius for a component")
    p.add_argument("component_id"); p.add_argument("--path"); p.add_argument("--json", action="store_true")

    # ── export ──
    p = sub.add_parser("export", help="Export architecture diagram")
    p.add_argument("--format", choices=["mermaid", "dot", "c4"], default="mermaid")
    p.add_argument("--out", help="Write output to file instead of stdout")
    p.add_argument("--path"); p.add_argument("--json", action="store_true")

    # ── snapshot ──
    p = sub.add_parser("snapshot", help="Save an architecture snapshot")
    p.add_argument("--label"); p.add_argument("--path"); p.add_argument("--json", action="store_true")

    # ── diff ──
    p = sub.add_parser("diff", help="Show architectural changes since a snapshot")
    p.add_argument("--snapshot", required=True, help="Snapshot label")
    p.add_argument("--path"); p.add_argument("--json", action="store_true")

    # ── collab ──
    pcl = sub.add_parser("collab", help="Multi-agent collaboration")
    pcl.add_argument("--path"); pcl.add_argument("--json", action="store_true")
    clsc = pcl.add_subparsers(dest="collab_action", required=True)
    clsc.add_parser("list", parents=[_COMMON])
    p = clsc.add_parser("claim", parents=[_COMMON])
    p.add_argument("component_id"); p.add_argument("--actor", required=True); p.add_argument("--task", default="")
    p = clsc.add_parser("release", parents=[_COMMON])
    p.add_argument("component_id"); p.add_argument("--actor", required=True)
    p = clsc.add_parser("changes", parents=[_COMMON])
    p.add_argument("--since", required=True)

    # ── audit ──
    p = sub.add_parser("audit", help="Show audit log")
    p.add_argument("--last", type=int, default=50); p.add_argument("--actor")
    p.add_argument("--path"); p.add_argument("--json", action="store_true")

    # ── validate ──
    p = sub.add_parser("validate", help="Check dependencies against architectural rules")
    _add_path_json(p)

    # ── dispatch ──────────────────────────────────────────────────────────────
    args = parser.parse_args()

    # Propagate top-level --path/--json to subcommand args if not set
    if not getattr(args, "path", None) and hasattr(parser, "_defaults"):
        pass

    dispatch = {
        "init":       cmd_init,
        "scan":       cmd_scan,
        "status":     cmd_status,
        "component":  cmd_component,
        "comp":       cmd_component,
        "dep":        cmd_dep,
        "dependency": cmd_dep,
        "file":       cmd_file,
        "plan":       cmd_plan,
        "decision":   cmd_decision,
        "adr":        cmd_decision,
        "rule":       cmd_rule,
        "sync":       cmd_sync,
        "health":     cmd_health,
        "impact":     cmd_impact,
        "export":     cmd_export,
        "snapshot":   cmd_snapshot,
        "diff":       cmd_diff,
        "collab":     cmd_collab,
        "audit":      cmd_audit,
        "validate":   cmd_validate,
    }

    try:
        fn = dispatch.get(args.command)
        if fn:
            fn(args)
        else:
            parser.print_help()
    except Exception as e:
        if getattr(args, "json", False):
            print(json.dumps({"ok": False, "error": str(e)}, indent=2))
        else:
            _err(str(e))


if __name__ == "__main__":
    main()
