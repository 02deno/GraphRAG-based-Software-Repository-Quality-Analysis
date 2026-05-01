"""Default filesystem locations for pipeline outputs."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from src.utils.repo_slug import filesystem_slug


def cli_dated_results_dir(repo_path: Path) -> Path:
    """Return ``results/<repo_name>_<YYYYMMDD>/``, creating parents as needed.

    Args:
        repo_path: Repository being analyzed.

    Returns:
        Resolved directory path for CLI default outputs.
    """
    folder_name = f"{repo_path.name}_{date.today().strftime('%Y%m%d')}"
    output_dir = Path("results") / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def default_cli_graph_path(repo_path: Path) -> Path:
    """Default graph JSON path for CLI runs."""
    return cli_dated_results_dir(repo_path) / f"{repo_path.name}_graph.json"


def default_cli_visual_summary_path(repo_path: Path) -> Path:
    """Default visual summary text path for CLI runs."""
    return cli_dated_results_dir(repo_path) / f"{repo_path.name}_pipeline_visual_summary.txt"


def new_web_session_results_dir(repo_slug: str | None = None) -> Path:
    """Create a timestamped directory under ``results/`` for web-triggered runs.

    Args:
        repo_slug: Short name for the repository (e.g. ``owner_repo`` from GitHub);
            sanitized and embedded in the folder name.

    Returns:
        Newly created directory path such as
        ``results/web_analysis_<slug>_YYYYMMDD_HHMMSS``.
    """
    slug = filesystem_slug(repo_slug) if repo_slug else "repo"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path("results") / f"web_analysis_{slug}_{stamp}"
    results_dir.mkdir(parents=True, exist_ok=True)
    return results_dir
