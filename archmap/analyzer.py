"""
Symbol extraction — parse source files and return functions/classes with
line ranges and cyclomatic complexity.

Supports: Python (AST), TypeScript/JavaScript (regex + brace counting).
"""
from __future__ import annotations
import ast
import re
from pathlib import Path


# ─── Entry point ──────────────────────────────────────────────────────────────

def extract_symbols(file_path: str, project_path: str) -> list[dict]:
    """
    Extract top-level and class-level functions/classes from a source file.
    Returns sorted list of {name, kind, line_start, line_end, complexity, docstring}.
    """
    full = Path(project_path) / file_path
    if not full.exists():
        return []

    suffix = full.suffix.lower()
    try:
        content = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if suffix == ".py":
        return _extract_python(content)
    if suffix in (".ts", ".tsx", ".js", ".jsx", ".mts", ".mjs"):
        return _extract_js(content)
    return []


def read_file_content(file_path: str, project_path: str) -> str:
    """Read full file content. Returns empty string on error."""
    try:
        return (Path(project_path) / file_path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ─── Python ───────────────────────────────────────────────────────────────────

def _cyclomatic(node: ast.AST) -> int:
    """Cyclomatic complexity = 1 + decision points within a function/class node."""
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                               ast.With, ast.AsyncWith, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            # and / or — each additional operand is a branch
            complexity += len(child.values) - 1
        elif hasattr(ast, "Match") and isinstance(child, ast.Match):
            complexity += len(child.cases)
    return complexity


def _docstring(node: ast.AST) -> str:
    if (node.body and
            isinstance(node.body[0], ast.Expr) and
            isinstance(node.body[0].value, ast.Constant) and
            isinstance(node.body[0].value.value, str)):
        return node.body[0].value.value.strip()
    return ""


def _extract_python(content: str) -> list[dict]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return []

    symbols: list[dict] = []

    def _visit(nodes, depth: int = 0):
        for node in nodes:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                kind = "async_function" if isinstance(node, ast.AsyncFunctionDef) else "function"
                symbols.append({
                    "name": node.name,
                    "kind": kind,
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "complexity": _cyclomatic(node),
                    "docstring": _docstring(node),
                    "depth": depth,
                })
                # Recurse into class methods
                _visit(node.body, depth + 1)

            elif isinstance(node, ast.ClassDef):
                method_names = [
                    n.name for n in node.body
                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                ]
                symbols.append({
                    "name": node.name,
                    "kind": "class",
                    "line_start": node.lineno,
                    "line_end": getattr(node, "end_lineno", node.lineno),
                    "complexity": 1,
                    "docstring": _docstring(node),
                    "methods": method_names,
                    "depth": depth,
                })
                _visit(node.body, depth + 1)

    _visit(ast.iter_child_nodes(tree))
    return sorted(symbols, key=lambda s: s["line_start"])


# ─── TypeScript / JavaScript ──────────────────────────────────────────────────

# Patterns that identify the start of a symbol.
# Each entry: (regex, kind)
_JS_PATTERNS: list[tuple[re.Pattern, str]] = [
    # export default class Foo / class Foo extends Bar
    (re.compile(r"^(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+(\w+)"), "class"),
    # export function foo / async function foo
    (re.compile(r"^(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s+(\w+)\s*[\(<]"), "function"),
    # export const foo = () => / = async () => / = function
    (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w_$]+)\s*=>"), "function"),
    (re.compile(r"^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?function"), "function"),
    # Method shorthand inside class: foo() { or async foo() {
    (re.compile(r"^\s{2,}(?:(?:public|private|protected|static|async|override|abstract)\s+)*(\w+)\s*\([^)]*\)\s*(?::\s*\S+\s*)?\{"), "method"),
]


def _find_block_end(lines: list[str], start: int) -> int:
    """
    Starting from `start` (0-based), scan forward counting braces until
    the outermost block closes. Returns the 1-based line number of the closing brace.
    """
    depth = 0
    in_string = False
    string_char = ""
    found_open = False

    for i in range(start, len(lines)):
        for ch in lines[i]:
            if in_string:
                if ch == string_char:
                    in_string = False
            else:
                if ch in ('"', "'", "`"):
                    in_string = True
                    string_char = ch
                elif ch == "{":
                    depth += 1
                    found_open = True
                elif ch == "}":
                    depth -= 1
                    if found_open and depth == 0:
                        return i + 1  # 1-based

    return len(lines)  # fallback: end of file


def _js_complexity(lines: list[str], start: int, end: int) -> int:
    """
    Approximate cyclomatic complexity for a JS/TS block by counting
    keywords that indicate branches.
    """
    BRANCH_RE = re.compile(
        r"\b(if|else\s+if|for|while|catch|case|&&|\|\||\?\?)\b"
    )
    complexity = 1
    block = "\n".join(lines[start:end])
    complexity += len(BRANCH_RE.findall(block))
    return complexity


def _extract_js(content: str) -> list[dict]:
    lines = content.split("\n")
    symbols: list[dict] = []
    seen_lines: set[int] = set()

    for i, raw_line in enumerate(lines):
        line = raw_line.strip()
        if not line or line.startswith("//") or line.startswith("*"):
            continue

        for pattern, kind in _JS_PATTERNS:
            m = pattern.match(raw_line)
            if m:
                name = m.group(1)
                if not name or name in ("if", "for", "while", "switch", "return"):
                    continue
                line_start = i + 1  # 1-based
                if line_start in seen_lines:
                    break
                seen_lines.add(line_start)

                line_end = _find_block_end(lines, i)
                complexity = _js_complexity(lines, i, line_end)

                symbols.append({
                    "name": name,
                    "kind": kind,
                    "line_start": line_start,
                    "line_end": line_end,
                    "complexity": complexity,
                    "docstring": "",
                    "depth": 0 if kind != "method" else 1,
                })
                break  # only match one pattern per line

    return symbols
