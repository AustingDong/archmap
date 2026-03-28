"""
One-shot migration: restructure ArchMap's flat component graph into the
5-level multi-layer hierarchy.

Invoke via:
  MCP: bootstrap_architecture(project_path=..., strategy="multilevel")
  CLI: python cli.py migrate --path <project_path>

What it does:
  1. Creates L1 System node
  2. Creates L2 Domain nodes (UI, Access Protocol, Architecture Graph, Persistence)
  3. Promotes existing components to correct levels with parent_id
  4. Splits "Core Engine" into 4 L4 components under Architecture Graph domain
  5. Annotates all existing dependency edges with semantic types (edge_type,
     edge_level, interface_points, payload_types, stability, crosses_boundary)
  6. Declares contracts for each node

The migration is IDEMPOTENT: running it again skips nodes/edges that already
have level/edge_type set, so it is safe to re-run.
"""
from __future__ import annotations
from archmap.store import load_arch, mutate_arch, mutate_mappings, load_mappings
from archmap.models import Component, Dependency, _now, _short_id
from archmap.contracts import declare_contract


# ─── Known component roles (by name pattern) ──────────────────────────────────

_DOMAIN_SPEC = {
    "ui_domain": {
        "name": "User Interface Domain",
        "description": "Everything the user sees and interacts with. Owns the visual representation of the architecture graph.",
        "layer": "frontend",
        "color": "#34d399",
        "data_owned": ["GraphNode", "GraphEdge", "UIState"],
        "members": ["React Frontend"],
    },
    "access_domain": {
        "name": "Access Protocol Domain",
        "description": "Entry points into the system: HTTP REST for the UI, MCP stdio for agents, CLI for operators.",
        "layer": "infra",
        "color": "#8b5cf6",
        "data_owned": [],
        "members": ["REST API", "MCP Server", "CLI"],
    },
    "arch_domain": {
        "name": "Architecture Graph Domain",
        "description": "Core knowledge graph: stores, analyses, and reasons about the architecture. Owns all graph data.",
        "layer": "backend",
        "color": "#60a5fa",
        "data_owned": ["Component", "Dependency", "Contract", "Symbol", "FileMapping", "PlanItem"],
        "members": [
            "Core Engine", "Intelligence Layer", "Impact Engine",
            "Export & Diff", "Decisions (ADRs)", "Collaboration", "Data Models",
        ],
    },
    "persist_domain": {
        "name": "Persistence Domain",
        "description": "Durable storage layer. Owns the .archmap/ directory and atomic JSON files.",
        "layer": "database",
        "color": "#fbbf24",
        "data_owned": ["architecture.json", "mappings.json", "plan.json", "meta.json"],
        "members": ["Storage Layer"],
    },
}

# ── Semantic annotation for known dependency patterns ─────────────────────────

_EDGE_ANNOTATIONS = [
    # (from_name_fragment, to_name_fragment, edge_type, edge_level, interface_points, payload_types, stability, async_flag)
    ("React Frontend", "REST API",          "query",      "service",   ["GET /api/architecture", "GET /api/components", "POST /api/components", "GET /api/plan"], ["Component[]", "Dependency[]", "PlanItem[]"], "stable", False),
    ("REST API",       "Core Engine",        "command",    "component", ["add_component", "update_component", "delete_component", "add_dependency", "create_plan_item", "update_plan_item"], ["Component", "Dependency", "PlanItem"], "stable", False),
    ("REST API",       "Intelligence Layer", "query",      "component", ["describe_architecture", "find_related", "get_symbol_index", "trace_path"], ["str", "dict"], "stable", False),
    ("MCP Server",     "Core Engine",        "command",    "component", ["add_component", "update_component", "scan_project", "map_file", "post_edit_sync"], ["Component", "FileMapping"], "stable", False),
    ("MCP Server",     "Intelligence Layer", "query",      "component", ["describe_architecture", "get_generation_context", "find_related", "search_symbol"], ["str", "dict"], "stable", False),
    ("MCP Server",     "Storage Layer",      "data_read",  "service",   ["load_arch", "load_mappings"], ["dict"], "stable", False),
    ("MCP Server",     "Export & Diff",      "invoke",     "component", ["export_architecture", "snapshot_architecture", "diff_architecture"], ["str"], "stable", False),
    ("MCP Server",     "Collaboration",      "invoke",     "component", ["claim_component", "release_component", "list_active_work"], ["dict"], "stable", False),
    ("MCP Server",     "Data Models",        "import",     "component", [], ["Component", "Dependency", "Symbol"], "stable", False),
    ("MCP Server",     "Decisions (ADRs)",   "import",     "component", ["add_decision", "list_decisions", "get_decision"], ["dict"], "stable", False),
    ("Core Engine",    "Storage Layer",      "data_write", "service",   ["mutate_arch", "mutate_mappings", "mutate_plan"], ["dict"], "stable", False),
    ("Core Engine",    "Data Models",        "import",     "component", [], ["Component", "Dependency", "FileMapping", "PlanItem"], "stable", False),
    ("Intelligence Layer", "Core Engine",    "query",      "component", ["get_architecture", "list_components"], ["dict"], "stable", False),
    ("Intelligence Layer", "Storage Layer",  "data_read",  "service",   ["load_arch", "load_mappings"], ["dict"], "stable", False),
    ("Intelligence Layer", "Data Models",    "import",     "component", [], ["Component", "Dependency", "Symbol"], "stable", False),
    ("Export & Diff",  "Storage Layer",      "data_read",  "service",   ["load_arch"], ["dict"], "stable", False),
    ("Export & Diff",  "Data Models",        "import",     "component", [], ["Component", "Dependency"], "stable", False),
    ("Collaboration",  "Storage Layer",      "data_write", "service",   ["mutate_arch"], ["dict"], "stable", False),
    ("Collaboration",  "Core Engine",        "query",      "component", ["get_component"], ["Component"], "stable", False),
    ("CLI",            "Core Engine",        "command",    "component", ["scan_project", "add_component", "create_plan_item"], ["Component", "PlanItem"], "stable", False),
    ("CLI",            "Storage Layer",      "import",     "component", [], [], "stable", False),
    ("CLI",            "Data Models",        "import",     "component", [], ["Component", "PlanItem"], "stable", False),
    ("Storage Layer",  "Data Models",        "import",     "component", [], ["Component", "Dependency", "FileMapping", "PlanItem"], "stable", False),
    ("Decisions (ADRs)", "Storage Layer",    "data_write", "service",   ["mutate_arch"], ["dict"], "stable", False),
    ("REST API",       "Data Models",        "import",     "component", [], ["Component", "Dependency"], "stable", False),
]


def bootstrap_multilevel_graph(project_path: str) -> dict:
    """
    Transform the flat graph into a 5-level hierarchy.
    Returns a summary of what was created/updated.
    """
    arch = load_arch(project_path)
    by_name: dict[str, dict] = {c["name"]: c for c in arch.get("components", [])}

    created_nodes: list[str] = []
    updated_nodes: list[str] = []
    annotated_edges: list[str] = []
    contracts_declared: list[str] = []

    # ── Step 1: Create L1 System node ─────────────────────────────────────────
    def _mutate_system(data: dict):
        existing = next((c for c in data.get("components", []) if c.get("level") == 1), None)
        if existing:
            return existing["id"]
        sys_node = Component.new(
            name="ArchMap",
            description="Architecture knowledge graph system for humans and AI agents. Maps codebases, tracks decisions, and provides structure-aware context for code generation.",
            layer="other",
            level=1,
            parent_id="",
            stability="stable",
            color="#1e293b",
            tags=["system"],
        )
        data.setdefault("components", []).append(sys_node.to_dict())
        return sys_node.id

    system_id = mutate_arch(project_path, _mutate_system)
    if system_id not in [c["id"] for c in load_arch(project_path).get("components", []) if c.get("level") == 1 and c["id"] != system_id]:
        created_nodes.append("ArchMap [L1 System]")

    # ── Step 2: Create L2 Domain nodes ────────────────────────────────────────
    domain_ids: dict[str, str] = {}  # domain_key → node_id

    for domain_key, spec in _DOMAIN_SPEC.items():
        def _mutate_domain(data: dict, spec=spec, domain_key=domain_key):
            existing = next(
                (c for c in data.get("components", [])
                 if c.get("level") == 2 and c["name"] == spec["name"]),
                None
            )
            if existing:
                return existing["id"]
            d_node = Component.new(
                name=spec["name"],
                description=spec["description"],
                layer=spec["layer"],
                level=2,
                parent_id=system_id,
                stability="stable",
                color=spec["color"],
                data_owned=spec["data_owned"],
                tags=["domain"],
            )
            data.setdefault("components", []).append(d_node.to_dict())
            return d_node.id

        did = mutate_arch(project_path, _mutate_domain)
        domain_ids[domain_key] = did
        created_nodes.append(f"{spec['name']} [L2 Domain]")

    # Reload to get fresh state
    arch = load_arch(project_path)
    by_name = {c["name"]: c for c in arch.get("components", [])}

    # Rebuild domain_ids mapping from stored data (ids may differ if already existed)
    for domain_key, spec in _DOMAIN_SPEC.items():
        stored = next((c for c in arch.get("components", []) if c.get("level") == 2 and c["name"] == spec["name"]), None)
        if stored:
            domain_ids[domain_key] = stored["id"]

    # ── Step 3: Set level=3 on service nodes + assign parent_id ───────────────
    service_map = {
        "React Frontend": ("ui_domain",      3, "http_rest", 5174, True),
        "REST API":       ("access_domain",  3, "http_rest", 8765, True),
        "MCP Server":     ("access_domain",  3, "stdio",     None, False),
        "CLI":            ("access_domain",  3, "cli",       None, False),
        "Storage Layer":  ("persist_domain", 3, "filesystem",None, False),
    }

    def _mutate_services(data: dict):
        for c in data.get("components", []):
            if c["name"] in service_map:
                domain_key, lv, proto, port, deploy = service_map[c["name"]]
                if c.get("level", 4) == 4:  # only update if still at default
                    c["level"] = lv
                    c["parent_id"] = domain_ids.get(domain_key, "")
                    c["protocol"] = proto
                    if port:
                        c["port"] = port
                    c["deploy_unit"] = deploy
                    c["updated_at"] = _now()
                    updated_nodes.append(f"{c['name']} → L{lv}")

    mutate_arch(project_path, _mutate_services)

    # ── Step 4: Assign L4 components to their domain parent ───────────────────
    comp_parent_map = {
        "Intelligence Layer": "arch_domain",
        "Impact Engine":      "arch_domain",
        "Export & Diff":      "arch_domain",
        "Decisions (ADRs)":   "arch_domain",
        "Collaboration":      "arch_domain",
        "Data Models":        "arch_domain",
        "tests":              "arch_domain",
    }

    def _mutate_comp_parents(data: dict):
        for c in data.get("components", []):
            if c["name"] in comp_parent_map and not c.get("parent_id"):
                domain_key = comp_parent_map[c["name"]]
                c["parent_id"] = domain_ids.get(domain_key, "")
                c["updated_at"] = _now()
                updated_nodes.append(f"{c['name']} → parent={_DOMAIN_SPEC[domain_key]['name']}")

    mutate_arch(project_path, _mutate_comp_parents)

    # ── Step 5: Split "Core Engine" into sub-components ───────────────────────
    arch = load_arch(project_path)
    core_engine = next((c for c in arch.get("components", []) if c["name"] == "Core Engine"), None)
    arch_domain_id = domain_ids.get("arch_domain", "")

    sub_components = [
        {
            "name": "Architecture CRUD",
            "description": "Component and dependency create/read/update/delete. The mutation surface for the knowledge graph.",
            "files": ["archmap/architecture.py"],
            "public_api": ["add_component", "update_component", "delete_component", "add_dependency",
                           "remove_dependency", "get_architecture", "get_dependency_graph",
                           "annotate_dependency", "promote_to_contract", "remap_files_to_node"],
            "data_owned": ["Component", "Dependency"],
            "color": "#6366f1",
        },
        {
            "name": "Planning Engine",
            "description": "Task/plan CRUD: create, update, delete, and list plan items. Tracks work-in-progress against components.",
            "files": ["archmap/planning.py"],
            "public_api": ["list_plan_items", "create_plan_item", "update_plan_item", "delete_plan_item"],
            "data_owned": ["PlanItem"],
            "color": "#10b981",
        },
        {
            "name": "Mapping Engine",
            "description": "File-to-component mapping registry: map, unmap, annotate, bulk_map. Also manages file staleness tracking.",
            "files": ["archmap/mapping.py"],
            "public_api": ["map_file", "unmap_file", "get_file_component", "list_component_files",
                           "update_file_metadata", "bulk_map", "list_all_mappings"],
            "data_owned": ["FileMapping"],
            "color": "#f59e0b",
        },
        {
            "name": "Scanner",
            "description": "Auto-detection: scans project directories, infers component membership, extracts imports to infer dependencies.",
            "files": ["archmap/scanner.py", "archmap/inference.py", "archmap/watcher.py"],
            "public_api": ["scan_project", "infer_dependencies", "confirm_dependency", "start_watcher", "stop_watcher"],
            "data_owned": [],
            "color": "#0ea5e9",
        },
    ]

    if core_engine:
        core_id = core_engine["id"]
        sub_ids: dict[str, str] = {}

        def _mutate_split(data: dict):
            existing_names = {c["name"] for c in data.get("components", [])}
            for spec in sub_components:
                if spec["name"] not in existing_names:
                    sub = Component.new(
                        name=spec["name"],
                        description=spec["description"],
                        layer="backend",
                        level=4,
                        parent_id=arch_domain_id,
                        public_api=spec["public_api"],
                        data_owned=spec["data_owned"],
                        stability="stable",
                        color=spec["color"],
                        tags=["core-engine"],
                    )
                    data.setdefault("components", []).append(sub.to_dict())
                    sub_ids[spec["name"]] = sub.id
                    created_nodes.append(f"{spec['name']} [L4 split from Core Engine]")
                else:
                    existing = next(c for c in data["components"] if c["name"] == spec["name"])
                    sub_ids[spec["name"]] = existing["id"]

        mutate_arch(project_path, _mutate_split)

        # Reload to get new IDs
        arch = load_arch(project_path)
        sub_ids = {c["name"]: c["id"] for c in arch.get("components", [])
                   if c["name"] in {s["name"] for s in sub_components}}

        # Remap files to sub-components
        for spec in sub_components:
            if spec["files"]:
                from archmap.architecture import remap_files_to_node
                sub_id = sub_ids.get(spec["name"])
                if sub_id:
                    result = remap_files_to_node(project_path, spec["files"], sub_id)
                    if result["remapped"]:
                        updated_nodes.append(f"Remapped {result['remapped']} → {spec['name']}")

        # Also parent the Core Engine itself under arch_domain and mark as L2 aggregate
        def _mutate_core_parent(data: dict):
            for c in data.get("components", []):
                if c["id"] == core_id:
                    if not c.get("parent_id"):
                        c["parent_id"] = arch_domain_id
                    c["description"] = (
                        "Aggregate component — split into: Architecture CRUD, Planning Engine, "
                        "Mapping Engine, Scanner. Kept for backwards-compatibility with existing edges."
                    )
                    c["updated_at"] = _now()

        mutate_arch(project_path, _mutate_core_parent)

    # ── Step 6: Annotate existing dependency edges ────────────────────────────
    arch = load_arch(project_path)
    name_map = {c["name"]: c["id"] for c in arch.get("components", [])}

    def _name_match(comp_name: str, fragment: str) -> bool:
        return fragment.lower() in comp_name.lower()

    def _mutate_edges(data: dict):
        for dep in data.get("dependencies", []):
            # Skip if already annotated
            if dep.get("edge_type") and dep["edge_type"] != "invoke":
                continue

            # Find from/to names
            from_comp = next((c for c in data.get("components", []) if c["id"] == dep["from_component"]), {})
            to_comp   = next((c for c in data.get("components", []) if c["id"] == dep["to_component"]),   {})
            fname = from_comp.get("name", "")
            tname = to_comp.get("name", "")

            for ann in _EDGE_ANNOTATIONS:
                ff, tf, etype, elevel, ipts, ptypes, stab, async_f = ann
                if _name_match(fname, ff) and _name_match(tname, tf):
                    dep["edge_type"] = etype
                    dep["edge_level"] = elevel
                    dep["interface_points"] = ipts
                    dep["payload_types"] = ptypes
                    dep["stability"] = stab
                    dep["async_flag"] = async_f

                    # Detect cross-boundary (service-level crosses are level ≤ 3)
                    from_lv = from_comp.get("level", 4)
                    to_lv   = to_comp.get("level", 4)
                    dep["crosses_boundary"] = (elevel in ("service", "domain")) or (from_lv != to_lv)

                    annotated_edges.append(f"{fname} --[{etype}]--> {tname}")
                    break

    mutate_arch(project_path, _mutate_edges)

    # ── Step 7: Declare contracts for key nodes ────────────────────────────────
    arch = load_arch(project_path)
    by_name_fresh = {c["name"]: c for c in arch.get("components", [])}

    contracts_to_declare = [
        {
            "name": "Storage Layer",
            "node_level": 3,
            "commands": [
                {"name": "mutate_arch", "description": "Atomically update architecture.json", "input_type": "Callable[[dict], Any]", "output_type": "Any", "stability": "stable"},
                {"name": "mutate_mappings", "description": "Atomically update mappings.json", "input_type": "Callable[[dict], Any]", "output_type": "Any", "stability": "stable"},
                {"name": "mutate_plan", "description": "Atomically update plan.json", "input_type": "Callable[[dict], Any]", "output_type": "Any", "stability": "stable"},
            ],
            "queries": [
                {"name": "load_arch", "description": "Read architecture.json", "input_type": "str", "output_type": "dict", "stability": "stable"},
                {"name": "load_mappings", "description": "Read mappings.json", "input_type": "str", "output_type": "dict", "stability": "stable"},
                {"name": "load_plan", "description": "Read plan.json", "input_type": "str", "output_type": "dict", "stability": "stable"},
            ],
            "data_owned": [
                {"type_name": "architecture.json", "description": "Component and dependency graph", "stability": "stable", "authoritative": True},
                {"type_name": "mappings.json", "description": "File-to-component mapping registry", "stability": "stable", "authoritative": True},
            ],
            "sla": "local filesystem, no network; atomic writes via temp-file rename",
        },
        {
            "name": "REST API",
            "node_level": 3,
            "queries": [
                {"name": "GET /api/architecture", "description": "Get full architecture graph", "output_type": "DependencyGraph", "stability": "stable"},
                {"name": "GET /api/components", "description": "List all components", "output_type": "Component[]", "stability": "stable"},
                {"name": "GET /api/plan", "description": "List plan items", "output_type": "PlanItem[]", "stability": "stable"},
            ],
            "commands": [
                {"name": "POST /api/components", "description": "Add a component", "input_type": "AddComponentReq", "output_type": "Component", "stability": "stable"},
                {"name": "POST /api/plan", "description": "Create plan item", "input_type": "CreatePlanReq", "output_type": "PlanItem", "stability": "stable"},
                {"name": "POST /api/post_edit_sync", "description": "Sync symbols after edit", "input_type": "PostEditSyncReq", "output_type": "dict", "stability": "stable"},
            ],
            "sla": "local dev: no SLA; production: p99 < 200ms",
            "api_spec_url": "http://localhost:8765/docs",
        },
        {
            "name": "Data Models",
            "node_level": 4,
            "queries": [],
            "commands": [],
            "data_owned": [
                {"type_name": "Component", "description": "Architecture node with level, parent, public API", "stability": "stable", "authoritative": True},
                {"type_name": "Dependency", "description": "Typed edge between nodes with edge_type, interface_points, payload_types", "stability": "stable", "authoritative": True},
                {"type_name": "Contract", "description": "Formal contract declaration for a node", "stability": "stable", "authoritative": True},
                {"type_name": "Symbol", "description": "Extracted code symbol with signature and visibility", "stability": "stable", "authoritative": True},
                {"type_name": "FileMapping", "description": "File-to-component association with symbol index", "stability": "stable", "authoritative": True},
                {"type_name": "PlanItem", "description": "Work item linked to a component", "stability": "stable", "authoritative": True},
            ],
        },
    ]

    for spec in contracts_to_declare:
        node = by_name_fresh.get(spec["name"])
        if not node:
            continue
        try:
            declare_contract(
                project_path=project_path,
                node_id=node["id"],
                node_level=spec.get("node_level", 4),
                commands=spec.get("commands", []),
                queries=spec.get("queries", []),
                data_owned=spec.get("data_owned", []),
                api_spec_url=spec.get("api_spec_url", ""),
                sla=spec.get("sla", ""),
                declared_by="migration",
            )
            contracts_declared.append(spec["name"])
        except Exception:
            pass

    return {
        "ok": True,
        "created_nodes": created_nodes,
        "updated_nodes": updated_nodes,
        "annotated_edges": annotated_edges,
        "contracts_declared": contracts_declared,
        "summary": (
            f"Created {len(created_nodes)} nodes, "
            f"updated {len(updated_nodes)} nodes, "
            f"annotated {len(annotated_edges)} edges, "
            f"declared {len(contracts_declared)} contracts."
        ),
    }
