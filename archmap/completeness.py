"""
Knowledge completeness scoring for ArchMap nodes.

A completeness score measures how well-documented and current a component is
in the knowledge graph — not code quality, but structural knowledge coverage
and whether completed tasks have been reflected back into the graph.

Scoring signals (total 100 points):
  +10  description present and >20 chars
  +15  contract declared (contracts.json has an entry with declared=True)
  +10  contract.public_api / commands / queries non-empty
  +10  contract.data_owned non-empty
  +15  ≥1 mapped source file
  +15  ≥1 synced symbol across owned files
  +15  graph is current: 0 tasks completed since last sync (no drift)
  +10  ≥1 accepted ADR

The "graph is current" signal replaces a days-based staleness check.
A component that had tasks completed after its last post_edit_sync has
structural drift — the graph no longer reflects the actual code.
"""
from __future__ import annotations

from archmap.repo import load_arch, load_mappings, load_contracts
from archmap.context import _collect_descendants
import archmap.decisions as decisions_mod
import archmap.planning as planning_mod


def score_component(project_path: str, component_id: str) -> dict:
    """
    Score how well-documented and current a single component is (0–100).

    Args:
        project_path:  Path to the ArchMap project root.
        component_id:  Component to score.

    Returns:
        {
          score: int,
          component_id: str,
          name: str,
          signals: {
            description: bool,
            contract_declared: bool,
            public_api: bool,
            data_owned: bool,
            files_mapped: bool,
            symbols_synced: bool,
            graph_current: bool,      # no tasks completed since last sync
            has_adrs: bool
          },
          tasks_since_sync: int,      # tasks completed after last sync
          missing: [str]
        }
    """
    arch = load_arch(project_path)
    by_id = {c["id"]: c for c in arch.get("components", [])}
    node = by_id.get(component_id)
    if not node:
        return {"error": f"Node not found: {component_id!r}"}

    mappings = load_mappings(project_path)
    contracts = load_contracts(project_path)

    # Gather all descendant IDs to count files/symbols owned by subtree
    owned_ids = {component_id} | _collect_descendants(arch, component_id)

    # ── Signals ────────────────────────────────────────────────────────────────
    desc = node.get("description", "")
    has_description = isinstance(desc, str) and len(desc) > 20

    contract = contracts.get(component_id, {})
    contract_declared = bool(contract.get("declared", False))
    has_public_api = bool(
        contract.get("public_api", []) or
        contract.get("commands", []) or
        contract.get("queries", [])
    )
    has_data_owned = bool(contract.get("data_owned", []))

    owned_files = [
        fp for fp, rec in mappings.get("files", {}).items()
        if rec.get("component_id") in owned_ids
    ]
    has_files = len(owned_files) > 0

    has_symbols = any(
        len(mappings["files"][fp].get("symbols", [])) > 0
        for fp in owned_files
        if fp in mappings.get("files", {})
    )

    # Graph-current signal: tasks completed after the last sync timestamp
    # Last sync = earliest synced_at among owned files (most conservative)
    synced_at = ""
    for fp in owned_files:
        sat = mappings.get("files", {}).get(fp, {}).get("synced_at", "")
        if sat and (not synced_at or sat < synced_at):
            synced_at = sat

    tasks_since_sync = 0
    if synced_at:
        try:
            tasks_since_sync = planning_mod.tasks_completed_since_sync(
                project_path, component_id, synced_at
            )
        except Exception:
            tasks_since_sync = 0

    graph_current = tasks_since_sync == 0

    try:
        all_decisions = decisions_mod.list_decisions(project_path, component_id=component_id, status="accepted")
        has_adrs = len(all_decisions) > 0
    except Exception:
        has_adrs = False

    # ── Scoring ────────────────────────────────────────────────────────────────
    _WEIGHTS = {
        "description":       10,
        "contract_declared": 15,
        "public_api":        10,
        "data_owned":        10,
        "files_mapped":      15,
        "symbols_synced":    15,
        "graph_current":     15,
        "has_adrs":          10,
    }

    earned = 0
    total_available = sum(_WEIGHTS.values())
    missing: list[str] = []

    def _check(key: str, value: bool, label: str) -> None:
        nonlocal earned
        if value:
            earned += _WEIGHTS[key]
        else:
            missing.append(label)

    _check("description",       has_description,    "no description (or too short)")
    _check("contract_declared", contract_declared,   "no declared contract")
    _check("public_api",        has_public_api,      "contract missing public_api/commands/queries")
    _check("data_owned",        has_data_owned,      "contract missing data_owned")
    _check("files_mapped",      has_files,           "no files mapped")
    _check("symbols_synced",    has_symbols,         "no symbols synced")
    _check("graph_current",     graph_current,       f"graph drift: {tasks_since_sync} task(s) completed since last sync")
    _check("has_adrs",          has_adrs,            "no accepted ADRs")

    score = round(earned * 100 / total_available) if total_available > 0 else 0

    return {
        "score": score,
        "component_id": component_id,
        "name": node.get("name", component_id),
        "signals": {
            "description":       has_description,
            "contract_declared": contract_declared,
            "public_api":        has_public_api,
            "data_owned":        has_data_owned,
            "files_mapped":      has_files,
            "symbols_synced":    has_symbols,
            "graph_current":     graph_current,
            "has_adrs":          has_adrs,
        },
        "tasks_since_sync": tasks_since_sync,
        "missing": missing,
    }


def score_all_components(project_path: str) -> list[dict]:
    """
    Score every component in the graph, sorted by score ascending (gaps first).

    Returns a list of score_component() results (without the `signals` detail
    for brevity — only score, name, component_id, missing).
    """
    arch = load_arch(project_path)
    components = arch.get("components", [])

    results = []
    for comp in components:
        result = score_component(project_path, comp["id"])
        if "error" in result:
            continue
        results.append({
            "score": result["score"],
            "component_id": result["component_id"],
            "name": result["name"],
            "level": comp.get("level", 4),
            "layer": comp.get("layer", "other"),
            "missing": result["missing"],
        })

    results.sort(key=lambda r: r["score"])
    return results
