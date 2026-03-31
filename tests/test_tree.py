"""Tests for tree CRUD operations."""
import tempfile
from archmap.core.store import init_project, reset_tree
from archmap.tree import (
    get_tree, create_root, add_node, update_node,
    remove_node, move_node, attach_files, detach_file,
    get_context, render_tree,
)


def _tmp_project():
    d = tempfile.mkdtemp()
    init_project(d)
    return d


def test_create_and_read_tree():
    p = _tmp_project()
    root = create_root(p, "TestProject", "A test project")
    assert root.id
    assert root.name == "TestProject"
    assert root.status == "confirmed"
    tree = get_tree(p)
    assert tree is not None
    assert tree.id == root.id


def test_add_and_find_nodes():
    p = _tmp_project()
    root = create_root(p, "Root")
    a = add_node(p, root.id, "A", "desc A")
    b = add_node(p, root.id, "B")
    c = add_node(p, a.id, "C")
    tree = get_tree(p)
    assert len(tree.children) == 2
    assert tree.children[0].name == "A"
    assert tree.children[0].status == "confirmed"
    assert tree.find(c.id).name == "C"


def test_update_node():
    p = _tmp_project()
    root = create_root(p, "Root")
    a = add_node(p, root.id, "A")
    updated = update_node(p, a.id, name="A2", description="new desc", user_notes="note")
    assert updated.name == "A2"
    assert updated.description == "new desc"
    assert updated.user_notes == "note"


def test_remove_node():
    p = _tmp_project()
    root = create_root(p, "Root")
    a = add_node(p, root.id, "A")
    b = add_node(p, a.id, "B")
    name = remove_node(p, a.id)
    assert name == "A"
    tree = get_tree(p)
    assert len(tree.children) == 0


def test_move_node():
    p = _tmp_project()
    root = create_root(p, "Root")
    a = add_node(p, root.id, "A")
    b = add_node(p, root.id, "B")
    c = add_node(p, a.id, "C")
    move_node(p, c.id, b.id)
    tree = get_tree(p)
    assert len(tree.find(a.id).children) == 0
    assert len(tree.find(b.id).children) == 1


def test_attach_detach_files():
    p = _tmp_project()
    root = create_root(p, "MyApp")
    a = add_node(p, root.id, "Storage")
    attach_files(p, a.id, ["src/store.py", "src/db.py"])
    tree = get_tree(p)
    assert "src/store.py" in tree.children[0].files
    assert "src/db.py" in tree.children[0].files
    detach_file(p, a.id, "src/db.py")
    tree = get_tree(p)
    assert "src/db.py" not in tree.children[0].files


def test_attach_file_moves_from_other_node():
    """Attaching a file to node B that's already on node A moves it."""
    p = _tmp_project()
    root = create_root(p, "Root")
    a = add_node(p, root.id, "A")
    b = add_node(p, root.id, "B")
    attach_files(p, a.id, ["shared.py"])
    attach_files(p, b.id, ["shared.py"])
    tree = get_tree(p)
    assert "shared.py" not in tree.find(a.id).files
    assert "shared.py" in tree.find(b.id).files


def test_get_context():
    p = _tmp_project()
    root = create_root(p, "Root", "root desc")
    a = add_node(p, root.id, "A", "desc A")
    b = add_node(p, root.id, "B", "desc B")
    ctx = get_context(p, a.id)
    assert "Root > A" in ctx
    assert "B" in ctx
    assert a.id in ctx


def test_render_tree():
    p = _tmp_project()
    root = create_root(p, "Root", "top")
    a = add_node(p, root.id, "Child", "sub")
    text = render_tree(p, 1)
    assert "Root" in text
    assert "Child" in text
    assert root.id in text


def test_reset():
    p = _tmp_project()
    create_root(p, "Root")
    reset_tree(p)
    assert get_tree(p) is None
