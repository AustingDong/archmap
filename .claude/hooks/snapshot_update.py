"""Post-edit hook: update file mtime snapshot to keep drift detection accurate."""
import json
import sys
import os
from pathlib import Path


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        file_path = data.get("tool_input", {}).get("file_path", "")
        if not file_path:
            return

        project_path = data.get("cwd", "")
        if not project_path:
            project_path = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if not project_path:
            project_path = str(Path(__file__).resolve().parent.parent.parent)

        archmap_root = str(Path(__file__).resolve().parent.parent.parent)
        if archmap_root not in sys.path:
            sys.path.insert(0, archmap_root)

        from archmap.core.store import is_initialized
        if not is_initialized(project_path):
            return

        from archmap.context import update_file_snapshot

        update_file_snapshot(project_path, file_path)
    except Exception:
        pass  # Never block


if __name__ == "__main__":
    main()
