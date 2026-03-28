"""
Contract management — declare, retrieve, and validate node contracts.

A Contract formally specifies what a node (at any level 1-5) exposes to the
rest of the system and what it consumes from others. Contracts are stored in
architecture.json["contracts"] keyed by node_id.

Agents use contracts to understand:
  - What operations they can call on a dependency (without reading its source)
  - What their own public API is (and therefore what they cannot break)
  - What data they own vs. data they merely read
"""
from __future__ import annotations
from archmap.models import Contract, ContractOp, ContractEvent, DataType, NotFoundError, _now
from archmap.store import load_contracts, mutate_contracts, load_arch


# ─── CRUD ─────────────────────────────────────────────────────────────────────

def declare_contract(
    project_path: str,
    node_id: str,
    node_level: int = 4,
    commands: list[dict] | None = None,
    queries: list[dict] | None = None,
    events_emitted: list[dict] | None = None,
    events_consumed: list[dict] | None = None,
    data_owned: list[dict] | None = None,
    data_read: list[dict] | None = None,
    api_spec_url: str = "",
    sla: str = "",
    declared_by: str = "user",
) -> dict:
    """
    Declare or fully replace the contract for a node.
    If a contract already exists for node_id it is overwritten.
    """
    # Validate the node exists
    arch = load_arch(project_path)
    node_ids = {c["id"] for c in arch.get("components", [])}
    if node_id not in node_ids:
        raise NotFoundError(f"Node not found: {node_id!r}")

    contract = Contract(
        node_id=node_id,
        node_level=node_level,
        commands=[ContractOp.from_dict(op) for op in (commands or [])],
        queries=[ContractOp.from_dict(op) for op in (queries or [])],
        events_emitted=[ContractEvent.from_dict(e) for e in (events_emitted or [])],
        events_consumed=[ContractEvent.from_dict(e) for e in (events_consumed or [])],
        data_owned=[DataType.from_dict(dt) for dt in (data_owned or [])],
        data_read=[DataType.from_dict(dt) for dt in (data_read or [])],
        api_spec_url=api_spec_url,
        sla=sla,
        declared_by=declared_by,
    )
    contract_dict = contract.to_dict()

    def _mutate(contracts: dict):
        contracts[node_id] = contract_dict

    mutate_contracts(project_path, _mutate)
    return contract_dict


def get_contract(project_path: str, node_id: str) -> dict:
    """Return the contract for a node, or an empty structure if none declared."""
    contracts = load_contracts(project_path)
    if node_id not in contracts:
        return {
            "node_id": node_id,
            "declared": False,
            "commands": [],
            "queries": [],
            "events_emitted": [],
            "events_consumed": [],
            "data_owned": [],
            "data_read": [],
            "api_spec_url": "",
            "sla": "",
        }
    c = contracts[node_id]
    c["declared"] = True
    return c


def list_contracts(project_path: str, node_level: int | None = None) -> list[dict]:
    """List all declared contracts, optionally filtered by node_level."""
    contracts = load_contracts(project_path)
    result = list(contracts.values())
    if node_level is not None:
        result = [c for c in result if c.get("node_level") == node_level]
    return result


def patch_contract(
    project_path: str,
    node_id: str,
    **kwargs,
) -> dict:
    """
    Partial update to an existing contract — add/replace specific fields only.
    Useful for incrementally building up a contract without re-declaring everything.
    """
    contracts = load_contracts(project_path)
    if node_id not in contracts:
        # Bootstrap empty contract first
        arch = load_arch(project_path)
        node_ids = {c["id"] for c in arch.get("components", [])}
        if node_id not in node_ids:
            raise NotFoundError(f"Node not found: {node_id!r}")
        existing = {"node_id": node_id, "node_level": 4, "commands": [],
                    "queries": [], "events_emitted": [], "events_consumed": [],
                    "data_owned": [], "data_read": [], "api_spec_url": "", "sla": "",
                    "declared_at": _now(), "declared_by": "user"}
    else:
        existing = dict(contracts[node_id])

    list_fields = {"commands", "queries", "events_emitted", "events_consumed",
                   "data_owned", "data_read"}
    for k, v in kwargs.items():
        if k in list_fields and isinstance(v, list):
            # Merge by name — replace existing entry with same name, append new ones
            existing_by_name = {item["name"]: item for item in existing.get(k, [])}
            for item in v:
                existing_by_name[item["name"]] = item
            existing[k] = list(existing_by_name.values())
        elif v is not None:
            existing[k] = v

    existing["declared_at"] = _now()

    def _mutate(contracts: dict):
        contracts[node_id] = existing

    mutate_contracts(project_path, _mutate)
    return existing


def delete_contract(project_path: str, node_id: str) -> str:
    def _mutate(contracts: dict):
        if node_id not in contracts:
            raise NotFoundError(f"Contract not found for node: {node_id!r}")
        del contracts[node_id]

    mutate_contracts(project_path, _mutate)
    return "deleted"


# ─── Contract-break detection ──────────────────────────────────────────────────

def check_contract_break(
    project_path: str,
    node_id: str,
    operation_name: str,
    new_input_type: str = "",
    new_output_type: str = "",
) -> dict:
    """
    Check whether changing an operation would break the declared contract.
    Compares new_input_type / new_output_type against what was declared.

    Returns:
      breaking: bool
      reason: str (empty if not breaking)
      callers: list of dependency edges that reference this operation
    """
    arch = load_arch(project_path)
    contracts = load_contracts(project_path)

    contract = contracts.get(node_id)
    if not contract:
        return {"breaking": False, "reason": "No contract declared for this node", "callers": []}

    # Find the operation in commands or queries
    all_ops = contract.get("commands", []) + contract.get("queries", [])
    existing_op = next((op for op in all_ops if op["name"] == operation_name), None)

    if not existing_op:
        return {"breaking": False, "reason": "Operation not in declared contract", "callers": []}

    reasons = []
    if new_input_type and new_input_type != existing_op.get("input_type", ""):
        reasons.append(
            f"input_type changed: '{existing_op.get('input_type','')}' → '{new_input_type}'"
        )
    if new_output_type and new_output_type != existing_op.get("output_type", ""):
        reasons.append(
            f"output_type changed: '{existing_op.get('output_type','')}' → '{new_output_type}'"
        )

    # Find edges that reference this operation in interface_points
    callers = []
    name_map = {c["id"]: c["name"] for c in arch.get("components", [])}
    for dep in arch.get("dependencies", []):
        if dep.get("to_component") == node_id and operation_name in dep.get("interface_points", []):
            callers.append({
                "from_component": dep["from_component"],
                "from_name": name_map.get(dep["from_component"], dep["from_component"]),
                "dep_id": dep["id"],
                "stability": dep.get("stability", "stable"),
            })

    return {
        "breaking": len(reasons) > 0,
        "reason": "; ".join(reasons),
        "operation": operation_name,
        "callers": callers,
        "caller_count": len(callers),
    }
