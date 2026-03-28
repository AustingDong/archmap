"""
Code quality analysis — per-component lint, type, and complexity reporting.

Agents use this to discover actionable issues before and after edits.
Results are injected into get_generation_context so agents always see the
quality state of the component they are about to touch.

Tools:
  lint_files(project_path, file_paths)     → ruff issues per file
  type_check_files(project_path, file_paths) → mypy issues per file
  get_quality_report(project_path, component_id) → full report

Issue severity: "error" | "warning" | "info"
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path

from archmap.mapping import list_component_files
from archmap.metrics import _keyword_complexity, _line_count


# ── Ruff (Python linter / formatter) ─────────────────────────────────────────

def lint_files(project_path: str, file_paths: list[str]) -> list[dict]:
    """
    Run ruff on a list of (relative) Python file paths.
    Returns a list of issue dicts: {file_path, line, col, code, message, severity}.
    Non-Python files are skipped silently.
    """
    root = Path(project_path)
    py_files = [fp for fp in file_paths if fp.endswith(".py")]
    if not py_files:
        return []

    abs_files = [str(root / fp) for fp in py_files]
    try:
        result = subprocess.run(
            ["ruff", "check", "--output-format", "json", "--", *abs_files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        raw = result.stdout.strip()
        if not raw:
            return []
        issues_raw = json.loads(raw)
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return []

    out: list[dict] = []
    for issue in issues_raw:
        fp = issue.get("filename", "")
        # Convert back to relative path
        try:
            rel = str(Path(fp).relative_to(root)).replace("\\", "/")
        except ValueError:
            rel = fp
        code = issue.get("code", "")
        severity = "error" if code and code[0] == "E" else "warning"
        out.append({
            "file_path": rel,
            "line": issue.get("location", {}).get("row", 0),
            "col": issue.get("location", {}).get("column", 0),
            "code": code,
            "message": issue.get("message", ""),
            "severity": severity,
            "url": issue.get("url", ""),
        })
    return out


def lint_format(project_path: str, file_paths: list[str]) -> list[dict]:
    """
    Run ruff format --check to find unformatted Python files.
    Returns one issue per file that would be reformatted.
    """
    root = Path(project_path)
    py_files = [fp for fp in file_paths if fp.endswith(".py")]
    if not py_files:
        return []

    abs_files = [str(root / fp) for fp in py_files]
    try:
        result = subprocess.run(
            ["ruff", "format", "--check", "--quiet", "--", *abs_files],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        # ruff format --check exits 1 if any files would be changed,
        # and prints "Would reformat <path>" lines to stderr.
        issues: list[dict] = []
        for line in result.stderr.splitlines():
            if line.startswith("Would reformat"):
                fp_str = line.removeprefix("Would reformat").strip()
                try:
                    rel = str(Path(fp_str).relative_to(root)).replace("\\", "/")
                except ValueError:
                    rel = fp_str
                issues.append({
                    "file_path": rel,
                    "line": 0,
                    "col": 0,
                    "code": "FORMAT",
                    "message": "File would be reformatted by ruff format",
                    "severity": "warning",
                    "url": "",
                })
        return issues
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ── Mypy (Python type checker) ────────────────────────────────────────────────

def type_check_files(project_path: str, file_paths: list[str]) -> list[dict]:
    """
    Run mypy on a list of (relative) Python file paths.
    Returns a list of issue dicts.
    """
    root = Path(project_path)
    py_files = [fp for fp in file_paths if fp.endswith(".py")]
    if not py_files:
        return []

    abs_files = [str(root / fp) for fp in py_files]
    try:
        result = subprocess.run(
            [
                "mypy",
                "--ignore-missing-imports",
                "--no-error-summary",
                "--show-column-numbers",
                "--",
                *abs_files,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        issues: list[dict] = []
        for line in result.stdout.splitlines():
            # Format: path:line:col: severity: message  [error-code]
            parts = line.split(":", 3)
            if len(parts) < 4:
                continue
            fp_str, lineno_s, col_s, rest = parts
            lineno = int(lineno_s) if lineno_s.strip().isdigit() else 0
            col = int(col_s.strip().split()[0]) if col_s.strip().split()[0].isdigit() else 0
            # rest: " error: message  [code]" or " note: ..."
            rest = rest.strip()
            if ": " not in rest:
                continue
            sev_str, msg = rest.split(": ", 1)
            sev_str = sev_str.strip()
            if sev_str not in ("error", "warning", "note"):
                continue
            code = ""
            if msg.endswith("]") and "[" in msg:
                code = msg[msg.rfind("[") + 1:-1]
                msg = msg[:msg.rfind("[")].strip()
            try:
                rel = str(Path(fp_str.strip()).relative_to(root)).replace("\\", "/")
            except ValueError:
                rel = fp_str.strip()
            issues.append({
                "file_path": rel,
                "line": lineno,
                "col": col,
                "code": code,
                "message": msg,
                "severity": sev_str if sev_str != "note" else "info",
                "url": "",
            })
        return issues
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []


# ── Aggregate quality report ──────────────────────────────────────────────────

def get_quality_report(
    project_path: str,
    component_id: str,
    include_types: bool = False,
) -> dict:
    """
    Full quality report for a component:
      lint_issues      — ruff violations per file
      format_issues    — files that need reformatting
      type_issues      — mypy errors (if include_types=True)
      complexity       — per-file keyword complexity scores
      hotspots         — files that are both complex and have lint issues
      score            — 0-100, 100 = perfect (no issues)
      summary          — one-line text for agents
      fix_priority     — ordered list of files to fix first
    """
    root = Path(project_path)
    files = list_component_files(project_path, component_id)
    file_paths = [f["file_path"] for f in files]

    lint = lint_files(project_path, file_paths)
    fmt = lint_format(project_path, file_paths)
    types = type_check_files(project_path, file_paths) if include_types else []

    all_issues = lint + fmt + types
    issue_count = len(all_issues)
    error_count = sum(1 for i in all_issues if i["severity"] == "error")
    warning_count = sum(1 for i in all_issues if i["severity"] == "warning")

    # Per-file breakdown
    file_map: dict[str, dict] = {}
    for f in files:
        fp = f["file_path"]
        full = root / fp
        lang = f.get("language", "")
        file_map[fp] = {
            "file_path": fp,
            "lines": _line_count(full),
            "complexity": _keyword_complexity(full, lang),
            "lint_issues": [],
            "type_issues": [],
            "format_ok": True,
        }

    for issue in lint:
        fp = issue["file_path"]
        if fp in file_map:
            file_map[fp]["lint_issues"].append(issue)

    for issue in fmt:
        fp = issue["file_path"]
        if fp in file_map:
            file_map[fp]["format_ok"] = False

    for issue in types:
        fp = issue["file_path"]
        if fp in file_map:
            file_map[fp]["type_issues"].append(issue)

    # Hotspots: files with high complexity AND lint issues
    hotspots = [
        fp for fp, m in file_map.items()
        if m["complexity"] > 20 and len(m["lint_issues"]) > 0
    ]

    # Score: start at 100, deduct for errors (5pts) and warnings (1pt), floor 0
    score = max(0, 100 - error_count * 5 - warning_count)

    # Fix priority: errors first, then high-complexity files with warnings
    fix_priority: list[str] = []
    seen: set[str] = set()
    for issue in sorted(all_issues, key=lambda i: (i["severity"] != "error", i["file_path"])):
        fp = issue["file_path"]
        if fp not in seen:
            fix_priority.append(fp)
            seen.add(fp)

    n_files = len(file_paths)
    summary_parts = []
    if error_count:
        summary_parts.append(f"{error_count} error(s)")
    if warning_count:
        summary_parts.append(f"{warning_count} warning(s)")
    if not summary_parts:
        summary_parts.append("no issues")
    summary = f"{n_files} file(s), score {score}/100 — {', '.join(summary_parts)}"

    return {
        "component_id": component_id,
        "file_count": n_files,
        "score": score,
        "error_count": error_count,
        "warning_count": warning_count,
        "issue_count": issue_count,
        "lint_issues": lint,
        "format_issues": fmt,
        "type_issues": types,
        "files": list(file_map.values()),
        "hotspots": hotspots,
        "fix_priority": fix_priority,
        "summary": summary,
    }
