"""
ArchMap CLI — manage architecture maps from the terminal.

Usage:
    python cli.py init [--path <dir>] [--name <name>]
    python cli.py scan [--path <dir>] [--depth <n>] [--overwrite]
    python cli.py status [--path <dir>]
    python cli.py list [--path <dir>] [--layer <layer>]
    python cli.py plan [--path <dir>] [--status <status>]
"""
import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


def _cwd() -> str:
    return str(Path.cwd())


def _print_table(rows: list[list[str]], headers: list[str]) -> None:
    widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(str(cell)))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*headers))
    print("  ".join("-" * w for w in widths))
    for row in rows:
        print(fmt.format(*[str(c) for c in row]))


# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_init(args):
    from archmap.project import init_project
    path = args.path or _cwd()
    meta = init_project(path, name=args.name or None)
    print(f"[OK] Initialized ArchMap in: {path}")
    print(f"  Project name : {meta.get('name')}")
    print(f"  Version      : {meta.get('archmap_version')}")
    print(f"  Data stored  : {path}/.archmap/")
    print()
    print("Next step: python cli.py scan --path", path)


def cmd_scan(args):
    from archmap.project import init_project, project_status
    from archmap.scanner import scan_project
    path = args.path or _cwd()

    # Auto-init if needed
    from archmap.store import is_initialized
    if not is_initialized(path):
        init_project(path)
        print(f"  Auto-initialized .archmap/ in {path}")

    print(f"Scanning {path} (depth={args.depth})...")
    result = scan_project(path, overwrite_auto=args.overwrite, depth=args.depth)
    print(f"\n{result['message']}")
    if result["components"]:
        print("\nDetected components:")
        for name in result["components"]:
            print(f"  - {name}")
    print(f"\nFiles mapped : {result['files_mapped']}")
    if result["mapping_errors"]:
        print(f"Errors       : {result['mapping_errors']}")
    print(f"\nUse 'python cli.py list --path {path}' to see all components.")


def cmd_status(args):
    from archmap.project import project_status
    path = args.path or _cwd()
    s = project_status(path)
    print(f"Project     : {s['name']}")
    print(f"Path        : {path}")
    print(f"Components  : {s['components']}")
    print(f"Dependencies: {s['dependencies']}")
    print(f"Mapped files: {s['mapped_files']}")
    print(f"Plan items  : {s['plan_items']} total, {s['plan_open']} open")


def cmd_list(args):
    from archmap.architecture import list_components
    path = args.path or _cwd()
    comps = list_components(path, layer=args.layer or None)
    if not comps:
        print("No components found. Run: python cli.py scan")
        return
    rows = [[c["id"], c["name"], c["layer"], c["confidence"], c.get("description", "")[:50]]
            for c in comps]
    _print_table(rows, ["ID", "Name", "Layer", "Confidence", "Description"])


def cmd_plan(args):
    from archmap.planning import list_plan_items
    path = args.path or _cwd()
    items = list_plan_items(path, status=args.status or None)
    if not items:
        print("No plan items found.")
        return
    rows = [[i["id"], i["status"], i["priority"], i["title"][:60]] for i in items]
    _print_table(rows, ["ID", "Status", "Priority", "Title"])


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        prog="archmap",
        description="ArchMap — Architecture mapping + planning with MCP support",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # init
    p_init = sub.add_parser("init", help="Initialize ArchMap in a project")
    p_init.add_argument("--path", help="Project path (default: cwd)")
    p_init.add_argument("--name", help="Project name")

    # scan
    p_scan = sub.add_parser("scan", help="Auto-detect components from folder structure")
    p_scan.add_argument("--path", help="Project path (default: cwd)")
    p_scan.add_argument("--depth", type=int, default=2, help="Scan depth (default: 2)")
    p_scan.add_argument("--overwrite", action="store_true", help="Re-detect auto components")

    # status
    p_status = sub.add_parser("status", help="Show project summary")
    p_status.add_argument("--path", help="Project path (default: cwd)")

    # list
    p_list = sub.add_parser("list", help="List components")
    p_list.add_argument("--path", help="Project path (default: cwd)")
    p_list.add_argument("--layer", help="Filter by layer")

    # plan
    p_plan = sub.add_parser("plan", help="List plan items")
    p_plan.add_argument("--path", help="Project path (default: cwd)")
    p_plan.add_argument("--status", help="Filter by status")

    args = parser.parse_args()

    dispatch = {
        "init": cmd_init,
        "scan": cmd_scan,
        "status": cmd_status,
        "list": cmd_list,
        "plan": cmd_plan,
    }
    try:
        dispatch[args.command](args)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
