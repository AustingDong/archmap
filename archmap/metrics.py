"""
Code quality metrics per component.

Computes per-file and aggregate metrics:
  - Line count
  - Keyword complexity (McCabe-like approximation, no external deps)
  - Git churn (commit count from git log)
  - Hotspot detection (high churn AND high complexity)
"""
from __future__ import annotations
import re
import subprocess
from pathlib import Path

from archmap.mapping import list_component_files

# Branching/complexity keywords per language
_PATTERNS: dict[str, re.Pattern] = {
    "python":     re.compile(r"\b(def|if|elif|for|while|except|with|and|or|lambda|return|yield)\b"),
    "typescript": re.compile(r"\b(function|if|else|for|while|catch|switch|case|return)\b|&&|\|\||\?\?"),
    "javascript": re.compile(r"\b(function|if|else|for|while|catch|switch|case|return)\b|&&|\|\||\?\?"),
}
_DEFAULT_PATTERN = re.compile(r"\b(if|else|for|while|catch|switch|case)\b")

_CHURN_HOTSPOT = 5    # commits threshold
_COMPLEX_HOTSPOT = 20 # keyword count threshold


def _line_count(path: Path) -> int:
    try:
        return len(path.read_text(encoding="utf-8", errors="replace").splitlines())
    except Exception:
        return 0


def _keyword_complexity(path: Path, language: str) -> int:
    """Approximate cyclomatic complexity by counting decision keywords."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        pattern = _PATTERNS.get(language.lower(), _DEFAULT_PATTERN)
        return len(pattern.findall(text))
    except Exception:
        return 0


def _git_churn(project_root: Path, rel_path: str) -> int:
    """Number of unique git commits that touched this file."""
    try:
        result = subprocess.run(
            ["git", "log", "--oneline", "--follow", "--", rel_path],
            cwd=project_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        return sum(1 for line in result.stdout.splitlines() if line.strip())
    except Exception:
        return 0


def get_component_metrics(project_path: str, component_id: str) -> dict:
    """
    Return aggregate + per-file quality metrics for a component.
    """
    root = Path(project_path)
    files = list_component_files(project_path, component_id)

    file_metrics: list[dict] = []
    for f in files:
        fp = root / f["file_path"]
        lang = (f.get("metadata") or {}).get("language", "")
        lines = _line_count(fp)
        complexity = _keyword_complexity(fp, lang)
        churn = _git_churn(root, f["file_path"])
        file_metrics.append({
            "file_path": f["file_path"],
            "lines": lines,
            "complexity": complexity,
            "churn": churn,
            "hotspot": churn >= _CHURN_HOTSPOT and complexity >= _COMPLEX_HOTSPOT,
        })

    n = len(file_metrics) or 1
    total_lines     = sum(m["lines"]      for m in file_metrics)
    total_complexity = sum(m["complexity"] for m in file_metrics)
    total_churn     = sum(m["churn"]      for m in file_metrics)
    avg_complexity  = round(total_complexity / n)

    return {
        "component_id":   component_id,
        "file_count":     len(files),
        "total_lines":    total_lines,
        "avg_complexity": avg_complexity,
        "total_churn":    total_churn,
        "hotspot":        total_churn >= _CHURN_HOTSPOT and avg_complexity >= _COMPLEX_HOTSPOT,
        "files":          file_metrics,
    }
