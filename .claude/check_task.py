"""Hook script: prints the active task if one exists."""
import json, os, sys

tasks_path = os.path.join(os.environ.get("PROJECT_PATH", "C:/Users/a7don/my_projects/archmap"), ".archmap", "tasks.json")
if not os.path.exists(tasks_path):
    sys.exit(0)

try:
    with open(tasks_path, "r", encoding="utf-8") as f:
        tasks = json.load(f)
    active = [t for t in tasks if t.get("status") == "active"]
    if active:
        desc = active[0]["description"]
        print(f"ArchMap active task: {desc}")
        print("Did you call orient() and get_task() first? If not, do that before editing.")
except Exception:
    pass
