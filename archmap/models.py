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


# ─── Component ────────────────────────────────────────────────────────────────

ComponentLayer = Literal["frontend", "backend", "database", "infra", "shared", "testing", "other"]
Confidence = Literal["auto", "confirmed"]


@dataclass
class Component:
    id: str
    name: str
    description: str = ""
    layer: str = "other"
    tags: list[str] = field(default_factory=list)
    color: str = "#6366f1"
    confidence: Confidence = "confirmed"
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
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            metadata=d.get("metadata", {}),
        )


# ─── Dependency ───────────────────────────────────────────────────────────────

DependencyKind = Literal["runtime", "build", "test", "dev"]


@dataclass
class Dependency:
    id: str
    from_component: str
    to_component: str
    label: str = "uses"
    kind: DependencyKind = "runtime"
    created_at: str = field(default_factory=_now)

    @staticmethod
    def new(from_component: str, to_component: str, **kwargs) -> "Dependency":
        return Dependency(id=_short_id("dep"), from_component=from_component, to_component=to_component, **kwargs)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_component": self.from_component,
            "to_component": self.to_component,
            "label": self.label,
            "kind": self.kind,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> "Dependency":
        return Dependency(
            id=d["id"],
            from_component=d["from_component"],
            to_component=d["to_component"],
            label=d.get("label", "uses"),
            kind=d.get("kind", "runtime"),
            created_at=d.get("created_at", _now()),
        )


# ─── FileMapping ──────────────────────────────────────────────────────────────

@dataclass
class FileMapping:
    file_path: str          # relative, forward slashes
    component_id: str
    mapped_at: str = field(default_factory=_now)
    mapped_by: str = "user"  # "user" | "scanner" | agent name

    def to_dict(self) -> dict:
        return {
            "component_id": self.component_id,
            "mapped_at": self.mapped_at,
            "mapped_by": self.mapped_by,
        }

    @staticmethod
    def from_dict(file_path: str, d: dict) -> "FileMapping":
        return FileMapping(
            file_path=file_path,
            component_id=d["component_id"],
            mapped_at=d.get("mapped_at", _now()),
            mapped_by=d.get("mapped_by", "user"),
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
