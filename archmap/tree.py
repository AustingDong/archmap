"""
Tree operations — re-export barrel.

Split by purpose:
  tree_crud.py   — node CRUD + file attachment
  tasks.py       — task queue (create, complete, reject, advance)
  proposals.py   — propose/approve/reject (agent gate)
  context.py     — agent context serialization + ASCII rendering + file scanning
"""
# Tree CRUD
from archmap.tree_crud import (  # noqa: F401
    get_tree, create_root, add_node, update_node,
    remove_node, move_node, attach_files, detach_file,
    _file_index,
)

# Task queue
from archmap.tasks import (  # noqa: F401
    list_tasks, get_active_task, create_task, activate_next_task,
    complete_task, reject_task,
)

# Proposals
from archmap.proposals import (  # noqa: F401
    propose_addition, propose_removal, approve_proposal, reject_proposal,
)

# Context & rendering
from archmap.context import (  # noqa: F401
    get_context, render_tree, detect_drift, suggest_files,
    get_brief_context, update_file_snapshot,
)
