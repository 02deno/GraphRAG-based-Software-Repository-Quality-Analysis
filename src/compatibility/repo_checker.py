from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from src.compatibility.check_item import CheckItem

# Extensions used to estimate "primary language" (same set as ``_check_python_primary``).
_TRACKED_SOURCE_GLOBS = ("*.py", "*.js", "*.ts", "*.java", "*.cpp", "*.c", "*.go", "*.rs")

# Below this share of tracked files being ``.py``, the repo is treated as **not
# Python-primary** for this pipeline: weighted checks still run, but the headline
# score is capped under 50% so a Java/Node-only tree cannot read as "good" for
# Python graph extraction.
_MIN_PYTHON_RATIO_FOR_PIPELINE = 0.3


def _directory_has_python_files(path: Path) -> bool:
    """Return True if *path* is a directory containing at least one ``*.py`` file."""
    if not path.is_dir():
        return False
    for _ in path.rglob("*.py"):
        return True
    return False


def _language_source_counts(repo_path: Path) -> Tuple[int, int]:
    """Count ``*.py`` files and all tracked source extensions (for language ratio).

    Returns:
        ``(python_file_count, total_tracked_source_count)``.
    """
    n_py = sum(1 for _ in repo_path.rglob("*.py"))
    n_total = 0
    for ext in _TRACKED_SOURCE_GLOBS:
        n_total += sum(1 for _ in repo_path.rglob(ext))
    return n_py, n_total


class RepoCompatibilityChecker:
    """Weighted checklist scoring how well a repo fits the Python graph pipeline."""

    def __init__(self) -> None:
        """Load the default ordered list of checks and scoring weights."""
        self.checks = self._define_checks()

    def _define_checks(self) -> List[Dict[str, Any]]:
        """Build check descriptors bound to this instance's handler methods.

        Returns:
            List of dicts with keys ``name``, ``description``, ``weight``, ``check_fn``,
            and ``explanation`` (help text for the UI).
        """
        return [
            {
                "name": "python_primary",
                "description": "Primary language is Python",
                "weight": 0.25,
                "check_fn": self._check_python_primary,
                "explanation": (
                    "Compares counts of ``.py`` files to other common source extensions "
                    "(``.js``, ``.java``, ``.go``, …). The check score reflects how "
                    "Python-dominant the tree is; mixed-language repos score lower by design."
                ),
            },
            {
                "name": "src_folder_exists",
                "description": "Python package root (src/, app/, backend/…)",
                "weight": 0.15,
                "check_fn": self._check_src_folder,
                "explanation": (
                    "Looks for a recognizable Python tree root: top-level ``src/``, "
                    "``backend/app`` or ``backend/src`` (full-stack / monorepos), "
                    "top-level ``app/`` with ``.py`` files (common FastAPI layout), or "
                    "substitutes such as ``lib/``. Helps the extractor anchor packages."
                ),
            },
            {
                "name": "tests_folder_exists",
                "description": "tests/ folder (root or service)",
                "weight": 0.10,
                "check_fn": self._check_tests_folder,
                "explanation": (
                    "Detects ``tests/``, ``test/``, or ``specs/`` at the repo root or under "
                    "common service folders (e.g. ``backend/tests``, ``app/tests``) so "
                    "full-stack templates are not penalized for keeping tests next to the API."
                ),
            },
            {
                "name": "static_imports",
                "description": "Mostly static imports (parseable by AST)",
                "weight": 0.20,
                "check_fn": self._check_static_imports,
                "explanation": (
                    "Samples up to 20 Python files and classifies ``import`` / ``from`` lines "
                    "versus dynamic patterns (``importlib``, ``__import__``, etc.). Static "
                    "imports resolve more reliably into IMPORTS edges in the graph. "
                    "Fails when there are no Python files to sample."
                ),
            },
            {
                "name": "package_structure",
                "description": "Reasonable package structure",
                "weight": 0.10,
                "check_fn": self._check_package_structure,
                "explanation": (
                    "Uses ``__init__.py`` presence relative to all ``.py`` files as a proxy "
                    "for package layout. Flat script-only trees score lower; many packages "
                    "with inits score higher (capped at 1.0). Requires Python sources."
                ),
            },
            {
                "name": "repo_size_manageable",
                "description": "Repository size is manageable",
                "weight": 0.10,
                "check_fn": self._check_repo_size,
                "explanation": (
                    "Counts Python files across the tree. Very large codebases may be slow "
                    "or noisy for a local AST pass; tiny repos may lack structure. Buckets "
                    "map to partial or full credit."
                ),
            },
            {
                "name": "has_requirements",
                "description": "Has requirements.txt or setup.py",
                "weight": 0.05,
                "check_fn": self._check_requirements,
                "explanation": (
                    "Looks at the repo root for ``requirements.txt``, ``setup.py``, "
                    "``pyproject.toml``, or ``Pipfile``. This pipeline expects Python "
                    "packaging hints, not e.g. ``package.json`` alone."
                ),
            },
            {
                "name": "readme_exists",
                "description": "README file exists",
                "weight": 0.05,
                "check_fn": self._check_readme,
                "explanation": (
                    "Checks for common README filenames at the root. Documentation presence "
                    "is a weak proxy for maturity; it does not directly affect graph edges."
                ),
            },
        ]

    def analyze_repository(self, repo_path: str) -> Dict[str, Any]:
        """Run all checks, aggregate weighted scores, and collect warnings.

        Args:
            repo_path: Filesystem path to the repository root (string or path-like).

        Returns:
            Dict with ``score`` (0–100), ``passed`` (>=50), ``details`` (``CheckItem`` list),
            ``warnings`` (str messages), and ``repo_path`` (resolved string).

        Raises:
            ValueError: If *repo_path* does not exist on disk.
        """
        resolved = Path(repo_path).resolve()

        if not resolved.exists():
            raise ValueError(f"Repository path does not exist: {resolved}")

        results: List[CheckItem] = []
        total_weight = 0.0
        total_score = 0.0
        warnings: List[str] = []

        for check in self.checks:
            try:
                passed, score, warning = check["check_fn"](resolved)
                weight = float(check["weight"])

                check_result = CheckItem(
                    name=check["name"],
                    description=check["description"],
                    weight=weight,
                    passed=passed,
                    score=score,
                    explanation=str(check.get("explanation", "")),
                    result_note=str(warning or ""),
                )

                results.append(check_result)
                total_weight += weight
                total_score += score * weight

            except Exception as exc:
                weight = float(check["weight"])
                err_msg = f"Error checking {check['name']}: {exc!s}"
                check_result = CheckItem(
                    name=check["name"],
                    description=check["description"],
                    weight=weight,
                    passed=False,
                    score=0.0,
                    explanation=(
                        "This check failed with an internal error and is scored at 0. "
                        "See warnings above for the exception message."
                    ),
                    result_note=err_msg,
                )
                results.append(check_result)
                total_weight += weight
                warnings.append(err_msg)

        # Per-check ``score`` is in [0, 1]; aggregate as a weighted mean, then scale to %.
        final_score = (total_score / total_weight * 100) if total_weight > 0 else 0.0

        n_py, n_tracked = _language_source_counts(resolved)
        py_ratio = (n_py / n_tracked) if n_tracked > 0 else 0.0

        if n_tracked == 0:
            warnings.insert(
                0,
                "No tracked source files (``.py``, ``.java``, …) found; graph extraction "
                "targets Python. Overall compatibility is capped below 50%.",
            )
            final_score = min(final_score, 49.0)
        elif n_py == 0:
            warnings.insert(
                0,
                "No ``.py`` files found in the repository. This pipeline builds graphs from "
                "Python sources only. Overall compatibility is capped below 50%.",
            )
            final_score = min(final_score, 49.0)
        elif py_ratio < _MIN_PYTHON_RATIO_FOR_PIPELINE:
            warnings.insert(
                0,
                f"Python is not the primary language (``.py`` share {py_ratio:.0%} among "
                f"tracked sources, below {_MIN_PYTHON_RATIO_FOR_PIPELINE:.0%}). "
                "Overall compatibility is capped below 50% because graph analysis is "
                "Python-focused.",
            )
            final_score = min(final_score, 49.0)

        final_score = round(final_score, 1)

        return {
            "score": final_score,
            "passed": final_score >= 50,
            "details": results,
            "warnings": warnings,
            "repo_path": str(resolved),
        }

    def _check_python_primary(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Estimate whether Python dominates the repository by file counts.

        Args:
            repo_path: Root of the repository to scan.

        Returns:
            ``(passed, contribution 0..1, warning_or_empty)`` for the weighted scorer.
        """
        py_files_count, total_count = _language_source_counts(repo_path)

        if not total_count:
            return False, 0.0, "No source files found"

        py_ratio = py_files_count / total_count

        if py_ratio >= 0.7:
            return True, py_ratio, ""
        if py_ratio >= 0.3:
            return True, py_ratio * 0.7, "Mixed language repository"
        return False, py_ratio * 0.3, "Python is not the primary language"

    def _check_src_folder(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Detect a conventional or monorepo Python package root.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        if (repo_path / "src").is_dir():
            return True, 1.0, "Found top-level src/"

        backend = repo_path / "backend"
        if backend.is_dir():
            for name in ("app", "src"):
                child = backend / name
                if child.is_dir() and _directory_has_python_files(child):
                    return True, 0.95, f"Found backend/{name}/ with Python sources (monorepo)"
            if _directory_has_python_files(backend):
                return True, 0.85, "Found backend/ with Python sources (no dedicated app/ or src/ subfolder)"

        app_root = repo_path / "app"
        if app_root.is_dir() and _directory_has_python_files(app_root):
            return True, 0.9, "Found top-level app/ with Python sources (e.g. FastAPI service)"

        common_folders = ["lib", "source", "code"]
        for folder in common_folders:
            if (repo_path / folder).is_dir():
                return True, 0.8, f"Found {folder}/ folder instead of src/"

        return False, 0.0, "No src/, backend/app, backend/src, or app/ with Python sources found"

    def _check_tests_folder(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Detect test directories at repo root or under common Python service paths.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        relative_candidates = (
            "tests",
            "test",
            "specs",
            "backend/tests",
            "backend/test",
            "backend/app/tests",
            "backend/src/tests",
            "src/tests",
            "app/tests",
            "server/tests",
            "api/tests",
        )
        for rel in relative_candidates:
            candidate = repo_path / rel
            if candidate.is_dir():
                return True, 1.0, f"Found {rel}/"

        return (
            False,
            0.0,
            "No tests/, backend/tests/, app/tests/, or similar test directory found",
        )

    def _check_static_imports(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Heuristically measure static ``import`` / ``from`` lines in a small sample.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        py_files = list(repo_path.rglob("*.py"))[:20]

        if not py_files:
            return False, 0.0, "No Python files found — cannot assess import style"

        static_imports = 0
        total_imports = 0
        dynamic_patterns = ["importlib", "__import__", "getattr", "hasattr"]

        for py_file in py_files:
            try:
                content = py_file.read_text(encoding="utf-8")
                for raw_line in content.split("\n"):
                    line = raw_line.strip()
                    if line.startswith(("import ", "from ")):
                        total_imports += 1
                        if not any(pattern in line for pattern in dynamic_patterns):
                            static_imports += 1
            except (OSError, UnicodeDecodeError):
                continue

        if total_imports == 0:
            return True, 0.8, "No imports found"

        static_ratio = static_imports / total_imports

        if static_ratio >= 0.9:
            return True, static_ratio, ""
        if static_ratio >= 0.7:
            return True, static_ratio * 0.8, "Some dynamic imports detected"
        return False, static_ratio * 0.6, "Many dynamic imports detected"

    def _check_package_structure(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Reward presence of ``__init__.py`` as a proxy for package layout.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        has_init_files = list(repo_path.rglob("__init__.py"))
        py_files = list(repo_path.rglob("*.py"))

        if not py_files:
            return False, 0.0, "No Python files found — cannot assess package layout"

        if has_init_files:
            init_ratio = len(has_init_files) / len(py_files)
            return True, min(init_ratio * 2, 1.0), ""
        return False, 0.3, "No __init__.py files found"

    def _check_repo_size(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Classify repo size by Python file count into manageable buckets.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        py_files = list(repo_path.rglob("*.py"))

        if len(py_files) == 0:
            return False, 0.1, "No Python files — pipeline has nothing to traverse"

        if len(py_files) > 1000:
            return False, 0.3, "Large repository (>1000 Python files)"
        if len(py_files) > 500:
            return True, 0.7, "Medium-large repository (500-1000 files)"
        if len(py_files) > 50:
            return True, 1.0, "Manageable repository size"
        return True, 0.8, "Small repository (<50 files)"

    def _check_requirements(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Detect common Python dependency manifest files at repo root.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        req_files = ["requirements.txt", "setup.py", "pyproject.toml", "Pipfile"]

        for req_file in req_files:
            if (repo_path / req_file).exists():
                return True, 1.0, f"Found {req_file}"

        return False, 0.0, "No Python dependency file found at repository root"

    def _check_readme(self, repo_path: Path) -> Tuple[bool, float, str]:
        """Detect a README file at repo root with common filenames.

        Args:
            repo_path: Root of the repository.

        Returns:
            ``(passed, contribution, warning_or_empty)``.
        """
        readme_files = ["README.md", "README.rst", "README.txt", "readme.md"]

        for readme in readme_files:
            if (repo_path / readme).exists():
                return True, 1.0, f"Found {readme}"

        return False, 0.0, "No README file found"
