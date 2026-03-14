"""
Plan item CRUD.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from archmap.models import PlanItem, NotFoundError
from archmap.store import load_plan, mutate_plan


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def list_plan_items(
    project_path: str,
    component_id: Optional[str] = None,
    status: Optional[str] = None,
    priority: Optional[str] = None,
) -> list[dict]:
    data = load_plan(project_path)
    items = data.get("items", [])
    if component_id is not None:
        items = [i for i in items if i.get("component_id") == component_id]
    if status:
        items = [i for i in items if i.get("status") == status]
    if priority:
        items = [i for i in items if i.get("priority") == priority]
    return items


def create_plan_item(
    project_path: str,
    title: str,
    description: str = "",
    component_id: Optional[str] = None,
    priority: str = "medium",
    tags: Optional[list[str]] = None,
    metadata: Optional[dict] = None,
) -> dict:
    item = PlanItem.new(
        title=title,
        description=description,
        component_id=component_id,
        priority=priority,
        tags=tags or [],
        metadata=metadata or {},
    )
    item_dict = item.to_dict()

    def _mutate(data):
        data.setdefault("items", []).append(item_dict)

    mutate_plan(project_path, _mutate)
    return item_dict


def update_plan_item(
    project_path: str,
    item_id: str,
    **kwargs,
) -> dict:
    updatable = {"title", "description", "status", "priority", "component_id", "tags", "metadata"}
    result: dict = {}

    def _mutate(data):
        nonlocal result
        for item in data.get("items", []):
            if item["id"] == item_id:
                for k, v in kwargs.items():
                    if k in updatable and v is not None:
                        item[k] = v
                item["updated_at"] = _ts()
                result = item
                return
        raise NotFoundError(f"Plan item not found: {item_id}")

    mutate_plan(project_path, _mutate)
    return result


def delete_plan_item(project_path: str, item_id: str) -> str:
    def _mutate(data):
        before = len(data.get("items", []))
        data["items"] = [i for i in data.get("items", []) if i["id"] != item_id]
        if len(data["items"]) == before:
            raise NotFoundError(f"Plan item not found: {item_id}")

    mutate_plan(project_path, _mutate)
    return "deleted"
