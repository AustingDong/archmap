"""Tests for the task system."""
import tempfile
from archmap.core.store import init_project
from archmap.tree import (
    create_root, add_node, get_tree,
    create_task, get_active_task, list_tasks,
    activate_next_task, complete_task, reject_task,
    propose_addition, propose_removal,
    approve_proposal, reject_proposal,
)


def _tmp():
    d = tempfile.mkdtemp()
    init_project(d, "Test")
    create_root(d, "TestProject", "A test")
    return d


def test_create_task_auto_activates_first():
    p = _tmp()
    root = get_tree(p)
    t = create_task(p, "Add auth", root.id)
    assert t.status == "active"


def test_second_task_queued():
    p = _tmp()
    root = get_tree(p)
    t1 = create_task(p, "Task 1", root.id)
    t2 = create_task(p, "Task 2", root.id)
    assert t1.status == "active"
    assert t2.status == "queued"


def test_complete_and_activate_next():
    p = _tmp()
    root = get_tree(p)
    t1 = create_task(p, "Task 1", root.id)
    t2 = create_task(p, "Task 2", root.id)
    complete_task(p, t1.id, auto_advance=True)
    active = get_active_task(p)
    assert active is not None
    assert active.id == t2.id


def test_stack_ordering_lifo():
    """Tasks activate in LIFO order — most recently created first (depth-first)."""
    p = _tmp()
    root = get_tree(p)
    t1 = create_task(p, "Branch A", root.id)  # active
    t2 = create_task(p, "Branch B", root.id)  # queued
    t3 = create_task(p, "Deepen A", root.id)  # queued (most recent)
    complete_task(p, t1.id, auto_advance=True)
    active = get_active_task(p)
    assert active is not None
    assert active.id == t3.id, "LIFO: most recently created task should activate first"
    complete_task(p, t3.id, auto_advance=True)
    active = get_active_task(p)
    assert active is not None
    assert active.id == t2.id, "After deepening done, older branch task activates"


def test_propose_addition_creates_grey_node():
    p = _tmp()
    root = get_tree(p)
    task = create_task(p, "Add auth", root.id)
    proposed = propose_addition(p, task.id, root.id, "Auth system", "Handles authentication")
    tree = get_tree(p)
    auth = tree.find(proposed.id)
    assert auth is not None
    assert auth.status == "proposed"
    assert auth.name == "Auth system"


def test_approve_proposed_node():
    p = _tmp()
    root = get_tree(p)
    task = create_task(p, "Add auth", root.id)
    proposed = propose_addition(p, task.id, root.id, "Auth system")
    approved = approve_proposal(p, proposed.id)
    assert approved.status == "confirmed"


def test_reject_proposed_node():
    p = _tmp()
    root = get_tree(p)
    task = create_task(p, "Add auth", root.id)
    proposed = propose_addition(p, task.id, root.id, "Auth system")
    reject_proposal(p, proposed.id)
    tree = get_tree(p)
    assert tree.find(proposed.id) is None


def test_propose_removal():
    p = _tmp()
    root = get_tree(p)
    child = add_node(p, root.id, "Old feature")
    task = create_task(p, "Remove old feature", root.id)
    propose_removal(p, task.id, child.id)
    tree = get_tree(p)
    node = tree.find(child.id)
    assert node.status == "removing"


def test_approve_removal():
    p = _tmp()
    root = get_tree(p)
    child = add_node(p, root.id, "Old feature")
    task = create_task(p, "Remove old feature", root.id)
    propose_removal(p, task.id, child.id)
    approve_proposal(p, child.id)
    tree = get_tree(p)
    assert tree.find(child.id) is None


def test_reject_removal_reverts():
    p = _tmp()
    root = get_tree(p)
    child = add_node(p, root.id, "Old feature")
    task = create_task(p, "Remove old feature", root.id)
    propose_removal(p, task.id, child.id)
    reject_proposal(p, child.id)
    tree = get_tree(p)
    node = tree.find(child.id)
    assert node.status == "confirmed"


def test_reject_task_removes_all_proposals():
    p = _tmp()
    root = get_tree(p)
    task = create_task(p, "Add stuff", root.id)
    p1 = propose_addition(p, task.id, root.id, "Node A")
    p2 = propose_addition(p, task.id, root.id, "Node B")
    reject_task(p, task.id)
    tree = get_tree(p)
    assert tree.find(p1.id) is None
    assert tree.find(p2.id) is None


def test_list_tasks():
    p = _tmp()
    root = get_tree(p)
    create_task(p, "Task 1", root.id)
    create_task(p, "Task 2", root.id)
    tasks = list_tasks(p)
    assert len(tasks) == 2
    assert tasks[0].status == "active"
    assert tasks[1].status == "queued"


def test_propose_with_files():
    p = _tmp()
    root = get_tree(p)
    task = create_task(p, "Add auth", root.id)
    proposed = propose_addition(p, task.id, root.id, "Auth", files=["src/auth.py"])
    tree = get_tree(p)
    node = tree.find(proposed.id)
    assert "src/auth.py" in node.files
