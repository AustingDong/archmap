"""
ArchMap HTTP API Server — REST bridge for the UI.
Runs on port 8765. The Vite dev server proxies /api → http://localhost:8765.

Usage:
    conda run -n archmap python api_server.py
    # or inside the env:
    python api_server.py
"""
import asyncio
import json
import sys
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncGenerator

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Optional, List
import uvicorn

import archmap.architecture as arch_mod
import archmap.inference as infer_mod
import archmap.mapping as map_mod
import archmap.metrics as metrics_mod
import archmap.planning as plan_mod
import archmap.project as proj_mod
import archmap.scanner as scan_mod
import archmap.symbols as symbols_mod
from archmap.models import ArchMapError, NotFoundError
from archmap import __version__

_executor = ThreadPoolExecutor(max_workers=4)

app = FastAPI(title="ArchMap API", version=__version__, docs_url="/api/docs")

# ─── SSE pub/sub ──────────────────────────────────────────────────────────────

_subscribers: set[asyncio.Queue] = set()

def _notify(event: str, data: dict | None = None) -> None:
    """Broadcast an SSE event to all connected clients (fire-and-forget)."""
    payload = json.dumps({"event": event, **(data or {})})
    for q in list(_subscribers):
        try:
            q.put_nowait(payload)
        except asyncio.QueueFull:
            pass  # slow client — drop the event

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

class AnnotateFileReq(BaseModel):
    project_path: str
    file_path: str
    description: str = ""
    functions: List[str] = []
    language: str = ""

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


# ─── Server-Sent Events ───────────────────────────────────────────────────────

@app.get("/api/events")
async def events(request: Request):
    """
    SSE stream. Clients receive push events instead of polling.
    Events: plan_changed, mappings_changed, architecture_changed
    Heartbeat every 15s to keep the connection alive through proxies.
    """
    q: asyncio.Queue = asyncio.Queue(maxsize=64)
    _subscribers.add(q)

    async def stream() -> AsyncGenerator[str, None]:
        try:
            yield "data: {\"event\": \"connected\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    payload = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {payload}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"  # keeps connection alive
        finally:
            _subscribers.discard(q)

    return StreamingResponse(stream(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    })


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

@app.patch("/api/mappings")
async def annotate_file(req: AnnotateFileReq):
    metadata: dict = {}
    if req.description:
        metadata["description"] = req.description
    if req.functions:
        metadata["functions"] = req.functions
    if req.language:
        metadata["language"] = req.language
    try:
        result = await _run_sync(map_mod.update_file_metadata, req.project_path, req.file_path, metadata)
        _notify("mappings_changed")
        return result
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.post("/api/mappings")
async def map_file(req: MapFileReq):
    try:
        result = await _run_sync(map_mod.map_file, req.project_path, req.file_path, req.component_id)
        _notify("mappings_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/mappings")
async def unmap_file(project_path: str, file_path: str):
    try:
        result = await _run_sync(map_mod.unmap_file, project_path, file_path)
        _notify("mappings_changed")
        return result
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
        result = await _run_sync(
            plan_mod.create_plan_item,
            req.project_path, req.title, req.description,
            req.component_id, req.priority, req.status, req.tags,
        )
        _notify("plan_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.patch("/api/plan/{item_id}")
async def update_plan_item(item_id: str, project_path: str, req: UpdatePlanReq):
    try:
        result = await _run_sync(
            plan_mod.update_plan_item, project_path, item_id,
            **{k: v for k, v in req.model_dump().items() if v is not None}
        )
        _notify("plan_changed")
        return result
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.delete("/api/plan/{item_id}")
async def delete_plan_item(project_path: str, item_id: str):
    try:
        result = await _run_sync(plan_mod.delete_plan_item, project_path, item_id)
        _notify("plan_changed")
        return result
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Inference ────────────────────────────────────────────────────────────────

@app.post("/api/infer/dependencies")
async def infer_dependencies(project_path: str, overwrite_auto: bool = False):
    try:
        result = await _run_sync(infer_mod.infer_dependencies, project_path, overwrite_auto)
        if result["added"] > 0:
            _notify("architecture_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.post("/api/dependencies/{dep_id}/confirm")
async def confirm_dependency(dep_id: str, project_path: str):
    try:
        result = await _run_sync(infer_mod.confirm_dependency, project_path, dep_id)
        _notify("architecture_changed")
        return result
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


# ─── Metrics ──────────────────────────────────────────────────────────────────

@app.get("/api/metrics/component/{component_id}")
async def get_component_metrics(component_id: str, project_path: str):
    try:
        return await _run_sync(metrics_mod.get_component_metrics, project_path, component_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Impact analysis ──────────────────────────────────────────────────────────

@app.get("/api/impact/{component_id}")
async def get_component_impact(component_id: str, project_path: str):
    """
    BFS impact analysis: given a component, return:
    - upstream: components that depend ON this component (would break if it changes)
    - downstream: components this component depends ON
    - cycles: any dependency cycle involving this component
    - is_leaf: no outgoing deps
    - is_root: no incoming deps
    """
    try:
        arch = await _run_sync(arch_mod.get_architecture, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

    deps = arch.get("dependencies", [])
    comp_ids = {c["id"] for c in arch.get("components", [])}

    if component_id not in comp_ids:
        raise HTTPException(404, f"Component {component_id!r} not found")

    # Build adjacency maps
    outgoing: dict[str, list[str]] = {cid: [] for cid in comp_ids}  # from → [to]
    incoming: dict[str, list[str]] = {cid: [] for cid in comp_ids}  # to → [from]
    for d in deps:
        f, t = d["from_component"], d["to_component"]
        if f in outgoing:
            outgoing[f].append(t)
        if t in incoming:
            incoming[t].append(f)

    def bfs(adjacency: dict[str, list[str]], start: str) -> set[str]:
        visited: set[str] = set()
        queue = [start]
        while queue:
            cur = queue.pop(0)
            for nxt in adjacency.get(cur, []):
                if nxt not in visited and nxt != start:
                    visited.add(nxt)
                    queue.append(nxt)
        return visited

    downstream = bfs(outgoing, component_id)   # this → ... (what it depends on)
    upstream   = bfs(incoming, component_id)   # ... → this (what depends on it)

    # Cycle detection: downstream nodes that also have a path back
    cycles = [cid for cid in downstream if component_id in bfs(outgoing, cid)]

    return {
        "component_id": component_id,
        "upstream":    sorted(upstream),     # will break if this component changes
        "downstream":  sorted(downstream),   # this component depends on these
        "cycles":      sorted(cycles),
        "is_leaf":     len(outgoing.get(component_id, [])) == 0,
        "is_root":     len(incoming.get(component_id, [])) == 0,
        "impact_score": len(upstream),       # how many components would be affected
    }


# ─── File content + symbol extraction ────────────────────────────────────────

@app.get("/api/file")
async def get_file_content(project_path: str, file_path: str):
    """Return raw file content as text."""
    try:
        return await _run_sync(symbols_mod.get_file_content, project_path, file_path)
    except FileNotFoundError as e:
        raise HTTPException(404, str(e))

@app.get("/api/file/symbol")
async def get_file_symbol(project_path: str, file_path: str, symbol: str):
    """Extract source code of a named function or class from a file."""
    return await _run_sync(symbols_mod.extract_symbol, project_path, file_path, symbol)


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
