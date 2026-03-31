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

        project_path = os.environ.get("CLAUDE_PROJECT_DIR", "")
        if not project_path:
            # Derive from hook script location: .claude/hooks/ → project root
            project_path = str(Path(__file__).resolve().parent.parent.parent)

        if project_path not in sys.path:
            sys.path.insert(0, project_path)

        from archmap.context import get_brief_context

        result = get_brief_context(project_path, file_path)
        if result:
            print(result)
    except Exception:
        pass  # Never block the edit


if __name__ == "__main__":
    main()
