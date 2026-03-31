"""Tests for auto-deepening and file migration."""
import tempfile
from archmap.core.store import init_project
from archmap.tree import (
    create_root, add_node, list_tasks, create_task,
    complete_task, propose_addition, approve_proposal, attach_files, get_tree,
)


def _tmp():
    d = tempfile.mkdtemp()
    init_project(d)
    return d


def test_approve_proposal_creates_deepening_task():
    p = _tmp()
    root = create_root(p, "Root")
    task = create_task(p, "Test task", target_node_id=root.id)
    proposed = propose_addition(p, task.id, root.id, "New Feature", "Does something")
    # Approve — becomes confirmed directly, and since childless, should create task
    result = approve_proposal(p, proposed.id)
    assert result.status == "confirmed"
    tasks = list_tasks(p)
    deepening = [t for t in tasks if "Propose children for" in t.description]
    assert len(deepening) == 1
    assert proposed.id in deepening[0].target_node_id


def test_approve_with_children_no_deepening_task():
    p = _tmp()
    root = create_root(p, "Root")
    task = create_task(p, "Test task", target_node_id=root.id)
    parent = propose_addition(p, task.id, root.id, "Parent")
    child = propose_addition(p, task.id, parent.id, "Child")
    # Approve parent — it has a child, so no deepening task
    approve_proposal(p, parent.id)
    tasks = list_tasks(p)
    deepening = [t for t in tasks if "Propose children for: Parent" in t.description]
    assert len(deepening) == 0


def test_no_duplicate_deepening_tasks():
    p = _tmp()
    root = create_root(p, "Root")
    task = create_task(p, "Test task", target_node_id=root.id)
    p1 = propose_addition(p, task.id, root.id, "Feature")
    approve_proposal(p, p1.id)
    # First approval creates a deepening task
    tasks1 = [t for t in list_tasks(p) if "Propose children for: Feature" in t.description]
    assert len(tasks1) == 1
    # Approve again (shouldn't happen but test the guard)
    # Simulate by creating another proposal and approving
    task2 = create_task(p, "Another task", target_node_id=root.id)
    p2 = propose_addition(p, task2.id, root.id, "Feature2")
    approve_proposal(p, p2.id)
    # The dedup guard should prevent duplicates for Feature2 too
    tasks2 = [t for t in list_tasks(p) if "Propose children for: Feature2" in t.description]
    assert len(tasks2) == 1


def test_complete_task_creates_deepening_tasks():
    """Completing a task promotes proposed→confirmed; childless ones get deepening tasks."""
    p = _tmp()
    root = create_root(p, "Root")
    task = create_task(p, "Add features", target_node_id=root.id)
    p1 = propose_addition(p, task.id, root.id, "Feature A")
    p2 = propose_addition(p, task.id, root.id, "Feature B")
    # Add a child to p2 so only p1 should get a deepening task
    p2_child = propose_addition(p, task.id, p2.id, "Sub B")
    complete_task(p, task.id)
    tasks = list_tasks(p)
    deepening = [t for t in tasks if "Propose children for" in t.description]
    targets = {t.target_node_id for t in deepening}
    assert p1.id in targets, "Childless Feature A should get a deepening task"
    assert p2.id not in targets, "Feature B has children, should not get a deepening task"


def test_complete_task_no_duplicate_deepening():
    """If a deepening task already exists for a node, complete_task shouldn't create another."""
    p = _tmp()
    root = create_root(p, "Root")
    task = create_task(p, "Add stuff", target_node_id=root.id)
    p1 = propose_addition(p, task.id, root.id, "Module")
    # Manually create a deepening task before completing
    create_task(p, f"Propose children for: Module", target_node_id=p1.id)
    complete_task(p, task.id)
    tasks = list_tasks(p)
    deepening = [t for t in tasks if "Propose children for: Module" in t.description]
    assert len(deepening) == 1, "Should not duplicate deepening tasks"


def test_propose_child_migrates_parent_files():
    """Proposing a child with files that exist on parent migrates them down."""
    p = _tmp()
    root = create_root(p, "Root")
    attach_files(p, root.id, ["a.py", "b.py", "c.py"])
    task = create_task(p, "Deepen root", target_node_id=root.id)
    # Propose child that takes a.py from root
    child = propose_addition(p, task.id, root.id, "Module A", files=["a.py"])
    tree = get_tree(p)
    assert "a.py" not in tree.files  # migrated away from root
    assert "a.py" in tree.find(child.id).files
    assert "b.py" in tree.files  # still on root
    assert "c.py" in tree.files  # still on root


def test_file_global_uniqueness():
    """Each file appears on at most one node in the entire tree."""
    p = _tmp()
    root = create_root(p, "Root")
    a = add_node(p, root.id, "A")
    b = add_node(p, root.id, "B")
    attach_files(p, a.id, ["shared.py"])
    # Now attach same file to B — should move from A
    attach_files(p, b.id, ["shared.py"])
    tree = get_tree(p)
    all_files = []
    for node in tree.walk():
        all_files.extend(node.files)
    assert all_files.count("shared.py") == 1
    assert "shared.py" in tree.find(b.id).files
    assert "shared.py" not in tree.find(a.id).files
