"""
Architectural rule enforcement.

Rules are stored in .archmap/rules.json as a list of constraint objects:
  {
    "id": "rule_abc123",
    "type": "no_dep",          # from_layer cannot depend on to_layer
    "from_layer": "frontend",
    "to_layer": "database",
    "message": "Frontend must not access the database directly"
  }
  {
    "id": "rule_def456",
    "type": "no_cycles",       # no circular dependencies allowed
    "message": "Circular dependencies are forbidden"
  }

Supported rule types:
  - no_dep:    from_layer cannot have a dependency on to_layer
  - no_cycles: no cyclic dependencies anywhere in the graph
  - required_dep: from_layer must depend on to_layer (at least one)
"""
from __future__ import annotations
import json
from pathlib import Path
from archmap.repo import require_init as _require_init
from archmap.architecture import get_architecture
from archmap.impact import _bfs

RULES_FILE = "rules.json"


def _rules_path(project_path: str) -> Path:
    return _require_init(project_path) / RULES_FILE


def load_rules(project_path: str) -> list[dict]:
    p = _rules_path(project_path)
    if not p.exists():
        return []
    return json.loads(p.read_text(encoding="utf-8"))


def save_rules(project_path: str, rules: list[dict]) -> None:
    p = _rules_path(project_path)
    p.write_text(json.dumps(rules, indent=2), encoding="utf-8")


def add_rule(project_path: str, rule_type: str, **kwargs) -> dict:
    """Add a new architectural rule. Returns the created rule dict."""
    from archmap.models import _short_id
    rule = {"id": _short_id("rule"), "type": rule_type, **kwargs}
    rules = load_rules(project_path)
    rules.append(rule)
    save_rules(project_path, rules)
    return rule


def delete_rule(project_path: str, rule_id: str) -> bool:
    rules = load_rules(project_path)
    new = [r for r in rules if r["id"] != rule_id]
    if len(new) == len(rules):
        return False
    save_rules(project_path, new)
    return True


def validate_architecture(project_path: str) -> dict:
    """
    Check all current dependencies against the configured rules.
    Returns: {valid, violations: [{rule_id, rule_type, message, from_component, to_component}]}
    """
    rules = load_rules(project_path)
    arch = get_architecture(project_path)
    components = arch.get("components", [])
    deps = arch.get("dependencies", [])

    comp_by_id: dict[str, dict] = {c["id"]: c for c in components}
    name_map: dict[str, str] = {c["id"]: c["name"] for c in components}
    layer_map: dict[str, str] = {c["id"]: c.get("layer", "") for c in components}

    violations: list[dict] = []

    # Build adjacency for cycle detection
    outgoing: dict[str, list[str]] = {c["id"]: [] for c in components}
    for d in deps:
        f, t = d["from_component"], d["to_component"]
        if f in outgoing:
            outgoing[f].append(t)

    for rule in rules:
        rtype = rule.get("type")
        rid = rule["id"]
        msg = rule.get("message", "")

        if rtype == "no_dep":
            from_layer = rule.get("from_layer", "")
            to_layer = rule.get("to_layer", "")
            for d in deps:
                fl = layer_map.get(d["from_component"], "")
                tl = layer_map.get(d["to_component"], "")
                if fl == from_layer and tl == to_layer:
                    violations.append({
                        "rule_id": rid,
                        "rule_type": rtype,
                        "message": msg or f"{from_layer} → {to_layer} dependency is not allowed",
                        "from_component": d["from_component"],
                        "from_name": name_map.get(d["from_component"], "?"),
                        "to_component": d["to_component"],
                        "to_name": name_map.get(d["to_component"], "?"),
                        "dep_id": d["id"],
                    })

        elif rtype == "no_cycles":
            for comp_id in comp_by_id:
                downstream = _bfs(outgoing, comp_id)
                if comp_id in _bfs(outgoing, next(iter(downstream), comp_id)) or any(
                    comp_id in _bfs(outgoing, d) for d in downstream
                ):
                    # Cheaper check: any node where bfs from a downstream reaches back
                    for d in downstream:
                        if comp_id in _bfs(outgoing, d):
                            violations.append({
                                "rule_id": rid,
                                "rule_type": rtype,
                                "message": msg or "Circular dependency detected",
                                "from_component": comp_id,
                                "from_name": name_map.get(comp_id, "?"),
                                "to_component": d,
                                "to_name": name_map.get(d, "?"),
                                "dep_id": None,
                            })

        elif rtype == "required_dep":
            from_layer = rule.get("from_layer", "")
            to_layer = rule.get("to_layer", "")
            from_comps = [c["id"] for c in components if c.get("layer") == from_layer]
            to_comps = {c["id"] for c in components if c.get("layer") == to_layer}
            dep_pairs = {(d["from_component"], d["to_component"]) for d in deps}
            for fc in from_comps:
                if not any((fc, tc) in dep_pairs for tc in to_comps):
                    violations.append({
                        "rule_id": rid,
                        "rule_type": rtype,
                        "message": msg or f"{from_layer} component must depend on a {to_layer} component",
                        "from_component": fc,
                        "from_name": name_map.get(fc, "?"),
                        "to_component": None,
                        "to_name": f"(any {to_layer})",
                        "dep_id": None,
                    })

    return {
        "valid": len(violations) == 0,
        "rule_count": len(rules),
        "violation_count": len(violations),
        "violations": violations,
    }
