"""
Symbol (function/class) extraction from source files.
Returns the source code of a named function or class given file + symbol name.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path


def extract_symbol(project_path: str, file_path: str, symbol_name: str) -> dict:
    """
    Locate and return the source code of a named function or class.
    Returns: {symbol, file_path, code, start_line, end_line, language, fallback?}
    """
    root = Path(project_path)
    fp = root / file_path
    try:
        source = fp.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return _empty(symbol_name, file_path, "")

    ext = fp.suffix.lower()
    name = symbol_name.rstrip("()")  # strip trailing () if present

    if ext == ".py":
        return _extract_python(source, file_path, name)
    elif ext in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        lang = "typescript" if ext in {".ts", ".tsx"} else "javascript"
        return _extract_ts(source, file_path, name, lang)
    else:
        lines = source.splitlines()
        return {"symbol": name, "file_path": file_path, "code": source,
                "start_line": 1, "end_line": len(lines), "language": ext.lstrip(".")}


def extract_all_symbols(project_path: str, file_path: str) -> dict:
    """
    Extract all top-level functions and classes from a source file.
    Returns: {symbols: [str], language: str}
    Symbol names follow the metadata.functions convention: "name()" for functions, "Name" for classes.
    """
    root = Path(project_path)
    fp = root / file_path
    try:
        source = fp.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return {"symbols": [], "language": ""}

    ext = fp.suffix.lower()

    if ext == ".py":
        return _extract_all_python(source)
    elif ext in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        lang = "typescript" if ext in {".ts", ".tsx"} else "javascript"
        return _extract_all_ts(source, lang)
    else:
        return {"symbols": [], "language": ext.lstrip(".")}


def get_file_content(project_path: str, file_path: str) -> dict:
    root = Path(project_path)
    fp = root / file_path
    try:
        content = fp.read_text(encoding="utf-8", errors="replace")
        return {"file_path": file_path, "content": content, "lines": len(content.splitlines())}
    except (OSError, FileNotFoundError):
        raise FileNotFoundError(f"File not found: {file_path}")


# ── Python ─────────────────────────────────────────────────────────────────────

def _extract_python(source: str, file_path: str, name: str) -> dict:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return _fallback_search(source, file_path, name, "python")

    lines = source.splitlines()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.name == name:
                start = node.lineno - 1   # 0-indexed
                end = getattr(node, "end_lineno", node.lineno + 40)
                code = "\n".join(lines[start:end])
                return {"symbol": name, "file_path": file_path, "code": code,
                        "start_line": node.lineno, "end_line": end, "language": "python"}

    return _fallback_search(source, file_path, name, "python")


# ── TypeScript / JavaScript ────────────────────────────────────────────────────

_TS_DEF = re.compile(
    r"(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function\s+{name}\b|class\s+{name}\b|const\s+{name}\s*[:=(]|"
    r"(?:let|var)\s+{name}\s*[:=(])"
)


def _extract_ts(source: str, file_path: str, name: str, language: str) -> dict:
    lines = source.splitlines()
    pattern = re.compile(
        r"(?:export\s+)?(?:default\s+)?(?:async\s+)?"
        r"(?:function\s+" + re.escape(name) + r"\b"
        r"|class\s+" + re.escape(name) + r"\b"
        r"|const\s+" + re.escape(name) + r"\s*[:=(]"
        r"|(?:let|var)\s+" + re.escape(name) + r"\s*[:=(])"
    )

    for i, line in enumerate(lines):
        if pattern.search(line):
            start = i
            # Brace-depth scan to find the end
            depth = 0
            found_open = False
            end = min(i + 120, len(lines))
            for j in range(i, end):
                opens = lines[j].count("{") + lines[j].count("(")
                closes = lines[j].count("}") + lines[j].count(")")
                if opens > 0:
                    found_open = True
                if found_open:
                    depth += opens - closes
                    if depth <= 0 and j > i:
                        end = j + 1
                        break

            code = "\n".join(lines[start:end])
            return {"symbol": name, "file_path": file_path, "code": code,
                    "start_line": start + 1, "end_line": end, "language": language}

    return _fallback_search(source, file_path, name, language)


# ── Extract-all helpers ────────────────────────────────────────────────────────

def _extract_all_python(source: str) -> dict:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"symbols": [], "language": "python"}
    symbols = []
    for node in tree.body:  # top-level only — not ast.walk
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            symbols.append(f"{node.name}()")
        elif isinstance(node, ast.ClassDef):
            symbols.append(node.name)
    return {"symbols": symbols, "language": "python"}


_TS_ALL_DEF = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var)\s+(\w+)"
)


def _extract_all_ts(source: str, language: str) -> dict:
    symbols = []
    seen: set[str] = set()
    for line in source.splitlines():
        m = _TS_ALL_DEF.match(line.lstrip())
        if m:
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                # Heuristic: class if starts with uppercase, function if lowercase
                symbols.append(name if name[0].isupper() else f"{name}()")
    return {"symbols": symbols, "language": language}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _fallback_search(source: str, file_path: str, name: str, language: str) -> dict:
    """Search for symbol name as substring and return surrounding context."""
    lines = source.splitlines()
    for i, line in enumerate(lines):
        if name in line:
            start = max(0, i - 1)
            end = min(len(lines), i + 50)
            return {"symbol": name, "file_path": file_path,
                    "code": "\n".join(lines[start:end]),
                    "start_line": start + 1, "end_line": end,
                    "language": language, "fallback": True}
    return _empty(name, file_path, language)


def _empty(name: str, file_path: str, language: str) -> dict:
    return {"symbol": name, "file_path": file_path, "code": "",
            "start_line": 0, "end_line": 0, "language": language}
