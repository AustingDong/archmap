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
import archmap.completeness as completeness_mod
import archmap.navigation as navigation_mod
import archmap.audit as audit_mod
import archmap.cognition as cognition_mod
import archmap.context as ctx_mod
import archmap.contracts as contracts_mod
import archmap.decisions as decisions_mod
import archmap.impact as impact_mod
import archmap.inference as infer_mod
import archmap.intelligence as intel_mod
import archmap.mapping as map_mod
import archmap.metrics as metrics_mod
import archmap.quality as quality_mod
import archmap.migration as migration_mod
import archmap.planning as plan_mod
import archmap.project as proj_mod
import archmap.rules as rules_mod
import archmap.scanner as scan_mod
import archmap.session as session_mod
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
    # Multi-level hierarchy
    level: int = 4
    parent_id: str = ""
    protocol: str = ""
    port: Optional[int] = None
    deploy_unit: bool = False
    public_api: List[str] = []
    data_owned: List[str] = []
    stability: str = "stable"

class UpdateComponentReq(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    layer: Optional[str] = None
    tags: Optional[List[str]] = None
    color: Optional[str] = None
    confidence: Optional[str] = None
    owner: Optional[str] = None
    tier: Optional[str] = None
    onboarding_notes: Optional[str] = None
    runbook_url: Optional[str] = None
    slack_channel: Optional[str] = None
    # Multi-level hierarchy
    level: Optional[int] = None
    parent_id: Optional[str] = None
    protocol: Optional[str] = None
    port: Optional[int] = None
    deploy_unit: Optional[bool] = None
    public_api: Optional[List[str]] = None
    data_owned: Optional[List[str]] = None
    stability: Optional[str] = None

class AnnotateDependencyReq(BaseModel):
    project_path: str
    dependency_id: str
    edge_type: Optional[str] = None
    edge_level: Optional[str] = None
    crosses_boundary: Optional[bool] = None
    async_flag: Optional[bool] = None
    direction: Optional[str] = None
    interface_points: Optional[List[str]] = None
    payload_types: Optional[List[str]] = None
    stability: Optional[str] = None
    label: Optional[str] = None

class DeclareContractReq(BaseModel):
    project_path: str
    node_id: str
    node_level: int = 4
    commands: List[dict] = []
    queries: List[dict] = []
    events_emitted: List[dict] = []
    events_consumed: List[dict] = []
    data_owned: List[dict] = []
    data_read: List[dict] = []
    api_spec_url: str = ""
    sla: str = ""

class PromoteContractReq(BaseModel):
    project_path: str
    component_id: str
    symbol_names: List[str]

class RemapFilesReq(BaseModel):
    project_path: str
    file_paths: List[str]
    target_component_id: str

class MigrateReq(BaseModel):
    project_path: str

class AddDecisionReq(BaseModel):
    project_path: str
    component_id: str
    title: str
    context: str = ""
    decision: str = ""
    consequences: str = ""
    alternatives: str = ""
    status: str = "proposed"

class UpdateDecisionReq(BaseModel):
    title: Optional[str] = None
    status: Optional[str] = None
    context: Optional[str] = None
    decision: Optional[str] = None
    consequences: Optional[str] = None
    alternatives: Optional[str] = None
    superseded_by: Optional[str] = None

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

class BulkMapReq(BaseModel):
    project_path: str
    mappings: List[dict]

class PostEditSyncReq(BaseModel):
    project_path: str
    file_paths: List[str]
    reinfer_dependencies: bool = False

class AddRuleReq(BaseModel):
    project_path: str
    rule_type: str
    from_layer: str = ""
    to_layer: str = ""
    message: str = ""

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

@app.post("/api/project/reset")
async def reset_graph(project_path: str):
    """Wipe architecture + mappings back to empty. meta.json and plan.json are preserved."""
    try:
        from archmap.store import reset_graph as _reset
        return await _run_sync(_reset, project_path)
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
            req.layer, req.tags, req.color, req.confidence,
            metadata=req.metadata or {},
            level=req.level, parent_id=req.parent_id,
            protocol=req.protocol, port=req.port, deploy_unit=req.deploy_unit,
            public_api=req.public_api, data_owned=req.data_owned, stability=req.stability,
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
            lambda: plan_mod.list_plan_items(
                project_path,
                component_id=component_id or None,
                status=status or None,
                priority=priority or None,
            )
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


@app.get("/api/quality/{component_id}")
async def get_code_quality(
    component_id: str,
    project_path: str,
    include_types: bool = False,
):
    """Lint + type-check + complexity report for a component's source files."""
    try:
        return await _run_sync(
            quality_mod.get_quality_report, project_path, component_id,
            include_types=include_types,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Impact analysis ──────────────────────────────────────────────────────────

@app.get("/api/impact/{component_id}")
async def get_component_impact(component_id: str, project_path: str):
    try:
        return await _run_sync(impact_mod.get_component_impact, project_path, component_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Symbol sync + search + coding context ────────────────────────────────────

class SyncSymbolsReq(BaseModel):
    project_path: str
    file_path: str

@app.post("/api/mappings/sync-symbols")
async def sync_file_symbols(req: SyncSymbolsReq):
    """Scan the actual file, auto-extract all top-level symbols, and update the mapping metadata."""
    try:
        extracted = await _run_sync(symbols_mod.extract_all_symbols, req.project_path, req.file_path)
        metadata: dict = {
            "functions": extracted["symbols"],
            "symbol_details": extracted.get("details", []),
        }
        if extracted["language"]:
            metadata["language"] = extracted["language"]
        result = await _run_sync(map_mod.update_file_metadata, req.project_path, req.file_path, metadata)
        _notify("mappings_changed")
        return result
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/symbols/search")
async def search_symbol(project_path: str, q: str = ""):
    """Search for a symbol name across all mapped files. Returns [{symbol, file_path, component_id}]."""
    try:
        mappings = await _run_sync(map_mod.list_all_mappings, project_path)
        q_lower = q.lower()
        results = []
        for rec in mappings:
            for fn in rec.get("metadata", {}).get("functions", []):
                if not q or q_lower in fn.lower():
                    results.append({
                        "symbol": fn,
                        "file_path": rec["file_path"],
                        "component_id": rec["component_id"],
                    })
        return results
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/context/{component_id}")
async def get_context(component_id: str, project_path: str, task: str = "", depth: str = "implement"):
    """Unified agent context. depth: orient|plan|implement (controls response size)."""
    try:
        return await _run_sync(ctx_mod.get_context, project_path, component_id, task, depth)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/coding-context/{component_id}")
async def get_coding_context(component_id: str, project_path: str):
    """
    Return all information an agent needs before editing code in a component:
    component details, mapped files with symbols, related dependencies (with names),
    and open plan items.
    """
    try:
        comp = await _run_sync(arch_mod.get_component, project_path, component_id)
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

    try:
        files = await _run_sync(map_mod.list_component_files, project_path, component_id)
        arch = await _run_sync(arch_mod.get_architecture, project_path)
        items = await _run_sync(lambda: plan_mod.list_plan_items(project_path, component_id=component_id))
    except ArchMapError as e:
        raise HTTPException(400, str(e))

    # Build component name lookup
    name_map = {c["id"]: c["name"] for c in arch.get("components", [])}

    # Filter deps involving this component and enrich with names
    enriched_deps = []
    for d in arch.get("dependencies", []):
        if d["from_component"] == component_id or d["to_component"] == component_id:
            enriched_deps.append({
                **d,
                "from_name": name_map.get(d["from_component"], d["from_component"]),
                "to_name": name_map.get(d["to_component"], d["to_component"]),
            })

    return {
        "component": comp,
        "files": files,
        "dependencies": enriched_deps,
        "plan_items": items,
    }


# ─── Architecture intelligence ────────────────────────────────────────────────

@app.get("/api/architecture/describe")
async def describe_architecture(project_path: str, level: Optional[int] = None):
    """Markdown overview of the architecture. level=1-5 filters to that zoom level."""
    try:
        text = await _run_sync(intel_mod.describe_architecture, project_path, level)
        return {"text": text}
    except ArchMapError as e:
        raise HTTPException(400, str(e))

@app.get("/api/architecture/search")
async def find_related(project_path: str, q: str = ""):
    """Full-text search across all graph entities (components, files, symbols). Returns ranked results."""
    try:
        return await _run_sync(intel_mod.find_related, project_path, q)
    except ArchMapError as e:
        raise HTTPException(400, str(e))

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


# ─── Bulk mapping ─────────────────────────────────────────────────────────────

@app.post("/api/mappings/bulk")
async def bulk_map(req: BulkMapReq):
    """Map multiple files to components in a single request."""
    try:
        result = await _run_sync(map_mod.bulk_map, req.project_path, req.mappings)
        _notify("mappings_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.post("/api/mappings/cleanup")
async def cleanup_non_source_mappings(project_path: str):
    """
    Remove mapped files that are not source code (docs, config, compiled artefacts).
    Safe to run at any time — only non-source entries are removed.
    """
    try:
        result = await _run_sync(map_mod.cleanup_non_source_mappings, project_path)
        _notify("mappings_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Post-edit sync ───────────────────────────────────────────────────────────

@app.post("/api/sync")
async def post_edit_sync(req: PostEditSyncReq):
    """
    Sync symbol metadata for edited files. Call after editing source files.
    Returns {synced, unmapped, errors, deps_added}.
    """
    def _do_sync():
        synced, unmapped, errors = [], [], {}
        for fp in req.file_paths:
            try:
                mapping = map_mod.get_file_component(req.project_path, fp)
                if not mapping:
                    unmapped.append(fp)
                    continue
                extracted = symbols_mod.extract_all_symbols(req.project_path, fp)
                metadata: dict = {
                    "functions": extracted["symbols"],
                    "symbol_details": extracted.get("details", []),
                }
                if extracted["language"]:
                    metadata["language"] = extracted["language"]
                map_mod.update_file_metadata(req.project_path, fp, metadata)
                synced.append(fp)
            except Exception as e:
                errors[fp] = str(e)
        deps_added = 0
        if req.reinfer_dependencies:
            try:
                result = infer_mod.infer_dependencies(req.project_path, overwrite_auto=False)
                deps_added = result.get("added", 0)
            except Exception as e:
                errors["__infer__"] = str(e)
        return {"synced": synced, "unmapped": unmapped, "errors": errors, "deps_added": deps_added}

    try:
        result = await _run_sync(_do_sync)
        if result["synced"]:
            _notify("mappings_changed")
        if result["deps_added"]:
            _notify("architecture_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Cycle detection ──────────────────────────────────────────────────────────

@app.get("/api/cycles")
async def list_cycles(project_path: str):
    """Find all dependency cycles in the architecture."""
    try:
        arch = await _run_sync(arch_mod.get_architecture, project_path)
        components = arch.get("components", [])
        deps = arch.get("dependencies", [])
        name_map = {c["id"]: c["name"] for c in components}
        layer_map = {c["id"]: c.get("layer", "") for c in components}

        outgoing: dict = {c["id"]: [] for c in components}
        for d in deps:
            if d["from_component"] in outgoing:
                outgoing[d["from_component"]].append(d["to_component"])

        def bfs(start: str) -> set:
            visited: set = set()
            queue = [start]
            while queue:
                cur = queue.pop(0)
                for nxt in outgoing.get(cur, []):
                    if nxt not in visited and nxt != start:
                        visited.add(nxt)
                        queue.append(nxt)
            return visited

        cycles = []
        seen_pairs: set = set()
        for comp in components:
            cid = comp["id"]
            downstream = bfs(cid)
            cycle_partners = [d for d in downstream if cid in bfs(d)]
            if cycle_partners:
                for partner in cycle_partners:
                    pair = tuple(sorted([cid, partner]))
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        cycles.append({
                            "component_id": cid,
                            "component_name": name_map.get(cid, cid),
                            "layer": layer_map.get(cid, ""),
                            "cycles_with": [{"component_id": p, "component_name": name_map.get(p, p), "layer": layer_map.get(p, "")} for p in cycle_partners],
                        })

        return {"cycle_count": len(cycles), "cycles": cycles}
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Architectural rules ──────────────────────────────────────────────────────

@app.get("/api/rules")
async def list_architecture_rules(project_path: str):
    """List all configured architectural rules."""
    try:
        return await _run_sync(rules_mod.load_rules, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.post("/api/rules")
async def add_architecture_rule(req: AddRuleReq):
    """Add an architectural constraint rule (no_dep, no_cycles, required_dep)."""
    try:
        kwargs: dict = {}
        if req.from_layer: kwargs["from_layer"] = req.from_layer
        if req.to_layer:   kwargs["to_layer"]   = req.to_layer
        if req.message:    kwargs["message"]     = req.message
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor, lambda: rules_mod.add_rule(req.project_path, req.rule_type, **kwargs)
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.delete("/api/rules/{rule_id}")
async def delete_architecture_rule(rule_id: str, project_path: str):
    """Remove an architectural rule by ID."""
    try:
        deleted = await _run_sync(rules_mod.delete_rule, project_path, rule_id)
        if not deleted:
            raise HTTPException(404, f"Rule {rule_id} not found")
        return {"deleted": True, "rule_id": rule_id}
    except HTTPException:
        raise
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/validate")
async def validate_architecture(project_path: str):
    """Check all dependencies against configured architectural rules."""
    try:
        return await _run_sync(rules_mod.validate_architecture, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Audit log ────────────────────────────────────────────────────────────────

@app.get("/api/audit")
async def get_audit_log(
    project_path: str,
    last_n: int = 50,
    entity_type: str = "",
    entity_id: str = "",
    actor: str = "",
):
    """Return recent architecture change history, newest first."""
    try:
        return await _run_sync(
            audit_mod.get_audit_log,
            project_path,
            last_n=last_n,
            entity_type=entity_type,
            entity_id=entity_id,
            actor=actor,
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Agent cognition queries ──────────────────────────────────────────────────

@app.get("/api/who-owns")
async def who_owns(project_path: str, symbol_name: str):
    """Find which file and component owns a named symbol."""
    try:
        return await _run_sync(cognition_mod.who_owns_symbol, project_path, symbol_name)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/component-interface/{component_id}")
async def get_component_interface(component_id: str, project_path: str):
    """Return the public interface of a component: exports, upstreams, imports."""
    try:
        result = await _run_sync(cognition_mod.get_component_interface, project_path, component_id)
        if "error" in result:
            raise HTTPException(404, result["error"])
        return result
    except HTTPException:
        raise
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/integrity")
async def check_integrity(project_path: str):
    """Health check: stale files, missing files, dangling deps, unmapped files, orphan plans."""
    try:
        return await _run_sync(cognition_mod.check_integrity, project_path)
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
            return await _run_sync(lambda: plan_mod.list_plan_items(p["project_path"], component_id=p.get("component_id") or None, status=p.get("status") or None))
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


# ─── Decisions (ADRs) ─────────────────────────────────────────────────────────

@app.get("/api/decisions")
async def list_decisions(project_path: str, component_id: str = "", status: str = ""):
    return await _run_sync(decisions_mod.list_decisions, project_path,
                           component_id, status)

@app.get("/api/decisions/{decision_id}")
async def get_decision(project_path: str, decision_id: str):
    try:
        return await _run_sync(decisions_mod.get_decision, project_path, decision_id)
    except KeyError as e:
        raise HTTPException(404, str(e))

@app.post("/api/decisions")
async def add_decision(req: AddDecisionReq):
    return await _run_sync(
        decisions_mod.add_decision,
        req.project_path, req.component_id, req.title,
        req.context, req.decision, req.consequences, req.alternatives,
        None, req.status,
    )

@app.patch("/api/decisions/{decision_id}")
async def update_decision(decision_id: str, project_path: str, req: UpdateDecisionReq):
    try:
        return await _run_sync(
            decisions_mod.update_decision, project_path, decision_id,
            **{k: v for k, v in req.model_dump().items() if v is not None}
        )
    except KeyError as e:
        raise HTTPException(404, str(e))

@app.delete("/api/decisions/{decision_id}")
async def delete_decision(project_path: str, decision_id: str):
    return await _run_sync(decisions_mod.delete_decision, project_path, decision_id)


# ─── Collaboration sessions ────────────────────────────────────────────────────

@app.get("/api/sessions")
async def list_active_work(project_path: str):
    """Return all active work claims — used by the UI collaboration feed."""
    return await _run_sync(session_mod.list_active_work, project_path)


# ─── Multi-level graph — new endpoints ───────────────────────────────────────

@app.get("/api/graph/domain-map")
async def get_domain_map(project_path: str):
    """L1/L2 orientation: system + domains + cross-domain edges. Start here."""
    try:
        return await _run_sync(ctx_mod.get_domain_map, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/graph/node/{node_id}")
async def describe_node(node_id: str, project_path: str, show_files: bool = False):
    """Drill-down view of any node: metadata, children, contract, edges."""
    try:
        return await _run_sync(ctx_mod.describe_node, project_path, node_id, show_files)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/graph/children/{parent_id}")
async def list_children(parent_id: str, project_path: str):
    """List direct child nodes of a parent."""
    try:
        return await _run_sync(arch_mod.list_children, project_path, parent_id)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/work-context/{node_id}")
async def get_work_context(node_id: str, project_path: str, task: str = ""):
    """Scope-isolated context: full detail for owned files + contract-only for consumed nodes."""
    try:
        return await _run_sync(ctx_mod.get_work_context, project_path, node_id, task)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Contracts ────────────────────────────────────────────────────────────────

@app.get("/api/contracts")
async def list_contracts(project_path: str, node_level: Optional[int] = None):
    """List all declared contracts, optionally filtered by level."""
    try:
        return await _run_sync(contracts_mod.list_contracts, project_path, node_level)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/contracts/{node_id}")
async def get_contract(node_id: str, project_path: str):
    """Get the declared contract for a node."""
    try:
        return await _run_sync(contracts_mod.get_contract, project_path, node_id)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.post("/api/contracts")
async def declare_contract(req: DeclareContractReq):
    """Declare or replace the contract for a node."""
    try:
        return await _run_sync(
            contracts_mod.declare_contract,
            req.project_path, req.node_id, req.node_level,
            req.commands, req.queries,
            req.events_emitted, req.events_consumed,
            req.data_owned, req.data_read,
            req.api_spec_url, req.sla,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/contracts/{node_id}/check-break")
async def check_contract_break(
    node_id: str, project_path: str,
    operation_name: str = "",
    new_input_type: str = "",
    new_output_type: str = "",
):
    """Check if changing an operation would break the declared contract."""
    try:
        return await _run_sync(
            contracts_mod.check_contract_break,
            project_path, node_id, operation_name, new_input_type, new_output_type,
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Dependency annotation ────────────────────────────────────────────────────

@app.patch("/api/dependencies/{dep_id}/annotate")
async def annotate_dependency(dep_id: str, req: AnnotateDependencyReq):
    """Enrich a dependency edge with semantic type, interface_points, payload_types."""
    try:
        return await _run_sync(
            arch_mod.annotate_dependency,
            req.project_path, dep_id,
            edge_type=req.edge_type, edge_level=req.edge_level,
            crosses_boundary=req.crosses_boundary, async_flag=req.async_flag,
            direction=req.direction, interface_points=req.interface_points,
            payload_types=req.payload_types, stability=req.stability, label=req.label,
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Public API management ────────────────────────────────────────────────────

@app.post("/api/components/{component_id}/promote")
async def promote_to_contract(component_id: str, req: PromoteContractReq):
    """Mark symbols as stable public API for a component."""
    try:
        return await _run_sync(
            arch_mod.promote_to_contract, req.project_path, component_id, req.symbol_names
        )
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── File remapping ───────────────────────────────────────────────────────────

@app.post("/api/mappings/remap")
async def remap_files(req: RemapFilesReq):
    """Move files from one component to another (used when splitting components)."""
    try:
        result = await _run_sync(
            arch_mod.remap_files_to_node,
            req.project_path, req.file_paths, req.target_component_id,
        )
        _notify("mappings_changed")
        return result
    except NotFoundError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Migration ────────────────────────────────────────────────────────────────

@app.post("/api/migrate/multilevel")
async def migrate_multilevel(req: MigrateReq):
    """
    One-shot migration: restructure the flat graph into a 5-level hierarchy.
    Creates system/domain nodes, promotes existing components, splits Core Engine,
    annotates edges with semantic types, declares contracts. Safe to re-run.
    """
    try:
        result = await _run_sync(migration_mod.bootstrap_multilevel_graph, req.project_path)
        _notify("architecture_changed")
        return result
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Hierarchical task endpoints ─────────────────────────────────────────────

@app.post("/api/tasks")
async def api_add_task(body: dict):
    """Create a task (root or child). Body: title, description, component_id, parent_task_id, priority, created_by, expects, tags."""
    try:
        project_path = body.get("project_path", "")
        return await _run_sync(
            plan_mod.add_task,
            project_path,
            title=body.get("title", ""),
            description=body.get("description", ""),
            component_id=body.get("component_id") or None,
            parent_task_id=body.get("parent_task_id") or None,
            priority=body.get("priority", "medium"),
            created_by=body.get("created_by", "user"),
            expects=body.get("expects"),
            tags=body.get("tags"),
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.post("/api/tasks/{task_id}/decompose")
async def api_decompose_task(task_id: str, body: dict):
    """Decompose a task into subtasks. Body: project_path, subtasks: [...], created_by."""
    try:
        project_path = body.get("project_path", "")
        return await _run_sync(
            plan_mod.decompose_task,
            project_path, task_id,
            body.get("subtasks", []),
            body.get("created_by", "user"),
        )
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.post("/api/tasks/{task_id}/complete")
async def api_complete_task(task_id: str, body: dict):
    """Complete a task and propagate progress. Body: project_path, completed_by, note."""
    try:
        project_path = body.get("project_path", "")
        return await _run_sync(
            plan_mod.complete_task,
            project_path, task_id,
            body.get("completed_by", "user"),
            body.get("note", ""),
        )
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks/{task_id}/tree")
async def api_get_task_tree(task_id: str, project_path: str):
    """Return task and all descendants as a nested tree."""
    try:
        return await _run_sync(plan_mod.get_task_tree, project_path, task_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks/{task_id}/drift")
async def api_check_task_drift(task_id: str, project_path: str):
    """Compare task expects against current graph state."""
    try:
        return await _run_sync(plan_mod.check_task_drift, project_path, task_id)
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/tasks")
async def api_list_tasks(
    project_path: str,
    component_id: str = "",
    parent_task_id: str = "_root_",
    status: str = "",
    priority: str = "",
    include_subtasks: bool = False,
):
    """List tasks with optional filtering."""
    try:
        return await _run_sync(
            plan_mod.list_tasks, project_path,
            component_id=component_id or None,
            parent_task_id=parent_task_id if parent_task_id != "" else None,
            status=status or None,
            priority=priority or None,
            include_subtasks=include_subtasks,
        )
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.patch("/api/tasks/{task_id}")
async def api_update_task(task_id: str, body: dict):
    """Update mutable task fields."""
    try:
        project_path = body.pop("project_path", "")
        return await _run_sync(plan_mod.update_task, project_path, task_id, **{
            k: v for k, v in body.items()
            if k in {"title", "description", "status", "priority", "component_id", "expects", "tags"}
        })
    except KeyError as e:
        raise HTTPException(404, str(e))
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Progressive knowledge endpoints ─────────────────────────────────────────

@app.get("/api/completeness/{component_id}")
async def get_completeness_single(component_id: str, project_path: str):
    """Completeness score for a single component (0–100)."""
    try:
        return await _run_sync(completeness_mod.score_component, project_path, component_id)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/completeness")
async def get_completeness_all(project_path: str):
    """Completeness scores for all components, sorted ascending (gaps first)."""
    try:
        return await _run_sync(completeness_mod.score_all_components, project_path)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/drill-into")
async def get_drill_into(project_path: str, task: str, start_id: str = ""):
    """Suggest the best L2→L4 component path for a task description."""
    try:
        return await _run_sync(navigation_mod.drill_into, project_path, task, start_id)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


@app.get("/api/knowledge-gaps")
async def get_knowledge_gaps(project_path: str, min_score: int = 70):
    """Surface underdocumented components, unmapped files, and stale symbols."""
    try:
        return await _run_sync(navigation_mod.get_knowledge_gaps, project_path, min_score)
    except ArchMapError as e:
        raise HTTPException(400, str(e))


# ─── Entry point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "api_server:app",
        host="127.0.0.1",
        port=8765,
        log_level="info",
        reload=True,
        reload_dirs=[str(Path(__file__).parent / "archmap")],
    )
