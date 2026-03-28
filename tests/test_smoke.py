"""
ArchMap smoke tests — uses the archmap project itself as the test fixture.
Run with: pytest tests/test_smoke.py -v
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

PROJECT = str(Path(__file__).parent.parent)


def _comp_id(name: str) -> str:
    """Look up a component ID by name from the live graph."""
    from archmap.architecture import list_components
    for c in list_components(PROJECT):
        if c["name"] == name:
            return c["id"]
    raise KeyError(f"Component not found: {name!r}")


# ── Intelligence ───────────────────────────────────────────────────────────────

def test_describe_architecture_returns_markdown():
    from archmap.intelligence import describe_architecture
    text = describe_architecture(PROJECT)
    assert "## Components by Layer" in text
    assert "Graph Engine" in text
    assert "Storage" in text


def test_describe_architecture_has_entry_points():
    from archmap.intelligence import describe_architecture
    text = describe_architecture(PROJECT)
    assert "Entry Points" in text


def test_find_related_components():
    from archmap.intelligence import find_related
    result = find_related(PROJECT, "storage")
    assert result["query"] == "storage"
    assert any(c["name"] in ("Storage", "Atomic Store") for c in result["components"])


def test_find_related_symbols():
    from archmap.intelligence import find_related
    result = find_related(PROJECT, "mutate")
    # symbols are returned only if the file index has been populated via post_edit_sync
    assert isinstance(result["symbols"], list)
    # if symbols ARE present, they should match the query
    for s in result["symbols"]:
        assert "mutate" in s["symbol"].lower()


def test_find_related_no_results():
    from archmap.intelligence import find_related
    result = find_related(PROJECT, "xyznonexistent123")
    assert result["components"] == []
    assert result["files"] == []
    assert result["symbols"] == []


def test_get_symbol_index_returns_list():
    from archmap.intelligence import get_symbol_index
    index = get_symbol_index(PROJECT)
    assert isinstance(index, list)
    for entry in index[:5]:
        assert "symbol" in entry
        assert "file_path" in entry
        assert "component_id" in entry


def test_trace_path_found():
    from archmap.intelligence import trace_path
    from archmap.architecture import list_components, get_architecture
    # Find any pair with a confirmed dependency between them
    arch = get_architecture(PROJECT)
    deps = [d for d in arch["dependencies"] if d.get("confidence") == "confirmed"]
    if not deps:
        pytest.skip("No confirmed dependencies in graph to trace")
    dep = deps[0]
    result = trace_path(PROJECT, dep["from_component"], dep["to_component"])
    assert result["found"] is True
    assert result["length"] >= 1


def test_trace_path_same_component():
    from archmap.intelligence import trace_path
    cid = _comp_id("Graph Engine")
    result = trace_path(PROJECT, cid, cid)
    assert result["found"] is True
    assert result["length"] == 0


def test_trace_path_not_found():
    from archmap.intelligence import trace_path
    # Atomic Store has no outgoing deps toward the UI (wrong direction)
    from_id = _comp_id("Atomic Store")
    to_id   = _comp_id("React Frontend")
    result  = trace_path(PROJECT, from_id, to_id)
    assert result["found"] is False


# ── Symbols ────────────────────────────────────────────────────────────────────

def test_extract_symbol_python_function():
    from archmap.symbols import extract_symbol
    result = extract_symbol(PROJECT, "archmap/store.py", "mutate_arch")
    assert result["symbol"] == "mutate_arch"
    assert "def mutate_arch" in result["code"]
    assert result["language"] == "python"
    assert result["start_line"] > 0


def test_extract_symbol_python_class():
    from archmap.symbols import extract_symbol
    result = extract_symbol(PROJECT, "archmap/models.py", "Component")
    assert result["symbol"] == "Component"
    assert "Component" in result["code"]
    assert result["language"] == "python"


def test_extract_symbol_not_found_returns_empty():
    from archmap.symbols import extract_symbol
    result = extract_symbol(PROJECT, "archmap/store.py", "nonexistent_xyz")
    assert result["symbol"] == "nonexistent_xyz"
    assert result["code"] == "" or result.get("fallback")


def test_extract_all_symbols_python():
    from archmap.symbols import extract_all_symbols
    result = extract_all_symbols(PROJECT, "archmap/store.py")
    assert result["language"] == "python"
    assert "mutate_arch()" in result["symbols"]
    assert "load_arch()" in result["symbols"]


def test_extract_all_symbols_has_details():
    from archmap.symbols import extract_all_symbols
    result = extract_all_symbols(PROJECT, "archmap/store.py")
    assert len(result["details"]) == len(result["symbols"])
    detail = next(d for d in result["details"] if d["name"] in ("mutate_arch", "mutate_arch()"))
    assert "mutate_arch" in detail["signature"]
    assert isinstance(detail["doc"], str)


def test_extract_all_symbols_python_signatures():
    from archmap.symbols import extract_all_symbols
    result = extract_all_symbols(PROJECT, "archmap/models.py")
    assert "Component" in result["symbols"]
    cls_detail = next((d for d in result["details"] if d["name"] == "Component"), None)
    assert cls_detail is not None
    assert "class Component" in cls_detail["signature"]


def test_extract_all_symbols_typescript():
    from archmap.symbols import extract_all_symbols
    result = extract_all_symbols(PROJECT, "ui/src/store.ts")
    assert result["language"] == "typescript"
    assert len(result["symbols"]) > 0


def test_get_file_content():
    from archmap.symbols import get_file_content
    result = get_file_content(PROJECT, "archmap/store.py")
    assert "file_path" in result
    assert "content" in result
    assert "lines" in result
    assert result["lines"] > 0
    assert "mutate_arch" in result["content"]


def test_get_file_content_not_found():
    from archmap.symbols import get_file_content
    with pytest.raises(FileNotFoundError):
        get_file_content(PROJECT, "nonexistent/file.py")


# ── Impact ─────────────────────────────────────────────────────────────────────

def test_impact_architecture_crud_has_upstream():
    from archmap.impact import get_component_impact
    cid = _comp_id("Architecture CRUD")
    result = get_component_impact(PROJECT, cid)
    assert isinstance(result["upstream"], list)
    assert isinstance(result["downstream"], list)
    assert "impact_score" in result


def test_impact_atomic_store():
    from archmap.impact import get_component_impact
    cid = _comp_id("Atomic Store")
    result = get_component_impact(PROJECT, cid)
    assert "component_name" in result
    assert result["component_name"] == "Atomic Store"
    assert isinstance(result["upstream"], list)
    assert isinstance(result["downstream"], list)


def test_impact_not_found():
    from archmap.impact import get_component_impact
    from archmap.models import NotFoundError
    with pytest.raises(NotFoundError):
        get_component_impact(PROJECT, "comp_doesnotexist")


# ── Metrics ────────────────────────────────────────────────────────────────────

def test_metrics_architecture_crud():
    from archmap.metrics import get_component_metrics
    cid = _comp_id("Architecture CRUD")
    result = get_component_metrics(PROJECT, cid)
    assert result["component_id"] == cid
    assert result["file_count"] > 0
    assert result["total_lines"] > 0
    assert isinstance(result["files"], list)
    for f in result["files"]:
        assert "file_path" in f
        assert "lines" in f
        assert "complexity" in f
        assert "churn" in f
        assert "hotspot" in f


def test_metrics_atomic_store():
    from archmap.metrics import get_component_metrics
    cid = _comp_id("Atomic Store")
    result = get_component_metrics(PROJECT, cid)
    assert result["file_count"] >= 1
    store_file = result["files"][0]
    assert "store.py" in store_file["file_path"]


# ── Architecture CRUD ──────────────────────────────────────────────────────────

def test_list_components_returns_all():
    from archmap.architecture import list_components
    comps = list_components(PROJECT)
    assert len(comps) >= 10
    names = [c["name"] for c in comps]
    assert "Graph Engine" in names
    assert "Storage" in names
    assert "Access Layer" in names


def test_list_components_filter_by_layer():
    from archmap.architecture import list_components
    backend = list_components(PROJECT, layer="backend")
    assert all(c["layer"] == "backend" for c in backend)
    assert len(backend) >= 1


def test_get_architecture_structure():
    from archmap.architecture import get_architecture
    arch = get_architecture(PROJECT)
    assert "components" in arch
    assert "dependencies" in arch
    assert len(arch["components"]) >= 10
    for d in arch["dependencies"]:
        assert "confidence" in d, f"dep {d['id']} missing confidence"
