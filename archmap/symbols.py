"""
Symbol (function/class) extraction from source files.
Returns the source code of a named function or class given file + symbol name.
"""
from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path


def _symbol_id(file_path: str, name: str) -> str:
    """Stable content-addressed ID: same file + name always gives same ID."""
    raw = f"{file_path}:{name}".encode()
    return "sym_" + hashlib.sha256(raw).hexdigest()[:12]


def _detect_visibility(name: str, is_exported: bool = False) -> str:
    """Python: _ prefix = private. TS: no export = private (heuristic)."""
    if name.startswith("_"):
        return "private"
    return "public"


def _detect_entry_point(name: str, kind: str, doc: str = "") -> bool:
    """Heuristic: is this a primary API surface / entry callable?"""
    entry_names = {"main", "run", "app", "start", "create_app", "make_app", "cli", "serve"}
    if name.lower() in entry_names:
        return True
    # Common FastAPI/Flask app factory pattern
    if kind == "function" and name.startswith("create_") and "app" in name.lower():
        return True
    return False


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
    Returns: {symbols: [str], details: [{id, name, display_name, kind, visibility, is_entry_point, signature, doc}], language: str}
    """
    root = Path(project_path)
    fp = root / file_path
    try:
        source = fp.read_text(encoding="utf-8", errors="replace")
    except (OSError, FileNotFoundError):
        return {"symbols": [], "details": [], "language": ""}

    ext = fp.suffix.lower()

    if ext == ".py":
        return _extract_all_python(source, file_path)
    elif ext in {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}:
        lang = "typescript" if ext in {".ts", ".tsx"} else "javascript"
        return _extract_all_ts(source, lang, file_path)
    else:
        return {"symbols": [], "details": [], "language": ext.lstrip(".")}


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

def _py_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Build a compact signature string from an AST function node."""
    args = node.args
    params: list[str] = []
    # positional args with optional annotations
    defaults_offset = len(args.args) - len(args.defaults)
    for i, arg in enumerate(args.args):
        part = arg.arg
        if arg.annotation:
            part += f": {ast.unparse(arg.annotation)}"
        if i >= defaults_offset:
            part += f" = {ast.unparse(args.defaults[i - defaults_offset])}"
        params.append(part)
    if args.vararg:
        params.append(f"*{args.vararg.arg}")
    for kw in args.kwonlyargs:
        params.append(kw.arg)
    if args.kwarg:
        params.append(f"**{args.kwarg.arg}")
    ret = f" -> {ast.unparse(node.returns)}" if node.returns else ""
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    return f"{prefix} {node.name}({', '.join(params)}){ret}"


def _py_docstring(node) -> str:
    """Return the first line of a Python docstring, or ''."""
    if (node.body and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)):
        return node.body[0].value.value.strip().splitlines()[0]
    return ""


def _extract_all_python(source: str, file_path: str = "") -> dict:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return {"symbols": [], "details": [], "language": "python"}
    symbols: list[str] = []
    details: list[dict] = []
    for node in tree.body:  # top-level only
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raw_name = node.name
            display = f"{raw_name}()"
            sig = _py_signature(node)
            doc = _py_docstring(node)
            vis = _detect_visibility(raw_name)
            entry = _detect_entry_point(raw_name, "function", doc)
            sym_id = _symbol_id(file_path, raw_name)
            symbols.append(display)
            details.append({
                "id": sym_id,
                "name": raw_name,
                "display_name": display,
                "kind": "function",
                "visibility": vis,
                "is_entry_point": entry,
                "signature": sig,
                "doc": doc,
            })
        elif isinstance(node, ast.ClassDef):
            raw_name = node.name
            vis = _detect_visibility(raw_name)
            entry = _detect_entry_point(raw_name, "class")
            sym_id = _symbol_id(file_path, raw_name)
            symbols.append(raw_name)
            details.append({
                "id": sym_id,
                "name": raw_name,
                "display_name": raw_name,
                "kind": "class",
                "visibility": vis,
                "is_entry_point": entry,
                "signature": f"class {raw_name}",
                "doc": _py_docstring(node),
            })
    return {"symbols": symbols, "details": details, "language": "python"}


_TS_ALL_DEF = re.compile(
    r"^(?:export\s+)?(?:default\s+)?(?:async\s+)?"
    r"(?:function|class|const|let|var)\s+(\w+)"
)


_TS_JSDOC_LINE = re.compile(r"^\s*\*\s?(.+)")


def _ts_jsdoc_before(lines: list[str], start: int) -> str:
    """Scan upward from start to find a JSDoc comment and return its first description line."""
    i = start - 1
    block: list[str] = []
    while i >= 0 and lines[i].strip() in ("", "*/") or (i >= 0 and lines[i].strip().startswith("*")):
        block.append(lines[i])
        i -= 1
        if i >= 0 and lines[i].strip() == "/**":
            for bl in reversed(block):
                m = _TS_JSDOC_LINE.match(bl)
                if m:
                    return m.group(1).strip()
            break
    return ""


def _extract_all_ts(source: str, language: str, file_path: str = "") -> dict:
    symbols: list[str] = []
    details: list[dict] = []
    seen: set[str] = set()
    lines = source.splitlines()
    for idx, line in enumerate(lines):
        m = _TS_ALL_DEF.match(line.lstrip())
        if m:
            name = m.group(1)
            if name not in seen:
                seen.add(name)
                is_cls = name[0].isupper()
                sym_name = name if is_cls else f"{name}()"
                is_exported = "export" in line
                vis = _detect_visibility(name, is_exported)
                kind = "class" if is_cls else "function"
                entry = _detect_entry_point(name, kind)
                sym_id = _symbol_id(file_path, name)
                sig_line = line.strip().rstrip("{").rstrip("=>").strip()
                doc = _ts_jsdoc_before(lines, idx)
                symbols.append(sym_name)
                details.append({
                    "id": sym_id,
                    "name": name,
                    "display_name": sym_name,
                    "kind": kind,
                    "visibility": vis,
                    "is_entry_point": entry,
                    "signature": sig_line,
                    "doc": doc,
                })
    return {"symbols": symbols, "details": details, "language": language}


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
