"""Tests for brief context injection and snapshot updates."""
import tempfile
import time
from pathlib import Path
from archmap.core.store import init_project
from archmap.tree import (
    create_root, add_node, attach_files, get_tree,
    create_task, detect_drift,
    get_brief_context, update_file_snapshot,
)


def _tmp():
    d = tempfile.mkdtemp()
    init_project(d)
    return d


def test_brief_context_mapped_file():
    p = _tmp()
    root = create_root(p, "MyApp", "A test application")
    branch = add_node(p, root.id, "Backend", "Server-side logic")
    leaf = add_node(p, branch.id, "Auth", "Authentication and authorization")
    sibling = add_node(p, branch.id, "Database", "Data persistence")
    fp = Path(p) / "auth.py"
    fp.write_text("# auth")
    sfp = Path(p) / "db.py"
    sfp.write_text("# db")
    attach_files(p, leaf.id, ["auth.py"])
    attach_files(p, sibling.id, ["db.py"])

    result = get_brief_context(p, str(fp))
    assert "[ArchMap] auth.py" in result
    assert "Auth" in result
    assert "MyApp > Backend > Auth" in result
    assert "Authentication and authorization" in result
    assert "Database (db.py)" in result


def test_brief_context_unmapped_file():
    p = _tmp()
    create_root(p, "Root")
    result = get_brief_context(p, "random_file.py")
    assert result == ""


def test_brief_context_includes_user_notes():
    p = _tmp()
    root = create_root(p, "Root")
    from archmap.tree import update_node
    update_node(p, root.id, user_notes="LIFO is deliberate")
    fp = Path(p) / "main.py"
    fp.write_text("# main")
    attach_files(p, root.id, ["main.py"])

    result = get_brief_context(p, str(fp))
    assert "Notes: LIFO is deliberate" in result


def test_brief_context_omits_notes_when_empty():
    p = _tmp()
    root = create_root(p, "Root")
    fp = Path(p) / "main.py"
    fp.write_text("# main")
    attach_files(p, root.id, ["main.py"])

    result = get_brief_context(p, str(fp))
    assert "Notes:" not in result


def test_brief_context_no_tree():
    p = _tmp()
    result = get_brief_context(p, "anything.py")
    assert result == ""


def test_brief_context_includes_active_task():
    p = _tmp()
    root = create_root(p, "Root", "The root")
    fp = Path(p) / "app.py"
    fp.write_text("# app")
    attach_files(p, root.id, ["app.py"])
    create_task(p, "Add feature X", target_node_id=root.id)

    result = get_brief_context(p, str(fp))
    assert "Active task: Add feature X" in result


def test_update_snapshot_clears_drift():
    p = _tmp()
    root = create_root(p, "Root")
    fp = Path(p) / "code.py"
    fp.write_text("v1")
    attach_files(p, root.id, ["code.py"])

    # Modify file to create drift
    import os
    time.sleep(0.05)
    fp.write_text("v2")
    os.utime(fp, (fp.stat().st_atime, fp.stat().st_mtime + 1))
    assert len(detect_drift(p)) == 1

    # Update snapshot should clear drift
    result = update_file_snapshot(p, str(fp))
    assert result is True
    assert len(detect_drift(p)) == 0


def test_update_snapshot_unmapped_file():
    p = _tmp()
    create_root(p, "Root")
    result = update_file_snapshot(p, "nonexistent.py")
    assert result is False
