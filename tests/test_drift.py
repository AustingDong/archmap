"""Tests for drift detection — flag nodes whose files changed since last snapshot."""
import os
import tempfile
import time
from pathlib import Path
from archmap.core.store import init_project
from archmap.tree import (
    create_root, add_node, attach_files, get_tree,
    detect_drift,
)


def _tmp():
    d = tempfile.mkdtemp()
    init_project(d)
    return d


def test_attach_records_mtime():
    p = _tmp()
    root = create_root(p, "Root")
    # Create a real file
    fp = Path(p) / "hello.py"
    fp.write_text("print('hi')")
    attach_files(p, root.id, ["hello.py"])
    tree = get_tree(p)
    assert "hello.py" in tree.file_snapshots
    assert tree.file_snapshots["hello.py"] == fp.stat().st_mtime


def test_modified_file_detected():
    p = _tmp()
    root = create_root(p, "Root")
    fp = Path(p) / "app.py"
    fp.write_text("v1")
    attach_files(p, root.id, ["app.py"])
    # Modify the file (ensure mtime changes)
    time.sleep(0.05)
    fp.write_text("v2")
    os.utime(fp, (fp.stat().st_atime, fp.stat().st_mtime + 1))
    drift = detect_drift(p)
    assert len(drift) == 1
    assert drift[0]["node_name"] == "Root"
    assert "app.py" in drift[0]["changed_files"]


def test_missing_file_detected():
    p = _tmp()
    root = create_root(p, "Root")
    fp = Path(p) / "gone.py"
    fp.write_text("bye")
    attach_files(p, root.id, ["gone.py"])
    fp.unlink()
    drift = detect_drift(p)
    assert len(drift) == 1
    assert "gone.py" in drift[0]["missing_files"]


def test_no_drift_when_unchanged():
    p = _tmp()
    root = create_root(p, "Root")
    fp = Path(p) / "stable.py"
    fp.write_text("ok")
    attach_files(p, root.id, ["stable.py"])
    drift = detect_drift(p)
    assert drift == []


def test_backward_compat_no_snapshots():
    """Tree without file_snapshots field loads correctly, no drift reported."""
    p = _tmp()
    root = create_root(p, "Root")
    # Manually remove file_snapshots from stored data
    import json
    tree_path = Path(p) / ".archmap" / "tree.json"
    data = json.loads(tree_path.read_text())
    data.pop("file_snapshots", None)
    tree_path.write_text(json.dumps(data))
    # Should load without error
    tree = get_tree(p)
    assert tree is not None
    assert tree.file_snapshots == {}
    drift = detect_drift(p)
    assert drift == []


def test_detach_clears_snapshot():
    p = _tmp()
    root = create_root(p, "Root")
    fp = Path(p) / "temp.py"
    fp.write_text("x")
    attach_files(p, root.id, ["temp.py"])
    tree = get_tree(p)
    assert "temp.py" in tree.file_snapshots
    from archmap.tree import detach_file
    detach_file(p, root.id, "temp.py")
    tree = get_tree(p)
    assert "temp.py" not in tree.file_snapshots
