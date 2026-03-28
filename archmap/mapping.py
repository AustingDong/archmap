"""
File-to-component mapping operations.
All file paths stored as relative posix strings.
"""
from __future__ import annotations
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from archmap.models import NotFoundError
from archmap.store import load_mappings, mutate_mappings, normalize_path

# ── Source file detection ──────────────────────────────────────────────────────

# Extensions that contain actual source code worth indexing.
SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    # Python
    ".py", ".pyi",
    # TypeScript / JavaScript
    ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs",
    # Web
    ".css", ".scss", ".sass", ".less",
    ".html", ".htm", ".vue", ".svelte",
    # Go / Rust / Java / JVM
    ".go", ".rs", ".java", ".kt", ".kts", ".scala",
    # C family
    ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp", ".hxx",
    # .NET
    ".cs", ".fs", ".vb",
    # Ruby / PHP / Swift / Dart
    ".rb", ".php", ".swift", ".dart",
    # Shell
    ".sh", ".bash", ".zsh", ".fish", ".ps1",
    # Data / API definition (structural code)
    ".sql", ".graphql", ".gql", ".proto",
    # IaC (code that deploys things)
    ".tf", ".hcl",
    # Config-as-code with logic
    ".ex", ".exs", ".erl", ".hs", ".ml", ".mli", ".clj", ".cljs",
    ".r", ".R", ".lua", ".groovy",
})

# Exact filenames that are never source code regardless of extension.
NON_SOURCE_NAMES: frozenset[str] = frozenset({
    # Docs / legal
    "README.md", "readme.md", "CHANGELOG.md", "CHANGELOG", "CHANGES",
    "LICENSE", "LICENSE.md", "LICENSE.txt", "NOTICE", "NOTICE.md",
    "AUTHORS", "CONTRIBUTORS",
    # Config/lock files (data, not code)
    "requirements.txt", "requirements-dev.txt", "requirements-test.txt",
    "package.json", "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "Pipfile", "Pipfile.lock", "poetry.lock", "uv.lock",
    "pyproject.toml", "setup.cfg", "setup.py", ".flake8", ".pylintrc",
    "tsconfig.json", "tsconfig.node.json", "jsconfig.json",
    "vite.config.ts", "vite.config.js", "webpack.config.js",
    "rollup.config.js", "esbuild.config.js", "jest.config.js",
    "prettier.config.js", ".prettierrc", ".eslintrc", ".eslintrc.js",
    ".eslintrc.json", ".babelrc", "babel.config.js",
    "tailwind.config.js", "tailwind.config.ts", "postcss.config.js",
    ".editorconfig", ".gitignore", ".gitattributes", ".npmignore",
    ".dockerignore", "Makefile", "makefile", "GNUmakefile",
    "Dockerfile", "docker-compose.yml", "docker-compose.yaml",
    ".env", ".env.example", ".env.sample", ".env.local",
    "CLAUDE.md", "AGENTS.md", "COPILOT.md",
    ".gitkeep", ".keep", "CODEOWNERS",
})


def is_source_file(file_path: str) -> bool:
    """
    Return True if file_path points to a source code file worth indexing.

    Excludes: documentation, lock files, config files, compiled artefacts,
    generated type declarations, and binary assets.
    Agents and the scanner call this before mapping to keep the graph clean.
    """
    p = Path(file_path)
    name = p.name

    # Exact-name exclusions
    if name in NON_SOURCE_NAMES:
        return False

    # Compiled / generated artefacts
    suffix = p.suffix.lower()
    if suffix in {".pyc", ".pyo", ".class", ".o", ".obj", ".so", ".dylib",
                  ".dll", ".exe", ".wasm", ".map"}:
        return False

    # Generated TypeScript declaration files
    if name.endswith(".d.ts") or name.endswith(".d.mts") or name.endswith(".d.cts"):
        return False

    # Minified bundles
    if ".min." in name:
        return False

    # Binary assets
    if suffix in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp",
                  ".pdf", ".ttf", ".woff", ".woff2", ".eot", ".otf",
                  ".mp3", ".mp4", ".wav", ".ogg", ".zip", ".tar", ".gz"}:
        return False

    return suffix in SOURCE_EXTENSIONS


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


def _file_hash(project_path: str, file_path: str) -> str:
    """Compute sha256 hex digest of file content. Returns '' if file not found."""
    try:
        content = (Path(project_path) / file_path).read_bytes()
        return hashlib.sha256(content).hexdigest()
    except (OSError, FileNotFoundError):
        return ""


def get_staleness_status(project_path: str) -> dict:
    """
    Check which mapped files are stale (content changed since last sync),
    missing (file deleted), or fresh.
    Returns {total, stale: [path], missing: [path], fresh_count: int}
    """
    data = load_mappings(project_path)
    stale: list[str] = []
    missing: list[str] = []
    fresh_count = 0
    root = Path(project_path)

    for fp, rec in data.get("files", {}).items():
        full = root / fp
        if not full.exists():
            missing.append(fp)
            continue
        stored_hash = rec.get("content_hash", "")
        if not stored_hash:
            # No hash yet — treat as stale (needs first sync)
            stale.append(fp)
        else:
            current = hashlib.sha256(full.read_bytes()).hexdigest()
            if current != stored_hash:
                stale.append(fp)
            else:
                fresh_count += 1

    total = len(stale) + len(missing) + fresh_count
    return {
        "total": total,
        "stale": stale,
        "missing": missing,
        "fresh_count": fresh_count,
        "healthy": len(stale) == 0 and len(missing) == 0,
    }


def map_file(
    project_path: str,
    file_path: str,
    component_id: str,
    mapped_by: str = "user",
) -> dict:
    rel = normalize_path(project_path, file_path)
    content_hash = _file_hash(project_path, rel)
    # Detect language from extension
    ext = Path(rel).suffix.lower()
    language = {
        ".py": "python", ".ts": "typescript", ".tsx": "typescript",
        ".js": "javascript", ".jsx": "javascript", ".mjs": "javascript",
        ".go": "go", ".rs": "rust", ".java": "java", ".cs": "csharp",
    }.get(ext, "")

    record = {
        "component_id": component_id,
        "mapped_at": _ts(),
        "mapped_by": mapped_by,
        "content_hash": content_hash,
        "synced_at": "",   # will be populated on first sync_file_symbols call
        "language": language,
        "symbols": [],
        "metadata": {},
    }

    def _mutate(data):
        data.setdefault("files", {})[rel] = record

    mutate_mappings(project_path, _mutate)
    return {"file_path": rel, **record}


def unmap_file(project_path: str, file_path: str) -> str:
    rel = normalize_path(project_path, file_path)

    def _mutate(data):
        files = data.get("files", {})
        if rel not in files:
            raise NotFoundError(f"No mapping for: {rel}")
        del files[rel]

    mutate_mappings(project_path, _mutate)
    return "unmapped"


def get_file_component(project_path: str, file_path: str) -> Optional[dict]:
    rel = normalize_path(project_path, file_path)
    data = load_mappings(project_path)
    record = data.get("files", {}).get(rel)
    if record is None:
        return None
    return {"file_path": rel, **record}


def list_component_files(project_path: str, component_id: str) -> list[dict]:
    data = load_mappings(project_path)
    return [
        {"file_path": fp, **rec}
        for fp, rec in data.get("files", {}).items()
        if rec.get("component_id") == component_id
    ]


def update_file_metadata(project_path: str, file_path: str, metadata: dict) -> dict:
    """
    Merge metadata into a file's record.
    If metadata contains 'symbols' (list of symbol dicts with ids) or
    'functions'/'symbol_details' (legacy), promotes them to top-level symbols.
    Also updates content_hash and synced_at when symbols are refreshed.
    """
    rel = normalize_path(project_path, file_path)
    result: dict = {}

    def _mutate(data):
        files = data.get("files", {})
        if rel not in files:
            raise NotFoundError(f"No mapping for: {rel}")

        rec = files[rel]

        # Handle new-format symbol list
        if "symbols" in metadata and isinstance(metadata["symbols"], list):
            rec["symbols"] = metadata["symbols"]
            rec["synced_at"] = _ts()
            rec["content_hash"] = _file_hash(project_path, rel)
            # Also update language if provided
            if "language" in metadata:
                rec["language"] = metadata["language"]
        else:
            # Legacy path: functions/symbol_details in metadata dict
            # Promote to top-level if present
            legacy_meta = {k: v for k, v in metadata.items()
                           if k not in ("functions", "symbol_details", "language")}
            rec.setdefault("metadata", {}).update(legacy_meta)

            if "language" in metadata:
                rec["language"] = metadata["language"]

            if "symbol_details" in metadata or "functions" in metadata:
                # Upgrade legacy format to top-level symbols
                sym_details = metadata.get("symbol_details", [])
                fn_names = metadata.get("functions", [])
                symbols = []
                if sym_details:
                    import hashlib
                    for sd in sym_details:
                        raw_name = sd["name"].rstrip("()")
                        sym_id = sd.get("id") or ("sym_" + hashlib.sha256(f"{rel}:{raw_name}".encode()).hexdigest()[:12])
                        symbols.append({
                            "id": sym_id,
                            "name": raw_name,
                            "display_name": sd["name"],
                            "kind": sd.get("kind", "class" if sd["name"] == raw_name else "function"),
                            "visibility": sd.get("visibility", "private" if raw_name.startswith("_") else "public"),
                            "is_entry_point": sd.get("is_entry_point", False),
                            "signature": sd.get("signature", ""),
                            "doc": sd.get("doc", ""),
                            "file_path": rel,
                            "component_id": rec.get("component_id", ""),
                        })
                elif fn_names:
                    import hashlib
                    for fn in fn_names:
                        raw_name = fn.rstrip("()")
                        sym_id = "sym_" + hashlib.sha256(f"{rel}:{raw_name}".encode()).hexdigest()[:12]
                        symbols.append({
                            "id": sym_id,
                            "name": raw_name,
                            "display_name": fn,
                            "kind": "class" if fn == raw_name else "function",
                            "visibility": "private" if raw_name.startswith("_") else "public",
                            "is_entry_point": raw_name in {"main", "run", "app", "start", "cli"},
                            "signature": "",
                            "doc": "",
                            "file_path": rel,
                            "component_id": rec.get("component_id", ""),
                        })
                if symbols:
                    rec["symbols"] = symbols
                    rec["synced_at"] = _ts()
                    rec["content_hash"] = _file_hash(project_path, rel)

        result.update({"file_path": rel, **rec})

    mutate_mappings(project_path, _mutate)
    return result


def bulk_map(
    project_path: str,
    mappings: list[dict],  # [{file_path, component_id}]
    mapped_by: str = "user",
    source_only: bool = True,
) -> dict:
    """
    Map multiple files at once.

    source_only (default True): skip non-source files (docs, config, compiled
    artefacts) automatically. Set False to map everything regardless.

    Returns {mapped, skipped, errors}.
    """
    mapped = 0
    skipped: list[str] = []
    errors = []
    for entry in mappings:
        fp = entry.get("file_path", "")
        try:
            if source_only and not is_source_file(fp):
                skipped.append(fp)
                continue
            map_file(project_path, fp, entry["component_id"], mapped_by=mapped_by)
            mapped += 1
        except Exception as e:
            errors.append({"file_path": fp, "error": str(e)})
    return {"mapped": mapped, "skipped": skipped, "errors": errors}


def cleanup_non_source_mappings(project_path: str) -> dict:
    """
    Remove all mapped files that are not source code (docs, config, compiled,
    lock files, etc.). Safe to call at any time — only affects non-source entries.

    Returns {removed: [file_path], kept: int}.
    """
    data = load_mappings(project_path)
    files = data.get("files", {})
    to_remove = [fp for fp in files if not is_source_file(fp)]

    if not to_remove:
        return {"removed": [], "kept": len(files)}

    def _mutate(data):
        f = data.setdefault("files", {})
        for fp in to_remove:
            f.pop(fp, None)

    mutate_mappings(project_path, _mutate)
    return {"removed": to_remove, "kept": len(files) - len(to_remove)}


def list_all_mappings(project_path: str) -> list[dict]:
    data = load_mappings(project_path)
    return [
        {"file_path": fp, **rec}
        for fp, rec in data.get("files", {}).items()
    ]
