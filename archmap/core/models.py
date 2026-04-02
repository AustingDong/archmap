"""
ArchMap data models — a purpose tree with code leaves.

The tree is the only data structure. Depth = abstraction level:
  root        "What is this project?"
  branches    "What does it do?"  (purpose groups, user-curated)
  leaves      "Where is the code?" (files/symbols, auto-populated)
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal
import uuid


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id() -> str:
    return uuid.uuid4().hex[:8]


NodeStatus = Literal["confirmed", "proposed", "removing"]
TaskStatus = Literal["queued", "active", "done", "rejected"]


@dataclass
class TreeNode:
    """A node in the purpose tree.

    Upper nodes (user-curated): describe *what* and *why*.
    Lower nodes (auto-populated): point to *where* in the code.
    """
    id: str
    name: str
    description: str = ""
    status: NodeStatus = "confirmed"
    user_notes: str = ""              # user's corrections/constraints
    children: list[TreeNode] = field(default_factory=list)

    # Code leaves — only set on leaf-ish nodes
    files: list[str] = field(default_factory=list)
    file_snapshots: dict[str, float] = field(default_factory=dict)  # {rel_path: mtime_epoch}
    # Cross-branch references in plain text
    cross_references: list[str] = field(default_factory=list)

    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @staticmethod
    def new(name: str, **kwargs) -> TreeNode:
        return TreeNode(id=_short_id(), name=name, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "user_notes": self.user_notes,
            "children": [c.to_dict() for c in self.children],
            "files": self.files,
            "file_snapshots": self.file_snapshots,
            "cross_references": self.cross_references,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @staticmethod
    def from_dict(d: dict) -> TreeNode:
        return TreeNode(
            id=d["id"],
            name=d["name"],
            description=d.get("description", ""),
            status="confirmed" if d.get("status", "confirmed") == "provisional" else d.get("status", "confirmed"),
            user_notes=d.get("user_notes", ""),
            children=[TreeNode.from_dict(c) for c in d.get("children", [])],
            files=d.get("files", []),
            file_snapshots=d.get("file_snapshots", {}),
            cross_references=d.get("cross_references", []),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
        )

    def depth(self) -> int:
        """Max depth of this subtree."""
        if not self.children:
            return 0
        return 1 + max(c.depth() for c in self.children)

    def find(self, node_id: str) -> TreeNode | None:
        """Find a node by id anywhere in the subtree."""
        if self.id == node_id:
            return self
        for child in self.children:
            found = child.find(node_id)
            if found:
                return found
        return None

    def path_to(self, node_id: str) -> list[TreeNode] | None:
        """Return the path from this node to the target, or None."""
        if self.id == node_id:
            return [self]
        for child in self.children:
            path = child.path_to(node_id)
            if path:
                return [self] + path
        return None

    def walk(self):
        """Yield all nodes in pre-order."""
        yield self
        for child in self.children:
            yield from child.walk()


# ─── Task ────────────────────────────────────────────────────────────────────

@dataclass
class Task:
    """A scoped intention that drives tree growth.

    Tasks use LIFO (stack) ordering for depth-first tree construction.
    The active task's proposed nodes appear as grey/ghost nodes in the
    tree. The user reviews and approves/rejects proposals before the
    next task activates.
    """
    id: str
    description: str
    target_node_id: str = ""          # which tree node this task targets
    status: TaskStatus = "queued"
    parent_task_id: str = ""          # "" if top-level
    proposed_additions: list[str] = field(default_factory=list)   # node IDs
    proposed_removals: list[str] = field(default_factory=list)    # node IDs
    created_at: str = field(default_factory=_now)

    @staticmethod
    def new(description: str, **kwargs) -> Task:
        return Task(id=_short_id(), description=description, **kwargs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "description": self.description,
            "target_node_id": self.target_node_id,
            "status": self.status,
            "parent_task_id": self.parent_task_id,
            "proposed_additions": self.proposed_additions,
            "proposed_removals": self.proposed_removals,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d: dict) -> Task:
        return Task(
            id=d["id"],
            description=d["description"],
            target_node_id=d.get("target_node_id", ""),
            status=d.get("status", "queued"),
            parent_task_id=d.get("parent_task_id", ""),
            proposed_additions=d.get("proposed_additions", []),
            proposed_removals=d.get("proposed_removals", []),
            created_at=d.get("created_at", _now()),
        )


# ─── Errors ──────────────────────────────────────────────────────────────────

class ArchMapError(Exception):
    pass


class ProjectNotInitializedError(ArchMapError):
    def __init__(self, project_path: str):
        super().__init__(f"ArchMap not initialized in '{project_path}'.")


class NotFoundError(ArchMapError):
    pass
