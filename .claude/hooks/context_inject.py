"""Pre-edit hook: inject architectural context for the file being edited."""
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

        # Use cwd from hook input (the project being worked on),
        # then CLAUDE_PROJECT_DIR, then derive from script location
        project_path = data.get("cwd", "")
        if not project_path:
            project_path = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if not project_path:
            project_path = str(Path(__file__).resolve().parent.parent.parent)

        # Ensure archmap is importable
        archmap_root = str(Path(__file__).resolve().parent.parent.parent)
        if archmap_root not in sys.path:
            sys.path.insert(0, archmap_root)

        from archmap.core.store import is_initialized
        if not is_initialized(project_path):
            return

        from archmap.context import get_brief_context

        result = get_brief_context(project_path, file_path)
        if result:
            print(result)
    except Exception:
        pass  # Never block the edit


if __name__ == "__main__":
    main()
