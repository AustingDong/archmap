"""
File watcher — auto-syncs symbol metadata when mapped files change on disk.

Uses the watchdog library (pip install watchdog). Falls back gracefully if
watchdog is not installed — the rest of ArchMap continues to work, just
without auto-sync.

Usage (called from api_server.py on startup):
    from archmap.watcher import start_watcher
    start_watcher(project_path, notify_fn)

notify_fn is called with the updated FileMapping dict after each sync.
"""
from __future__ import annotations
import logging
import threading
from pathlib import Path
from typing import Callable

log = logging.getLogger(__name__)

_watchers: dict[str, object] = {}   # project_path → Observer


def start_watcher(project_path: str, notify_fn: Callable[[dict], None]) -> bool:
    """
    Start a background file watcher for the given project.
    Returns True if watchdog is available and the watcher started, False otherwise.
    """
    if project_path in _watchers:
        return True  # already running

    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
    except ImportError:
        log.info("watchdog not installed — auto-sync disabled. Install with: pip install watchdog")
        return False

    from archmap.mapping import list_all_mappings, get_file_component
    from archmap.symbols import extract_all_symbols
    from archmap.mapping import update_file_metadata

    root = Path(project_path).resolve()

    class _Handler(FileSystemEventHandler):
        def __init__(self):
            self._lock = threading.Lock()

        def on_modified(self, event):
            if event.is_directory:
                return
            self._sync(Path(event.src_path))

        def on_created(self, event):
            if event.is_directory:
                return
            self._sync(Path(event.src_path))

        def _sync(self, abs_path: Path):
            try:
                rel = abs_path.relative_to(root).as_posix()
            except ValueError:
                return

            # Only sync if this file is mapped
            mapping = get_file_component(project_path, rel)
            if not mapping:
                return

            with self._lock:
                try:
                    extracted = extract_all_symbols(project_path, rel)
                    metadata = {
                        "functions": extracted["symbols"],
                        "symbol_details": extracted.get("details", []),
                    }
                    if extracted["language"]:
                        metadata["language"] = extracted["language"]
                    updated = update_file_metadata(project_path, rel, metadata)
                    log.info("auto-synced %s (%d symbols)", rel, len(extracted["symbols"]))
                    notify_fn(updated)
                except Exception as e:
                    log.warning("auto-sync failed for %s: %s", rel, e)

    observer = Observer()
    observer.schedule(_Handler(), str(root), recursive=True)
    observer.daemon = True
    observer.start()
    _watchers[project_path] = observer
    log.info("file watcher started for %s", project_path)
    return True


def stop_watcher(project_path: str) -> None:
    observer = _watchers.pop(project_path, None)
    if observer:
        observer.stop()
        observer.join()
