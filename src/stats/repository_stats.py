from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path
from typing import Dict, List


def collect_python_files(repo_path: Path) -> List[Path]:
    """Collect all Python files inside the repository path."""
    return [path for path in repo_path.rglob("*.py") if path.is_file()]


def count_loc(file_path: Path) -> int:
    """Count non-empty lines of code in a file."""
    try:
        lines = file_path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return 0
    return sum(1 for line in lines if line.strip())


def analyze_python_file(file_path: Path) -> Dict[str, int]:
    """Count classes, functions, and variable assignments for one file."""
    counts = {"classes": 0, "functions": 0, "variables": 0}
    try:
        source = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except Exception:
        return counts

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            counts["classes"] += 1
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            counts["functions"] += 1
        elif isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign, ast.NamedExpr)):
            counts["variables"] += 1
    return counts


def build_repo_stats(repo_path: Path) -> Dict[str, int]:
    """Build repository-level statistics from Python files."""
    py_files = collect_python_files(repo_path)
    totals = {
        "python_files": len(py_files),
        "lines_of_code": 0,
        "classes": 0,
        "functions": 0,
        "variables": 0,
    }

    for file_path in py_files:
        totals["lines_of_code"] += count_loc(file_path)
        file_counts = analyze_python_file(file_path)
        totals["classes"] += file_counts["classes"]
        totals["functions"] += file_counts["functions"]
        totals["variables"] += file_counts["variables"]
    return totals


def format_stats_report(repo_path: Path, stats: Dict[str, int]) -> str:
    """Format repository statistics as plain text."""
    lines = [
        f"Repository: {repo_path}",
        "",
        f"Python files: {stats['python_files']}",
        f"Lines of code (non-empty): {stats['lines_of_code']}",
        f"Classes: {stats['classes']}",
        f"Functions: {stats['functions']}",
        f"Variables (assignments): {stats['variables']}",
    ]
    return "\n".join(lines) + "\n"


def save_stats_report(report: str, report_path: Path) -> None:
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")


def save_stats_json(stats: Dict[str, int], json_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(stats, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute general Python repository statistics.")
    parser.add_argument("--repo", required=True, help="Path to target repository")
    parser.add_argument(
        "--save-report",
        default="results/repo_stats.txt",
        help="Optional output path for plain text stats report",
    )
    parser.add_argument(
        "--save-json",
        default="results/repo_stats.json",
        help="Optional output path for JSON stats report",
    )
    args = parser.parse_args()

    repo_path = Path(args.repo).resolve()
    stats = build_repo_stats(repo_path)
    report = format_stats_report(repo_path, stats)
    print(report, end="")

    if args.save_report:
        save_stats_report(report, Path(args.save_report).resolve())
        print(f"Text report saved to: {Path(args.save_report).resolve()}")

    if args.save_json:
        save_stats_json(stats, Path(args.save_json).resolve())
        print(f"JSON report saved to: {Path(args.save_json).resolve()}")
