"""
ArchMap HTTP API Server — REST bridge for the UI.
Runs on port 8765. The Vite dev server proxies /api → http://localhost:8765.

Usage:
    conda run -n archmap python api_server.py
    # or inside the env:
    python api_server.py
"""
import asyncio
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

import archmap.architecture as arch_mod
import archmap.mapping as map_mod
import archmap.planning as plan_mod
import archmap.project as proj_mod
import archmap.scanner as scan_mod
from archmap.models import ArchMapError, NotFoundError
from archmap import __version__

_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(title="ArchMap API", version=__version__, docs_url="/api/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _run_sync(fn, *args, **kwargs):
    """Run a blocking function in a thread pool (keeps event loop free)."""
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(_executor, lambda: fn(*args, **kwargs))


# ─── Request models ───────────────────────────────────────────────────────────

class InitReq(BaseModel):
    project_path: str
    name: str = ""

class AddComponentReq(BaseModel):
    project_path: str
    name: str
    description: str = ""
    layer: str = "other"
    tags: List[str] = []
    color: str = "#6366f1"
    confidence: str = "confirmed"
    metadata: dict = {}

class UpdateComponentReq(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    layer: Optional[str] = None
    tags: Optional[List[str]] = None
    color: Optional[str] = None
    confidence: Optional[str] = None

class AddDependencyReq(BaseModel):
    project_path: str
    from_component: str
    to_component: str
    label: str = "uses"
    kind: str = "runtime"

class MapFileReq(BaseModel):
    project_path: str
    file_path: str
    component_id: str

class CreatePlanReq(BaseModel):
    project_path: str
    title: str
    description: str = ""
    component_id: Optional[str] = None
    priority: str = "medium"
    status: str = "todo"
    tags: List[str] = []

class UpdatePlanReq(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    component_id: Optional[str] = None
    tags: Optional[List[str]] = None

class ScanReq(BaseModel):
    project_path: str
    overwrite_auto: bool = False
    depth: int = 2

# Legacy generic tool call (kept for MCP UI compat)
class ToolCall(BaseModel):
    model_config = {"extra": "allow"}


# ─── Health ───────────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok", "version": __version__}


# ─── Project ──────────────────────────────────────────────────────────────────

@app.post("/api/project/init")
async def init_project(req: InitReq):
    try:
        return await _run_sync(proj_mod.init_project, req.project_path, req.name or None)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/project/status")
async def project_status(project_path: str):
    try:
        return await _run_sync(proj_mod.project_status, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Architecture ─────────────────────────────────────────────────────────────

@app.get("/api/architecture")
async def get_architecture(project_path: str):
    try:
        return await _run_sync(arch_mod.get_architecture, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/components")
async def list_components(project_path: str, layer: str = ""):
    try:
        return await _run_sync(arch_mod.list_components, project_path, layer or None)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.post("/api/components")
async def add_component(req: AddComponentReq):
    try:
        return await _run_sync(
            arch_mod.add_component,
            req.project_path, req.name, req.description,
            req.layer, req.tags, req.color, req.confidence, req.metadata,
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/components/{component_id}")
async def get_component(project_path: str, component_id: str):
    try:
        return await _run_sync(arch_mod.get_component, project_path, component_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.patch("/api/components/{component_id}")
async def update_component(component_id: str, project_path: str, req: UpdateComponentReq):
    try:
        return await _run_sync(
            arch_mod.update_component, project_path, component_id,
            **{k: v for k, v in req.model_dump().items() if v is not None}
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/components/{component_id}")
async def delete_component(project_path: str, component_id: str):
    try:
        return await _run_sync(arch_mod.delete_component, project_path, component_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/graph")
async def get_dependency_graph(project_path: str):
    try:
        return await _run_sync(arch_mod.get_dependency_graph, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.post("/api/dependencies")
async def add_dependency(req: AddDependencyReq):
    try:
        return await _run_sync(
            arch_mod.add_dependency,
            req.project_path, req.from_component, req.to_component, req.label, req.kind,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/dependencies/{dep_id}")
async def remove_dependency(project_path: str, dep_id: str):
    try:
        return await _run_sync(arch_mod.remove_dependency, project_path, dep_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Mappings ─────────────────────────────────────────────────────────────────

@app.get("/api/mappings")
async def list_all_mappings(project_path: str):
    try:
        return await _run_sync(map_mod.list_all_mappings, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/mappings/file")
async def get_file_component(project_path: str, file_path: str):
    try:
        return await _run_sync(map_mod.get_file_component, project_path, file_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/mappings/component/{component_id}")
async def list_component_files(project_path: str, component_id: str):
    try:
        return await _run_sync(map_mod.list_component_files, project_path, component_id)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.post("/api/mappings")
async def map_file(req: MapFileReq):
    try:
        return await _run_sync(map_mod.map_file, req.project_path, req.file_path, req.component_id)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/mappings")
async def unmap_file(project_path: str, file_path: str):
    try:
        return await _run_sync(map_mod.unmap_file, project_path, file_path)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Plan ─────────────────────────────────────────────────────────────────────

@app.get("/api/plan")
async def list_plan_items(project_path: str, component_id: str = "", status: str = "", priority: str = ""):
    try:
        return await _run_sync(
            plan_mod.list_plan_items, project_path,
            component_id or None, status or None, priority or None,
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.post("/api/plan")
async def create_plan_item(req: CreatePlanReq):
    try:
        return await _run_sync(
            plan_mod.create_plan_item,
            req.project_path, req.title, req.description,
            req.component_id, req.priority, req.status, req.tags,
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.patch("/api/plan/{item_id}")
async def update_plan_item(item_id: str, project_path: str, req: UpdatePlanReq):
    try:
        return await _run_sync(
            plan_mod.update_plan_item, project_path, item_id,
            **{k: v for k, v in req.model_dump().items() if v is not None}
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/plan/{item_id}")
async def delete_plan_item(project_path: str, item_id: str):
    try:
        return await _run_sync(plan_mod.delete_plan_item, project_path, item_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Scanner ──────────────────────────────────────────────────────────────────

@app.post("/api/scan")
async def scan_project(req: ScanReq):
    """Scan runs in thread pool — can take a few seconds on large projects."""
    try:
        return await _run_sync(
            scan_mod.scan_project,
            req.project_path, req.overwrite_auto, req.depth,
        )
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Legacy generic tool endpoint (backward-compatible) ───────────────────────

@app.post("/api/tools/{tool}")
async def call_tool_legacy(tool: str, body: ToolCall):
    """Generic dispatch kept for backward compat with old UI client."""
    p = body.model_dump()
    try:
        if tool == "project_status":
            return await _run_sync(proj_mod.project_status, p["project_path"])
        if tool == "get_architecture":
            return await _run_sync(arch_mod.get_architecture, p["project_path"])
        if tool == "list_components":
            return await _run_sync(arch_mod.list_components, p["project_path"], p.get("layer") or None)
        if tool == "get_dependency_graph":
            return await _run_sync(arch_mod.get_dependency_graph, p["project_path"])
        if tool == "list_plan_items":
            return await _run_sync(plan_mod.list_plan_items, p["project_path"], p.get("component_id") or None, p.get("status") or None)
        if tool == "update_plan_item":
            kw = {k: v for k, v in p.items() if k not in ("project_path", "item_id") and v is not None}
            return await _run_sync(plan_mod.update_plan_item, p["project_path"], p["item_id"], **kw)
        if tool == "scan_project":
            return await _run_sync(scan_mod.scan_project, p["project_path"], p.get("overwrite_auto", False), int(p.get("depth", 2)))
        raise ValueError(f"Unknown tool: {tool}")
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        reload=True,
        reload_dirs=[str(Path(__file__).parent / "archmap")],
    )
