"""
ArchMap v2 API — minimal FastAPI server for the purpose tree.
"""
from __future__ import annotations
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from archmap.core.models import NotFoundError, ArchMapError
from archmap.core.store import init_project, is_initialized, load_meta, reset_tree
from archmap.tree import (
    get_tree, create_root, add_node, update_node,
    remove_node, move_node, attach_files, detach_file,
    get_context, render_tree, suggest_files, detect_drift,
    list_tasks, get_active_task, create_task, activate_next_task,
    complete_task, reject_task, propose_addition, propose_removal,
    approve_proposal, reject_proposal,
)

app = FastAPI(title="ArchMap v2", version="2.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _path(project_path: str | None) -> str:
    if not project_path:
        raise HTTPException(400, "project_path is required")
    return project_path


# ─── Request models ──────────────────────────────────────────────────────────

class InitReq(BaseModel):
    project_path: str
    name: str = ""

class CreateRootReq(BaseModel):
    project_path: str
    name: str
    description: str = ""

class AddNodeReq(BaseModel):
    project_path: str
    parent_id: str
    name: str
    description: str = ""

class UpdateNodeReq(BaseModel):
    project_path: str
    node_id: str
    name: str | None = None
    description: str | None = None
    user_notes: str | None = None

class MoveNodeReq(BaseModel):
    project_path: str
    node_id: str
    new_parent_id: str

class AttachFilesReq(BaseModel):
    project_path: str
    node_id: str
    file_paths: list[str]

class DetachFileReq(BaseModel):
    project_path: str
    node_id: str
    file_path: str

class CreateTaskReq(BaseModel):
    project_path: str
    description: str
    target_node_id: str = ""
    parent_task_id: str = ""

class ProposeAdditionReq(BaseModel):
    project_path: str
    task_id: str
    parent_id: str
    name: str
    description: str = ""
    files: list[str] = []

class ProposeRemovalReq(BaseModel):
    project_path: str
    task_id: str
    node_id: str


# ─── Project ─────────────────────────────────────────────────────────────────

@app.post("/api/init")
def api_init(req: InitReq):
    meta = init_project(req.project_path, req.name)
    return {"ok": True, "meta": meta}


@app.get("/api/status")
def api_status(project_path: str):
    p = _path(project_path)
    if not is_initialized(p):
        return {"initialized": False}
    meta = load_meta(p)
    tree = get_tree(p)
    node_count = sum(1 for _ in tree.walk()) if tree else 0
    confirmed = sum(1 for n in tree.walk() if n.status == "confirmed") if tree else 0
    return {
        "initialized": True,
        "name": meta.get("name", ""),
        "node_count": node_count,
        "confirmed": confirmed,
        "has_tree": tree is not None,
    }


# ─── Tree ────────────────────────────────────────────────────────────────────

@app.get("/api/tree")
def api_get_tree(project_path: str):
    tree = get_tree(_path(project_path))
    if tree is None:
        return None
    return tree.to_dict()


@app.get("/api/tree/render")
def api_render_tree(project_path: str, max_depth: int = 2):
    return {"text": render_tree(_path(project_path), max_depth)}


@app.post("/api/tree/root")
def api_create_root(req: CreateRootReq):
    try:
        root = create_root(req.project_path, req.name, req.description)
        return root.to_dict()
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.post("/api/tree/reset")
def api_reset_tree(project_path: str):
    reset_tree(_path(project_path))
    return {"ok": True}


# ─── Nodes ───────────────────────────────────────────────────────────────────

@app.post("/api/node")
def api_add_node(req: AddNodeReq):
    try:
        node = add_node(req.project_path, req.parent_id, req.name, req.description)
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.patch("/api/node")
def api_update_node(req: UpdateNodeReq):
    try:
        node = update_node(
            req.project_path, req.node_id,
            name=req.name, description=req.description, user_notes=req.user_notes,
        )
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/node")
def api_remove_node(project_path: str, node_id: str):
    try:
        name = remove_node(_path(project_path), node_id)
        return {"ok": True, "removed": name}
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))


@app.post("/api/node/move")
def api_move_node(req: MoveNodeReq):
    try:
        node = move_node(req.project_path, req.node_id, req.new_parent_id)
        return node.to_dict()
    except (NotFoundError, ValueError) as e:
        raise HTTPException(400, str(e))


# ─── Files ───────────────────────────────────────────────────────────────────

@app.post("/api/node/files")
def api_attach_files(req: AttachFilesReq):
    try:
        node = attach_files(req.project_path, req.node_id, req.file_paths)
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.delete("/api/node/file")
def api_detach_file(req: DetachFileReq):
    try:
        node = detach_file(req.project_path, req.node_id, req.file_path)
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.get("/api/suggest-files")
def api_suggest_files(project_path: str):
    return {"files": suggest_files(_path(project_path))}


@app.get("/api/drift")
def api_detect_drift(project_path: str):
    return {"drift": detect_drift(_path(project_path))}


# ─── Context (for agent) ────────────────────────────────────────────────────

@app.get("/api/context")
def api_get_context(project_path: str, node_id: str):
    try:
        return {"text": get_context(_path(project_path), node_id)}
    except NotFoundError as e:
        raise HTTPException(404, str(e))


# ─── Tasks ───────────────────────────────────────────────────────────────────

@app.get("/api/tasks")
def api_list_tasks(project_path: str):
    tasks = list_tasks(_path(project_path))
    return [t.to_dict() for t in tasks]


@app.get("/api/task/active")
def api_active_task(project_path: str):
    task = get_active_task(_path(project_path))
    return task.to_dict() if task else None


@app.post("/api/task")
def api_create_task(req: CreateTaskReq):
    task = create_task(req.project_path, req.description, req.target_node_id, req.parent_task_id)
    return task.to_dict()


@app.post("/api/task/activate-next")
def api_activate_next(project_path: str):
    task = activate_next_task(_path(project_path))
    return task.to_dict() if task else None


@app.post("/api/task/complete")
def api_complete_task(project_path: str, task_id: str, auto_advance: bool = False):
    try:
        task = complete_task(_path(project_path), task_id, auto_advance)
        return task.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/task/reject")
def api_reject_task(project_path: str, task_id: str, auto_advance: bool = False):
    try:
        task = reject_task(_path(project_path), task_id, auto_advance)
        return task.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


# ─── Task proposals ─────────────────────────────────────────────────────────

@app.post("/api/task/propose")
def api_propose_addition(req: ProposeAdditionReq):
    try:
        node = propose_addition(
            req.project_path, req.task_id, req.parent_id,
            req.name, req.description, req.files or None,
        )
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/task/propose-removal")
def api_propose_removal(req: ProposeRemovalReq):
    try:
        node = propose_removal(req.project_path, req.task_id, req.node_id)
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/node/approve")
def api_approve_proposal(project_path: str, node_id: str):
    try:
        node = approve_proposal(_path(project_path), node_id)
        return node.to_dict()
    except NotFoundError as e:
        raise HTTPException(404, str(e))


@app.post("/api/node/reject-proposal")
def api_reject_proposal(project_path: str, node_id: str):
    try:
        name = reject_proposal(_path(project_path), node_id)
        return {"ok": True, "name": name}
    except NotFoundError as e:
        raise HTTPException(404, str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8765)
