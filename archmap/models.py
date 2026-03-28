"""
ArchMap data models — all dataclasses with to_dict / from_dict.
No external dependencies.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal, Optional
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


# ─── Component (ArchNode) ─────────────────────────────────────────────────────
#
# level=1  System     — the product as a whole
# level=2  Domain     — bounded context; owns specific data; has a team
# level=3  Service    — deployable/runnable unit; has a protocol and port
# level=4  Component  — cohesive functional group; has a declared public API
# level=5  Module     — single file or tightly-coupled file group
#
# Existing components default to level=4 (backward-compatible).

ComponentLayer = Literal["frontend", "backend", "database", "infra", "shared", "testing", "other"]
Confidence = Literal["auto", "confirmed"]
ComponentTier = Literal["p0", "p1", "p2", "p3", ""]
NodeLevel = Literal[1, 2, 3, 4, 5]
Stability = Literal["stable", "beta", "internal", "deprecated"]
Protocol = Literal["http_rest", "grpc", "stdio", "cli", "library", "filesystem", "message_queue", ""]


@dataclass
class Component:
    id: str
    name: str
    description: str = ""
    layer: str = "other"
    tags: list[str] = field(default_factory=list)
    color: str = "#6366f1"
    confidence: Confidence = "confirmed"

    # ── Multi-level hierarchy (Phase 1 additions) ──────────────────────────────
    level: int = 4                  # 1=system 2=domain 3=service 4=component 5=module
    parent_id: str = ""             # id of parent node; "" = top-level

    # ── L3 service metadata ────────────────────────────────────────────────────
    protocol: str = ""              # http_rest | grpc | stdio | cli | library | filesystem
    port: Optional[int] = None      # listening port (L3 services)
    deploy_unit: bool = False       # independently startable/deployable

    # ── L4 component interface ─────────────────────────────────────────────────
    public_api: list[str] = field(default_factory=list)    # declared stable symbol names
    data_owned: list[str] = field(default_factory=list)    # types this node is authoritative for
    stability: str = "stable"       # stable | beta | internal | deprecated

    # ── Ownership & operational metadata ──────────────────────────────────────
    owner: str = ""
    tier: str = ""
    onboarding_notes: str = ""
    runbook_url: str = ""
    slack_channel: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(name: str, **kwargs) -> "Component":
        return Component(id=_short_id("comp"), name=name, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "layer": self.layer,
            "tags": self.tags,
            "color": self.color,
            "confidence": self.confidence,
            # hierarchy
            "level": self.level,
            "parent_id": self.parent_id,
            # service
            "protocol": self.protocol,
            "port": self.port,
            "deploy_unit": self.deploy_unit,
            # component interface
            "public_api": self.public_api,
            "data_owned": self.data_owned,
            "stability": self.stability,
            # ownership
            "owner": self.owner,
            "tier": self.tier,
            "onboarding_notes": self.onboarding_notes,
            "runbook_url": self.runbook_url,
            "slack_channel": self.slack_channel,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "Component":
        return Component(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            layer=d.get("layer", "other"),
            tags=d.get("tags", []),
            color=d.get("color", "#6366f1"),
            confidence=d.get("confidence", "confirmed"),
            # hierarchy
            level=d.get("level", 4),
            parent_id=d.get("parent_id", ""),
            # service
            protocol=d.get("protocol", ""),
            port=d.get("port"),
            deploy_unit=d.get("deploy_unit", False),
            # component interface
            public_api=d.get("public_api", []),
            data_owned=d.get("data_owned", []),
            stability=d.get("stability", "stable"),
            # ownership
            owner=d.get("owner", ""),
            tier=d.get("tier", ""),
            onboarding_notes=d.get("onboarding_notes", ""),
            runbook_url=d.get("runbook_url", ""),
            slack_channel=d.get("slack_channel", ""),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            metadata=d.get("metadata", {}),
        )


# ─── Dependency (ArchEdge) ────────────────────────────────────────────────────
#
# edge_type classifies what kind of interaction crosses the boundary:
#   command    — write intent (caller mutates state in target)
#   query      — read request (caller reads data from target)
#   event      — async notification; caller publishes, target subscribes
#   import     — static type/module import only (no runtime data flow)
#   data_read  — reads data owned by target (storage-level)
#   data_write — writes/mutates data owned by target (storage-level)
#   invoke     — synchronous function call (generic, use command/query when known)
#   stream     — continuous data flow (websocket, SSE, queue consumer)
#
# edge_level tracks which abstraction level the edge lives at:
#   domain     — L2→L2 cross-domain integration
#   service    — L3→L3 cross-service call (network boundary)
#   component  — L4→L4 within-service component call
#   module     — L5→L5 file import

DependencyKind = Literal["runtime", "build", "test", "dev"]
EdgeType = Literal["command", "query", "event", "import", "data_read", "data_write", "invoke", "stream"]
EdgeLevel = Literal["domain", "service", "component", "module"]


@dataclass
class Dependency:
    id: str
    from_component: str
    to_component: str
    label: str = "uses"
    kind: DependencyKind = "runtime"
    confidence: Confidence = "confirmed"
    created_at: str = field(default_factory=_now)

    # ── Semantic edge typing (Phase 1 additions) ───────────────────────────────
    edge_type: str = "invoke"           # EdgeType — what kind of interaction
    edge_level: str = "component"       # EdgeLevel — which abstraction level
    crosses_boundary: bool = False      # True if from/to are at different levels
    async_flag: bool = False            # True for events/queues, False for sync calls
    direction: str = "uni"             # uni | bi

    # ── What flows across the boundary ────────────────────────────────────────
    interface_points: list[str] = field(default_factory=list)  # specific ops/fns/endpoints used
    payload_types: list[str] = field(default_factory=list)      # data types transferred
    stability: str = "stable"          # stable | internal | experimental | deprecated

    @staticmethod
    def new(from_component: str, to_component: str, **kwargs) -> "Dependency":
        return Dependency(id=_short_id("dep"), from_component=from_component,
                          to_component=to_component, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_component": self.from_component,
            "to_component": self.to_component,
            "label": self.label,
            "kind": self.kind,
            "confidence": self.confidence,
            "created_at": self.created_at,
            # semantic edge typing
            "edge_type": self.edge_type,
            "edge_level": self.edge_level,
            "crosses_boundary": self.crosses_boundary,
            "async_flag": self.async_flag,
            "direction": self.direction,
            # what flows
            "interface_points": self.interface_points,
            "payload_types": self.payload_types,
            "stability": self.stability,
        }

    @staticmethod
    def from_dict(d: dict) -> "Dependency":
        return Dependency(
            id=d["id"],
            from_component=d["from_component"],
            to_component=d["to_component"],
            label=d.get("label", "uses"),
            kind=d.get("kind", "runtime"),
            confidence=d.get("confidence", "confirmed"),
            created_at=d.get("created_at", _now()),
            # semantic
            edge_type=d.get("edge_type", "invoke"),
            edge_level=d.get("edge_level", "component"),
            crosses_boundary=d.get("crosses_boundary", False),
            async_flag=d.get("async_flag", False),
            direction=d.get("direction", "uni"),
            interface_points=d.get("interface_points", []),
            payload_types=d.get("payload_types", []),
            stability=d.get("stability", "stable"),
        )


# ─── Contract ─────────────────────────────────────────────────────────────────
#
# A Contract formally declares what a node (at any level) exposes and consumes.
# Stored in architecture.json["contracts"] keyed by node_id.

@dataclass
class ContractOp:
    """A single operation (command or query) declared in a contract."""
    name: str
    description: str = ""
    input_type: str = ""    # parameter schema or type name
    output_type: str = ""   # return type schema or type name
    stability: str = "stable"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_type": self.input_type,
            "output_type": self.output_type,
            "stability": self.stability,
        }

    @staticmethod
    def from_dict(d: dict) -> "ContractOp":
        return ContractOp(
            name=d["name"],
            description=d.get("description", ""),
            input_type=d.get("input_type", ""),
            output_type=d.get("output_type", ""),
            stability=d.get("stability", "stable"),
        )


@dataclass
class ContractEvent:
    """An event emitted or consumed by a node."""
    name: str
    description: str = ""
    payload_type: str = ""
    stability: str = "stable"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "payload_type": self.payload_type,
            "stability": self.stability,
        }

    @staticmethod
    def from_dict(d: dict) -> "ContractEvent":
        return ContractEvent(
            name=d["name"],
            description=d.get("description", ""),
            payload_type=d.get("payload_type", ""),
            stability=d.get("stability", "stable"),
        )


@dataclass
class DataType:
    """A data type declared in a contract — ownership and schema."""
    type_name: str
    description: str = ""
    schema: str = ""        # JSON schema string, TypeScript interface, or prose
    stability: str = "stable"
    authoritative: bool = True  # True=this node owns it, False=reads but doesn't own

    def to_dict(self) -> dict:
        return {
            "type_name": self.type_name,
            "description": self.description,
            "schema": self.schema,
            "stability": self.stability,
            "authoritative": self.authoritative,
        }

    @staticmethod
    def from_dict(d: dict) -> "DataType":
        return DataType(
            type_name=d["type_name"],
            description=d.get("description", ""),
            schema=d.get("schema", ""),
            stability=d.get("stability", "stable"),
            authoritative=d.get("authoritative", True),
        )


@dataclass
class Contract:
    """
    Formal declaration of what a node exposes and consumes.
    - commands: mutations this node accepts (changes state)
    - queries:  reads this node accepts (returns data)
    - events_emitted: facts this node publishes asynchronously
    - events_consumed: events this node subscribes to
    - data_owned: data types this node is the authoritative source for
    - data_read: data types this node reads but does not own
    - api_spec_url: link to OpenAPI spec, proto file, etc. (L3 services)
    - sla: service-level agreement string (L3 services)
    """
    node_id: str
    node_level: int = 4

    commands: list[ContractOp] = field(default_factory=list)
    queries: list[ContractOp] = field(default_factory=list)
    events_emitted: list[ContractEvent] = field(default_factory=list)
    events_consumed: list[ContractEvent] = field(default_factory=list)
    data_owned: list[DataType] = field(default_factory=list)
    data_read: list[DataType] = field(default_factory=list)

    api_spec_url: str = ""
    sla: str = ""

    declared_at: str = field(default_factory=_now)
    declared_by: str = "user"

    def to_dict(self) -> dict:
        return {
            "node_id": self.node_id,
            "node_level": self.node_level,
            "commands": [op.to_dict() for op in self.commands],
            "queries": [op.to_dict() for op in self.queries],
            "events_emitted": [e.to_dict() for e in self.events_emitted],
            "events_consumed": [e.to_dict() for e in self.events_consumed],
            "data_owned": [dt.to_dict() for dt in self.data_owned],
            "data_read": [dt.to_dict() for dt in self.data_read],
            "api_spec_url": self.api_spec_url,
            "sla": self.sla,
            "declared_at": self.declared_at,
            "declared_by": self.declared_by,
        }

    @staticmethod
    def from_dict(d: dict) -> "Contract":
        return Contract(
            node_id=d["node_id"],
            node_level=d.get("node_level", 4),
            commands=[ContractOp.from_dict(op) for op in d.get("commands", [])],
            queries=[ContractOp.from_dict(op) for op in d.get("queries", [])],
            events_emitted=[ContractEvent.from_dict(e) for e in d.get("events_emitted", [])],
            events_consumed=[ContractEvent.from_dict(e) for e in d.get("events_consumed", [])],
            data_owned=[DataType.from_dict(dt) for dt in d.get("data_owned", [])],
            data_read=[DataType.from_dict(dt) for dt in d.get("data_read", [])],
            api_spec_url=d.get("api_spec_url", ""),
            sla=d.get("sla", ""),
            declared_at=d.get("declared_at", _now()),
            declared_by=d.get("declared_by", "user"),
        )


# ─── Symbol ───────────────────────────────────────────────────────────────────

@dataclass
class Symbol:
    id: str                   # "sym_" + sha256(file_path + ":" + name)[:12]
    name: str                 # raw name without parens: "validate_token"
    display_name: str         # "validate_token()" for fn, "MyClass" for class
    kind: str                 # "function" | "class" | "method" | "const" | "interface"
    file_path: str            # relative path (denormalized for fast lookup)
    component_id: str         # denormalized
    signature: str            # "def validate_token(token: str) -> dict"
    doc: str                  # first line of docstring
    visibility: str           # "public" | "private"
    is_entry_point: bool      # True if this is a primary API/entry callable

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "display_name": self.display_name,
            "kind": self.kind,
            "file_path": self.file_path,
            "component_id": self.component_id,
            "signature": self.signature,
            "doc": self.doc,
            "visibility": self.visibility,
            "is_entry_point": self.is_entry_point,
        }

    @staticmethod
    def from_dict(d: dict) -> "Symbol":
        return Symbol(
            id=d.get("id", ""),
            name=d.get("name", ""),
            display_name=d.get("display_name", d.get("name", "")),
            kind=d.get("kind", "function"),
            file_path=d.get("file_path", ""),
            component_id=d.get("component_id", ""),
            signature=d.get("signature", ""),
            doc=d.get("doc", ""),
            visibility=d.get("visibility", "public"),
            is_entry_point=d.get("is_entry_point", False),
        )


# ─── FileMapping ──────────────────────────────────────────────────────────────

@dataclass
class FileMapping:
    file_path: str
    component_id: str
    mapped_at: str = field(default_factory=_now)
    mapped_by: str = "user"
    content_hash: str = ""
    synced_at: str = ""
    language: str = ""
    symbols: list[Symbol] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "mapped_at": self.mapped_at,
            "mapped_by": self.mapped_by,
            "content_hash": self.content_hash,
            "synced_at": self.synced_at,
            "language": self.language,
            "symbols": [s.to_dict() for s in self.symbols],
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(file_path: str, d: dict) -> "FileMapping":
        raw_symbols = d.get("symbols", [])
        if raw_symbols:
            symbols = [Symbol.from_dict(s) for s in raw_symbols]
        else:
            meta = d.get("metadata", {})
            sym_details = meta.get("symbol_details", [])
            fn_names = meta.get("functions", [])
            symbols = []
            if sym_details:
                for sd in sym_details:
                    raw_name = sd["name"].rstrip("()")
                    import hashlib
                    sym_id = "sym_" + hashlib.sha256(f"{file_path}:{raw_name}".encode()).hexdigest()[:12]
                    symbols.append(Symbol(
                        id=sym_id,
                        name=raw_name,
                        display_name=sd["name"],
                        kind="class" if sd["name"] == raw_name else "function",
                        file_path=file_path,
                        component_id=d.get("component_id", ""),
                        signature=sd.get("signature", ""),
                        doc=sd.get("doc", ""),
                        visibility="private" if raw_name.startswith("_") else "public",
                        is_entry_point=raw_name in {"main", "run", "app", "start", "cli"},
                    ))
            elif fn_names:
                for fn in fn_names:
                    raw_name = fn.rstrip("()")
                    import hashlib
                    sym_id = "sym_" + hashlib.sha256(f"{file_path}:{raw_name}".encode()).hexdigest()[:12]
                    symbols.append(Symbol(
                        id=sym_id,
                        name=raw_name,
                        display_name=fn,
                        kind="class" if fn == raw_name else "function",
                        file_path=file_path,
                        component_id=d.get("component_id", ""),
                        signature="",
                        doc="",
                        visibility="private" if raw_name.startswith("_") else "public",
                        is_entry_point=raw_name in {"main", "run", "app", "start", "cli"},
                    ))

        language = d.get("language", "") or d.get("metadata", {}).get("language", "")

        return FileMapping(
            file_path=file_path,
            component_id=d["component_id"],
            mapped_at=d.get("mapped_at", _now()),
            mapped_by=d.get("mapped_by", "user"),
            content_hash=d.get("content_hash", ""),
            synced_at=d.get("synced_at", ""),
            language=language,
            symbols=symbols,
            metadata=d.get("metadata", {}),
        )


# ─── PlanItem ─────────────────────────────────────────────────────────────────

PlanStatus = Literal["todo", "in_progress", "done", "blocked", "cancelled"]
PlanPriority = Literal["low", "medium", "high", "critical"]


@dataclass
class PlanItem:
    id: str
    title: str
    description: str = ""
    component_id: Optional[str] = None
    status: PlanStatus = "todo"
    priority: PlanPriority = "medium"
    tags: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def new(title: str, **kwargs) -> "PlanItem":
        return PlanItem(id=_short_id("plan"), title=title, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "component_id": self.component_id,
            "status": self.status,
            "priority": self.priority,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }

    @staticmethod
    def from_dict(d: dict) -> "PlanItem":
        return PlanItem(
            id=d["id"],
            title=d["title"],
            description=d.get("description", ""),
            component_id=d.get("component_id"),
            status=d.get("status", "todo"),
            priority=d.get("priority", "medium"),
            tags=d.get("tags", []),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            metadata=d.get("metadata", {}),
        )


# ─── Error ────────────────────────────────────────────────────────────────────

class ArchMapError(Exception):
    pass


class ProjectNotInitializedError(ArchMapError):
    def __init__(self, project_path: str):
        super().__init__(
            f"ArchMap not initialized in '{project_path}'. Run: python cli.py init --path {project_path}"
        )


class NotFoundError(ArchMapError):
    pass
